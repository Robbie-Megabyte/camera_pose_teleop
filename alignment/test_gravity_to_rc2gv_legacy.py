#!/usr/bin/env python3

from pathlib import Path

import numpy as np

from neutral_alignment import (
    NeutralAlignmentError,
    gravity_up_camera_to_R_c2gv,
)


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

GRAVITY = (
    ROOT
    / "calibration/legacy_fixed/"
      "stereo_gravity_1280x720.npz"
)

REFERENCE = (
    ROOT
    / "calibration/reference/"
      "F_LEFT_HMR2_CALIBRATED_ROOT.npz"
)


print(
    "===== LEGACY GRAVITY -> V2 R_C2GV ====="
)

with np.load(
    GRAVITY,
    allow_pickle=False,
) as g:
    gravity_up = np.asarray(
        g["gravity_up_left"],
        dtype=np.float32,
    )


with np.load(
    REFERENCE,
    allow_pickle=False,
) as z:
    R_ref = np.asarray(
        z["R_c2gv"],
        dtype=np.float32,
    )


R_v2 = (
    gravity_up_camera_to_R_c2gv(
        gravity_up
    )
)

error = float(
    np.max(
        np.abs(
            R_v2
            - R_ref
        )
    )
)

print(
    "gravity_up_camera:"
)
print(
    gravity_up
)

print()
print(
    "V2 R_c2gv:"
)
print(
    R_v2
)

print()
print(
    "protected V1 R_c2gv:"
)
print(
    R_ref
)

print()
print(
    "max error:",
    error,
)

print(
    "det:",
    np.linalg.det(
        R_v2.astype(
            np.float64
        )
    ),
)

print(
    "orthogonality max error:",
    np.max(
        np.abs(
            R_v2.T
            @ R_v2
            - np.eye(
                3,
                dtype=np.float32,
            )
        )
    ),
)

assert error == 0.0

print(
    "LEGACY_R_C2GV_BIT_EXACT=PASS"
)


print()
print(
    "===== INPUT VALIDATION ====="
)

bad_inputs = (
    np.array(
        [0.0, 1.0],
        dtype=np.float32,
    ),
    np.array(
        [0.0, np.nan, 0.0],
        dtype=np.float32,
    ),
    np.array(
        [0.0, 0.0, 0.0],
        dtype=np.float32,
    ),
    np.array(
        [0.0, -2.0, 0.0],
        dtype=np.float32,
    ),
)

for bad in bad_inputs:
    try:
        gravity_up_camera_to_R_c2gv(
            bad
        )
    except NeutralAlignmentError as exc:
        print(
            "REJECTED:",
            repr(bad),
            f"({exc})",
        )
    else:
        raise AssertionError(
            "Invalid gravity input accepted"
        )

print(
    "GRAVITY_TRANSFORM_VALIDATION=PASS"
)


print()
print(
    "===== RESULT ====="
)

print(
    "GRAVITY_TO_R_C2GV_TESTS=PASS"
)
