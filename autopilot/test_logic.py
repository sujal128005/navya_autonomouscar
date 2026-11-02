"""Offline checks for the obstacle detector and speed planner (no camera needed).

    python test_logic.py
Builds synthetic depth images of a floor (and optionally a box) as the D435i
would see them, using the camera height and tilt from config.py.
"""

import math
import sys

import numpy as np

import config
from obstacle import CorridorDetector, Intrinsics
from speed_planner import CLEAR, RESUMING, SLOWING, STOPPED, SpeedPlanner, apply_trim

SCALE = 0.001  # D435i default: 1 unit = 1 mm
INTR = Intrinsics(640, 480, 385.0, 385.0, 320.0, 240.0)


def render(box=None, wall_at=None) -> np.ndarray:
    """box = (forward_m, half_width_m, height_m) standing on the floor, centred ahead."""
    p = math.radians(config.CAMERA_PITCH_DEG)
    c, s = math.cos(p), math.sin(p)
    h = config.CAMERA_HEIGHT_M
    us = (np.arange(INTR.width) - INTR.ppx) / INTR.fx
    vs = (np.arange(INTR.height) - INTR.ppy) / INTR.fy
    xn, yn = np.meshgrid(us, vs)

    # Ray with camera z = 1: level-forward and down components.
    fwd1 = c - yn * s
    down1 = yn * c + s
    z = np.full(xn.shape, np.inf)
    floor = down1 > 1e-6
    z[floor] = h / down1[floor]

    planes = []
    if box:
        planes.append(box)
    if wall_at:
        planes.append((wall_at, 10.0, 3.0))
    for fwd, half_w, top in planes:
        zp = np.where(fwd1 > 1e-6, fwd / np.maximum(fwd1, 1e-6), np.inf)
        height = h - down1 * zp
        hit = (np.abs(xn * zp) < half_w) & (height >= 0) & (height <= top) & (zp < z)
        z[hit] = zp[hit]

    z[(z > 10.0) | ~np.isfinite(z)] = 0  # beyond range reads as no data
    return (z / SCALE).astype(np.uint16)


def test_floor_only_is_clear():
    m = CorridorDetector(INTR, SCALE).measure(render(wall_at=8.0))
    assert m.distance_m is None and not m.blind, m


def test_box_distance():
    for dist in (1.0, 2.0, 2.7):  # a 0.5 m box drops below MIN_OBSTACLE_POINTS beyond ~2.8 m
        m = CorridorDetector(INTR, SCALE).measure(render(box=(dist, 0.25, 0.5), wall_at=8.0))
        assert m.distance_m is not None and abs(m.distance_m - dist) < 0.05, (dist, m.distance_m)


def test_box_outside_corridor_ignored():
    det = CorridorDetector(INTR, SCALE)
    depth = render(wall_at=8.0)
    side = render(box=(2.0, 0.15, 0.5), wall_at=8.0)
    # shift the box image sideways so it sits ~1 m to the right of the car
    shift = int(1.0 / 2.0 * INTR.fx)
    depth[:, shift:] = np.where(side[:, :-shift] < depth[:, shift:], side[:, :-shift], depth[:, shift:])
    m = det.measure(depth)
    assert m.distance_m is None, m.distance_m


def test_blind_when_lens_covered():
    m = CorridorDetector(INTR, SCALE).measure(np.zeros((480, 640), dtype=np.uint16))
    assert m.blind and m.distance_m == 0.0


def test_planner_cycle():
    p = SpeedPlanner()
    t = 0.0
    # starts stopped; needs RESUME_DELAY_S of clear path before moving
    assert p.update(None, t) == (0, True) and p.state == RESUMING
    t += config.RESUME_DELAY_S + 0.01
    assert p.update(None, t) == (config.START_BOOST_SPEED, False) and p.state == CLEAR  # moving off: boost
    t += config.START_BOOST_S + 0.01
    assert p.update(None, t) == (config.CRUISE_SPEED, False)

    mid = (config.STOP_DIST_M + config.SLOW_DOWN_DIST_M) / 2
    speed, brake = p.update(mid, t)
    assert p.state == SLOWING and config.CREEP_SPEED < speed < config.CRUISE_SPEED and not brake

    assert p.update(config.STOP_DIST_M - 0.1, t) == (0, True) and p.state == STOPPED
    # obstacle removed: history still holds the near reading for DISTANCE_HISTORY frames
    for _ in range(config.DISTANCE_HISTORY):
        t += 0.03
        p.update(None, t)
    assert p.state == RESUMING
    t += config.RESUME_DELAY_S + 0.01
    assert p.update(None, t) == (config.START_BOOST_SPEED, False)  # boost again after every stop


def test_planner_obstacle_back_during_resume():
    p = SpeedPlanner()
    p.update(None, 0.0)
    p.update(config.RESUME_DIST_M - 0.1, 0.5)
    assert p.state == STOPPED


def render_strips(centres, half_width=0.1, heading_deg=0.0, floor=170, tile=25) -> np.ndarray:
    """Colour image of a light floor with black strips at lateral = c + tan(heading) * forward."""
    p = math.radians(config.CAMERA_PITCH_DEG)
    c, s = math.cos(p), math.sin(p)
    xn, yn = np.meshgrid((np.arange(INTR.width) - INTR.ppx) / INTR.fx, (np.arange(INTR.height) - INTR.ppy) / INTR.fy)
    down = yn * c + s
    img = np.full((INTR.height, INTR.width, 3), 110, np.uint8)  # walls above the horizon
    floor_px = down > 1e-6
    t = np.where(floor_px, config.CAMERA_HEIGHT_M / np.where(floor_px, down, 1), 0)
    forward, lateral = (c - yn * s) * t, xn * t + config.CAMERA_LATERAL_OFFSET_M
    img[floor_px] = floor
    slope = math.tan(math.radians(heading_deg))
    for centre in centres:
        img[floor_px & (np.abs(lateral - (centre + slope * forward)) < half_width)] = tile
    return img


def test_lane_between_two_strips():
    from lane import LaneFinder
    lv = LaneFinder(INTR).find(render_strips([-0.5, 0.7]))
    lane = lv.lane
    assert lane and lane.left and lane.right, lane
    assert abs(lane.offset_m - 0.1) < 0.04 and abs(lane.width_m - 1.2) < 0.06, lane
    assert abs(lane.heading_deg) < 1.5, lane


def test_lane_heading():
    from lane import LaneFinder
    lane = LaneFinder(INTR).find(render_strips([-0.6, 0.6], heading_deg=8.0)).lane
    assert lane and abs(lane.heading_deg - 8.0) < 1.5 and abs(lane.offset_m) < 0.05, lane


def test_lane_one_strip_uses_remembered_width():
    from lane import LaneFinder
    finder = LaneFinder(INTR)
    finder.find(render_strips([-0.6, 0.6]))
    lane = finder.find(render_strips([-0.6])).lane
    assert lane and lane.right is None and abs(lane.offset_m) < 0.05, lane


def test_no_strips_no_lane():
    from lane import LaneFinder
    assert LaneFinder(INTR).find(render_strips([])).lane is None


def corridor_points(left=-1.0, right=1.3, heading_deg=0.0, person=None):
    """Point arrays (forward, lateral, height, valid) for a corridor with two walls (+ optional person)."""
    rng = np.random.default_rng(1)
    slope = math.tan(math.radians(heading_deg))
    f = rng.uniform(0.3, 6.0, 20000)
    h = rng.uniform(-0.3, 2.0, 20000)   # below 0 = mirror images in a shiny floor
    lat = np.where(rng.random(20000) < 0.5, left, right) + slope * f + rng.normal(0, 0.02, 20000)
    if person:
        pf, pl = person
        f = np.concatenate([f, rng.uniform(pf, pf + 0.3, 2000)])
        lat = np.concatenate([lat, rng.uniform(pl - 0.2, pl + 0.2, 2000)])
        h = np.concatenate([h, rng.uniform(0, 1.7, 2000)])
    return f, lat, h, np.ones_like(f, dtype=bool)


def test_wall_lane():
    from lane import WallLaneFinder
    lane = WallLaneFinder().find(*corridor_points())
    assert lane and abs(lane.offset_m - 0.15) < 0.05 and abs(lane.width_m - 2.3) < 0.1, lane
    lane = WallLaneFinder().find(*corridor_points(heading_deg=-6))
    assert lane and abs(lane.heading_deg + 6) < 1.5, lane


def test_wall_lane_ignores_person_by_the_wall():
    from lane import WallLaneFinder
    lane = WallLaneFinder().find(*corridor_points(person=(2.0, 0.8)))
    assert lane and abs(lane.width_m - 2.3) < 0.1, lane


def test_object_distance_ignores_background():
    from vision import box_distance
    intr = Intrinsics(640, 480, 600, 600, 320, 240)
    depth = np.full((480, 640), 5000, np.uint16)       # wall at 5 m
    depth[150:400, 250:390] = 2000                     # person at 2 m...
    depth[300:400, 300:340] = 5000                     # ...with the wall showing between the legs
    distance, lateral = box_distance(depth, 0.001, (250, 150, 390, 400), intr)
    assert abs(distance - 2.0) < 0.01 and abs(lateral) < 0.01, (distance, lateral)
    assert box_distance(np.zeros((480, 640), np.uint16), 0.001, (250, 150, 390, 400), intr) == (None, None)


def test_vision_rules_people():
    from vision import Detection
    from vision_rules import VisionRules
    r = VisionRules()
    ahead = Detection("person", 0.9, (0, 0, 1, 1), distance_m=3.5, lateral_m=0.1)
    beside = Detection("person", 0.9, (0, 0, 1, 1), distance_m=2.0, lateral_m=1.5)
    res = r.evaluate([ahead, beside], 0.0)
    assert abs(res.distance_m - (3.5 - config.PERSON_EXTRA_MARGIN_M)) < 1e-6 and not res.hold, res
    assert r.evaluate([beside], 0.0).distance_m is None          # well to the side: not in the way
    no_depth = Detection("person", 0.9, (0, 0, 1, 1))
    assert r.evaluate([no_depth], 0.0).distance_m is None        # no distance: rely on depth check


def test_vision_rules_stop_sign():
    from vision import Detection
    from vision_rules import VisionRules
    r = VisionRules()
    sign = Detection("stop sign", 0.9, (0, 0, 1, 1), distance_m=config.STOP_SIGN_TRIGGER_M - 0.5, lateral_m=0.8)
    far = Detection("stop sign", 0.9, (0, 0, 1, 1), distance_m=config.STOP_SIGN_TRIGGER_M + 1.0, lateral_m=0.8)
    assert not r.evaluate([far], 0.0).hold                       # too far: keep going
    assert r.evaluate([sign], 1.0).hold                          # stop
    assert r.evaluate([], 1.0 + config.STOP_SIGN_WAIT_S - 0.1).hold   # still waiting, even if sign not seen
    t = 1.0 + config.STOP_SIGN_WAIT_S + 0.1
    assert not r.evaluate([sign], t).hold                        # waited: drive on past the sign
    assert not r.evaluate([sign], t + config.STOP_SIGN_IGNORE_S - 0.2).hold
    assert r.evaluate([sign], t + config.STOP_SIGN_IGNORE_S + 0.1).hold   # a later sign counts again


def make_lane(offset, heading_deg=0.0):
    from lane import Lane, Line
    centre = Line(offset, math.tan(math.radians(heading_deg)))
    return Lane(None, None, centre, 1.8, offset, heading_deg)


def test_lane_follow_direction_and_limits():
    from lane_follow import LaneFollower
    f = LaneFollower()
    assert f.wheel_angle_deg(make_lane(0.3)) > 0        # lane centre to the right -> steer right
    assert f.wheel_angle_deg(make_lane(-0.3)) < 0
    assert abs(f.wheel_angle_deg(make_lane(0.0))) < 1e-9
    assert f.wheel_angle_deg(make_lane(0.0, 10)) > 0    # lane bends right -> steer right
    # pure pursuit: atan(2 L y / d^2) with y at the lookahead point
    x = config.LOOKAHEAD_M + config.CAMERA_TO_REAR_AXLE_M
    expect = math.degrees(math.atan2(2 * config.WHEELBASE_M * 0.3, x * x + 0.09))
    assert abs(f.wheel_angle_deg(make_lane(0.3)) - expect) < 1e-9

    # Pure pursuit never asks for more than atan(L / d) (~17 deg here); with a small
    # full-lock angle the command must still clamp at 1000.
    saved = config.STEER_MAX_DEG
    config.STEER_MAX_DEG = 5.0
    try:
        t = 0.0
        f.update(make_lane(1.0), t)
        for _ in range(50):
            t += 0.05
            d = f.update(make_lane(1.0), t)
        assert d.steer == 1000 and d.speed_cap is None, d   # clamped at full lock
    finally:
        config.STEER_MAX_DEG = saved

    f.reset()
    f.update(make_lane(5.0), 0.0)
    d = f.update(make_lane(5.0), 0.1)                   # rate limit: 0.1 s of change only
    assert d.steer == int(config.STEER_RATE_PER_S * 0.1), d


def test_lane_follow_lost_lane():
    from lane_follow import LaneFollower
    f = LaneFollower()
    t = 0.0
    for _ in range(40):                                 # settle on a right-hand lane
        t += 0.05
        f.update(make_lane(0.4), t)
    held = f.update(None, t + 0.05)
    assert held.steer > 0 and held.speed_cap is None    # short gap: keep steering
    t += 0.05 + config.LANE_LOST_HOLD_S + 0.01
    for _ in range(40):
        t += 0.05
        d = f.update(None, t)
    assert d.steer == 0 and d.speed_cap == config.LANE_LOST_SPEED


def test_link_status_v1_and_v2():
    import navya_link

    class FakeSerial:
        def __init__(self, *a, **k):
            self.lines = [b"NAVYA READY", b" v2\n",       # a read that timed out mid-line
                          b"S,AUTO,1464,1848,1,86,86,0,1500,-300,-280,512,0,1,OK\n"]
            self.out = b""

        def readline(self):
            time.sleep(0.01)
            return self.lines.pop(0) if self.lines else b""

        def write(self, b):
            self.out += b

        def close(self):
            pass

    import time
    real = navya_link.serial.Serial
    navya_link.serial.Serial = FakeSerial
    try:
        link = navya_link.NavyaLink("COMX")
        assert link.wait_ready(1)
        time.sleep(0.1)
        s = link.status
        assert (s.mode, s.steer_target, s.steer_pos, s.pot_raw, s.limit_right, s.steer_state) == \
               ("AUTO", -300, -280, 512, True, "OK"), s
        link.drive(100, 100, False, -250)
        assert link._ser.out.endswith(b"D,100,100,0,-250\n")
        link._parse_status("S,MANUAL,1464,1000,0,0,0,1")          # v1 status still parsed
        assert link.status.mode == "MANUAL" and link.status.steer_state == "-"
        link.firmware = "v1"
        link.drive(100, 100, False, -250)
        assert link._ser.out.endswith(b"D,100,100,0\n")           # v1 gets 3 fields only
        link._stop.set()

        # The USB link can drop bytes: a banner without its version still ends as v2
        FakeSerial.__init__ = lambda self, *a, **k: setattr(self, "lines", [
            b"NAVYA READY \n", b"CFG,pwm_start=75,steering=1,cal_ok=0\n"]) or setattr(self, "out", b"")
        link = navya_link.NavyaLink("COMX")
        assert link.wait_ready(1)
        time.sleep(0.1)
        assert link.firmware == "v2", link.firmware
        link._stop.set()
    finally:
        navya_link.serial.Serial = real


def test_battery_guard():
    from battery import BatteryGuard, describe
    g = BatteryGuard()
    assert g.update(0, 0, True, 0) == ""                                 # monitor not wired
    assert g.update(24.5, 24.6, True, 0) == ""
    assert g.update(22.0, 24.6, True, 1) == "LOW"
    low = config.BATTERY_STOP_V - 0.3
    assert g.update(low, 24.6, True, 2) == "LOW"                         # brief dip under load
    assert g.update(24.0, 24.6, True, 2.5) == ""                         # recovered: dip forgotten
    g.update(low, 24.6, True, 3)
    assert g.update(low, 24.6, True, 3 + config.BATTERY_STOP_S) == "STOP"
    assert g.update(24.0, 24.6, False, 10) == "STOP"                     # stays stopped (latched)
    assert describe(25.2) == "25.2 V (100%)" and describe(0) == "-"



def test_battery_guard_ignores_unwired_pin():
    from battery import BatteryGuard, describe
    g = BatteryGuard()
    for t in range(10):                                  # a floating pin reading 8 V must not stop the car
        assert g.update(8.4, 0.0, True, float(t)) == "", t
    assert "check divider" in describe(8.4) and describe(0.0) == "-"
    assert g.update(8.4, 21.0, True, 20.0) == "LOW"      # the real battery still counts...
    assert g.update(8.4, 21.0, True, 24.0) == "STOP"     # ...and stops the car when low

def test_live_settings(tmp_dir=None):
    import tempfile
    from pathlib import Path
    import live_settings
    saved = {n: getattr(config, n) for n in ("STOP_DIST_M", "SLOW_DOWN_DIST_M", "RESUME_DIST_M",
                                             "DETECT_MAX_M", "CRUISE_SPEED", "TRIM")}
    try:
        live_settings.apply("CRUISE_SPEED", 999)
        assert config.CRUISE_SPEED == 400                                # clamped to the safe range
        live_settings.apply("TRIM", 0.0349)
        assert config.TRIM == 0.03                                       # snapped to the 0.01 step
        live_settings.apply("STOP_DIST_M", 3.6)                          # pushes the others out
        assert config.SLOW_DOWN_DIST_M >= 4.1 and config.RESUME_DIST_M >= 4.0
        assert config.DETECT_MAX_M >= config.SLOW_DOWN_DIST_M + 0.7 - 1e-9
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "config.py"
            copy.write_text(live_settings.CONFIG_FILE.read_text(encoding="utf-8"), encoding="utf-8")
            changed = live_settings.save(copy)
            text = copy.read_text(encoding="utf-8")
            assert any(c.startswith("CRUISE_SPEED") for c in changed)
            assert "CRUISE_SPEED = 400" in text and "STOP_DIST_M = 3.6" in text
            assert "# stop here" in text                                 # comments kept
    finally:
        for n, v in saved.items():
            setattr(config, n, v)


def test_phone_settings_and_ask_endpoints():
    import json
    import urllib.request
    import live_settings
    from phone_stream import PhoneStream
    p = PhoneStream("t", {}, port=8097, settings=live_settings.SETTINGS,
                    settings_values=live_settings.values, ask=True)
    try:
        base = "http://127.0.0.1:8097"
        page = urllib.request.urlopen(base + "/").read().decode()
        assert "Tune settings" in page and "Ask Navya" in page and "Save settings" in page
        meta = json.loads(urllib.request.urlopen(base + "/settings").read())
        assert meta["values"]["CRUISE_SPEED"] == config.CRUISE_SPEED and len(meta["meta"]) == len(live_settings.SETTINGS)
        urllib.request.urlopen(base + "/set?k=CRUISE_SPEED&v=150")
        urllib.request.urlopen(base + "/set?k=PWM_MAX&v=255")                 # not a phone setting: ignored
        urllib.request.urlopen(base + "/ask?q=any%20people%3F")
        urllib.request.urlopen(base + "/cmd?k=save")
        assert p.pop_settings() == [("CRUISE_SPEED", 150.0)]
        assert p.pop_questions() == ["any people?"] and p.pop_commands() == ["save"]
    finally:
        p.close()


def test_ask_navya_providers_and_fallback():
    """Gemini/Groq requests are built right, and a failing provider falls through to the next.
    No network: urlopen is replaced by a fake that records requests and plays back replies."""
    import io
    import json
    import os
    import urllib.error
    import ask_navya

    calls = []

    class Reply(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_urlopen(script):
        def opener(request, timeout=None):
            body = json.loads(request.data)
            calls.append((request.full_url, dict(request.header_items()), body))
            outcome = script.pop(0)
            if isinstance(outcome, int):
                raise urllib.error.HTTPError(request.full_url, outcome, "err", {}, None)
            return Reply(json.dumps(outcome).encode())
        return opener

    gemini_ok = {"candidates": [{"content": {"parts": [{"text": "A person 2 m ahead."}]}}]}
    groq_ok = {"choices": [{"message": {"content": "<think>hmm</think>Clear corridor, door on the left."}}]}
    saved_env = {k: os.environ.pop(k) for k in ("GEMINI_API_KEY", "GROQ_API_KEY") if k in os.environ}
    real_urlopen, real_file = ask_navya.urllib.request.urlopen, ask_navya.KEYS_FILE
    ask_navya.KEYS_FILE = ask_navya.Path("does-not-exist.env")
    try:
        a = ask_navya.AskNavya()
        assert "No AI key" in a.describe(b"jpg", "q", "")               # nothing configured

        os.environ["GEMINI_API_KEY"], os.environ["GROQ_API_KEY"] = "g-key", "q-key"
        ask_navya.urllib.request.urlopen = fake_urlopen([gemini_ok])
        answer = a.describe(b"jpg", "any people?", "nearest obstacle 2.1 m")
        assert answer.startswith("A person 2 m ahead.") and "[Gemini" in answer, answer
        url, headers, body = calls[-1]
        assert config.GEMINI_MODEL in url and "key=" not in url        # key in a header, not the URL
        assert headers.get("X-goog-api-key") == "g-key"
        parts = body["contents"][0]["parts"]
        assert parts[1]["inline_data"]["mime_type"] == "image/jpeg" and "any people?" in parts[0]["text"]

        ask_navya.urllib.request.urlopen = fake_urlopen([429, groq_ok])   # Gemini over its free limit
        answer = a.describe(b"jpg", "q", "")
        assert answer.startswith("Clear corridor, door on the left.") and "<think>" not in answer
        assert "[Groq" in answer and "Gemini: free limit reached" in answer, answer
        url, headers, body = calls[-1]
        assert url.endswith("/chat/completions") and headers.get("Authorization") == "Bearer q-key"
        assert body["model"] == config.GROQ_MODEL
        assert body["messages"][1]["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

        ask_navya.urllib.request.urlopen = fake_urlopen([500, 401])      # both fail
        answer = a.describe(b"jpg", "q", "")
        assert answer.startswith("No AI could answer") and "Groq: invalid key" in answer, answer
    finally:
        ask_navya.urllib.request.urlopen, ask_navya.KEYS_FILE = real_urlopen, real_file
        for k in ("GEMINI_API_KEY", "GROQ_API_KEY"):
            os.environ.pop(k, None)
        os.environ.update(saved_env)



def lidar_packet(start_deg, end_deg, dists_mm, intensity=200, speed_dps=3600):
    """One 47-byte LiDAR packet as the D500 sends it, CRC included."""
    import struct
    from lidar import crc8
    body = struct.pack("<BBHH", 0x54, 0x2C, speed_dps, round(start_deg * 100) % 36000)
    for d in dists_mm:
        body += struct.pack("<HB", d, intensity)
    body += struct.pack("<HH", round(end_deg * 100) % 36000, 1234)
    return body + bytes([crc8(body)])


def test_lidar_parser_builds_full_turns():
    from lidar import LidarParser
    turn = b"".join(lidar_packet(12 * k, 12 * k + 11, [1000 + k] * 12) for k in range(30))
    corrupt = bytearray(lidar_packet(5, 16, [500] * 12))
    corrupt[10] ^= 0xFF
    stream = b"\x00\x54junk" + turn[:47 * 4] + bytes(corrupt) + turn[47 * 4:] + lidar_packet(0, 11, [1500] * 12)
    parser, scans = LidarParser(), []
    for i in range(0, len(stream), 37):          # arrives in odd-sized chunks
        scans += parser.feed(stream[i:i + 37], now=1.0)
    assert parser.bad_packets >= 1 and parser.good_packets == 31, (parser.good_packets, parser.bad_packets)
    assert len(scans) == 1, len(scans)
    scan = scans[0]
    assert len(scan.angle_deg) == 360 and abs(scan.rpm - 600) < 1e-6
    assert abs(scan.angle_deg[13] - 13) < 1e-6 and abs(scan.distance_m[13] - 1.001) < 1e-9
    assert not np.any(np.isclose(scan.distance_m, 0.5))   # the corrupt packet's points are dropped

    # Reading that starts half-way round: the half turn is dropped, the next full turn kept
    parser = LidarParser()
    scans = parser.feed(turn[47 * 15:] + turn + lidar_packet(0, 11, [1500] * 12), now=1.0)
    assert len(scans) == 1 and len(scans[0].angle_deg) == 360, [len(s.angle_deg) for s in scans]


def test_lidar_corridor_and_sides():
    from lidar import Scan, corridor_distance, nearest_by_side
    angles = np.arange(0, 360, 0.5)
    dists = np.full(angles.shape, 6.0)                       # room walls 6 m away
    ahead = (angles < 8) | (angles > 352)
    dists[ahead] = 1.5                                       # box straight ahead
    dists[(angles > 88) & (angles < 92)] = 0.5               # post close on the right
    dists[(angles > 200) & (angles < 202)] = 0.05            # the car's own mast: ignored
    scan = Scan(angles, dists, np.full(angles.shape, 200), 600, 0.0)
    saved = (config.LIDAR_ANGLE_OFFSET_DEG, config.LIDAR_SETBACK_M, config.LIDAR_CLOCKWISE)
    try:
        config.LIDAR_ANGLE_OFFSET_DEG, config.LIDAR_SETBACK_M, config.LIDAR_CLOCKWISE = 0.0, 0.3, True
        d = corridor_distance(scan)
        assert d is not None and abs(d - 1.2) < 0.02, d      # 1.5 m minus the 0.3 m setback
        sides = nearest_by_side(scan)
        assert abs(sides["right"] - 0.5) < 1e-6 and sides["left"] == 6.0 and sides["back"] == 6.0, sides
        config.LIDAR_CLOCKWISE = False                       # mirrored: the post is now on the left
        assert abs(nearest_by_side(scan)["left"] - 0.5) < 1e-6
        config.LIDAR_ANGLE_OFFSET_DEG = 90.0                 # mounted turned: the post is ahead now
        config.LIDAR_CLOCKWISE = True
        assert abs(corridor_distance(scan) - 0.2) < 0.02
        dists[:] = 6.0
        dists[0] = 1.0                                       # a single stray point is not an obstacle
        config.LIDAR_ANGLE_OFFSET_DEG = 0.0
        assert corridor_distance(scan) is None
    finally:
        config.LIDAR_ANGLE_OFFSET_DEG, config.LIDAR_SETBACK_M, config.LIDAR_CLOCKWISE = saved


def test_arduino_port_ignores_lidar_adapter():
    import navya_link
    from types import SimpleNamespace as P
    real = navya_link.list_ports.comports
    try:
        navya_link.list_ports.comports = lambda: [P(device="COM7", vid=0x10C4, description="CP2102"),
                                                  P(device="COM6", vid=0x1A86, description="CH340")]
        assert navya_link.find_port() == "COM6"
    finally:
        navya_link.list_ports.comports = real

def test_trim():
    assert apply_trim(400, 0.0) == (400, 400)
    left, right = apply_trim(400, 0.05)
    assert right > left
    assert apply_trim(1000, 0.2) == (800, 1000)


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
