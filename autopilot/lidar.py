"""LDROBOT D500 LiDAR (STL-19P / LD19 sensor) on the laptop's USB.

The sensor spins about 10 turns a second and streams 47-byte packets of 12 points each
at 230400 baud; it needs no start command. LidarReader collects the packets into full
360-degree scans in a background thread.

Car coordinates, as in the rest of the autopilot: x forward, y right, metres, with the
LiDAR's centre at the origin. LIDAR_ANGLE_OFFSET_DEG in config.py says which sensor
angle points straight ahead (python lidar_view.py shows it).
"""

import struct
import threading
import time
from dataclasses import dataclass

import numpy as np
import serial
from serial.tools import list_ports

import config

HEADER, VER_LEN = 0x54, 0x2C        # every packet starts with these two bytes
PACKET_LEN = 47
POINTS_PER_PACKET = 12
GENUINE_ARDUINO_VIDS = {0x2341, 0x2A03}   # never a LiDAR: skipped when searching
CP210X_VID = 0x10C4                        # the D500 kit's USB adapter: searched first


def _crc_table() -> list[int]:
    """CRC-8, polynomial 0x4D, as in LDROBOT's protocol sheet."""
    table = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x4D) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
        table.append(crc)
    return table


CRC_TABLE = _crc_table()


def crc8(data: bytes) -> int:
    crc = 0
    for b in data:
        crc = CRC_TABLE[crc ^ b]
    return crc


@dataclass
class Scan:
    angle_deg: np.ndarray       # sensor angles 0..360, as the LiDAR reports them
    distance_m: np.ndarray      # 0 = no return
    intensity: np.ndarray       # 0..255
    rpm: float
    t: float                    # time.monotonic() when the turn completed

    def valid(self) -> np.ndarray:
        return ((self.distance_m > 0) & (self.distance_m >= config.LIDAR_IGNORE_WITHIN_M)
                & (self.intensity >= config.LIDAR_MIN_INTENSITY))

    def car_angles_deg(self) -> np.ndarray:
        """0 = straight ahead, positive = to the right."""
        a = self.angle_deg - config.LIDAR_ANGLE_OFFSET_DEG
        return (a if config.LIDAR_CLOCKWISE else -a) % 360

    def points_xy(self) -> tuple[np.ndarray, np.ndarray]:
        """x forward, y right of the valid returns."""
        ok = self.valid()
        a = np.radians(self.car_angles_deg()[ok])
        d = self.distance_m[ok]
        return d * np.cos(a), d * np.sin(a)


def corridor_distance(scan: Scan) -> float | None:
    """Nearest obstacle in the car's path, metres from the front bumper (None = clear).
    The same corridor as the depth camera uses, but only at the LiDAR's height."""
    x, y = scan.points_xy()
    ahead = x - config.LIDAR_SETBACK_M
    lateral = y + config.LIDAR_LATERAL_OFFSET_M
    inside = (np.abs(lateral) <= config.CORRIDOR_HALF_WIDTH_M) & (ahead > 0) & (ahead <= config.DETECT_MAX_M)
    hits = np.sort(ahead[inside])
    if len(hits) < config.LIDAR_MIN_POINTS:
        return None
    return float(hits[config.LIDAR_MIN_POINTS - 1])   # ignore the odd stray point


def nearest_by_side(scan: Scan) -> dict[str, float | None]:
    """Nearest return in each 90-degree sector around the LiDAR: front, right, back, left."""
    ok = scan.valid()
    a, d = scan.car_angles_deg()[ok], scan.distance_m[ok]
    sector = ((a + 45) % 360 // 90).astype(int)
    out = {}
    for n, side in enumerate(("front", "right", "back", "left")):
        ds = d[sector == n]
        out[side] = float(ds.min()) if len(ds) else None
    return out


class LidarParser:
    """Bytes in, full scans out. Skips junk and corrupt packets (CRC check)."""

    def __init__(self):
        self._buf = bytearray()
        self._angles: list[float] = []
        self._dists: list[float] = []
        self._intens: list[int] = []
        self._last_start: float | None = None
        self.rpm = 0.0
        self.good_packets = 0
        self.bad_packets = 0

    def feed(self, data: bytes, now: float | None = None) -> list[Scan]:
        self._buf += data
        scans = []
        while True:
            i = self._buf.find(bytes((HEADER, VER_LEN)))
            if i < 0:
                del self._buf[:-1]      # keep a last 0x54: it may start the next packet
                break
            del self._buf[:i]
            if len(self._buf) < PACKET_LEN:
                break
            packet = bytes(self._buf[:PACKET_LEN])
            if crc8(packet[:-1]) != packet[-1]:
                self.bad_packets += 1
                del self._buf[:1]       # not a real packet start; search on
                continue
            del self._buf[:PACKET_LEN]
            self.good_packets += 1
            scan = self._add(packet, time.monotonic() if now is None else now)
            if scan:
                scans.append(scan)
        return scans

    def _add(self, p: bytes, now: float) -> Scan | None:
        speed, start = struct.unpack_from("<HH", p, 2)
        end = struct.unpack_from("<H", p, 42)[0]
        start, end = start / 100, end / 100
        if end < start:
            end += 360
        step = (end - start) / (POINTS_PER_PACKET - 1)
        scan = None
        if self._last_start is not None and start < self._last_start and self._angles:
            # Start angle went back past 0: the turn is complete.
            scan = Scan(np.array(self._angles), np.array(self._dists), np.array(self._intens),
                        self.rpm, now)
            self._angles, self._dists, self._intens = [], [], []
        self._last_start = start
        self.rpm = speed / 6            # degrees per second -> turns per minute
        for k in range(POINTS_PER_PACKET):
            dist_mm, intensity = struct.unpack_from("<HB", p, 6 + 3 * k)
            self._angles.append((start + step * k) % 360)
            self._dists.append(dist_mm / 1000)
            self._intens.append(intensity)
        return scan


def looks_like_lidar(port: str, seconds: float = 0.6) -> bool:
    try:
        with serial.Serial(port, config.LIDAR_BAUD, timeout=0.1) as s:
            parser = LidarParser()
            end = time.monotonic() + seconds
            while time.monotonic() < end:
                parser.feed(s.read(256))
                if parser.good_packets >= 2:
                    return True
    except (serial.SerialException, OSError):
        pass        # busy (e.g. the Arduino, already open) or gone
    return False


def find_lidar_port(skip=()) -> str | None:
    """The serial port that streams LiDAR packets, or None. skip: ports already in use."""
    # USB ports only: opening a Bluetooth COM port can hang for many seconds.
    ports = [p for p in list_ports.comports()
             if p.vid is not None and p.vid not in GENUINE_ARDUINO_VIDS and p.device not in skip]
    ports.sort(key=lambda p: p.vid != CP210X_VID)
    for p in ports:
        if looks_like_lidar(p.device):
            return p.device
    return None


class LidarReader:
    """Reads the LiDAR in the background; latest() is the newest full scan."""

    def __init__(self, port: str | None = None, skip=()):
        self.port = port or config.LIDAR_PORT or find_lidar_port(skip)
        if not self.port:
            raise RuntimeError("LiDAR not found. Plug its USB adapter into the laptop, check the "
                               "sensor spins, or set LIDAR_PORT in config.py.")
        self._serial = serial.Serial(self.port, config.LIDAR_BAUD, timeout=0.1)
        self._parser = LidarParser()
        self._lock = threading.Lock()
        self._scan: Scan | None = None
        self.scans = 0
        self.error = ""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        while self._running:
            try:
                data = self._serial.read(self._serial.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                self.error = str(e)     # cable pulled: latest() goes stale, the autopilot stops
                return
            for scan in self._parser.feed(data):
                with self._lock:
                    self._scan = scan
                    self.scans += 1

    def latest(self) -> Scan | None:
        with self._lock:
            return self._scan

    @property
    def rpm(self) -> float:
        return self._parser.rpm

    def wait_first(self, timeout_s: float = 5.0) -> bool:
        end = time.monotonic() + timeout_s
        while time.monotonic() < end:
            if self.latest() is not None:
                return True
            time.sleep(0.05)
        return False

    def close(self):
        self._running = False
        self._thread.join(timeout=1)
        self._serial.close()
