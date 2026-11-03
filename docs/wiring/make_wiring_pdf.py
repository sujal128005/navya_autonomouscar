"""Build docs/Navya_wiring.pdf: the car's wiring on landscape A4 pages (vector diagrams, HD).

    python docs/wiring/make_wiring_pdf.py            # writes docs/Navya_wiring.pdf
    python docs/wiring/make_wiring_pdf.py --png DIR  # also one PNG per page, for checking

Edit the tables below when the wiring changes, then run it again. Pin assignments follow
firmware v2 (firmware/navya_drive/navya_drive.ino) and the README's Wiring section; the
photos are stills from the walk-round video of 3 Nov 2026.
"""

import argparse
import textwrap
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch

HERE = Path(__file__).resolve().parent
PHOTOS = HERE / "photos"
OUT = HERE.parent / "Navya_wiring.pdf"
A4_LANDSCAPE = (11.69, 8.27)

POWER, SIGNAL, USB, RADIO, PLANNED = "#c62828", "#1565c0", "#2e7d32", "#757575", "#ef6c00"
BOX_FILL = {"power": "#ffebee", "drive": "#fff8e1", "control": "#e3f2fd", "compute": "#e8f5e9",
            "sensor": "#f3e5f5", "planned": "#fff3e0", "other": "#f5f5f5"}

ARDUINO_PINS = [
    ("D9", "LEFT controller throttle signal (purple)", "drive"),
    ("D10", "RIGHT controller throttle signal (purple)", "drive"),
    ("D8", "LEFT controller F/R (silver)", "drive"),
    ("D7", "RIGHT controller F/R (silver)", "drive"),
    ("D11", "LEFT controller brake wire (optional; active low)", "drive"),
    ("D12", "RIGHT controller brake wire (optional; active low)", "drive"),
    ("GND", "BOTH controllers' throttle black + F/R black (shared ground)", "drive"),
    ("D3", "Receiver CH2 signal (right stick up/down: throttle, pull back = STOP)", "control"),
    ("D2", "Receiver CH5 signal (switch: MANUAL / AUTO)", "control"),
    ("D4", "Receiver CH1 signal (right stick left/right: manual steering)", "control"),
    ("5V / GND", "Receiver + / -", "control"),
    ("D5 / D6", "BTS7960 RPWM / LPWM  (steering - parts on order)", "planned"),
    ("A3", "BTS7960 R_EN + L_EN  (steering)", "planned"),
    ("A0", "Steering potentiometer middle pin (outer pins 5V / GND)", "planned"),
    ("A1 / A2", "LEFT / RIGHT steering limit switch to GND", "planned"),
    ("A4 / A5", "Battery monitor: LiPo+ -47k- pin -10k- GND (left / right)", "planned"),
    ("USB", "Jetson USB-A port (or laptop) - 250000 baud, CH340 chip", "compute"),
]

USB_PORTS = [
    ("RealSense D435i camera", "Jetson USB-A, straight in (USB 3, 5 Gbit/s)",
     "Plain cable only. Through a USB-C dock it fails to start ('Port reset failed')."),
    ("Arduino Uno (CH340)", "Jetson USB-A", "Needs the ch341 driver: bash jetson/build_ch341.sh"),
    ("LiDAR D500 via CP2102 adapter", "Jetson USB-A", "230400 baud; found automatically"),
    ("Samsung T7 SSD 1 TB", "Jetson USB-C", "Mounted at /mnt/t7ssd at start-up; trips in navya_trips"),
    ("Power", "Jetson DC barrel jack 5.5 x 2.5 mm", "9-20 V, max 4.2 A. Now: 19 V wall adapter"),
    ("Network", "Wi-Fi", "Same Wi-Fi as the laptop (phone hotspot / laptop hotspot)"),
]


# ---------------------------------------------------------------- drawing helpers

def new_page(pdf_title: str, subtitle: str = ""):
    fig = plt.figure(figsize=A4_LANDSCAPE)
    fig.text(0.04, 0.955, pdf_title, fontsize=19, weight="bold", color="#212121")
    if subtitle:
        fig.text(0.04, 0.925, subtitle, fontsize=10.5, color="#616161")
    fig.add_artist(plt.Line2D([0.04, 0.96], [0.912, 0.912], color="#bdbdbd", lw=0.8))
    fig.text(0.04, 0.025, "Navya autonomous car - wiring", fontsize=8, color="#9e9e9e")
    fig.text(0.96, 0.025, f"{date.today():%d %b %Y}  |  github.com/sujal128005/navya_autonomouscar",
             fontsize=8, color="#9e9e9e", ha="right")
    return fig


def canvas(fig, rect=(0.04, 0.08, 0.92, 0.82), xlim=(0, 100), ylim=(0, 62)):
    ax = fig.add_axes(rect)
    ax.set_xlim(*xlim)
    ax.set_ylim(*ylim)
    ax.axis("off")
    return ax


def box(ax, x, y, w, h, title, lines=(), kind="other", dashed=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.25,rounding_size=0.9",
                                fc=BOX_FILL[kind], ec=PLANNED if dashed else "#424242",
                                lw=1.4, ls="--" if dashed else "-"))
    ax.text(x + w / 2, y + h - 1.4, title, ha="center", va="top", fontsize=10, weight="bold")
    for i, line in enumerate(lines):
        ax.text(x + w / 2, y + h - 3.6 - 1.85 * i, line, ha="center", va="top", fontsize=7.6,
                color="#424242")


def wire(ax, points, color, label=None, label_at=0.5, lw=2.0, ls="-", label_dy=0.8, ha="center"):
    xs, ys = zip(*points)
    ax.plot(xs, ys, color=color, lw=lw, ls=ls, solid_capstyle="round", zorder=1)
    if label:
        # label at the midpoint of the longest segment
        segs = list(zip(points[:-1], points[1:]))
        (x0, y0), (x1, y1) = max(segs, key=lambda s: abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1]))
        lx, ly = x0 + (x1 - x0) * label_at, y0 + (y1 - y0) * label_at
        ax.text(lx, ly + label_dy, label, color=color, fontsize=7.3, ha=ha, va="bottom",
                bbox=dict(fc="white", ec="none", pad=0.6, alpha=0.9), zorder=3)


def legend(ax, x, y):
    for i, (color, ls, text) in enumerate([(POWER, "-", "Power"),
                                           (SIGNAL, "-", "Arduino signals"),
                                           (USB, "-", "USB"),
                                           (RADIO, ":", "Radio / Wi-Fi"),
                                           (PLANNED, "--", "Planned")]):
        ax.plot([x, x + 3.5], [y - 2.2 * i] * 2, color=color, lw=2.2, ls=ls)
        ax.text(x + 4.5, y - 2.2 * i, text, va="center", fontsize=8)


def table(fig, rect, rows, col_labels, col_widths, kinds=None, fontsize=8.5):
    ax = fig.add_axes(rect)
    ax.axis("off")
    t = ax.table(cellText=rows, colLabels=col_labels, colWidths=col_widths, loc="upper center",
                 cellLoc="left", colLoc="left")
    t.auto_set_font_size(False)
    t.set_fontsize(fontsize)
    t.scale(1, 1.55)
    for (r, c), cell in t.get_celld().items():
        cell.set_edgecolor("#e0e0e0")
        if r == 0:
            cell.set_facecolor("#37474f")
            cell.set_text_props(color="white", weight="bold")
        elif kinds:
            cell.set_facecolor(BOX_FILL[kinds[r - 1]])
        if c == 0 and r > 0:
            cell.set_text_props(weight="bold")
    return ax


def photo(fig, rect, path, title, caption):
    ax = fig.add_axes(rect)
    ax.imshow(mpimg.imread(path))
    ax.set_xticks([])
    ax.set_yticks([])
    for s in ax.spines.values():
        s.set_edgecolor("#9e9e9e")
    ax.set_title(title, fontsize=10.5, weight="bold", loc="left", pad=4)
    ax.text(0, -0.04, textwrap.fill(caption, 58), transform=ax.transAxes, fontsize=8, va="top", color="#424242")
    return ax


# ---------------------------------------------------------------- pages

def page_overview(pdf):
    fig = new_page("1. Whole car - how everything connects",
                   "Jetson Orin Nano drives the car; the laptop is only the screen (dashboard + SSH over Wi-Fi).")
    ax = canvas(fig, xlim=(-5, 100))
    # drive train, left and right
    for y, side in ((45, "LEFT"), (7, "RIGHT")):
        box(ax, 1, y, 14, 10, f"LiPo {side}", ["6S 22.2 V 5200 mAh", "25.2 V full, 21 V empty"], "power")
        box(ax, 21, y, 16, 10, f"YL-12 {side}", ["24 V 350 W sine controller", "brake active low, cut 21 V"], "drive")
        box(ax, 43, y, 13, 10, f"Hub motor {side}", ['8" BLDC 24 V 350 W', "rear wheel"], "drive")
        wire(ax, [(15.3, y + 6), (20.7, y + 6)], POWER, "XT60", label_dy=0.5)
        wire(ax, [(37.3, y + 6), (42.7, y + 6)], POWER, "3 phases + hall", label_dy=0.5)
    # joined negatives, along the left edge (clear of the receiver and transmitter)
    wire(ax, [(0.7, 49), (-1.8, 49), (-1.8, 11), (0.7, 11)], POWER, lw=2.6)
    ax.text(-3.4, 30, "battery negatives joined  (+ Arduino GND)", rotation=90, ha="center", va="center",
            fontsize=7.3, color=POWER)
    # Arduino + receiver
    box(ax, 21, 25, 16, 11.5, "Arduino Uno", ["firmware v2, 250000 baud", "safety: radio + laptop", "timeouts, stick-back STOP"], "control")
    box(ax, 1, 25.5, 13.5, 10.5, "FS-R6B receiver", ["CH2 throttle / stop", "CH5 MANUAL-AUTO", "CH1 steering"], "control")
    wire(ax, [(14.8, 30.5), (20.7, 30.5)], SIGNAL, "D3 D2 D4\n5V GND", label_dy=0.4)
    wire(ax, [(27, 36.8), (27, 44.7)], SIGNAL, "D9 throttle\nD8 F/R  D11 brake", label_dy=-0.4, ha="left", label_at=0.1)
    wire(ax, [(27, 24.7), (27, 17.3)], SIGNAL, "D10 throttle\nD7 F/R  D12 brake", label_dy=-3.2, ha="left", label_at=0.1)
    box(ax, 0.5, 38.5, 12, 4.4, "FS-CT6B", ["transmitter"], "other")
    wire(ax, [(6.5, 38.3), (6.5, 36.2)], RADIO, ls=":", lw=1.6)
    # steering (planned)
    box(ax, 43, 25.5, 13, 10.5, "Steering", ["BTS7960 + toy motor", "pot A0, limits A1/A2", "12 V battery, 10 A fuse"], "planned", dashed=True)
    wire(ax, [(37.3, 30.5), (42.7, 30.5)], PLANNED, "D5 D6 A3", ls="--", label_dy=0.4)
    # Jetson and its USB
    box(ax, 63, 23.5, 16, 14, "Jetson Orin Nano", ["Super, JetPack 6.2", "autopilot + TensorRT", "detection, dashboard :8080"], "compute")
    wire(ax, [(37.3, 26.5), (40, 26.5), (40, 21.5), (60, 21.5), (60, 25.5), (62.7, 25.5)], USB,
         "USB to the Jetson (CH340 driver)", label_dy=0.3)
    box(ax, 85, 47, 14, 9, "RealSense D435i", ["front, 0.554 m, 4.4 deg down", "USB 3 - plain cable"], "sensor")
    box(ax, 85, 33, 14, 9, "LiDAR D500", ["dashboard bar, raised", "CP2102 USB adapter"], "sensor")
    box(ax, 85, 19, 14, 9, "Samsung T7 SSD", ["1 TB, /mnt/t7ssd", "trip recordings"], "compute")
    wire(ax, [(79.3, 34), (82, 34), (82, 51.5), (84.7, 51.5)], USB, "USB 3", label_at=0.5, label_dy=0.3)
    wire(ax, [(79.3, 31.5), (84.7, 37.5)], USB)
    wire(ax, [(79.3, 28.5), (82, 28.5), (82, 23.5), (84.7, 23.5)], USB, "USB-C", label_dy=0.3)
    # Jetson power
    box(ax, 63, 5, 16, 11, "Jetson power", ["now: 19 V wall adapter", "planned: LiPo -> 5 A fuse ->", "12 V step-down (>= 5 A)"], "planned", dashed=True)
    wire(ax, [(71, 16.3), (71, 23.2)], POWER, "barrel jack 9-20 V", label_dy=0, ha="left", label_at=0.2)
    wire(ax, [(15.3, 9), (17.5, 9), (17.5, 2.5), (60, 2.5), (60, 8), (62.7, 8)], PLANNED, "planned tap from a LiPo", ls="--", label_at=0.45, label_dy=0.3)
    # laptop
    box(ax, 63, 47, 16, 9, "Laptop (screen)", ["dashboard in browser", "Navya Jetson.bat (SSH)"], "other")
    wire(ax, [(71, 46.7), (71, 37.8)], RADIO, "Wi-Fi", ls=":", lw=1.8, ha="left", label_dy=-1)
    legend(ax, 86, 13)
    pdf.savefig(fig)
    return fig


def page_arduino(pdf):
    fig = new_page("2. Arduino Uno - every pin",
                   "Firmware v2. Orange rows: wiring for parts still on order (steering, battery monitor).")
    rows = [[p, d] for p, d, _ in ARDUINO_PINS]
    kinds = [k for _, _, k in ARDUINO_PINS]
    table(fig, (0.04, 0.08, 0.6, 0.8), rows, ["Uno pin", "Goes to"], [0.16, 0.84], kinds, fontsize=8.6)
    notes = [
        ("Controller plug colours", ["Throttle: black = GND, orange = +5 V out (leave free),",
                                     "purple = signal.  F/R: black = GND, silver = signal",
                                     "(open = forward).  Brake: pull to GND = brake."]),
        ("Must-haves", ["Uno GND joined to BOTH controllers' throttle GND -",
                        "without it the throttle signal means nothing.",
                        "Battery negatives joined with a proper wire."]),
        ("Radio", ["SWA DOWN (no dual rate). CH5 low = MANUAL, high = AUTO.",
                   "Right stick back (< 1300 us) = STOP + brake in any mode.",
                   "No radio for 0.1 s or no laptop/Jetson for 0.3 s = stop."]),
        ("Recommended (cheap)", ["10 k from each purple throttle wire to GND, so a",
                                 "resetting Arduino reads as zero throttle.",
                                 "Kill switch on both controllers' power-lock wires."]),
    ]
    y = 0.86
    for title, lines in notes:
        fig.text(0.67, y, title, fontsize=10.5, weight="bold")
        for i, line in enumerate(lines):
            fig.text(0.67, y - 0.03 - 0.026 * i, line, fontsize=8.6, color="#424242")
        y -= 0.04 + 0.026 * len(lines) + 0.035
    pdf.savefig(fig)
    return fig


def page_usb(pdf):
    fig = new_page("3. Jetson - ports, network and software",
                   "What goes into which Jetson port, and what to check if something is missing.")
    table(fig, (0.04, 0.45, 0.92, 0.44), [list(r) for r in USB_PORTS],
          ["Device", "Where", "Notes"], [0.24, 0.28, 0.48], fontsize=9)
    lines = [
        ("Start a session (laptop)", "Double-click Navya Jetson.bat: finds the Jetson on the Wi-Fi, opens the menu on it,"
                                     " opens the dashboard when a drive starts."),
        ("Dashboard", "http://<jetson-ip>:8080 in the laptop's browser (the batch file opens it)."),
        ("Pre-flight", "Menu option 1 - checks Arduino, radio, camera + calibration, LiDAR, SSD, detection, network."),
        ("Code on the Jetson", "~/navya_autonomouscar, own Python in .venv (jetson/setup_jetson.sh); "
                               "object detection = TensorRT engine (export_models.py)."),
        ("Serial ports", "/dev/ttyUSB*: Arduino = CH340 (ch341 driver), LiDAR = CP2102 (cp210x). Found by USB ID."),
        ("If the SSD is missing", "Plug it in before switching on, or run: sudo mount /mnt/t7ssd"),
        ("If the camera is missing", "Plain cable straight into a Jetson port; unplug 10 s and re-plug; no docks or hubs."),
        ("If the Arduino is missing", "lsusb shows CH340 but no /dev/ttyUSB -> bash jetson/build_ch341.sh"),
    ]
    for i, (k, v) in enumerate(lines):
        y = 0.6 - 0.045 * i
        fig.text(0.04, y, k, fontsize=9, weight="bold")
        fig.text(0.24, y, v, fontsize=9, color="#424242")
    pdf.savefig(fig)
    return fig


def page_power(pdf):
    fig = new_page("4. Power - today, and the Jetson on the car (planned)",
                   "Jetson barrel jack accepts 9-20 V, max 4.2 A (19 V adapter supplied). A 6S LiPo gives 21-25.2 V.")
    ax = canvas(fig, rect=(0.04, 0.33, 0.92, 0.57), ylim=(0, 40))
    box(ax, 1, 24, 15, 12, "LiPo LEFT", ["6S 22.2 V", "21.0-25.2 V"], "power")
    box(ax, 1, 3, 15, 12, "LiPo RIGHT", ["6S 22.2 V", "21.0-25.2 V"], "power")
    box(ax, 24, 24, 15, 12, "YL-12 LEFT", ["cuts out at 21 V"], "drive")
    box(ax, 24, 3, 15, 12, "YL-12 RIGHT", ["cuts out at 21 V"], "drive")
    wire(ax, [(16.3, 30), (23.7, 30)], POWER, "+/-", label_dy=0.4)
    wire(ax, [(16.3, 9), (23.7, 9)], POWER, "+/-", label_dy=0.4)
    wire(ax, [(8.5, 23.7), (8.5, 15.3)], POWER, "negatives joined", ha="left", label_dy=-1)
    box(ax, 47, 24, 12, 12, "Fuse 5 A", ["inline blade", "on the + lead"], "planned", dashed=True)
    box(ax, 66, 24, 15, 12, "Step-down", ["IN 15-35 V", "OUT 12 V, >= 5 A", "non-isolated, common GND"], "planned", dashed=True)
    box(ax, 87, 24, 12, 12, "Jetson", ["barrel 5.5x2.5", "centre +", "~25 W + USB"], "compute")
    wire(ax, [(16.3, 33), (20, 33), (20, 38.5), (44, 38.5), (44, 31), (46.7, 31)], PLANNED, "+ from LEFT LiPo (Y-split at its XT60)", ls="--", label_dy=0.3)
    wire(ax, [(59.3, 30), (65.7, 30)], PLANNED, "+", ls="--", label_dy=0.4)
    wire(ax, [(81.3, 30), (86.7, 30)], PLANNED, "12 V", ls="--", label_dy=0.4)
    wire(ax, [(8.5, 21), (73.5, 21), (73.5, 23.7)], PLANNED, "- to the joined negatives (same point as Arduino GND)", ls="--", label_dy=0.3)
    box(ax, 47, 3, 22, 12, "Arduino Uno", ["powered by USB from the Jetson", "GND = joined battery negatives"], "control")
    wire(ax, [(69.3, 9), (93, 9), (93, 23.7)], USB, "USB", label_dy=0.4)
    rules = [
        "Why 12 V and not 19 V: a 19 V converter needs a few volts of headroom, which a 6S pack near empty (21 V) does not "
        "have. 12 V sits safely inside the Jetson's 9-20 V range at every battery voltage.",
        "Converter to buy: step-down (buck), input covering 21-26 V (e.g. 8-35 V), output 12 V fixed or adjustable, "
        "at least 5 A / 60 W. Set it to 12.0 V with a multimeter BEFORE connecting the Jetson.",
        "Fuse 5 A on the LiPo + lead to the converter. Barrel plug 5.5 x 2.5 mm, centre positive (check before plugging in).",
        "The LiPo keeps feeding the Jetson after the controllers cut out at 21 V: switch the Jetson off and unplug "
        "the converter after a session, or the pack is drained below 3 V per cell. The battery monitor (A4/A5) warns at 22.2 V.",
        "Power-on order: Jetson first (it powers the Arduino over USB), then the controllers - they refuse to start "
        "if they see throttle at power-on. Unplug all LiPos when the car is not being tested.",
    ]
    for i, text in enumerate(rules):
        y = 0.3 - 0.05 * i
        fig.text(0.04, y, f"{i + 1}.", fontsize=9, weight="bold", va="top")
        fig.text(0.06, y, textwrap.fill(text, 165), fontsize=8.7, color="#424242", va="top")
    pdf.savefig(fig)
    return fig


def page_photos(pdf):
    fig = new_page("5. On the car (stills from the walk-round video, 3 Nov 2026)",
                   "Replace with HD photos when convenient: docs/wiring/photos/, then run make_wiring_pdf.py again.")
    items = [
        ("overview.jpg", "Controllers and steering wheel", "Both YL-12 controllers behind the steering wheel, with their plugs."),
        ("camera_front.jpg", "RealSense camera (front)", "Front bonnet, centred, rigid bracket; 0.554 m high, 4.4 deg down. Toy steering motor below."),
        ("lidar_dashboard.jpg", "LiDAR (dashboard bar)", "Raised above the camera, level; CP2102 adapter next to it. 0.365 m behind the bumper, 0.10 m left."),
        ("jetson_ssd.jpg", "Jetson + SSD (footwell)", "Jetson Orin Nano with the Samsung T7; Arduino (top) on the blue USB cable."),
        ("arduino_receiver.jpg", "Arduino + receiver", "Uno with jumper wires to the FS-R6B receiver and the breadboard rails (GND / 5 V)."),
        ("controllers.jpg", "Controller harness", "YL-12 signal plugs (throttle, F/R, brake) and the joined grounds."),
    ]
    for i, (name, title, caption) in enumerate(items):
        col, row = i % 3, i // 3
        photo(fig, (0.04 + col * 0.315, 0.52 - row * 0.42, 0.29, 0.33), PHOTOS / name, title, caption)
    pdf.savefig(fig)
    return fig


def page_checklist(pdf):
    fig = new_page("6. Before every run", "Short version of the README bring-up. The car moves only with CH5 in AUTO.")
    steps = [
        ("Car", "Wheels up on blocks for the first test of the day. Camera and LiDAR not knocked (pre-flight checks the camera)."),
        ("Transmitter", "ON, SWA down, CH5 MANUAL, right stick centred. One person holds it the whole run."),
        ("Jetson", "SSD plugged in, then power on. Laptop and Jetson on the same Wi-Fi."),
        ("Laptop", "Double-click Navya Jetson.bat. Option 1 = pre-flight: everything OK?"),
        ("LiPos", "Connect the controllers' LiPos last (Arduino already running)."),
        ("Drive", "Option 2 (or 3 with detection + recording). Dashboard opens by itself. CH5 to AUTO."),
        ("Stop", "Right stick back = stop and brake, any mode. Q in the terminal ends the program."),
        ("After", "CH5 MANUAL, unplug the LiPos, switch the Jetson off. Trips are on the SSD (navya_trips)."),
    ]
    for i, (k, v) in enumerate(steps):
        y = 0.84 - 0.085 * i
        fig.add_artist(FancyBboxPatch((0.04, y - 0.03), 0.92, 0.065, boxstyle="round,pad=0.004,rounding_size=0.01",
                                      transform=fig.transFigure, fc="#fafafa", ec="#e0e0e0"))
        fig.text(0.055, y, f"{i + 1}", fontsize=16, weight="bold", color="#1565c0", va="center")
        fig.text(0.09, y, k, fontsize=11, weight="bold", va="center")
        fig.text(0.22, y, v, fontsize=10, color="#424242", va="center")
    pdf.savefig(fig)
    return fig


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--png", help="also write one PNG per page into this folder")
    args = parser.parse_args()
    plt.rcParams["font.family"] = "DejaVu Sans"
    with PdfPages(OUT) as pdf:
        figs = [page(pdf) for page in (page_overview, page_arduino, page_usb, page_power, page_photos, page_checklist)]
        info = pdf.infodict()
        info["Title"] = "Navya wiring"
        info["Author"] = "Navya project"
    if args.png:
        out = Path(args.png)
        out.mkdir(parents=True, exist_ok=True)
        for i, fig in enumerate(figs, 1):
            fig.savefig(out / f"page{i}.png", dpi=110)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
