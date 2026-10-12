from __future__ import annotations

import unittest
from pathlib import Path


class PackagingContractTests(unittest.TestCase):
    def test_spec_excludes_third_party_icu_that_can_break_qt_on_windows(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        spec = (project_root / "packaging" / "Codex监控面板_win_x64.spec").read_text(encoding="utf-8")
        self.assertIn("a.binaries = [entry for entry in a.binaries", spec)
        self.assertIn('"icuuc.dll"', spec.lower())
        self.assertIn('"icudt78.dll"', spec.lower())


if __name__ == "__main__":
    unittest.main()
