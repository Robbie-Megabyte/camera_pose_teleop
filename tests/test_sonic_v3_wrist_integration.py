import math

import numpy as np

from scipy.spatial.transform import Rotation

from v3_fusion.sonic_v3_wrist_integration import (
    SonicV3WristIntegration,
    inject_wrists_into_bridge_fields,
    validate_sonic_wrists,
)


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


def fake_bridge_fields():
    """Mirror the protected bridge's current output contract."""

    joints = np.arange(
        72,
        dtype=np.float32,
    ).reshape(
        1,
        24,
        3,
    )

    quat = np.array(
        [
            [
                0.1,
                0.2,
                0.3,
                0.9,
            ]
        ],
        dtype=np.float32,
    )

    pose = np.arange(
        63,
        dtype=np.float32,
    ).reshape(
        1,
        21,
        3,
    )

    return {
        "smpl_joints":
            joints,

        "body_quat":
            quat,

        "smpl_pose":
            pose,

        # This is exactly what the protected bridge currently emits.
        "wrists":
            np.zeros(
                (
                    1,
                    6,
                ),
                dtype=np.float32,
            ),
    }


def test_validate_contract():

    wrists = validate_sonic_wrists(
        np.zeros(
            (
                1,
                6,
            )
        )
    )

    assert wrists.shape == (
        1,
        6,
    )

    assert wrists.dtype == np.float32

    print(
        "test_validate_contract=PASS"
    )


def test_only_wrists_change():

    original = fake_bridge_fields()

    joints_before = (
        original[
            "smpl_joints"
        ].copy()
    )

    quat_before = (
        original[
            "body_quat"
        ].copy()
    )

    pose_before = (
        original[
            "smpl_pose"
        ].copy()
    )

    wrists = np.array(
        [
            [
                0.10,
                0.20,
                0.30,
                0.40,
                0.50,
                0.60,
            ]
        ],
        dtype=np.float32,
    )

    out = inject_wrists_into_bridge_fields(
        original,
        wrists,
        copy_fields=True,
    )

    close(
        out[
            "wrists"
        ],
        wrists,
    )

    close(
        out[
            "smpl_joints"
        ],
        joints_before,
    )

    close(
        out[
            "body_quat"
        ],
        quat_before,
    )

    close(
        out[
            "smpl_pose"
        ],
        pose_before,
    )

    # copy_fields=True means even the original zero field is untouched.
    close(
        original[
            "wrists"
        ],
        np.zeros(
            (
                1,
                6,
            )
        ),
    )

    print(
        "test_only_wrists_change=PASS"
    )


def test_live_q5_to_bridge_fields():

    adapter = SonicV3WristIntegration(
        teleop_max_speed_rad_s=
            math.radians(
                90.0
            ),
        max_dt_s=
            0.20,
    )

    adapter.initialize_neutral(
        0.0
    )

    # Choose small rotations so the 90 deg/s teleop slew does not
    # constrain them after 1 second.
    left_R = (
        Rotation
        .from_euler(
            "XYZ",
            [
                5.0,
                10.0,
                15.0,
            ],
            degrees=True,
        )
        .as_matrix()
    )

    # Right-side Q5 convention:
    # human [-X,-Y,+Z] here gives positive G1 roll/pitch/yaw.
    right_R = (
        Rotation
        .from_euler(
            "XYZ",
            [
                -6.0,
                -11.0,
                16.0,
            ],
            degrees=True,
        )
        .as_matrix()
    )

    adapter.update_side(
        "L",
        1.0,
        left_R,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    adapter.update_side(
        "R",
        1.0,
        right_R,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    fields = adapter.inject(
        fake_bridge_fields()
    )

    wrists_deg = np.degrees(
        fields[
            "wrists"
        ]
    )

    # Exact Protocol-v3 wire order:
    #
    # 23 L_roll
    # 24 R_roll
    # 25 L_pitch
    # 26 R_pitch
    # 27 L_yaw
    # 28 R_yaw
    close(
        wrists_deg,
        [
            [
                5.0,
                6.0,
                10.0,
                11.0,
                15.0,
                16.0,
            ]
        ],
        tol=1e-4,
    )

    print(
        "test_live_q5_to_bridge_fields=PASS"
    )


def test_publisher_slot_emulation():

    adapter = SonicV3WristIntegration(
        teleop_max_speed_rad_s=
            math.radians(
                90.0
            ),
        max_dt_s=
            0.20,
    )

    adapter.initialize_neutral(
        0.0
    )

    left_R = (
        Rotation
        .from_euler(
            "XYZ",
            [
                7.0,
                12.0,
                17.0,
            ],
            degrees=True,
        )
        .as_matrix()
    )

    right_R = (
        Rotation
        .from_euler(
            "XYZ",
            [
                -8.0,
                -13.0,
                18.0,
            ],
            degrees=True,
        )
        .as_matrix()
    )

    adapter.update_side(
        "L",
        1.0,
        left_R,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    adapter.update_side(
        "R",
        1.0,
        right_R,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    fields = adapter.inject(
        fake_bridge_fields()
    )

    # Emulate the already-source-confirmed publisher behavior.
    joint_pos = np.zeros(
        (
            1,
            29,
        ),
        dtype=np.float32,
    )

    joint_pos[
        :,
        23:29
    ] = fields[
        "wrists"
    ]

    expected_deg = np.array(
        [
            [
                7.0,
                8.0,
                12.0,
                13.0,
                17.0,
                18.0,
            ]
        ],
        dtype=np.float64,
    )

    close(
        np.degrees(
            joint_pos[
                :,
                23:29
            ]
        ),
        expected_deg,
        tol=1e-4,
    )

    # Everything outside the six wrist slots remains untouched.
    close(
        joint_pos[
            :,
            :23
        ],
        0.0,
    )

    print(
        "test_publisher_slot_emulation=PASS"
    )


def test_lost_side_holds_while_other_side_tracks():

    adapter = SonicV3WristIntegration(
        teleop_max_speed_rad_s=
            math.radians(
                90.0
            ),
        max_dt_s=
            0.20,
    )

    adapter.initialize_neutral(
        0.0
    )

    L_good = (
        Rotation
        .from_euler(
            "X",
            20.0,
            degrees=True,
        )
        .as_matrix()
    )

    R_good = (
        Rotation
        .from_euler(
            "X",
            -20.0,
            degrees=True,
        )
        .as_matrix()
    )

    adapter.update_side(
        "L",
        0.1,
        L_good,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    adapter.update_side(
        "R",
        0.1,
        R_good,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    before = (
        adapter
        .wrists()
        .copy()
    )

    garbage = (
        Rotation
        .from_euler(
            "XYZ",
            [
                170.0,
                89.0,
                -170.0,
            ],
            degrees=True,
        )
        .as_matrix()
    )

    # Left loses authority.
    adapter.update_side(
        "L",
        0.2,
        garbage,
        trust_state=
            "LOST",
        authority=
            0.0,
    )

    # Right continues tracking.
    R_next = (
        Rotation
        .from_euler(
            "X",
            -30.0,
            degrees=True,
        )
        .as_matrix()
    )

    adapter.update_side(
        "R",
        0.2,
        R_next,
        trust_state=
            "TRACKING",
        authority=
            1.0,
    )

    after = (
        adapter
        .wrists()
    )

    # L_roll slot is unchanged.
    close(
        after[
            0,
            0
        ],
        before[
            0,
            0
        ],
    )

    # R_roll slot is allowed to advance.
    assert abs(
        float(
            after[
                0,
                1
            ]
            -
            before[
                0,
                1
            ]
        )
    ) > 1e-6

    print(
        "test_lost_side_holds_while_other_side_tracks=PASS"
    )


if __name__ == "__main__":

    test_validate_contract()
    test_only_wrists_change()
    test_live_q5_to_bridge_fields()
    test_publisher_slot_emulation()
    test_lost_side_holds_while_other_side_tracks()

    print()
    print(
        "Q5_SONIC_V3_SANDBOX_INTEGRATION=PASS"
    )
