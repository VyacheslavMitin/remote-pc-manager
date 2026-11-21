"""Управление процессом LM Studio: проверка, запуск, остановка, версия.

Windows:
    check    -> tasklist /FI "IMAGENAME eq <name>"
    start    -> subprocess.Popen([exe], CREATE_NEW_PROCESS_GROUP)
    stop     -> taskkill /IM (WM_CLOSE, аккуратно) -> ждём -> taskkill /F /IM
    version  -> powershell (Get-Item <exe>).VersionInfo.ProductVersion

macOS/Linux (для разработки/тестов):
    check    -> pgrep -f <base>
    start    -> Popen([exe])  или  open -a "LM Studio"
    stop     -> аккуратно: osascript quit (macOS) / SIGTERM,
                затем SIGKILL, если не завершилось за отведённое время.
    version  -> None (только Windows: версия — из VersionInfo exe-файла)

любая ОС:
    model    -> GET http://127.0.0.1:<api_port>/v1/models — id загруженной
                модели (локальный API-сервер LM Studio)

Остановка всегда «мягкая» сначала: приложение успевает сохранить состояние,
принудительное убийство — только как fallback.
"""
from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
import urllib.request

# Сколько секунд давать приложению на аккуратное завершение.
GRACEFUL_TIMEOUT_S = 8.0

# Кэш версии LM Studio: (версия, mtime exe). Версия меняется только при
# обновлении приложения (сменится mtime файла) — тогда перепроверяем.
# Без кэша каждый status-запрос запускал бы powershell (~1 с) — а клиент
# опрашивает status каждые 10 секунд.
_version_cache: tuple[str, float] | None = None
# Неудача чтения версии: повторять не чаще, чем раз в _VERSION_RETRY_S,
# чтобы не спамить powershell, пока exe недоступен.
_VERSION_RETRY_S = 60.0
_version_fail_at = 0.0


def _wait_gone(process_name: str, timeout_s: float = GRACEFUL_TIMEOUT_S) -> bool:
    """Ждать, пока процесс исчезнет (опрос is_running). True — исчез."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if not is_running(process_name):
            return True
        time.sleep(0.3)
    return not is_running(process_name)


def _system() -> str:
    return platform.system()


def _base_name(process_name: str) -> str:
    """'LM Studio.exe' -> 'LM Studio' (для pgrep/pkill на unix)."""
    p = (process_name or "").strip()
    if p.lower().endswith(".exe"):
        return p[: -len(".exe")]
    return p


def is_running(process_name: str) -> bool:
    name = (process_name or "").strip()
    if not name:
        return False
    if _system() == "Windows":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}"],
                capture_output=True,
                text=True,
                timeout=15,
            ).stdout
            return name.lower() in out.lower()
        except Exception:
            return False
    base = _base_name(name)
    if not base:
        return False
    try:
        res = subprocess.run(["pgrep", "-f", base], capture_output=True)
        return res.returncode == 0
    except FileNotFoundError:
        # fallback: ps
        try:
            out = subprocess.run(
                ["ps", "-A", "-o", "command="], capture_output=True, text=True
            ).stdout
            return base.lower() in out.lower()
        except Exception:
            return False


def _resolve_version_exe(exe: str) -> str:
    """Путь к exe для чтения версии: из конфига (если существует), иначе
    стандартный путь установки в %LOCALAPPDATA%. Пустая строка — exe не найден."""
    exe = (exe or "").strip()
    if exe and os.path.exists(exe):
        return exe
    default = os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "LM Studio", "LM Studio.exe",
    )
    if default and os.path.exists(default):
        return default
    return ""


def version(exe: str = "") -> str | None:
    """Версия установленной LM Studio (ProductVersion из VersionInfo exe).

    Только Windows:
        powershell -NoProfile -Command "(Get-Item -LiteralPath '<exe>').VersionInfo.ProductVersion"
    Результат кэшируется до смены mtime файла (обновление LM Studio);
    при неудаче повтор не чаще, чем раз в _VERSION_RETRY_S секунд.
    Возвращает строку версии ("0.3.25") или None (не Windows, exe не найден,
    прочитать не удалось). Клиент при None показывает старый формат заголовка.
    """
    global _version_cache, _version_fail_at
    if _system() != "Windows":
        return None
    path = _resolve_version_exe(exe)
    if not path:
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if _version_cache is not None:
        if _version_cache[1] == mtime:
            return _version_cache[0]
        # mtime сменён (обновление приложения) — перепроверяем вне retry-окна
    elif time.monotonic() - _version_fail_at < _VERSION_RETRY_S:
        return None  # недавняя неудача — не спамим powershell
    escaped = path.replace("'", "''")  # экранирование для однокавычной строки PS
    script = f"(Get-Item -LiteralPath '{escaped}').VersionInfo.ProductVersion"
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True, text=True, timeout=20,
        ).stdout.strip()
    except Exception:
        _version_fail_at = time.monotonic()
        return None
    if out and re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z.\-+]*", out):
        _version_cache = (out, mtime)
        return out
    _version_fail_at = time.monotonic()
    return None


# Максимальная длина id модели в заголовке (длинные GGUF-имена не должны
# раздвигать окно клиента).
_MODEL_ID_MAX = 48


def loaded_model(port: int = 1234) -> str | None:
    """ID загруженной в LM Studio модели через локальный API-сервер.

    GET http://127.0.0.1:<port>/v1/models (OpenAI-совместимый ответ:
    {"data": [{"id": "..."}, ...]}). Несколько загруженных моделей —
    только первый id (основная, обслуживающая запросы; остальные,
    напр. embedding-модели, в заголовок не попадают). None —
    API-сервер не запущен, порт закрыт, ответ не распознан или
    моделей нет (всё это нормально: LM Studio может работать без
    включённого API).
    Запрос быстрый локальный, кэшировать не нужно (состав моделей
    меняется динамически, клиент опрашивает status каждые 10 с).
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    url = f"http://127.0.0.1:{port}/v1/models"
    try:
        with urllib.request.urlopen(url, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        return None
    ids = [str(m["id"]).strip() for m in data
           if isinstance(m, dict) and str(m.get("id", "")).strip()]
    if not ids:
        return None
    first = ids[0]
    if len(first) > _MODEL_ID_MAX:
        first = first[:_MODEL_ID_MAX] + "…"
    return first


def _get_json(url: str, timeout: float = 3.0) -> dict | None:
    """GET url -> dict (JSON) или None при любой ошибке (соединение, HTTP, JSON)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None


def loaded_context(port: int = 1234) -> int | None:
    """Контекст загруженной модели (токены) через нативный API LM Studio.

    GET http://127.0.0.1:<port>/api/v0/models (LM Studio >= 0.3.6):
    {"data": [{"id": "qwen/qwen3.8-27b", "state": "loaded",
               "max_context_length": 262144, "loaded_context_length": 65536}]} —
    берём loaded_context_length у загруженной модели (state == «loaded»;
    если state нет — любое вхождение loaded_context_length).
    Фолбэк: GET /api/v1/models — models[].loaded_instances[].config.context_length.
    None, если API недоступен, модель не загружена или контекст не прислан
    (клиент просто не покажет контекст в заголовке).
    """
    try:
        port = int(port)
    except (TypeError, ValueError):
        return None
    data = _get_json(f"http://127.0.0.1:{port}/api/v0/models")
    for m in ((data or {}).get("data") or []):
        if m.get("state") and (m.get("state") or "").lower() != "loaded":
            continue
        v = m.get("loaded_context_length")
        if isinstance(v, int) and v > 0:
            return v
    data = _get_json(f"http://127.0.0.1:{port}/api/v1/models")
    for m in ((data or {}).get("models") or []):
        for inst in (m.get("loaded_instances") or []):
            v = (inst.get("config") or {}).get("context_length")
            if isinstance(v, int) and v > 0:
                return v
    return None


def start(exe: str) -> dict:
    exe = (exe or "").strip()
    if _system() == "Windows":
        if not exe:
            raise ValueError("lmstudio.exe не задан в конфиге")
        target = exe
        if not os.path.exists(exe):
            found = shutil.which(exe) or shutil.which(_base_name(exe) + ".exe")
            if not found:
                raise FileNotFoundError(f"исполняемый файл не найден: {exe}")
            target = found
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        proc = subprocess.Popen(
            [target],
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            close_fds=True,
        )
        return {"pid": proc.pid, "exe": target}

    # ---- unix (dev/test) ----
    if exe:
        if not os.path.exists(exe):
            raise FileNotFoundError(f"исполняемый файл не найден: {exe}")
        proc = subprocess.Popen(
            [exe],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {"pid": proc.pid, "exe": exe}
    # macOS: открыть приложение по имени
    app_name = "LM Studio"
    res = subprocess.run(["open", "-a", app_name], capture_output=True)
    if res.returncode == 0:
        return {"opened": app_name}
    raise FileNotFoundError(
        f"не удалось запустить {app_name}; задайте lmstudio.exe в конфиге"
    )


def stop(process_name: str) -> dict:
    """Остановить LM Studio аккуратно, затем — принудительно.

    Windows: taskkill /IM (WM_CLOSE) -> ждём -> taskkill /F /IM.
    macOS:   osascript quit          -> ждём -> pkill -x -> pkill -KILL.
    Linux:   pkill (SIGTERM)         -> ждём -> pkill -KILL.
    """
    name = (process_name or "").strip()
    if not name:
        raise ValueError("lmstudio.process_name пуст")
    base = _base_name(name)
    if not base:
        raise ValueError("lmstudio.process_name пуст")

    if not is_running(name):
        return {"killed": None, "note": "процесс не был запущен"}

    if _system() == "Windows":
        # Аккуратно: WM_CLOSE без /F — приложение закрывается штатно.
        subprocess.run(["taskkill", "/IM", name], capture_output=True, text=True)
        if _wait_gone(name):
            return {"killed": name, "note": "остановлена аккуратно"}
        # Fallback: принудительно.
        res = subprocess.run(
            ["taskkill", "/F", "/IM", name], capture_output=True, text=True
        )
        if res.returncode == 0 and not is_running(name):
            return {"killed": name, "note": "остановлена принудительно"}
        err = (res.stderr or res.stdout or "").strip()
        low = err.lower()
        if "not found" in low or "не найден" in low or "нет задач" in low:
            return {"killed": None, "note": "процесс не был запущен"}
        raise RuntimeError(f"taskkill завершился с ошибкой: {err}")

    if _system() == "Darwin":
        # Аккуратно: AppleScript quit (приложение успевает сохранить состояние).
        subprocess.run(
            ["osascript", "-e", f'tell application "{base}" to quit'],
            capture_output=True,
            timeout=20,
        )
        if _wait_gone(name):
            return {"killed": base, "note": "остановлена аккуратно"}
        # Fallback: SIGTERM по точному имени процесса…
        subprocess.run(["pkill", "-x", base], capture_output=True)
        if _wait_gone(name, 3.0):
            return {"killed": base, "note": "остановлена принудительно"}
        # …и в последнюю очередь SIGKILL по командной строке.
        subprocess.run(["pkill", "-KILL", "-f", base], capture_output=True)
        if not is_running(name):
            return {"killed": base, "note": "остановлена принудительно"}
        raise RuntimeError("pkill не смог завершить процесс")

    # Linux: SIGTERM, затем SIGKILL.
    subprocess.run(["pkill", "-x", base], capture_output=True)
    if _wait_gone(name):
        return {"killed": base, "note": "остановлена аккуратно"}
    subprocess.run(["pkill", "-KILL", "-x", base], capture_output=True)
    if not is_running(name):
        return {"killed": base, "note": "остановлена принудительно"}
    raise RuntimeError("pkill не смог завершить процесс")
