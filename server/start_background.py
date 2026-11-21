"""Запуск сервера в фоне (отделённый процесс, без привязки к консоли).

Windows:  DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP, вывод -> server.out.log
unix:     start_new_session,  вывод -> server.out.log

Запуск:   python start_background.py
Остановка:
    Windows:  taskkill /F /PID <pid>
    unix:     kill <pid>
PID печатается в консоль при запуске.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MAIN_PY = os.path.join(HERE, "main.py")
OUT_LOG = os.path.join(HERE, "server.out.log")


def start_background() -> int:
    py = sys.executable or "python"
    with open(OUT_LOG, "ab") as out:
        if platform.system() == "Windows":
            DETACHED = 0x00000008
            NEW_GROUP = 0x00000200
            proc = subprocess.Popen(
                [py, MAIN_PY],
                cwd=HERE,
                stdout=out,
                stderr=subprocess.STDOUT,
                creationflags=DETACHED | NEW_GROUP,
                close_fds=True,
            )
        else:
            proc = subprocess.Popen(
                [py, MAIN_PY],
                cwd=HERE,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    print(f"сервер запущен в фоне: PID={proc.pid}")
    print(f"stdout/stderr -> {OUT_LOG}")
    print(f"лог команд      -> {os.path.join(HERE, 'server.log')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(start_background())
