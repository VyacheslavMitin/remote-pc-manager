"""Управление процессом LM Studio: проверка, запуск, остановка.

Windows:
    check    -> tasklist /FI "IMAGENAME eq <name>"
    start    -> subprocess.Popen([exe], CREATE_NEW_PROCESS_GROUP)
    stop     -> taskkill /F /IM <name>

macOS/Linux (для разработки/тестов):
    check    -> pgrep -f <base>
    start    -> Popen([exe])  или  open -a "LM Studio"
    stop     -> pkill -f <base>
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess


def _system() -> str:
    return platform.system()


def _base_name(process_name: str) -> str:
    """'LM Studio.exe' -> 'LM Studio' (для pgrep/pkill на unix)."""
    p = (process_name or "").strip()
    if p.lower().endswith(".exe"):
        return p[: -len(".exe")]
    return p


def is_running(process_name: str) -> bool:
    name = (process_name or "").strip()
    if not name:
        return False
    if _system() == "Windows":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
            return name.lower() in out.lower()
        except Exception:
            return False
    base = _base_name(name)
    if not base:
        return False
    try:
        res = subprocess.run(["pgrep", "-f", base], capture_output=True)
        return res.returncode == 0
    except FileNotFoundError:
        # fallback: ps
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "command="], capture_output=True, text=True
            ).stdout
            return base.lower() in out.lower()
        except Exception:
            return False


def start(exe: str) -> dict:
    exe = (exe or "").strip()
    if _system() == "Windows":
        if not exe:
            raise ValueError("lmstudio.exe не задан в конфиге")
        target = exe
        if not os.path.exists(exe):
            found = shutil.which(exe) or shutil.which(_base_name(exe) + ".exe")
            if not found:
                raise FileNotFoundError(f"исполняемый файл не найден: {exe}")
            target = found
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        proc = subprocess.Popen(
            [target],
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            close_fds=True,
        )
        return {"pid": proc.pid, "exe": target}

    # ---- unix (dev/test) ----
    if exe:
        if not os.path.exists(exe):
            raise FileNotFoundError(f"исполняемый файл не найден: {exe}")
        proc = subprocess.Popen(
            [exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"pid": proc.pid, "exe": exe}
    # macOS: открыть приложение по имени
    app_name = "LM Studio"
    res = subprocess.run(["open", "-a", app_name], capture_output=True)
    if res.returncode == 0:
        return {"opened": app_name}
    raise FileNotFoundError(
        f"не удалось запустить {app_name}; задайте lmstudio.exe в конфиге"
    )


def stop(process_name: str) -> dict:
    name = (process_name or "").strip()
    if not name:
        raise ValueError("lmstudio.process_name пуст")
    if _system() == "Windows":
        res = subprocess.run(
            ["taskkill", "/F", "/IM", name], capture_output=True, text=True
        )
        if res.returncode == 0:
            return {"killed": name}
        err = (res.stderr or res.stdout or "").strip()
        low = err.lower()
        if "not found" in low or "не найден" in low or "нет задач" in low:
            return {"killed": None, "note": "процесс не был запущен"}
        raise RuntimeError(f"taskkill завершился с ошибкой: {err}")
    base = _base_name(name)
    if not base:
        raise ValueError("lmstudio.process_name пуст")
    res = subprocess.run(["pkill", "-f", base], capture_output=True)
    if res.returncode == 0:
        return {"killed": base}
    if not is_running(name):
        return {"killed": None, "note": "процесс не был запущен"}
    raise RuntimeError("pkill завершился с ошибкой (процесс мог быть защищён)")
