import math

import numpy as np
from scipy.spatial.transform import Rotation

from v3_fusion.g1_wrist_control_runtime import (
    G1WristControlRuntime,
    G1_WRIST_HARD_VELOCITY_LIMITS_RAD_S,
)


DEG = math.pi / 180.0


def close(
    a,
    b,
    tol=1e-6,
):
    a = np.asarray(
        a,
        dtype=np.float64,
    )

    b = np.asarray(
        b,
        dtype=np.float64,
    )

    assert np.max(
        np.abs(
            a
            -
            b
        )
    ) < tol, (
        a,
        b,
    )


def make_runtime():

    return G1WristControlRuntime(
        # Conservative TELEOP cap.
        # This is deliberately below the source-confirmed hard limits.
        teleop_max_speed_rad_s=
            np.radians(
                [
                    90.0,
                    90.0,
                    90.0,
                ]
            ),

        max_dt_s=0.20,
    )


def test_hard_velocity_limits_declared():

    close(
        G1_WRIST_HARD_VELOCITY_LIMITS_RAD_S,
        [
            37.0,
            22.0,
            22.0,
        ],
    )

    print(
        "test_hard_velocity_limits_declared=PASS"
    )


def test_neutral_protocol_field():

    runtime = make_runtime()

    runtime.initialize_neutral(
        10.0
    )

    wrists = runtime.sonic_wrists()

    assert wrists.shape == (
        1,
        6,
    )

    assert wrists.dtype == np.float32

    close(
        wrists,
        np.zeros(
            (
                1,
                6,
            )
        ),
    )

    print(
        "test_neutral_protocol_field=PASS"
    )


def test_exact_interleaved_sonic_order():

    runtime = make_runtime()

    runtime.initialize_neutral(
        0.0
    )

    L = Rotation.from_euler(
        "XYZ",
        np.radians(
            [
                5.0,
                10.0,
                15.0,
            ]
        ),
    ).as_matrix()

    # Right convention in Q5 is:
    # human XYZ -> G1 [-X, -Y, +Z].
    R = Rotation.from_euler(
        "XYZ",
        np.radians(
            [
                -6.0,
                -11.0,
                16.0,
            ]
        ),
    ).as_matrix()

    runtime.update_side(
        "L",
        1.0,
        L,
        trust_state="TRACKING",
        authority=1.0,
    )

    runtime.update_side(
        "R",
        1.0,
        R,
        trust_state="TRACKING",
        authority=1.0,
    )

    wrists_deg = np.degrees(
        runtime.sonic_wrists()
    )

    # Protocol v3:
    # [Lr, Rr, Lp, Rp, Ly, Ry]
    close(
        wrists_deg,
        [
            [
                +5.0,
                +6.0,
                +10.0,
                +11.0,
                +15.0,
                +16.0,
            ]
        ],
        tol=1e-4,
    )

    print(
        "test_exact_interleaved_sonic_order=PASS"
    )


def test_slew_is_applied():

    runtime = make_runtime()

    runtime.initialize_neutral(
        0.0
    )

    target = Rotation.from_euler(
        "X",
        90.0,
        degrees=True,
    ).as_matrix()

    out = runtime.update_side(
        "L",
        0.1,
        target,
        trust_state="TRACKING",
        authority=1.0,
    )

    q = np.degrees(
        out.command.as_array()
    )

    # 90 deg/s * 0.1 s = 9 deg.
    close(
        q,
        [
            9.0,
            0.0,
            0.0,
        ],
        tol=1e-5,
    )

    print(
        "test_slew_is_applied=PASS"
    )


def test_lost_does_not_contaminate_mapper():

    runtime = make_runtime()

    runtime.initialize_neutral(
        0.0
    )

    tracking_R = Rotation.from_euler(
        "X",
        20.0,
        degrees=True,
    ).as_matrix()

    runtime.update_side(
        "L",
        0.1,
        tracking_R,
        trust_state="TRACKING",
        authority=1.0,
    )

    before = (
        runtime
        .current_side(
            "L"
        )
        .as_array()
        .copy()
    )

    # Deliberately absurd untrusted orientation.
    garbage_R = Rotation.from_euler(
        "XYZ",
        [
            170.0,
            89.0,
            -170.0,
        ],
        degrees=True,
    ).as_matrix()

    out = runtime.update_side(
        "L",
        0.2,
        garbage_R,
        trust_state="LOST",
        authority=0.0,
    )

    close(
        out.command.as_array(),
        before,
    )

    assert (
        out.command_reason
        ==
        "trust_lost_hold"
    )

    # Reacquire still must not use the supplied matrix.
    out2 = runtime.update_side(
        "L",
        0.3,
        garbage_R,
        trust_state="REACQUIRE",
        authority=0.0,
    )

    close(
        out2.command.as_array(),
        before,
    )

    assert (
        out2.command_reason
        ==
        "trust_reacquire_hold"
    )

    print(
        "test_lost_does_not_contaminate_mapper=PASS"
    )


def test_suspect_reduced_authority():

    runtime = make_runtime()

    runtime.initialize_neutral(
        0.0
    )

    target = Rotation.from_euler(
        "X",
        90.0,
        degrees=True,
    ).as_matrix()

    out = runtime.update_side(
        "L",
        0.1,
        target,
        trust_state="SUSPECT",
        authority=0.25,
    )

    q = np.degrees(
        out.command.as_array()
    )

    close(
        q,
        [
            2.25,
            0.0,
            0.0,
        ],
        tol=1e-5,
    )

    print(
        "test_suspect_reduced_authority=PASS"
    )


if __name__ == "__main__":

    test_hard_velocity_limits_declared()
    test_neutral_protocol_field()
    test_exact_interleaved_sonic_order()
    test_slew_is_applied()
    test_lost_does_not_contaminate_mapper()
    test_suspect_reduced_authority()

    print()
    print(
        "Q5_COMPLETE_WRIST_CONTROLLER=PASS"
    )
