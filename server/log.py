"""Настройка логирования: файл (по умолчанию рядом с сервером) + консоль."""
from __future__ import annotations

import logging

from config import Config


def setup(cfg: Config) -> logging.Logger:
    level = getattr(logging, cfg.log_level, logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # сброс старых хендлеров (при повторном запуске в том же процессе)
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        file_handler = logging.FileHandler(cfg.log_file, encoding="utf-8")
        file_handler.setFormatter(fmt)
        root.addHandler(file_handler)
    except Exception as exc:  # файл недоступен — не роняем сервер
        print(f"[warn] не удалось открыть лог-файл {cfg.log_file}: {exc}")

    stream = logging.StreamHandler()
    stream.setFormatter(fmt)
    root.addHandler(stream)

    return logging.getLogger("rpcm.server")
