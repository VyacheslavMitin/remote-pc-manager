"""Диспетчер команд сервера.

Поддерживаемые команды (тело POST /command: {"command": "<имя>"}):
    status           {"ok": true, "command": "status", "lmstudio_running": bool,
                      "lmstudio_version": "<версия из VersionInfo exe, или null>",
                      "lmstudio_model": "<id загруженной модели (API, /v1/models), или null>",
                      "lmstudio_context": "<контекст модели (токены, API /api/v0/models), или null>",
                      "lmstudio_vram_mb": "<VRAM процессов LM Studio (app + llama-server, nvidia-smi), МБ; null — нет NVIDIA/не запущена>",
                      "ram_used_mb": "<занято RAM, МБ; null — не удалось прочитать>",
                      "ram_total_mb": "<всего RAM, МБ; null — не удалось прочитать>",
                      "pc_name": "<имя ПК (hostname)>",
                      "os_name": "<ОС сервера, напр. «Windows 11»>",
                      "uptime_s": <секунд с момента запуска системы, int|null>}
    hibernate       -> {"ok": true, ...}  (машина погаснет после ответа)
    start_lmstudio  -> {"ok": true, "pid": int, ...}
    stop_lmstudio   -> {"ok": true, "killed": str|None,
                        "note": "остановлена аккуратно|принудительно|не был запущен"}
    set_lm_port     тело {"command": "set_lm_port", "port": 1234}
                    -> {"ok": true, "command": "set_lm_port", "lmstudio_api_port": 1234}
                       (задаёт lmstudio.api_port и сохраняет его в config.json)
"""
from __future__ import annotations

import platform
import re
import socket
import subprocess
import time

import hibernate
import lmstudio
import system
from config import Config, save as save_config

SUPPORTED = ("status", "hibernate", "start_lmstudio", "stop_lmstudio", "set_lm_port")


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


def run(command: str, cfg: Config, args: dict | None = None) -> dict:
    c = (command or "").strip().lower()
    if c not in SUPPORTED:
        raise ValueError(
            f"неизвестная команда {command!r}; допустимы: {', '.join(SUPPORTED)}"
        )

    if c == "status":
        running = lmstudio.is_running(cfg.lm_process)
        mem = system.memory_info() or {}
        return {
            "ok": True,
            "command": "status",
            "lmstudio_running": running,
            "lmstudio_version": lmstudio.version(cfg.lm_exe),
            "lmstudio_model": lmstudio.loaded_model(cfg.lm_api_port),
            "lmstudio_context": lmstudio.loaded_context(cfg.lm_api_port),
            # VRAM процессов LM Studio — только когда она запущена (иначе
            # nvidia-smi не покажет их и «0» в заголовке обманет).
            # llama-server — inference-движок LM Studio: VRAM занят
            # именно в нём, а не обязательно в самом приложении.
            "lmstudio_vram_mb": (system.process_vram_mb([cfg.lm_process, "llama-server"])
                                if running else None),
            "ram_used_mb": mem.get("used_mb"),
            "ram_total_mb": mem.get("total_mb"),
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

    if c == "set_lm_port":
        raw = (args or {}).get("port")
        try:
            port = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ValueError(f"set_lm_port: порт должен быть числом, а не {raw!r}")
        if not (1 <= port <= 65535):
            raise ValueError(f"set_lm_port: порт вне диапазона 1–65535: {raw!r}")
        cfg.data.setdefault("lmstudio", {})["api_port"] = port
        save_config(cfg)
        return {"ok": True, "command": "set_lm_port", "lmstudio_api_port": port}

    # недостижимо
    raise ValueError(f"неизвестная команда {command!r}")
