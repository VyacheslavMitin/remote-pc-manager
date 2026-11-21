"""Главное окно клиента: кнопки и три независимых индикатора состояния."""
from __future__ import annotations

import config
from netcheck import ping_host
from server_api import request as api_request
from settings_dialog import SettingsDialog
from wol import send_wol
from worker import Worker

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMessageBox,
)


class StatusRow(QWidget):
    """Строка: [название] [●] … [кнопка «Проверить»]."""

    def __init__(self, name: str, on_check, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(10)

        name_lbl = QLabel(name)
        name_lbl.setObjectName("rowname")
        name_lbl.setMinimumWidth(96)

        self.dot = QLabel("⚪")
        self.dot.setObjectName("dot")
        self.dot.setToolTip("не проверено")

        self.btn = QPushButton("Проверить")
        self.btn.clicked.connect(lambda: on_check(self))

        h.addWidget(name_lbl)
        h.addWidget(self.dot)
        h.addStretch(1)
        h.addWidget(self.btn)

    def set_state(self, ok: bool | None, tooltip: str = "") -> None:
        if ok is None:
            self.dot.setText("⚪")
        else:
            self.dot.setText("🟢" if ok else "🔴")
        if tooltip:
            self.dot.setToolTip(tooltip)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self._workers: list[Worker] = []

        self.setWindowTitle("Удалённый ПК — менеджер")
        self.setMinimumSize(440, 620)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        title = QLabel("Управление удалённым ПК")
        title.setObjectName("title")
        root.addWidget(title)

        # 1. Wake-on-LAN
        self.btn_wol = QPushButton("⏻  Пробудить ПК (Wake-on-LAN)")
        self.btn_wol.setObjectName("primary")
        self.btn_wol.clicked.connect(self.on_wol)
        root.addWidget(self.btn_wol)

        # 2. Состояние ПК
        self.row_pc = StatusRow("ПК", self.on_check_pc)
        root.addWidget(self.row_pc)

        # 3. Состояние сервера
        self.row_srv = StatusRow("Сервер", self.on_check_server)
        root.addWidget(self.row_srv)

        # 4. Гибернация
        self.btn_hib = QPushButton("🌙  Гибернация")
        self.btn_hib.clicked.connect(self.on_hibernate)
        root.addWidget(self.btn_hib)

        # 5/6. Управление LM Studio
        self.btn_start = QPushButton("▶  Включить LM Studio")
        self.btn_start.setObjectName("success")
        self.btn_start.clicked.connect(self.on_start_lm)
        root.addWidget(self.btn_start)

        self.btn_stop = QPushButton("⏹  Выключить LM Studio")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.on_stop_lm)
        root.addWidget(self.btn_stop)

        # 7. Состояние LM Studio
        self.row_lm = StatusRow("LM Studio", self.on_check_lm)
        root.addWidget(self.row_lm)

        # 8. Настройки
        self.btn_settings = QPushButton("⚙  Настройки")
        self.btn_settings.clicked.connect(self.on_settings)
        root.addWidget(self.btn_settings)

        root.addStretch(1)

        self.status = QLabel("Готов.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root.addWidget(self.status)

    # ---------- инфраструктура ----------
    def _run(self, fn, ok=None, fail=None, on_finish=None) -> Worker:
        """Выполняет fn в фоновом потоке; ok(res)/fail(msg)/on_finish() — колбэки."""
        def _on_ok(res):
            if ok is not None:
                ok(res)
            else:
                self._msg("Готово.")

        def _on_fail(msg):
            if fail is not None:
                fail(msg)
            else:
                self._msg(f"Ошибка: {msg}")

        def _on_finish():
            self._drop(w)
            if on_finish is not None:
                on_finish()

        w = Worker(fn, parent=self)
        w.ok.connect(_on_ok)
        w.fail.connect(_on_fail)
        w.finished.connect(_on_finish)
        self._workers.append(w)
        w.start()
        return w

    def _drop(self, w) -> None:
        if w in self._workers:
            self._workers.remove(w)

    def _msg(self, text: str) -> None:
        self.status.setText(text)

    def _server(self):
        return self.cfg["server"]["host"], self.cfg["server"]["port"]

    # ---------- действия ----------
    def on_wol(self) -> None:
        mac = self.cfg["pc"]["mac"]
        self._msg(f"Отправляю magic packet → {mac} …")

        def _ok(res):
            self._msg(f"✅ Magic packet: {res['to']} (MAC {res['mac']}, ×{res['sent']}).")

        self._run(lambda: send_wol(mac, count=3), ok=_ok)

    def on_check_pc(self, row: StatusRow) -> None:
        host = self.cfg["pc"]["ip"]
        row.btn.setEnabled(False)
        self._msg(f"Пинг {host} …")

        def _ok(res):
            row.set_state(bool(res), "в сети" if res else "не отвечает на ping")
            self._msg(f"ПК: {'🟢 в сети' if res else '🔴 не отвечает'} ({host})")

        def _fail(msg):
            row.set_state(False, f"ошибка: {msg}")
            self._msg(f"Ошибка проверки ПК: {msg}")

        self._run(lambda: ping_host(host), ok=_ok, fail=_fail, on_finish=lambda: row.btn.setEnabled(True))

    def on_check_server(self, row: StatusRow) -> None:
        host, port = self._server()
        row.btn.setEnabled(False)
        self._msg(f"Запрашиваю статус сервера {host}:{port} …")

        def _ok(res):
            row.set_state(True, f"сервер отвечает ({host}:{port})")
            if "lmstudio_running" in res:  # ответ status везёт и состояние LM Studio
                running = bool(res["lmstudio_running"])
                self.row_lm.set_state(running, "запущена" if running else "не запущена")
            self._msg(f"Сервер: 🟢 отвечает ({host}:{port})")

        def _fail(msg):
            row.set_state(False, f"недоступен: {msg}")
            self._msg(f"Сервер: 🔴 недоступен — {msg}")

        self._run(lambda: api_request(host, port, "status"), ok=_ok, fail=_fail,
                  on_finish=lambda: row.btn.setEnabled(True))

    def on_check_lm(self, row: StatusRow) -> None:
        host, port = self._server()
        row.btn.setEnabled(False)
        self._msg("Проверяю состояние LM Studio …")

        def _ok(res):
            running = bool(res.get("lmstudio_running"))
            row.set_state(running, "запущена" if running else "не запущена")
            self._msg(f"LM Studio: {'🟢 запущена' if running else '🔴 не запущена'}")

        def _fail(msg):
            row.set_state(False, f"не проверено: {msg}")
            self._msg(f"LM Studio: не проверено — {msg}")

        self._run(lambda: api_request(host, port, "status"), ok=_ok, fail=_fail,
                  on_finish=lambda: row.btn.setEnabled(True))

    def on_start_lm(self) -> None:
        host, port = self._server()
        self._msg("Отправляю команду: запустить LM Studio …")

        def _ok(res):
            extra = f" (PID {res['pid']})" if res.get("pid") else (f" ({res['opened']})" if res.get("opened") else "")
            self._msg(f"✅ LM Studio: запущена{extra}.")
            self.on_check_lm(self.row_lm)

        def _fail(msg):
            self._msg(f"❌ Не удалось запустить LM Studio: {msg}")

        self._run(lambda: api_request(host, port, "start_lmstudio"), ok=_ok, fail=_fail)

    def on_stop_lm(self) -> None:
        host, port = self._server()
        self._msg("Отправляю команду: остановить LM Studio …")

        def _ok(res):
            if res.get("killed") is None and res.get("note"):
                self._msg(f"✅ LM Studio: {res['note']}.")
            else:
                self._msg(f"✅ LM Studio: остановлена ({res.get('killed')}).")
            self.on_check_lm(self.row_lm)

        def _fail(msg):
            self._msg(f"❌ Не удалось остановить LM Studio: {msg}")

        self._run(lambda: api_request(host, port, "stop_lmstudio"), ok=_ok, fail=_fail)

    def on_hibernate(self) -> None:
        host, port = self._server()
        ans = QMessageBox.question(
            self,
            "Гибернация",
            f"Уснуть (hibernate) удалённый ПК?\nСервер ({host}:{port}) отработает ответ и погасит систему.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            self._msg("Отменено.")
            return
        self._msg("Отправляю команду: гибернация …")

        def _ok(res):
            self.row_srv.set_state(False, "уходит в гибернацию")
            self._msg("🌙 Гибернация запущена. Через секунду ПК погаснет.")

        def _fail(msg):
            self._msg(f"❌ Гибернация не выполнена: {msg}")

        self._run(lambda: api_request(host, port, "hibernate", timeout=6.0), ok=_ok, fail=_fail)

    def on_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == SettingsDialog.Accepted:
            self.cfg = dlg.values()
            config.save(self.cfg)
            self._msg("⚙ Настройки сохранены.")
