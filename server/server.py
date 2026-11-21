"""HTTP-сервер (стандартная библиотека, без внешних зависимостей).

Эндпоинты:
    POST /command   тело {"command": "status"|"hibernate"|
                        "start_lmstudio"|"stop_lmstudio"|"set_lm_port",
                        ...доп. поля, напр. "port"}
    GET  /status    то же, что команда "status" (удобно для проверки из браузера)
    GET  /          {"ok": true, "service": "rpcm-server"}

Ответы всегда JSON. Ошибки -> {"ok": false, "error": "..."}.
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from commands import run
from config import Config


class Handler(BaseHTTPRequestHandler):
    server_version = "RPCM/1.0"
    # проставляется в serve()
    cfg: Config | None = None

    # ---------- утилиты ----------
    def _send_json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _cfg(self) -> Config:
        if self.cfg is None:
            raise RuntimeError("сервер не инициализирован")
        return self.cfg

    # ---------- HTTP ----------
    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        if path == "/status":
            self._handle_command("status", {})
        elif path == "/":
            self._send_json(200, {"ok": True, "service": "rpcm-server"})
        else:
            self._send_json(404, {"ok": False, "error": "не найдено; используйте POST /command"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/")
        if path != "/command":
            self._send_json(404, {"ok": False, "error": "не найдено; используйте POST /command"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception as exc:
            self._send_json(400, {"ok": False, "error": f"тело не является JSON: {exc}"})
            return
        if not isinstance(payload, dict):
            self._send_json(400, {"ok": False, "error": "ожидается объект JSON"})
            return
        command = str(payload.get("command", "") or "")
        # всё, кроме "command", — аргументы команды (напр. "port" для
        # set_lm_port)
        args = {k: v for k, v in payload.items() if k != "command"}
        self._handle_command(command, args)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    # ---------- логика ----------
    def _handle_command(self, command: str, args: dict | None = None) -> None:
        log = logging.getLogger("rpcm.server")
        log.info("команда: %r  от %s", command, self.address_string())
        try:
            result = run(command, self._cfg(), args)
        except ValueError as exc:
            self._send_json(400, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:  # noqa: BLE001
            log.exception("команда завершилась ошибкой")
            self._send_json(500, {"ok": False, "error": f"внутренняя ошибка: {exc}"})
            return
        log.info("команда %r -> %s", command, json.dumps(result, ensure_ascii=False))
        self._send_json(200, result)

    # ---------- доступный лог http.server ----------
    def log_message(self, fmt: str, *args) -> None:
        logging.getLogger("rpcm.http").debug("%s %s", self.address_string(), fmt % args)


def serve(cfg: Config) -> None:
    Handler.cfg = cfg
    httpd = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    log = logging.getLogger("rpcm.server")
    display_host = "0.0.0.0" if cfg.host == "0.0.0.0" else cfg.host
    log.info("сервер слушает http://%s:%s", display_host, cfg.port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        log.info("остановлено по Ctrl+C")
    finally:
        httpd.server_close()
