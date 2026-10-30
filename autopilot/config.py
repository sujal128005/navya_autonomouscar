"""Navya autopilot settings. Every laptop script reads this file.

Distances are metres. Speeds are 0..1000, a share of the Arduino's
PWM_START..PWM_MAX throttle range (see firmware/navya_drive/navya_drive.ino).
"""

# --- Arduino link ---
SERIAL_PORT = None          # e.g. "COM5"; None = auto-detect the Uno
SERIAL_BAUD = 115200

# --- RealSense depth stream ---
DEPTH_WIDTH = 640
DEPTH_HEIGHT = 480
DEPTH_FPS = 30
DEPTH_STRIDE = 2            # use every 2nd pixel each way; plenty for this job

# --- Camera mounting (python calibrate_camera.py --write fills the first two) ---
CAMERA_HEIGHT_M = 0.559      # lens centre above the floor
CAMERA_PITCH_DEG = 14.6      # positive = tilted down
CAMERA_LATERAL_OFFSET_M = 0.0   # positive = camera right of the car's centre line
CAMERA_SETBACK_M = 0.0      # lens behind the front bumper; subtracted from distances

# --- Driving corridor: only points inside this box count as obstacles ---
CORRIDOR_HALF_WIDTH_M = 0.45    # car is ~0.62 m wide; half-width plus a 0.14 m margin
FLOOR_CLEARANCE_M = 0.15       # ignore anything lower (the floor itself, tape, cables)
MAX_OBSTACLE_HEIGHT_M = 1.6     # ignore anything higher (ceiling, overhead lights)
DETECT_MIN_M = 0.2
DETECT_MAX_M = 4.5
OBSTACLE_PERCENTILE = 5         # nearest 5% of corridor points sets the distance
MIN_OBSTACLE_POINTS = 800      # fewer points than this = sensor noise, not an obstacle

# The D435i cannot see closer than ~0.3 m: those pixels read 0. If most of the
# centre of the image has no depth, something is right in front of the lens.
# Shiny floors can also read as "no depth"; set 1.01 to switch this check off.
BLIND_CHECK_FRACTION = 0.6

# --- Speed plan ---
CRUISE_SPEED = 130
CREEP_SPEED = 80            # slowest moving speed while closing in on an obstacle
SLOW_DOWN_DIST_M = 3.8      # start slowing down when an obstacle is this close
STOP_DIST_M = 2.0           # stop here; the car coasts ~0.9 m more (first ground run)
RESUME_DIST_M = 2.4         # path counts as clear again beyond this distance...
RESUME_DELAY_S = 1.5        # ...for this long, then the car moves off again
DISTANCE_HISTORY = 3        # use the nearest reading of the last N frames

# --- Straight-line trim: positive = right wheel faster. Car veers right -> raise it.
TRIM = 0.0

# --- Corridor viewer and lane finder (python corridor_view.py) ---
# The lane is the floor between two black tile strips, one each side of the car.
VIEW_FPS = 15               # depth + colour together; 15 is safe even on USB 2
VIEW_POINT_STRIDE = 3       # 3D view draws every 3rd pixel each way
BEV_RES_M = 0.02            # bird's-eye floor map: 2 cm per cell
BEV_HALF_WIDTH_M = 2.0      # map covers 2 m either side of the car...
BEV_MIN_FORWARD_M = 0.5     # ...from 0.5 m...
BEV_MAX_FORWARD_M = 6.0     # ...to 6 m ahead
LANE_DARK_MAX = 70          # a floor cell is black tile if darker than this (0-255)...
LANE_DARK_RATIO = 0.5       # ...and darker than this share of the floor's median brightness
LANE_MIN_WIDTH_M = 0.05     # ignore dark bits narrower than this (grout lines, cables)
LANE_MAX_FORWARD_M = 4.0    # fit the strips only up to here; tiles further away are blurry
LANE_MIN_SAMPLES = 8        # rows of a strip needed before it counts as found
