import math

import numpy as np

from v3_fusion.g1_wrist_mapping import (
    G1WristAngles,
)

from v3_fusion.wrist_command_runtime import (
    G1WristCommandSlewLimiter,
)


DEG = math.pi / 180.0


def arr(
    q,
):
    return np.asarray(
        q.as_array(),
        dtype=np.float64,
    )


def assert_close(
    a,
    b,
    tol=1e-8,
):
    assert np.max(
        np.abs(
            np.asarray(a)
            -
            np.asarray(b)
        )
    ) < tol, (
        a,
        b,
    )


def test_exact_timestamp_rate_limit():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        10.0,
        [
            0.0,
            0.0,
            0.0,
        ],
    )

    out = limiter.update(
        "L",
        10.1,
        [
            90.0 * DEG,
            0.0,
            0.0,
        ],
    )

    q = np.degrees(
        arr(
            out.command
        )
    )

    assert_close(
        q,
        [
            9.0,
            0.0,
            0.0,
        ],
        tol=1e-6,
    )

    assert out.limited

    print(
        "test_exact_timestamp_rate_limit=PASS"
    )


def test_axes_independent():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=np.radians(
            [
                90.0,
                60.0,
                30.0,
            ]
        ),
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        0.0,
        [
            0.0,
            0.0,
            0.0,
        ],
    )

    out = limiter.update(
        "L",
        0.1,
        np.radians(
            [
                90.0,
                90.0,
                90.0,
            ]
        ),
    )

    q = np.degrees(
        arr(
            out.command
        )
    )

    assert_close(
        q,
        [
            9.0,
            6.0,
            3.0,
        ],
        tol=1e-6,
    )

    print(
        "test_axes_independent=PASS"
    )


def test_long_gap_catchup_cap():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        0.0,
        [
            0.0,
            0.0,
            0.0,
        ],
    )

    out = limiter.update(
        "L",
        2.0,
        [
            90.0 * DEG,
            0.0,
            0.0,
        ],
    )

    q = np.degrees(
        arr(
            out.command
        )
    )

    assert_close(
        q,
        [
            18.0,
            0.0,
            0.0,
        ],
        tol=1e-6,
    )

    assert abs(
        out.dt_used_s
        -
        0.20
    ) < 1e-9

    print(
        "test_long_gap_catchup_cap=PASS"
    )


def test_nonmonotonic_timestamp_holds():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "R",
        5.0,
        [
            0.1,
            0.2,
            0.3,
        ],
    )

    before = arr(
        limiter.current(
            "R"
        )
    )

    out = limiter.update(
        "R",
        4.9,
        [
            -0.5,
            -0.5,
            -0.5,
        ],
    )

    after = arr(
        out.command
    )

    assert_close(
        before,
        after,
    )

    assert (
        out.reason
        ==
        "non_monotonic_timestamp_hold"
    )

    print(
        "test_nonmonotonic_timestamp_holds=PASS"
    )


def test_left_right_state_independent():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        0.0,
        [
            0.0,
            0.0,
            0.0,
        ],
    )

    limiter.initialize(
        "R",
        0.0,
        [
            0.0,
            0.0,
            0.0,
        ],
    )

    L = limiter.update(
        "L",
        0.1,
        [
            1.0,
            0.0,
            0.0,
        ],
    )

    R = limiter.update(
        "R",
        0.1,
        [
            -1.0,
            0.0,
            0.0,
        ],
    )

    Lq = np.degrees(
        arr(
            L.command
        )
    )

    Rq = np.degrees(
        arr(
            R.command
        )
    )

    assert abs(
        Lq[0]
        -
        9.0
    ) < 1e-6

    assert abs(
        Rq[0]
        +
        9.0
    ) < 1e-6

    print(
        "test_left_right_state_independent=PASS"
    )


if __name__ == "__main__":

    test_exact_timestamp_rate_limit()
    test_axes_independent()
    test_long_gap_catchup_cap()
    test_nonmonotonic_timestamp_holds()
    test_left_right_state_independent()

    print(
        "Q5_WRIST_COMMAND_SLEW=PASS"
    )


# =====================================================================
# Q5.14 trust / authority tests
# =====================================================================

def test_zero_authority_holds_and_advances_timestamp():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        0.0,
        [0.0, 0.0, 0.0],
    )

    hold = limiter.update(
        "L",
        0.1,
        np.radians(
            [90.0, 0.0, 0.0]
        ),
        authority=0.0,
    )

    assert_close(
        np.degrees(
            arr(
                hold.command
            )
        ),
        [0.0, 0.0, 0.0],
        tol=1e-6,
    )

    # Timestamp must have advanced during the hold.
    # Therefore this next 0.1-second tracking update moves 9 deg,
    # not 18 deg and not a large catch-up.
    tracked = limiter.update(
        "L",
        0.2,
        np.radians(
            [90.0, 0.0, 0.0]
        ),
        authority=1.0,
    )

    assert_close(
        np.degrees(
            arr(
                tracked.command
            )
        ),
        [9.0, 0.0, 0.0],
        tol=1e-6,
    )

    print(
        "test_zero_authority_holds_and_advances_timestamp=PASS"
    )


def test_quarter_authority_scales_motion():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        0.0,
        [0.0, 0.0, 0.0],
    )

    out = limiter.update(
        "L",
        0.1,
        np.radians(
            [90.0, 0.0, 0.0]
        ),
        authority=0.25,
    )

    assert_close(
        np.degrees(
            arr(
                out.command
            )
        ),
        [2.25, 0.0, 0.0],
        tol=1e-6,
    )

    assert (
        out.reason
        ==
        "authority_limited"
    )

    print(
        "test_quarter_authority_scales_motion=PASS"
    )


def test_lost_and_reacquire_hold():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "L",
        0.0,
        [0.0, 0.0, 0.0],
    )

    lost = limiter.update_trusted(
        "L",
        0.1,
        np.radians(
            [90.0, 90.0, 90.0]
        ),
        trust_state="LOST",
        authority=1.0,
    )

    assert_close(
        np.degrees(
            arr(
                lost.command
            )
        ),
        [0.0, 0.0, 0.0],
        tol=1e-6,
    )

    assert lost.reason == "trust_lost_hold"

    reacquire = limiter.update_trusted(
        "L",
        0.2,
        np.radians(
            [-90.0, -90.0, -90.0]
        ),
        trust_state="REACQUIRE",
        authority=1.0,
    )

    assert_close(
        np.degrees(
            arr(
                reacquire.command
            )
        ),
        [0.0, 0.0, 0.0],
        tol=1e-6,
    )

    assert (
        reacquire.reason
        ==
        "trust_reacquire_hold"
    )

    print(
        "test_lost_and_reacquire_hold=PASS"
    )


def test_suspect_then_tracking():

    limiter = G1WristCommandSlewLimiter(
        max_speed_rad_s=90.0 * DEG,
        max_dt_s=0.20,
    )

    limiter.initialize(
        "R",
        0.0,
        [0.0, 0.0, 0.0],
    )

    suspect = limiter.update_trusted(
        "R",
        0.1,
        np.radians(
            [90.0, 0.0, 0.0]
        ),
        trust_state="SUSPECT",
        authority=0.25,
    )

    assert abs(
        np.degrees(
            arr(
                suspect.command
            )
        )[0]
        -
        2.25
    ) < 1e-6

    tracking = limiter.update_trusted(
        "R",
        0.2,
        np.radians(
            [90.0, 0.0, 0.0]
        ),
        trust_state="TRACKING",
        authority=1.0,
    )

    # Another 0.1 seconds at full authority = +9 deg.
    assert abs(
        np.degrees(
            arr(
                tracking.command
            )
        )[0]
        -
        11.25
    ) < 1e-6

    print(
        "test_suspect_then_tracking=PASS"
    )


def run_q5_trust_tests():

    tests = [
        test_zero_authority_holds_and_advances_timestamp,
        test_quarter_authority_scales_motion,
        test_lost_and_reacquire_hold,
        test_suspect_then_tracking,
    ]

    for fn in tests:
        fn()

    print(
        "Q5_WRIST_TRUST_AUTHORITY=PASS"
    )


if __name__ == "__main__":
    run_q5_trust_tests()
