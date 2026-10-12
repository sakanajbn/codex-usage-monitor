from __future__ import annotations

import unittest

from codex_monitor.formatting import format_rate, format_tokens


class FormattingTests(unittest.TestCase):
    def test_formats_token_counts_for_compact_display(self) -> None:
        self.assertEqual(format_tokens(0), "0")
        self.assertEqual(format_tokens(12_345), "12.3K")
        self.assertEqual(format_tokens(1_234_567), "1.23M")
        self.assertEqual(format_tokens(1_234_567_890), "1.23B")

    def test_formats_missing_rate_as_placeholder(self) -> None:
        self.assertEqual(format_rate(None), "--")
        self.assertEqual(format_rate(46.666), "46.7%")


if __name__ == "__main__":
    unittest.main()
