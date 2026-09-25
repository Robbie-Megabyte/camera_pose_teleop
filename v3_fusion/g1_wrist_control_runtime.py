from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from v3_fusion.g1_wrist_mapping import (
    StatefulG1WristMapper,
    G1WristAngles,
    pack_sonic_wrists,
)

from v3_fusion.wrist_command_runtime import (
    G1WristCommandSlewLimiter,
)


# ------------------------------------------------------------
# Source-confirmed G1 URDF joint velocity limits.
#
# These are HARD model limits, not our desired teleoperation speed.
# The runtime teleop speed must remain <= these values.
# ------------------------------------------------------------

G1_WRIST_HARD_VELOCITY_LIMITS_RAD_S = np.array(
    [
        37.0,  # roll
        22.0,  # pitch
        22.0,  # yaw
    ],
    dtype=np.float64,
)


def _angles_array(
    q: G1WristAngles,
) -> np.ndarray:

    return np.asarray(
        q.as_array(),
        dtype=np.float64,
    ).reshape(3)


@dataclass(frozen=True)
class WristSideControlResult:
    side: str

    mapped_target: G1WristAngles
    command: G1WristAngles

    trust_state: str
    authority: float

    mapper_branch: int
    mapper_clamped: bool
    mapper_rotation_error_deg: float

    command_reason: str


class G1WristControlRuntime:
    """Complete live Q4 -> SONIC wrist-control layer.

    Input:
        one Q4 canonical forearm-relative SO(3) matrix per side.

    Output:
        six G1 wrist joint positions in SONIC Protocol-v3 order:

        [L_roll, R_roll, L_pitch, R_pitch, L_yaw, R_yaw]

    Responsibilities:
        - continuous SO(3) -> G1 XYZ mapping
        - G1 position limits
        - left/right sign conventions
        - trust/authority behavior
        - timestamp-aware slew limiting
        - SONIC field ordering

    Does NOT:
        - perform Q4 calibration
        - infer trust states
        - publish ZMQ
        - touch robot hardware
    """

    def __init__(
        self,
        *,
        teleop_max_speed_rad_s,
        max_dt_s: float,
    ):

        requested_speed = np.asarray(
            teleop_max_speed_rad_s,
            dtype=np.float64,
        )

        if requested_speed.ndim == 0:
            requested_speed = np.full(
                3,
                float(
                    requested_speed
                ),
                dtype=np.float64,
            )

        requested_speed = (
            requested_speed
            .reshape(3)
        )

        if not np.all(
            np.isfinite(
                requested_speed
            )
        ):
            raise ValueError(
                "teleop_max_speed_rad_s must be finite"
            )

        if np.any(
            requested_speed <= 0.0
        ):
            raise ValueError(
                "teleop_max_speed_rad_s must be > 0"
            )

        # Never permit a configured teleop slew above the
        # source-confirmed robot-description hard limit.
        self.teleop_max_speed_rad_s = np.minimum(
            requested_speed,
            G1_WRIST_HARD_VELOCITY_LIMITS_RAD_S,
        )

        self.mapper = (
            StatefulG1WristMapper(
                clamp=True,
            )
        )

        self.command = (
            G1WristCommandSlewLimiter(
                max_speed_rad_s=
                    self.teleop_max_speed_rad_s,
                max_dt_s=
                    float(
                        max_dt_s
                    ),
            )
        )

        self._latest_command = {
            "L": None,
            "R": None,
        }

        self._initialized = {
            "L": False,
            "R": False,
        }

    @staticmethod
    def _side(
        side,
    ):

        side = str(
            side
        ).upper()

        if side not in (
            "L",
            "R",
        ):
            raise ValueError(
                f"side must be L or R, got {side!r}"
            )

        return side

    def reset(
        self,
    ):
        """Explicit new session / calibration reset."""

        self.mapper.reset()
        self.command.reset()

        self._latest_command = {
            "L": None,
            "R": None,
        }

        self._initialized = {
            "L": False,
            "R": False,
        }

    def initialize_neutral(
        self,
        timestamp_s: float,
    ):
        """Initialize both G1 wrists at Q4 calibrated neutral.

        Q4's explicit calibration defines neutral as identity relative
        wrist rotation, therefore the corresponding G1 wrist command
        is zero on all six joints.
        """

        timestamp_s = float(
            timestamp_s
        )

        zero = np.zeros(
            3,
            dtype=np.float64,
        )

        for side in (
            "L",
            "R",
        ):

            self.mapper.reset(
                side
            )

            self.command.initialize(
                side,
                timestamp_s,
                zero,
            )

            self._latest_command[
                side
            ] = G1WristAngles(
                roll=0.0,
                pitch=0.0,
                yaw=0.0,
            )

            self._initialized[
                side
            ] = True

    def update_side(
        self,
        side,
        timestamp_s: float,
        R_canonical,
        *,
        trust_state,
        authority,
    ) -> WristSideControlResult:

        side = self._side(
            side
        )

        if not self._initialized[
            side
        ]:
            raise RuntimeError(
                f"{side}: wrist controller not initialized"
            )

        state = str(
            trust_state
        ).strip().upper()

        # ----------------------------------------------------
        # LOST / REACQUIRE:
        #
        # Do not even feed bad/stale orientation into the stateful
        # Euler mapper.  This is important because mapper history
        # itself must not be contaminated by untrusted measurements.
        # ----------------------------------------------------

        if state in (
            "LOST",
            "REACQUIRE",
        ):

            current = self._latest_command[
                side
            ]

            result = (
                self.command.update_trusted(
                    side,
                    timestamp_s,
                    None,
                    trust_state=state,
                    authority=0.0,
                )
            )

            self._latest_command[
                side
            ] = result.command

            return WristSideControlResult(
                side=side,

                mapped_target=current,

                command=result.command,

                trust_state=state,

                authority=0.0,

                mapper_branch=-999,

                mapper_clamped=False,

                mapper_rotation_error_deg=0.0,

                command_reason=
                    result.reason,
            )

        if state not in (
            "TRACKING",
            "SUSPECT",
        ):

            current = self._latest_command[
                side
            ]

            result = (
                self.command.update_trusted(
                    side,
                    timestamp_s,
                    None,
                    trust_state=state,
                    authority=0.0,
                )
            )

            self._latest_command[
                side
            ] = result.command

            return WristSideControlResult(
                side=side,
                mapped_target=current,
                command=result.command,
                trust_state=state,
                authority=0.0,
                mapper_branch=-998,
                mapper_clamped=False,
                mapper_rotation_error_deg=0.0,
                command_reason=
                    result.reason,
            )

        if R_canonical is None:

            current = self._latest_command[
                side
            ]

            result = (
                self.command.update_trusted(
                    side,
                    timestamp_s,
                    None,
                    trust_state=state,
                    authority=authority,
                )
            )

            self._latest_command[
                side
            ] = result.command

            return WristSideControlResult(
                side=side,
                mapped_target=current,
                command=result.command,
                trust_state=state,
                authority=0.0,
                mapper_branch=-997,
                mapper_clamped=False,
                mapper_rotation_error_deg=0.0,
                command_reason=
                    result.reason,
            )

        mapped = (
            self.mapper.map_rotation(
                side,
                R_canonical,
            )
        )

        command_result = (
            self.command.update_trusted(
                side,
                timestamp_s,
                mapped.command,
                trust_state=state,
                authority=authority,
            )
        )

        self._latest_command[
            side
        ] = (
            command_result.command
        )

        return WristSideControlResult(
            side=side,

            mapped_target=
                mapped.command,

            command=
                command_result.command,

            trust_state=
                state,

            authority=
                float(
                    authority
                ),

            mapper_branch=
                int(
                    mapped.branch
                ),

            mapper_clamped=
                bool(
                    mapped.clamped
                ),

            mapper_rotation_error_deg=
                float(
                    mapped.rotation_error_deg
                ),

            command_reason=
                command_result.reason,
        )

    def current_side(
        self,
        side,
    ):

        side = self._side(
            side
        )

        return self._latest_command[
            side
        ]

    def sonic_wrists(
        self,
    ) -> np.ndarray:
        """Return exact Protocol-v3 wrist field shape/order."""

        left = self._latest_command[
            "L"
        ]

        right = self._latest_command[
            "R"
        ]

        if (
            left is None
            or
            right is None
        ):
            raise RuntimeError(
                "both wrist sides must be initialized"
            )

        wrists = pack_sonic_wrists(
            left,
            right,
        )

        wrists = np.asarray(
            wrists,
            dtype=np.float32,
        ).reshape(
            1,
            6,
        )

        return wrists
