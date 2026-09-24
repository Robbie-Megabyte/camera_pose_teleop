#!/usr/bin/env python3

from __future__ import annotations

import math
from pathlib import Path
import tempfile

import numpy as np

from session_v2_bridge_gate import (
    SessionV2BridgeGate,
)

from session_v2_runtime import (
    SessionV2AlignmentController,
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
        [FOCAL, 0.0, WIDTH / 2.0],
        [0.0, FOCAL, HEIGHT / 2.0],
        [0.0, 0.0, 1.0],
    ],
    dtype=np.float32,
)


class FakeBridge:
    pass


print(
    "===== SUCCESS GATING ====="
)

with tempfile.TemporaryDirectory(
    prefix="v2_bridge_gate_success_"
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
            min_frames=20,
        )
    )

    factory_calls = []

    def bridge_factory():
        factory_calls.append(
            "called"
        )

        return FakeBridge()

    gate = SessionV2BridgeGate(
        controller=controller,
        bridge_factory=bridge_factory,
    )

    body = neutral_body()

    rng = np.random.default_rng(
        1234
    )

    ready_at = None

    for i in range(80):
        timestamp = (
            i / 15.0
        )

        joints = (
            body
            + np.asarray(
                [0.2, -0.3, 2.0]
            )
        )

        joints += rng.normal(
            0.0,
            0.002,
            size=joints.shape,
        )

        (
            status,
            bridge,
            created_now,
        ) = gate.process_alignment_frame(
            joints,
            timestamp_s=timestamp,
        )

        if timestamp < 2.0:
            assert bridge is None
            assert not created_now
            assert len(
                factory_calls
            ) == 0

        if status.state == "ready":
            ready_at = timestamp

            assert bridge is not None
            assert created_now
            break

    print(
        "ready at:",
        ready_at,
    )

    print(
        "factory calls:",
        len(factory_calls),
    )

    print(
        "bridge create count:",
        gate.bridge_create_count,
    )

    print(status.message)

    assert ready_at is not None
    assert ready_at >= 2.0

    assert len(
        factory_calls
    ) == 1

    assert (
        gate.bridge_create_count
        == 1
    )

    # Additional frames after READY must never
    # instantiate a second bridge.
    (
        status2,
        bridge2,
        created2,
    ) = gate.process_alignment_frame(
        body,
        timestamp_s=3.0,
    )

    assert bridge2 is bridge
    assert not created2

    assert len(
        factory_calls
    ) == 1

    print(
        "SESSION_V2_BRIDGE_DEFERRED_UNTIL_READY=PASS"
    )

    print(
        "SESSION_V2_BRIDGE_CREATED_ONCE=PASS"
    )


print()
print(
    "===== FAILURE GATING ====="
)

with tempfile.TemporaryDirectory(
    prefix="v2_bridge_gate_failure_"
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
            min_frames=20,
        )
    )

    factory_calls = []

    def bridge_factory_fail_test():
        factory_calls.append(
            "CALLED_BUT_SHOULD_NOT_BE"
        )

        return FakeBridge()

    gate = SessionV2BridgeGate(
        controller=controller,
        bridge_factory=(
            bridge_factory_fail_test
        ),
    )

    invalid = np.zeros(
        (24, 3),
        dtype=np.float64,
    )

    for i in range(90):
        (
            status,
            bridge,
            created_now,
        ) = gate.process_alignment_frame(
            invalid,
            timestamp_s=(
                i / 15.0
            ),
        )

        assert bridge is None
        assert not created_now

        if status.state == "failed":
            break

    print(
        "state:",
        status.state,
    )

    print(
        "factory calls:",
        len(factory_calls),
    )

    print(status.message)

    assert status.state == "failed"

    assert len(
        factory_calls
    ) == 0

    assert gate.bridge is None

    print(
        "SESSION_V2_FAILED_ALIGNMENT_NO_BRIDGE=PASS"
    )


print()
print(
    "===== RESULT ====="
)

print(
    "SESSION_V2_BRIDGE_GATE_TESTS=PASS"
)
