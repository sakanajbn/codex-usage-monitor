from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codex_monitor.models import UsageSnapshot
from codex_monitor.reader import CodexUsageReader, CodexUsageReaderOptions


def token_event(timestamp: datetime, *, input_tokens: int, cached_input_tokens: int,
                output_tokens: int, total_tokens: int | None = None,
                cache_write_input_tokens: int = 0) -> str:
    total_tokens = total_tokens if total_tokens is not None else input_tokens + output_tokens
    return json.dumps(
        {
            "timestamp": timestamp.isoformat().replace("+00:00", "Z"),
            "type": "event_msg",
            "payload": {
                "type": "token_count",
                "info": {
                    "total_token_usage": {
                        "input_tokens": 999999,
                        "cached_input_tokens": 888888,
                        "output_tokens": 777777,
                        "total_tokens": 999999,
                    },
                    "last_token_usage": {
                        "input_tokens": input_tokens,
                        "cached_input_tokens": cached_input_tokens,
                        "cache_write_input_tokens": cache_write_input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                    },
                },
            },
        }
    )


class CodexUsageReaderTests(unittest.TestCase):
    def make_sessions(self) -> tuple[tempfile.TemporaryDirectory[str], Path, datetime]:
        temporary_directory = tempfile.TemporaryDirectory()
        sessions = Path(temporary_directory.name) / "sessions" / "2026" / "08" / "28"
        sessions.mkdir(parents=True)
        now = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
        return temporary_directory, sessions, now

    def test_sums_recent_last_usage_and_ignores_cumulative_snapshot(self) -> None:
        temporary_directory, sessions, now = self.make_sessions()
        try:
            path = sessions / "sample.jsonl"
            path.write_text(
                "\n".join(
                    [
                        token_event(now - timedelta(hours=1), input_tokens=100, cached_input_tokens=40, output_tokens=10),
                        token_event(now - timedelta(minutes=30), input_tokens=200, cached_input_tokens=100, output_tokens=20),
                        token_event(now - timedelta(hours=24, seconds=1), input_tokens=900, cached_input_tokens=900, output_tokens=90),
                        "not json",
                    ]
                ) + "\n",
                encoding="utf-8",
            )

            snapshot = CodexUsageReader().read(CodexUsageReaderOptions(sessions), now=now)

            self.assertIsInstance(snapshot, UsageSnapshot)
            self.assertEqual(snapshot.input_tokens, 300)
            self.assertEqual(snapshot.cached_input_tokens, 140)
            self.assertEqual(snapshot.output_tokens, 30)
            self.assertEqual(snapshot.consumed_tokens, 330)
            self.assertEqual(snapshot.uncached_input_tokens, 160)
            self.assertEqual(snapshot.event_count, 2)
            self.assertEqual(snapshot.malformed_line_count, 1)
            self.assertAlmostEqual(snapshot.cache_hit_rate_percent or 0, 46.6666666667, places=6)
        finally:
            temporary_directory.cleanup()

    def test_excludes_estimated_total_only_events_emitted_during_compaction(self) -> None:
        temporary_directory, sessions, now = self.make_sessions()
        try:
            path = sessions / "compaction.jsonl"
            estimated = {
                "timestamp": (now - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
                "type": "event_msg",
                "payload": {
                    "type": "token_count",
                    "info": {
                        "total_token_usage": {
                            "input_tokens": 999,
                            "cached_input_tokens": 888,
                            "output_tokens": 777,
                            "total_tokens": 2664,
                        },
                        "last_token_usage": {
                            "input_tokens": 0,
                            "cached_input_tokens": 0,
                            "output_tokens": 0,
                            "total_tokens": 31356,
                        },
                    },
                },
            }
            path.write_text(
                "\n".join(
                    [
                        json.dumps(estimated),
                        token_event(now - timedelta(minutes=4), input_tokens=100, cached_input_tokens=80, output_tokens=10),
                    ]
                ) + "\n",
                encoding="utf-8",
            )

            snapshot = CodexUsageReader().read(CodexUsageReaderOptions(sessions), now=now)

            self.assertEqual(snapshot.event_count, 1)
            self.assertEqual(snapshot.input_tokens, 100)
            self.assertEqual(snapshot.cached_input_tokens, 80)
            self.assertEqual(snapshot.output_tokens, 10)
            self.assertEqual(snapshot.consumed_tokens, 110)
        finally:
            temporary_directory.cleanup()

    def test_normalizes_legacy_input_that_reports_cached_tokens_separately(self) -> None:
        temporary_directory, sessions, now = self.make_sessions()
        try:
            path = sessions / "legacy-usage.jsonl"
            path.write_text(
                token_event(
                    now - timedelta(minutes=3),
                    input_tokens=100,
                    cached_input_tokens=40,
                    output_tokens=10,
                    total_tokens=150,
                ) + "\n",
                encoding="utf-8",
            )

            snapshot = CodexUsageReader().read(CodexUsageReaderOptions(sessions), now=now)

            self.assertEqual(snapshot.input_tokens, 140)
            self.assertEqual(snapshot.cached_input_tokens, 40)
            self.assertEqual(snapshot.output_tokens, 10)
            self.assertEqual(snapshot.consumed_tokens, 150)
            self.assertEqual(snapshot.uncached_input_tokens, 100)
            self.assertAlmostEqual(snapshot.cache_hit_rate_percent or 0, 28.5714285714, places=6)
        finally:
            temporary_directory.cleanup()

    def test_supports_selectable_time_windows(self) -> None:
        temporary_directory, sessions, now = self.make_sessions()
        try:
            path = sessions / "windows.jsonl"
            path.write_text(
                "\n".join(
                    [
                        token_event(now - timedelta(minutes=30), input_tokens=10, cached_input_tokens=2, output_tokens=1),
                        token_event(now - timedelta(hours=2), input_tokens=20, cached_input_tokens=4, output_tokens=2),
                        token_event(now - timedelta(hours=9), input_tokens=30, cached_input_tokens=6, output_tokens=3),
                        token_event(now - timedelta(hours=17), input_tokens=40, cached_input_tokens=8, output_tokens=4),
                    ]
                ) + "\n",
                encoding="utf-8",
            )

            reader = CodexUsageReader()
            for hours, expected_events, expected_consumed in (
                (1, 1, 11),
                (8, 2, 33),
                (16, 3, 66),
                (24, 4, 110),
            ):
                snapshot = reader.read(
                    CodexUsageReaderOptions(sessions, window=timedelta(hours=hours)),
                    now=now,
                )
                self.assertEqual(snapshot.event_count, expected_events)
                self.assertEqual(snapshot.consumed_tokens, expected_consumed)
        finally:
            temporary_directory.cleanup()

    def test_handles_missing_directory_and_zero_input(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        try:
            missing = Path(temporary_directory.name) / "missing"
            now = datetime.now(timezone.utc)
            snapshot = CodexUsageReader().read(CodexUsageReaderOptions(missing), now=now)
            self.assertEqual(snapshot.event_count, 0)
            self.assertEqual(snapshot.scanned_file_count, 0)
            self.assertIsNone(snapshot.cache_hit_rate_percent)
            self.assertIn("未找到", snapshot.error_message or "")
        finally:
            temporary_directory.cleanup()

    def test_ignores_future_events_and_non_token_events(self) -> None:
        temporary_directory, sessions, now = self.make_sessions()
        try:
            path = sessions / "sample.jsonl"
            path.write_text(
                "\n".join(
                    [
                        token_event(now + timedelta(seconds=1), input_tokens=100, cached_input_tokens=20, output_tokens=10),
                        json.dumps({"timestamp": now.isoformat(), "type": "response_item", "payload": {"type": "token_count"}}),
                    ]
                ),
                encoding="utf-8",
            )
            snapshot = CodexUsageReader().read(CodexUsageReaderOptions(sessions), now=now)
            self.assertEqual(snapshot.event_count, 0)
            self.assertEqual(snapshot.consumed_tokens, 0)
        finally:
            temporary_directory.cleanup()

    def test_reads_an_appending_file_after_the_initial_scan(self) -> None:
        temporary_directory, sessions, now = self.make_sessions()
        try:
            path = sessions / "live.jsonl"
            path.write_text(token_event(now - timedelta(minutes=1), input_tokens=10, cached_input_tokens=5, output_tokens=1), encoding="utf-8")
            reader = CodexUsageReader()
            options = CodexUsageReaderOptions(sessions)
            first = reader.read(options, now=now)
            with path.open("a", encoding="utf-8") as stream:
                stream.write("\n" + token_event(now, input_tokens=20, cached_input_tokens=10, output_tokens=2))
            second = reader.read(options, now=now)
            self.assertEqual(first.consumed_tokens, 11)
            self.assertEqual(second.consumed_tokens, 33)
            self.assertEqual(second.event_count, 2)
        finally:
            temporary_directory.cleanup()

    def test_resolves_codex_home_from_environment(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        old_value = os.environ.get("CODEX_HOME")
        try:
            os.environ["CODEX_HOME"] = temporary_directory.name
            resolved = CodexUsageReaderOptions.default().sessions_directory
            self.assertEqual(resolved, Path(temporary_directory.name) / "sessions")
        finally:
            if old_value is None:
                os.environ.pop("CODEX_HOME", None)
            else:
                os.environ["CODEX_HOME"] = old_value
            temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
