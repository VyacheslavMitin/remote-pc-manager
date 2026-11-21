"""Точка входа клиента (PySide6 GUI).

Запуск:  python main.py
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

import theme
from app import MainWindow


def main() -> int:
    # Высокий DPI (Windows 11 / macOS retina)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("RPCM Client")
    theme.apply_dark(app)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
