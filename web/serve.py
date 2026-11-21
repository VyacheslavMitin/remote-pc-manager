#!/usr/bin/env python3
"""Веб-раздача интерфейса remote-pc-manager (web/index.html) + WoL-эндпоинт.

Запускает простой HTTP-сервер на корне проекта, чтобы страница могла
подтягивать client/config.json (IP/порты — там, не в коде).

Плюс эндпоинт WoL:
    POST /wol   тело {"mac": "AA:BB:CC:DD:EE:FF"} (необязательно —
                возьмётся из client/config.json → pc.mac)
                -> {"ok": true, "sent": 3, "to": "255.255.255.255:9", "mac": "..."}
    Браузер сам UDP broadcast слать не умеет, а мак (всегда включён) — умеет:
    именно он будит спящий ПК magic packet'ом (та же логика, что и в
    desktop-клиенте: client/wol.py).

Запуск:
    python3 web/serve.py [--port 8080] [--host 0.0.0.0]

После старта скрипт печатает ссылки:
    http://127.0.0.1:<port>/web/index.html      — с этого компьютера
    http://<IP-сети>:<port>/web/index.html      — с айфона/другого устройства
                                                   (в той же Wi-Fi сети)
Остановка: Ctrl+C.
"""

import argparse
import http.server
import json
import os
import socket
import sys
from functools import partial

# Корень проекта = родитель каталога web/ (отсюда запускаем и web/ и client/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# client/wol.py — готовая сборка и отправка magic packet (переиспользуем)
sys.path.insert(0, os.path.join(ROOT, "client"))
import wol  # noqa: E402  # type: ignore[reportMissingImports]


def lan_ip() -> str:
    """Локальный IP в Wi-Fi сети (без подключения к интернету)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def default_mac() -> str | None:
    """MAC целевого ПК из client/config.json (pc.mac), или None."""
    try:
        with open(os.path.join(ROOT, "client", "config.json"), encoding="utf-8") as f:
            data = json.load(f)
        mac = (data.get("pc") or {}).get("mac")
        if mac:
            return wol.normalize_mac(str(mac))
    except (OSError, ValueError, KeyError):
        pass
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    """Статика с корня проекта + POST /wol (будит ПК с мака)."""

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/wol":
            self._json(404, {"ok": False, "error": f"неизвестный эндпоинт: {self.path}"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except (ValueError, UnicodeDecodeError):
            data = {}
        mac = str(data.get("mac") or "").strip() or default_mac() or ""
        if not mac:
            self._json(400, {"ok": False, "error": "MAC не задан: тело {\"mac\": \"...\"} или client/config.json → pc.mac"})
            return
        try:
            info = wol.send_wol(mac)
        except ValueError as e:
            self._json(400, {"ok": False, "error": str(e)})
            return
        self._json(200, {"ok": True, **info})


def main() -> int:
    ap = argparse.ArgumentParser(description="Веб-раздача web/index.html + WoL")
    ap.add_argument("--port", type=int, default=8080, help="порт (по умолчанию 8080)")
    ap.add_argument("--host", default="0.0.0.0", help="адрес привязки (по умолчанию 0.0.0.0)")
    args = ap.parse_args()

    handler = partial(Handler, directory=ROOT)
    try:
        httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as e:
        print(f"✗ Не удалось занять {args.host}:{args.port}: {e}", file=sys.stderr)
        return 1

    url_path = "/web/index.html"
    print(f"Раздаю: {ROOT}")
    print(f"  этот компьютер : http://127.0.0.1:{args.port}{url_path}")
    print(f"  из сети (айфон): http://{lan_ip()}:{args.port}{url_path}")
    print(f"  WoL            : POST http://127.0.0.1:{args.port}/wol  (мак будит ПК)")
    print("Ctrl+C — остановить")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
