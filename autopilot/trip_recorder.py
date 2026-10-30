"""Record a drive: camera + depth videos and a telemetry table, into one folder per trip.

Trips go to the SD card when one is inserted (the removable drive with the most free
space), else to autopilot/recordings. RECORD_DIR in config.py can name a folder instead.
Recording stops by itself before the disk gets full; the car keeps driving.
"""

import csv
import ctypes
import os
import shutil
import string
import time
from datetime import datetime
from pathlib import Path

import cv2

import config

FIELDS = ["t", "mode", "state", "obstacle_m", "speed_left", "speed_right", "brake",
          "pwm_left", "pwm_right", "ch2_us", "ch5_us", "vision", "objects", "fps"]
LOCAL_DIR = Path(__file__).with_name("recordings")


def removable_drives() -> list[Path]:
    """Removable drives (SD cards, USB sticks) on Windows; empty elsewhere."""
    if os.name != "nt":
        return []
    drives = []
    for letter in string.ascii_uppercase:
        root = f"{letter}:\\"
        if ctypes.windll.kernel32.GetDriveTypeW(root) == 2 and os.path.exists(root):  # 2 = DRIVE_REMOVABLE
            drives.append(Path(root))
    return drives


def storage_root() -> Path:
    if config.RECORD_DIR != "auto":
        return Path(config.RECORD_DIR)
    drives = removable_drives()
    if drives:
        best = max(drives, key=lambda d: shutil.disk_usage(d).free)
        return best / "navya_trips"
    return LOCAL_DIR


class TripRecorder:
    def __init__(self, root: Path | None = None):
        self.root = root or storage_root()
        self.dir = self.root / datetime.now().strftime("trip_%Y%m%d_%H%M%S")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.active = True
        self._t0 = time.monotonic()
        self._writers: dict[str, cv2.VideoWriter] = {}
        self._next_frame_at: dict[str, float] = {}
        self._next_log_at = 0.0
        self._next_disk_check = 0.0
        self._csv_file = open(self.dir / "telemetry.csv", "w", newline="", encoding="utf-8")
        self._csv = csv.DictWriter(self._csv_file, fieldnames=FIELDS, extrasaction="ignore")
        self._csv.writeheader()
        free = shutil.disk_usage(self.dir).free / 1e9
        print(f"Recording trip to {self.dir} ({free:.0f} GB free)")

    @property
    def raw_path(self) -> Path:
        return self.dir / "raw.bag"

    def frame(self, name: str, image):
        """Add a picture to <name>.mp4. Pictures are written at a steady RECORD_FPS
        (repeated or skipped as needed) so the video plays back in real time."""
        if not self.active:
            return
        now = time.monotonic()
        writer = self._writers.get(name)
        if writer is None:
            h, w = image.shape[:2]
            writer = cv2.VideoWriter(str(self.dir / f"{name}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                     config.RECORD_FPS, (w, h))
            self._writers[name] = writer
            self._next_frame_at[name] = now
        step = 1.0 / config.RECORD_FPS
        if now - self._next_frame_at[name] > 1.0:      # long gap (e.g. camera hiccup): don't pad a whole second
            self._next_frame_at[name] = now
        while self._next_frame_at[name] <= now:
            writer.write(image)
            self._next_frame_at[name] += step

    def log(self, **fields):
        """One telemetry row, at most RECORD_LOG_HZ per second."""
        if not self.active:
            return
        now = time.monotonic()
        if now < self._next_log_at:
            return
        self._next_log_at = now + 1.0 / config.RECORD_LOG_HZ
        self._csv.writerow(dict(fields, t=f"{now - self._t0:.2f}"))
        if now >= self._next_disk_check:
            self._next_disk_check = now + 5.0
            self._csv_file.flush()
            if shutil.disk_usage(self.dir).free / 1e9 < config.RECORD_MIN_FREE_GB:
                print(f"Recording stopped: less than {config.RECORD_MIN_FREE_GB} GB free on {self.root}.")
                self.close()

    def close(self):
        if not self.active:
            return
        self.active = False
        for writer in self._writers.values():
            writer.release()
        self._csv_file.close()
        print(f"Trip saved: {self.dir}")
