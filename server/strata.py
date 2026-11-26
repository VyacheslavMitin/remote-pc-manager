r"""Управление Strata (strata-main): проверка, запуск, остановка, здоровье.

Strata — локальный OpenAI-совместимый сервер моделей (как LM Studio, API
тот же: /v1/models и пр.). На целевом ПК запускается пакетником
START-HERE.bat; живое дерево процессов выглядит так:

    python.exe  ".venv\Scripts\python.exe" setup.py            (надзиратель)
    python.exe  ...\strata-main\serve\server.py --engine strata --port 8090

Имя процесса — обычный python.exe, поэтому НЕ годится проверка по имени
(tasklist/pgrep зацепил бы и сам RPCM-сервер, и Strata-надзирателя):
процесс ищем по СОДЕРЖИМОМУ командной строки (WMI Get-CimInstance).

Windows:
    check    -> WMI: CommandLine ~ 'serve\\server.py' + '--engine strata';
                быстрый путь — GET /health на настроенном порту (без ключа),
                WMI только если /health не ответил
    start    -> cmd /c <START-HERE.bat> (detached, cwd=каталог Strata)
    stop    -> taskkill /T /PID (дерево: надзиратель setup.py + server.py)
                -> ждём -> taskkill /F /T /PID
    health  -> GET http://127.0.0.1:<api_port>/health
               {"status":"ok","max_context":131072,"model":"...","loaded":true,
                "service":"strata"} — модель/контекст/загруженность без
                API-ключа (/v1/models у Strata требует ключ — не трогаем)

macOS/Linux (для разработки/тестов):
    check    -> pgrep -f 'serve/server.py.*--engine strata'
    start    -> Popen([exe]) если exe задан
    stop     -> pkill по паттерну (SIGTERM -> SIGKILL)
    health   -> тот же GET /health

Остановка всегда «мягкая» сначала, принудительное убийство — fallback.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import time
import urllib.request

# Таймаут зонда /health в контексте status — как у LM Studio API: суммарное
# время status должно укладываться в 8-секундный таймаут клиента
# (client/server_api.py). Закрытый порт отвечает мгновенно (connection
# refused), слушающий, но загружающийся — не больше API_TIMEOUT_S.
API_TIMEOUT_S = 1.0

# Сколько секунд давать Strata на аккуратное завершение.
GRACEFUL_TIMEOUT_S = 8.0

# Пакетник запуска по умолчанию (боевая установка на целевом ПК).
DEFAULT_LAUNCH_BAT = r"C:\AI\Strata\strata-main\START-HERE.bat"

# Признаки процесса Strata в командной строке (оба обязательны): движок
# serve/server.py и флаг --engine strata. Это отличает Strata от любого
# другого python.exe (в т.ч. самого RPCM-сервера).
_MATCH_SERVER = r"serve[\\/]+server\.py"
_MATCH_ENGINE = r"--engine\s+strata"


def _system() -> str:
    return platform.system()


# ---------- поиск процессов ----------

_PS_FIND = r"""
$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.CommandLine -match 'serve\\server\.py' -and $_.CommandLine -match '--engine\s+strata'
}
$ids = @()
foreach ($p in $procs) {
    $parent = Get-CimInstance Win32_Process -Filter "ProcessId=$($p.ParentProcessId)" -ErrorAction SilentlyContinue
    if ($parent -and $parent.CommandLine -match 'setup\.py') { $ids += $parent.ProcessId } else { $ids += $p.ProcessId }
}
$ids | Select-Object -Unique
"""


def find_pids() -> list[int]:
    """PID процессов Strata (для остановки — надзиратель setup.py, если он
    родитель server.py, чтобы taskkill /T снял всё дерево).

    Windows — WMI Get-CimInstance по содержимому CommandLine; unix — pgrep -f.
    Пустой список — процессов Strata нет."""
    if _system() == "Windows":
        try:
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_FIND],
                capture_output=True, text=True, timeout=10,
            ).stdout
        except Exception:
            return []
        pids = [int(x) for x in re.findall(r"^\s*(\d+)\s*$", out, re.M)]
        return sorted(set(pids))
    try:
        res = subprocess.run(
            ["pgrep", "-f", r"serve/server\.py.*--engine strata"],
            capture_output=True, text=True,
        )
        return sorted({int(x) for x in res.stdout.split() if x.strip().isdigit()})
    except FileNotFoundError:
        return []


def is_running(api_port: int | None = None) -> bool:
    """Запущена ли Strata.

    Быстрый путь — GET /health на api_port (живой сервер отвечает за
    миллисекунды, WMI-запрос ~1-2 с не нужен). Если /health не ответил
    (порт в конфиге не совпал с фактическим, сервер загружается) —
    проверяем наличие процесса по командной строке."""
    if api_port is not None and health(api_port) is not None:
        return True
    return bool(find_pids())


# ---------- здоровье / модель ----------

def health(api_port: int) -> dict | None:
    """GET http://127.0.0.1:<port>/health — словарь вида
    {"status": "ok", "max_context": 128000-подобный int, "model": "id",
     "loaded": bool, "service": "strata"} или None (порт закрыт, отвечает
    не Strata, таймаут, мусор в ответе).

    /health у Strata открыт (без API-ключа) — в отличие от /v1/models.
    Требуем service == "strata": на чужом порту случайный сервис с /health
    не должен выглядеть как Strata."""
    try:
        port = int(api_port)
    except (TypeError, ValueError):
        return None
    url = f"http://127.0.0.1:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=API_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
    except Exception:
        return None
    if not isinstance(body, dict) or body.get("service") != "strata":
        return None
    return body


# ---------- версия ----------

def version(exe: str = "") -> str | None:
    """Версия движка Strata из engine/BUILD.json.

    Манифест лежит рядом с пакетником запуска:
    <каталог(START-HERE.bat)>/engine/BUILD.json — {"version": "0.1.41",
    "source": "release", ...} (тот же источник, что читает сам сервер
    Strata для Monitor-вкладки). Читается и при остановленной Strata.
    None — BUILD.json нет (движок, собранный из исходников) или битый JSON."""
    exe = (exe or "").strip() or DEFAULT_LAUNCH_BAT
    path = os.path.join(os.path.dirname(os.path.abspath(exe)), "engine", "BUILD.json")
    try:
        with open(path, encoding="utf-8") as f:
            v = json.load(f).get("version")
    except (OSError, ValueError):
        return None
    return str(v) if v else None


# ---------- запуск / остановка ----------

def start(exe: str = "") -> dict:
    """Запустить Strata пакетником START-HERE.bat (первый запуск ставит всё
    нужное, дальше просто поднимает модель). exe — путь из конфига
    (strata.exe); пусто — DEFAULT_LAUNCH_BAT.

    detached: свой process group, не умрёт вместе с RPCM-сервером."""
    exe = (exe or "").strip() or DEFAULT_LAUNCH_BAT
    if not os.path.exists(exe):
        raise FileNotFoundError(f"пакетник Strata не найден: {exe}")
    cwd = os.path.dirname(os.path.abspath(exe))

    if _system() == "Windows":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        DETACHED_PROCESS = 0x00000008
        proc = subprocess.Popen(
            ["cmd", "/c", exe],
            cwd=cwd,
            creationflags=CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS,
            close_fds=True,
        )
        return {"pid": proc.pid, "bat": exe}

    proc = subprocess.Popen(
        [exe],
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return {"pid": proc.pid, "bat": exe}


def _gone(pids: list[int]) -> bool:
    """Исчезли ли все PID из списка (повторный WMI/pgrep-запрос)."""
    alive = set(find_pids())
    return not (set(pids) & alive)


def _wait_gone(pids: list[int], timeout_s: float = GRACEFUL_TIMEOUT_S) -> bool:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _gone(pids):
            return True
        time.sleep(1.0)
    return _gone(pids)


def stop() -> dict:
    """Остановить Strata аккуратно (taskkill /T без /F), затем принудительно.

    Древо (надзиратель setup.py + serve/server.py) снимается целиком:
    /T убивает детей выбранного PID, а find_pids возвращает сам
    надзиратель, если он родитель server.py — иначе его не поднимет
    повторный опрос, но и не оставит сироту, перезапускающего движок.
    """
    pids = find_pids()
    if not pids:
        return {"killed": None, "note": "процесс не был запущен"}

    if _system() == "Windows":
        for pid in pids:
            subprocess.run(["taskkill", "/T", "/PID", str(pid)],
                           capture_output=True, text=True)
        if _wait_gone(pids):
            return {"killed": pids, "note": "остановлена аккуратно"}
        for pid in pids:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                           capture_output=True, text=True)
        if _gone(pids):
            return {"killed": pids, "note": "остановлена принудительно"}
        raise RuntimeError(f"taskkill не смог завершить процессы {pids}")

    for pid in pids:
        subprocess.run(["kill", str(pid)], capture_output=True)
    if _wait_gone(pids):
        return {"killed": pids, "note": "остановлена аккуратно"}
    for pid in pids:
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)
    if _gone(pids):
        return {"killed": pids, "note": "остановлена принудительно"}
    raise RuntimeError(f"kill не смог завершить процессы {pids}")
