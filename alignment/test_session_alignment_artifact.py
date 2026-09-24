#!/usr/bin/env python3

from __future__ import annotations

import json
import math
from pathlib import Path
import tempfile

import numpy as np

from neutral_alignment import (
    NeutralGravityEstimator,
    gravity_up_camera_to_R_c2gv,
)

from session_alignment_artifact import (
    write_session_alignment,
)

from sonic_smpl_bridge import (
    SonicCalibrationProfile,
    load_session_R_c2gv,
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


def neutral_body():
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


print(
    "===== BUILD SYNTHETIC ESTIMATE ====="
)

base = neutral_body()

R = (
    rz(11.0)
    @ rx(-17.0)
)

estimator = NeutralGravityEstimator(
    min_frames=20,
)

rng = np.random.default_rng(
    20260828
)

for i in range(30):
    joints = (
        base
        @ R.T
        + np.array(
            [
                0.2 + 0.005 * i,
                -0.4,
                2.2,
            ]
        )
    )

    joints += rng.normal(
        0.0,
        0.002,
        size=joints.shape,
    )

    assert estimator.add_frame(
        joints
    )

estimate = estimator.estimate()

print(
    "gravity_up_camera:",
    estimate.gravity_up_camera,
)

print(
    "accepted:",
    estimate.accepted_frames,
)

print(
    "spread:",
    estimate.angular_spread_deg,
)

print(
    "confidence:",
    estimate.confidence,
)


print()
print(
    "===== BUILD GENERIC GVHMR K ====="
)

width = 1280
height = 720

focal = math.sqrt(
    width * width
    + height * height
)

K = np.asarray(
    [
        [
            focal,
            0.0,
            width / 2.0,
        ],
        [
            0.0,
            focal,
            height / 2.0,
        ],
        [
            0.0,
            0.0,
            1.0,
        ],
    ],
    dtype=np.float32,
)

print(K)


print()
print(
    "===== WRITE SESSION ARTIFACT ====="
)

with tempfile.TemporaryDirectory(
    prefix="camera_pose_artifact_"
) as td:

    td = Path(td)

    npz_path = (
        td
        / "session_alignment.npz"
    )

    json_path = (
        td
        / "session_alignment.json"
    )

    written = write_session_alignment(
        npz_path=npz_path,
        json_path=json_path,
        estimate=estimate,
        image_width=width,
        image_height=height,
        K_fullimg=K,
        intrinsics_source=(
            "gvhmr_estimate_K"
        ),
        smoothing_history_weight=0.0,
    )

    assert npz_path.exists()
    assert json_path.exists()

    print(
        "NPZ:",
        npz_path,
    )

    print(
        "JSON:",
        json_path,
    )


    print()
    print(
        "===== NPZ CONTRACT ====="
    )

    with np.load(
        npz_path,
        allow_pickle=False,
    ) as z:

        print(
            "keys:",
            sorted(z.files),
        )

        assert int(
            z["format_version"]
        ) == 1

        assert str(
            z["alignment_mode"]
        ) == "session_v2"

        assert str(
            z["alignment_method"]
        ) == "neutral_smpl24_v1"

        assert np.array_equal(
            z["image_size"],
            np.array(
                [1280, 720],
                dtype=np.int64,
            ),
        )

        assert np.array_equal(
            z["K_fullimg"],
            K,
        )

        R_npz = np.asarray(
            z["R_c2gv"],
            dtype=np.float32,
        )

        up_npz = np.asarray(
            z["gravity_up_camera"],
            dtype=np.float32,
        )


    expected_R = (
        gravity_up_camera_to_R_c2gv(
            estimate.gravity_up_camera
        )
    )

    assert np.array_equal(
        R_npz,
        expected_R,
    )

    assert np.array_equal(
        R_npz,
        written["R_c2gv"],
    )

    assert np.allclose(
        up_npz,
        estimate.gravity_up_camera,
        atol=1e-7,
    )

    print(
        "SESSION_NPZ_CONTRACT=PASS"
    )


    print()
    print(
        "===== JSON CONTRACT ====="
    )

    with json_path.open(
        "r",
        encoding="utf-8",
    ) as f:
        metadata = json.load(
            f
        )

    assert (
        metadata[
            "format_version"
        ]
        == 1
    )

    assert (
        metadata[
            "alignment_mode"
        ]
        == "session_v2"
    )

    assert (
        metadata[
            "alignment_method"
        ]
        == "neutral_smpl24_v1"
    )

    assert (
        metadata[
            "image_size"
        ]
        == {
            "width": 1280,
            "height": 720,
        }
    )

    assert (
        metadata[
            "intrinsics_source"
        ]
        == "gvhmr_estimate_K"
    )

    assert (
        metadata[
            "quality"
        ][
            "accepted_frames"
        ]
        == estimate.accepted_frames
    )

    print(
        "SESSION_JSON_CONTRACT=PASS"
    )


    print()
    print(
        "===== EXISTING SESSION_V2 LOADER ROUNDTRIP ====="
    )

    profile = (
        SonicCalibrationProfile
        .from_paths(
            alignment_mode="session_v2",
            session_alignment_file=(
                npz_path
            ),
        )
    )

    (
        R_loaded,
        smooth_loaded,
    ) = load_session_R_c2gv(
        profile,
        "cpu",
    )

    R_loaded = (
        R_loaded
        .detach()
        .cpu()
        .numpy()
    )

    max_error = float(
        np.max(
            np.abs(
                R_loaded
                - expected_R
            )
        )
    )

    print(
        "roundtrip max error:",
        max_error,
    )

    print(
        "smoothing:",
        smooth_loaded,
    )

    assert max_error == 0.0
    assert smooth_loaded == 0.0

    print(
        "SESSION_LOADER_ROUNDTRIP=PASS"
    )


print()
print(
    "===== RESULT ====="
)

print(
    "SESSION_ALIGNMENT_ARTIFACT_TESTS=PASS"
)
