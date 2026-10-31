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
    # Steering (firmware v2; stay at defaults with v1 firmware)
    ch1_us: int = 0
    steer_target: int = 0     # -1000 full left .. 1000 full right
    steer_pos: int = 0
    pot_raw: int = 0
    limit_left: bool = False
    limit_right: bool = False
    steer_state: str = "-"    # OK / OFF / NOCAL / POT / STALL / RAW / NONE
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
        self.firmware = ""
        self.config: dict[str, str] = {}
        self._ser = serial.Serial(self.port, baud, timeout=0.1)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def wait_ready(self, timeout_s: float = 5.0) -> bool:
        """Opening the port resets the Uno; wait for its banner."""
        return self._ready.wait(timeout_s)

    def drive(self, left: int, right: int, brake: bool, steer: int = 0):
        """steer: -1000 full left .. 0 straight .. 1000 full right."""
        if self.firmware == "v1":   # v1 firmware rejects a 4th field
            self._write(f"D,{int(left)},{int(right)},{1 if brake else 0}\n")
        else:
            self._write(f"D,{int(left)},{int(right)},{1 if brake else 0},{int(steer)}\n")

    def raw(self, pwm_left: int, pwm_right: int):
        self._write(f"R,{int(pwm_left)},{int(pwm_right)}\n")

    def steer_raw(self, pwm: int):
        """Steering motor PWM -255..255 (+ = RPWM). Calibration only; needs AUTO."""
        self._write(f"M,{int(pwm)}\n")

    def steer_store(self, which: str):
        """Store the current pot reading as 'L' (full left), 'C' (straight) or 'R' (full right)."""
        self._write(f"K,{which}\n")

    def steer_set_invert(self, invert: bool):
        self._write(f"K,I,{1 if invert else 0}\n")

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
                self.firmware = line[len("NAVYA READY"):].strip()
                self._ready.set()
            elif line.startswith("S,"):
                self._parse_status(line)
            elif line.startswith("CFG,"):
                self.config = dict(kv.split("=", 1) for kv in line[4:].split(",") if "=" in kv)

    def _parse_status(self, line: str):
        parts = line.split(",")
        if len(parts) not in (8, 15):   # v1 firmware: 8 fields; v2 adds steering
            return
        try:
            status = DriveStatus(
                mode=parts[1],
                ch2_us=int(parts[2]),
                ch5_us=int(parts[3]),
                host_ok=parts[4] == "1",
                pwm_left=int(parts[5]),
                pwm_right=int(parts[6]),
                brake=parts[7] == "1",
                received_at=time.monotonic(),
            )
            if len(parts) == 15:
                status.ch1_us = int(parts[8])
                status.steer_target = int(parts[9])
                status.steer_pos = int(parts[10])
                status.pot_raw = int(parts[11])
                status.limit_left = parts[12] == "1"
                status.limit_right = parts[13] == "1"
                status.steer_state = parts[14]
            self.status = status
            self._ready.set()
        except ValueError:
            pass
