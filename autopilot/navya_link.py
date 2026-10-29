"""USB serial link to the Arduino Uno running firmware/navya_drive."""

import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

import config

ARDUINO_VIDS = {0x2341, 0x2A03, 0x1A86, 0x0403, 0x10C4}  # Arduino, CH340, FTDI, CP210x


@dataclass
class DriveStatus:
    mode: str = "UNKNOWN"     # NO_RC / MANUAL / AUTO
    ch2_us: int = 0
    ch5_us: int = 0
    host_ok: bool = False
    pwm_left: int = 0
    pwm_right: int = 0
    brake: bool = True
    received_at: float = 0.0


def find_port() -> str:
    ports = [p for p in list_ports.comports() if p.vid in ARDUINO_VIDS]
    if len(ports) == 1:
        return ports[0].device
    listing = ", ".join(f"{p.device} ({p.description})" for p in list_ports.comports()) or "none"
    raise RuntimeError(f"Could not pick the Arduino port automatically. Ports: {listing}. "
                       "Pass --port COMx or set SERIAL_PORT in config.py.")


class NavyaLink:
    def __init__(self, port: str | None = None, baud: int = config.SERIAL_BAUD):
        self.port = port or config.SERIAL_PORT or find_port()
        self.status = DriveStatus()
        self.last_line = ""
        self._ser = serial.Serial(self.port, baud, timeout=0.1)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def wait_ready(self, timeout_s: float = 5.0) -> bool:
        """Opening the port resets the Uno; wait for its banner."""
        return self._ready.wait(timeout_s)

    def drive(self, left: int, right: int, brake: bool):
        self._write(f"D,{int(left)},{int(right)},{1 if brake else 0}\n")

    def raw(self, pwm_left: int, pwm_right: int):
        self._write(f"R,{int(pwm_left)},{int(pwm_right)}\n")

    def stop(self):
        self.drive(0, 0, True)

    def status_age_s(self) -> float:
        return time.monotonic() - self.status.received_at if self.status.received_at else float("inf")

    def close(self):
        try:
            for _ in range(3):
                self.stop()
                time.sleep(0.02)
        finally:
            self._stop.set()
            self._reader.join(timeout=1.0)
            self._ser.close()

    def _write(self, line: str):
        self._ser.write(line.encode("ascii"))

    def _read_loop(self):
        while not self._stop.is_set():
            try:
                raw = self._ser.readline()
            except serial.SerialException:
                break
            if not raw:
                continue
            line = raw.decode("ascii", errors="replace").strip()
            self.last_line = line
            if line.startswith("NAVYA READY"):
                self._ready.set()
            elif line.startswith("S,"):
                self._parse_status(line)

    def _parse_status(self, line: str):
        parts = line.split(",")
        if len(parts) != 8:
            return
        try:
            self.status = DriveStatus(
                mode=parts[1],
                ch2_us=int(parts[2]),
                ch5_us=int(parts[3]),
                host_ok=parts[4] == "1",
                pwm_left=int(parts[5]),
                pwm_right=int(parts[6]),
                brake=parts[7] == "1",
                received_at=time.monotonic(),
            )
            self._ready.set()
        except ValueError:
            pass
