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

Защита токеном (для вывода в интернет через nginx-проброс):
    client/config.json → "web_token": "<секрет>"
    - токен задан  : страницы/конфиг/WoL — только с токеном (cookie,
                     заголовок X-Token или ?token=...); вход — POST /login;
    - токен пустой : защита выключена (локальный режим, как раньше).

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
import secrets
import socket
import sys
from functools import partial
from urllib.parse import parse_qs

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


def _load_config() -> dict:
    try:
        with open(os.path.join(ROOT, "client", "config.json"), encoding="utf-8") as f:
            return json.load(f) or {}
    except (OSError, ValueError):
        return {}


def web_token() -> str:
    """Токен доступа из client/config.json → web_token (пусто = без защиты)."""
    return str(_load_config().get("web_token") or "").strip()


TOKEN = web_token()
COOKIE = "rpcm_token"

LOGIN_PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>remote-pc-manager — вход</title>
<style>
  :root { color-scheme: dark; }
  * { box-sizing: border-box; }
  body { margin: 0; min-height: 100vh; display: flex; align-items: center;
         justify-content: center; background: #1e1e20; color: #e6e6e6;
         font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  .card { background: #242428; border: 1px solid #3a3a40; border-radius: 12px;
          padding: 28px 26px; width: 340px; max-width: calc(100vw - 32px); }
  h1 { font-size: 16px; margin: 0 0 16px; }
  input { width: 100%; padding: 10px 12px; border-radius: 8px;
          border: 1px solid #3a3a40; background: #222226; color: #e6e6e6;
          font-size: 14px; }
  button { margin-top: 12px; width: 100%; padding: 10px; border: 0;
           border-radius: 8px; background: #1f6feb; color: #fff;
           font-size: 14px; cursor: pointer; }
  .err { color: #f85149; font-size: 13px; margin-top: 10px; min-height: 1em; }
  .muted { color: #9a9aa2; font-size: 12px; margin-top: 14px; line-height: 1.4; }
</style>
</head>
<body>
<form class="card" method="post" action="/login">
  <h1>remote-pc-manager</h1>
  <input type="password" name="token" placeholder="Токен" autocomplete="off" autofocus>
  <div class="err">{err}</div>
  <button type="submit">Войти</button>
  <div class="muted">Токен — ключ web_token в client/config.json на машине
  с веб-сервером (мак/NAS).</div>
</form>
</body>
</html>
"""


def default_mac() -> str | None:
    """MAC целевого ПК из client/config.json (pc.mac), или None."""
    mac = (_load_config().get("pc") or {}).get("mac")
    if mac:
        return wol.normalize_mac(str(mac))
    return None


class Handler(http.server.SimpleHTTPRequestHandler):
    """Статика с корня проекта + POST /wol (будит ПК) + токен-защита."""

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _login_page(self, err: str = "") -> None:
        body = LOGIN_PAGE.replace("{err}", err).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- аутентификация ----------------------------------------------------

    def _token_from_request(self) -> str:
        cookie = self.headers.get("Cookie") or ""
        for part in cookie.split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE and v:
                return v
        h = (self.headers.get("X-Token") or "").strip()
        if h:
            return h
        if "?" in self.path:
            qs = parse_qs(self.path.split("?", 1)[1])
            if qs.get("token"):
                return qs["token"][0]
        return ""

    def _authed(self) -> bool:
        if not TOKEN:
            return True
        t = self._token_from_request()
        return bool(t) and secrets.compare_digest(t, TOKEN)

    def _require_auth(self) -> bool:
        """True — запрос пропущен. False — уже ответили (401/302/страница)."""
        if self._authed():
            return True
        path = self.path.split("?")[0]
        if path in ("/client/config.json", "/wol", "/favicon.ico"):
            self._json(401, {"ok": False, "error": "нужен токен"})
        else:
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Content-Length", "0")
            self.end_headers()
        return False

    # --- HTTP --------------------------------------------------------------

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Token")
        self.end_headers()

    def do_GET(self) -> None:
        if TOKEN:
            path = self.path.split("?")[0]
            if path == "/login":
                if self._authed():
                    self.send_response(302)
                    self.send_header("Location", "/web/index.html")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                else:
                    self._login_page()
                return
            if not self._require_auth():
                return
        super().do_GET()

    def do_POST(self) -> None:
        path = self.path.split("?")[0]

        if path == "/login":
            if not TOKEN:
                self._json(404, {"ok": False, "error": "защита выключена"})
                return
            self._do_login()
            return

        if path != "/wol":
            self._json(404, {"ok": False, "error": f"неизвестный эндпоинт: {self.path}"})
            return
        if not self._require_auth():
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

    def _do_login(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        token = ""
        if "application/json" in (self.headers.get("Content-Type") or ""):
            try:
                token = str((json.loads(raw.decode("utf-8")) or {}).get("token") or "")
            except (ValueError, UnicodeDecodeError):
                token = ""
        else:
            token = (parse_qs(raw.decode("utf-8", "replace")).get("token") or [""])[0]
        if token and secrets.compare_digest(token, TOKEN):
            self.send_response(302)
            self.send_header("Location", "/web/index.html")
            self.send_header("Set-Cookie", f"{COOKIE}={TOKEN}; Path=/; HttpOnly; SameSite=Lax")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._login_page("Неверный токен")


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
    if TOKEN:
        print("  защита        : ВКЛ (web_token из client/config.json)")
    else:
        print("  защита        : ВЫКЛ (в client/config.json нет web_token)")
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
