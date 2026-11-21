"""Запуск гибернации/сна после отправки HTTP-ответа.

Windows:
    rundll32  -> rundll32.exe powrprof.dll,SetSuspendState 0,1,0
    shutdown  -> shutdown /h /f

macOS/Linux (dev/test): pmset sleepnow (или аналог) — только чтобы код
отработал на других системах; на Windows используются штатные команды.

Важно: запуск выполняется в отдельном потоке с небольшой задержкой, чтобы
HTTP-ответ успел дойти до клиента, прежде чем машина погаснет.
"""
from __future__ import annotations

import platform
import subprocess
import threading
import time


def _do_hibernate(method: str) -> None:
    system = platform.system()
    if system == "Windows":
        if method == "shutdown":
            subprocess.run(["shutdown", "/h", "/f"])
        else:
            subprocess.run(
                ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]
            )
    else:
        # best-effort на других ОС (для разработки)
        try:
            if system == "Darwin":
                subprocess.run(["pmset", "sleepnow"])
            else:
                subprocess.run(["systemctl", "hibernate"])
        except Exception:
            pass


def trigger(method: str = "rundll32", delay_s: float = 1.0) -> None:
    """Планирует гибернацию в фоновом потоке через delay_s секунд."""
    def _worker() -> None:
        try:
            time.sleep(max(0.0, float(delay_s)))
        except Exception:
            pass
        try:
            _do_hibernate(method)
        except Exception:
            # не критично: машина может уже быть не в сети
            pass

    threading.Thread(target=_worker, name="hibernate", daemon=True).start()
