"""Диспетчер команд сервера.

Поддерживаемые команды (тело POST /command: {"command": "<имя>"}):
    status           {"ok": true, "command": "status", "lmstudio_running": bool,
                      "pc_name": "<имя ПК (hostname)>"}
    hibernate       -> {"ok": true, ...}  (машина погаснет после ответа)
    start_lmstudio  -> {"ok": true, "pid": int, ...}
    stop_lmstudio   -> {"ok": true, "killed": str|None,
                        "note": "остановлена аккуратно|принудительно|не был запущен"}
"""
from __future__ import annotations

import socket

import hibernate
import lmstudio
from config import Config

SUPPORTED = ("status", "hibernate", "start_lmstudio", "stop_lmstudio")


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
