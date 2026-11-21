"""Конфигурация клиента (хранится в JSON рядом с приложением).

Поля:
    pc.ip             — IP удалённого ПК (для пинга И для сервера — это одна машина)
    pc.mac            — MAC удалённого ПК (для Wake-on-LAN)
    server.port       — порт HTTP-сервера (хост сервера = pc.ip)
    auto_check.enabled    — автопроверка состояния: вкл/выкл
    auto_check.interval_s — интервал автопроверки, в секундах
"""
from __future__ import annotations

import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")

DEFAULTS = {
    "pc": {
        "ip": "192.168.1.100",
        "mac": "AA:BB:CC:DD:EE:FF",
    },
    "server": {
        "port": 8787,
    },
    "auto_check": {
        "enabled": True,
        "interval_s": 10,
    },
}


def _deep_merge(base: dict, override: dict | None) -> dict:
    out = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def load() -> dict:
    """Читает config.json, подставляя дефолты для отсутствующих полей."""
    data = {}
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            data = {}
    data = _deep_merge(DEFAULTS, data)
    return data


def save(data: dict) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def path() -> str:
    return CONFIG_PATH
