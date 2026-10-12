from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from codex_monitor.main import configure_application_font
from codex_monitor.main_window import MainWindow, REFRESH_INTERVAL_MS, WINDOW_TITLE
from codex_monitor.models import UsageSnapshot
from codex_monitor.reader import CodexUsageReaderOptions


class UiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_window_exposes_local_read_only_metrics_and_refresh_control(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(options=CodexUsageReaderOptions(Path(directory)))
            try:
                self.assertEqual(window.windowTitle(), WINDOW_TITLE)
                self.assertGreaterEqual(REFRESH_INTERVAL_MS, 10_000)
                self.assertEqual(window.refresh_button.accessibleName(), "刷新本地 Codex 数据")
                self.assertEqual(
                    window.consumed_value.toolTip(),
                    "24 小时内 未缓存输入 + 缓存输入 + 输出的精确合计",
                )
                self.assertEqual(window.cache_value.toolTip(), "cached_input_tokens / input_tokens")
                self.assertEqual(window.input_value.toolTip(), "输入 token（不含缓存）")
                self.assertEqual(window.read_only_label.text(), "LOCAL / READ-ONLY")
                self.assertEqual(set(window.window_buttons), {1, 8, 16, 24})
                self.assertTrue(window.window_buttons[24].isChecked())

                window.window_buttons[8].click()

                self.assertEqual(window.selected_window_hours, 8)
                self.assertEqual(window.options.window, timedelta(hours=8))
                self.assertEqual(window.range_label.text(), "8h")
            finally:
                window.close()

    def test_extended_window_dropdown_exposes_longer_ranges(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(options=CodexUsageReaderOptions(Path(directory)))
            try:
                self.assertEqual(
                    [
                        window.range_combo.itemData(index)
                        for index in range(window.range_combo.count())
                    ],
                    [None, 72, 168, 720, 1440, 2160],
                )
                self.assertEqual(window.range_combo.currentIndex(), 0)
                self.assertEqual(
                    [window.range_combo.itemText(index) for index in range(window.range_combo.count())],
                    ["更多…", "3 天", "7 天", "30 天", "60 天", "90 天"],
                )

                window.range_combo.setCurrentIndex(window.range_combo.findData(720))

                self.assertEqual(window.selected_window_hours, 720)
                self.assertEqual(window.options.window, timedelta(hours=720))
                self.assertEqual(window.range_label.text(), "30 天")
                self.assertFalse(
                    any(button.isChecked() for button in window.window_buttons.values())
                )

                window.window_buttons[8].click()

                self.assertEqual(window.selected_window_hours, 8)
                self.assertEqual(window.range_combo.currentIndex(), 0)
            finally:
                window.close()

    def test_long_window_can_be_selected_from_initial_options(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(
                options=CodexUsageReaderOptions(Path(directory), window=timedelta(days=90))
            )
            try:
                self.assertEqual(window.selected_window_hours, 2160)
                self.assertEqual(window.range_combo.currentData(), 2160)
                self.assertEqual(window.range_label.text(), "90 天")
                self.assertFalse(any(button.isChecked() for button in window.window_buttons.values()))
            finally:
                window.close()

    def test_input_metric_displays_input_after_cached_tokens_are_removed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            window = MainWindow(options=CodexUsageReaderOptions(Path(directory)))
            try:
                window.refresh_timer.stop()
                snapshot = UsageSnapshot(
                    input_tokens=300,
                    cached_input_tokens=140,
                    output_tokens=30,
                    event_count=1,
                    scanned_file_count=1,
                    skipped_file_count=0,
                    malformed_line_count=0,
                    last_event_at=datetime.now(timezone.utc),
                    source_directory=Path(directory),
                )

                window._apply_snapshot(snapshot, window.options)

                self.assertEqual(window.input_value.text(), "160")
                self.assertEqual(window.cached_value.text(), "140")
            finally:
                window.close()

    def test_application_font_supports_chinese_ui_text(self) -> None:
        font = configure_application_font(self.application)
        self.assertTrue(font.family())
        self.assertNotEqual(font.family().lower(), "sans serif")


if __name__ == "__main__":
    unittest.main()
