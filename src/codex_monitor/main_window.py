from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .formatting import format_rate, format_tokens
from .models import UsageSnapshot
from .reader import CodexUsageReader, CodexUsageReaderOptions


WINDOW_TITLE = "Codex 监控面板"
REFRESH_INTERVAL_MS = 15_000
WINDOW_OPTIONS_HOURS = (1, 8, 16, 24)
DROPDOWN_OPTIONS_HOURS = (72, 168, 720, 1440, 2160)
ALLOWED_HOURS = WINDOW_OPTIONS_HOURS + DROPDOWN_OPTIONS_HOURS


class _RefreshSignals(QObject):
    succeeded = Signal(object, object)
    failed = Signal(str, object)


class _RefreshJob(QRunnable):
    def __init__(self, reader: CodexUsageReader, options: CodexUsageReaderOptions) -> None:
        super().__init__()
        self.reader = reader
        self.options = options
        self.signals = _RefreshSignals()

    def run(self) -> None:
        try:
            self.signals.succeeded.emit(self.reader.read(self.options), self.options)
        except Exception as error:  # pragma: no cover - defensive boundary for the UI thread
            self.signals.failed.emit(str(error), self.options)


class MainWindow(QMainWindow):
    def __init__(
        self,
        reader: CodexUsageReader | None = None,
        options: CodexUsageReaderOptions | None = None,
    ) -> None:
        super().__init__()
        self.reader = reader or CodexUsageReader()
        self.options = options or CodexUsageReaderOptions.default()
        self.thread_pool = QThreadPool(self)
        self.refresh_in_flight = False
        self.refresh_requested = False
        self.selected_window_hours = self._resolve_window_hours(self.options.window)
        if self.options.window != self._window_for_hours(self.selected_window_hours):
            self.options = replace(self.options, window=self._window_for_hours(self.selected_window_hours))
        self.window_buttons: dict[int, QToolButton] = {}

        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(720, 440)
        self.resize(840, 520)
        self._build_ui()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(REFRESH_INTERVAL_MS)
        self.refresh_timer.timeout.connect(self.refresh)
        self.refresh_timer.start()
        QTimer.singleShot(0, self.refresh)

    def _build_ui(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget#root { background: #10161c; color: #edf2f6; }
            QFrame#panel {
                background: #18232b;
                border: 1px solid #2d3b46;
                border-radius: 8px;
            }
            QFrame#primaryPanel {
                background: #1a2730;
                border: 1px solid #354752;
                border-radius: 8px;
            }
            QLabel#brand { color: #f5f7f8; font-size: 25px; font-weight: 700; }
            QLabel#subtitle { color: #8fa0ad; font-size: 12px; }
            QLabel#eyebrow { color: #9cabb6; font-size: 11px; font-weight: 600; }
            QLabel#primaryValue { color: #f4f7f8; font-size: 39px; font-weight: 700; }
            QLabel#cacheValue { color: #f4b860; font-size: 39px; font-weight: 700; }
            QLabel#detailValue { color: #eef3f5; font-size: 20px; font-weight: 700; }
            QLabel#detailLabel { color: #8fa0ad; font-size: 11px; }
            QLabel#supporting { color: #8495a1; font-size: 11px; }
            QLabel#rangeCaption { color: #8fa0ad; font-size: 11px; }
            QLabel#rangeValue { color: #f5f7f8; font-size: 12px; font-weight: 700; }
            QLabel#status { color: #86d26d; font-size: 12px; font-weight: 600; }
            QLabel#source { color: #8fa0ad; font-size: 11px; }
            QToolButton#rangeButton {
                background: #1c2931;
                border: 1px solid #3b4d59;
                border-radius: 6px;
                color: #aebbc3;
                min-width: 38px;
                padding: 6px 8px;
            }
            QToolButton#rangeButton:hover { background: #2d414d; color: #f5f7f8; }
            QToolButton#rangeButton:checked {
                background: #68d4d2;
                border-color: #68d4d2;
                color: #102125;
                font-weight: 700;
            }
            QComboBox#rangeCombo {
                background: #1c2931;
                border: 1px solid #3b4d59;
                border-radius: 6px;
                color: #aebbc3;
                min-width: 62px;
                padding: 6px 8px;
            }
            QComboBox#rangeCombo:hover { background: #2d414d; color: #f5f7f8; }
            QComboBox#rangeCombo::drop-down { border: none; width: 18px; }
            QComboBox#rangeCombo QAbstractItemView {
                background: #1c2931;
                border: 1px solid #3b4d59;
                color: #dbe4e9;
                outline: none;
                selection-background-color: #2d414d;
                selection-color: #f5f7f8;
            }
            QToolButton#refreshButton {
                background: #24333d;
                border: 1px solid #3b4d59;
                border-radius: 8px;
                padding: 8px;
            }
            QToolButton#refreshButton:hover { background: #2d414d; }
            QToolButton#refreshButton:pressed { background: #1e2b33; }
            QToolButton#refreshButton:disabled { color: #6c7b84; background: #1c272e; }
            """
        )

        root = QWidget(self)
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header.setSpacing(12)
        brand_column = QVBoxLayout()
        brand_column.setSpacing(3)
        brand = QLabel("Codex 监控面板")
        brand.setObjectName("brand")
        subtitle = QLabel("本地 Codex · 只读统计")
        subtitle.setObjectName("subtitle")
        brand_column.addWidget(brand)
        brand_column.addWidget(subtitle)
        header.addLayout(brand_column)
        header.addStretch(1)

        range_control = QHBoxLayout()
        range_control.setSpacing(5)
        range_caption = QLabel("统计窗口")
        range_caption.setObjectName("rangeCaption")
        self.range_label = QLabel(self._window_label(self.selected_window_hours))
        self.range_label.setObjectName("rangeValue")
        self.range_label.setToolTip("当前统计窗口")
        range_control.addWidget(range_caption)
        range_control.addWidget(self.range_label)
        self.window_group = QButtonGroup(self)
        self.window_group.setExclusive(True)
        for hours in WINDOW_OPTIONS_HOURS:
            button = QToolButton()
            button.setObjectName("rangeButton")
            button.setText(f"{hours}h")
            button.setCheckable(True)
            button.setToolTip(f"统计最近 {hours} 小时")
            button.setAccessibleName(f"选择最近 {hours} 小时")
            button.clicked.connect(lambda _checked=False, value=hours: self._select_window(value))
            self.window_group.addButton(button, hours)
            self.window_buttons[hours] = button
            range_control.addWidget(button)
        if self.selected_window_hours in self.window_buttons:
            self.window_buttons[self.selected_window_hours].setChecked(True)

        self.range_combo = QComboBox()
        self.range_combo.setObjectName("rangeCombo")
        self.range_combo.setToolTip("更多统计窗口")
        self.range_combo.setAccessibleName("选择更多统计窗口")
        self.range_combo.addItem("更多…", None)
        for hours in DROPDOWN_OPTIONS_HOURS:
            self.range_combo.addItem(self._window_label(hours), hours)
        initial_combo_index = self.range_combo.findData(self.selected_window_hours)
        self.range_combo.setCurrentIndex(initial_combo_index if initial_combo_index >= 0 else 0)
        self.range_combo.currentIndexChanged.connect(self._on_combo_changed)
        range_control.addWidget(self.range_combo)
        header.addLayout(range_control)

        self.read_only_label = QLabel("LOCAL / READ-ONLY")
        self.read_only_label.setObjectName("supporting")
        header.addWidget(self.read_only_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        self.refresh_button = QToolButton()
        self.refresh_button.setObjectName("refreshButton")
        self.refresh_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.refresh_button.setToolTip("立即刷新本地 Codex 数据")
        self.refresh_button.setAccessibleName("刷新本地 Codex 数据")
        self.refresh_button.clicked.connect(self.refresh)
        header.addWidget(self.refresh_button)
        layout.addLayout(header)

        primary_row = QHBoxLayout()
        primary_row.setSpacing(14)
        self.consumed_value = QLabel("读取中…")
        self.consumed_value.setObjectName("primaryValue")
        self.consumed_value.setToolTip(self._consumed_tooltip())
        consumed_card, self.consumed_title = self._primary_card(
            f"{self._window_label(self.selected_window_hours)} 消耗 token",
            self.consumed_value,
            "输入（不含缓存） + 缓存 + 输出",
        )
        self.cache_value = QLabel("读取中…")
        self.cache_value.setObjectName("cacheValue")
        self.cache_value.setToolTip("cached_input_tokens / input_tokens")
        cache_card, _cache_title = self._primary_card("缓存命中率", self.cache_value, "缓存输入 / 输入")
        primary_row.addWidget(consumed_card, 1)
        primary_row.addWidget(cache_card, 1)
        layout.addLayout(primary_row)

        details = QGridLayout()
        details.setHorizontalSpacing(14)
        details.setVerticalSpacing(14)
        self.input_value = QLabel("--")
        self.cached_value = QLabel("--")
        self.output_value = QLabel("--")
        self.events_value = QLabel("--")
        detail_specs = [
            ("输入 token（不含缓存）", self.input_value, 0, 0),
            ("缓存 token", self.cached_value, 0, 1),
            ("输出 token", self.output_value, 0, 2),
            ("有效事件", self.events_value, 0, 3),
        ]
        for label, value, row, column in detail_specs:
            details.addWidget(self._detail_card(label, value), row, column)
        for column in range(4):
            details.setColumnStretch(column, 1)
        layout.addLayout(details)

        status_panel = QFrame()
        status_panel.setObjectName("panel")
        status_layout = QVBoxLayout(status_panel)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(5)
        self.status_label = QLabel("正在读取本地 Codex 数据…")
        self.status_label.setObjectName("status")
        self.source_label = QLabel()
        self.source_label.setObjectName("source")
        self.source_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.updated_label = QLabel("")
        self.updated_label.setObjectName("source")
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.source_label)
        status_layout.addWidget(self.updated_label)
        layout.addWidget(status_panel)
        self._set_source_text(self.options.sessions_directory)

    def _primary_card(self, title: str, value: QLabel, supporting: str) -> tuple[QFrame, QLabel]:
        panel = QFrame()
        panel.setObjectName("primaryPanel")
        panel.setMinimumHeight(154)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 18)
        panel_layout.setSpacing(8)
        eyebrow = QLabel(title)
        eyebrow.setObjectName("eyebrow")
        supporting_label = QLabel(supporting)
        supporting_label.setObjectName("supporting")
        panel_layout.addWidget(eyebrow)
        panel_layout.addWidget(value)
        panel_layout.addWidget(supporting_label)
        panel_layout.addStretch(1)
        return panel, eyebrow

    def _detail_card(self, title: str, value: QLabel) -> QFrame:
        panel = QFrame()
        panel.setObjectName("panel")
        panel.setMinimumHeight(86)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(4)
        value.setObjectName("detailValue")
        value.setToolTip(title)
        label = QLabel(title)
        label.setObjectName("detailLabel")
        panel_layout.addWidget(value)
        panel_layout.addWidget(label)
        return panel

    def refresh(self) -> None:
        if self.refresh_in_flight:
            self.refresh_requested = True
            return
        self.refresh_in_flight = True
        self.refresh_button.setEnabled(False)
        self.status_label.setText("正在读取本地 Codex 数据…")
        self.status_label.setStyleSheet("color: #68d4d2;")
        job = _RefreshJob(self.reader, self.options)
        job.signals.succeeded.connect(self._apply_snapshot)
        job.signals.failed.connect(self._show_refresh_error)
        self.thread_pool.start(job)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.refresh_timer.stop()
        self.thread_pool.waitForDone()
        event.accept()

    def _apply_snapshot(self, snapshot: UsageSnapshot, job_options: CodexUsageReaderOptions) -> None:
        if job_options.window != self.options.window:
            self._finish_refresh()
            return

        self.consumed_value.setText(format_tokens(snapshot.consumed_tokens))
        self.consumed_value.setToolTip(self._consumed_tooltip())
        self.cache_value.setText(format_rate(snapshot.cache_hit_rate_percent))
        self.input_value.setText(format_tokens(snapshot.uncached_input_tokens))
        self.cached_value.setText(format_tokens(snapshot.cached_input_tokens))
        self.output_value.setText(format_tokens(snapshot.output_tokens))
        self.events_value.setText(f"{snapshot.event_count:,}")
        self._set_source_text(snapshot.source_directory)
        refreshed_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
        latest_event = (
            snapshot.last_event_at.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            if snapshot.last_event_at is not None
            else "--"
        )
        self.updated_label.setText(f"面板刷新  {refreshed_at}  ·  最近事件  {latest_event}")

        if snapshot.error_message and snapshot.event_count:
            self.status_label.setText(snapshot.error_message)
            self.status_label.setStyleSheet("color: #f4b860;")
        elif snapshot.error_message:
            self.status_label.setText(snapshot.error_message)
            self.status_label.setStyleSheet("color: #e77f7f;")
        elif snapshot.event_count == 0:
            self.status_label.setText(
                f"最近 {self._window_phrase(self.selected_window_hours)}没有有效 token 记录"
            )
            self.status_label.setStyleSheet("color: #f4b860;")
        else:
            self.status_label.setText(f"本地数据正常  ·  {snapshot.scanned_file_count} 个文件")
            self.status_label.setStyleSheet("color: #86d26d;")
        self._finish_refresh()

    def _show_refresh_error(self, message: str, job_options: CodexUsageReaderOptions) -> None:
        if job_options.window != self.options.window:
            self._finish_refresh()
            return
        self.status_label.setText(f"刷新失败：{message}")
        self.status_label.setStyleSheet("color: #e77f7f;")
        self._finish_refresh()

    def _finish_refresh(self) -> None:
        self.refresh_in_flight = False
        self.refresh_button.setEnabled(True)
        if self.refresh_requested:
            self.refresh_requested = False
            QTimer.singleShot(0, self.refresh)

    def _select_window(self, hours: int) -> None:
        if hours not in ALLOWED_HOURS:
            return
        self.selected_window_hours = hours
        self.options = replace(self.options, window=self._window_for_hours(hours))
        self.range_label.setText(self._window_label(hours))
        self.consumed_title.setText(f"{self._window_label(hours)} 消耗 token")
        self.consumed_value.setToolTip(self._consumed_tooltip())
        if hours in self.window_buttons:
            self.window_buttons[hours].setChecked(True)
            self._set_combo_index(0)
        else:
            self._clear_window_buttons()
            combo_index = self.range_combo.findData(hours)
            if combo_index >= 0:
                self._set_combo_index(combo_index)
        self.refresh()

    def _on_combo_changed(self, index: int) -> None:
        hours = self.range_combo.itemData(index)
        if hours is None:
            if self.selected_window_hours not in self.window_buttons:
                combo_index = self.range_combo.findData(self.selected_window_hours)
                if combo_index >= 0:
                    self._set_combo_index(combo_index)
            return
        self._select_window(int(hours))

    def _set_combo_index(self, index: int) -> None:
        self.range_combo.blockSignals(True)
        self.range_combo.setCurrentIndex(index)
        self.range_combo.blockSignals(False)

    def _clear_window_buttons(self) -> None:
        self.window_group.setExclusive(False)
        for button in self.window_buttons.values():
            button.setChecked(False)
        self.window_group.setExclusive(True)

    def _consumed_tooltip(self) -> str:
        return (
            f"{self._window_phrase(self.selected_window_hours)}内 未缓存输入 + 缓存输入 + 输出的精确合计"
        )

    @staticmethod
    def _window_for_hours(hours: int) -> timedelta:
        return timedelta(hours=hours)

    @staticmethod
    def _window_label(hours: int) -> str:
        if hours >= 72 and hours % 24 == 0:
            return f"{hours // 24} 天"
        return f"{hours}h"

    @staticmethod
    def _window_phrase(hours: int) -> str:
        if hours >= 72 and hours % 24 == 0:
            return f"{hours // 24} 天"
        return f"{hours} 小时"

    @staticmethod
    def _resolve_window_hours(window: timedelta) -> int:
        total_seconds = window.total_seconds()
        for hours in ALLOWED_HOURS:
            if total_seconds == hours * 3600:
                return hours
        return 24

    def _set_source_text(self, source: Path) -> None:
        path_text = str(source)
        self.source_label.setText(f"数据源  {path_text}")
        self.source_label.setToolTip(path_text)
