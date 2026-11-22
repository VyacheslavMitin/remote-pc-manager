r"""Системная информация: RAM и занятая память GPU (VRAM) под LM Studio.

Windows (боевая):
    RAM  -> GlobalMemoryStatusEx() (kernel32, stdlib ctypes) — общая и
           свободная физическая память, без PowerShell.
    VRAM -> PowerShell `Get-Counter '\GPU Process Memory(*)\Dedicated Usage'`
           — самый крупный процесс на GPU (загруженная модель), байты → МБ.
           nvidia-smi на целевом ПК процессы по памяти не отдаёт.

macOS/Linux (разработка/тесты):
    RAM  -> /proc/meminfo (Linux) или sysctl hw.memsize + vm_stat (macOS).
    VRAM -> None (Get-Counter неприменим; в тестах monkeypatch'им _system).
"""
from __future__ import annotations

import platform
import re
import subprocess
import time

# Кэш последнего чтения VRAM: (время monotonic, значение).
# Клиент опрашивает status раз в ~10 c, но ручной опрос может быть чаще,
# а nvidia-smi — это subprocess (~0.5 c): не больше одного запуска за TTL.
_VRAM_TTL_S = 5.0
_vram_cache: tuple[float, int | None] | None = None


def _system() -> str:
    return platform.system()


def memory_info() -> dict | None:
    """Общая/занятая физическая память: ``{"used_mb": int, "total_mb": int}``.

    Windows — GlobalMemoryStatusEx (занято = общая - свободная);
    Linux — /proc/meminfo (MemTotal, MemAvailable);
    macOS — sysctl hw.memsize + vm_stat (свободно = free + inactive +
    speculative страницы).

    ``None``, если прочитать не удалось — клиент просто не покажет RAM
    в заголовке (старое поведение).
    """
    total_b: int | None = None
    used_b: int | None = None
    try:
        system = _system()
        if system == "Windows":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = (
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                )

            st = MEMORYSTATUSEX()
            st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[reportAttributeAccessIssue]
            total_b = int(st.ullTotalPhys)
            used_b = total_b - int(st.ullAvailPhys)
        elif system == "Linux":
            kb: dict[str, int] = {}
            with open("/proc/meminfo", encoding="ascii") as fh:
                for line in fh:
                    m = re.match(r"(MemTotal|MemAvailable):\s+(\d+)\s*kB", line)
                    if m:
                        kb[m.group(1)] = int(m.group(2))
            if "MemTotal" not in kb:
                return None
            total_b = kb["MemTotal"] * 1024
            used_b = (kb["MemTotal"] - kb.get("MemAvailable", 0)) * 1024
        elif system == "Darwin":
            out = subprocess.run(
                ["sysctl", "-n", "hw.memsize"],
                capture_output=True, text=True, timeout=5,
            )
            total_b = int(out.stdout.strip())
            vm = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=5
            ).stdout
            pm = re.search(r"page size of (\d+) bytes", vm)
            page = int(pm.group(1)) if pm else 16384

            def _pages(key: str) -> int:
                m = re.search(rf"{re.escape(key)}:\s+(\d+)", vm)
                return int(m.group(1)) if m else 0

            avail_b = (_pages("Pages free") + _pages("Pages inactive")
                       + _pages("Pages speculative")) * page
            used_b = max(0, total_b - avail_b)
        else:
            return None
    except Exception:
        return None
    if total_b is None:
        return None
    return {
        "used_mb": max(0, used_b or 0) // (1024 * 1024),
        "total_mb": total_b // (1024 * 1024),
    }


def vram_debug(needles: str | list[str] | None = None) -> dict:
    """Отладка VRAM (команда ``vram_debug``): сырые выходы nvidia-smi.

    ``compute_apps`` — `--query-compute-apps` (PID, имя, MiB) по процессам
    на GPU; ``gpu`` — `--query-gpu=name,memory_total,memory_used` (вся
    занятая память GPU, для sanity-чека: если там ~16 ГБ, а в
    compute_apps пусто/имя не совпало — видна причина). ``rows`` —
    разобранные строки compute_apps с флагом ``match`` (совпало ли имя
    с одним из needles).
    """
    def _run(argv: list[str]) -> dict:
        try:
            p = subprocess.run(argv, capture_output=True, text=True, timeout=10)
            return {"rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr}
        except Exception as e:  # FileNotFoundError и пр.
            return {"error": str(e)}

    names = ([needles] if isinstance(needles, str) else list(needles or []))
    info = {
        "system": _system(),
        "compute_apps": _run([
            "nvidia-smi",
            "--query-compute-apps=pid,process_name,used_memory",
            "--format=csv,noheader,nounits",
        ]),
        "gpu": _run([
            "nvidia-smi",
            "--query-gpu=name,memory_total,memory_used",
            "--format=csv,noheader,nounits",
        ]),
    }
    if names:
        nds = [n.lower() for n in names if n]
        rows = []
        for line in (info["compute_apps"].get("stdout") or "").splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                rows.append({
                    "name": parts[1],
                    "mem_mb": parts[2],
                    "match": any(nd in parts[1].lower() for nd in nds),
                })
        info["rows"] = rows
    return info


def gpu_process_vram_mb() -> int | None:
    """VRAM самого большого процесса на GPU (загруженная модель), в МБ.

    PowerShell ``Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage'
    -MaxSamples 1 -SampleInterval 1`` выдаёт занятую выделенную память
    каждого процесса GPU (CookedValue, байты); берём **максимум** —
    при запущенной LM Studio с загруженной моделью это и есть модель.
    Байты переводим в МБ.

    Возврат:
        ``int`` — МБ самого крупного процесса (``0``, если процессов
        на GPU нет);
        ``None`` — PowerShell/Get-Counter недоступны (не Windows) —
        клиент просто не покажет VRAM.

    Результат кэшируется на _VRAM_TTL_S секунд (см. модуль).
    """
    global _vram_cache
    if _vram_cache is not None and time.monotonic() - _vram_cache[0] < _VRAM_TTL_S:
        return _vram_cache[1]
    if _system() != "Windows":
        return None  # dev/тесты на macOS/Linux
    ps = (
        "Get-Counter '\\GPU Process Memory(*)\\Dedicated Usage' "
        "-MaxSamples 1 -SampleInterval 1 -ErrorAction SilentlyContinue | "
        "ForEach-Object { $_.CounterSamples } | "
        "Sort-Object CookedValue -Descending | "
        "Select-Object -First 1 -ExpandProperty CookedValue"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return None  # PowerShell нет/не запустился — не кэшируем
    if out.returncode != 0:
        return None
    for line in (out.stdout or "").splitlines():
        value = line.strip()
        if not value:
            continue
        try:
            largest_mb = int(float(value)) // (1024 * 1024)
        except ValueError:
            continue
        _vram_cache = (time.monotonic(), largest_mb)
        return largest_mb
    # PowerShell запустился, но процессов на GPU нет (или счётчика нет)
    value = 0
    _vram_cache = (time.monotonic(), value)
    return value
