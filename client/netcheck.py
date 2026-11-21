"""Проверка доступности ПК: системный ping (кроссплатформенно).

Используется штатная утилита ping:
    Windows:  ping -n 1 -w <ms> <host>
    macOS:    ping -c 1 -t <s>  <host>
    Linux:    ping -c 1 -W <s>  <host>
"""
from __future__ import annotations

import platform
import subprocess


def ping_host(host: str, timeout: float = 2.0) -> bool:
    """Возвращает True, если хост ответил на ping, иначе False."""
    host = (host or "").strip()
    if not host:
        raise ValueError("IP/хост компьютера не задан (раздел «ПК» в настройках)")

    system = platform.system()
    t_int = max(1, int(round(timeout)))
    if system == "Windows":
        args = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
    elif system == "Darwin":
        args = ["ping", "-c", "1", "-t", str(t_int), host]
    else:
        args = ["ping", "-c", "1", "-W", str(t_int), host]

    try:
        res = subprocess.run(args, capture_output=True, timeout=max(3.0, timeout + 1.5))
        return res.returncode == 0
    except FileNotFoundError:
        raise RuntimeError("утилита ping не найдена в системе")
    except subprocess.TimeoutExpired:
        return False
