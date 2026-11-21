#!/usr/bin/env python3
"""Веб-раздача интерфейса remote-pc-manager (web/index.html).

Запускает простой HTTP-сервер на корне проекта, чтобы страница могла
подтягивать client/config.json (IP/порты — там, не в коде).

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
import os
import socket
import sys
from functools import partial

# Корень проекта = родитель каталога web/ (отсюда запускаем и web/ и client/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lan_ip() -> str:
    """Локальный IP в Wi-Fi сети (без подключения к интернету)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> int:
    ap = argparse.ArgumentParser(description="Веб-раздача web/index.html")
    ap.add_argument("--port", type=int, default=8080, help="порт (по умолчанию 8080)")
    ap.add_argument("--host", default="0.0.0.0", help="адрес привязки (по умолчанию 0.0.0.0)")
    args = ap.parse_args()

    handler = partial(http.server.SimpleHTTPRequestHandler, directory=ROOT)
    try:
        httpd = http.server.ThreadingHTTPServer((args.host, args.port), handler)
    except OSError as e:
        print(f"✗ Не удалось занять {args.host}:{args.port}: {e}", file=sys.stderr)
        return 1

    url_path = "/web/index.html"
    print(f"Раздаю: {ROOT}")
    print(f"  этот компьютер : http://127.0.0.1:{args.port}{url_path}")
    print(f"  из сети (айфон): http://{lan_ip()}:{args.port}{url_path}")
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
