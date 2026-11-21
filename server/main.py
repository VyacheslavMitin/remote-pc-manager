"""Точка входа сервера (фоновый HTTP-сервер; целевая ОС — Windows 11).

Запуск в консоли (из каталога server/):
    python main.py

Фоновый запуск на Windows — см. start_background.py и start_server.bat.
"""
from __future__ import annotations

import sys


def main() -> int:
    from config import load
    from log import setup
    from server import serve

    cfg = load()
    log = setup(cfg)
    log.info(
        "RPCM server запускается (порт %s, процесс LM Studio: %r, гибернация: %s)",
        cfg.port, cfg.lm_process, cfg.hibernate_method,
    )
    serve(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
