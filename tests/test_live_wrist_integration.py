from pathlib import Path

import numpy as np

from v3_fusion.live_wilor_q4_runtime import (
    DEFAULT_KP_CONF_MIN,
    DEFAULT_PAIR_MAX_S,
    hand_proposal,
)


ROOT = Path(__file__).resolve().parents[1]

RUNNER = (
    ROOT
    / "perception"
    / "runtime"
    / "live_gvhmr_pair_prio2_interactive_test.py"
)

OWNER = (
    ROOT
    / "sonic"
    / "runtime"
    / "live_gvhmr_pair_prio2_sonic_async_interactive.py"
)


def test_exact_hand_crop_geometry():
    box = hand_proposal(
        np.array(
            [
                100.0,
                100.0,
            ]
        ),
        np.array(
            [
                200.0,
                100.0,
            ]
        ),
        640,
        480,
    )

    expected = np.array(
        [
            192.5,
            55.0,
            282.5,
            145.0,
        ],
        dtype=np.float32,
    )

    assert box is not None

    assert np.max(
        np.abs(
            box
            -
            expected
        )
    ) < 1e-5

    print(
        "test_exact_hand_crop_geometry=PASS"
    )


def test_crop_clips_to_frame():
    box = hand_proposal(
        np.array(
            [
                100.0,
                100.0,
            ]
        ),
        np.array(
            [
                200.0,
                100.0,
            ]
        ),
        250,
        480,
    )

    assert box is not None

    assert float(
        box[2]
    ) == 249.0

    print(
        "test_crop_clips_to_frame=PASS"
    )


def test_frozen_threshold_defaults():
    import os
    import re

    crop_script = (
        ROOT
        / "tests"
        / "extract_production_vitpose_hand_crops.py"
    )

    production_value = None

    if crop_script.exists():
        source = crop_script.read_text()

        match = re.search(
            r"(?m)^\s*KP_CONF_MIN\s*=\s*([0-9.]+)",
            source,
        )

        if match:
            production_value = float(
                match.group(1)
            )

    if (
        "Q4_HAND_KP_CONF_MIN"
        in os.environ
    ):
        expected_kp = float(
            os.environ[
                "Q4_HAND_KP_CONF_MIN"
            ]
        )

        expected_source = (
            "environment override"
        )

    elif production_value is not None:
        expected_kp = (
            production_value
        )

        expected_source = (
            "accepted production crop script"
        )

    else:
        expected_kp = 0.25

        expected_source = (
            "accepted fallback"
        )

    expected_pair = float(
        os.environ.get(
            "Q4_LIVE_PAIR_MAX_S",
            "0.20",
        )
    )

    assert abs(
        DEFAULT_KP_CONF_MIN
        -
        expected_kp
    ) < 1e-9, (
        DEFAULT_KP_CONF_MIN,
        expected_kp,
        expected_source,
    )

    assert abs(
        DEFAULT_PAIR_MAX_S
        -
        expected_pair
    ) < 1e-9, (
        DEFAULT_PAIR_MAX_S,
        expected_pair,
    )

    print(
        "test_frozen_threshold_defaults=PASS "
        f"kp_conf={DEFAULT_KP_CONF_MIN} "
        f"source={expected_source!r} "
        f"pair_max_s={DEFAULT_PAIR_MAX_S}"
    )


def test_runner_exact_post_fastik_exposure():
    text = RUNNER.read_text()

    assert (
        "# V3_POST_FASTIK_Q4_EXPOSURE_V1"
        in text
    )

    assert (
        '"v3_post_fastik_joints_last"'
        in text
    )

    assert (
        "_v3_post_fastik_joints_last.detach().clone()"
        in text
    )

    print(
        "test_runner_exact_post_fastik_exposure=PASS"
    )


def test_owner_one_hand_worker():
    text = OWNER.read_text()

    assert (
        'name="v3-wilor-latest-worker"'
        in text
    )

    assert (
        '"hand_pending"'
        in text
    )

    assert (
        'runtime["hand_pending"] = None'
        in text
        or
        '''runtime[
                            "hand_pending"
                        ] = None'''
        in text
    )

    print(
        "test_owner_one_hand_worker=PASS"
    )


def test_owner_q4_trust_q5_chain():
    text = OWNER.read_text()

    required = (
        "LiveWilorQ4Runtime",
        "G1WristControlRuntime",
        "hand_runtime.update_body",
        "hand_runtime.command_sample",
        "wrist_controller.update_side",
        "inject_wrists_into_bridge_fields",
        "wrist_controller.sonic_wrists",
    )

    for item in required:
        assert item in text, item

    print(
        "test_owner_q4_trust_q5_chain=PASS"
    )


def test_explicit_calibration_only():
    text = OWNER.read_text()

    assert (
        "--v3-wrist-calibrate-startup"
        in text
    )

    assert (
        "hand_runtime.arm_calibration()"
        in text
    )

    assert (
        "hand_runtime.try_calibrate()"
        in text
    )

    assert (
        "session_v2"
        in text
    )

    print(
        "test_explicit_calibration_only=PASS"
    )


def test_hold_on_unusable_q4():
    text = OWNER.read_text()

    assert (
        'if R_target is None:'
        in text
    )

    assert (
        'trust_state = "LOST"'
        in text
    )

    assert (
        "authority = 0.0"
        in text
    )

    print(
        "test_hold_on_unusable_q4=PASS"
    )


if __name__ == "__main__":
    test_exact_hand_crop_geometry()
    test_crop_clips_to_frame()
    test_frozen_threshold_defaults()
    test_runner_exact_post_fastik_exposure()
    test_owner_one_hand_worker()
    test_owner_q4_trust_q5_chain()
    test_explicit_calibration_only()
    test_hold_on_unusable_q4()

    print()
    print(
        "Q5_24_LIVE_WRIST_INTEGRATION_CONTRACT=PASS"
    )
