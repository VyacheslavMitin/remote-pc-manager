"""Конфигурация сервера.

Всё, что зависит от ОС и установки (порт, путь к LM Studio, имя процесса,
метод гибернации, файл лога) живёт в JSON-конфиге, а не захардкожено.
Код кроссплатформенный: на Windows используются tasklist/taskkill/rundll32,
на macOS/Linux — pgrep/pkill/pmset, чтобы проект можно было тестировать и
на других системах.
"""
from __future__ import annotations

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "host": "0.0.0.0",
    "port": 8787,
    "lmstudio": {
        # Путь к исполняемому файлу LM Studio.
        # Windows (пример): C:\\Users\\<user>\\AppData\\Local\\Programs\\LM Studio\\LM Studio.exe
        # Если пусто — на Windows будет поиск по PATH, на macOS — `open -a "LM Studio"`.
        "exe": "",
        # Имя процесса для проверки/остановки. На Windows — с .exe.
        "process_name": "LM Studio.exe",
        # Порт локального API-сервера LM Studio (загруженные модели, /v1/models).
        "api_port": 1234,
    },
    "strata": {
        # Путь к пакетнику запуска Strata (START-HERE.bat). Пусто —
        # стандарт C:\AI\Strata\strata-main\START-HERE.bat.
        "exe": "",
        # Порт локального API-сервера Strata (OpenAI-совместимый, как у
        # LM Studio; состояние читаем из открытого /health). Стандарт — 8080.
        "api_port": 8080,
    },
    "hibernate": {
        # "rundll32" -> rundll32.exe powrprof.dll,SetSuspendState 0,1,0
        # "shutdown" -> shutdown /h /f
        "method": "rundll32",
        # Задержка (сек) между отправкой ответа и реальным усыплением,
        # чтобы клиент успел получить HTTP-ответ.
        "delay_s": 1.0,
    },
    "log_file": "server.log",
    "log_level": "INFO",
}


def _deep_merge(base: dict, override: dict | None) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    def __init__(self, data: dict, path: str | None = None):
        self.data = data
        # Откуда загружен конфиг (config.json / config.example.json) — save()
        # пишет обратно в тот же файл, если явно не задан path.
        self.path = path

    # --- общие ---
    @property
    def host(self) -> str:
        return str(self.data["host"])

    @property
    def port(self) -> int:
        return int(self.data["port"])

    # --- LM Studio ---
    @property
    def lm_exe(self) -> str:
        return str(self.data["lmstudio"].get("exe", "") or "").strip()

    @property
    def lm_process(self) -> str:
        return str(self.data["lmstudio"].get("process_name", "LM Studio.exe")).strip()

    @property
    def lm_api_port(self) -> int:
        """Порт локального API-сервера LM Studio (загруженные модели)."""
        return int(self.data["lmstudio"].get("api_port", 1234))

    # --- Strata ---
    @property
    def strata_exe(self) -> str:
        return str(self.data.get("strata", {}).get("exe", "") or "").strip()

    @property
    def strata_api_port(self) -> int:
        """Порт локального API-сервера Strata (открытый /health)."""
        return int(self.data.get("strata", {}).get("api_port", 8080))

    # --- гибернация ---
    @property
    def hibernate_method(self) -> str:
        return str(self.data["hibernate"].get("method", "rundll32")).strip().lower()

    @property
    def hibernate_delay(self) -> float:
        return float(self.data["hibernate"].get("delay_s", 1.0))

    # --- логирование ---
    @property
    def log_file(self) -> str:
        lf = str(self.data.get("log_file", "server.log"))
        if not os.path.isabs(lf):
            lf = os.path.join(BASE_DIR, lf)
        return lf

    @property
    def log_level(self) -> str:
        return str(self.data.get("log_level", "INFO")).upper()


def load(path: str | None = None) -> Config:
    """Загружает конфиг: config.json (если есть), иначе config.example.json."""
    if path is None:
        path = os.path.join(BASE_DIR, "config.json")
        if not os.path.exists(path):
            path = os.path.join(BASE_DIR, "config.example.json")
    data = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    data = _deep_merge(DEFAULTS, data)
    return Config(data, path if os.path.exists(path) else None)


EXAMPLE_PATH = os.path.join(BASE_DIR, "config.example.json")


def save(cfg: Config, path: str | None = None) -> str:
    """Сохраняет конфиг (данные с подставленными дефолтами) в файл.

    `path` — явная цель (в тестах); по умолчанию — тот файл, из которого
    конфиг загружен. Если это config.example.json (коммитный файл-пример),
    рядом создаётся новый config.json."""
    target = path or cfg.path or os.path.join(BASE_DIR, "config.json")
    # файл-пример (config.example.json) — не перезаписываем: рядом с ним
    # создаём обычный config.json
    if os.path.basename(os.path.abspath(target)) == "config.example.json":
        target = os.path.join(os.path.dirname(os.path.abspath(target)), "config.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(cfg.data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return target
