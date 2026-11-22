"""Тёмная тема: Fusion + палитра + QSS. Кроссплатформенно (Qt)."""
from __future__ import annotations

from PySide6.QtGui import QPalette, QColor

QSS = """
/* Фон — только у главного окна; подписи и строка статуса прозрачны,
   чтобы не появлялись тёмные «поля» под статусами и справа от заголовка. */
QWidget { color: #e6e6e6; font-size: 13px; }
QMainWindow, QWidget#central { background-color: #1e1e20; }
QLabel { background-color: transparent; }
QWidget#card { background-color: transparent; }

QLabel#title { font-size: 17px; font-weight: 700; color: #f2f2f4; }
QLabel#rowname { color: #cfcfd4; font-weight: 600; }
QLabel#status { color: #9a9aa2; font-size: 12px; }
QLabel#ip { color: #9a9aa2; font-size: 12px; }
QLabel#dot { font-size: 15px; }

QPushButton#gear {
    background-color: #242428;
    border: 1px solid #3a3a40;
    border-radius: 10px;
    font-size: 27px;
    color: #cfcfd4;
    padding: 0px;
}
QPushButton#gear:hover { background-color: #333338; border-color: #4a4a52; color: #ffffff; }
QPushButton#gear:pressed { background-color: #1e1e22; border-color: #4a4a52; }

QPushButton {
    background-color: #2a2a2e;
    color: #e6e6e6;
    border: 1px solid #3a3a40;
    border-radius: 8px;
    padding: 9px 14px;
}
QPushButton:hover { background-color: #333338; border-color: #4a4a52; }
QPushButton:pressed { background-color: #242428; }
QPushButton:disabled { color: #6f6f76; background-color: #232327; border-color: #2c2c31; }

QPushButton#primary { background-color: #1f6feb; border-color: #2f81f7; color: #ffffff; font-weight: 600; }
QPushButton#primary:hover { background-color: #2f81f7; }
QPushButton#primary:pressed { background-color: #1859c7; }

QPushButton#success { background-color: #1a7f37; border-color: #238636; color: #ffffff; }
QPushButton#success:hover { background-color: #238636; }
QPushButton#success:pressed { background-color: #156429; }

QPushButton#danger { background-color: #b62324; border-color: #da3633; color: #ffffff; }
QPushButton#danger:hover { background-color: #da3633; }
QPushButton#danger:pressed { background-color: #971c1c; }

QLineEdit, QSpinBox {
    background-color: #222226;
    color: #e6e6e6;
    border: 1px solid #3a3a40;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #1f6feb;
    selection-color: #ffffff;
}
QLineEdit:focus, QSpinBox:focus { border-color: #2f81f7; }
QSpinBox::up-button, QSpinBox::down-button { background: #2a2a2e; }

QMessageBox, QDialog { background-color: #202024; }
QToolTip { background-color: #2c2c31; color: #e6e6e6; border: 1px solid #3a3a40; padding: 4px 6px; }

QFrame#block { background-color: #232327; border: 1px solid #34343a; border-radius: 12px; }
QLabel#section { font-size: 14px; font-weight: 700; color: #f2f2f4; padding: 2px 2px 0px 2px; }
QFrame#card { background-color: #2a2a30; border: 1px solid #3a3a40; border-radius: 10px; }
"""


def apply_dark(app) -> None:
    """Применяет тёмную тему к QApplication."""
    app.setStyle("Fusion")

    p = QPalette()
    def set(role, color, group=QPalette.Active):
        p.setColor(group, role, QColor(*color))

    BG = (30, 30, 32)
    BG2 = (36, 36, 40)
    TEXT = (230, 230, 230)
    MUTED = (120, 120, 128)
    ACCENT = (47, 129, 247)

    set(QPalette.Window, BG)
    set(QPalette.WindowText, TEXT)
    set(QPalette.Base, (24, 24, 26))
    set(QPalette.AlternateBase, BG2)
    set(QPalette.Text, TEXT)
    set(QPalette.BrightText, (255, 255, 255))
    set(QPalette.Button, (38, 38, 42))
    set(QPalette.ButtonText, TEXT)
    set(QPalette.ToolTipBase, (44, 44, 49))
    set(QPalette.ToolTipText, TEXT)
    set(QPalette.Highlight, ACCENT)
    set(QPalette.HighlightedText, (255, 255, 255))
    set(QPalette.Link, ACCENT)
    set(QPalette.LinkVisited, (120, 140, 255))
    set(QPalette.PlaceholderText, MUTED)

    # disabled
    set(QPalette.WindowText, MUTED, QPalette.Disabled)
    set(QPalette.Text, MUTED, QPalette.Disabled)
    set(QPalette.ButtonText, MUTED, QPalette.Disabled)

    app.setPalette(p)
    app.setStyleSheet(QSS)
