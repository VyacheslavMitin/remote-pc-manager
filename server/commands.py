"""Диспетчер команд сервера.

Поддерживаемые команды (тело POST /command: {"command": "<имя>"}):
    status           {"ok": true, "command": "status", "lmstudio_running": bool,
                      "pc_name": "<имя ПК (hostname)>",
                      "os_name": "<ОС сервера, напр. «Windows 11»>",
                      "uptime_s": <секунд с момента запуска системы, int|null>}
    hibernate       -> {"ok": true, ...}  (машина погаснет после ответа)
    start_lmstudio  -> {"ok": true, "pid": int, ...}
    stop_lmstudio   -> {"ok": true, "killed": str|None,
                        "note": "остановлена аккуратно|принудительно|не был запущен"}
"""
from __future__ import annotations

import platform
import re
import socket
import subprocess
import time

import hibernate
import lmstudio
from config import Config

SUPPORTED = ("status", "hibernate", "start_lmstudio", "stop_lmstudio")


def _os_name() -> str:
    """Человекочитаемое имя ОС сервера: «Windows 11», «macOS», «Linux»…
    Без слова «Microsoft» (platform.system() и так возвращает «Windows»)."""
    system = platform.system()
    if system == "Windows":
        return f"Windows {platform.release()}".strip()
    if system == "Darwin":
        return "macOS"
    return system or "unknown OS"


def _uptime_seconds() -> int | None:
    """Секунд с момента запуска системы (только stdlib, кроссплатформенно).

    Windows  — GetTickCount64() (мс с момента загрузки, переполнение ~584 года);
    Linux    — /proc/uptime;
    macOS    — sysctl kern.boottime.
    None, если определить не удалось (клиент просто не покажет аптайм)."""
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes
            return ctypes.windll.kernel32.GetTickCount64() // 1000  # type: ignore[reportAttributeAccessIssue]
        if system == "Linux":
            with open("/proc/uptime", encoding="ascii") as f:
                return int(float(f.read().split()[0]))
        if system == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                capture_output=True, text=True, timeout=5, check=False,
            ).stdout
            m = re.search(r"sec\s*=\s*(\d+)", out)
            if m:
                return max(0, int(time.time()) - int(m.group(1)))
    except Exception:
        pass
    return None


def run(command: str, cfg: Config) -> dict:
    c = (command or "").strip().lower()
    if c not in SUPPORTED:
        raise ValueError(
            f"неизвестная команда {command!r}; допустимы: {', '.join(SUPPORTED)}"
        )

    if c == "status":
        return {
            "ok": True,
            "command": "status",
            "lmstudio_running": lmstudio.is_running(cfg.lm_process),
            "pc_name": socket.gethostname(),
            "os_name": _os_name(),
            "uptime_s": _uptime_seconds(),
        }

    if c == "hibernate":
        # Сначала ответим, затем в фоне усыпит систему.
        hibernate.trigger(method=cfg.hibernate_method, delay_s=cfg.hibernate_delay)
        return {"ok": True, "command": "hibernate", "note": "гибернация запущена"}

    if c == "start_lmstudio":
        info = lmstudio.start(cfg.lm_exe)
        return {"ok": True, "command": "start_lmstudio", **info}

    if c == "stop_lmstudio":
        info = lmstudio.stop(cfg.lm_process)
        return {"ok": True, "command": "stop_lmstudio", **info}

    # недостижимо
    raise ValueError(f"неизвестная команда {command!r}")
