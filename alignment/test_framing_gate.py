#!/usr/bin/env python3

from __future__ import annotations

import numpy as np

from framing_gate import (
    FullBodyFramingGate,
    evaluate_full_body_framing,
)


def make_pose(
    width=1280,
    height=720,
):
    """
    Synthetic neutral COCO-17 skeleton in normalized image
    coordinates. Confidence 0.95 everywhere.
    """

    normalized = np.asarray(
        [
            [0.50, 0.12],  # 0 nose
            [0.48, 0.11],  # 1 left eye
            [0.52, 0.11],  # 2 right eye
            [0.46, 0.12],  # 3 left ear
            [0.54, 0.12],  # 4 right ear

            [0.43, 0.27],  # 5 left shoulder
            [0.57, 0.27],  # 6 right shoulder

            [0.39, 0.43],  # 7 left elbow
            [0.61, 0.43],  # 8 right elbow

            [0.40, 0.58],  # 9 left wrist
            [0.60, 0.58],  # 10 right wrist

            [0.46, 0.52],  # 11 left hip
            [0.54, 0.52],  # 12 right hip

            [0.46, 0.70],  # 13 left knee
            [0.54, 0.70],  # 14 right knee

            [0.46, 0.90],  # 15 left ankle
            [0.54, 0.90],  # 16 right ankle
        ],
        dtype=np.float32,
    )

    kp = np.zeros(
        (17, 3),
        dtype=np.float32,
    )

    kp[:, 0] = (
        normalized[:, 0]
        * width
    )

    kp[:, 1] = (
        normalized[:, 1]
        * height
    )

    kp[:, 2] = 0.95

    return kp


print(
    "===== GOOD FULL BODY ====="
)

good = make_pose()

result = evaluate_full_body_framing(
    good,
    image_width=1280,
    image_height=720,
)

assert result.frame_ok
assert result.head_visible
assert result.shoulders_visible
assert result.hips_visible
assert result.knees_visible
assert result.ankles_visible
assert result.margins_ok

print(
    "FRAMING_GOOD_FULL_BODY=PASS"
)


print()
print(
    "===== CONSECUTIVE STARTUP GATE ====="
)

gate = FullBodyFramingGate(
    image_width=1280,
    image_height=720,
    consecutive_good_frames=8,
)

for index in range(7):
    status = gate.observe(
        good
    )

    assert status.frame_ok
    assert not status.ready
    assert (
        status.good_streak
        == index + 1
    )

status = gate.observe(
    good
)

assert status.ready
assert status.good_streak == 8

print(
    "FRAMING_CONSECUTIVE_GATE=PASS"
)


print()
print(
    "===== BAD FRAME RESETS STREAK ====="
)

gate = FullBodyFramingGate(
    image_width=1280,
    image_height=720,
    consecutive_good_frames=4,
)

for _ in range(3):
    gate.observe(
        good
    )

bad = good.copy()

bad[
    15,
    2,
] = 0.1

status = gate.observe(
    bad
)

assert not status.frame_ok
assert not status.ready
assert status.good_streak == 0

status = gate.observe(
    good
)

assert status.good_streak == 1
assert not status.ready

print(
    "FRAMING_BAD_FRAME_RESETS=PASS"
)


print()
print(
    "===== CROPPED ANKLES REJECTED ====="
)

cropped = good.copy()

cropped[
    [15, 16],
    2,
] = 0.1

result = evaluate_full_body_framing(
    cropped,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok
assert not result.ankles_visible
assert "ankles" in result.reason.lower()

print(
    "FRAMING_CROPPED_ANKLES_REJECTED=PASS"
)


print()
print(
    "===== BOTTOM EDGE REJECTED ====="
)

bottom = good.copy()

bottom[
    [15, 16],
    1,
] = 0.985 * 720

result = evaluate_full_body_framing(
    bottom,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok
assert "bottom" in result.reason.lower()

print(
    "FRAMING_BOTTOM_EDGE_REJECTED=PASS"
)


print()
print(
    "===== TOP EDGE REJECTED ====="
)

top = good.copy()

top[
    [0, 1, 2, 3, 4],
    1,
] = 0.01 * 720

result = evaluate_full_body_framing(
    top,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok
assert "top" in result.reason.lower()

print(
    "FRAMING_TOP_EDGE_REJECTED=PASS"
)


print()
print(
    "===== SIDE EDGE REJECTED ====="
)

side = good.copy()

side[
    5,
    0,
] = 0.01 * 1280

result = evaluate_full_body_framing(
    side,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok
assert "left" in result.reason.lower()

print(
    "FRAMING_SIDE_EDGE_REJECTED=PASS"
)


print()
print(
    "===== LOW-CONFIDENCE KNEE REJECTED ====="
)

low_conf = good.copy()

low_conf[
    13,
    2,
] = 0.49

result = evaluate_full_body_framing(
    low_conf,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok
assert not result.knees_visible

print(
    "FRAMING_LOW_CONFIDENCE_REJECTED=PASS"
)


print()
print(
    "===== RESOLUTION INDEPENDENCE ====="
)

good_720 = make_pose(
    1280,
    720,
)

good_480 = make_pose(
    640,
    480,
)

a = evaluate_full_body_framing(
    good_720,
    image_width=1280,
    image_height=720,
)

b = evaluate_full_body_framing(
    good_480,
    image_width=640,
    image_height=480,
)

assert a.frame_ok
assert b.frame_ok

print(
    "FRAMING_RESOLUTION_INDEPENDENT=PASS"
)


print()
print(
    "===== INVALID SHAPE REJECTED ====="
)

invalid = np.zeros(
    (24, 3),
    dtype=np.float32,
)

result = evaluate_full_body_framing(
    invalid,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok

print(
    "FRAMING_INVALID_SHAPE_REJECTED=PASS"
)


print()
print(
    "===== NONFINITE REQUIRED JOINT REJECTED ====="
)

nonfinite = good.copy()

nonfinite[
    15,
    0,
] = np.nan

result = evaluate_full_body_framing(
    nonfinite,
    image_width=1280,
    image_height=720,
)

assert not result.frame_ok
assert not result.ankles_visible

print(
    "FRAMING_NONFINITE_REJECTED=PASS"
)


print()
print(
    "===== RESULT ====="
)

print(
    "FULL_BODY_FRAMING_GATE_TESTS=PASS"
)
