#!/usr/bin/env python3

from __future__ import annotations

import math

import numpy as np

from neutral_alignment import (
    NeutralAlignmentError,
    NeutralGravityEstimator,
)


def rx(deg):
    a = math.radians(deg)
    c = math.cos(a)
    s = math.sin(a)

    return np.asarray(
        [
            [1.0, 0.0, 0.0],
            [0.0, c, -s],
            [0.0, s, c],
        ],
        dtype=np.float64,
    )


def ry(deg):
    a = math.radians(deg)
    c = math.cos(a)
    s = math.sin(a)

    return np.asarray(
        [
            [c, 0.0, s],
            [0.0, 1.0, 0.0],
            [-s, 0.0, c],
        ],
        dtype=np.float64,
    )


def rz(deg):
    a = math.radians(deg)
    c = math.cos(a)
    s = math.sin(a)

    return np.asarray(
        [
            [c, -s, 0.0],
            [s, c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def unit(v):
    v = np.asarray(
        v,
        dtype=np.float64,
    )

    return (
        v
        / np.linalg.norm(v)
    )


def angle_deg(a, b):
    a = unit(a)
    b = unit(b)

    return math.degrees(
        math.acos(
            float(
                np.clip(
                    np.dot(a, b),
                    -1.0,
                    1.0,
                )
            )
        )
    )


def neutral_smpl24():
    joints = np.zeros(
        (24, 3),
        dtype=np.float64,
    )

    joints[0] = [0.0, 0.0, 0.0]

    joints[1] = [-0.12, 0.0, 0.0]
    joints[2] = [0.12, 0.0, 0.0]

    joints[3] = [0.0, 0.15, 0.0]
    joints[6] = [0.0, 0.30, 0.0]
    joints[9] = [0.0, 0.45, 0.0]

    joints[12] = [0.0, 0.60, 0.0]

    joints[16] = [-0.22, 0.52, 0.0]
    joints[17] = [0.22, 0.52, 0.0]

    return joints


def transform(
    joints,
    R,
    translation,
):
    return (
        joints
        @ R.T
        + np.asarray(
            translation,
            dtype=np.float64,
        )
    )


print(
    "===== SYNTHETIC NEUTRAL ALIGNMENT ====="
)

base = neutral_smpl24()

# Arbitrary camera-relative orientation containing
# roll, pitch and yaw components.
R_camera = (
    rz(18.0)
    @ ry(-35.0)
    @ rx(22.0)
)

expected_up = (
    R_camera
    @ np.asarray(
        [0.0, 1.0, 0.0],
        dtype=np.float64,
    )
)

estimator = NeutralGravityEstimator(
    min_frames=20,
)

rng = np.random.default_rng(
    12345
)

# 40 good frames with small 3-D joint noise and
# deliberately changing translation. Translation must
# have no effect on the estimated gravity direction.
for i in range(40):
    translation = np.asarray(
        [
            0.4 + 0.01 * i,
            -0.3 + 0.002 * i,
            2.0 - 0.003 * i,
        ],
        dtype=np.float64,
    )

    joints = transform(
        base,
        R_camera,
        translation,
    )

    joints += rng.normal(
        0.0,
        0.003,
        size=joints.shape,
    )

    assert estimator.add_frame(
        joints
    )


# Add eight coherent but grossly wrong temporal frames.
# Their internal anatomy is valid, so temporal robust
# aggregation must reject them rather than the per-frame
# checks.
R_outlier = (
    rx(28.0)
    @ R_camera
)

for i in range(8):
    joints = transform(
        base,
        R_outlier,
        [
            0.8,
            -0.2,
            1.9,
        ],
    )

    joints += rng.normal(
        0.0,
        0.003,
        size=joints.shape,
    )

    assert estimator.add_frame(
        joints
    )


# One invalid frame must be rejected immediately.
bad = transform(
    base,
    R_camera,
    [0.0, 0.0, 2.0],
)

bad[12, 1] = np.nan

assert not estimator.add_frame(
    bad
)


result = estimator.estimate()

error = angle_deg(
    result.gravity_up_camera,
    expected_up,
)

print(
    "expected gravity_up_camera:",
    expected_up,
)

print(
    "estimated gravity_up_camera:",
    result.gravity_up_camera,
)

print(
    "angular error deg:",
    error,
)

print(
    "total frames:",
    result.total_frames,
)

print(
    "candidate frames:",
    result.candidate_frames,
)

print(
    "accepted frames:",
    result.accepted_frames,
)

print(
    "rejected frames:",
    result.rejected_frames,
)

print(
    "median residual deg:",
    result.median_residual_deg,
)

print(
    "95pct spread deg:",
    result.angular_spread_deg,
)

print(
    "inlier ratio:",
    result.inlier_ratio,
)

print(
    "confidence:",
    result.confidence,
)

print(
    "frame rejection reasons:",
    estimator.rejection_reasons,
)

assert error < 1.0

assert (
    result.accepted_frames
    == 40
)

assert (
    result.total_frames
    == 49
)

assert (
    result.rejected_frames
    == 9
)

assert (
    result.angular_spread_deg
    < 2.0
)

assert (
    result.confidence
    > 0.70
)

print(
    "ROTATION_TRANSLATION_OUTLIER_TEST=PASS"
)


print()
print(
    "===== INSUFFICIENT-DATA TEST ====="
)

short = NeutralGravityEstimator(
    min_frames=20,
)

for _ in range(3):
    assert short.add_frame(
        base
    )

try:
    short.estimate()
except NeutralAlignmentError as exc:
    print(
        "insufficient data: REJECTED",
        f"({exc})",
    )
else:
    raise AssertionError(
        "Insufficient neutral sequence "
        "was accepted"
    )

print(
    "INSUFFICIENT_DATA_TEST=PASS"
)


print()
print(
    "===== DEGENERATE-BODY TEST ====="
)

degenerate = (
    NeutralGravityEstimator(
        min_frames=1,
    )
)

assert not degenerate.add_frame(
    np.zeros(
        (24, 3),
        dtype=np.float64,
    )
)

print(
    "degenerate body: REJECTED",
    degenerate.rejection_reasons,
)

print(
    "DEGENERATE_BODY_TEST=PASS"
)


print()
print(
    "===== RESULT ====="
)

print(
    "NEUTRAL_ALIGNMENT_SYNTHETIC_TESTS=PASS"
)
