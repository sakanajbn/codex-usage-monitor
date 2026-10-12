from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    event_count: int
    scanned_file_count: int
    skipped_file_count: int
    malformed_line_count: int
    last_event_at: datetime | None
    source_directory: Path
    error_message: str | None = None

    @property
    def consumed_tokens(self) -> int:
        # cached_input_tokens is a subset of input_tokens in the current Codex event format.
        return self.input_tokens + self.output_tokens

    @property
    def uncached_input_tokens(self) -> int:
        return max(self.input_tokens - self.cached_input_tokens, 0)

    @property
    def cache_hit_rate_percent(self) -> float | None:
        if self.input_tokens == 0:
            return None
        return self.cached_input_tokens * 100 / self.input_tokens
