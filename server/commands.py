"""Диспетчер команд сервера.

Поддерживаемые команды (тело POST /command: {"command": "<имя>"}):
    status           {"ok": true, "command": "status", "lmstudio_running": bool,
                      "lmstudio_version": "<версия из VersionInfo exe, или null>",
                      "lmstudio_model": "<id загруженной модели (API, /v1/models), или null>",
                      "lmstudio_context": "<контекст модели (токены, API /api/v0/models), или null>",
                      "lmstudio_vram_mb": "<VRAM модели — самый крупный процесс на GPU (PowerShell Get-Counter), МБ; null — не запущена / модель не загружена (нет контекста) / нет PowerShell>",
                      "strata_running": bool,
                      "strata_version": "<версия движка Strata из engine/BUILD.json (рядом с пакетником запуска), или null>",
                      "strata_model": "<id модели Strata (открытый GET /health), или null>",
                      "strata_context": "<max_context модели Strata (токены, /health), или null>",
                      "strata_loaded": bool,
                      "strata_vram_mb": "<VRAM — самый крупный процесс на GPU, МБ; null — Strata не запущена / модель не загружена / нет PowerShell. ВНИМАНИЕ: когда LM Studio и Strata загружены одновременно, это память крупнейшей из двух моделей — блок Strata может показать VRAM LM Studio (и наоборот)>",
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
    start_strata    -> {"ok": true, "pid": int, "bat": "<путь>", ...}
    stop_strata     -> {"ok": true, "killed": [pid, ...]|None,
                        "note": "остановлена аккуратно|принудительно|не был запущен"}
    set_strata_port тело {"command": "set_strata_port", "port": 8080}
                    -> {"ok": true, "command": "set_strata_port", "strata_api_port": 8080}
                       (задаёт strata.api_port и сохраняет его в config.json)
    vram_debug      -> {"ok": true, "command": "vram_debug",
                        "compute_apps": {rc, stdout, stderr},
                        "gpu": {rc, stdout, stderr},
                        "rows": [{name, mem_mb, match}, ...]}
                       (отладка VRAM: сырые выходы nvidia-smi; на старом
                       сервере команды нет — "неизвестная команда")
"""
from __future__ import annotations

import platform
import re
import socket
import subprocess
import time

import hibernate
import lmstudio
import strata
import system
from config import Config, save as save_config

SUPPORTED = ("status", "hibernate", "start_lmstudio", "stop_lmstudio", "set_lm_port",
             "start_strata", "stop_strata", "set_strata_port", "vram_debug")


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
        model = lmstudio.loaded_model(cfg.lm_api_port)
        context = lmstudio.loaded_context(cfg.lm_api_port)
        # Strata: /health открыт и отвечает за миллисекунды — если он
        # ответил, процесс искать не нужно (WMI ~1-2 с экономим всегда,
        # когда Strata жива). Если /health молчит (порт не совпал /
        # загружается) — проверяем наличие процесса.
        st_health = strata.health(cfg.strata_api_port)
        st_running = st_health is not None or bool(strata.find_pids())
        st_loaded = bool((st_health or {}).get("loaded"))
        mem = system.memory_info() or {}
        return {
            "ok": True,
            "command": "status",
            "lmstudio_running": running,
            "lmstudio_version": lmstudio.version(cfg.lm_exe),
            "lmstudio_model": model,
            "lmstudio_context": context,
            # VRAM модели — самый крупный процесс на GPU (Get-Counter) —
            # только когда LM Studio запущена И модель реально загружена
            # (контекст известен: state == «loaded» в /api/v0/models).
            # Одного `model` недостаточно: /v1/models отдаёт каталог
            # скачанных моделей даже без загруженной — тогда в заголовок
            # попала бы память чужого приложения.
            "lmstudio_vram_mb": (
                system.gpu_process_vram_mb() if (running and context) else None
            ),
            "strata_running": st_running,
            "strata_version": strata.version(cfg.strata_exe),
            "strata_model": (st_health or {}).get("model"),
            "strata_context": (st_health or {}).get("max_context"),
            "strata_loaded": st_loaded,
            # VRAM — как у LM Studio: крупнейший процесс на GPU; только
            # когда Strata запущена и её модель реально загружена.
            "strata_vram_mb": (
                system.gpu_process_vram_mb() if (st_running and st_loaded) else None
            ),
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

    if c == "start_strata":
        info = strata.start(cfg.strata_exe)
        return {"ok": True, "command": "start_strata", **info}

    if c == "stop_strata":
        info = strata.stop()
        return {"ok": True, "command": "stop_strata", **info}

    if c == "vram_debug":
        # Отладка: сырые выходы nvidia-smi + разбор строк по names.
        return {
            "ok": True,
            "command": "vram_debug",
            **system.vram_debug([cfg.lm_process, "llama-server"]),
        }

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

    if c == "set_strata_port":
        raw = (args or {}).get("port")
        try:
            port = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ValueError(f"set_strata_port: порт должен быть числом, а не {raw!r}")
        if not (1 <= port <= 65535):
            raise ValueError(f"set_strata_port: порт вне диапазона 1–65535: {raw!r}")
        cfg.data.setdefault("strata", {})["api_port"] = port
        save_config(cfg)
        return {"ok": True, "command": "set_strata_port", "strata_api_port": port}

    # недостижимо
    raise ValueError(f"неизвестная команда {command!r}")
