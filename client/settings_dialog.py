"""Диалог настроек клиента: IP, MAC, порт сервера, автопроверка."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QCheckBox,
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

        # --- Сеть ---
        form = QFormLayout()
        form.setSpacing(10)

        self.ip = QLineEdit(str(cfg.get("pc", {}).get("ip", "")))
        self.mac = QLineEdit(str(cfg.get("pc", {}).get("mac", "")))
        self.sport = QSpinBox()
        self.sport.setRange(1, 65535)
        self.sport.setValue(int(cfg.get("server", {}).get("port", 8787)))

        form.addRow("IP компьютера", self.ip)
        form.addRow("MAC (Wake-on-LAN)", self.mac)
        form.addRow("Порт сервера", self.sport)
        layout.addLayout(form)

        # --- Автопроверка ---
        ac = cfg.get("auto_check", {})
        self.auto_enabled = QCheckBox("Автопроверка состояния")
        self.auto_enabled.setChecked(bool(ac.get("enabled", True)))
        self.auto_enabled.setToolTip(
            "Периодически сама проверять, что ПК в сети и каково состояние LM Studio."
        )
        self.auto_interval = QSpinBox()
        self.auto_interval.setRange(1, 3600)
        self.auto_interval.setSuffix(" сек")
        self.auto_interval.setValue(int(ac.get("interval_s", 10)))
        self.auto_interval.setToolTip("Через сколько секунд повторять автопроверку.")

        auto_form = QFormLayout()
        auto_form.setSpacing(10)
        auto_form.addRow("", self.auto_enabled)
        auto_form.addRow("Интервал проверки", self.auto_interval)
        layout.addLayout(auto_form)

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
            "IP компьютера — адрес в локальной сети (на Windows: ipconfig /all).\n"
            "MAC — физический адрес сетевой карты (на Windows: getmac).\n"
            "Сервер работает на том же компьютере, поэтому он использует "
            "этот же IP и указанный здесь порт.",
        )

    def _save(self) -> None:
        ip = self.ip.text().strip()
        mac = self.mac.text().strip()
        if not ip:
            self._warn("Укажите IP компьютера.")
            return
        try:
            mac_norm = normalize_mac(mac)
        except ValueError as exc:
            self._warn(str(exc))
            return
        self._result = self._values()
        self.accept()

    def _values(self) -> dict:
        mac = self.mac.text().strip()
        try:
            mac_norm = normalize_mac(mac)
        except ValueError:
            mac_norm = mac
        return {
            "pc": {"ip": self.ip.text().strip(), "mac": mac_norm},
            "server": {"port": self.sport.value()},
            "auto_check": {
                "enabled": self.auto_enabled.isChecked(),
                "interval_s": self.auto_interval.value(),
            },
        }

    def _warn(self, msg: str) -> None:
        QMessageBox.warning(self, "Проверьте значения", msg)

    def values(self) -> dict:
        return getattr(self, "_result", None) or self._values()
