from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from v3_fusion.g1_wrist_mapping import (
    G1_WRIST_LIMITS_RAD,
    G1WristAngles,
)


def _as_vector(value) -> np.ndarray:
    if isinstance(
        value,
        G1WristAngles,
    ):
        return np.asarray(
            value.as_array(),
            dtype=np.float64,
        ).reshape(3)

    return np.asarray(
        value,
        dtype=np.float64,
    ).reshape(3)


def _angles(q) -> G1WristAngles:
    q = np.asarray(
        q,
        dtype=np.float64,
    ).reshape(3)

    return G1WristAngles(
        roll=float(q[0]),
        pitch=float(q[1]),
        yaw=float(q[2]),
    )


_LIMIT_LOW = np.array(
    [
        G1_WRIST_LIMITS_RAD["roll"][0],
        G1_WRIST_LIMITS_RAD["pitch"][0],
        G1_WRIST_LIMITS_RAD["yaw"][0],
    ],
    dtype=np.float64,
)

_LIMIT_HIGH = np.array(
    [
        G1_WRIST_LIMITS_RAD["roll"][1],
        G1_WRIST_LIMITS_RAD["pitch"][1],
        G1_WRIST_LIMITS_RAD["yaw"][1],
    ],
    dtype=np.float64,
)


@dataclass(frozen=True)
class WristCommandResult:
    side: str

    target: G1WristAngles
    command: G1WristAngles

    timestamp_s: float
    dt_s: float
    dt_used_s: float

    initialized: bool
    limited: bool

    reason: str


class G1WristCommandSlewLimiter:
    """Timestamp-aware physical G1 wrist command limiter.

    This layer is intentionally separate from wrist-orientation
    mapping.

    Q5 mapping decides WHAT joint configuration represents the human
    wrist.

    This class controls HOW FAST the physical G1 joint reference may
    move toward that target.

    No recording-specific logic is present.

    `max_speed_rad_s` must be supplied explicitly.  It may be either:

        scalar
            same speed on roll/pitch/yaw

        length-3 array
            separate roll/pitch/yaw speeds

    `max_dt_s` caps catch-up after a long scheduling/tracking gap.
    Stale/trust handling is a separate layer and must still decide
    whether a target has authority at all.
    """

    def __init__(
        self,
        *,
        max_speed_rad_s,
        max_dt_s: float,
    ):
        speed = np.asarray(
            max_speed_rad_s,
            dtype=np.float64,
        )

        if speed.ndim == 0:
            speed = np.full(
                3,
                float(speed),
                dtype=np.float64,
            )

        speed = speed.reshape(3)

        if not np.all(
            np.isfinite(
                speed
            )
        ):
            raise ValueError(
                "max_speed_rad_s must be finite"
            )

        if np.any(
            speed <= 0.0
        ):
            raise ValueError(
                "max_speed_rad_s must be > 0"
            )

        max_dt_s = float(
            max_dt_s
        )

        if (
            not np.isfinite(
                max_dt_s
            )
            or
            max_dt_s <= 0.0
        ):
            raise ValueError(
                "max_dt_s must be finite and > 0"
            )

        self.max_speed_rad_s = speed
        self.max_dt_s = max_dt_s

        self._command = {
            "L": None,
            "R": None,
        }

        self._timestamp = {
            "L": None,
            "R": None,
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

    @staticmethod
    def _clip_limits(
        q,
    ):
        return np.clip(
            np.asarray(
                q,
                dtype=np.float64,
            ).reshape(3),
            _LIMIT_LOW,
            _LIMIT_HIGH,
        )

    def reset(
        self,
        side=None,
    ):
        """Clear command/timestamp history.

        In the final live runtime this belongs to an explicit new
        session/calibration, not to a brief hand dropout.
        """

        if side is None:
            for s in (
                "L",
                "R",
            ):
                self._command[s] = None
                self._timestamp[s] = None

            return

        side = self._side(
            side
        )

        self._command[
            side
        ] = None

        self._timestamp[
            side
        ] = None

    def initialize(
        self,
        side,
        timestamp_s,
        command,
    ):
        """Explicitly establish the current physical command state."""

        side = self._side(
            side
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

        q = self._clip_limits(
            _as_vector(
                command
            )
        )

        self._command[
            side
        ] = q.copy()

        self._timestamp[
            side
        ] = timestamp_s

        return _angles(
            q
        )

    def update_trusted(
        self,
        side,
        timestamp_s,
        target,
        *,
        trust_state,
        authority,
    ) -> WristCommandResult:
        """Apply hand-trust authority before physical slew limiting.

        LOST and REACQUIRE never advance toward a new wrist target.

        Missing target data also holds the current command.

        This method assumes the wrist command state was explicitly
        initialized by the session/calibration logic.
        """

        side = self._side(
            side
        )

        state = str(
            trust_state
        ).strip().upper()

        supplied_authority = float(
            authority
        )

        current = self.current(
            side
        )

        if current is None:
            raise RuntimeError(
                f"{side}: trusted wrist runtime not initialized"
            )

        if state in (
            "LOST",
            "REACQUIRE",
        ):
            effective_authority = 0.0
            effective_target = current

        elif state in (
            "TRACKING",
            "SUSPECT",
        ):
            effective_authority = float(
                np.clip(
                    supplied_authority,
                    0.0,
                    1.0,
                )
            )

            if target is None:
                effective_authority = 0.0
                effective_target = current
            else:
                effective_target = target

        else:
            # Unknown trust state: fail safe.
            effective_authority = 0.0
            effective_target = current

        result = self.update(
            side,
            timestamp_s,
            effective_target,
            authority=effective_authority,
        )

        if (
            state in (
                "LOST",
                "REACQUIRE",
            )
            and
            result.reason
            !=
            "non_monotonic_timestamp_hold"
        ):
            return WristCommandResult(
                side=result.side,
                target=result.target,
                command=result.command,
                timestamp_s=result.timestamp_s,
                dt_s=result.dt_s,
                dt_used_s=result.dt_used_s,
                initialized=result.initialized,
                limited=True,
                reason=(
                    "trust_lost_hold"
                    if state == "LOST"
                    else
                    "trust_reacquire_hold"
                ),
            )

        if (
            target is None
            and
            state in (
                "TRACKING",
                "SUSPECT",
            )
            and
            result.reason
            !=
            "non_monotonic_timestamp_hold"
        ):
            return WristCommandResult(
                side=result.side,
                target=result.target,
                command=result.command,
                timestamp_s=result.timestamp_s,
                dt_s=result.dt_s,
                dt_used_s=result.dt_used_s,
                initialized=result.initialized,
                limited=True,
                reason="missing_target_hold",
            )

        return result


    def current(
        self,
        side,
    ):
        side = self._side(
            side
        )

        q = self._command[
            side
        ]

        if q is None:
            return None

        return _angles(
            q
        )

    def update(
        self,
        side,
        timestamp_s,
        target,
        *,
        authority: float = 1.0,
    ) -> WristCommandResult:

        side = self._side(
            side
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

        authority = float(
            authority
        )

        if (
            not np.isfinite(
                authority
            )
            or
            authority < 0.0
            or
            authority > 1.0
        ):
            raise ValueError(
                "authority must be finite in [0, 1]"
            )

        target_q = self._clip_limits(
            _as_vector(
                target
            )
        )

        previous_q = self._command[
            side
        ]

        previous_t = self._timestamp[
            side
        ]

        # First sample:
        # final integration should begin this state from explicit
        # neutral calibration.  We do not invent an artificial ramp
        # without knowing the real current command.
        if (
            previous_q is None
            or
            previous_t is None
        ):
            self._command[
                side
            ] = target_q.copy()

            self._timestamp[
                side
            ] = timestamp_s

            return WristCommandResult(
                side=side,
                target=_angles(
                    target_q
                ),
                command=_angles(
                    target_q
                ),
                timestamp_s=timestamp_s,
                dt_s=0.0,
                dt_used_s=0.0,
                initialized=True,
                limited=False,
                reason="initialized",
            )

        dt_s = (
            timestamp_s
            -
            float(
                previous_t
            )
        )

        # Never advance state on non-monotonic timestamps.
        if dt_s <= 0.0:

            return WristCommandResult(
                side=side,
                target=_angles(
                    target_q
                ),
                command=_angles(
                    previous_q
                ),
                timestamp_s=timestamp_s,
                dt_s=float(
                    dt_s
                ),
                dt_used_s=0.0,
                initialized=False,
                limited=True,
                reason="non_monotonic_timestamp_hold",
            )

        dt_used_s = min(
            float(
                dt_s
            ),
            self.max_dt_s,
        )

        full_requested_delta = (
            target_q
            -
            previous_q
        )

        requested_delta = (
            authority
            *
            full_requested_delta
        )

        max_delta = (
            authority
            *
            self.max_speed_rad_s
            *
            dt_used_s
        )

        applied_delta = np.clip(
            requested_delta,
            -max_delta,
            +max_delta,
        )

        command_q = (
            previous_q
            +
            applied_delta
        )

        command_q = self._clip_limits(
            command_q
        )

        limited = bool(
            authority < 1.0
            or
            np.max(
                np.abs(
                    full_requested_delta
                    -
                    applied_delta
                )
            )
            >
            1e-10
        )

        self._command[
            side
        ] = command_q.copy()

        self._timestamp[
            side
        ] = timestamp_s

        return WristCommandResult(
            side=side,
            target=_angles(
                target_q
            ),
            command=_angles(
                command_q
            ),
            timestamp_s=timestamp_s,
            dt_s=float(
                dt_s
            ),
            dt_used_s=float(
                dt_used_s
            ),
            initialized=False,
            limited=limited,
            reason=(
                "authority_hold"
                if authority <= 0.0
                else
                "authority_limited"
                if authority < 1.0
                else
                "slew_limited"
                if limited
                else
                "ok"
            ),
        )
