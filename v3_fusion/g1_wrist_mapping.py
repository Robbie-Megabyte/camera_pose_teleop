from __future__ import annotations

from dataclasses import dataclass
import warnings
from typing import Dict

import numpy as np
from scipy.spatial.transform import Rotation


# ---------------------------------------------------------------------
# SONIC / G1 Protocol-v3 wrist slots in the 29-DOF IsaacLab ordering.
#
#   23 left_wrist_roll
#   24 right_wrist_roll
#   25 left_wrist_pitch
#   26 right_wrist_pitch
#   27 left_wrist_yaw
#   28 right_wrist_yaw
#
# fields["wrists"] therefore uses the six-value order:
#
#   [L_roll, R_roll, L_pitch, R_pitch, L_yaw, R_yaw]
# ---------------------------------------------------------------------

WRIST_FIELD_ORDER = (
    "left_wrist_roll_joint",
    "right_wrist_roll_joint",
    "left_wrist_pitch_joint",
    "right_wrist_pitch_joint",
    "left_wrist_yaw_joint",
    "right_wrist_yaw_joint",
)


# G1 limits from g1_supplemental_info.py.
G1_WRIST_LIMITS_RAD = {
    "roll": (
        -1.972222054,
        +1.972222054,
    ),
    "pitch": (
        -1.614429558,
        +1.614429558,
    ),
    "yaw": (
        -1.614429558,
        +1.614429558,
    ),
}


# ---------------------------------------------------------------------
# Side convention.
#
# The existing SONIC Pico -> G1 path ultimately maps its wrist
# orientation contribution as:
#
#   LEFT : +X, +Y, +Z
#   RIGHT: -X, -Y, +Z
#
# Q4 has already removed forearm motion, so unlike the old Pico/SMPL
# path we DO NOT add elbow swing here.
# ---------------------------------------------------------------------

_SIDE_SIGNS = {
    "L": np.array(
        [
            +1.0,  # roll / anatomical X
            +1.0,  # pitch / anatomical Y
            +1.0,  # yaw / anatomical Z
        ],
        dtype=np.float64,
    ),

    "R": np.array(
        [
            -1.0,  # roll / anatomical X
            -1.0,  # pitch / anatomical Y
            +1.0,  # yaw / anatomical Z
        ],
        dtype=np.float64,
    ),
}


@dataclass(frozen=True)
class G1WristAngles:
    roll: float
    pitch: float
    yaw: float

    def as_array(
        self,
    ) -> np.ndarray:
        return np.array(
            [
                self.roll,
                self.pitch,
                self.yaw,
            ],
            dtype=np.float32,
        )


def _project_so3(
    R: np.ndarray,
) -> np.ndarray:
    R = np.asarray(
        R,
        dtype=np.float64,
    ).reshape(3, 3)

    U, _, Vt = np.linalg.svd(
        R,
    )

    out = U @ Vt

    if np.linalg.det(out) < 0.0:
        U[:, -1] *= -1.0
        out = U @ Vt

    return out


def _clip(
    value: float,
    joint: str,
) -> float:
    lo, hi = (
        G1_WRIST_LIMITS_RAD[
            joint
        ]
    )

    return float(
        np.clip(
            value,
            lo,
            hi,
        )
    )


def _wrap_pi(
    angle: float,
) -> float:
    return float(
        (
            float(angle)
            + np.pi
        )
        %
        (
            2.0
            *
            np.pi
        )
        -
        np.pi
    )


def _xyz_euler_candidates(
    R: np.ndarray,
):
    """Return the two equivalent intrinsic-XYZ Euler branches.

    SciPy returns the canonical branch whose middle angle is
    approximately [-pi/2, +pi/2].

    A serial XYZ joint chain also admits the complementary solution.
    We need to consider that second branch because the G1 wrist pitch
    limit extends slightly beyond 90 degrees.
    """

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="Gimbal lock detected.*",
        )

        base = np.asarray(
            Rotation
            .from_matrix(R)
            .as_euler(
                "XYZ",
                degrees=False,
            ),
            dtype=np.float64,
        )

    a, b, c = [
        float(v)
        for v in base
    ]

    if b >= 0.0:
        b_alt = (
            np.pi
            -
            b
        )
    else:
        b_alt = (
            -np.pi
            -
            b
        )

    alternate = np.array(
        [
            _wrap_pi(
                a
                +
                np.pi
            ),
            b_alt,
            _wrap_pi(
                c
                +
                np.pi
            ),
        ],
        dtype=np.float64,
    )

    return (
        base,
        alternate,
    )


def _limit_violation_score(
    q: np.ndarray,
) -> float:
    joints = (
        "roll",
        "pitch",
        "yaw",
    )

    score = 0.0

    for value, joint in zip(
        q,
        joints,
    ):
        lo, hi = (
            G1_WRIST_LIMITS_RAD[
                joint
            ]
        )

        value = float(
            value
        )

        if value < lo:
            d = (
                lo
                -
                value
            )
            score += (
                d
                *
                d
            )

        elif value > hi:
            d = (
                value
                -
                hi
            )
            score += (
                d
                *
                d
            )

    return float(
        score
    )


def _select_g1_xyz_solution(
    side: str,
    R: np.ndarray,
) -> np.ndarray:
    """Choose the physically useful XYZ branch for the G1 wrist.

    Priority:

      1. smallest violation of G1 joint limits
      2. smallest joint displacement from calibration-neutral

    This prevents the canonical Euler representation from turning a
    pitch slightly beyond 90 degrees into ~180-degree roll/yaw values.
    """

    candidates = []

    for xyz in _xyz_euler_candidates(
        R
    ):
        q = (
            _SIDE_SIGNS[
                side
            ]
            *
            xyz
        )

        candidates.append(
            q
        )

    best = min(
        candidates,
        key=lambda q: (
            _limit_violation_score(
                q
            ),
            float(
                np.dot(
                    q,
                    q,
                )
            ),
        ),
    )

    return np.asarray(
        best,
        dtype=np.float64,
    )


def canonical_rotation_to_g1(
    side: str,
    R_canonical: np.ndarray,
    *,
    clamp: bool = True,
) -> G1WristAngles:
    """Convert one Q4 canonical wrist rotation to G1 wrist joints.

    Parameters
    ----------
    side:
        "L" or "R".

    R_canonical:
        Q4's calibrated, forearm-relative, canonical human wrist
        orientation.

        Q4 semantic axes:

            X = pronation / supination
            Y = flexion / extension
            Z = radial / ulnar deviation

    clamp:
        Clamp to the physical G1 wrist limits.

    Returns
    -------
    G1WristAngles
        Absolute G1 reference joint positions in radians, relative
        to the Q4 calibration neutral.

    Notes
    -----
    The G1 wrist is a serial local-axis chain:

        roll  -> X
        pitch -> Y
        yaw   -> Z

    SONIC's existing wrist code uses intrinsic "XYZ" wrist angles.

    Both mathematically equivalent XYZ Euler branches are evaluated.
    We select the solution with the smallest G1-limit violation and,
    when both are valid, the one closest to calibration-neutral.

    Q4 has already removed forearm orientation. Do NOT add elbow
    swing or shoulder/forearm terms here.
    """

    side = str(
        side
    ).upper()

    if side not in _SIDE_SIGNS:
        raise ValueError(
            f"side must be 'L' or 'R', got {side!r}"
        )

    R_so3 = _project_so3(
        R_canonical
    )

    q = (
        _select_g1_xyz_solution(
            side,
            R_so3,
        )
    )

    roll = float(q[0])
    pitch = float(q[1])
    yaw = float(q[2])

    if clamp:
        roll = _clip(
            roll,
            "roll",
        )
        pitch = _clip(
            pitch,
            "pitch",
        )
        yaw = _clip(
            yaw,
            "yaw",
        )

    return G1WristAngles(
        roll=roll,
        pitch=pitch,
        yaw=yaw,
    )



@dataclass(frozen=True)
class G1WristMappingResult:
    """One stateful Q4 -> G1 wrist conversion."""

    raw: G1WristAngles
    command: G1WristAngles
    clamped: bool
    branch: int
    rotation_error_deg: float


def _angles_from_array(
    q: np.ndarray,
) -> G1WristAngles:
    q = np.asarray(
        q,
        dtype=np.float64,
    ).reshape(3)

    return G1WristAngles(
        roll=float(q[0]),
        pitch=float(q[1]),
        yaw=float(q[2]),
    )


def _clip_vector(
    q: np.ndarray,
) -> np.ndarray:
    q = np.asarray(
        q,
        dtype=np.float64,
    ).reshape(3)

    return np.array(
        [
            _clip(
                q[0],
                "roll",
            ),
            _clip(
                q[1],
                "pitch",
            ),
            _clip(
                q[2],
                "yaw",
            ),
        ],
        dtype=np.float64,
    )


def _canonical_matrix_from_g1_q(
    side: str,
    q: np.ndarray,
) -> np.ndarray:
    """Reconstruct canonical wrist orientation from G1 joint values."""

    q = np.asarray(
        q,
        dtype=np.float64,
    ).reshape(3)

    # _SIDE_SIGNS contains only +/-1, so its own inverse is itself.
    canonical_xyz = (
        _SIDE_SIGNS[
            side
        ]
        *
        q
    )

    return (
        Rotation
        .from_euler(
            "XYZ",
            canonical_xyz,
            degrees=False,
        )
        .as_matrix()
    )


def _rotation_error_rad(
    target_R: np.ndarray,
    candidate_R: np.ndarray,
) -> float:
    rel = (
        np.asarray(
            candidate_R,
            dtype=np.float64,
        ).T
        @
        np.asarray(
            target_R,
            dtype=np.float64,
        )
    )

    return float(
        Rotation
        .from_matrix(rel)
        .magnitude()
    )



def _singular_xyz_near_previous(
    R: np.ndarray,
    previous_xyz: np.ndarray,
    *,
    singular_tol: float = 1e-8,
):
    """Resolve the intrinsic-XYZ gimbal singularity continuously.

    At pitch = +pi/2:
        only roll + yaw is observable.

    At pitch = -pi/2:
        only yaw - roll is observable.

    There are infinitely many exact Euler solutions at the
    singularity.  Select the one nearest the previous continuous
    XYZ state.

    Returns None when the rotation is not at the singularity.
    """

    R = np.asarray(
        R,
        dtype=np.float64,
    ).reshape(3, 3)

    previous_xyz = np.asarray(
        previous_xyz,
        dtype=np.float64,
    ).reshape(3)

    # For intrinsic XYZ:
    #
    #     R[0, 2] = sin(pitch)
    #
    sin_pitch = float(
        np.clip(
            R[0, 2],
            -1.0,
            +1.0,
        )
    )

    if (
        abs(
            abs(
                sin_pitch
            )
            -
            1.0
        )
        >
        float(
            singular_tol
        )
    ):
        return None

    prev_roll = float(
        previous_xyz[0]
    )

    prev_yaw = float(
        previous_xyz[2]
    )

    # At both singularities these two matrix terms encode the
    # remaining observable roll/yaw combination.
    theta = float(
        np.arctan2(
            R[1, 0],
            R[1, 1],
        )
    )

    two_pi = (
        2.0
        *
        np.pi
    )

    if sin_pitch >= 0.0:
        # pitch = +pi/2
        #
        # Constraint:
        #
        #     roll + yaw = theta
        #
        # Pick the equivalent 2*pi branch nearest the previous
        # roll+yaw sum, then minimize displacement of roll/yaw.
        previous_sum = (
            prev_roll
            +
            prev_yaw
        )

        theta = (
            theta
            +
            two_pi
            *
            round(
                (
                    previous_sum
                    -
                    theta
                )
                /
                two_pi
            )
        )

        roll = 0.5 * (
            theta
            +
            prev_roll
            -
            prev_yaw
        )

        yaw = 0.5 * (
            theta
            -
            prev_roll
            +
            prev_yaw
        )

        pitch = (
            np.pi
            /
            2.0
        )

    else:
        # pitch = -pi/2
        #
        # Constraint:
        #
        #     yaw - roll = theta
        #
        previous_difference = (
            prev_yaw
            -
            prev_roll
        )

        theta = (
            theta
            +
            two_pi
            *
            round(
                (
                    previous_difference
                    -
                    theta
                )
                /
                two_pi
            )
        )

        roll = 0.5 * (
            prev_roll
            +
            prev_yaw
            -
            theta
        )

        yaw = 0.5 * (
            prev_roll
            +
            prev_yaw
            +
            theta
        )

        pitch = (
            -np.pi
            /
            2.0
        )

    return np.array(
        [
            roll,
            pitch,
            yaw,
        ],
        dtype=np.float64,
    )



def _unwrap_g1_euler_near(
    q: np.ndarray,
    reference: np.ndarray,
) -> np.ndarray:
    """Lift a G1 Euler triple continuously near a previous target.

    Adding integer multiples of 2*pi does not change the represented
    SO(3) orientation, but it DOES matter for a limited physical joint.

    Example:
        previous desired roll = +181 deg
        new principal Euler   = -178 deg

    The continuous physical target is +182 deg, not -178 deg.

    The physical command can then remain saturated at +roll_limit
    instead of teleporting to the negative limit.
    """

    q = np.asarray(
        q,
        dtype=np.float64,
    ).reshape(3)

    reference = np.asarray(
        reference,
        dtype=np.float64,
    ).reshape(3)

    two_pi = (
        2.0
        *
        np.pi
    )

    return (
        q
        +
        two_pi
        *
        np.round(
            (
                reference
                -
                q
            )
            /
            two_pi
        )
    )


class StatefulG1WristMapper:
    """Continuous live Q4 -> G1 wrist mapper.

    The same wrist orientation can have two equivalent intrinsic-XYZ
    Euler representations.  A stateless per-frame selector can jump
    between them.

    This mapper instead:

      1. evaluates both valid XYZ branches;
      2. applies the physical G1 limits;
      3. finds the branch producing the smallest orientation error;
      4. among effectively equivalent candidates, chooses the command
         closest to the previous commanded wrist state.

    State is separate for left and right wrists.

    No recording-specific knowledge is used.
    """

    def __init__(
        self,
        *,
        clamp: bool = True,
        equivalent_error_tol_rad: float = 1e-7,
    ):
        self.clamp = bool(
            clamp
        )

        self.equivalent_error_tol_rad = float(
            equivalent_error_tol_rad
        )

        self.previous_command = {
            "L": None,
            "R": None,
        }

        self.previous_unwrapped = {
            "L": None,
            "R": None,
        }

    def reset(
        self,
        side=None,
    ):
        """Reset branch-continuity state.

        In the final runtime this should normally happen only for an
        explicit new calibration/session, not for brief tracking loss.
        """

        if side is None:
            self.previous_command[
                "L"
            ] = None

            self.previous_command[
                "R"
            ] = None

            return

        side = str(
            side
        ).upper()

        if side not in self.previous_command:
            raise ValueError(
                f"side must be 'L' or 'R', got {side!r}"
            )

        self.previous_command[
            side
        ] = None

    def map_rotation(
        self,
        side: str,
        R_canonical: np.ndarray,
    ) -> G1WristMappingResult:

        side = str(
            side
        ).upper()

        if side not in _SIDE_SIGNS:
            raise ValueError(
                f"side must be 'L' or 'R', got {side!r}"
            )

        target_R = _project_so3(
            R_canonical
        )

        previous_command = (
            self.previous_command[
                side
            ]
        )

        # A reset of previous_command also means a new continuity
        # session, even if an old previous_unwrapped value happened
        # to remain in memory.
        if previous_command is None:
            previous_unwrapped = None
        else:
            previous_unwrapped = (
                self.previous_unwrapped[
                    side
                ]
            )

        xyz_candidates = list(
            _xyz_euler_candidates(
                target_R
            )
        )

        # ----------------------------------------------------
        # Exact XYZ singularity:
        #
        # use the previous UNWRAPPED desired state, not the clipped
        # physical command, to preserve the continuous target.
        # ----------------------------------------------------

        if previous_unwrapped is not None:

            previous_xyz = (
                _SIDE_SIGNS[
                    side
                ]
                *
                np.asarray(
                    previous_unwrapped,
                    dtype=np.float64,
                )
            )

            singular_xyz = (
                _singular_xyz_near_previous(
                    target_R,
                    previous_xyz,
                )
            )

            if singular_xyz is not None:
                xyz_candidates.append(
                    singular_xyz
                )

        branch_data = []

        for branch_index, xyz in enumerate(
            xyz_candidates
        ):

            raw_q = (
                _SIDE_SIGNS[
                    side
                ]
                *
                np.asarray(
                    xyz,
                    dtype=np.float64,
                )
            )

            # ------------------------------------------------
            # The key live-runtime operation:
            #
            # lift this mathematically equivalent Euler solution
            # onto the continuous joint trajectory nearest the
            # previous DESIRED state.
            # ------------------------------------------------

            if previous_unwrapped is not None:
                raw_q = (
                    _unwrap_g1_euler_near(
                        raw_q,
                        previous_unwrapped,
                    )
                )

            if self.clamp:
                command_q = (
                    _clip_vector(
                        raw_q
                    )
                )
            else:
                command_q = raw_q.copy()

            reconstructed_R = (
                _canonical_matrix_from_g1_q(
                    side,
                    command_q,
                )
            )

            error_rad = (
                _rotation_error_rad(
                    target_R,
                    reconstructed_R,
                )
            )

            # Amount by which this exact desired Euler solution lies
            # outside the physical G1 joint range.
            clipped_for_violation = (
                _clip_vector(
                    raw_q
                )
            )

            violation = (
                raw_q
                -
                clipped_for_violation
            )

            violation_score = float(
                np.dot(
                    violation,
                    violation,
                )
            )

            branch_data.append(
                {
                    "branch":
                        int(
                            branch_index
                        ),

                    "raw":
                        np.asarray(
                            raw_q,
                            dtype=np.float64,
                        ),

                    "command":
                        np.asarray(
                            command_q,
                            dtype=np.float64,
                        ),

                    "error_rad":
                        float(
                            error_rad
                        ),

                    "violation_score":
                        violation_score,
                }
            )

        if not branch_data:
            raise RuntimeError(
                "no G1 wrist Euler candidates"
            )

        # ----------------------------------------------------
        # First frame after calibration/reset.
        #
        # There is no temporal branch history yet, so retain the
        # original semantics:
        #   1. smallest joint-limit violation
        #   2. nearest neutral
        # ----------------------------------------------------

        if previous_unwrapped is None:

            selected = min(
                branch_data,
                key=lambda item: (
                    item[
                        "violation_score"
                    ],

                    float(
                        np.dot(
                            item[
                                "raw"
                            ],
                            item[
                                "raw"
                            ],
                        )
                    ),
                ),
            )

        # ----------------------------------------------------
        # Live frames.
        #
        # Both XYZ candidates represent exactly the same Q4
        # orientation before physical limiting.
        #
        # Select by continuity of the DESIRED physical joint
        # coordinates, not by whichever independently-clipped
        # representation happens to have lower SO(3) error.
        # ----------------------------------------------------

        else:

            previous_unwrapped = np.asarray(
                previous_unwrapped,
                dtype=np.float64,
            )

            selected = min(
                branch_data,
                key=lambda item: float(
                    np.dot(
                        item[
                            "raw"
                        ]
                        -
                        previous_unwrapped,
                        item[
                            "raw"
                        ]
                        -
                        previous_unwrapped,
                    )
                ),
            )

        raw_q = np.asarray(
            selected[
                "raw"
            ],
            dtype=np.float64,
        )

        command_q = np.asarray(
            selected[
                "command"
            ],
            dtype=np.float64,
        )

        # Q5_ANTI_WINDUP_REACHABLE_CONTINUITY_V1
        #
        # Euler continuity must be anchored to a PHYSICALLY REACHABLE
        # wrist state.
        #
        # Keeping the unclipped raw_q here allows the continuity state
        # to wind up outside the G1 joint limits.  Future equivalent
        # Euler solutions then unwrap toward that unreachable state and
        # can remain permanently pinned at the same hard limits even
        # after the Q4 orientation has returned to a valid range.
        #
        # command_q is the selected solution after physical clipping,
        # so it is the correct reachable state from which to continue.
        self.previous_unwrapped[
            side
        ] = command_q.copy()

        self.previous_command[
            side
        ] = command_q.copy()

        return G1WristMappingResult(
            raw=_angles_from_array(
                raw_q
            ),

            command=_angles_from_array(
                command_q
            ),

            clamped=bool(
                np.max(
                    np.abs(
                        raw_q
                        -
                        command_q
                    )
                )
                >
                1e-8
            ),

            branch=int(
                selected[
                    "branch"
                ]
            ),

            rotation_error_deg=float(
                np.degrees(
                    selected[
                        "error_rad"
                    ]
                )
            ),
        )

    def map_pair(
        self,
        R_left: np.ndarray,
        R_right: np.ndarray,
    ):
        left = self.map_rotation(
            "L",
            R_left,
        )

        right = self.map_rotation(
            "R",
            R_right,
        )

        wrists = pack_sonic_wrists(
            left.command,
            right.command,
        )

        return {
            "L": left,
            "R": right,
            "wrists": wrists,
        }


def pack_sonic_wrists(
    left: G1WristAngles,
    right: G1WristAngles,
) -> np.ndarray:
    """Pack both wrists exactly as joint_pos[:, 23:29] expects.

    Order:

        [L_roll,
         R_roll,
         L_pitch,
         R_pitch,
         L_yaw,
         R_yaw]
    """

    return np.array(
        [
            [
                left.roll,
                right.roll,
                left.pitch,
                right.pitch,
                left.yaw,
                right.yaw,
            ]
        ],
        dtype=np.float32,
    )


def canonical_pair_to_sonic_wrists(
    R_left: np.ndarray,
    R_right: np.ndarray,
    *,
    clamp: bool = True,
) -> Dict[str, object]:
    left = canonical_rotation_to_g1(
        "L",
        R_left,
        clamp=clamp,
    )

    right = canonical_rotation_to_g1(
        "R",
        R_right,
        clamp=clamp,
    )

    wrists = pack_sonic_wrists(
        left,
        right,
    )

    return {
        "L": left,
        "R": right,
        "wrists": wrists,
    }
