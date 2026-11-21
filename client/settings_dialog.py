"""Диалог настроек клиента: IP, MAC, хост и порт сервера."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QHBoxLayout,
    QMessageBox,
)

from wol import normalize_mac


class SettingsDialog(QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Настройки")
        self.setMinimumWidth(440)
        self._cfg = cfg

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.ip = QLineEdit(str(cfg.get("pc", {}).get("ip", "")))
        self.mac = QLineEdit(str(cfg.get("pc", {}).get("mac", "")))
        self.shost = QLineEdit(str(cfg.get("server", {}).get("host", "")))
        self.sport = QSpinBox()
        self.sport.setRange(1, 65535)
        self.sport.setValue(int(cfg.get("server", {}).get("port", 8787)))

        form.addRow("IP компьютера", self.ip)
        form.addRow("MAC (Wake-on-LAN)", self.mac)
        form.addRow("Хост сервера", self.shost)
        form.addRow("Порт сервера", self.sport)
        layout.addLayout(form)

        hint = QPushButton("ℹ  Как узнать IP и MAC?")
        hint.setFlat(True)
        hint.setStyleSheet("text-align:left; color:#8ab4ff;")
        hint.clicked.connect(self._show_howto)
        layout.addWidget(hint)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton("Отмена")
        cancel.clicked.connect(self.reject)
        save = QPushButton("Сохранить")
        save.setObjectName("primary")
        save.clicked.connect(self._save)
        btns.addWidget(cancel)
        btns.addWidget(save)
        layout.addLayout(btns)

    def _show_howto(self) -> None:
        QMessageBox.information(
            self, "Как узнать IP и MAC",
            "IP компьютера — адрес в локальной сети (на Windows: ipconfig).\n"
            "MAC — физический адрес сетевой карты (на Windows: getmac).\n"
            "Хост/порт сервера — те, что указаны в server/config.json на Windows.",
        )

    def _save(self) -> None:
        ip = self.ip.text().strip()
        mac = self.mac.text().strip()
        shost = self.shost.text().strip()
        if not ip:
            self._warn("Укажите IP компьютера.")
            return
        if not shost:
            self._warn("Укажите хост сервера.")
            return
        try:
            mac_norm = normalize_mac(mac)
        except ValueError as exc:
            self._warn(str(exc))
            return
        self._result = {
            "pc": {"ip": ip, "mac": mac_norm},
            "server": {"host": shost, "port": self.sport.value()},
        }
        self.accept()

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "Проверьте значения", msg)

    def values(self) -> dict:
        return getattr(self, "_result", None) or self._current()

    def _current(self) -> dict:
        return {
            "pc": {"ip": self.ip.text().strip(), "mac": self.mac.text().strip()},
            "server": {"host": self.shost.text().strip(), "port": self.sport.value()},
        }
