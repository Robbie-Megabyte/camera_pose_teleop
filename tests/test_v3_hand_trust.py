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
)
from v3_fusion.hand_trust import (  # noqa: E402
    HandTrustConfig,
    HandTrustState,
    HandTrustTracker,
)


def rz(deg):
    a = np.deg2rad(
        deg
    )

    c = np.cos(a)
    s = np.sin(a)

    return np.array(
        [
            [c, -s, 0.0],
            [s,  c, 0.0],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )


def make_hand():
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


def obs(
    *,
    t,
    track=1,
    angle=0.0,
    detected=True,
    crop_valid=True,
    elbow_conf=0.9,
    wrist_conf=0.9,
):
    o = build_hand_observation(
        make_hand()
        if detected
        else None,
        "R",
        frame_id=int(t * 100),
        capture_timestamp=t,
        track_id=track,
        detected=detected,
        crop_valid=crop_valid,
        elbow_conf=elbow_conf,
        wrist_conf=wrist_conf,
    )

    if o.geometry_valid:
        o.R_hand = rz(
            angle
        )

        o.hand_lateral = (
            o.R_hand[:, 0].copy()
        )

        o.hand_forward = (
            o.R_hand[:, 1].copy()
        )

        o.palm_normal = (
            o.R_hand[:, 2].copy()
        )

    return o


cfg = HandTrustConfig(
    max_source_age_s=0.35,
    max_orientation_step_deg=60.0,
    reacquire_consecutive=3,
    suspect_recover_consecutive=2,
    suspect_bad_frames_to_lost=2,
)

tracker = HandTrustTracker(
    "R",
    cfg,
)


print("===== TEST V3 HAND TRUST =====")


print()
print("--- INITIAL REACQUIRE ---")

d1 = tracker.update(
    obs(
        t=1.00,
        angle=0,
    ),
    now_timestamp=1.05,
)

print(
    d1.state,
    d1.reason,
    d1.authority,
)

assert d1.state == HandTrustState.REACQUIRE
assert not d1.trusted


d2 = tracker.update(
    obs(
        t=1.10,
        angle=5,
    ),
    now_timestamp=1.15,
)

print(
    d2.state,
    d2.reason,
    d2.authority,
)

assert d2.state == HandTrustState.REACQUIRE


d3 = tracker.update(
    obs(
        t=1.20,
        angle=10,
    ),
    now_timestamp=1.25,
)

print(
    d3.state,
    d3.reason,
    d3.authority,
)

assert d3.state == HandTrustState.TRACKING
assert d3.trusted
assert d3.authority == 1.0

print("REACQUIRE=PASS")


print()
print("--- NORMAL TRACKING ---")

d4 = tracker.update(
    obs(
        t=1.30,
        angle=20,
    ),
    now_timestamp=1.35,
)

print(
    d4.state,
    d4.reason,
    d4.orientation_step_deg,
)

assert d4.state == HandTrustState.TRACKING
assert d4.trusted

print("TRACKING=PASS")


print()
print("--- LARGE ORIENTATION JUMP -> SUSPECT ---")

d5 = tracker.update(
    obs(
        t=1.40,
        angle=120,
    ),
    now_timestamp=1.45,
)

print(
    d5.state,
    d5.reason,
    d5.orientation_step_deg,
    d5.authority,
)

assert d5.state == HandTrustState.SUSPECT
assert not d5.trusted
assert d5.reason == "orientation_jump"

print("JUMP_SUSPECT=PASS")


print()
print("--- RECOVER FROM SUSPECT ---")

d6 = tracker.update(
    obs(
        t=1.50,
        angle=25,
    ),
    now_timestamp=1.55,
)

print(
    d6.state,
    d6.reason,
)

assert d6.state == HandTrustState.SUSPECT
assert not d6.trusted


d7 = tracker.update(
    obs(
        t=1.60,
        angle=30,
    ),
    now_timestamp=1.65,
)

print(
    d7.state,
    d7.reason,
)

assert d7.state == HandTrustState.TRACKING
assert d7.trusted

print("SUSPECT_RECOVERY=PASS")


print()
print("--- OCCLUSION / LOSS ---")

d8 = tracker.update(
    obs(
        t=1.70,
        detected=False,
        crop_valid=False,
    ),
    now_timestamp=1.75,
)

print(
    d8.state,
    d8.reason,
    d8.authority,
)

assert d8.state == HandTrustState.SUSPECT


d9 = tracker.update(
    obs(
        t=1.80,
        detected=False,
        crop_valid=False,
    ),
    now_timestamp=1.85,
)

print(
    d9.state,
    d9.reason,
    d9.authority,
)

assert d9.state == HandTrustState.LOST
assert d9.authority == 0.0

print("LOSS=PASS")


print()
print("--- REACQUIRE AFTER LOSS ---")

for idx, angle in enumerate(
    [
        35,
        37,
        39,
    ]
):
    t = 2.00 + 0.10 * idx

    d = tracker.update(
        obs(
            t=t,
            angle=angle,
        ),
        now_timestamp=t + 0.05,
    )

    print(
        idx + 1,
        d.state,
        d.reason,
    )

assert d.state == HandTrustState.TRACKING
assert d.trusted

print("REACQUIRE_AFTER_LOSS=PASS")


print()
print("--- TRACK CHANGE MUST RESET AUTHORITY ---")

d10 = tracker.update(
    obs(
        t=2.40,
        track=99,
        angle=40,
    ),
    now_timestamp=2.45,
)

print(
    d10.state,
    d10.reason,
    "track_changed=",
    d10.track_changed,
    "authority=",
    d10.authority,
)

assert d10.track_changed
assert d10.state == HandTrustState.REACQUIRE
assert not d10.trusted
assert d10.authority == 0.0

print("TRACK_CHANGE=PASS")


print()
print("--- STALE RESULT ---")

tracker.reset()

# Reacquire first.
for i in range(3):
    t = 3.0 + 0.1 * i

    tracker.update(
        obs(
            t=t,
            angle=i * 2,
        ),
        now_timestamp=t + 0.05,
    )

d_stale = tracker.update(
    obs(
        t=3.30,
        angle=8,
    ),
    now_timestamp=4.00,
)

print(
    d_stale.state,
    d_stale.reason,
    "age=",
    d_stale.source_age_s,
)

assert d_stale.state == HandTrustState.SUSPECT
assert d_stale.reason == "stale"

print("STALE=PASS")


print()
print("--- LOW VITPOSE WRIST CONFIDENCE ---")

tracker.reset()

d_low = tracker.update(
    obs(
        t=5.0,
        wrist_conf=0.10,
    ),
    now_timestamp=5.05,
)

print(
    d_low.state,
    d_low.reason,
)

assert d_low.state == HandTrustState.LOST
assert d_low.reason == "low_wrist_conf"

print("LOW_CONF=PASS")


print()
print("===== ALL TRUST TESTS PASS =====")
