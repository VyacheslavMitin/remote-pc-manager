"""Главное окно клиента: кнопки и два независимых индикатора состояния.

Автопроверка: каждые N секунд (N задаётся в настройках, по умолчанию 10)
сам опрашивает всё, что проверяется — пинг ПК + один status-запрос к серверу
(проверяет LM Studio). Сервер и ПК — одна машина, поэтому отдельного
индикатора «Сервер» нет.
Включение автопроверки и её интервал настраиваются только в «⚙ Настройки».
Пока идёт проверка, индикатор строки жёлтый.
Раскладка: шестерёнка настроек — в верхнем правом углу (только значок);
внизу слева — строка состояния автопроверки (вкл/выкл + время следующей
проверки), внизу справа — «IP: <адрес управляемого ПК>» (из настроек).
"""
from __future__ import annotations

import time

import config
from netcheck import ping_host
from server_api import request as api_request
from settings_dialog import SettingsDialog
from wol import send_wol
from worker import Worker

from PySide6.QtCore import Qt, QTimer
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

    def set_checking(self) -> None:
        """Состояние «проверка идёт» — жёлтый индикатор."""
        self.dot.setText("🟡")
        self.dot.setToolTip("проверка…")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self._workers: list[Worker] = []

        # автопроверка: включение и интервал — из конфига (настройки)
        ac = self.cfg.get("auto_check", {})
        self._auto_enabled = bool(ac.get("enabled", True))
        self._auto_interval_s = max(1, int(ac.get("interval_s", 10)))
        self._auto_mode = False          # разрешить авто-строке переписывать статус
        self._manual_inflight = 0        # сколько ручных операций сейчас в полёте
        self._last: dict[str, object] = {"pc": None, "lm": None, "t": None}

        self.setWindowTitle("Удалённый ПК — менеджер")
        self.setMinimumSize(440, 340)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Заголовок + шестерёнка настроек (верхний правый угол, только значок)
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        title = QLabel("Управление удалённым ПК")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("gear")
        self.btn_settings.setFixedSize(51, 51)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки")
        self.btn_settings.clicked.connect(self.on_settings)
        title_row.addWidget(self.btn_settings)
        root.addLayout(title_row)

        # 1. Питание ПК: пробуждение + гибернация в одну строку
        power = QHBoxLayout()
        power.setSpacing(10)
        self.btn_wol = QPushButton("⏻  Пробудить ПК")
        self.btn_wol.setObjectName("primary")
        self.btn_wol.setToolTip("Отправить magic packet (Wake-on-LAN)")
        self.btn_wol.clicked.connect(self.on_wol)
        power.addWidget(self.btn_wol, 3)
        self.btn_hib = QPushButton("🌙  Гибернация")
        self.btn_hib.clicked.connect(self.on_hibernate)
        power.addWidget(self.btn_hib, 2)
        root.addLayout(power)

        # 2. Состояние ПК — единственный индикатор «машина жива» (сервер — та же машина)
        self.row_pc = StatusRow("ПК", self.on_check_pc)
        root.addWidget(self.row_pc)

        # 3/4. Управление LM Studio — в одну строку
        lm = QHBoxLayout()
        lm.setSpacing(10)
        self.btn_start = QPushButton("▶  Включить LM Studio")
        self.btn_start.setObjectName("success")
        self.btn_start.clicked.connect(self.on_start_lm)
        lm.addWidget(self.btn_start, 1)
        self.btn_stop = QPushButton("⏹  Выключить LM Studio")
        self.btn_stop.setObjectName("danger")
        self.btn_stop.clicked.connect(self.on_stop_lm)
        lm.addWidget(self.btn_stop, 1)
        root.addLayout(lm)

        # 5. Состояние LM Studio (берётся из status-запроса к серверу)
        self.row_lm = StatusRow("LM Studio", self.on_check_lm)
        root.addWidget(self.row_lm)

        root.addStretch(1)

        # 6. Нижняя строка: статус слева, IP управляемого ПК (из настроек) справа
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(12)
        self.status = QLabel("Готов.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom.addWidget(self.status, 1)
        self.lbl_ip = QLabel(self._ip_text())
        self.lbl_ip.setObjectName("ip")
        self.lbl_ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_ip.setToolTip("IP управляемого ПК (из ⚙ Настроек)")
        self.lbl_ip.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        bottom.addWidget(self.lbl_ip)
        root.addLayout(bottom)

        # Автопроверка: каждые N секунд (N — из настроек)
        self._timer = QTimer(self)
        self._timer.setInterval(self._auto_interval_ms())
        self._timer.timeout.connect(self._auto_tick)
        if self._auto_enabled:
            self._timer.start()
            # первая проверка сразу, чтобы не ждать N секунд на «⚪»
            self._auto_tick()
        else:
            self.status.setText(self._auto_line())

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

    def closeEvent(self, event) -> None:
        """При закрытии дожидаемся фоновых проверок, чтобы не уничтожить
        QThread «на лету» (иначе Qt роняет процесс при выходе)."""
        for w in list(self._workers):
            if w.isRunning():
                w.wait(6000)  # сеть максимум ~5с (timeout) + ping ~3.5с
        super().closeEvent(event)

    def _drop(self, w) -> None:
        if w in self._workers:
            self._workers.remove(w)

    def _msg(self, text: str) -> None:
        self._auto_mode = False  # ручное сообщение не давим авто-строкой
        self.status.setText(text)

    def _ip_text(self) -> str:
        """Текст метки IP внизу справа — один формат в обоих местах
        (при создании и после сохранения настроек)."""
        return f"IP: {self.cfg['pc']['ip']}"

    def _server(self):
        # Сервер = тот же ПК: хост берём из pc.ip
        return self.cfg["pc"]["ip"], self.cfg["server"]["port"]

    def _auto_interval_ms(self) -> int:
        return max(1, int(self._auto_interval_s)) * 1000

    def _begin_manual(self) -> None:
        self._manual_inflight += 1
        self._auto_mode = False

    def _finish_manual(self, row: StatusRow | None = None) -> None:
        if row is not None:
            row.btn.setEnabled(True)
        self._manual_inflight = max(0, self._manual_inflight - 1)
        # автопроверка выключена — верни постоянную строку (она не
        # обновится сама, тики не идут), сообщение об операции было временным
        if self._manual_inflight == 0 and not self._auto_enabled:
            self.status.setText(self._auto_line())

    # ---------- автопроверка ----------
    def _auto_tick(self) -> None:
        """Раз в 10 секунд: пинг ПК + один status (проверяет LM Studio)."""
        if not self._auto_enabled:
            return
        if self._manual_inflight > 0:
            return  # идёт ручная операция — не наступаем на неё

        self._auto_mode = True
        host = self.cfg["pc"]["ip"]
        self.row_pc.set_checking()
        self._run(
            lambda: ping_host(host),
            ok=lambda res: self._apply_pc(bool(res), "в сети" if res else "не отвечает на ping"),
            fail=lambda msg: self._apply_pc(False, f"ошибка: {msg}"),
        )
        sh, sp = self._server()
        self.row_lm.set_checking()
        self._run(
            lambda: api_request(sh, sp, "status"),
            ok=lambda res: self._apply_status(res),
            fail=lambda msg: self._apply_status_down(msg),
        )

    def _apply_pc(self, ok: bool | None, tip: str = "") -> None:
        self.row_pc.set_state(ok, tip)
        self._last["pc"] = ok
        self._last["t"] = time.strftime("%H:%M:%S")
        self._refresh_status_line()

    def _apply_status(self, res: dict) -> None:
        if "lmstudio_running" in res:
            running = bool(res["lmstudio_running"])
            self.row_lm.set_state(running, "запущена" if running else "не запущена")
            self._last["lm"] = running
        self._last["t"] = time.strftime("%H:%M:%S")
        self._refresh_status_line()

    def _apply_status_down(self, msg: str) -> None:
        self.row_lm.set_state(None, "сервер недоступен")
        self._last["lm"] = None
        self._last["t"] = time.strftime("%H:%M:%S")
        self._refresh_status_line()

    def _auto_line(self) -> str:
        """Текст нижней строки: состояние автопроверки.

        Включена — сколько времени до следующей проверки; выключена — просто
        «выключена». Индикаторов здесь нет (они в строках «ПК»/«LM Studio»).
        """
        if not self._auto_enabled:
            return "Автопроверка: выключена"
        if self._timer.isActive():
            remaining_s = max(0, self._timer.remainingTime()) // 1000
            nxt = time.strftime("%H:%M:%S", time.localtime(time.time() + remaining_s))
            return f"Автопроверка: включена, следующая в {nxt}"
        return "Автопроверка: включена"

    def _refresh_status_line(self) -> None:
        if not self._auto_mode:
            return
        line = self._auto_line()
        if self.status.text() != line:
            self.status.setText(line)

    # ---------- действия ----------
    def on_wol(self) -> None:
        mac = self.cfg["pc"]["mac"]
        self._begin_manual()
        self._msg(f"Отправляю magic packet → {mac} …")

        def _ok(res):
            self._msg(f"✅ Magic packet: {res['to']} (MAC {res['mac']}, ×{res['sent']}).")

        self._run(lambda: send_wol(mac, count=3), ok=_ok,
                  on_finish=lambda: self._finish_manual())

    def on_check_pc(self, row: StatusRow) -> None:
        host = self.cfg["pc"]["ip"]
        row.btn.setEnabled(False)
        self._begin_manual()
        row.set_checking()
        self._msg(f"Пинг {host} …")

        def _ok(res):
            self._apply_pc(bool(res), "в сети" if res else "не отвечает на ping")
            self._msg(f"ПК: {'🟢 в сети' if res else '🔴 не отвечает'} ({host})")

        def _fail(msg):
            self._apply_pc(False, f"ошибка: {msg}")
            self._msg(f"Ошибка проверки ПК: {msg}")

        self._run(lambda: ping_host(host), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual(row))

    def on_check_lm(self, row: StatusRow) -> None:
        host, port = self._server()
        row.btn.setEnabled(False)
        self._begin_manual()
        row.set_checking()
        self._msg("Проверяю состояние LM Studio …")

        def _ok(res):
            running = bool(res.get("lmstudio_running"))
            self.row_lm.set_state(running, "запущена" if running else "не запущена")
            self._last["lm"] = running
            self._msg(f"LM Studio: {'🟢 запущена' if running else '🔴 не запущена'}")

        def _fail(msg):
            self.row_lm.set_state(None, f"не проверено: {msg}")
            self._last["lm"] = None
            self._msg(f"LM Studio: не проверено — {msg}")

        self._run(lambda: api_request(host, port, "status"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual(row))

    def on_start_lm(self) -> None:
        host, port = self._server()
        self._begin_manual()
        self._msg("Отправляю команду: запустить LM Studio …")

        def _ok(res):
            extra = (f" (PID {res['pid']})" if res.get("pid")
                     else (f" ({res['opened']})" if res.get("opened") else ""))
            self._msg(f"✅ LM Studio: запущена{extra}.")
            self._check_lm_quiet()

        def _fail(msg):
            self._msg(f"❌ Не удалось запустить LM Studio: {msg}")

        self._run(lambda: api_request(host, port, "start_lmstudio"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual())

    def on_stop_lm(self) -> None:
        host, port = self._server()
        self._begin_manual()
        self._msg("Отправляю команду: остановить LM Studio …")

        def _ok(res):
            if res.get("killed") is None and res.get("note"):
                self._msg(f"✅ LM Studio: {res['note']}.")
            else:
                self._msg(f"✅ LM Studio: остановлена ({res.get('killed')}).")
            self._check_lm_quiet()

        def _fail(msg):
            self._msg(f"❌ Не удалось остановить LM Studio: {msg}")

        self._run(lambda: api_request(host, port, "stop_lmstudio"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual())

    def _check_lm_quiet(self) -> None:
        """После вкл/выкл обновляет индикатор LM, не трогая статус-бар."""
        host, port = self._server()
        self.row_lm.set_checking()
        self._run(
            lambda: api_request(host, port, "status"),
            ok=lambda res: self.row_lm.set_state(
                bool(res.get("lmstudio_running")),
                "запущена" if res.get("lmstudio_running") else "не запущена"),
            fail=lambda msg: self.row_lm.set_state(None, f"не проверено: {msg}"),
        )

    def on_hibernate(self) -> None:
        host, port = self._server()
        ans = QMessageBox.question(
            self,
            "Гибернация",
            f"Уснуть (hibernate) удалённый ПК?\nСистема отправит ответ и погаснет ({host}:{port}).",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if ans != QMessageBox.Yes:
            self._msg("Отменено.")
            return
        self._begin_manual()
        self._msg("Отправляю команду: гибернация …")

        def _ok(res):
            self.row_pc.set_state(False, "уходит в гибернацию")
            self._last["pc"] = False
            self._msg("🌙 Гибернация запущена. Через секунду ПК погаснет.")

        def _fail(msg):
            self._msg(f"❌ Гибернация не выполнена: {msg}")

        self._run(lambda: api_request(host, port, "hibernate", timeout=6.0),
                  ok=_ok, fail=_fail, on_finish=lambda: self._finish_manual())

    def on_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == SettingsDialog.Accepted:
            self.cfg = dlg.values()
            config.save(self.cfg)
            self.lbl_ip.setText(self._ip_text())
            # переприменить настройки автопроверки (включение + интервал)
            ac = self.cfg.get("auto_check", {})
            self._auto_enabled = bool(ac.get("enabled", True))
            self._auto_interval_s = max(1, int(ac.get("interval_s", 10)))
            self._timer.setInterval(self._auto_interval_ms())
            if self._auto_enabled:
                self._timer.start()
                self._auto_tick()  # сразу перепроверить с новыми настройками
                self._msg("⚙ Настройки сохранены.")
            else:
                self._timer.stop()
                self._auto_mode = False
                self.status.setText(self._auto_line())
