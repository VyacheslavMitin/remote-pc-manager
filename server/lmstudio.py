"""Управление процессом LM Studio: проверка, запуск, остановка.

Windows:
    check    -> tasklist /FI "IMAGENAME eq <name>"
    start    -> subprocess.Popen([exe], CREATE_NEW_PROCESS_GROUP)
    stop     -> taskkill /IM (WM_CLOSE, аккуратно) -> ждём -> taskkill /F /IM

macOS/Linux (для разработки/тестов):
    check    -> pgrep -f <base>
    start    -> Popen([exe])  или  open -a "LM Studio"
    stop     -> аккуратно: osascript quit (macOS) / SIGTERM,
                затем SIGKILL, если не завершилось за отведённое время.

Остановка всегда «мягкая» сначала: приложение успевает сохранить состояние,
принудительное убийство — только как fallback.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import time

# Сколько секунд давать приложению на аккуратное завершение.
GRACEFUL_TIMEOUT_S = 8.0


def _wait_gone(process_name: str, timeout_s: float = GRACEFUL_TIMEOUT_S) -> bool:
    """Ждать, пока процесс исчезнет (опрос is_running). True — исчез."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not is_running(process_name):
            return True
        time.sleep(0.3)
    return not is_running(process_name)


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
    """Остановить LM Studio аккуратно, затем — принудительно.

    Windows: taskkill /IM (WM_CLOSE) -> ждём -> taskkill /F /IM.
    macOS:   osascript quit          -> ждём -> pkill -x -> pkill -KILL.
    Linux:   pkill (SIGTERM)         -> ждём -> pkill -KILL.
    """
    name = (process_name or "").strip()
    if not name:
        raise ValueError("lmstudio.process_name пуст")
    base = _base_name(name)
    if not base:
        raise ValueError("lmstudio.process_name пуст")

    if not is_running(name):
        return {"killed": None, "note": "процесс не был запущен"}

    if _system() == "Windows":
        # Аккуратно: WM_CLOSE без /F — приложение закрывается штатно.
        subprocess.run(["taskkill", "/IM", name], capture_output=True, text=True)
        if _wait_gone(name):
            return {"killed": name, "note": "остановлена аккуратно"}
        # Fallback: принудительно.
        res = subprocess.run(
            ["taskkill", "/F", "/IM", name], capture_output=True, text=True
        )
        if res.returncode == 0 and not is_running(name):
            return {"killed": name, "note": "остановлена принудительно"}
        err = (res.stderr or res.stdout or "").strip()
        low = err.lower()
        if "not found" in low or "не найден" in low or "нет задач" in low:
            return {"killed": None, "note": "процесс не был запущен"}
        raise RuntimeError(f"taskkill завершился с ошибкой: {err}")

    if _system() == "Darwin":
        # Аккуратно: AppleScript quit (приложение успевает сохранить состояние).
        subprocess.run(
            ["osascript", "-e", f'tell application "{base}" to quit'],
            capture_output=True,
            timeout=20,
        )
        if _wait_gone(name):
            return {"killed": base, "note": "остановлена аккуратно"}
        # Fallback: SIGTERM по точному имени процесса…
        subprocess.run(["pkill", "-x", base], capture_output=True)
        if _wait_gone(name, 3.0):
            return {"killed": base, "note": "остановлена принудительно"}
        # …и в последнюю очередь SIGKILL по командной строке.
        subprocess.run(["pkill", "-KILL", "-f", base], capture_output=True)
        if not is_running(name):
            return {"killed": base, "note": "остановлена принудительно"}
        raise RuntimeError("pkill не смог завершить процесс")

    # Linux: SIGTERM, затем SIGKILL.
    subprocess.run(["pkill", "-x", base], capture_output=True)
    if _wait_gone(name):
        return {"killed": base, "note": "остановлена аккуратно"}
    subprocess.run(["pkill", "-KILL", "-x", base], capture_output=True)
    if not is_running(name):
        return {"killed": base, "note": "остановлена принудительно"}
    raise RuntimeError("pkill не смог завершить процесс")
