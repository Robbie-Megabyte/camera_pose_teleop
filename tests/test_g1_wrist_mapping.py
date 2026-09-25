from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation


ROOT = (
    Path(__file__)
    .resolve()
    .parents[1]
)

sys.path.insert(
    0,
    str(ROOT),
)

from v3_fusion.g1_wrist_mapping import (
    G1_WRIST_LIMITS_RAD,
    WRIST_FIELD_ORDER,
    canonical_pair_to_sonic_wrists,
    canonical_rotation_to_g1,
)


def close(
    a,
    b,
    tol=1e-6,
):
    assert abs(
        float(a)
        -
        float(b)
    ) <= tol, (
        a,
        b,
    )


def axis_rotation(
    axis: str,
    angle: float,
):
    return (
        Rotation
        .from_euler(
            axis,
            angle,
            degrees=False,
        )
        .as_matrix()
    )


def test_neutral():
    I = np.eye(3)

    for side in (
        "L",
        "R",
    ):
        q = (
            canonical_rotation_to_g1(
                side,
                I,
            )
        )

        close(q.roll, 0.0)
        close(q.pitch, 0.0)
        close(q.yaw, 0.0)


def test_left_pure_axes():
    a = 0.25

    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "X",
            a,
        ),
    )
    close(q.roll, +a)
    close(q.pitch, 0.0)
    close(q.yaw, 0.0)

    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "Y",
            a,
        ),
    )
    close(q.roll, 0.0)
    close(q.pitch, +a)
    close(q.yaw, 0.0)

    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "Z",
            a,
        ),
    )
    close(q.roll, 0.0)
    close(q.pitch, 0.0)
    close(q.yaw, +a)


def test_right_pure_axes():
    a = 0.25

    q = canonical_rotation_to_g1(
        "R",
        axis_rotation(
            "X",
            a,
        ),
    )
    close(q.roll, -a)
    close(q.pitch, 0.0)
    close(q.yaw, 0.0)

    q = canonical_rotation_to_g1(
        "R",
        axis_rotation(
            "Y",
            a,
        ),
    )
    close(q.roll, 0.0)
    close(q.pitch, -a)
    close(q.yaw, 0.0)

    q = canonical_rotation_to_g1(
        "R",
        axis_rotation(
            "Z",
            a,
        ),
    )
    close(q.roll, 0.0)
    close(q.pitch, 0.0)
    close(q.yaw, +a)


def test_sonic_pack_order():
    L = canonical_rotation_to_g1(
        "L",
        Rotation
        .from_euler(
            "XYZ",
            [
                0.11,
                0.22,
                0.33,
            ],
        )
        .as_matrix(),
    )

    R = canonical_rotation_to_g1(
        "R",
        Rotation
        .from_euler(
            "XYZ",
            [
                0.44,
                0.55,
                0.66,
            ],
        )
        .as_matrix(),
    )

    out = canonical_pair_to_sonic_wrists(
        Rotation
        .from_euler(
            "XYZ",
            [
                0.11,
                0.22,
                0.33,
            ],
        )
        .as_matrix(),

        Rotation
        .from_euler(
            "XYZ",
            [
                0.44,
                0.55,
                0.66,
            ],
        )
        .as_matrix(),
    )

    w = out[
        "wrists"
    ]

    assert w.shape == (
        1,
        6,
    )

    expected = np.array(
        [
            [
                +0.11,
                -0.44,
                +0.22,
                -0.55,
                +0.33,
                +0.66,
            ]
        ],
        dtype=np.float32,
    )

    assert np.allclose(
        w,
        expected,
        atol=1e-6,
    ), (
        w,
        expected,
    )


def test_pitch_branch_beyond_90_within_limit():
    # G1 pitch reaches slightly beyond 90 degrees.
    #
    # SciPy's canonical XYZ representation would express this same
    # orientation using ~pi roll/yaw.  The mapper must instead choose
    # the physically useful serial-joint branch near neutral.
    a = 1.60

    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "Y",
            a,
        ),
        clamp=True,
    )

    close(
        q.roll,
        0.0,
    )
    close(
        q.pitch,
        +a,
    )
    close(
        q.yaw,
        0.0,
    )

    q = canonical_rotation_to_g1(
        "R",
        axis_rotation(
            "Y",
            a,
        ),
        clamp=True,
    )

    close(
        q.roll,
        0.0,
    )
    close(
        q.pitch,
        -a,
    )
    close(
        q.yaw,
        0.0,
    )


def test_limits():
    # Roll beyond the physical limit.
    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "X",
            math.pi,
        ),
        clamp=True,
    )

    roll_hi = (
        G1_WRIST_LIMITS_RAD[
            "roll"
        ][1]
    )

    close(
        abs(q.roll),
        roll_hi,
    )

    # Pitch well beyond the physical G1 limit.
    #
    # The branch selector should keep this as a primarily-pitch
    # solution rather than introducing ~pi roll/yaw, then the physical
    # pitch clamp should take effect.
    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "Y",
            1.80,
        ),
        clamp=True,
    )

    pitch_hi = (
        G1_WRIST_LIMITS_RAD[
            "pitch"
        ][1]
    )

    close(
        q.roll,
        0.0,
    )

    close(
        q.pitch,
        pitch_hi,
    )

    close(
        q.yaw,
        0.0,
    )

    # Same sanity check for yaw.
    q = canonical_rotation_to_g1(
        "L",
        axis_rotation(
            "Z",
            math.pi,
        ),
        clamp=True,
    )

    yaw_hi = (
        G1_WRIST_LIMITS_RAD[
            "yaw"
        ][1]
    )

    close(
        abs(q.yaw),
        yaw_hi,
    )


def test_declared_wire_order():
    assert WRIST_FIELD_ORDER == (
        "left_wrist_roll_joint",
        "right_wrist_roll_joint",
        "left_wrist_pitch_joint",
        "right_wrist_pitch_joint",
        "left_wrist_yaw_joint",
        "right_wrist_yaw_joint",
    )


if __name__ == "__main__":
    tests = [
        test_neutral,
        test_left_pure_axes,
        test_right_pure_axes,
        test_sonic_pack_order,
        test_pitch_branch_beyond_90_within_limit,
        test_limits,
        test_declared_wire_order,
    ]

    for fn in tests:
        fn()
        print(
            f"{fn.__name__}=PASS"
        )

    print(
        "Q5_G1_WRIST_MAPPING=PASS"
    )


# =====================================================================
# Q5.7 stateful live-mapper tests
# =====================================================================

from v3_fusion.g1_wrist_mapping import (
    StatefulG1WristMapper,
)


def _q5_deg(
    x,
):
    return math.degrees(
        float(
            x
        )
    )


def test_stateful_pitch_singularity_sweep():
    """Cross 90 degrees without an Euler branch jump."""

    mapper = StatefulG1WristMapper(
        clamp=True
    )

    commands = []

    sweep_deg = (
        list(
            np.arange(
                70.0,
                101.0,
                1.0,
            )
        )
        +
        list(
            np.arange(
                99.0,
                69.0,
                -1.0,
            )
        )
    )

    for deg in sweep_deg:
        R = (
            Rotation
            .from_euler(
                "Y",
                math.radians(
                    deg
                ),
            )
            .as_matrix()
        )

        out = mapper.map_rotation(
            "L",
            R,
        )

        commands.append(
            out.command.as_array()
        )

    commands = np.asarray(
        commands,
        dtype=np.float64,
    )

    steps_deg = np.degrees(
        np.abs(
            np.diff(
                commands,
                axis=0,
            )
        )
    )

    max_step = float(
        np.max(
            steps_deg
        )
    )

    # Input changes only 1 degree per sample.
    # The 92.5-degree physical pitch limit can create saturation,
    # but never a branch flip.
    assert max_step < 2.1, max_step


def test_stateful_coupled_near_singularity():
    """Coupled smooth wrist motion must stay continuous near pitch=90."""

    mapper = StatefulG1WristMapper(
        clamp=True
    )

    commands = []

    for pitch_deg in np.linspace(
        82.0,
        98.0,
        81,
    ):
        roll_deg = (
            15.0
            *
            math.sin(
                math.radians(
                    pitch_deg
                    *
                    3.0
                )
            )
        )

        yaw_deg = (
            12.0
            *
            math.cos(
                math.radians(
                    pitch_deg
                    *
                    2.0
                )
            )
        )

        R = (
            Rotation
            .from_euler(
                "XYZ",
                [
                    math.radians(
                        roll_deg
                    ),
                    math.radians(
                        pitch_deg
                    ),
                    math.radians(
                        yaw_deg
                    ),
                ],
            )
            .as_matrix()
        )

        out = mapper.map_rotation(
            "L",
            R,
        )

        commands.append(
            out.command.as_array()
        )

    commands = np.asarray(
        commands,
        dtype=np.float64,
    )

    steps_deg = np.degrees(
        np.abs(
            np.diff(
                commands,
                axis=0,
            )
        )
    )

    max_step = float(
        np.max(
            steps_deg
        )
    )

    assert max_step < 5.0, max_step


def test_stateful_left_right_independent():
    """Left and right branch memory must remain independent."""

    mapper = StatefulG1WristMapper(
        clamp=True
    )

    L1 = mapper.map_rotation(
        "L",
        Rotation
        .from_euler(
            "XYZ",
            [
                0.2,
                1.50,
                0.1,
            ],
        )
        .as_matrix(),
    )

    R1 = mapper.map_rotation(
        "R",
        Rotation
        .from_euler(
            "XYZ",
            [
                -0.3,
                1.48,
                -0.2,
            ],
        )
        .as_matrix(),
    )

    L2 = mapper.map_rotation(
        "L",
        Rotation
        .from_euler(
            "XYZ",
            [
                0.21,
                1.52,
                0.11,
            ],
        )
        .as_matrix(),
    )

    R2 = mapper.map_rotation(
        "R",
        Rotation
        .from_euler(
            "XYZ",
            [
                -0.31,
                1.50,
                -0.19,
            ],
        )
        .as_matrix(),
    )

    L_step = np.degrees(
        np.abs(
            L2.command.as_array()
            -
            L1.command.as_array()
        )
    )

    R_step = np.degrees(
        np.abs(
            R2.command.as_array()
            -
            R1.command.as_array()
        )
    )

    assert float(
        np.max(
            L_step
        )
    ) < 5.0

    assert float(
        np.max(
            R_step
        )
    ) < 5.0



def test_stateful_unreachable_limit_sweep():
    """A smooth saturated target must not wrap limit-to-limit.

    This deliberately rotates beyond the G1 wrist's physical roll
    range while maintaining coupled pitch/yaw motion.

    The target orientation remains continuous even after it becomes
    unreachable.  The emitted physically limited G1 command must also remain
    continuous.
    """

    mapper = StatefulG1WristMapper(
        clamp=True,
    )

    commands = []
    clamped_count = 0

    for roll_deg in np.linspace(
        90.0,
        250.0,
        321,
    ):

        pitch_deg = (
            82.0
            +
            5.0
            *
            math.sin(
                math.radians(
                    roll_deg
                    *
                    0.8
                )
            )
        )

        yaw_deg = (
            35.0
            *
            math.sin(
                math.radians(
                    roll_deg
                    *
                    1.3
                )
            )
        )

        R = (
            Rotation
            .from_euler(
                "XYZ",
                [
                    math.radians(
                        roll_deg
                    ),
                    math.radians(
                        pitch_deg
                    ),
                    math.radians(
                        yaw_deg
                    ),
                ],
            )
            .as_matrix()
        )

        out = mapper.map_rotation(
            "L",
            R,
        )

        if out.clamped:
            clamped_count += 1

        commands.append(
            out.command.as_array()
        )

    commands = np.asarray(
        commands,
        dtype=np.float64,
    )

    steps_deg = np.degrees(
        np.abs(
            np.diff(
                commands,
                axis=0,
            )
        )
    )

    max_step = float(
        np.max(
            steps_deg
        )
    )

    assert clamped_count > 0, (
        "test never exercised physical G1 saturation"
    )

    roll_command_deg = np.degrees(
        commands[
            :,
            0
        ]
    )

    # The desired roll moves continuously from +90 toward +250 deg.
    # Once it exceeds the G1 +roll limit, the PHYSICAL command must
    # remain on the positive saturation side.  It must never exploit
    # Euler periodicity by teleporting to the negative roll limit.
    assert float(
        np.min(
            roll_command_deg
        )
    ) > 80.0, (
        float(
            np.min(
                roll_command_deg
            )
        )
    )

    # This is deliberately much looser than the input step.  It is
    # only a catastrophic representation-flip test, not the eventual
    # robot velocity limiter.
    assert max_step < 30.0, max_step


def run_q5_stateful_tests():
    tests = [
        test_stateful_pitch_singularity_sweep,
        test_stateful_coupled_near_singularity,
        test_stateful_left_right_independent,
        test_stateful_unreachable_limit_sweep,
    ]

    for fn in tests:
        fn()
        print(
            f"{fn.__name__}=PASS"
        )

    print(
        "Q5_STATEFUL_CONTINUITY=PASS"
    )


if __name__ == "__main__":
    run_q5_stateful_tests()
