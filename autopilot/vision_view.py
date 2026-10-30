"""Navya vision: live object detection with distances.

    python vision_view.py            # D435i: objects with distance (needs the RealSense)
    python vision_view.py --webcam   # laptop webcam: objects only, no distance
    python vision_view.py --phone    # also watch it from a phone (see README)

Keys: S save a snapshot to captures/, Q quit. This program never drives the car.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from phone_stream import PhoneStream
from vision import ObjectDetector, describe, draw

CAPTURE_DIR = Path(__file__).with_name("captures")


class RealSenseSource:
    def __init__(self):
        from corridor_view import start_camera   # colour + depth aligned to colour
        self.pipeline, self.align, self.intr, self.scale = start_camera()

    def read(self):
        try:
            frames = self.align.process(self.pipeline.wait_for_frames(2000))
        except RuntimeError:
            return None, None
        c, d = frames.get_color_frame(), frames.get_depth_frame()
        if not c or not d:
            return None, None
        return np.asanyarray(c.get_data()), np.asanyarray(d.get_data())

    def close(self):
        self.pipeline.stop()


class WebcamSource:
    intr, scale = None, None

    def __init__(self, index: int):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f"Webcam {index} not found")

    def read(self):
        ok, frame = self.cap.read()
        return (frame, None) if ok else (None, None)

    def close(self):
        self.cap.release()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--webcam", type=int, nargs="?", const=0, default=None,
                        help="use a webcam (index, default 0) instead of the D435i")
    parser.add_argument("--phone", action="store_true", help="also serve the view and object list to a phone")
    parser.add_argument("--phone-port", type=int, default=8080)
    args = parser.parse_args()

    print("Loading the YOLO model...")
    detector = ObjectDetector()
    source = WebcamSource(args.webcam) if args.webcam is not None else RealSenseSource()
    phone = None
    if args.phone:
        phone = PhoneStream("Navya vision", {"vision": "Objects"}, port=args.phone_port)
        phone.print_addresses()
    CAPTURE_DIR.mkdir(exist_ok=True)
    print("Running. S = snapshot, Q = quit.")

    fps, n, t0 = 0.0, 0, time.monotonic()
    try:
        while True:
            color, depth = source.read()
            if color is None:
                print("No picture from the camera.")
                continue
            detections = detector.detect(color, depth, source.scale, source.intr)

            n += 1
            if time.monotonic() - t0 >= 1.0:
                fps, n, t0 = n / (time.monotonic() - t0), 0, time.monotonic()
            vis = draw(color.copy(), detections)
            header = f"{len(detections)} objects   {fps:.0f} fps"
            cv2.putText(vis, header, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(vis, header, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow("Navya vision", vis)

            if phone:
                phone.publish("vision", vis)
                phone.set_status(mode="VIEW ONLY",
                                 nearest=describe(detections[0]) if detections else "nothing",
                                 objects=", ".join(describe(d) for d in detections[:6]) or "-",
                                 fps=f"{fps:.0f}")

            key = chr(cv2.waitKey(1) & 0xFF).lower()
            if key == "q":
                break
            if key == "s":
                path = CAPTURE_DIR / f"vision_{datetime.now():%Y%m%d_%H%M%S}.png"
                cv2.imwrite(str(path), vis)
                print("Saved", path)
    except KeyboardInterrupt:
        pass
    finally:
        source.close()
        cv2.destroyAllWindows()
        if phone:
            phone.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
