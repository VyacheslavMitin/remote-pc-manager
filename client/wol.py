"""Wake-on-LAN: сборка и отправка magic packet (UDP broadcast).

Без внешних зависимостей — только socket.
"""
from __future__ import annotations

import re
import socket


def normalize_mac(mac: str) -> str:
    """Приводит MAC к форме AA:BB:CC:DD:EE:FF, иначе бросает ValueError.

    Допустимые входные формы: aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff,
    aabb.ccdd.eeff, AABBCCDDEEFF, « aa bb cc dd ee ff ».
    """
    hexs = re.sub(r"[^0-9a-fA-F]", "", (mac or ""))
    if len(hexs) != 12:
        raise ValueError(
            f"некорректный MAC: {mac!r} (нужно 6 пар hex, например AA:BB:CC:DD:EE:FF)"
        )
    pairs = [hexs[i:i + 2] for i in range(0, 12, 2)]
    return ":".join(p.upper() for p in pairs)


def magic_packet(mac: str) -> bytes:
    """6 байт 0xFF + MAC, повторённый 16 раз (102 байта)."""
    m = normalize_mac(mac)
    raw = bytes(int(x, 16) for x in m.split(":"))
    return b"\xff" * 6 + raw * 16


def send_wol(mac: str, broadcast: str = "255.255.255.255", port: int = 9,
             count: int = 3) -> dict:
    """Отправляет magic packet в broadcast-адрес (несколько раз для надёжности)."""
    packet = magic_packet(mac)  # может бросить ValueError на плохой MAC
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    try:
        for _ in range(max(1, int(count))):
            sock.sendto(packet, (broadcast, int(port)))
    finally:
        sock.close()
    return {"sent": max(1, int(count)), "to": f"{broadcast}:{port}", "mac": normalize_mac(mac)}
