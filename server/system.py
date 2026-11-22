"""Системная информация: RAM и VRAM процессов LM Studio (app + движок
llama-server).

Windows (боевая):
    RAM  -> GlobalMemoryStatusEx() (kernel32, stdlib ctypes) — общая и
           свободная физическая память, без PowerShell.
    VRAM -> `nvidia-smi --query-compute-apps=pid,process_name,used_memory`
           — VRAM по процессам (NVIDIA); суммируем все строки, где имя
           процесса содержит одно из базовых имён (напр. «LM Studio»,
           «llama-server») — у LM Studio VRAM сидит в движке
           (llama-server), а не обязательно в самом приложении.

macOS/Linux (разработка/тесты):
    RAM  -> /proc/meminfo (Linux) или sysctl hw.memsize + vm_stat (macOS).
    VRAM -> None (nvidia-smi неприменим; в тестах monkeypatch'им _system).
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


def _base_name(process_name: str) -> str:
    """«LM Studio.exe» -> «LM Studio» (без расширения)."""
    p = (process_name or "").strip()
    if p.lower().endswith(".exe"):
        return p[:-4]
    return p


def process_vram_mb(process_names: str | list[str]) -> int | None:
    """VRAM, занятый процессами, в МБ (MiB) — через nvidia-smi.

    Запрос ``nvidia-smi --query-compute-apps=pid,process_name,used_memory
    --format=csv,noheader,nounits`` выдаёт по одному ряду на приложение,
    использующее GPU: PID, имя процесса, VRAM в MiB. Суммируем used_memory
    по всем рядам, где имя содержит одно из базовых имён (регистр не
    важен) — у LM Studio VRAM занят процессами приложения и его
    inference-движка (llama-server).

    Возврат:
        ``int`` — суммарно МБ (``0``, если процессы на GPU не сидят);
        ``None`` — nvidia-smi недоступен/не запустился (нет NVIDIA,
        драйверов или не Windows) либо имена не переданы — клиент просто
        не покажет VRAM.

    Результат кэшируется на _VRAM_TTL_S секунд (см. модуль).
    """
    global _vram_cache
    names = [process_names] if isinstance(process_names, str) else list(process_names or [])
    needles = [n for n in (_base_name(nm).lower() for nm in names) if n]
    if not needles:
        return None
    if _vram_cache is not None and time.monotonic() - _vram_cache[0] < _VRAM_TTL_S:
        return _vram_cache[1]
    if _system() != "Windows":
        return None  # dev/тесты на macOS/Linux
    try:
        out = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return None  # nvidia-smi нет/не запустился — не кэшируем
    if out.returncode != 0:
        return None
    if not (out.stdout or "").strip():
        value = 0  # GPU работает, но вычислительных приложений нет
        _vram_cache = (time.monotonic(), value)
        return value
    total = 0
    for line in out.stdout.splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        pname, mem = parts[1], parts[2]
        pl = pname.lower()
        if not any(nd in pl for nd in needles):
            continue
        try:
            total += int(mem)
        except ValueError:
            pass
    _vram_cache = (time.monotonic(), total)
    return total
