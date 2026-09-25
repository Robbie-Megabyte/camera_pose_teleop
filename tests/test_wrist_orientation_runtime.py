#!/usr/bin/env python3

import math
import sys
from pathlib import Path

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT),
)

from v3_fusion.wrist_orientation_runtime import (
    LEFT_BILATERAL_CANONICAL,
    Q4WristOrientationRuntime,
    TimestampSO3Filter,
    build_anatomical_calibration,
    project_so3,
    rotvec_deg,
    rotation_distance_deg,
    wrist_rotation_from_frames,
)


def Rx(deg):
    a = math.radians(
        deg
    )

    c = math.cos(a)
    s = math.sin(a)

    return np.array(
        [
            [1, 0, 0],
            [0, c, -s],
            [0, s, c],
        ],
        dtype=np.float64,
    )


def Ry(deg):
    a = math.radians(
        deg
    )

    c = math.cos(a)
    s = math.sin(a)

    return np.array(
        [
            [c, 0, s],
            [0, 1, 0],
            [-s, 0, c],
        ],
        dtype=np.float64,
    )


def Rz(deg):
    a = math.radians(
        deg
    )

    c = math.cos(a)
    s = math.sin(a)

    return np.array(
        [
            [c, -s, 0],
            [s, c, 0],
            [0, 0, 1],
        ],
        dtype=np.float64,
    )


def check(
    condition,
    name,
):
    if not condition:
        raise RuntimeError(
            f"FAIL: {name}"
        )

    print(
        "PASS:",
        name,
    )


print(
    "===== Q4 RUNTIME MODULE TESTS ====="
)


# ------------------------------------------------------------
# 1. Timestamp response.
# ------------------------------------------------------------

f = TimestampSO3Filter(
    alpha_ref=0.40,
    reference_dt_s=0.100,
    reset_gap_s=0.400,
)

alpha = f.alpha_for_dt(
    0.100
)

check(
    abs(
        alpha - 0.40
    )
    < 1e-12,
    "timestamp alpha is exactly 0.40 at 100 ms",
)


# ------------------------------------------------------------
# 2. Explicit reference must produce identity.
# ------------------------------------------------------------

F0 = np.eye(
    3,
    dtype=np.float64,
)

# A reference hand orientation that is not numerically identical
# to the forearm frame, so calibration is actually exercised.
H0 = project_so3(
    Rz(18.0)
    @ Ry(-12.0)
    @ Rx(9.0)
)

cal = (
    build_anatomical_calibration(
        F0,
        H0,
    )
)

ref = (
    wrist_rotation_from_frames(
        F0,
        H0,
        cal,
        "R",
    )
)

check(
    ref[
        "relative_angle_deg"
    ]
    < 1e-8,
    "explicit reference outputs identity",
)


# ------------------------------------------------------------
# 3. Common camera/global rotation invariance.
#
# Rotate BOTH forearm and hand in camera coordinates.
# Wrist articulation must remain zero.
# ------------------------------------------------------------

G = project_so3(
    Rz(37.0)
    @ Ry(21.0)
    @ Rx(-14.0)
)

common = (
    wrist_rotation_from_frames(
        G @ F0,
        G @ H0,
        cal,
        "R",
    )
)

check(
    common[
        "relative_angle_deg"
    ]
    < 1e-8,
    "common global/body rotation cancels",
)


# ------------------------------------------------------------
# 4. Bilateral convention.
#
# Conjugation by S=diag(+1,-1,-1):
# - keeps X-axis rotation sign;
# - reverses Y;
# - reverses Z.
# ------------------------------------------------------------

S = (
    LEFT_BILATERAL_CANONICAL
)

check(
    np.allclose(
        S.T @ Rx(25.0) @ S,
        Rx(25.0),
        atol=1e-10,
    ),
    "left canonicalization preserves axial X sign",
)

check(
    np.allclose(
        S.T @ Ry(25.0) @ S,
        Ry(-25.0),
        atol=1e-10,
    ),
    "left canonicalization reverses Y bending sign",
)

check(
    np.allclose(
        S.T @ Rz(25.0) @ S,
        Rz(-25.0),
        atol=1e-10,
    ),
    "left canonicalization reverses Z bending sign",
)


# ------------------------------------------------------------
# 5. Stateful runtime calibration.
# ------------------------------------------------------------

runtime = (
    Q4WristOrientationRuntime(
        alpha_ref=0.40,
        reference_dt_s=0.100,
        reset_gap_s=0.400,
    )
)

# Non-straight arm.
shoulder = np.array(
    [-0.25, 0.15, 0.10],
    dtype=np.float64,
)

elbow = np.array(
    [0.00, 0.00, 0.00],
    dtype=np.float64,
)

wrist = np.array(
    [0.65, 0.10, -0.04],
    dtype=np.float64,
)

for side in (
    "L",
    "R",
):
    first = runtime.observe(
        side,
        1.000,
        shoulder,
        elbow,
        wrist,
        H0,
    )

    check(
        first[
            "valid"
        ],
        f"{side} first observation valid",
    )

    check(
        not first[
            "calibrated"
        ],
        f"{side} does not auto-calibrate",
    )


both = (
    runtime.calibrate_both(
        max_pair_age_s=0.200
    )
)

check(
    runtime.is_calibrated(),
    "explicit bilateral calibration succeeds",
)

check(
    both[
        "pair_age_s"
    ]
    < 1e-12,
    "bilateral calibration uses paired timestamps",
)


for side in (
    "L",
    "R",
):
    out = runtime.observe(
        side,
        1.100,
        shoulder,
        elbow,
        wrist,
        H0,
    )

    check(
        out[
            "calibrated"
        ],
        f"{side} remains explicitly calibrated",
    )

    check(
        out[
            "relative_angle_deg"
        ]
        < 1e-8,
        f"{side} unchanged pose remains zero",
    )


print()
print(
    "Q4_RUNTIME_MODULE_TEST=PASS"
)
