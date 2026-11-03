"""USB serial link to the Arduino Uno running firmware/navya_drive."""

import threading
import time
from dataclasses import dataclass

import serial
from serial.tools import list_ports

import config

# Arduino, CH340, FTDI. Not CP210x (0x10C4): that is the LiDAR's USB adapter on this car.
ARDUINO_VIDS = {0x2341, 0x2A03, 0x1A86, 0x0403}


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
    battery_left_v: float = 0.0   # 0 = no battery divider connected
    battery_right_v: float = 0.0
    received_at: float = 0.0


def find_port() -> str:
    ports = [p for p in list_ports.comports()
             if p.vid in ARDUINO_VIDS and p.device != config.LIDAR_PORT]
    if len(ports) == 1:
        return ports[0].device
    listing = ", ".join(f"{p.device} ({p.description})" for p in list_ports.comports()) or "none"
    hint = ("" if ports else " On a Jetson: is the CH340 driver installed (bash jetson/build_ch341.sh)?")
    raise RuntimeError(f"Could not pick the Arduino port automatically. Ports: {listing}. "
                       "Pass --port (COM5 / /dev/ttyUSB0) or set SERIAL_PORT in config.py." + hint)


class NavyaLink:
    def __init__(self, port: str | None = None, baud: int = config.SERIAL_BAUD):
        self.port = port or config.SERIAL_PORT or find_port()
        self.status = DriveStatus()
        self.last_line = ""
        self.firmware = ""
        self.config: dict[str, str] = {}
        self.bad_lines = 0      # damaged status lines dropped (bytes lost on the USB link)
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
        # Read whatever has arrived and split it into lines here. (readline() reads one byte
        # per call; with the ch341 driver on the Jetson that returned the same data over and
        # over.) A line that arrives in two reads is kept together.
        pending = b""
        while not self._stop.is_set():
            try:
                chunk = self._ser.read(self._ser.in_waiting or 1)
            except serial.SerialException:
                break
            if not chunk:
                continue
            *lines, pending = (pending + chunk).split(b"\n")
            if len(pending) > 512:
                pending = b""
            for raw in lines:
                self._handle_line(raw.decode("ascii", errors="replace").strip())

    def _handle_line(self, line: str):
        if not line:
            return
        self.last_line = line
        if line.startswith("NAVYA READY"):
            self.firmware = line[len("NAVYA READY"):].strip()
            self._ready.set()
        elif line.startswith("S,"):
            self._parse_status(line)
        elif line.startswith("CFG,"):
            self.config = dict(kv.split("=", 1) for kv in line[4:].split(",") if "=" in kv)
            if "steering" in self.config:
                self.firmware = "v2"    # only v2 reports steering; covers a garbled banner

    def _parse_status(self, line: str):
        parts = line.split(",")
        if len(parts) not in (8, 15, 17):   # v1: 8 fields; v2 adds steering, then batteries
            self.bad_lines += 1
            return
        # The USB link occasionally drops a byte ("AUO"); one bad line must not change the mode
        if parts[1] not in ("NO_RC", "MANUAL", "AUTO") or parts[4] not in ("0", "1") \
                or parts[7] not in ("0", "1"):
            self.bad_lines += 1
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
            if len(parts) == 17:
                status.battery_left_v = int(parts[15]) / 1000
                status.battery_right_v = int(parts[16]) / 1000
            if len(parts) >= 15:
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
            self.bad_lines += 1
