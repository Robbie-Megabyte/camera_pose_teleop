#!/usr/bin/env python3

from __future__ import annotations

import math
from pathlib import Path
import tempfile

import numpy as np

from session_v2_runtime import (
    SessionV2AlignmentController,
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


WIDTH = 1280
HEIGHT = 720

FOCAL = math.sqrt(
    WIDTH * WIDTH
    + HEIGHT * HEIGHT
)

K = np.asarray(
    [
        [
            FOCAL,
            0.0,
            WIDTH / 2.0,
        ],
        [
            0.0,
            FOCAL,
            HEIGHT / 2.0,
        ],
        [
            0.0,
            0.0,
            1.0,
        ],
    ],
    dtype=np.float32,
)


print(
    "===== SUCCESS STATE MACHINE ====="
)

with tempfile.TemporaryDirectory(
    prefix="session_v2_runtime_"
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

    controller = (
        SessionV2AlignmentController(
            npz_path=npz_path,
            json_path=json_path,
            image_width=WIDTH,
            image_height=HEIGHT,
            K_fullimg=K,
            min_duration_s=2.0,
            max_duration_s=5.0,
            min_frames=20,
        )
    )

    body = neutral_body()

    R = rz(12.0)

    rng = np.random.default_rng(
        123
    )

    ready_at = None

    # 15 Hz synthetic worker stream.
    for i in range(80):
        timestamp = (
            i / 15.0
        )

        joints = (
            body
            @ R.T
            + np.asarray(
                [
                    0.2,
                    -0.3,
                    2.0,
                ]
            )
        )

        joints += rng.normal(
            0.0,
            0.002,
            size=joints.shape,
        )

        status = controller.add_frame(
            joints,
            timestamp_s=timestamp,
        )

        if (
            timestamp < 2.0
            and status.state
            == "ready"
        ):
            raise AssertionError(
                "Alignment completed before "
                "minimum duration"
            )

        if status.state == "ready":
            ready_at = timestamp
            break

    print(
        "ready at:",
        ready_at,
    )

    print(
        "state:",
        status.state,
    )

    print(
        "total frames:",
        status.total_frames,
    )

    print(
        "candidate frames:",
        status.candidate_frames,
    )

    print(
        "NPZ exists:",
        npz_path.exists(),
    )

    print(
        "JSON exists:",
        json_path.exists(),
    )

    assert status.state == "ready"

    assert ready_at is not None

    assert (
        ready_at >= 2.0
    )

    assert (
        ready_at <= 5.0
    )

    assert npz_path.exists()
    assert json_path.exists()

    print()
    print("operator message:")
    print(status.message)

    assert (
        "CAMERA ALIGNMENT PASSED"
        in status.message
    )

    assert (
        "TELEOP STREAM MAY START"
        in status.message
    )

    print(
        "SESSION_V2_OPERATOR_SUCCESS_MESSAGE=PASS"
    )

    print(
        "SESSION_V2_RUNTIME_SUCCESS=PASS"
    )


print()
print(
    "===== FAILURE / NO ARTIFACT TEST ====="
)

with tempfile.TemporaryDirectory(
    prefix="session_v2_failure_"
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

    controller = (
        SessionV2AlignmentController(
            npz_path=npz_path,
            json_path=json_path,
            image_width=WIDTH,
            image_height=HEIGHT,
            K_fullimg=K,
            min_duration_s=2.0,
            max_duration_s=5.0,
            min_frames=20,
        )
    )

    invalid = np.zeros(
        (24, 3),
        dtype=np.float64,
    )

    for i in range(90):
        timestamp = (
            i / 15.0
        )

        status = controller.add_frame(
            invalid,
            timestamp_s=timestamp,
        )

        if status.state == "failed":
            break

    print(
        "failed at:",
        status.elapsed_s,
    )

    print(
        "state:",
        status.state,
    )

    print(
        "total frames:",
        status.total_frames,
    )

    print(
        "candidate frames:",
        status.candidate_frames,
    )

    print(
        "message:",
        status.message,
    )

    print(
        "NPZ exists:",
        npz_path.exists(),
    )

    print(
        "JSON exists:",
        json_path.exists(),
    )

    assert status.state == "failed"

    assert status.elapsed_s >= 5.0

    assert not npz_path.exists()
    assert not json_path.exists()

    print()
    print("operator failure message:")
    print(status.message)

    assert (
        "CAMERA ALIGNMENT FAILED"
        in status.message
    )

    assert (
        "NO TELEOP DATA IS BEING PUBLISHED"
        in status.message
    )

    assert (
        "retry"
        in status.message.lower()
    )

    print(
        "SESSION_V2_OPERATOR_FAILURE_MESSAGE=PASS"
    )

    print(
        "SESSION_V2_RUNTIME_FAILURE=PASS"
    )


print()
print(
    "===== STALE ARTIFACT PROTECTION ====="
)

with tempfile.TemporaryDirectory(
    prefix="session_v2_stale_"
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

    # Simulate a successful calibration from an OLD run.
    npz_path.write_bytes(
        b"STALE_OLD_SESSION"
    )

    json_path.write_text(
        "STALE_OLD_SESSION",
        encoding="utf-8",
    )

    assert npz_path.exists()
    assert json_path.exists()

    controller = (
        SessionV2AlignmentController(
            npz_path=npz_path,
            json_path=json_path,
            image_width=WIDTH,
            image_height=HEIGHT,
            K_fullimg=K,
            min_duration_s=2.0,
            max_duration_s=5.0,
            min_frames=20,
        )
    )

    print(
        "stale removed:",
        [
            str(p.name)
            for p
            in controller.stale_artifacts_removed
        ],
    )

    print(
        "NPZ after new session start:",
        npz_path.exists(),
    )

    print(
        "JSON after new session start:",
        json_path.exists(),
    )

    assert len(
        controller.stale_artifacts_removed
    ) == 2

    assert not npz_path.exists()
    assert not json_path.exists()

    # Now deliberately fail the NEW calibration.
    invalid = np.zeros(
        (24, 3),
        dtype=np.float64,
    )

    for i in range(90):
        status = controller.add_frame(
            invalid,
            timestamp_s=(
                i / 15.0
            ),
        )

        if status.state == "failed":
            break

    assert status.state == "failed"

    # Critical rule: failed new calibration must not make
    # the previous artifact usable again.
    assert not npz_path.exists()
    assert not json_path.exists()

    print(status.message)

    print(
        "SESSION_V2_STALE_ARTIFACT_PROTECTION=PASS"
    )


print()
print(
    "===== STARTUP GAP / CONTIGUOUS WINDOW TEST ====="
)

with tempfile.TemporaryDirectory(
    prefix="session_v2_gap_"
) as td:

    td = Path(td)

    controller = (
        SessionV2AlignmentController(
            npz_path=(
                td
                / "session_alignment.npz"
            ),
            json_path=(
                td
                / "session_alignment.json"
            ),
            image_width=WIDTH,
            image_height=HEIGHT,
            K_fullimg=K,
            min_duration_s=2.0,
            max_duration_s=5.0,
            max_interframe_gap_s=1.0,
            min_frames=20,
        )
    )

    body = neutral_body()

    status = controller.add_frame(
        body,
        timestamp_s=0.0,
    )

    assert status.state == "collecting"
    assert status.candidate_frames == 1

    # Simulate the ~3 s startup/countdown gap observed
    # in the first real V2 run.
    status = controller.add_frame(
        body,
        timestamp_s=3.1,
    )

    print(
        "window resets:",
        status.window_resets,
    )

    print(
        "elapsed after gap:",
        status.elapsed_s,
    )

    print(
        "candidate frames after gap:",
        status.candidate_frames,
    )

    assert status.window_resets == 1
    assert status.elapsed_s == 0.0
    assert status.candidate_frames == 1

    ready_timestamp = None

    for i in range(1, 50):
        timestamp = (
            3.1
            + i / 15.0
        )

        status = controller.add_frame(
            body,
            timestamp_s=timestamp,
        )

        if status.state == "ready":
            ready_timestamp = timestamp
            break

    print(
        "ready absolute timestamp:",
        ready_timestamp,
    )

    print(
        "ready contiguous elapsed:",
        status.elapsed_s,
    )

    print(status.message)

    assert status.state == "ready"
    assert ready_timestamp is not None
    assert status.elapsed_s >= 2.0
    assert status.elapsed_s <= 5.0

    # Prove that the pre-gap frame did not consume the
    # new session's 5-second alignment budget.
    assert ready_timestamp > 5.0

    print(
        "SESSION_V2_CONTIGUOUS_WINDOW_RESET=PASS"
    )


print()
print(
    "===== TIMESTAMP VALIDATION ====="
)

with tempfile.TemporaryDirectory(
    prefix="session_v2_time_"
) as td:

    td = Path(td)

    controller = (
        SessionV2AlignmentController(
            npz_path=td / "a.npz",
            json_path=td / "a.json",
            image_width=WIDTH,
            image_height=HEIGHT,
            K_fullimg=K,
        )
    )

    controller.add_frame(
        neutral_body(),
        timestamp_s=10.0,
    )

    try:
        controller.add_frame(
            neutral_body(),
            timestamp_s=9.0,
        )

    except Exception as exc:
        print(
            "backwards time: REJECTED",
            f"({exc})",
        )

    else:
        raise AssertionError(
            "Backwards timestamp accepted"
        )

    print(
        "SESSION_V2_RUNTIME_TIME_VALIDATION=PASS"
    )


print()
print(
    "===== RESULT ====="
)

print(
    "SESSION_V2_RUNTIME_TESTS=PASS"
)
