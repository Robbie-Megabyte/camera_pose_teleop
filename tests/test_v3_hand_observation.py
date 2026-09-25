#!/usr/bin/env python3

import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT),
)


from v3_fusion.hand_observation import (  # noqa: E402
    build_hand_observation,
    palm_frame,
)


def make_right_hand():
    """
    Synthetic canonical flat hand.

    Expected:
        X = +world X
        Y = +world Y
        Z = +world Z
    """
    J = np.zeros(
        (21, 3),
        dtype=np.float64,
    )

    J[0] = [0.0, 0.0, 0.0]

    J[5] = [0.40, 1.00, 0.0]
    J[9] = [0.12, 1.05, 0.0]
    J[13] = [-0.12, 1.05, 0.0]
    J[17] = [-0.40, 1.00, 0.0]

    return J


print("===== TEST V3 HAND OBSERVATION =====")

R_expected = np.eye(3)


print()
print("--- RIGHT HAND ---")

right = make_right_hand()

Rr = palm_frame(
    right,
    "R",
)

print("R_right =")
print(Rr)

assert Rr is not None
assert np.allclose(
    Rr,
    R_expected,
    atol=1e-8,
)

obs_r = build_hand_observation(
    right,
    "R",
    frame_id=123,
    capture_timestamp=10.5,
    track_id=7,
    detected=True,
    det_conf=0.9,
    crop_valid=True,
)

assert obs_r.geometry_valid
assert obs_r.invalid_reason == ""
assert abs(obs_r.determinant - 1.0) < 1e-8
assert obs_r.orthogonality_error < 1e-8

print("RIGHT=PASS")


print()
print("--- LEFT HAND HANDEDNESS NORMALIZATION ---")

# Construct the raw WiLoR-style left equivalent:
# mirror the canonical hand in X.
left_raw = right.copy()
left_raw[:, 0] *= -1.0

Rl = palm_frame(
    left_raw,
    "L",
)

print("R_left =")
print(Rl)

assert Rl is not None
assert np.allclose(
    Rl,
    R_expected,
    atol=1e-8,
)

obs_l = build_hand_observation(
    left_raw,
    "L",
    frame_id=123,
    detected=True,
    crop_valid=True,
)

assert obs_l.geometry_valid

print("LEFT=PASS")


print()
print("--- DEGENERATE HAND ---")

bad = np.zeros(
    (21, 3),
    dtype=np.float64,
)

obs_bad = build_hand_observation(
    bad,
    "R",
)

print(
    "geometry_valid =",
    obs_bad.geometry_valid,
)

print(
    "invalid_reason =",
    obs_bad.invalid_reason,
)

assert not obs_bad.geometry_valid
assert obs_bad.invalid_reason == "degenerate_palm_geometry"

print("DEGENERATE=PASS")


print()
print("--- OCCLUDED / NOT DETECTED ---")

obs_missing = build_hand_observation(
    None,
    "L",
    detected=False,
    crop_valid=False,
)

print(
    "geometry_valid =",
    obs_missing.geometry_valid,
)

print(
    "invalid_reason =",
    obs_missing.invalid_reason,
)

assert not obs_missing.geometry_valid
assert obs_missing.invalid_reason == "not_detected"

print("NOT_DETECTED=PASS")


print()
print("===== ALL TESTS PASS =====")
