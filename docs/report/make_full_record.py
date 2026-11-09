"""Build docs/Navya_complete_record.pdf: everything done on Navya so far, in one PDF.

    python docs/report/make_full_record.py            # writes docs/Navya_complete_record.pdf
    python docs/report/make_full_record.py --png DIR  # also one PNG per page, for checking

The text below is the project's story up to 9 November 2026. The appendices are read
from the repository when the PDF is built, so they always match the code on disk.
"""

import argparse
import html
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch
import pymupdf

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
DOCS = REPO / "docs"
OUT = DOCS / "Navya_complete_record.pdf"
BUILD = HERE / "build"
FONTS = Path("C:/Windows/Fonts")
SCRATCH_PULSE = HERE / "pulse1.py"

# ---------------------------------------------------------------- diagrams

RED, BLACK, BLUE, BROWN, PURPLE = "#d32f2f", "#424242", "#1565c0", "#8d4b1f", "#6a5acd"


def box(ax, x, y, w, h, fc, ec, lw=1.2, r=0.08):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw))


def T(**kw):
    return {"ha": "center", "va": "center", "fontsize": 11, **kw}


def relay_diagram(path):
    """Relay H-bridge wiring, as built on 9 Nov."""
    fig, ax = plt.subplots(figsize=(11, 7.4), dpi=170)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 7.4)
    ax.axis("off")
    # +12 V rail
    ax.plot([1.0, 1.0, 1.6], [4.6, 6.6, 6.6], color=RED, lw=4)
    ax.plot([2.6, 8.9, 8.9], [6.6, 6.6, 6.05], color=RED, lw=4)
    ax.plot([3.6, 3.6], [6.6, 6.05], color=RED, lw=4)
    ax.add_patch(Circle((3.6, 6.6), 0.07, color=RED))
    box(ax, 1.6, 6.4, 1.0, 0.4, "#ffe082", "#b28704")
    ax.text(2.1, 6.6, "10 A fuse", **T(fontsize=9.5))
    ax.text(6.3, 6.85, "+12 V (red wire) -> NO of BOTH relays",
            **T(color=RED, fontsize=11.5, fontweight="bold"))
    # battery - rail
    ax.plot([1.0, 1.0, 8.9, 8.9], [2.6, 1.45, 1.45, 2.0], color=BLACK, lw=4)
    ax.plot([3.6, 3.6], [1.45, 2.0], color=BLACK, lw=4)
    ax.add_patch(Circle((3.6, 1.45), 0.07, color=BLACK))
    ax.text(6.3, 1.15, "Battery - (black wire) -> NC of BOTH relays",
            **T(color=BLACK, fontsize=11.5, fontweight="bold"))
    # battery
    box(ax, 0.3, 2.6, 1.4, 2.0, "#eeeeee", "#616161")
    ax.text(1.0, 4.35, "+", **T(fontsize=18, color=RED, fontweight="bold"))
    ax.text(1.0, 3.75, "Grey toy\nbattery", **T())
    ax.text(1.0, 3.15, "12 V 8 Ah", **T(fontsize=9.5))
    ax.text(1.0, 2.8, "-", **T(fontsize=20, fontweight="bold"))
    # relays
    for x0, name, inp, com_side in ((2.85, "Relay 1", "IN1 <- D5", "right"),
                                    (8.15, "Relay 2", "IN2 <- D6", "left")):
        box(ax, x0, 2.0, 1.5, 4.05, "#ede7f6", "#5e35b1", lw=1.5)
        cx = x0 + 0.75
        ax.text(cx, 5.75, "NO", **T(fontweight="bold"))
        ax.text(cx, 4.8, name, **T(fontsize=13, fontweight="bold", color="#311b92"))
        ax.text(cx, 3.35, inp, **T(fontsize=10, color="#311b92"))
        ax.text(cx, 2.3, "NC", **T(fontweight="bold"))
        ax.text(x0 + 1.32 if com_side == "right" else x0 + 0.18, 4.05, "COM",
                ha="right" if com_side == "right" else "left", va="center", fontsize=11,
                fontweight="bold")
    # motor
    ax.add_patch(Circle((6.25, 4.05), 0.62, fc="#e0f2f1", ec="#00695c", lw=1.5))
    ax.text(6.25, 4.05, "Steering\nmotor", **T(fontsize=10))
    ax.plot([4.35, 5.63], [4.05, 4.05], color=BLUE, lw=4)
    ax.plot([6.87, 8.15], [4.05, 4.05], color=BROWN, lw=4)
    ax.text(5.0, 4.35, "dark blue", **T(color=BLUE, fontsize=10.5, fontweight="bold"))
    ax.text(7.5, 4.35, "brown", **T(color=BROWN, fontsize=10.5, fontweight="bold"))
    # control side
    box(ax, 9.75, 2.0, 1.15, 4.05, "#e3f2fd", "#1565c0")
    ax.text(10.33, 5.7, "Relay\nmodule\npins", **T(fontsize=10, fontweight="bold"))
    rows = [("DC+ -> 5V", RED), ("DC- -> GND", BLACK), ("IN1 -> D5", PURPLE),
            ("IN2 -> D6", PURPLE), ("Jumpers:\nLOW", "#2e7d32")]
    for i, (txt, c) in enumerate(rows):
        ax.text(10.33, 4.75 - i * 0.6, txt, **T(fontsize=9, color=c))
    ax.text(5.5, 0.45, "Both relays OFF = both motor wires on battery -  ->  motor stopped.   "
            "Relay 1 ON = dark blue gets +12 V  ->  turns one way.\n"
            "Relay 2 ON = brown gets +12 V  ->  turns the other way.   Both ON = both on +12 V  "
            "->  stopped (no short circuit possible).", **T(fontsize=9.5, color="#424242"))
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def current_path_diagram(path):
    """Where the current must flow when relay 1 is on: the four links to check."""
    fig, ax = plt.subplots(figsize=(11, 3.2), dpi=170)
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 3.2)
    ax.axis("off")
    steps = [("Battery +", "#ffcdd2"), ("Fuse", "#ffe082"), ("Relay 1\nNO -> COM", "#ede7f6"),
             ("Motor\ndark blue", "#bbdefb"), ("Motor\nbrown", "#d7ccc8"),
             ("Relay 2\nCOM -> NC", "#ede7f6"), ("Battery -", "#e0e0e0")]
    w, gap = 1.25, 0.32
    for i, (txt, fc) in enumerate(steps):
        x = 0.15 + i * (w + gap)
        box(ax, x, 1.2, w, 1.0, fc, "#616161")
        ax.text(x + w / 2, 1.7, txt, ha="center", va="center", fontsize=10, fontweight="bold")
        if i < len(steps) - 1:
            ax.annotate("", xy=(x + w + gap - 0.03, 1.7), xytext=(x + w + 0.03, 1.7),
                        arrowprops=dict(arrowstyle="-|>", lw=2, color="#424242"))
    ax.text(5.5, 2.75, "Relay 1 ON: the current must pass every link below. ONE loose link = "
            "motor does not move.", ha="center", fontsize=11, fontweight="bold", color=RED)
    ax.text(5.5, 0.6, "Relay 2 ON uses the mirror path: + -> fuse -> Relay 2 NO -> COM -> brown "
            "-> motor -> dark blue -> Relay 1 COM -> NC -> battery -", ha="center", fontsize=9.5,
            color="#424242")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def system_diagram(path):
    """The whole car: who talks to whom."""
    fig, ax = plt.subplots(figsize=(11, 4.6), dpi=170)
    ax.set_xlim(0, 11)
    ax.set_ylim(1.6, 6.2)
    ax.axis("off")

    def node(x, y, w, h, title, sub, fc, ec):
        box(ax, x, y, w, h, fc, ec, lw=1.3)
        ax.text(x + w / 2, y + h / 2 + (0.15 if sub else 0), title, ha="center", va="center",
                fontsize=10.5, fontweight="bold")
        if sub:
            ax.text(x + w / 2, y + h / 2 - 0.22, sub, ha="center", va="center", fontsize=8.5,
                    color="#424242")

    def arrow(x1, y1, x2, y2, label="", color="#424242"):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", lw=1.6, color=color))
        if label and abs(x1 - x2) < 0.01:      # vertical: label to the right of the line
            ax.text(x1 + 0.1, (y1 + y2) / 2, label, ha="left", va="center", fontsize=8,
                    color=color)
        elif label:
            ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.13, label, ha="center", fontsize=8,
                    color=color)

    node(0.2, 4.9, 2.2, 0.9, "RealSense D435i", "depth + colour camera", "#f3e5f5", "#7b1fa2")
    node(0.2, 3.6, 2.2, 0.9, "LDROBOT D500", "LiDAR (optional)", "#f3e5f5", "#7b1fa2")
    node(3.2, 3.6, 2.6, 2.2, "Jetson Orin Nano", "(or the laptop)\nnavya_autopilot.py",
         "#e8f5e9", "#2e7d32")
    node(3.2, 1.9, 2.6, 0.9, "Laptop", "screen: dashboard, menu", "#e8f5e9", "#2e7d32")
    node(6.6, 3.6, 2.0, 2.2, "Arduino Uno", "navya_drive.ino\nfirmware v2", "#e3f2fd",
         "#1565c0")
    node(6.6, 1.9, 2.0, 0.9, "FlySky FS-R6B", "radio receiver", "#e3f2fd", "#1565c0")
    node(9.2, 4.9, 1.7, 0.9, "2x YL-12", "controllers", "#fff8e1", "#f9a825")
    node(9.2, 3.6, 1.7, 0.9, "2x hub motor", "rear wheels", "#fff8e1", "#f9a825")
    node(9.2, 1.9, 1.7, 1.2, "Steering motor", "relays (now)\nBTS7960 (failed)", "#ffebee",
         "#c62828")
    node(0.2, 1.9, 2.2, 0.9, "Samsung T7 SSD", "trip recordings", "#eeeeee", "#616161")
    arrow(2.4, 5.35, 3.2, 5.1, "USB 3")
    arrow(2.4, 4.05, 3.2, 4.2, "USB")
    arrow(5.8, 4.9, 6.6, 4.9, "D,... 30/s")
    arrow(6.6, 4.4, 5.8, 4.4, "S,... 10/s")
    arrow(4.5, 2.8, 4.5, 3.6, "Wi-Fi / SSH")
    arrow(3.2, 3.75, 2.4, 2.55)
    arrow(7.6, 2.8, 7.6, 3.6, "CH1 CH2 CH5")
    arrow(8.6, 5.3, 9.2, 5.3, "PWM, F/R")
    arrow(10.05, 4.9, 10.05, 4.5)
    arrow(8.6, 3.75, 9.2, 2.85)
    ax.text(9.0, 3.42, "D5 D6", ha="left", va="center", fontsize=8, color="#424242")
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- text

def esc(s):
    return html.escape(s, quote=False)


def code_block(path, title):
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return f"<p><i>{esc(str(path))} was not found when this PDF was built.</i></p>"
    lines = text.splitlines()
    numbered = "\n".join(f"{i + 1:4d}  {line}" for i, line in enumerate(lines))
    return (f"<h3>{esc(title)}</h3><p class='small'>{esc(str(path))} - {len(lines)} lines</p>"
            f"<pre>{esc(numbered)}</pre>")


def diff_block():
    import subprocess
    try:
        out = subprocess.run(["git", "-C", str(REPO), "diff", "--",
                              "firmware/navya_drive/navya_drive.ino"],
                             capture_output=True, text=True, encoding="utf-8").stdout
    except OSError:
        out = ""
    if not out.strip():
        return "<p>No uncommitted change to the firmware when this PDF was built.</p>"
    return f"<pre>{esc(out)}</pre>"


CSS = """
@font-face { font-family: body; src: url(arial.ttf); }
@font-face { font-family: body; src: url(arialbd.ttf); font-weight: bold; }
@font-face { font-family: body; src: url(ariali.ttf); font-style: italic; }
@font-face { font-family: mono; src: url(consola.ttf); }
* { font-family: body; }
body { font-size: 10pt; line-height: 1.35; color: #212121; }
h1 { page-break-before: always; font-size: 20pt; color: #0d47a1; margin-top: 4pt; margin-bottom: 6pt; }
h2 { font-size: 14pt; color: #0d47a1; margin-top: 12pt; margin-bottom: 4pt; }
h3 { font-size: 11.5pt; color: #1a237e; margin-top: 10pt; margin-bottom: 3pt; }
p { margin-top: 3pt; margin-bottom: 3pt; }
li { margin-bottom: 2pt; }
table { border-collapse: collapse; width: 100%; margin-top: 4pt; margin-bottom: 6pt; }
th { font-weight: bold; color: #0d47a1; text-align: left; border: 0.8pt solid #546e7a;
     padding: 2pt 4pt; font-size: 9pt; }
td { border: 0.6pt solid #b0bec5; padding: 2pt 4pt; font-size: 9pt; vertical-align: top; }
pre { font-family: mono; font-size: 6.6pt; line-height: 1.18;
      padding: 4pt; }
code { font-family: mono; font-size: 8.8pt; color: #4a148c; }
.small { font-size: 8.5pt; color: #616161; }
.stuck { border: 2pt solid #c62828; padding: 6pt; }
.ok { border: 1.5pt solid #2e7d32; padding: 6pt; }
.note { border: 1.5pt solid #f9a825; padding: 6pt; }
.cover { font-size: 12pt; }
.first { page-break-before: avoid; }
.newpage { page-break-before: always; }
.good { color: #1b5e20; font-weight: bold; }
.bad { color: #b71c1c; font-weight: bold; }
.wait { color: #e65100; font-weight: bold; }
"""


def table(header, rows):
    h = "".join(f"<th>{c}</th>" for c in header)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table><tr>{h}</tr>{body}</table>"


G = "<span class='good'>{}</span>".format
B = "<span class='bad'>{}</span>".format
W = "<span class='wait'>{}</span>".format


def build_html(img):
    s = []
    a = s.append

    # ---------------- cover
    a(f"""
<h1 class="first">Navya: complete project record</h1>
<p class="cover"><b>Autonomous car on a TZ-306 ride-on toy.</b> Everything done from 29 October
to 9 November 2026: the car, every connection, all the code, every test with its result, every
problem and how it was fixed, where we are stuck now, and what is left.</p>
<p class="small">Owner: Sujal Negi. Repository: github.com/sujal128005/navya_autonomouscar
(branch main). Local copy on the laptop: C:\\Users\\connt\\dev\\navya_autonomouscar. This PDF is
made by docs/report/make_full_record.py.</p>

<div class="stuck"><b>WHERE WE ARE STUCK (9 Nov 2026)</b><br/>
The front steering does not move yet. We now drive the toy's steering motor through the
<b>2-channel relay module</b>. The new firmware is on the Arduino and works: on the first test
(front lifted, 1-second pulse) <b>relay 1 clicked, but the motor did not move</b>. So the
Arduino and the relay coil are fine, and the 12 V path through the relay contacts to the motor
is not complete. Next step: check the relay screw terminals (photo), battery + connection and
fuse, then test again. Details in section 10.</div>

<div class="ok"><b>WHAT WORKS (tested on the real car)</b><br/>
Demo 1 shown on 30 Oct (drive, slow, stop for an obstacle, drive on by itself). Rear drive with
both hub motors, manual and AUTO modes, radio emergency stop, laptop-silent stop (0.26 s),
obstacle stop on the ground (rests 1.10 m from a box), person detection on the ground (rests
1.8-2.0 m away), trip recorder, camera and LiDAR calibration. Jetson Orin Nano set up and
bench-tested on the car (3 Nov). The steering motor, gearbox, grey battery and fuse are proven
good.</div>

<h2>Contents</h2>
<ol>
<li>The project in short</li>
<li>The hardware</li>
<li>How the system works</li>
<li>Day-by-day record (29 Oct to 9 Nov)</li>
<li>All connections (wiring)</li>
<li>The steering story: every test and result</li>
<li>Firmware (Arduino) explained</li>
<li>Software (laptop / Jetson) explained, with commands</li>
<li>Every problem found and how it was fixed</li>
<li>Where we are stuck now, and how to get unstuck</li>
<li>What is left (full to-do list)</li>
<li>Parts, bill and what we own</li>
<li>Rules we work by</li>
<li>Appendix A: relay firmware change (exact diff)</li>
<li>Appendix B: config.py (all settings)</li>
<li>Appendix C: steering test script</li>
<li>Appendix D: full Arduino firmware</li>
</ol>
""")

    # ---------------- 1
    a(f"""
<h1>1. The project in short</h1>
<p><b>Navya</b> is a low-cost autonomous car built on a TZ-306 4x4 kids' ride-on car. (It is
not <i>Navyam</i>, which is a separate drone project.) The long-term goal is a car that drives
itself like a Tesla, on a student budget. We build it in stages:</p>
{table(["Stage", "Goal", "Status on 9 Nov"], [
    ["Demo 1", "Drive straight; slow down and stop for an obstacle; drive on by itself when it is "
     "removed", G("DONE, shown 30 Oct 2026")],
    ["Object detection", "Recognise people and stop signs; stop further from people",
     G("Tested on the ground 2 Nov")],
    ["Onboard computer", "Jetson Orin Nano on the car, laptop only as the screen",
     G("Set up and bench-tested 3 Nov") + "; " + W("needs a 12 V step-down converter to drive")],
    ["Demo 2: steering", "Turn the front wheels from the Arduino, then follow the corridor "
     "between the walls (lane following)", B("STUCK: steering motor does not move yet")],
    ["Later", "LiDAR mapping, wheel-speed feedback (needs an Arduino Mega)", "Planned"],
])}
<p><b>The professor's rule for steering:</b> keep the toy's own DC steering motor and gearbox
("not to change steering, do work with current only"). No servo. We only add a driver for the
motor (and later a position sensor).</p>
""")

    # ---------------- 2
    a(f"""
<h1>2. The hardware</h1>
{table(["Part", "Details", "Role"], [
    ["TZ-306 4x4 ride-on car", "about 31 kg with everything, wheelbase 0.745 m, width ~0.62 m",
     "chassis"],
    ["2x 8\" BLDC hub motors", "24 V 350 W, with drum brake arms, on welded steel brackets",
     "rear drive (replaced the toy's rear wheels)"],
    ["2x YL-12 brushless sine-wave controllers", "24 V, 350 W, 16 A, brake active LOW, "
     "under-voltage cut-off 21 V", "one per hub motor"],
    ["2x 6S LiPo", "22.2 V 5200 mAh (25.2 V full)", "motor power, one per controller"],
    ["Grey toy battery", "6-FMD-8, 12 V 8 Ah sealed lead-acid (SLA)", "steering motor power"],
    ["Arduino Uno (CH340 clone)", "16 MHz, USB serial at 250000 baud", "radio input, throttle, "
     "brakes, steering, safety rules"],
    ["FlySky FS-CT6B + FS-R6B", "6-channel transmitter and receiver",
     "manual driving, MANUAL/AUTO switch (CH5), emergency stop (stick back)"],
    ["Intel RealSense D435i", "depth + colour, at the front, 0.554 m high, 4.4 deg down",
     "obstacles, walls, object detection"],
    ["LDROBOT D500 LiDAR (STL-19P)", "360 deg, USB via CP210x, 230400 baud, on the dash bar",
     "second obstacle sensor (optional)"],
    ["NVIDIA Jetson Orin Nano Super", "JetPack 6.2, L4T 36.4.7, user nexara9, MAXN_SUPER",
     "onboard computer since 3 Nov"],
    ["Samsung T7 SSD 1 TB", "mounted at /mnt/t7ssd on the Jetson", "trip recordings"],
    ["Windows laptop", "i7-1260P, Iris Xe, Python 3.14", "development and the screen"],
    ["Toy steering DC motor + gearbox", "two wires: dark blue and brown", "turns the front wheels"],
    ["Toy's blue control board", "HONGHUIDIANZI HH-678K-RXSN2", "original toy electronics; "
     "not used for steering, NOT modified"],
    ["Steering driver (history)", "L298N (too weak) -> SmartElex BTS7960 (dead) -> 2-channel 5 V "
     "relay module (now)", "lets the Arduino turn the steering motor both ways"],
    ["Parts bought for steering (arrived 7 Nov)", "BTS7960, 2x 10k pot, 2x KW4 limit switch, "
     "inline blade fuse holders, 4x Littelfuse ATOF 10 A 32 V, 18 AWG red + black wire",
     "Robu.in order, Rs 2,302"],
    ["Also owned, unused", "Raspberry Pi 3B, ESP32, L298N, one unidentified LiDAR", ""],
])}
<p><b>Not owned:</b> a multimeter (strongly needed; see section 11).</p>
""")

    # ---------------- 3
    a(f"""
<h1>3. How the system works</h1>
<img src="{img['system']}" width="100%"/>
<p><b>Chain of command.</b> The onboard computer (Jetson, or the laptop) reads the camera (and
LiDAR), decides a speed and a steering angle, and sends the Arduino one short line about 30
times a second, for example <code>D,500,500,0,0</code> (left speed, right speed, brake,
steering). The Arduino replies 10 times a second with a status line <code>S,...</code>
(17 fields). The Arduino turns the speed into throttle PWM for the two YL-12 controllers,
drives the brake wires, and drives the steering motor.</p>
<h3>Driving modes (CH5 switch on the transmitter)</h3>
{table(["Mode", "What happens"], [
    ["MANUAL", "the right stick drives: up = forward, back = brake; left/right = steering"],
    ["AUTO (CH5 above 1700 us)", "the computer drives and steers. Pulling the stick back still "
     "stops the car"],
    ["NO_RC", "no radio signal for 0.1 s: motors off, brakes on, steering off"],
])}
<h3>Safety layers</h3>
{table(["Layer", "Protection", "Tested"], [
    ["Person with the transmitter", "stick back = stop + brake in any mode, even while the "
     "computer says drive", G("yes, 2 Nov (brake on in all 283 readings)")],
    ["Arduino", "stops if the radio is lost for 0.1 s or the computer is silent for 0.3 s",
     G("yes, motors off after 0.26 s")],
    ["Arduino, steering", "stops the steering motor at a limit switch, after 1.5 s without pot "
     "movement (stall), on a broken pot wire, with no radio", "firmware only"],
    ["Computer", "stops if depth frames stop for 0.5 s, if the LiDAR goes quiet (with --lidar), "
     "or if the lens is covered", G("yes")],
    ["Battery monitor", "warning at 22.2 V; below 21.6 V for 3 s it stops and stays stopped",
     W("needs 4 resistors (not fitted)")],
    ["Pre-flight check", "checks every part before a run", G("yes")],
])}
<h3>Obstacle detection and speed</h3>
<p>Each depth image becomes 3D points. Only points inside a box in front of the car count: 0.45 m
either side of the centre line, from 0.15 m above the floor up to 1.6 m, up to 4.5 m ahead. At
least 800 points are needed. The nearest 5% of those points is the obstacle distance.</p>
{table(["Distance to obstacle", "What the car does"], [
    ["more than 3.8 m", "CLEAR: cruise (speed 130)"],
    ["3.8 m to 2.0 m", "SLOWING: speed falls smoothly to creep (80)"],
    ["2.0 m or less", "STOPPED: brake. The 31 kg car rolls ~0.85 m more, so it rests ~1.1 m away"],
    ["nothing within 2.4 m for 0.5 s", "RESUMING: drives on, with a 0.4 s start boost (250)"],
])}
<p>With <code>--vision</code>, people make the car stop 1 m earlier (3.0 m). A stop sign within
2.5 m: stop, wait 3 s, drive on, ignore stop signs for 5 s. Detection and LiDAR can only make the
car more careful; the depth check always runs.</p>
""")

    # ---------------- 4 timeline
    a("<h1>4. Day-by-day record</h1>")
    days = [
        ("29 Oct 2026", [
            "Project started. Hardware identified from photos. Demo 1 goal set.",
            "Old work in the repository deleted (commit 4236da6), as the user asked.",
            "Demo 1 code written and pushed (ea16343): Arduino firmware (D9/D10 throttle, D8/D7 "
            "F/R, brake, radio CH2 on D3 and CH5 on D2) and the laptop autopilot.",
            "Firmware uploaded. The CH340 clone needed its USB driver rolled back to 3.5.2019.1 "
            "(version 3.9 fails with \"cannot set com-state\").",
            "Bench test: wheels start at PWM about 75. PWM_START = 75, PWM_MAX = 130 (aafcb04).",
            "First indoor AUTO ground run WORKED: drive, slow, stop, drive on. The car coasted "
            "~0.9 m past the stop (no brake wire), so stop distance raised to 2.0 m, slow-down "
            "3.8 m, cruise 130 (02378bd). Camera calibrated 0.555 m / 12.2 deg.",
        ]),
        ("30 Oct 2026 - DEMO 1 SHOWN", [
            "Corridor viewer (live lane, bird's-eye map, 3D point cloud) and lane finder added.",
            "Tape-strip lane detection failed on the shiny granite floor (mirror reflections), so "
            "the lane is found from the walls with depth (LANE_SOURCE = \"walls\").",
            "Demo 1 shown with the phone view over the laptop's hotspot "
            "(http://192.168.137.1:8080). Tweaks: resume delay 0.5 s, start boost 250 for 0.4 s.",
        ]),
        ("31 Oct 2026", [
            "Object detection: YOLO11n. Then OpenVINO on the Intel GPU: 19 ms per image (ONNX "
            "38 ms fallback). --vision: stop 1 m earlier for people; stop-sign rule.",
            "Trip recorder (--record), raw recording and replay, trip report.",
            "128 GB SD card (old Jetson card) wiped with the user's approval and formatted "
            "\"NAVYA\" for recordings.",
            "Steering parts studied. A 180 kg-cm servo was first chosen, then the professor "
            "decided: keep the toy steering motor. Final Robu.in cart: 7 lines, Rs 2,302 "
            "(BTS7960, 2 pots, 2 limit switches, fuse holders, 10 A fuses, red and black wire). "
            "The user paid themselves.",
        ]),
        ("1 Nov 2026", [
            "Firmware v2 (b1c368f): steering position control (BTS7960 on D5/D6, enable A3, "
            "pot A0, limit switches A1/A2, radio CH1 on D4). Brakes MOVED to D11/D12.",
            "steering_calibrate.py, lane_follow.py (pure pursuit), --steer.",
            "Pre-flight check, live tuning sliders, battery monitor (A4/A5), Ask Navya.",
            "Ask Navya changed to free AI: Gemini first, Groq fallback (no Anthropic key, as the "
            "user asked). Keys go in autopilot/keys.env (git-ignored).",
            "Navya.bat menu, GitHub Actions checks, LiDAR code, project report. Review fixes "
            "(2db5de0).",
        ]),
        ("2 Nov 2026 - hardware test day", [
            "Firmware v2 on the car. The CH340 3.9 driver package was deleted from Windows.",
            "Serial link moved to 250000 baud (115200 lost ~15 bytes a minute).",
            "Stick-back stop line lowered to 1300 us (stick centre had drifted to ~1410).",
            "LiDAR mounted above the camera and aligned (-1 deg, clockwise, 0.365 m, 10 cm left).",
            "Camera re-mounted rigidly: 0.554 m, 4.4 deg down.",
            "Ground run: braked at 1.97 m, rested 1.10 m from the box.",
            "--vision ground run: person seen at 5 m, braked 2.85 m, rested 1.8-2.0 m away.",
            "The laptop battery hit 4% and slept: pre-flight now fails below 20%.",
        ]),
        ("3 Nov 2026 - Jetson", [
            "Jetson Orin Nano Super set up: own Python environment, GPU PyTorch, TensorRT "
            "detection 23 ms per image, CH340 driver built for the JetPack kernel.",
            "Samsung T7 SSD erased (user ran the script; drone data deliberately discarded) and "
            "mounted at /mnt/t7ssd for recordings.",
            "Bench test on the car (wall power): camera, Arduino, LiDAR, detection, recording, "
            "dashboard all together; LiDAR 0 times \"lost\" (laptop had ~6 a minute).",
            "Navya Jetson.bat: one double-click on the laptop finds the Jetson and opens its menu.",
            "Wiring document docs/Navya_wiring.pdf (0bed771).",
        ]),
        ("4 Nov 2026 - first steering test (L298N)", [
            "Advice: one battery or two for the controllers (one is enough, the second as a swap).",
            "Brake wire question: the brake plug has yellow and orange wires and 2 sockets (one "
            "extended). Not yet wired.",
            "Wiring image Navya_wiring_16x9.png pushed (8eb2a54).",
            "L298N steering test: NO movement. Loose jumper wires at the Arduino kept dropping "
            "the radio; the Arduino was rewired without the breadboard.",
        ]),
        ("5 Nov 2026 - L298N works, but too weak", [
            "The user's old working code drove ENA from D10. The fix: remove the ENB jumper and "
            "drive ENB from A3. Then, front lifted, 255 for 1.4 s MOVED the wheels "
            "(0.8 s gave only a sound).",
            "On the ground: centre -> full right in 2 pulses; full right -> centre in 1 pulse; "
            "centre -> left: only a hum.",
            "Straight from the battery the motor took the wheels full right -> full left in 3 "
            "touches. So motor and battery are good; the L298N loses too much voltage.",
            "Grey battery charged with the iMAX B6AC (Pb mode, 12.0V(6P), 0.8 A). It finished at "
            "14.40 V / 0 mAh: it was already full.",
            "Decision: keep the BTS7960 order. L298N only for lifted tests.",
        ]),
        ("6 Nov 2026 (side task, not Navya)", [
            "Answers written for the Claude open-source programme application (reach and impact, "
            "how the subscription would be used, other info).",
        ]),
        ("7 Nov 2026 - parts arrive, BTS7960 fails", [
            "Parts arrived. Fuse holder explained; the fuse had been soldered straight to wires: "
            "use the inline holder. B- wire was red: use black, tape bare ends.",
            "Receiver to Arduino wiring repeated. Windows put CH340 driver 3.9 back on a new USB "
            "port (error 31); rolled back to 3.5.2019.1. Arduino became COM13.",
            "BTS7960: header and screw terminals came UNSOLDERED. The user soldered them; a "
            "solder bridge on L_EN shorted 5V (the 5V wire got warm), then it was fixed.",
            "No motor movement in either direction, with the firmware and with a bench test "
            "(EN and RPWM/LPWM straight to 5V). The board is presumed damaged.",
            "The fuse (Littelfuse ATOF 0287010, 10 A 32 V) has no indicator light; it is good "
            "(the motor ran through it straight from the battery). Datasheets checked.",
        ]),
        ("8-9 Nov 2026 - potentiometer, toy board, relays", [
            "How to fit the potentiometer: diagrams, 3D view, marked photo, YouTube links. "
            "From the underside video: the steering turns around a cross pin under the gearbox; "
            "a black arm goes from there to the tie rod. Option A: pot under the centre, on a "
            "plate held by the 2 gearbox screws. Option B: wire linkage from the tie rod. "
            "Coupler ideas: pot knob, M-seal, pen tube, bottle cap.",
            "The steering column is too thick for the pot, and it only turns the wheels by hand; "
            "the motor turns them in remote mode.",
            "The user: mechanical changes are difficult now. So: steering without a pot "
            "(open-loop: find the ends by stall, centre by time, correct with the camera).",
            "Toy board reviewed (HH-678K-RXSN2: MCU with 16 MHz crystal, GOLDEN GH-1C-12H 15 A "
            "relay, 2 MOSFETs, red 7-pin connector + - F B L S). Decision: do not modify it.",
            "Chosen: drive the steering motor with the 2-channel 5 V relay module (H-bridge). "
            "Firmware relay mode written (STEER_RELAYS), compiled (9684 bytes).",
            "Upload: Arduino on COM14, driver 3.9 again; user rolled back to 3.5.2019.1; upload OK. "
            "CFG shows steer_relays=1, radio in AUTO.",
            "Test, front lifted, 1 s pulse on relay 1: relay CLICKED, motor did NOT move. "
            "<b>We are here.</b>",
        ]),
    ]
    for day, items in days:
        a(f"<h3>{day}</h3><ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>")

    # ---------------- 5 wiring
    a(f"""
<h1>5. All connections (wiring)</h1>
<h2>5.1 Arduino Uno pins (firmware v2)</h2>
{table(["Arduino pin", "Goes to", "Status"], [
    ["D9", "LEFT controller throttle signal (purple wire)", G("working")],
    ["D10", "RIGHT controller throttle signal (purple wire)", G("working")],
    ["D8", "LEFT controller F/R (silver wire)", G("working")],
    ["D7", "RIGHT controller F/R (silver wire)", G("working")],
    ["GND", "BOTH controllers' throttle black + F/R black wires (shared ground)", G("working")],
    ["D11", "LEFT controller brake wire (active LOW)", W("not wired yet")],
    ["D12", "RIGHT controller brake wire (active LOW)", W("not wired yet")],
    ["D2", "receiver CH5 signal (MANUAL/AUTO switch)", G("working")],
    ["D3", "receiver CH2 signal (right stick up/down)", G("working")],
    ["D4", "receiver CH1 signal (right stick left/right = manual steering)", G("working")],
    ["5V / GND", "receiver + / - (middle / outer pin of any channel)", G("working")],
    ["D5", "relay module IN1 (relay 1)", W("wired 9 Nov, motor not moving yet")],
    ["D6", "relay module IN2 (relay 2)", W("wired 9 Nov")],
    ["5V / GND", "relay module DC+ / DC-", G("relay clicks")],
    ["A3", "steering enable (only for BTS7960 / L298N; leave EMPTY with relays)", "not used now"],
    ["A0", "potentiometer middle pin (outer pins to 5V and GND)", W("pot not fitted")],
    ["A1 / A2", "left / right limit switch to GND (closed = at that lock)", W("not fitted")],
    ["A4 / A5", "left / right LiPo through 47k / 10k divider (battery monitor)", W("not fitted")],
    ["USB", "laptop or Jetson", G("working (now COM14 on the laptop)")],
])}
<p>Every Uno pin is now in use. More inputs (wheel-speed sensors) need an Arduino Mega.</p>

<h2 class="newpage">5.2 Steering: relay module (CURRENT setup, 9 Nov)</h2>
<img src="{img['relay']}" width="100%"/>
{table(["Relay module", "Connect to"], [
    ["DC+ (VCC)", "Arduino 5V"], ["DC- (GND)", "Arduino GND"],
    ["IN1", "Arduino D5"], ["IN2", "Arduino D6"],
    ["Trigger jumpers (both)", "on LOW (input pulled LOW = relay ON)"],
    ["Relay 1 COM", "steering motor DARK BLUE wire"],
    ["Relay 2 COM", "steering motor BROWN wire"],
    ["Relay 1 NO and Relay 2 NO (joined)", "+12 V from the battery through the 10 A fuse"],
    ["Relay 1 NC and Relay 2 NC (joined)", "battery - (negative)"],
])}
{table(["D5 (relay 1)", "D6 (relay 2)", "Motor"], [
    ["off", "off", "stopped (both wires on battery -)"],
    ["ON", "off", "turns one way (dark blue +12 V)"],
    ["off", "ON", "turns the other way (brown +12 V)"],
    ["ON", "ON", "stopped (both on +12 V); this can never short the battery"],
])}
<p>Relay contacts are rated 10 A at 30 V DC. Use 18 AWG wire for battery and motor. The old
driver (BTS7960 / L298N) must be completely disconnected. Relays give full power or nothing:
no speed control (no PWM).</p>

<h2>5.3 Rear drive: YL-12 controller plugs</h2>
{table(["Plug", "Wire colours"], [
    ["Throttle", "black = GND, orange = +5 V out (leave unconnected), purple = signal"],
    ["F/R (direction)", "black = GND, silver = signal (open = forward)"],
    ["Brake (optional)", "\"Brake: Low\": pulling the brake wire to GND brakes. On our car the "
     "plug has yellow and orange wires and 2 sockets (one extended). Not wired yet."],
])}
<h3>Power</h3>
<ul>
<li>One 6S LiPo per controller. Join the two battery negatives with a proper wire, so motor
current never flows through the Arduino's ground.</li>
<li>Full charge 25.2 V; the controllers cut out at 21 V.</li>
<li>Power the Arduino before (or with) the controllers: they refuse to start if they see
throttle at power-on.</li>
<li>Steering motor: from the grey 12 V battery through the 10 A inline fuse.</li>
<li>Recommended: a 10k resistor from each purple throttle wire to GND, and a kill switch on the
controllers' power-lock wires.</li>
</ul>

<h2>5.4 Earlier steering drivers (for the record)</h2>
<h3>L298N (tested 4-5 Nov)</h3>
{table(["L298N", "Connect to"], [
    ["IN3 / IN4", "Arduino D5 / D6"], ["ENB", "Arduino A3 (jumper REMOVED; the ENB pin in line "
                                         "with the IN pins)"],
    ["OUT3 / OUT4", "steering motor dark blue / brown"], ["12V / GND", "grey battery + / -"],
    ["GND", "also to Arduino GND"],
])}
<h3>BTS7960 (tested 7 Nov, presumed dead)</h3>
{table(["BTS7960 pin", "Connect to"], [
    ["VCC / GND", "Arduino 5V / GND"], ["RPWM / LPWM", "Arduino D5 / D6"],
    ["R_EN + L_EN", "Arduino A3 (or 5V)"], ["R_IS / L_IS", "not used"],
    ["B+ / B-", "12 V battery through the 10 A fuse / battery -"],
    ["M+ / M-", "steering motor wires"],
])}
<p>Header labels: top row VCC, R_IS, R_EN, RPWM; bottom row GND, L_IS, L_EN, LPWM.</p>

<h2>5.5 Battery monitor (optional, not fitted)</h2>
<p>For each LiPo: <b>LiPo + -> 47 kOhm -> Uno pin -> 10 kOhm -> GND</b>. Left battery A4, right
battery A5. 25.2 V reads as 4.4 V at the pin.</p>

<h2>5.6 Computer connections</h2>
{table(["Device", "Connection"], [
    ["RealSense D435i", "USB 3 cable straight into the Jetson (or laptop). Not through a USB-C "
     "dock or cheap hub"],
    ["Arduino", "USB (CH340). Jetson: needs jetson/build_ch341.sh. Laptop: driver 3.5.2019.1"],
    ["LiDAR", "USB via its CP210x adapter"],
    ["Samsung T7", "Jetson USB-C, plug in before switching on (or sudo mount /mnt/t7ssd)"],
    ["Laptop <-> Jetson", "same Wi-Fi (phone hotspot or laptop hotspot; college Wi-Fi blocks "
     "it). ssh jetson, key ~/.ssh/navya_jetson"],
])}
<h2 class="newpage">5.7 Wiring image of 8 Nov (before the relay change)</h2>
<p class="small">docs/Navya_wiring_16x9.png. The steering part of this image is replaced by
section 5.2.</p>
<img src="{img['wiring16x9']}" width="100%"/>
""")

    # ---------------- 6 steering story
    a(f"""
<h1>6. The steering story: every test and result</h1>
<p>The toy's steering motor (two wires, dark blue and brown) turns the front wheels through the
toy gearbox. The Arduino cannot power a motor directly, so it needs a <b>driver</b> that can
switch 12 V both ways. This is everything we tried.</p>
{table(["Date", "Setup", "Test", "Result"], [
    ["4 Nov", "L298N, ENB jumper on", "full-power pulses, wheels lifted", B("no movement")],
    ["4 Nov", "same, IN3/IN4 and OUT3/OUT4", "retests after fixing loose wires", B("no movement")],
    ["5 Nov", "L298N, ENB driven by A3 (jumper removed)", "lifted, 255 for 0.8 s",
     "sound only"],
    ["5 Nov", "same", "lifted, 255 for 1.4 s", G("moved")],
    ["5 Nov", "same", "lifted, centre -> left", "moved about half way"],
    ["5 Nov", "same, ON THE GROUND", "centre -> full right", G("2 pulses")],
    ["5 Nov", "same, ground", "full right -> centre", G("1 pulse")],
    ["5 Nov", "same, ground", "centre -> left", B("hum only, no movement")],
    ["5 Nov", "motor straight on the battery, ground", "full right -> full left",
     G("3 short touches: motor and battery GOOD")],
    ["5 Nov", "verdict", "", "L298N loses too much voltage (about 2-3 V)"],
    ["7 Nov", "BTS7960 (after soldering)", "firmware pulses both ways", B("no movement")],
    ["7 Nov", "BTS7960 bench bypass", "EN to 5V, RPWM or LPWM to 5V", B("no movement")],
    ["7 Nov", "verdict", "", "BTS7960 presumed damaged (unsoldered from the factory, then a "
     "5 V short on L_EN)"],
    ["9 Nov", "2-channel relay module (H-bridge)", "lifted, relay 1 on for 1.0 s",
     B("relay clicked, motor did not move") + " - see section 10"],
])}
<h2>6.1 Why relays</h2>
<ul>
<li>The user already owns the relay module; no new parts.</li>
<li>A relay contact loses almost no voltage, unlike the L298N, so the motor gets the full 12 V
(the same as touching the battery, which worked).</li>
<li>Downside: full power or off, no speed control, and a click every switch. Fine for
steering.</li>
<li>Wired as an H-bridge where both relays off (or both on) means stopped, so a mistake in the
code can never short the battery.</li>
</ul>
<h2 class="newpage">6.2 Fitting the potentiometer (postponed)</h2>
<p>Without a position sensor the Arduino does not know where the wheels are. The plan is a 10k
pot that turns with the steering:</p>
<img src="{img['marked']}" width="100%"/>
<p class="small">Marked photo used while looking for the pot location (early guess; numbers 1-4
as labelled).</p>
{table(["Option", "How", "Notes"], [
    ["A: under the centre (coaxial)", "pot under the cross pin of the steering, body held by a "
     "small plate on the 2 gearbox screws; shaft coupled to the pin", "couplers: pot knob, "
     "M-seal putty, pen tube, bottle cap (pot shaft is 6 mm knurled, 18 splines)"],
    ["B: linkage", "pot on the chassis, a stiff wire from the tie-rod tab to a lever on the pot",
     "no need to reach the centre"],
    ["Not possible", "on the steering column", "the column is too thick and is only for manual "
     "steering; the motor turns the wheels in remote mode"],
])}
<p><b>Decision (8-9 Nov):</b> mechanical changes are difficult for now, so steer without the
pot first.</p>
<h2>6.3 Steering without a pot (plan, code not written yet)</h2>
{table(["Step", "How"], [
    ["Find the ends", "drive the motor until it stalls at full left / full right (stall = end)"],
    ["Find the centre", "from full right, drive left for half the measured end-to-end time"],
    ["While driving", "short pulses left/right; the camera's lane position corrects the error"],
    ["Limit", "firmware stall cut-off 1.5 s; without a pot, single pulses are capped at 1.4 s"],
])}
<h2>6.4 The toy's own board</h2>
<p>HONGHUIDIANZI HH-678K-RXSN2: a microcontroller with a 16 MHz crystal, one GOLDEN GH-1C-12H
15 A relay, two TO-220 MOSFETs, a red 7-pin connector marked roughly + - F B L S (drive inputs).
We decided <b>not</b> to modify it: there is no documentation, and our own relay module does
the same job safely.</p>
""")

    # ---------------- 7 firmware
    a(f"""
<h1>7. Firmware (Arduino) explained</h1>
<p>File: <code>firmware/navya_drive/navya_drive.ino</code> (firmware v2, 656 lines; full text
in Appendix D). Board: Arduino Uno, uploaded with arduino-cli (FQBN arduino:avr:uno).</p>
<h3>Commands the computer can send (250000 baud, one per line)</h3>
{table(["Command", "Meaning"], [
    ["D,&lt;left&gt;,&lt;right&gt;,&lt;brake&gt;[,&lt;steer&gt;]", "speed 0..1000 per wheel, "
     "brake 0/1, steering -1000 (full left)..1000 (full right)"],
    ["R,&lt;pwmLeft&gt;,&lt;pwmRight&gt;", "raw throttle PWM (calibration only)"],
    ["M,&lt;pwm&gt;", "raw steering motor -255..255 (AUTO only; used for our steering tests)"],
    ["K,L / K,C / K,R", "store the pot reading as full left / straight / full right (EEPROM)"],
    ["K,I,&lt;0|1&gt;", "1 = RPWM turns the wheels left"],
    ["K,X", "forget the steering calibration"],
    ["?", "print the settings (CFG line)"],
])}
<h3>Status line the Arduino sends 10 times a second (17 fields)</h3>
<p><code>S,mode,ch2_us,ch5_us,host_ok,pwmLeft,pwmRight,brake,ch1_us,steer_target,steer_pos,
pot_raw,limit_left,limit_right,steer_state,battery_left_mV,battery_right_mV</code></p>
<p class="small">Example from 9 Nov: S,AUTO,1512,2008,0,0,0,1,1500,0,0,969,0,0,NOCAL,0,0
(AUTO, stick centred, CH5 at 2008 us, brake on, steering not calibrated, no battery dividers).</p>
<h3>Key settings in the firmware</h3>
{table(["Setting", "Value", "Meaning"], [
    ["PWM_START / PWM_MAX", "75 / 130", "wheels start at 75; 130 = top speed cap"],
    ["RAMP_UP_PER_10MS", "5", "0 to full speed in 2 s"],
    ["RC_AUTO_ABOVE_US", "1700", "CH5 above this = AUTO"],
    ["RC_STOP_BELOW_US", "1300", "stick below this = stop + brake"],
    ["RC_TIMEOUT_MS / HOST_TIMEOUT_MS", "100 / 300", "radio lost / computer silent -> stop"],
    ["STEER_STALL_MS", "1500", "steering driven 1.5 s without pot movement = stall"],
    ["STEER_RELAYS", "true", "NEW 9 Nov: relay module instead of BTS7960"],
    ["STEER_RELAY_ON_PWM", "40", "|pwm| from 40 switches a relay on"],
    ["STEER_RELAY_MIN_MS / GAP_MS", "60 / 100", "no chatter; a reversal goes through \"both "
     "off\" for 100 ms"],
])}
<h3>The relay change (9 Nov, NOT committed yet)</h3>
<ul>
<li>New function <code>steerRelays()</code>: D5 LOW = relay 1 on, D6 LOW = relay 2 on, pin
released (floating) = relay off. Never both on at once.</li>
<li>Both relays are OFF at start-up and whenever the Arduino resets.</li>
<li><code>steerOff()</code> and <code>steerMotorRaw()</code> use the relays when
STEER_RELAYS is true; the old BTS7960 code stays for STEER_RELAYS = false.</li>
<li>The CFG line now shows <code>steer_relays=1</code>.</li>
<li>Compiled: 9684 bytes flash (30%), 379 bytes RAM (18%). Uploaded to COM14 on 9 Nov.</li>
</ul>
<h3>How to upload</h3>
<pre>arduino-cli compile --upload -p COM14 --fqbn arduino:avr:uno firmware/navya_drive
(arduino-cli.exe is in C:\\Users\\connt\\AppData\\Local\\Programs\\Arduino IDE\\resources\\app\\lib\\backend\\resources\\)</pre>
<p>Close the Arduino IDE Serial Monitor first. If the upload says "cannot set com-state":
Device Manager -> Ports -> USB-SERIAL CH340 -> Driver -> Roll Back Driver to 3.5.2019.1.</p>
""")

    # ---------------- 8 software
    a(f"""
<h1>8. Software (laptop / Jetson) explained</h1>
{table(["File", "What it does"], [
    ["Navya.bat / navya.sh", "menu on the laptop / on the Jetson: pre-flight, drive modes, "
     "viewers, calibration, tests"],
    ["Navya Jetson.bat", "laptop: one double-click finds the Jetson, opens its menu and dashboard"],
    ["autopilot/config.py", "every setting (Appendix B)"],
    ["autopilot/navya_autopilot.py", "the driving program (--phone --vision --steer --lidar "
     "--record --dry-run --show --replay)"],
    ["autopilot/preflight.py", "checks everything before a run; never moves the car"],
    ["autopilot/navya_link.py", "serial link to the Arduino (D, M, R, K commands; reads S lines)"],
    ["autopilot/obstacle.py", "depth image -> nearest obstacle in the car's path"],
    ["autopilot/speed_planner.py", "distance -> speed (CLEAR / SLOWING / STOPPED / RESUMING)"],
    ["autopilot/battery.py", "LiPo warning and stop"],
    ["autopilot/lane.py, lane_follow.py", "lane from the walls; pure-pursuit steering"],
    ["autopilot/steering_calibrate.py", "teaches full left / straight / full right (needs the pot)"],
    ["autopilot/vision.py, vision_rules.py, vision_view.py", "YOLO11n detection, people and "
     "stop-sign rules, viewer"],
    ["autopilot/export_models.py", "fast model copies: TensorRT (Jetson), OpenVINO, ONNX"],
    ["autopilot/lidar.py, lidar_view.py", "LiDAR reader and radar view"],
    ["autopilot/corridor_view.py", "lane, bird's-eye map, 3D map (never drives)"],
    ["autopilot/phone_stream.py, live_settings.py", "dashboard in the browser, live sliders"],
    ["autopilot/ask_navya.py", "Ask Navya: free Gemini, Groq fallback (display only)"],
    ["autopilot/trip_recorder.py, trip_report.py", "record videos + telemetry; trip summary"],
    ["autopilot/calibrate_camera.py", "measures camera height and tilt"],
    ["autopilot/throttle_test.py", "bench throttle test and PWM sweep"],
    ["autopilot/test_logic.py", "offline tests, no hardware (27 tests)"],
    ["jetson/setup_jetson.sh, build_ch341.sh, find_jetson.py", "Jetson setup, Arduino driver, "
     "finding the Jetson on the Wi-Fi"],
    ["docs/wiring/make_wiring_pdf.py, make_wiring_image.py", "wiring PDF and 16:9 image"],
    [".github/workflows/ci.yml", "GitHub runs the tests and compiles the firmware on every push"],
])}
<h3>Common commands (inside the autopilot folder)</h3>
<pre>python preflight.py                              check everything first
python navya_autopilot.py --phone                drive, watch in the browser
python navya_autopilot.py --phone --vision --record   drive + detection + recording
python navya_autopilot.py --dry-run --show       camera only, motors never driven
python navya_autopilot.py --phone --lidar        drive with the LiDAR too
python calibrate_camera.py --write               camera height and tilt
python throttle_test.py --sweep                  find PWM_START (wheels up)
python steering_calibrate.py                     needs the pot
python trip_report.py                            summary of the last trip
python test_logic.py                             offline tests</pre>
<h3>Steering test scripts used on 9 Nov (in the session scratchpad, copied to Appendix C)</h3>
<pre>python pulse1.py COM14 255 1.0     one 1-second pulse, relay 1 (D5)
python pulse1.py COM14 -255 1.0    one 1-second pulse, relay 2 (D6)</pre>
<p>The script refuses to send unless the radio is in AUTO, sends the M command every 50 ms,
and always ends with the motor off. Maximum 1.4 s per pulse.</p>
<h3>Ask Navya keys (still pending)</h3>
<p>Copy <code>autopilot/keys.env.example</code> to <code>autopilot/keys.env</code>, then add a
free GEMINI_API_KEY (aistudio.google.com) and GROQ_API_KEY (console.groq.com). Never paste keys
in chat. No Anthropic key.</p>
<h3>Jetson facts</h3>
{table(["Item", "Value"], [
    ["Model / OS", "Jetson Orin Nano Super, JetPack 6.2, L4T 36.4.7, MAXN_SUPER"],
    ["Python", "own environment ~/navya_autonomouscar/.venv: torch 2.8.0 (cu126), numpy &lt; 2, "
     "opencv &lt; 4.12"],
    ["Detection", "TensorRT engine, 23 ms per image"],
    ["Recordings", "/mnt/t7ssd/navya_trips (Samsung T7)"],
    ["Network", "laptop and Jetson on the same hotspot; ssh jetson; dashboard "
     "http://&lt;jetson-ip&gt;:8080"],
    ["sudo", "the user types the Jetson password in a terminal; never typed by Claude"],
])}
""")

    # ---------------- 9 problems
    a(f"""
<h1>9. Every problem found and how it was fixed</h1>
{table(["Problem", "Cause", "Fix / status"], [
    ["Car stopped too close (Demo 1)", "31 kg coasts ~0.9 m after the brake", "stop 2.0 m, "
     "slow-down 3.8 m, cruise 130"],
    ["Slow to move off", "long resume delay; car needs a push", "resume 0.5 s, start boost 0.4 s"],
    ["False obstacle at 1.8 m", "floor points just above the clearance line",
     "clearance 0.15 m, min 800 points"],
    ["Tape lane failed", "shiny floor reflections", "lane from the walls (depth)"],
    ["Arduino upload fails \"cannot set com-state\"", "CH340 driver 3.9 on the clone",
     "roll back to 3.5.2019.1 (happened again 7 Nov and 9 Nov on new USB ports)"],
    ["~15 damaged serial lines a minute", "115200 baud is 2% off on 16 MHz",
     "250000 baud: 0 damaged in 1,200 lines"],
    ["Brake flickered with stick untouched", "stick centre drifted to ~1410 us",
     "stop line 1300 us"],
    ["Camera at USB 2 / stuck", "shared cheap hub", "camera straight into a port; auto reset"],
    ["LiDAR saw the camera", "same height", "LiDAR raised above the camera"],
    ["Floor became an obstacle after hard stops", "taped camera mount nodded 8 deg",
     "rigid mount, recalibrated"],
    ["Laptop slept mid-test", "hub could not charge it; 4% battery",
     "charge directly; pre-flight fails below 20%"],
    ["No Arduino port on the Jetson", "JetPack kernel lacks CH341 driver",
     "jetson/build_ch341.sh"],
    ["Same line repeated on the Jetson", "byte-wise readline with that driver",
     "read chunks, split lines ourselves"],
    ["Camera would not start on the Jetson", "USB-C dock", "plain cable into a Jetson port"],
    ["GPU PyTorch broken", "wrong torch build, numpy 2 pulled in", "own venv, pinned versions"],
    ["Laptop cannot reach the Jetson", "college Wi-Fi isolates devices", "hotspot"],
    ["L298N silent (4 Nov)", "enable jumper not bridging", "ENB driven from A3"],
    ["Radio NO_RC, channels 0", "loose jumper wires at the Arduino",
     "pushed in; rewired without the breadboard"],
    ["L298N too weak going left on the ground", "voltage drop in the L298N",
     "not fixable; moved to BTS7960, then relays"],
    ["BTS7960 does not move the motor", "came unsoldered; 5 V solder bridge on L_EN",
     B("board presumed dead")],
    ["Fuse soldered to wires; red B- wire; bare ends close", "", "use the inline holder, black "
     "for negative, tape bare ends"],
    ["iMAX B6AC showed 2.0V(1P)", "wrong cell setting", "12.0V(6P), 0.8 A"],
    ["Relay clicks, motor does not move (9 Nov)", "12 V path through the contacts incomplete",
     B("OPEN - section 10")],
    ["LiDAR \"lost\" on the laptop", "unknown (not motors, not load)",
     "does not happen on the Jetson"],
])}
""")

    # ---------------- 10 stuck
    a(f"""
<h1>10. Where we are stuck now, and how to get unstuck</h1>
<div class="stuck"><b>Symptom:</b> front lifted, Arduino sends a 1-second pulse to relay 1
(D5). The relay CLICKS (its LED lights), but the steering motor does not move.<br/>
<b>Meaning:</b> the Arduino, the firmware, the radio (AUTO) and the relay coil all work. The
problem is on the 12 V side: the current is not getting from the battery, through the relay
contacts, to the motor and back.</div>
<img src="{img['path']}" width="100%"/>
<h3>Most likely causes, in order</h3>
{table(["#", "Possible cause", "How to check (no multimeter needed)"], [
    ["1", "Battery + was not connected during the test (earlier instructions said keep it off "
     "while wiring)", "make sure the fuse lead is on battery + before \"Ready\""],
    ["2", "A wire is on the wrong screw (COM is the MIDDLE screw of each relay)",
     "read the small print next to each screw: NO, COM, NC"],
    ["3", "A screw is clamped on the wire's plastic, not on bare copper",
     "pull each wire gently; strip 6-7 mm and re-tighten"],
    ["4", "Relay 2's NC is not on battery - (the return path for relay 1)",
     "follow the black wire from relay 2 NC to battery -"],
    ["5", "The NO-NO link or NC-NC link is missing", "both NO joined, both NC joined"],
    ["6", "Fuse not seated in the holder or blown", "swap in a spare 10 A fuse"],
    ["7", "Motor wire came off", "dark blue on relay 1 COM, brown on relay 2 COM"],
])}
<h3>Quick test without the Arduino (battery + connected, front lifted)</h3>
<ol>
<li>Disconnect the dark blue wire from relay 1 COM and touch it for one second to the fuse lead
(+12 V), with the brown wire still on relay 2 COM. If the wheels turn: relay 2's NC and the
battery - path are fine, and the fault is at relay 1 (NO or COM screw).</li>
<li>If nothing turns: the fault is on the battery - side (relay 2 NC, the NC link, or the black
wire).</li>
</ol>
<h3>After it moves</h3>
<ol>
<li>Pulse the other direction (relay 2, D6).</li>
<li>Ground test: centre -> full left, the move the L298N could not do.</li>
<li>Then open-loop steering (find the ends by stall, centre by time), and later the pot.</li>
<li>Commit the relay firmware with the co-author line, and update the README and wiring docs.</li>
</ol>
""")

    # ---------------- 11 todo
    a(f"""
<h1>11. What is left (full to-do list)</h1>
{table(["#", "Task", "Waiting for"], [
    ["1", "Fix the relay 12 V path and get the steering motor moving (section 10)", "terminal "
     "photo / check"],
    ["2", "Test both directions lifted, then centre -> full left on the ground", "item 1"],
    ["3", "Open-loop steering code: ends by stall, centre by time, camera correction", "item 2"],
    ["4", "Commit and push the relay firmware; update README steering section and wiring docs",
     "item 2 + the user's OK"],
    ["5", "Fit the potentiometer (option A or B), then run steering_calibrate.py",
     "time for mechanical work"],
    ["6", "Fit the 2 limit switches (A1/A2)", "mounting"],
    ["7", "Lane following run in the corridor at creep speed with --record", "items 3/5"],
    ["8", "Brake wires to D11/D12. The earlier plan put them through the relay module, which is "
     "now used for steering: needs a second relay module, or a multimeter check of the brake "
     "wire voltage first", "decision + multimeter"],
    ["9", "Buy a multimeter", "purchase"],
    ["10", "Replacement BTS7960 (buy pre-soldered) if relays are not good enough", "decision"],
    ["11", "One battery for both controllers (the second LiPo as a swap)", "decision"],
    ["12", "12 V step-down converter (LiPo -> 5 A fuse -> 12 V >= 5 A -> Jetson), then drive "
     "with the Jetson", "converter (ordered)"],
    ["13", "Person test on the ground: car must drive on after the person steps aside", "test time"],
    ["14", "--lidar ground run (with the Jetson)", "item 12"],
    ["15", "Battery monitor: 2x 47k + 2x 10k resistors on A4/A5", "4 resistors"],
    ["16", "Ask Navya keys in autopilot/keys.env, then a live test", "the user's free keys"],
    ["17", "Change the Jetson password with <code>passwd</code> (it was written in chat once)",
     "the user"],
    ["18", "MIT licence for the repository (offered, no answer yet)", "the user's choice"],
    ["19", "Later: Arduino Mega for wheel-speed sensors; LiDAR mapping", "budget"],
])}
""")

    # ---------------- 12 parts
    a(f"""
<h1>12. Parts, bill and what we own</h1>
<h3>Robu.in order (31 Oct, Rs 2,302 incl. GST), arrived 7 Nov</h3>
{table(["Qty", "Part", "SKU", "Status"], [
    ["1", "SmartElex BTS7960 motor driver (43 A, 6-27 V)", "R189064", B("presumed dead")],
    ["2", "10 kOhm potentiometer, 15 mm shaft", "607345", W("not fitted")],
    ["2", "KW4 roller-lever micro switch", "R132437", W("not fitted")],
    ["1", "Inline blade fuse holders (5 pcs)", "699636", G("in use")],
    ["4", "10 A blade fuse (Littelfuse ATOF 0287010, 32 V)", "R182177", G("in use, proven good")],
    ["2 m", "18 AWG silicone wire, red", "R164399", G("in use")],
    ["2 m", "18 AWG silicone wire, black", "R164398", G("in use")],
])}
<p>Considered but not bought (kept in docs/navya_bill_robu.xlsx, marked No): 180 kg-cm servo
BL51180-24V and its linkage (professor: keep the toy steering), e-stop button and relay, battery
isolator switches, XT60 pigtails, 256 GB microSD.</p>
<h3>Grey battery charging (iMAX B6AC)</h3>
{table(["Setting", "Value"], [
    ["Program", "Pb (lead-acid) CHARGE"], ["Voltage", "12.0V(6P)"],
    ["Current", "0.8 A (0.1 x 8 Ah; maximum 2.4 A)"],
    ["Label limits", "cyclic charge 14.5-14.9 V, max 2.4 A"],
    ["Result 5 Nov", "finished at 14.40 V, 0 mAh: it was already full"],
])}
""")

    # ---------------- 13 rules
    a(f"""
<h1>13. Rules we work by</h1>
<ul>
<li>The car never moves without the user's go-ahead: wheels up (or front lifted), everyone
clear, and the user says "Ready".</li>
<li>Keep battery + disconnected while wiring.</li>
<li>Steering: keep the toy's own motor and gearbox (professor).</li>
<li>Never type the user's passwords, OTPs or logins; the user types sudo passwords
themselves.</li>
<li>No Anthropic API key in the project; free Gemini + Groq with fallback; keys never pasted in
chat.</li>
<li>No simulation work; scripted offline tests are fine.</li>
<li>System and driver settings (like the CH340 rollback) are changed by the user.</li>
<li>Commit and push only with the user's OK. Commit messages end with
"Co-Authored-By: Claude Opus 5.5 &lt;noreply@anthropic.com&gt;".</li>
<li>One step at a time, simple words, tables.</li>
</ul>
""")

    # ---------------- appendices
    a("<h1>Appendix A: relay firmware change (exact diff, not committed yet)</h1>")
    a(diff_block())
    a("<h1>Appendix B: config.py (all settings)</h1>")
    a(code_block(REPO / "autopilot" / "config.py", "autopilot/config.py"))
    a("<h1>Appendix C: steering test script</h1>")
    a(code_block(SCRATCH_PULSE, "pulse1.py"))
    a("<h1>Appendix D: full Arduino firmware</h1>")
    a(code_block(REPO / "firmware" / "navya_drive" / "navya_drive.ino",
                 "firmware/navya_drive/navya_drive.ino"))
    return "\n".join(s)


# ---------------------------------------------------------------- PDF

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--png", help="also write one PNG per page into this folder")
    ap.add_argument("--marked", help="marked steering photo (default: steering_marked.jpg here)")
    args = ap.parse_args()

    BUILD.mkdir(exist_ok=True)
    relay_diagram(BUILD / "relay.png")
    current_path_diagram(BUILD / "path.png")
    system_diagram(BUILD / "system.png")
    img = {"relay": "relay.png", "path": "path.png", "system": "system.png",
           "wiring16x9": "Navya_wiring_16x9.png", "marked": "steering_marked.jpg"}
    marked = Path(args.marked) if args.marked else HERE / "steering_marked.jpg"
    (BUILD / "steering_marked.jpg").write_bytes(marked.read_bytes())

    arch = pymupdf.Archive()
    arch.add(str(BUILD))
    arch.add(str(DOCS))
    for name in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "consola.ttf"):
        arch.add((FONTS / name).read_bytes(), name)

    story = pymupdf.Story(html=build_html(img), user_css=CSS, archive=arch)
    page = pymupdf.paper_rect("a4")
    where = page + (42, 46, -42, -46)
    tmp = BUILD / "body.pdf"
    writer = pymupdf.DocumentWriter(str(tmp))
    more = 1
    while more:
        dev = writer.begin_page(page)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()

    doc = pymupdf.open(str(tmp))
    n = doc.page_count
    for i, p in enumerate(doc):
        p.insert_text((42, page.height - 22), "Navya - complete project record - 9 Nov 2026",
                      fontsize=7.5, color=(0.45, 0.45, 0.45))
        p.insert_text((page.width - 95, page.height - 22), f"page {i + 1} of {n}",
                      fontsize=7.5, color=(0.45, 0.45, 0.45))
    doc.set_metadata({"title": "Navya - complete project record", "author": "Sujal Negi"})
    doc.save(str(OUT), garbage=3, deflate=True)
    if args.png:
        out = Path(args.png)
        out.mkdir(parents=True, exist_ok=True)
        for i, p in enumerate(doc):
            p.get_pixmap(dpi=70).save(str(out / f"p{i + 1:02d}.png"))
    doc.close()
    try:
        tmp.unlink()
    except OSError:
        pass
    print(f"wrote {OUT} ({n} pages)")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
