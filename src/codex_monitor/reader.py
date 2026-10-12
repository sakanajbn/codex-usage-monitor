from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import UsageSnapshot


UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class CodexUsageReaderOptions:
    sessions_directory: Path
    window: timedelta = timedelta(hours=24)

    @classmethod
    def default(cls) -> "CodexUsageReaderOptions":
        configured_home = os.environ.get("CODEX_HOME", "").strip()
        codex_home = Path(configured_home).expanduser() if configured_home else Path.home() / ".codex"
        return cls(codex_home / "sessions")


@dataclass(frozen=True, slots=True)
class _UsageEvent:
    timestamp: datetime
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int


@dataclass(slots=True)
class _FileCache:
    size: int
    modified_ns: int
    parsed_offset: int
    pending: bytes
    events: list[_UsageEvent] = field(default_factory=list)
    malformed_line_count: int = 0


class CodexUsageReader:
    """Read Codex token_count events without modifying local Codex files."""

    def __init__(self) -> None:
        self._file_cache: dict[Path, _FileCache] = {}
        self._lock = threading.Lock()

    def read(
        self,
        options: CodexUsageReaderOptions | None = None,
        *,
        now: datetime | None = None,
    ) -> UsageSnapshot:
        options = options or CodexUsageReaderOptions.default()
        current_time = _as_utc(now or datetime.now(UTC))
        start_time = current_time - options.window

        with self._lock:
            return self._read_locked(options, start_time, current_time)

    def _read_locked(
        self,
        options: CodexUsageReaderOptions,
        start_time: datetime,
        current_time: datetime,
    ) -> UsageSnapshot:
        source_directory = options.sessions_directory.expanduser()
        if not source_directory.is_dir():
            self._remove_stale_cache(set())
            return UsageSnapshot(
                input_tokens=0,
                cached_input_tokens=0,
                output_tokens=0,
                event_count=0,
                scanned_file_count=0,
                skipped_file_count=0,
                malformed_line_count=0,
                last_event_at=None,
                source_directory=source_directory,
                error_message="未找到本地 Codex 数据目录",
            )

        paths = sorted(path for path in source_directory.rglob("*.jsonl") if path.is_file())
        self._remove_stale_cache(set(paths))
        events: list[_UsageEvent] = []
        skipped_file_count = 0
        malformed_line_count = 0

        for path in paths:
            try:
                file_cache = self._get_file_cache(path)
            except OSError:
                skipped_file_count += 1
                continue

            malformed_line_count += file_cache.malformed_line_count
            events.extend(file_cache.events)
            provisional_event = _parse_event(file_cache.pending)
            if provisional_event is not None:
                events.append(provisional_event)

        recent_events = (
            event
            for event in events
            if start_time <= event.timestamp <= current_time
        )
        input_tokens = 0
        cached_input_tokens = 0
        output_tokens = 0
        event_count = 0
        last_event_at: datetime | None = None
        for event in recent_events:
            input_tokens += event.input_tokens
            cached_input_tokens += event.cached_input_tokens
            output_tokens += event.output_tokens
            event_count += 1
            if last_event_at is None or event.timestamp > last_event_at:
                last_event_at = event.timestamp

        diagnostics: list[str] = []
        if skipped_file_count:
            diagnostics.append(f"部分文件读取失败：{skipped_file_count} 个文件已跳过")
        if malformed_line_count:
            diagnostics.append(f"已跳过 {malformed_line_count} 行无效记录")

        return UsageSnapshot(
            input_tokens=input_tokens,
            cached_input_tokens=cached_input_tokens,
            output_tokens=output_tokens,
            event_count=event_count,
            scanned_file_count=len(paths),
            skipped_file_count=skipped_file_count,
            malformed_line_count=malformed_line_count,
            last_event_at=last_event_at,
            source_directory=source_directory,
            error_message="；".join(diagnostics) if diagnostics else None,
        )

    def _get_file_cache(self, path: Path) -> _FileCache:
        stat = path.stat()
        cached = self._file_cache.get(path)
        if cached is not None and stat.st_size == cached.size and stat.st_mtime_ns == cached.modified_ns:
            return cached

        if cached is not None and stat.st_size > cached.size and stat.st_mtime_ns >= cached.modified_ns:
            return self._append_file(path, cached)

        return self._read_file_from_start(path)

    def _read_file_from_start(self, path: Path) -> _FileCache:
        return self._read_file(path, start_offset=0, pending=b"", events=[], malformed_line_count=0)

    def _append_file(self, path: Path, cached: _FileCache) -> _FileCache:
        return self._read_file(
            path,
            start_offset=cached.parsed_offset,
            pending=cached.pending,
            events=list(cached.events),
            malformed_line_count=cached.malformed_line_count,
        )

    def _read_file(
        self,
        path: Path,
        *,
        start_offset: int,
        pending: bytes,
        events: list[_UsageEvent],
        malformed_line_count: int,
    ) -> _FileCache:
        with path.open("rb") as stream:
            stream.seek(start_offset)
            buffer = pending
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                buffer += chunk
                lines = buffer.split(b"\n")
                buffer = lines.pop()
                for line in lines:
                    malformed_line_count += self._consume_line(line, events)

            parsed_offset = stream.tell()

        stat = path.stat()
        return _FileCache(
            size=parsed_offset,
            modified_ns=stat.st_mtime_ns,
            parsed_offset=parsed_offset,
            pending=buffer,
            events=events,
            malformed_line_count=malformed_line_count,
        )

    @staticmethod
    def _consume_line(line: bytes, events: list[_UsageEvent]) -> int:
        if not line.strip():
            return 0
        event = _parse_event(line.rstrip(b"\r"))
        if event is not None:
            events.append(event)
            return 0
        try:
            decoded = line.decode("utf-8")
            json.loads(decoded)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 1
        return 0

    def _remove_stale_cache(self, active_paths: set[Path]) -> None:
        for path in tuple(self._file_cache):
            if path not in active_paths:
                del self._file_cache[path]


def _parse_event(line: bytes) -> _UsageEvent | None:
    if not line or b"token_count" not in line:
        return None
    try:
        payload = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("type") != "event_msg":
        return None
    event_payload = payload.get("payload")
    if not isinstance(event_payload, dict) or event_payload.get("type") != "token_count":
        return None
    info = event_payload.get("info")
    if not isinstance(info, dict):
        return None
    last_usage = info.get("last_token_usage")
    if not isinstance(last_usage, dict):
        return None
    if not any(key in last_usage for key in ("input_tokens", "cached_input_tokens", "output_tokens")):
        return None
    timestamp = _parse_timestamp(payload.get("timestamp"))
    if timestamp is None:
        return None
    input_tokens = _token_value(last_usage.get("input_tokens"))
    cached_input_tokens = _token_value(last_usage.get("cached_input_tokens"))
    output_tokens = _token_value(last_usage.get("output_tokens"))
    if input_tokens == 0 and cached_input_tokens == 0 and output_tokens == 0:
        return None
    total_tokens = _token_value(last_usage.get("total_tokens"))
    if total_tokens:
        # Older Codex logs reported cached input separately; normalize input to the
        # total input implied by the event's authoritative total_tokens field.
        input_tokens = max(input_tokens, max(0, total_tokens - output_tokens))
    return _UsageEvent(
        timestamp=timestamp,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        seconds = value / 1000 if value > 10_000_000_000 else value
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_utc(timestamp)


def _token_value(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return 0


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
