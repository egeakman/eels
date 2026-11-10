"""Find the Mac's LAN IPv4 addresses and label them (Ethernet, Wi-Fi, ...)."""

from __future__ import annotations

import re
import socket
import subprocess


def _hardware_ports() -> dict[str, str]:
    """Map device (en0) to hardware port name (Wi-Fi, USB 10/100/1000 LAN, Thunderbolt Ethernet...)."""
    try:
        out = subprocess.run(
            ["networksetup", "-listallhardwareports"], capture_output=True, text=True, timeout=5
        ).stdout
    except Exception:
        return {}
    ports = {}
    port = None
    for line in out.splitlines():
        if line.startswith("Hardware Port:"):
            port = line.split(":", 1)[1].strip()
        elif line.startswith("Device:") and port:
            ports[line.split(":", 1)[1].strip()] = port
    return ports


def lan_addresses() -> list[dict]:
    """Return [{'ip', 'iface', 'port', 'kind'}] for active non-loopback IPv4 interfaces."""
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        out = ""
    ports = _hardware_ports()
    result = []
    iface = None
    for line in out.splitlines():
        m = re.match(r"^([a-z0-9]+): flags=", line)
        if m:
            iface = m.group(1)
            continue
        m = re.match(r"^\s+inet (\d+\.\d+\.\d+\.\d+)", line)
        if m and iface:
            ip = m.group(1)
            if ip.startswith("127.") or ip.startswith("169.254."):
                continue
            port = ports.get(iface, iface)
            low = port.lower()
            if "wi-fi" in low or "airport" in low:
                kind = "Wi-Fi"
            elif "ethernet" in low or "lan" in low or "thunderbolt" in low:
                kind = "wired"
            elif iface.startswith("utun") or iface.startswith("bridge"):
                kind = "virtual"
            else:
                kind = "other"
            result.append({"ip": ip, "iface": iface, "port": port, "kind": kind})
    order = {"wired": 0, "Wi-Fi": 1, "other": 2, "virtual": 3}
    result.sort(key=lambda r: order.get(r["kind"], 9))
    return result


def can_connect(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False
