"""Find the Jetson on the laptop's current Wi-Fi and point the laptop's "ssh jetson" at it.

    python jetson/find_jetson.py        (Navya Jetson.bat runs this for you)

The Jetson's address changes with the network (phone hotspot, the laptop's Mobile hotspot).
This first tries the last known address, then scans the laptop's networks for SSH and
keeps the one that answers as the Jetson with the laptop's key. Prints JETSON_IP=<address>.
Progress goes to stderr, so a batch file can read the result line on its own.

One-time setup (already done on Sujal's laptop): the key ~/.ssh/navya_jetson and a
"Host jetson" block in ~/.ssh/config - see the README, section "Jetson".
"""

import ipaddress
import re
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

JETSON_USER = "nexara9"
JETSON_HOSTNAME = "nexara9"         # what `hostname` prints on the Jetson
SSH_DIR = Path.home() / ".ssh"
KEY = SSH_DIR / "navya_jetson"
CONFIG = SSH_DIR / "config"


def say(text: str):
    print(text, file=sys.stderr, flush=True)


def is_jetson(ip: str) -> bool:
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=4", "-o", "StrictHostKeyChecking=accept-new",
             "-i", str(KEY), f"{JETSON_USER}@{ip}", "hostname"],
            capture_output=True, text=True, timeout=10)
        return out.stdout.strip() == JETSON_HOSTNAME
    except (OSError, subprocess.TimeoutExpired):
        return False


def known_ip() -> str | None:
    m = re.search(r"^Host jetson\s*\n(?:[ \t]+.*\n)*?[ \t]+HostName\s+(\S+)", CONFIG.read_text(), re.M)
    return m.group(1) if m else None


def remember(ip: str):
    text = CONFIG.read_text()
    new = re.sub(r"(^Host jetson\s*\n(?:[ \t]+.*\n)*?[ \t]+HostName\s+)\S+", rf"\g<1>{ip}", text, flags=re.M)
    if new != text:
        CONFIG.write_text(new)


def local_networks() -> list[ipaddress.IPv4Network]:
    nets = set()
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        ip = ipaddress.ip_address(info[4][0])
        # skip loopback, link-local, and Hyper-V/WSL's virtual network
        if ip.is_loopback or ip.is_link_local or str(ip).startswith("172.20."):
            continue
        nets.add(ipaddress.ip_network(f"{ip}/24", strict=False))
    return sorted(nets)


def ssh_open(ip: str) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((ip, 22)) == 0


def main() -> int:
    if not KEY.exists() or not CONFIG.exists() or known_ip() is None:
        say("The laptop's Jetson key or 'Host jetson' entry is missing - see the README, section Jetson.")
        return 1
    last = known_ip()
    say(f"Trying the last address {last} ...")
    if is_jetson(last):
        print(f"JETSON_IP={last}")
        return 0
    for net in local_networks():
        say(f"Searching {net} ...")
        hosts = [str(h) for h in net.hosts()]
        with ThreadPoolExecutor(max_workers=64) as pool:
            candidates = [ip for ip, ok in zip(hosts, pool.map(ssh_open, hosts)) if ok]
        for ip in candidates:
            if is_jetson(ip):
                remember(ip)
                say(f"Found the Jetson at {ip} (saved for next time).")
                print(f"JETSON_IP={ip}")
                return 0
    say("Jetson not found. Is it switched on, and on the same Wi-Fi as this laptop "
        "(a phone hotspot or the laptop's Mobile hotspot - not college Wi-Fi)?")
    return 1


if __name__ == "__main__":
    sys.exit(main())
