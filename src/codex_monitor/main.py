from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from codex_monitor.main_window import MainWindow


def configure_application_font(application: QApplication) -> QFont:
    font_paths = [
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf"),
    ]
    for font_path in font_paths:
        if not font_path.is_file():
            continue
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            continue
        families = QFontDatabase.applicationFontFamilies(font_id)
        if families:
            font = QFont(families[0])
            application.setFont(font)
            return font

    font = QFont("Microsoft YaHei UI")
    application.setFont(font)
    return font


def main() -> int:
    app = QApplication(sys.argv)
    configure_application_font(app)
    app.setApplicationName("Codex 监控面板")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
