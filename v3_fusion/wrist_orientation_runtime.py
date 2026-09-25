#!/usr/bin/env python3

"""
Reusable V3 Q4 human-wrist orientation runtime.

This module contains NO:
- recording event labels;
- frame-700 assumptions;
- SONIC/G1 mapping;
- automatic neutral recognition;
- automatic neutral reset;
- robot output.

Runtime contract
----------------

Input:
    * post-FASTIK SMPL shoulder/elbow/wrist positions
      in native SMPL camera-Y-up coordinates;
    * WiLoR pred_keypoints_3d for the corresponding hand;
    * monotonic capture timestamps.

Explicit calibration:
    calibrate(side) or calibrate_both()

Output:
    canonical anatomical wrist SO(3), where:
      X = longitudinal forearm axis / axial rotation,
      Y = flexion-extension hinge axis,
      Z = radial-ulnar hinge axis.

The left and right outputs use one common bilateral convention.

The mapping from these human anatomical axes into Unitree G1
roll/pitch/yaw is intentionally NOT done here. That is Q5.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import os

import cv2
import numpy as np


DEFAULT_ALPHA_REF = 0.40
DEFAULT_REFERENCE_DT_S = 0.100
DEFAULT_RESET_GAP_S = 0.400

STRAIGHT_ARM_SIN_THRESHOLD = 0.03

SIDES = ("L", "R")

# V12 validated left-hand semantic canonicalization.
#
# Corrected Q4 output coordinates are:
#   X = axial rotation
#   Y = flexion-extension
#   Z = radial-ulnar deviation
#
# The left convention preserves flexion-extension while reversing
# axial and deviation relative to the right:
#   X -> -X
#   Y ->  Y
#   Z -> -Z
#
# This is a proper SO(3) 180-degree rotation about corrected Y,
# NOT a reflection.
LEFT_BILATERAL_CANONICAL = np.diag(
    [
        -1.0,
        1.0,
        -1.0,
    ]
).astype(np.float64)


def normalize(v):
    v = np.asarray(
        v,
        dtype=np.float64,
    )

    n = float(
        np.linalg.norm(v)
    )

    if (
        not np.isfinite(n)
        or
        n < 1e-8
    ):
        return None

    return v / n


def project_so3(R):
    U, _, Vt = np.linalg.svd(
        np.asarray(
            R,
            dtype=np.float64,
        )
    )

    R = U @ Vt

    if np.linalg.det(R) < 0.0:
        U[:, -1] *= -1.0
        R = U @ Vt

    return R


def rotvec_deg(R):
    rv, _ = cv2.Rodrigues(
        np.asarray(
            R,
            dtype=np.float64,
        )
    )

    return (
        rv.reshape(3)
        * 180.0
        / np.pi
    )


def rotation_distance_deg(A, B):
    rv, _ = cv2.Rodrigues(
        (
            np.asarray(
                A,
                dtype=np.float64,
            ).T
            @ np.asarray(
                B,
                dtype=np.float64,
            )
        )
    )

    return float(
        np.linalg.norm(rv)
        * 180.0
        / np.pi
    )


def smooth_rotation(
    previous,
    raw,
    alpha,
):
    raw = project_so3(raw)

    if previous is None:
        return raw.copy()

    previous = project_so3(
        previous
    )

    delta = (
        previous.T
        @ raw
    )

    rv, _ = cv2.Rodrigues(
        delta.astype(
            np.float64
        )
    )

    step, _ = cv2.Rodrigues(
        rv * float(alpha)
    )

    return project_so3(
        previous @ step
    )


class TimestampSO3Filter:
    """
    Continuous-time SO(3) EMA.

    alpha_ref=0.40 at reference_dt=0.100 s corresponds to the
    currently accepted recording response.  It remains configurable
    for later live tuning.
    """

    def __init__(
        self,
        alpha_ref=DEFAULT_ALPHA_REF,
        reference_dt_s=DEFAULT_REFERENCE_DT_S,
        reset_gap_s=DEFAULT_RESET_GAP_S,
    ):
        self.alpha_ref = float(
            alpha_ref
        )

        self.reference_dt_s = float(
            reference_dt_s
        )

        self.reset_gap_s = float(
            reset_gap_s
        )

        if not (
            0.0
            < self.alpha_ref
            < 1.0
        ):
            raise ValueError(
                "alpha_ref must be in (0,1)"
            )

        if (
            not np.isfinite(
                self.reference_dt_s
            )
            or
            self.reference_dt_s
            <= 0.0
        ):
            raise ValueError(
                "reference_dt_s must be > 0"
            )

        if (
            not np.isfinite(
                self.reset_gap_s
            )
            or
            self.reset_gap_s
            <= 0.0
        ):
            raise ValueError(
                "reset_gap_s must be > 0"
            )

        self.tau_s = (
            -self.reference_dt_s
            /
            math.log(
                1.0
                -
                self.alpha_ref
            )
        )

        self.previous_R = None
        self.previous_timestamp_s = None

    def reset(self):
        self.previous_R = None
        self.previous_timestamp_s = None

    def alpha_for_dt(self, dt):
        return float(
            np.clip(
                1.0
                -
                math.exp(
                    -float(dt)
                    /
                    self.tau_s
                ),
                0.0,
                1.0,
            )
        )

    def update(
        self,
        raw_R,
        timestamp_s,
    ):
        raw_R = project_so3(
            raw_R
        )

        timestamp_s = float(
            timestamp_s
        )

        if not np.isfinite(
            timestamp_s
        ):
            raise ValueError(
                "timestamp must be finite"
            )

        reset = False
        alpha = 1.0
        dt = None

        if (
            self.previous_R is None
            or
            self.previous_timestamp_s is None
        ):
            filtered = (
                raw_R.copy()
            )

            reset = True

        else:
            dt = float(
                timestamp_s
                -
                self.previous_timestamp_s
            )

            if (
                not np.isfinite(dt)
                or
                dt <= 0.0
                or
                dt > self.reset_gap_s
            ):
                filtered = (
                    raw_R.copy()
                )

                reset = True

            else:
                alpha = (
                    self.alpha_for_dt(
                        dt
                    )
                )

                filtered = (
                    smooth_rotation(
                        self.previous_R,
                        raw_R,
                        alpha,
                    )
                )

        self.previous_R = (
            filtered.copy()
        )

        self.previous_timestamp_s = (
            timestamp_s
        )

        return {
            "R":
                filtered,
            "raw_R":
                raw_R,
            "timestamp_s":
                timestamp_s,
            "dt_s":
                dt,
            "alpha":
                float(alpha),
            "reset":
                bool(reset),
        }


def palm_frame_from_wilor_joints(
    joints,
    side,
    restore_left_handedness=True,
):
    """
    Construct the accepted anatomical WiLoR palm frame.

    WiLoR model output is canonical/right-like for the mirrored left
    crop.  When raw pred_keypoints_3d is supplied, left camera-space
    handedness therefore has to be restored exactly once.

    Frame columns:
        X = pinky MCP -> index MCP
            ("across palm")
        Y = wrist -> mean MCP center
            ("toward fingers")
        Z = X cross Y
            ("palm normal")
    """

    side = str(
        side
    ).upper()

    if side not in SIDES:
        raise ValueError(
            f"invalid side {side!r}"
        )

    J = np.asarray(
        joints,
        dtype=np.float64,
    ).copy()

    J = np.squeeze(
        J
    )

    if (
        J.ndim != 2
        or
        J.shape[0] < 18
        or
        J.shape[1] != 3
    ):
        raise ValueError(
            "WiLoR joints must have "
            f"shape >=(18,3), got {J.shape}"
        )

    if not np.all(
        np.isfinite(J)
    ):
        return None

    if (
        side == "L"
        and
        restore_left_handedness
    ):
        J[:, 0] *= -1.0

    wrist = J[0]

    index = J[5]
    middle = J[9]
    ring = J[13]
    pinky = J[17]

    center = np.mean(
        np.stack(
            (
                index,
                middle,
                ring,
                pinky,
            )
        ),
        axis=0,
    )

    y = normalize(
        center - wrist
    )

    if y is None:
        return None

    x_raw = (
        index
        -
        pinky
    )

    x_raw = (
        x_raw
        -
        np.dot(
            x_raw,
            y,
        )
        * y
    )

    x = normalize(
        x_raw
    )

    if x is None:
        return None

    z = normalize(
        np.cross(
            x,
            y,
        )
    )

    if z is None:
        return None

    x = normalize(
        np.cross(
            y,
            z,
        )
    )

    if x is None:
        return None

    return project_so3(
        np.column_stack(
            (
                x,
                y,
                z,
            )
        )
    )


def forearm_frame(
    shoulder,
    elbow,
    wrist,
    previous_z=None,
    straight_arm_sin_threshold=
        STRAIGHT_ARM_SIN_THRESHOLD,
):
    """
    Accepted position-only V2 forearm frame.

    X = elbow -> wrist
    Z = upper-arm/forearm plane normal
    Y = Z cross X

    Near a straight arm the bend plane is ill-conditioned, so the
    previous physical plane normal is projected perpendicular to the
    new longitudinal axis.
    """

    shoulder = np.asarray(
        shoulder,
        dtype=np.float64,
    ).reshape(3)

    elbow = np.asarray(
        elbow,
        dtype=np.float64,
    ).reshape(3)

    wrist = np.asarray(
        wrist,
        dtype=np.float64,
    ).reshape(3)

    x = normalize(
        wrist - elbow
    )

    upper = normalize(
        elbow - shoulder
    )

    if (
        x is None
        or
        upper is None
    ):
        return None

    z_raw = np.cross(
        upper,
        x,
    )

    bend_sin = float(
        np.linalg.norm(
            z_raw
        )
    )

    source = "geometry"

    if (
        np.isfinite(
            bend_sin
        )
        and
        bend_sin
        >= float(
            straight_arm_sin_threshold
        )
    ):
        z = normalize(
            z_raw
        )

        if z is None:
            return None

        if (
            previous_z is not None
            and
            np.dot(
                z,
                previous_z,
            )
            < 0.0
        ):
            z = -z

    else:
        if previous_z is None:
            return None

        previous_z = np.asarray(
            previous_z,
            dtype=np.float64,
        ).reshape(3)

        z_projected = (
            previous_z
            -
            np.dot(
                previous_z,
                x,
            )
            * x
        )

        z = normalize(
            z_projected
        )

        if z is None:
            return None

        source = "previous_plane"

    y = normalize(
        np.cross(
            z,
            x,
        )
    )

    if y is None:
        return None

    z = normalize(
        np.cross(
            x,
            y,
        )
    )

    if z is None:
        return None

    if (
        previous_z is not None
        and
        np.dot(
            z,
            previous_z,
        )
        < 0.0
    ):
        z = -z
        y = -y

    F = project_so3(
        np.column_stack(
            (
                x,
                y,
                z,
            )
        )
    )

    return {
        "F":
            F,
        "z":
            z.copy(),
        "bend_sin":
            bend_sin,
        "source":
            source,
    }


def build_anatomical_calibration(
    F_ref,
    H_ref,
):
    """
    Build the fixed explicit Q4 calibration.

        A_ref = F_ref.T @ H_ref

    The transverse wrist basis is aligned from the across-palm axis
    at this explicit reference rather than from the arbitrary
    upper-arm/forearm bend-plane twist.
    """

    F_ref = project_so3(
        F_ref
    )

    H_ref = project_so3(
        H_ref
    )

    A_ref = project_so3(
        F_ref.T
        @ H_ref
    )

    longitudinal = np.array(
        [
            1.0,
            0.0,
            0.0,
        ],
        dtype=np.float64,
    )

    across = (
        A_ref[:, 0]
        .copy()
    )

    across = (
        across
        -
        np.dot(
            across,
            longitudinal,
        )
        * longitudinal
    )

    flex_axis = normalize(
        across
    )

    if flex_axis is None:
        raise RuntimeError(
            "cannot construct anatomical "
            "across-palm calibration axis"
        )

    deviation_axis = normalize(
        np.cross(
            longitudinal,
            flex_axis,
        )
    )

    if deviation_axis is None:
        raise RuntimeError(
            "cannot construct anatomical "
            "deviation calibration axis"
        )

    flex_axis = normalize(
        np.cross(
            deviation_axis,
            longitudinal,
        )
    )

    if flex_axis is None:
        raise RuntimeError(
            "anatomical basis "
            "reorthogonalization failed"
        )

    # V10/V12 validated semantic basis.
    #
    # The original geometric candidate was:
    #
    #   [longitudinal, flex_axis, deviation_axis]
    #
    # Physical 3D replay established the corrected semantic mapping:
    #
    #   new X (axial)     =  old Z
    #   new Y (flex/ext)  = -old Y
    #   new Z (deviation) =  old X
    #
    # Therefore the equivalent direct right-handed basis is:
    #
    #   [deviation_axis, -flex_axis, longitudinal]
    #
    # This changes only the coordinate convention.  The explicit
    # reference A_ref and identity-at-calibration semantics remain
    # unchanged.
    Q_anatomical = project_so3(
        np.column_stack(
            (
                deviation_axis,
                -flex_axis,
                longitudinal,
            )
        )
    )

    anatomical_twist_deg = float(
        np.degrees(
            np.arctan2(
                flex_axis[2],
                flex_axis[1],
            )
        )
    )

    return {
        "A_ref":
            A_ref,
        "Q_anatomical":
            Q_anatomical,
        "anatomical_twist_deg":
            anatomical_twist_deg,
    }


def wrist_rotation_from_frames(
    F_now,
    H_now,
    calibration,
    side,
    canonicalize_bilateral=True,
):
    """
    Accepted Q4 fixed-reference wrist articulation.

        A_now      = F_now.T @ H_now
        R_forearm  = A_now @ A_ref.T
        R_anatomic = Q.T @ R_forearm @ Q

    Optional bilateral canonicalization then puts the left result into
    the same anatomical output convention as the right result.
    """

    side = str(
        side
    ).upper()

    if side not in SIDES:
        raise ValueError(
            f"invalid side {side!r}"
        )

    F_now = project_so3(
        F_now
    )

    H_now = project_so3(
        H_now
    )

    A_ref = project_so3(
        calibration[
            "A_ref"
        ]
    )

    Q = project_so3(
        calibration[
            "Q_anatomical"
        ]
    )

    A_now = project_so3(
        F_now.T
        @ H_now
    )

    R_forearm = project_so3(
        A_now
        @ A_ref.T
    )

    R_anatomical_native = (
        project_so3(
            Q.T
            @ R_forearm
            @ Q
        )
    )

    R_canonical = (
        R_anatomical_native
        .copy()
    )

    if (
        canonicalize_bilateral
        and
        side == "L"
    ):
        S = (
            LEFT_BILATERAL_CANONICAL
        )

        R_canonical = (
            project_so3(
                S.T
                @ R_canonical
                @ S
            )
        )

    return {
        "R":
            R_canonical,
        "R_native":
            R_anatomical_native,
        "R_forearm":
            R_forearm,
        "A_now":
            A_now,
        "rotvec_deg":
            rotvec_deg(
                R_canonical
            ),
        "relative_angle_deg":
            rotation_distance_deg(
                np.eye(3),
                R_canonical,
            ),
    }


@dataclass
class SideState:
    palm_filter: TimestampSO3Filter

    previous_forearm_z: np.ndarray | None = None

    latest_hand_timestamp_s: float | None = None
    latest_forearm_timestamp_s: float | None = None

    latest_H: np.ndarray | None = None
    latest_F: np.ndarray | None = None

    latest_forearm_source: str | None = None
    latest_bend_sin: float | None = None

    calibration: dict | None = None


class Q4WristOrientationRuntime:
    """
    Stateful reusable Q4 runtime.

    IMPORTANT ARCHITECTURE:

        WiLoR stream
            -> update_palm()

        V2 / FASTIK body stream
            -> update_forearm()

    These streams intentionally advance independently.

    The surrounding live system may then use the freshest compatible
    pair.  Q4 never requires the body loop to wait for WiLoR and never
    requires WiLoR filtering to wait for a body result.

    There is NO automatic neutral recognition.  Calibration occurs
    only through an explicit calibrate*() call.
    """

    def __init__(
        self,
        alpha_ref=DEFAULT_ALPHA_REF,
        reference_dt_s=DEFAULT_REFERENCE_DT_S,
        reset_gap_s=DEFAULT_RESET_GAP_S,
        straight_arm_sin_threshold=
            STRAIGHT_ARM_SIN_THRESHOLD,
        canonicalize_bilateral=True,
    ):
        self.alpha_ref = float(
            alpha_ref
        )

        self.reference_dt_s = float(
            reference_dt_s
        )

        self.reset_gap_s = float(
            reset_gap_s
        )

        self.straight_arm_sin_threshold = float(
            straight_arm_sin_threshold
        )

        self.canonicalize_bilateral = bool(
            canonicalize_bilateral
        )

        self.side = {
            s: SideState(
                palm_filter=
                    TimestampSO3Filter(
                        alpha_ref=
                            self.alpha_ref,
                        reference_dt_s=
                            self.reference_dt_s,
                        reset_gap_s=
                            self.reset_gap_s,
                    )
            )
            for s in SIDES
        }

    def _side(
        self,
        side,
    ):
        side = str(
            side
        ).upper()

        if side not in SIDES:
            raise ValueError(
                f"invalid side {side!r}"
            )

        return side

    def reset_tracking(
        self,
        side=None,
        keep_calibration=True,
    ):
        sides = (
            SIDES
            if side is None
            else (
                self._side(side),
            )
        )

        for s in sides:
            state = self.side[s]

            calibration = (
                state.calibration
                if keep_calibration
                else None
            )

            state.palm_filter.reset()

            state.previous_forearm_z = None

            state.latest_hand_timestamp_s = None
            state.latest_forearm_timestamp_s = None

            state.latest_H = None
            state.latest_F = None

            state.latest_forearm_source = None
            state.latest_bend_sin = None

            state.calibration = calibration

    def reset_calibration(
        self,
        side=None,
    ):
        sides = (
            SIDES
            if side is None
            else (
                self._side(side),
            )
        )

        for s in sides:
            self.side[
                s
            ].calibration = None

    # ========================================================
    # INDEPENDENT HAND STREAM
    # ========================================================

    def update_palm(
        self,
        side,
        timestamp_s,
        palm_R_raw,
    ):
        """
        Advance the timestamp-aware WiLoR SO(3) filter.

        Q5_26AM2_RAW_PALM_MOTION_GUARD_V1

        Normal observations pass into the accepted Q4 filter unchanged.

        An implausibly large isolated WiLoR palm rotation is held rather
        than injected into H.  A genuinely changed pose can still
        reacquire after several mutually coherent observations, with
        the source rotation advanced at a bounded rate.

        No automatic neutral/reset/calibration is introduced here.
        """

        side = self._side(
            side
        )

        state = self.side[
            side
        ]

        timestamp_s = float(
            timestamp_s
        )

        if not np.isfinite(
            timestamp_s
        ):
            raise ValueError(
                "timestamp must be finite"
            )

        raw_R = project_so3(
            palm_R_raw
        )

        # --------------------------------------------------------
        # Guard configuration.
        #
        # Q5.26AK stationary evidence:
        #   raw palm steps stayed below ~8 deg.
        #
        # Default allowance at 100 ms:
        #   10 + 240 * 0.1 = 34 deg.
        #
        # Therefore normal motion has large margin while the observed
        # 40–70 degree transient jumps are challenged.
        # --------------------------------------------------------

        if not hasattr(
            self,
            "_palm_motion_guard_config",
        ):
            self._palm_motion_guard_config = {
                "base_deg":
                    float(
                        os.environ.get(
                            "Q4_PALM_GUARD_BASE_DEG",
                            "10.0",
                        )
                    ),

                "rate_deg_s":
                    float(
                        os.environ.get(
                            "Q4_PALM_GUARD_RATE_DEG_S",
                            "240.0",
                        )
                    ),

                "hard_deg":
                    float(
                        os.environ.get(
                            "Q4_PALM_GUARD_HARD_DEG",
                            "60.0",
                        )
                    ),

                "coherence_deg":
                    float(
                        os.environ.get(
                            "Q4_PALM_GUARD_COHERENCE_DEG",
                            "20.0",
                        )
                    ),

                "reacquire_frames":
                    int(
                        os.environ.get(
                            "Q4_PALM_GUARD_REACQUIRE_FRAMES",
                            "3",
                        )
                    ),
            }

            cfg = (
                self._palm_motion_guard_config
            )

            if not (
                0.0
                <
                cfg["base_deg"]
                <=
                cfg["hard_deg"]
            ):
                raise ValueError(
                    "invalid palm guard base/hard threshold"
                )

            if (
                cfg["rate_deg_s"]
                <=
                0.0
            ):
                raise ValueError(
                    "palm guard rate must be > 0"
                )

            if (
                cfg["coherence_deg"]
                <=
                0.0
            ):
                raise ValueError(
                    "palm guard coherence must be > 0"
                )

            if (
                cfg["reacquire_frames"]
                <
                2
            ):
                raise ValueError(
                    "palm guard reacquire_frames must be >= 2"
                )


        if not hasattr(
            self,
            "_palm_motion_guard",
        ):
            self._palm_motion_guard = {
                s: {
                    "accepted_raw":
                        None,

                    "last_observation_timestamp_s":
                        None,

                    "pending_raw":
                        None,

                    "pending_count":
                        0,

                    "reacquiring":
                        False,
                }
                for s in SIDES
            }


        # Synchronize auxiliary state with an ordinary Q4 tracking
        # reset without altering reset_tracking() itself.
        if (
            state.latest_H is None
            or
            state.latest_hand_timestamp_s
            is None
        ):
            self._palm_motion_guard[
                side
            ] = {
                "accepted_raw":
                    None,

                "last_observation_timestamp_s":
                    None,

                "pending_raw":
                    None,

                "pending_count":
                    0,

                "reacquiring":
                    False,
            }


        guard = (
            self._palm_motion_guard[
                side
            ]
        )

        cfg = (
            self._palm_motion_guard_config
        )

        previous_ts = (
            guard[
                "last_observation_timestamp_s"
            ]
        )

        dt_s = (
            None
            if previous_ts is None
            else
            timestamp_s
            -
            float(
                previous_ts
            )
        )

        guard[
            "last_observation_timestamp_s"
        ] = timestamp_s

        accepted_raw = (
            guard[
                "accepted_raw"
            ]
        )

        raw_step_deg = None
        allowed_step_deg = None
        pending_step_deg = None

        accept = False
        bounded = False
        mode = "initial"


        # --------------------------------------------------------
        # First valid observation seeds the original filter.
        # --------------------------------------------------------

        if accepted_raw is None:

            candidate_raw = (
                raw_R.copy()
            )

            accept = True
            mode = "initial"


        else:

            raw_step_deg = (
                rotation_distance_deg(
                    accepted_raw,
                    raw_R,
                )
            )

            if (
                dt_s is None
                or
                not np.isfinite(
                    dt_s
                )
                or
                dt_s <= 0.0
            ):
                effective_dt_s = 0.0

            else:
                effective_dt_s = float(
                    dt_s
                )

            allowed_step_deg = min(
                float(
                    cfg[
                        "hard_deg"
                    ]
                ),
                float(
                    cfg[
                        "base_deg"
                    ]
                )
                +
                float(
                    cfg[
                        "rate_deg_s"
                    ]
                )
                *
                effective_dt_s,
            )


            # ----------------------------------------------------
            # Normal motion.
            # ----------------------------------------------------

            if (
                raw_step_deg
                <=
                allowed_step_deg
            ):

                candidate_raw = (
                    raw_R.copy()
                )

                accept = True
                mode = "normal"

                guard[
                    "pending_raw"
                ] = None

                guard[
                    "pending_count"
                ] = 0

                guard[
                    "reacquiring"
                ] = False


            # ----------------------------------------------------
            # Large raw step.
            # ----------------------------------------------------

            else:

                pending = (
                    guard[
                        "pending_raw"
                    ]
                )

                if pending is None:
                    coherent = False

                else:

                    pending_step_deg = (
                        rotation_distance_deg(
                            pending,
                            raw_R,
                        )
                    )

                    coherent = bool(
                        pending_step_deg
                        <=
                        float(
                            cfg[
                                "coherence_deg"
                            ]
                        )
                    )


                if coherent:

                    guard[
                        "pending_count"
                    ] += 1

                else:

                    guard[
                        "pending_count"
                    ] = 1

                    guard[
                        "reacquiring"
                    ] = False


                guard[
                    "pending_raw"
                ] = (
                    raw_R.copy()
                )


                if (
                    guard[
                        "reacquiring"
                    ]
                    or
                    guard[
                        "pending_count"
                    ]
                    >=
                    int(
                        cfg[
                            "reacquire_frames"
                        ]
                    )
                ):

                    # Coherent new pose: move the accepted RAW source
                    # toward it, but never jump there in one sample.

                    fraction = min(
                        1.0,
                        float(
                            allowed_step_deg
                        )
                        /
                        max(
                            float(
                                raw_step_deg
                            ),
                            1e-9,
                        ),
                    )

                    candidate_raw = (
                        smooth_rotation(
                            accepted_raw,
                            raw_R,
                            fraction,
                        )
                    )

                    accept = True
                    bounded = True

                    mode = (
                        "coherent_reacquire_bounded"
                    )

                    guard[
                        "reacquiring"
                    ] = True


                else:

                    accept = False
                    mode = "outlier_hold"


        # --------------------------------------------------------
        # Reject path.
        #
        # Preserve current H.
        #
        # We feed that held H into the filter only to advance the
        # filter timestamp.  latest_hand_timestamp_s deliberately
        # remains unchanged so the existing Q4 pair-age protection
        # can still age out rejected hand data.
        # --------------------------------------------------------

        if not accept:

            held_H = (
                state.latest_H.copy()
            )

            held_filter = (
                state.palm_filter.update(
                    held_H,
                    timestamp_s,
                )
            )

            return {
                "side":
                    side,

                "timestamp_s":
                    timestamp_s,

                "valid":
                    False,

                "reason":
                    "palm_motion_outlier_hold",

                "H":
                    held_H,

                "filter":
                    held_filter,

                "guard": {
                    "mode":
                        mode,

                    "raw_step_deg":
                        raw_step_deg,

                    "allowed_step_deg":
                        allowed_step_deg,

                    "pending_step_deg":
                        pending_step_deg,

                    "pending_count":
                        int(
                            guard[
                                "pending_count"
                            ]
                        ),

                    "reacquiring":
                        bool(
                            guard[
                                "reacquiring"
                            ]
                        ),

                    "bounded":
                        False,
                },
            }


        # --------------------------------------------------------
        # Accepted path — original timestamp-aware filter remains.
        # --------------------------------------------------------

        filtered = (
            state.palm_filter.update(
                candidate_raw,
                timestamp_s,
            )
        )

        H = (
            filtered[
                "R"
            ].copy()
        )

        state.latest_H = H

        state.latest_hand_timestamp_s = (
            timestamp_s
        )

        guard[
            "accepted_raw"
        ] = (
            candidate_raw.copy()
        )

        return {
            "side":
                side,

            "timestamp_s":
                timestamp_s,

            "valid":
                True,

            "reason":
                (
                    "ok_bounded_reacquire"
                    if bounded
                    else
                    "ok"
                ),

            "H":
                H,

            "filter":
                filtered,

            "guard": {
                "mode":
                    mode,

                "raw_step_deg":
                    raw_step_deg,

                "allowed_step_deg":
                    allowed_step_deg,

                "pending_step_deg":
                    pending_step_deg,

                "pending_count":
                    int(
                        guard[
                            "pending_count"
                        ]
                    ),

                "reacquiring":
                    bool(
                        guard[
                            "reacquiring"
                        ]
                    ),

                "bounded":
                    bool(
                        bounded
                    ),
            },
        }

    def update_wilor_joints(
        self,
        side,
        timestamp_s,
        wilor_joints,
        restore_left_handedness=True,
    ):
        """
        Convert raw WiLoR pred_keypoints_3d into the accepted palm
        frame and advance the independent hand filter.
        """

        side = self._side(
            side
        )

        H_raw = (
            palm_frame_from_wilor_joints(
                wilor_joints,
                side,
                restore_left_handedness=
                    restore_left_handedness,
            )
        )

        if H_raw is None:
            return {
                "side":
                    side,
                "timestamp_s":
                    float(timestamp_s),
                "valid":
                    False,
                "reason":
                    "palm_frame_unavailable",
            }

        return self.update_palm(
            side,
            timestamp_s,
            H_raw,
        )

    # ========================================================
    # INDEPENDENT V2 / FASTIK BODY STREAM
    # ========================================================

    def update_forearm(
        self,
        side,
        timestamp_s,
        shoulder,
        elbow,
        wrist,
    ):
        """
        Advance the forearm-frame state from one new V2 post-FASTIK
        body result.

        This must be called for EVERY usable new body result,
        irrespective of WiLoR cadence.
        """

        side = self._side(
            side
        )

        state = self.side[
            side
        ]

        # Q5_26AN_FOREARM_HYSTERESIS_V1
        #
        # The underlying forearm_frame() geometry is unchanged.
        #
        # We only choose a state-dependent effective threshold:
        #
        #   previous source = geometry
        #       use LOWER exit threshold so small noise near the
        #       boundary does not immediately force fallback.
        #
        #   previous source = previous_plane
        #       use HIGHER re-entry threshold so weak/ill-conditioned
        #       geometry does not immediately take ownership again.
        #
        #   no previous source
        #       use the original threshold exactly.
        #
        # Default hysteresis:
        #     geometry -> fallback at 0.75 * base
        #     fallback -> geometry at 1.50 * base
        #
        # This changes source-selection stability only.  It does not
        # change X/Y/Z construction, calibration, anatomical mapping,
        # left/right conventions, Q5, or SONIC.

        if not hasattr(
            self,
            "_forearm_hysteresis_config",
        ):
            self._forearm_hysteresis_config = {
                "exit_scale":
                    float(
                        os.environ.get(
                            "Q4_FOREARM_HYST_EXIT_SCALE",
                            "0.75",
                        )
                    ),

                "enter_scale":
                    float(
                        os.environ.get(
                            "Q4_FOREARM_HYST_ENTER_SCALE",
                            "1.50",
                        )
                    ),
            }

            cfg = (
                self._forearm_hysteresis_config
            )

            if not (
                0.0
                <
                cfg["exit_scale"]
                <
                1.0
            ):
                raise ValueError(
                    "Q4_FOREARM_HYST_EXIT_SCALE must be in (0,1)"
                )

            if not (
                cfg["enter_scale"]
                >
                1.0
            ):
                raise ValueError(
                    "Q4_FOREARM_HYST_ENTER_SCALE must be > 1"
                )

        base_threshold = float(
            self.straight_arm_sin_threshold
        )

        if not (
            np.isfinite(
                base_threshold
            )
            and
            0.0
            <
            base_threshold
            <
            1.0
        ):
            raise ValueError(
                "invalid straight_arm_sin_threshold"
            )

        previous_source = (
            state.latest_forearm_source
        )

        if (
            previous_source
            ==
            "geometry"
        ):
            effective_threshold = (
                base_threshold
                *
                float(
                    self._forearm_hysteresis_config[
                        "exit_scale"
                    ]
                )
            )

            hysteresis_mode = (
                "geometry_hold"
            )

        elif (
            previous_source
            ==
            "previous_plane"
        ):
            effective_threshold = min(
                0.999999,
                base_threshold
                *
                float(
                    self._forearm_hysteresis_config[
                        "enter_scale"
                    ]
                ),
            )

            hysteresis_mode = (
                "previous_plane_hold"
            )

        else:
            effective_threshold = (
                base_threshold
            )

            hysteresis_mode = (
                "initial"
            )

        built = (
            forearm_frame(
                shoulder,
                elbow,
                wrist,
                previous_z=
                    state.previous_forearm_z,
                straight_arm_sin_threshold=
                    effective_threshold,
            )
        )

        if built is None:
            return {
                "side":
                    side,
                "timestamp_s":
                    float(timestamp_s),
                "valid":
                    False,
                "reason":
                    "forearm_frame_unavailable",
            }

        F = (
            built[
                "F"
            ].copy()
        )

        state.previous_forearm_z = (
            built[
                "z"
            ].copy()
        )

        state.latest_F = F

        state.latest_forearm_timestamp_s = float(
            timestamp_s
        )

        state.latest_forearm_source = (
            built[
                "source"
            ]
        )

        state.latest_bend_sin = float(
            built[
                "bend_sin"
            ]
        )

        return {
            "side":
                side,
            "timestamp_s":
                float(timestamp_s),
            "valid":
                True,
            "reason":
                "ok",
            "F":
                F,
            "forearm_source":
                built[
                    "source"
                ],
            "forearm_bend_sin":
                float(
                    built[
                        "bend_sin"
                    ]
                ),

            "forearm_threshold_sin":
                float(
                    effective_threshold
                ),

            "forearm_hysteresis_mode":
                hysteresis_mode,
        }

    # ========================================================
    # PAIRING / CALIBRATION
    # ========================================================

    def pair_ready(
        self,
        side,
    ):
        side = self._side(
            side
        )

        state = self.side[
            side
        ]

        return bool(
            state.latest_H is not None
            and
            state.latest_F is not None
            and
            state.latest_hand_timestamp_s is not None
            and
            state.latest_forearm_timestamp_s is not None
        )

    def latest_pair_age_s(
        self,
        side,
    ):
        side = self._side(
            side
        )

        if not self.pair_ready(
            side
        ):
            return None

        state = self.side[
            side
        ]

        return abs(
            float(
                state.latest_hand_timestamp_s
            )
            -
            float(
                state.latest_forearm_timestamp_s
            )
        )

    def set_calibration_from_frames(
        self,
        side,
        F_ref,
        H_ref,
        timestamp_s=None,
    ):
        """
        Explicitly set Q4 calibration from one already-paired
        forearm/palm observation.

        Used by deterministic replay and also useful when a live
        controller has explicitly selected the calibration pair.
        """

        side = self._side(
            side
        )

        calibration = (
            build_anatomical_calibration(
                F_ref,
                H_ref,
            )
        )

        if timestamp_s is not None:
            calibration[
                "timestamp_s"
            ] = float(
                timestamp_s
            )

        self.side[
            side
        ].calibration = calibration

        return {
            "side":
                side,
            **calibration,
        }

    def calibrate(
        self,
        side,
        max_pair_age_s=0.200,
    ):
        """
        Explicit calibration from the latest compatible live pair.
        """

        side = self._side(
            side
        )

        if not self.pair_ready(
            side
        ):
            raise RuntimeError(
                f"{side}: no valid hand/body pair "
                "available for explicit calibration"
            )

        pair_age_s = (
            self.latest_pair_age_s(
                side
            )
        )

        if (
            pair_age_s
            > float(
                max_pair_age_s
            )
        ):
            raise RuntimeError(
                f"{side}: hand/body calibration samples are "
                f"{pair_age_s:.3f}s apart"
            )

        state = self.side[
            side
        ]

        out = (
            self.set_calibration_from_frames(
                side,
                state.latest_F,
                state.latest_H,
                timestamp_s=
                    state.latest_hand_timestamp_s,
            )
        )

        out[
            "pair_age_s"
        ] = float(
            pair_age_s
        )

        return out

    def calibrate_both(
        self,
        max_pair_age_s=0.200,
    ):
        """
        Explicit bilateral calibration.

        Both hands and both body forearms must already have valid
        latest observations.  No automatic neutral recognition.
        """

        for side in SIDES:
            if not self.pair_ready(
                side
            ):
                raise RuntimeError(
                    "both hands require valid hand/body "
                    "observations before bilateral calibration"
                )

        bilateral_hand_age_s = abs(
            float(
                self.side[
                    "L"
                ].latest_hand_timestamp_s
            )
            -
            float(
                self.side[
                    "R"
                ].latest_hand_timestamp_s
            )
        )

        if (
            bilateral_hand_age_s
            > float(
                max_pair_age_s
            )
        ):
            raise RuntimeError(
                "left/right hand calibration observations are "
                f"{bilateral_hand_age_s:.3f}s apart"
            )

        L = self.calibrate(
            "L",
            max_pair_age_s=
                max_pair_age_s,
        )

        R = self.calibrate(
            "R",
            max_pair_age_s=
                max_pair_age_s,
        )

        return {
            "L":
                L,
            "R":
                R,
            "pair_age_s":
                bilateral_hand_age_s,
        }

    # ========================================================
    # Q4 ARTICULATION
    # ========================================================

    def compute_from_frames(
        self,
        side,
        F,
        H,
    ):
        """
        Compute Q4 from an explicitly paired forearm frame and
        filtered palm frame.

        Does not update either stream.
        """

        side = self._side(
            side
        )

        calibration = (
            self.side[
                side
            ].calibration
        )

        if calibration is None:
            return {
                "side":
                    side,
                "valid":
                    True,
                "calibrated":
                    False,
                "reason":
                    "not_calibrated",
            }

        wrist = (
            wrist_rotation_from_frames(
                F,
                H,
                calibration,
                side,
                canonicalize_bilateral=
                    self.canonicalize_bilateral,
            )
        )

        return {
            "side":
                side,
            "valid":
                True,
            "calibrated":
                True,
            "reason":
                "ok",
            **wrist,
        }

    def compute_latest(
        self,
        side,
        max_pair_age_s=None,
    ):
        """
        Compute Q4 from the latest independently-updated hand/body
        states.  Intended for live latest-only use.
        """

        side = self._side(
            side
        )

        if not self.pair_ready(
            side
        ):
            return {
                "side":
                    side,
                "valid":
                    False,
                "calibrated":
                    self.is_calibrated(
                        side
                    ),
                "reason":
                    "pair_unavailable",
            }

        state = self.side[
            side
        ]

        pair_age_s = (
            self.latest_pair_age_s(
                side
            )
        )

        if (
            max_pair_age_s is not None
            and
            pair_age_s
            > float(
                max_pair_age_s
            )
        ):
            return {
                "side":
                    side,
                "valid":
                    False,
                "calibrated":
                    self.is_calibrated(
                        side
                    ),
                "reason":
                    "pair_too_old",
                "pair_age_s":
                    float(
                        pair_age_s
                    ),
            }

        result = (
            self.compute_from_frames(
                side,
                state.latest_F,
                state.latest_H,
            )
        )

        result.update(
            {
                "hand_timestamp_s":
                    float(
                        state.latest_hand_timestamp_s
                    ),
                "forearm_timestamp_s":
                    float(
                        state.latest_forearm_timestamp_s
                    ),
                "pair_age_s":
                    float(
                        pair_age_s
                    ),
                "forearm_source":
                    state.latest_forearm_source,
                "forearm_bend_sin":
                    state.latest_bend_sin,
            }
        )

        return result

    # ========================================================
    # BACKWARD-COMPATIBLE SYNCHRONOUS CONVENIENCE CALLS
    # ========================================================

    def observe(
        self,
        side,
        timestamp_s,
        shoulder,
        elbow,
        wrist,
        palm_R_raw,
    ):
        """
        Convenience path when hand and body genuinely belong to the
        same capture timestamp.

        Final async integration should normally call update_palm()
        and update_forearm() independently instead.
        """

        hand = self.update_palm(
            side,
            timestamp_s,
            palm_R_raw,
        )

        body = self.update_forearm(
            side,
            timestamp_s,
            shoulder,
            elbow,
            wrist,
        )

        if not body[
            "valid"
        ]:
            return {
                **body,
                "calibrated":
                    self.is_calibrated(
                        side
                    ),
                "filter":
                    hand[
                        "filter"
                    ],
            }

        result = self.compute_latest(
            side
        )

        result[
            "filter"
        ] = hand[
            "filter"
        ]

        return result

    def observe_wilor_joints(
        self,
        side,
        timestamp_s,
        shoulder,
        elbow,
        wrist,
        wilor_joints,
        restore_left_handedness=True,
    ):
        side = self._side(
            side
        )

        hand = self.update_wilor_joints(
            side,
            timestamp_s,
            wilor_joints,
            restore_left_handedness=
                restore_left_handedness,
        )

        if not hand[
            "valid"
        ]:
            return {
                **hand,
                "calibrated":
                    self.is_calibrated(
                        side
                    ),
            }

        body = self.update_forearm(
            side,
            timestamp_s,
            shoulder,
            elbow,
            wrist,
        )

        if not body[
            "valid"
        ]:
            return {
                **body,
                "calibrated":
                    self.is_calibrated(
                        side
                    ),
                "filter":
                    hand[
                        "filter"
                    ],
            }

        result = self.compute_latest(
            side
        )

        result[
            "filter"
        ] = hand[
            "filter"
        ]

        return result

    def is_calibrated(
        self,
        side=None,
    ):
        if side is None:
            return all(
                self.side[
                    s
                ].calibration
                is not None
                for s in SIDES
            )

        side = self._side(
            side
        )

        return (
            self.side[
                side
            ].calibration
            is not None
        )
