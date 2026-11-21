"""HTTP-клиент для сервера RPCM (stdlib urllib, без внешних зависимостей).

Отправляет POST /command {"command": "..."} и разбирает JSON-ответ.
Сервер отвечает {"ok": true, ...} или {"ok": false, "error": "..."};
последнее превращается в ServerError, чтобы GUI показал человекочитаемый текст.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request


class ServerError(Exception):
    """Ошибка общения с сервером (нет связи, таймаут, ошибка сервера)."""


def request(host: str, port: int, command: str, timeout: float = 5.0,
            args: dict | None = None) -> dict:
    """Выполняет команду на сервере и возвращает распарсенный JSON (ok=true).

    args — дополнительные поля запроса (например {"port": 1234} для
    set_lm_port); идут в тело POST рядом с "command"."""
    host = (host or "").strip()
    if not host:
        raise ServerError("IP компьютера не задан (поле «IP компьютера» в настройках)")
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ServerError(f"некорректный порт сервера: {port!r}")

    url = f"http://{host}:{port}/command"
    payload = json.dumps({"command": command, **(args or {})}).encode("utf-8")
    req = urllib.request.Request(
        url, data=payload, method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "rpcm-client/1.0"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            code = resp.getcode()
    except urllib.error.HTTPError as e:
        # сервер ответил, но с ошибочным статусом — читаем его JSON
        try:
            obj = json.loads(e.read().decode("utf-8"))
            raise ServerError(str(obj.get("error") or f"HTTP {e.code}"))
        except json.JSONDecodeError:
            raise ServerError(f"сервер вернул HTTP {e.code}")
    except (urllib.error.URLError, OSError) as e:
        reason = getattr(e, "reason", None) or e
        raise ServerError(f"нет соединения с {host}:{port} ({reason})")
    except TimeoutError as e:
        raise ServerError(f"таймаут соединения с {host}:{port}")

    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        raise ServerError("ответ сервера не является JSON")
    if not isinstance(obj, dict) or not obj.get("ok"):
        raise ServerError(str((obj or {}).get("error") or "сервер вернул ошибку"))
    return obj


def status(host: str, port: int, timeout: float = 5.0) -> dict:
    """Удобная обёртка: команда «status» (подтверждает и сервер, и LM Studio)."""
    return request(host, port, "status", timeout=timeout)
