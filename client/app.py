"""Главное окно клиента: кнопки и два независимых индикатора состояния.

Автопроверка: каждые N секунд (N задаётся в настройках, по умолчанию 10)
сам опрашивает всё, что проверяется — пинг ПК + один status-запрос к серверу
(проверяет LM Studio). Сервер и ПК — одна машина, поэтому отдельного
индикатора «Сервер» нет.
Включение автопроверки и её интервал настраиваются только в «⚙ Настройки».
Пока идёт проверка, индикатор строки жёлтый.
Раскладка: главное окно разделено на три блока — «ПК», «LM Studio» и
«Strata»; в каждом блоке строка проверки состояния (индикатор + «Проверить»)
сверху, под ней — кнопки действий.
Заголовок блока «ПК» — «ПК (имя, ОС, аптайм, 37 ГБ)», если
сервер ответил (pc_name, os_name, uptime_s, ram_used_mb
из status; аптайм форматируется без секунд, ОС — из ответа сервера, либо
константа Win 11, если сервер не прислал её, RAM — только занятое
в гигабайтах), иначе просто «ПК» (сервер недоступен).
Шестерёнка настроек — в верхнем правом углу (только значок);
внизу слева — строка состояния автопроверки (вкл/выкл + время следующей
проверки), внизу справа — «IP: <адрес управляемого ПК>» (из настроек).
Заголовок блока «LM Studio» — версия LM Studio на целевом ПК (кроп с
обоих концов: «v0.4.28.0» → «0.4.28»), загруженная модель и её контекст,
VRAM, занятый процессами LM Studio:
«LM Studio (0.3.25, qwen2.5-7b-instruct, 64K, 16 ГБ)», если
сервер прислал lmstudio_version / lmstudio_model / lmstudio_context /
lmstudio_vram_mb (модель — первый id из локального API-сервера LM Studio,
GET /v1/models, остальные, например embedding-модели, в заголовок не
идут; контекст — контекст загруженной модели в токенах, GET
/api/v0/models, 65536 показывается как «64K»; VRAM — nvidia-smi,
суммарно по процессам LM Studio и её движка llama-server, целые
гигабайты);
показывается только то, что прислал. Если ничего неизвестно
(старый сервер или сервер недоступен) — просто «LM Studio»;
состояние (запущена/не запущена) показывает индикатор-точка.
Заголовок блока «Strata» — модель Strata на целевом ПК, её контекст и
VRAM: «Strata (qwen3.8-flash-next-iq3_s, 128K, 14 ГБ)», если сервер
прислал strata_model / strata_context / strata_vram_mb (берутся из
открытого GET /health Strata — её /v1/models требует API-ключ и клиентом
не опрашивается). Strata — OpenAI-совместимый сервер (API как у LM Studio),
порт её API задаётся в настройках (по умолчанию 8080) и пушится на сервер
командой set_strata_port.
Нижняя сводка сообщает, что активно: «активна LM Studio», «активна Strata»
или «активны обе: LM Studio и Strata».
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
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
)

# Запасное имя ОС сервера (целевой Windows-ПК) — на случай, если сервер
# не прислал os_name в status (старая версия сервера). Если сервер прислал —
# его значение в приоритете. В заголовке «Windows 11» сокращается до «Win 11».
DEFAULT_PC_OS = "Win 11"


def _format_uptime(total: int) -> str:
    """Аптайм без секунд: «12 мин», «3 ч 14 мин», «2 д 5 ч».

    Берутся две старших ненулевых единицы; менее минуты — «меньше минуты»."""
    total = max(0, int(total))
    if total < 60:
        return "меньше минуты"
    parts: list[str] = []
    rest = total
    for div, unit in ((86400, "д"), (3600, "ч"), (60, "мин")):
        v = rest // div
        if v:
            parts.append(f"{v} {unit}")
        rest %= div
        if len(parts) == 2:
            break
    return " ".join(parts) or "меньше минуты"


def _format_context(tokens: int | str | None) -> str:
    """Контекст модели (токены) для заголовка: 65536 -> «64K», 131072 -> «128K»;
    не кратное 1024 — как есть (100000 -> «100000»); пусто/не число -> ''."""
    if tokens is None:
        return ""
    try:
        v = int(tokens)
    except (TypeError, ValueError):
        return ""
    if v <= 0:
        return ""
    if v % 1024 == 0:
        return f"{v // 1024}K"
    return str(v)


def _round_half_up(x: float) -> int:
    """Математическое округление: 0.5 — в большую сторону (16.5 -> 17).

    Не Python `round()` — он «банковское» (16.5 -> 16). x здесь >= 0.
    """
    return int(x + 0.5)


def _format_gb(mb: int | str | None) -> str:
    """МБ для заголовка: 16384 -> «16 ГБ» (целые ГБ, математическое
    округление; меньше 1 ГБ — один знак). Пусто/не число -> '' (часть
    заголовка не показывать)."""
    if mb is None or mb == "":
        return ""
    try:
        v = int(mb)
    except (TypeError, ValueError):
        return ""
    if v < 0:
        return ""
    gb = v / 1024
    if gb < 1:
        return f"{_round_half_up(gb * 10) / 10:.1f} ГБ"
    return f"{_round_half_up(gb)} ГБ"


def _format_ram(used_mb: int | str | None, total_mb: int | str | None) -> str:
    """RAM для заголовка: «37 ГБ» (только занято, математическое округление).

    `total_mb` сервер присылает, но в заголовок не попадает (осталось в API).
    Значение неизвестно или не число — '' (часть заголовка не показывать).
    """
    if used_mb is None or used_mb == "":
        return ""
    try:
        u = int(used_mb)
    except (TypeError, ValueError):
        return ""
    if u < 0:
        return ""
    gb = u / 1024
    if gb < 1:
        return f"{_round_half_up(gb * 10) / 10:.1f} ГБ"
    return f"{_round_half_up(gb)} ГБ"


class StatusRow(QWidget):
    """Строка: [●] [состояние] … [кнопка «Проверить»].

    Индикатор — у левого края, рядом живой статус:
    ПК — «в сети»/«не в сети», LM Studio и Strata — «работает»/«остановлен».
    """

    _PC = {True: "в сети", False: "не в сети", None: "—"}
    _LM = {True: "работает", False: "остановлен", None: "—"}
    _ST = {True: "работает", False: "остановлен", None: "—"}

    def __init__(self, kind: str, on_check, parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._kind = kind
        h = QHBoxLayout(self)
        h.setContentsMargins(12, 8, 12, 8)
        h.setSpacing(10)

        self.dot = QLabel("⚪")
        self.dot.setObjectName("dot")
        self.dot.setToolTip("не проверено")

        self.state = QLabel("—")
        self.state.setObjectName("rowname")
        self.state.setMinimumWidth(96)

        self.btn = QPushButton("Проверить")
        self.btn.clicked.connect(lambda: on_check(self))

        h.addWidget(self.dot)
        h.addWidget(self.state)
        h.addStretch(1)
        h.addWidget(self.btn)

    def _state_text(self, ok: bool | None) -> str:
        table = {"pc": self._PC, "lm": self._LM}.get(self._kind, self._ST)
        return table.get(ok, "—")

    def set_state(self, ok: bool | None, tooltip: str = "") -> None:
        if ok is None:
            self.dot.setText("⚪")
        else:
            self.dot.setText("🟢" if ok else "🔴")
        if tooltip:
            self.dot.setToolTip(tooltip)
        self.state.setText(self._state_text(ok))

    def set_checking(self) -> None:
        """Состояние «проверка идёт» — жёлтый индикатор."""
        self.dot.setText("🟡")
        self.dot.setToolTip("проверка…")
        self.state.setText("проверка…")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.cfg = config.load()
        self._workers: list[Worker] = []

        # автопроверка: включение и интервал — из конфига (настройки)
        ac = self.cfg.get("auto_check", {})
        self._auto_enabled = bool(ac.get("enabled", True))
        self._auto_interval_s = max(1, int(ac.get("interval_s", 10)))
        self._auto_mode = False          # идёт автопроверка (да — 1-я строка = сводка)
        self._manual_inflight = 0        # сколько ручных операций сейчас в полёте
        self._last: dict[str, object] = {"pc": None, "lm": None, "t": None, "model": None,
                                         "strata": None, "strata_loaded": False}

        self.setWindowTitle("Удалённый ПК — менеджер")
        self.setMinimumSize(440, 470)

        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Шестерёнка настроек — в верхнем правом углу (только значок), затем заголовок
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(8)
        self.btn_settings = QPushButton("⚙")
        self.btn_settings.setObjectName("gear")
        self.btn_settings.setFixedSize(51, 51)
        self.btn_settings.setCursor(Qt.PointingHandCursor)
        self.btn_settings.setToolTip("Настройки")
        self.btn_settings.clicked.connect(self.on_settings)
        title = QLabel("Управление удалённым ПК")
        title.setObjectName("title")
        title_row.addWidget(title)
        title_row.addStretch(1)
        title_row.addWidget(self.btn_settings)
        # Шапка: заголовок + IP прямо под ним (плотный отступ, как в iOS)
        head = QVBoxLayout()
        head.setSpacing(6)
        head.addLayout(title_row)

        # IP управляемого ПК (из настроек) — строка прямо под заголовком
        self.lbl_ip = QLabel(self._ip_text())
        self.lbl_ip.setObjectName("ip")
        self.lbl_ip.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.lbl_ip.setToolTip("IP управляемого ПК (из ⚙ Настроек)")
        self.lbl_ip.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        head.addWidget(self.lbl_ip)
        root.addLayout(head)

        # ── Блок «ПК» ── проверка состояния сверху, затем действия
        block_pc, pc, pc_title = self._block("ПК")
        self.title_pc = pc_title
        self.row_pc = StatusRow("pc", self.on_check_pc)
        pc.addWidget(self.row_pc)
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
        pc.addLayout(power)
        root.addWidget(block_pc)

        # ── Блок «LM Studio» ── проверка состояния сверху, затем действия
        block_lm, lmb, self.title_lm = self._block("LM Studio")
        self.row_lm = StatusRow("lm", self.on_check_lm)
        lmb.addWidget(self.row_lm)
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
        lmb.addLayout(lm)
        root.addWidget(block_lm)

        # ── Блок «Strata» ── проверка состояния сверху, затем действия
        # (Strata — OpenAI-совместимый сервер, API как у LM Studio)
        block_st, stb, self.title_st = self._block("Strata")
        self.row_st = StatusRow("strata", self.on_check_strata)
        stb.addWidget(self.row_st)
        st = QHBoxLayout()
        st.setSpacing(10)
        self.btn_start_st = QPushButton("▶  Включить Strata")
        self.btn_start_st.setObjectName("success")
        self.btn_start_st.clicked.connect(self.on_start_strata)
        st.addWidget(self.btn_start_st, 1)
        self.btn_stop_st = QPushButton("⏹  Выключить Strata")
        self.btn_stop_st.setObjectName("danger")
        self.btn_stop_st.clicked.connect(self.on_stop_strata)
        st.addWidget(self.btn_stop_st, 1)
        stb.addLayout(st)
        root.addWidget(block_st)

        root.addStretch(1)

        # 6. Нижняя область: две строки (как в веб/iOS) — сообщение сверху,
        #    автопроверка снизу (всегда видна, сообщение её не вытесняет)
        bottom = QVBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.setSpacing(2)
        self.status = QLabel("Готов.")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom.addWidget(self.status)
        self.auto_label = QLabel("")
        self.auto_label.setStyleSheet("color: #9a9aa0; font-size: 11px;")
        bottom.addWidget(self.auto_label)
        root.addLayout(bottom)

        # Автопроверка: каждые N секунд (N — из настроек)
        self._timer = QTimer(self)
        self._timer.setInterval(self._auto_interval_ms())
        self._timer.timeout.connect(self._auto_tick)
        self._refresh_auto_line()   # заполнить строку автопроверки (таймер готов)
        if self._auto_enabled:
            self._timer.start()
            # первая проверка сразу, чтобы не ждать N секунд на «⚪»
            self._auto_tick()

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
                w.wait(10000)  # сеть максимум ~8с (timeout) + запас на ping
        super().closeEvent(event)

    def _drop(self, w) -> None:
        if w in self._workers:
            self._workers.remove(w)

    def _msg(self, text: str) -> None:
        self._auto_mode = False  # ручное сообщение не давим сводкой
        self.status.setText(text)

    def _ip_text(self) -> str:
        """Текст метки IP внизу справа — один формат в обоих местах
        (при создании и после сохранения настроек)."""
        return f"IP: {self.cfg['pc']['ip']}"

    def _set_pc_title(
        self,
        name: str | None,
        os_name: str | None = None,
        uptime_s: int | None = None,
        ram_used_mb: int | None = None,
        ram_total_mb: int | None = None,
    ) -> None:
        """Заголовок блока «ПК»: «ПК (имя, ОС, аптайм, 37 ГБ)»,
        если сервер ответил (pc_name + os_name + uptime_s +
        ram_used_mb из status). ОС — из ответа сервера, либо при старой
        версии сервера — константа DEFAULT_PC_OS; в заголовке «Windows 11»
        сокращается до «Win 11». Аптайм форматируется без секунд
        (uptime_s — секунды). RAM — только занятое в ГБ; если сервер не
        прислал (старая версия) — части заголовка нет. Сервер недоступен
        или имя пустое — просто «ПК»."""
        name = (name or "").strip()
        if not name:
            self.title_pc.setText("ПК")
            return
        parts = [name]
        os_text = (os_name or "").strip() or DEFAULT_PC_OS
        if os_text.lower().startswith("windows"):
            os_text = f"Win {os_text[7:].strip()}"
        parts.append(os_text)
        if uptime_s is not None:
            parts.append(_format_uptime(uptime_s))
        ram = _format_ram(ram_used_mb, ram_total_mb)
        if ram:
            parts.append(ram)
        self.title_pc.setText(f"ПК ({', '.join(parts)})")

    def _set_lm_title(
        self,
        version: str | None = None,
        model: str | None = None,
        context: int | None = None,
        vram_mb: int | None = None,
    ) -> None:
        """Заголовок блока «LM Studio» — версия, загруженная модель и её
        контекст на ПК, VRAM процессов LM Studio (app + движок llama-server):

        «LM Studio (0.3.25, qwen2.5-7b-instruct, 64K, 16 ГБ)»,
        если сервер прислал lmstudio_version / lmstudio_model /
        lmstudio_context / lmstudio_vram_mb; только то, что прислал
        (версия кропится с обоих концов: «v0.4.28.0» → «0.4.28», модель
        без версии, контекст — окно модели в токенах, 65536 показывается
        как «64K», VRAM — целые ГБ, занятые процессами LM Studio и её
        движком llama-server). Если ничего неизвестно (старый сервер или
        сервер недоступен) — просто «LM Studio»; состояние (запущена/не
        запущена) показывает индикатор-точка."""
        parts: list[str] = []
        v = (version or "").strip()
        if v[:1] in ("v", "V"):
            v = v[1:]
        if v.endswith(".0"):
            v = v[:-2]
        if v:
            parts.append(v)
        m = (model or "").strip()
        if m:
            parts.append(m)
        ctx = _format_context(context)
        if ctx:
            parts.append(ctx)
        vr = _format_gb(vram_mb)
        if vr:
            parts.append(vr)
        if parts:
            self.title_lm.setText(f"LM Studio ({', '.join(parts)})")
        else:
            self.title_lm.setText("LM Studio")

    def _set_strata_title(
        self,
        model: str | None = None,
        context: int | None = None,
        vram_mb: int | None = None,
    ) -> None:
        """Заголовок блока «Strata» — модель, её контекст и VRAM:

        «Strata (qwen3.8-flash-next-iq3_s, 128K, 14 ГБ)», если сервер
        прислал strata_model / strata_context / strata_vram_mb (из
        открытого /health Strata; контекст 131072 -> «128K», VRAM — целые
        ГБ). Только то, что прислал; если ничего неизвестно (старый сервер
        или сервер недоступен) — просто «Strata»; состояние показывает
        индикатор-точка."""
        parts: list[str] = []
        m = (model or "").strip()
        if m:
            parts.append(m)
        ctx = _format_context(context)
        if ctx:
            parts.append(ctx)
        vr = _format_gb(vram_mb)
        if vr:
            parts.append(vr)
        if parts:
            self.title_st.setText(f"Strata ({', '.join(parts)})")
        else:
            self.title_st.setText("Strata")

    def _block(self, title: str) -> tuple[QFrame, QVBoxLayout, QLabel]:
        """Собирает блок-панель: заголовок секции + внутренний layout.

        Возвращает (frame, inner_layout, title_label) — содержимое
        (проверка, кнопки) добавляется в inner_layout в нужном порядке;
        title_label — заголовок секции (можно менять динамически)."""
        frame = QFrame()
        frame.setObjectName("block")
        v = QVBoxLayout(frame)
        v.setContentsMargins(14, 12, 14, 14)
        v.setSpacing(10)
        h = QLabel(title)
        h.setObjectName("section")
        v.addWidget(h)
        return frame, v, h

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
        # автопроверка выключена — обнови строку автопроверки (тики не идут)
        if self._manual_inflight == 0 and not self._auto_enabled:
            self._refresh_auto_line()

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
        self.row_st.set_checking()
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
        # «модель загружена» = известен контекст (state==«loaded» в /api/v0/models);
        # /v1/models отдаёт каталог скачанных моделей даже без загрузки — опираться нельзя.
        self._last["model"] = (res.get("lmstudio_context") or 0) > 0
        self._set_lm_title(
            res.get("lmstudio_version"), res.get("lmstudio_model"),
            res.get("lmstudio_context"), res.get("lmstudio_vram_mb"))
        if "strata_running" in res:
            st_running = bool(res["strata_running"])
            self.row_st.set_state(st_running, "запущена" if st_running else "не запущена")
            self._last["strata"] = st_running
        self._last["strata_loaded"] = bool(res.get("strata_loaded"))
        self._set_strata_title(
            res.get("strata_model"), res.get("strata_context"),
            res.get("strata_vram_mb"))
        self._set_pc_title(
            res.get("pc_name"), res.get("os_name"), res.get("uptime_s"),
            res.get("ram_used_mb"), res.get("ram_total_mb")
        )
        self._last["t"] = time.strftime("%H:%M:%S")
        self._refresh_status_line()

    def _apply_status_down(self, msg: str) -> None:
        self.row_lm.set_state(None, "сервер недоступен")
        self._last["lm"] = None
        self._last["model"] = False
        self.row_st.set_state(None, "сервер недоступен")
        self._last["strata"] = None
        self._last["strata_loaded"] = False
        self._set_lm_title(None)
        self._set_strata_title(None)
        self._set_pc_title(None)
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

    def _status_summary(self) -> str:
        """Первая строка после автопроверки: что активно — LM Studio,
        Strata или обе («активна LM Studio» / «активна Strata» /
        «активны обе: LM Studio и Strata»)."""
        if self._last["pc"] is False:
            return "ПК не отвечает."
        lm = self._last["lm"]
        st = self._last.get("strata")
        if lm and st:
            return "ПК в сети, активны обе: LM Studio и Strata."
        if lm:
            return "ПК в сети, активна LM Studio."
        if st:
            return "ПК в сети, активна Strata."
        if lm is False or st is False:
            # хотя бы одна подтверждённо остановлена, активна ни одна
            return "ПК в сети, ничего не активно."
        if self._last["pc"] is True:
            return "ПК в сети."
        return "—"

    def _refresh_status_line(self) -> None:
        """1-я строка: сводка (только после автопроверки — ручное сообщение не давим)."""
        if self._auto_mode:
            line = self._status_summary()
            if self.status.text() != line:
                self.status.setText(line)
        self._refresh_auto_line()

    def _refresh_auto_line(self) -> None:
        """2-я строка: состояние автопроверки (всегда актуальна)."""
        line = self._auto_line()
        if self.auto_label.text() != line:
            self.auto_label.setText(line)

    # ---------- действия ----------
    def on_wol(self) -> None:
        mac = self.cfg["pc"]["mac"]
        self._begin_manual()
        self._msg("⏻ Пробуждаю ПК …")

        def _ok(res):
            self._msg(f"✅ WoL: ×{res['sent']} → MAC {res['mac']}")

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
            self._set_lm_title(
                res.get("lmstudio_version"), res.get("lmstudio_model"),
                res.get("lmstudio_context"), res.get("lmstudio_vram_mb"))
            if "strata_running" in res:
                st_running = bool(res["strata_running"])
                self.row_st.set_state(st_running, "запущена" if st_running else "не запущена")
                self._last["strata"] = st_running
            self._set_strata_title(
                res.get("strata_model"), res.get("strata_context"),
                res.get("strata_vram_mb"))
            self._set_pc_title(
                res.get("pc_name"), res.get("os_name"), res.get("uptime_s"),
                res.get("ram_used_mb"), res.get("ram_total_mb")
            )
            self._msg(f"LM Studio: {'🟢 запущена' if running else '🔴 не запущена'}")

        def _fail(msg):
            self.row_lm.set_state(None, f"не проверено: {msg}")
            self._last["lm"] = None
            self._set_lm_title(None)
            self._set_pc_title(None)
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
            note = res.get("note")
            if res.get("killed") is None and note:
                self._msg(f"✅ LM Studio: {note}.")
            elif note:
                self._msg(f"✅ LM Studio: {note}.")
            else:
                self._msg("✅ LM Studio: остановлена.")
            self._check_lm_quiet()

        def _fail(msg):
            self._msg(f"❌ Не удалось остановить LM Studio: {msg}")

        self._run(lambda: api_request(host, port, "stop_lmstudio"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual())

    def _check_lm_quiet(self) -> None:
        """После вкл/выкл обновляет индикатор LM, не трогая статус-бар."""
        host, port = self._server()
        self.row_lm.set_checking()

        def _ok(res):
            self.row_lm.set_state(
                bool(res.get("lmstudio_running")),
                "запущена" if res.get("lmstudio_running") else "не запущена")
            self._set_lm_title(
                res.get("lmstudio_version"), res.get("lmstudio_model"),
                res.get("lmstudio_context"), res.get("lmstudio_vram_mb"))
            self._set_pc_title(
                res.get("pc_name"), res.get("os_name"), res.get("uptime_s"),
                res.get("ram_used_mb"), res.get("ram_total_mb")
            )

        def _fail(msg):
            self.row_lm.set_state(None, f"не проверено: {msg}")
            self._set_lm_title(None)
            self._set_pc_title(None)

        self._run(lambda: api_request(host, port, "status"), ok=_ok, fail=_fail)

    # ---------- Strata ----------
    def on_check_strata(self, row: StatusRow) -> None:
        host, port = self._server()
        row.btn.setEnabled(False)
        self._begin_manual()
        row.set_checking()
        self._msg("Проверяю состояние Strata …")

        def _ok(res):
            running = bool(res.get("strata_running"))
            self.row_st.set_state(running, "запущена" if running else "не запущена")
            self._last["strata"] = running
            self._last["strata_loaded"] = bool(res.get("strata_loaded"))
            self._set_strata_title(
                res.get("strata_model"), res.get("strata_context"),
                res.get("strata_vram_mb"))
            self._set_pc_title(
                res.get("pc_name"), res.get("os_name"), res.get("uptime_s"),
                res.get("ram_used_mb"), res.get("ram_total_mb")
            )
            self._msg(f"Strata: {'🟢 запущена' if running else '🔴 не запущена'}")

        def _fail(msg):
            self.row_st.set_state(None, f"не проверено: {msg}")
            self._last["strata"] = None
            self._set_strata_title(None)
            self._set_pc_title(None)
            self._msg(f"Strata: не проверено — {msg}")

        self._run(lambda: api_request(host, port, "status"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual(row))

    def on_start_strata(self) -> None:
        host, port = self._server()
        self._begin_manual()
        self._msg("Отправляю команду: запустить Strata …")

        def _ok(res):
            extra = f" (PID {res['pid']})" if res.get("pid") else ""
            self._msg(f"✅ Strata: запуск отправлен{extra}.")
            self._check_strata_quiet()

        def _fail(msg):
            self._msg(f"❌ Не удалось запустить Strata: {msg}")

        self._run(lambda: api_request(host, port, "start_strata"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual())

    def on_stop_strata(self) -> None:
        host, port = self._server()
        self._begin_manual()
        self._msg("Отправляю команду: остановить Strata …")

        def _ok(res):
            note = res.get("note")
            self._msg(f"✅ Strata: {note}." if note else "✅ Strata: остановлена.")
            self._check_strata_quiet()

        def _fail(msg):
            self._msg(f"❌ Не удалось остановить Strata: {msg}")

        self._run(lambda: api_request(host, port, "stop_strata"), ok=_ok, fail=_fail,
                  on_finish=lambda: self._finish_manual())

    def _check_strata_quiet(self) -> None:
        """После вкл/выкл обновляет индикатор Strata, не трогая статус-бар."""
        host, port = self._server()
        self.row_st.set_checking()

        def _ok(res):
            self.row_st.set_state(
                bool(res.get("strata_running")),
                "запущена" if res.get("strata_running") else "не запущена")
            self._last["strata"] = bool(res.get("strata_running"))
            self._last["strata_loaded"] = bool(res.get("strata_loaded"))
            self._set_strata_title(
                res.get("strata_model"), res.get("strata_context"),
                res.get("strata_vram_mb"))
            self._set_pc_title(
                res.get("pc_name"), res.get("os_name"), res.get("uptime_s"),
                res.get("ram_used_mb"), res.get("ram_total_mb")
            )

        def _fail(msg):
            self.row_st.set_state(None, f"не проверено: {msg}")
            self._set_strata_title(None)
            self._set_pc_title(None)

        self._run(lambda: api_request(host, port, "status"), ok=_ok, fail=_fail)

    def on_hibernate(self) -> None:
        host, port = self._server()
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
            else:
                self._timer.stop()
                self._auto_mode = False
                self._refresh_auto_line()
            self._msg("⚙ Настройки сохранены.")
            self._push_lm_port()
            self._push_strata_port()

    def _push_lm_port(self) -> None:
        """Применяет порт API LM Studio на сервере (команда set_lm_port):
        сервер сохраняет его в свой config.json и сразу использует новое
        значение. Значение дублируется в конфиге клиента — поле в
        настройках не теряет значение, даже если сервер недоступен или
        это старая версия без команды set_lm_port."""
        host, port = self._server()
        lm_port = int(self.cfg.get("lmstudio", {}).get("api_port", 1234))

        def _ok(res):
            got = res.get("lmstudio_api_port")
            self._msg(f"⚙ Порт LM Studio применён на сервере: {got or lm_port}.")

        def _fail(msg):
            self._msg(
                f"⚙ Порт LM Studio сохранён локально ({lm_port}), но применить "
                f"на сервере не удалось: {msg}. Если сервер старой версии — "
                f"задайте lmstudio.api_port в его config.json вручную."
            )

        self._run(
            lambda: api_request(host, port, "set_lm_port", timeout=6.0,
                                args={"port": lm_port}),
            ok=_ok, fail=_fail,
        )

    def _push_strata_port(self) -> None:
        """Применяет порт API Strata на сервере (команда set_strata_port):
        сервер сохраняет его в свой config.json и сразу использует новое
        значение. Значение дублируется в конфиге клиента — поле в
        настройках не теряет значение, даже если сервер недоступен или
        это старая версия без команды set_strata_port."""
        host, port = self._server()
        st_port = int(self.cfg.get("strata", {}).get("api_port", 8080))

        def _ok(res):
            got = res.get("strata_api_port")
            self._msg(f"⚙ Порт Strata применён на сервере: {got or st_port}.")

        def _fail(msg):
            self._msg(
                f"⚙ Порт Strata сохранён локально ({st_port}), но применить "
                f"на сервере не удалось: {msg}. Если сервер старой версии — "
                f"задайте strata.api_port в его config.json вручную."
            )

        self._run(
            lambda: api_request(host, port, "set_strata_port", timeout=6.0,
                                args={"port": st_port}),
            ok=_ok, fail=_fail,
        )
