#!/usr/bin/env python3
"""Validate docs/phase0/vehicle_params.yaml.

Checks, by field type:
  - required numbers are present and > 0
  - required strings are present and non-blank
  - redundant geometry fields agree with each other
Booleans and free-text notes are intentionally not constrained.
Exit 0 = all good, exit 1 = one or more problems (all printed).
"""

import sys
from pathlib import Path

import yaml

# Numbers that must exist and be strictly > 0.
REQUIRED_POSITIVE = [
    "wheelbase_left_cm",
    "wheelbase_right_cm",
    "wheelbase_m",
    "track_front_cm",
    "track_rear_cm",
    "rear_wheel_diameter_mm",
    "rear_wheel_radius_m",
    "rear_motor_count",
    "mass_kg",
    "front_drive_motors",
    "front_steer_motor",
    "total_motors",
    "poc_driven_motors",
]

# Strings that must exist and be non-blank.
REQUIRED_STRINGS = [
    "platform",
    "drive_type",
    "rear_wheel_type",
    "rear_motor",
    "rear_axle",
]

# How close two floats must be to count as "equal" (accounts for rounding).
TOL = 1e-6

PARAMS_PATH = (
    Path(__file__).resolve().parent.parent
    / "docs" / "phase0" / "vehicle_params.yaml"
)


def load_params(path):
    """Read YAML into a dict. Exit with a clear message if unreadable."""
    if not path.exists():
        print(f"ERROR: params file not found: {path}")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        print(f"ERROR: {path} did not parse into key/value pairs.")
        sys.exit(1)

    return data


def check_positive_numbers(params, problems):
    """Every REQUIRED_POSITIVE field must exist and be a number > 0."""
    for key in REQUIRED_POSITIVE:
        if key not in params:
            problems.append(f"missing number field: '{key}'")
            continue
        value = params[key]
        if value is None or value == "":
            problems.append(f"blank number field: '{key}'")
            continue
        # bool is a subclass of int in Python; reject it explicitly.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            problems.append(f"field '{key}' is not a number: {value!r}")
            continue
        if value <= 0:
            problems.append(f"field '{key}' must be > 0, got {value}")


def check_strings(params, problems):
    """Every REQUIRED_STRINGS field must exist and be non-blank text."""
    for key in REQUIRED_STRINGS:
        if key not in params:
            problems.append(f"missing string field: '{key}'")
            continue
        value = params[key]
        if not isinstance(value, str) or value.strip() == "":
            problems.append(f"blank/invalid string field: '{key}'")


def check_consistency(params, problems):
    """Redundant fields describing the same physical fact must agree."""
    # Left and right wheelbase should match, and both should match the
    # single wheelbase_m (after unit conversion cm -> m).
    l_cm = params.get("wheelbase_left_cm")
    r_cm = params.get("wheelbase_right_cm")
    wb_m = params.get("wheelbase_m")
    if _all_numbers(l_cm, r_cm, wb_m):
        if abs(l_cm - r_cm) > TOL:
            problems.append(
                f"wheelbase_left_cm ({l_cm}) != wheelbase_right_cm ({r_cm})"
            )
        avg_cm = (l_cm + r_cm) / 2.0
        if abs(avg_cm / 100.0 - wb_m) > TOL:
            problems.append(
                f"wheelbase_m ({wb_m}) disagrees with cm fields "
                f"(~{avg_cm/100.0:.3f} m)"
            )

    # Wheel diameter (mm) and radius (m) must describe the same wheel.
    dia_mm = params.get("rear_wheel_diameter_mm")
    rad_m = params.get("rear_wheel_radius_m")
    if _all_numbers(dia_mm, rad_m):
        # radius(m) = diameter(mm) / 1000 / 2
        expected_rad_m = dia_mm / 1000.0 / 2.0
        if abs(expected_rad_m - rad_m) > TOL:
            problems.append(
                f"rear_wheel_radius_m ({rad_m}) disagrees with "
                f"diameter {dia_mm}mm (expected {expected_rad_m} m)"
            )

    # Motor bookkeeping: rear + front drive + front steer must equal total.
    rear = params.get("rear_motor_count")
    fdrive = params.get("front_drive_motors")
    fsteer = params.get("front_steer_motor")
    total = params.get("total_motors")
    if _all_numbers(rear, fdrive, fsteer, total):
        if rear + fdrive + fsteer != total:
            problems.append(
                f"total_motors ({total}) != rear({rear}) + "
                f"front_drive({fdrive}) + front_steer({fsteer})"
            )

    # Only the rear motors are driven in the PoC.
    driven = params.get("poc_driven_motors")
    if _all_numbers(driven, rear) and driven != rear:
        problems.append(
            f"poc_driven_motors ({driven}) != rear_motor_count ({rear}); "
            f"PoC drives rear wheels only"
        )


def _all_numbers(*values):
    """True only if every value is a real (non-bool) number."""
    return all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in values
    )


def validate(params):
    """Run all checks, return a list of problems (empty == all good)."""
    problems = []
    check_positive_numbers(params, problems)
    check_strings(params, problems)
    check_consistency(params, problems)
    return problems


def main():
    params = load_params(PARAMS_PATH)
    problems = validate(params)

    if problems:
        print("VALIDATION FAILED:")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)

    n = len(REQUIRED_POSITIVE) + len(REQUIRED_STRINGS)
    print(f"VALIDATION PASSED: {n} required fields OK, consistency checks OK.")
    sys.exit(0)


if __name__ == "__main__":
    main()