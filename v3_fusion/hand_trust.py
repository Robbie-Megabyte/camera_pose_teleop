from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np

from .hand_observation import HandObservation


class HandTrustState(str, Enum):
    TRACKING = "TRACKING"
    SUSPECT = "SUSPECT"
    LOST = "LOST"
    REACQUIRE = "REACQUIRE"


@dataclass
class HandTrustConfig:
    """
    First-pass V3 trust thresholds.

    These are intentionally centralized and provisional.
    We will calibrate them against the recorded wrist session before
    using them in the live pipeline.
    """

    # WiLoR is expected to run asynchronously at a lower rate than body.
    max_source_age_s: float = 0.35

    # COCO17 elbow/wrist evidence used to generate the hand crop.
    min_elbow_conf: float = 0.25
    min_wrist_conf: float = 0.25

    # Maximum one-result orientation step considered immediately plausible.
    max_orientation_step_deg: float = 60.0

    # Require several consecutive valid observations after LOST / track change.
    reacquire_consecutive: int = 3

    # One good frame is not enough to leave SUSPECT.
    suspect_recover_consecutive: int = 2

    # Short grace period before declaring the hand LOST.
    suspect_bad_frames_to_lost: int = 2

    # During SUSPECT we may later use a heavily damped previous orientation.
    suspect_authority: float = 0.25

    # A clipped proposal is metadata, not automatically a hard failure.
    reject_clipped_crop: bool = False


@dataclass
class HandTrustDecision:
    state: HandTrustState

    trusted: bool
    authority: float

    reason: str

    source_age_s: Optional[float] = None
    orientation_step_deg: Optional[float] = None

    track_changed: bool = False


def rotation_distance_deg(
    Ra: np.ndarray,
    Rb: np.ndarray,
) -> float:
    """
    SO(3) geodesic distance in degrees.
    """
    A = np.asarray(
        Ra,
        dtype=np.float64,
    ).reshape(3, 3)

    B = np.asarray(
        Rb,
        dtype=np.float64,
    ).reshape(3, 3)

    rel = A.T @ B

    c = np.clip(
        (np.trace(rel) - 1.0) / 2.0,
        -1.0,
        1.0,
    )

    return float(
        np.degrees(
            np.arccos(c)
        )
    )


class HandTrustTracker:
    """
    Per-hand V3 WiLoR trust state machine.

    Important:
      - It does NOT modify the body pose.
      - It does NOT compare "V2 confidence vs WiLoR confidence".
      - Large V2/WiLoR disagreement is therefore NOT itself a rejection.
      - This layer judges only whether the WiLoR-side observation is
        internally trustworthy enough to enter the later fusion stage.
    """

    def __init__(
        self,
        side: str,
        config: Optional[HandTrustConfig] = None,
    ):
        side = str(side).upper()

        if side not in ("L", "R"):
            raise ValueError(
                f"side must be L or R, got {side!r}"
            )

        self.side = side

        self.config = (
            config
            if config is not None
            else HandTrustConfig()
        )

        self.state = HandTrustState.LOST

        self.track_id = None

        self.last_trusted_observation: Optional[
            HandObservation
        ] = None

        self.last_trusted_R: Optional[
            np.ndarray
        ] = None

        self.reacquire_count = 0
        self.suspect_bad_count = 0
        self.suspect_recover_count = 0


    def reset(
        self,
    ):
        self.state = HandTrustState.LOST

        self.track_id = None

        self.last_trusted_observation = None
        self.last_trusted_R = None

        self.reacquire_count = 0
        self.suspect_bad_count = 0
        self.suspect_recover_count = 0


    def _quality_check(
        self,
        obs: HandObservation,
        now_timestamp: Optional[float],
    ):
        if obs.side != self.side:
            return (
                False,
                "wrong_side",
                None,
            )

        if not obs.detected:
            return (
                False,
                "not_detected",
                None,
            )

        if not obs.crop_valid:
            return (
                False,
                "invalid_crop",
                None,
            )

        if (
            self.config.reject_clipped_crop
            and
            obs.crop_clipped
        ):
            return (
                False,
                "clipped_crop",
                None,
            )

        if not obs.geometry_valid:
            return (
                False,
                obs.invalid_reason
                or
                "invalid_geometry",
                None,
            )

        if obs.R_hand is None:
            return (
                False,
                "missing_rotation",
                None,
            )

        R = np.asarray(
            obs.R_hand,
            dtype=np.float64,
        )

        if (
            R.shape != (3, 3)
            or
            not np.all(
                np.isfinite(R)
            )
        ):
            return (
                False,
                "invalid_rotation",
                None,
            )

        if (
            obs.elbow_conf is not None
            and
            obs.elbow_conf
            < self.config.min_elbow_conf
        ):
            return (
                False,
                "low_elbow_conf",
                None,
            )

        if (
            obs.wrist_conf is not None
            and
            obs.wrist_conf
            < self.config.min_wrist_conf
        ):
            return (
                False,
                "low_wrist_conf",
                None,
            )

        source_age_s = None

        if (
            now_timestamp is not None
            and
            obs.capture_timestamp is not None
        ):
            source_age_s = float(
                now_timestamp
                - obs.capture_timestamp
            )

            if (
                not np.isfinite(
                    source_age_s
                )
                or
                source_age_s < -0.05
            ):
                return (
                    False,
                    "invalid_timestamp",
                    source_age_s,
                )

            if (
                source_age_s
                > self.config.max_source_age_s
            ):
                return (
                    False,
                    "stale",
                    source_age_s,
                )

        return (
            True,
            "quality_ok",
            source_age_s,
        )


    def update(
        self,
        obs: HandObservation,
        *,
        now_timestamp: Optional[float] = None,
    ) -> HandTrustDecision:

        (
            quality_ok,
            quality_reason,
            source_age_s,
        ) = self._quality_check(
            obs,
            now_timestamp,
        )

        track_changed = False

        if (
            quality_ok
            and
            obs.track_id is not None
        ):
            if (
                self.track_id is not None
                and
                obs.track_id
                != self.track_id
            ):
                track_changed = True

                # Never carry hand state across selected-person changes.
                self.state = HandTrustState.LOST

                self.last_trusted_observation = None
                self.last_trusted_R = None

                self.reacquire_count = 0
                self.suspect_bad_count = 0
                self.suspect_recover_count = 0

            self.track_id = obs.track_id


        step_deg = None

        temporal_ok = quality_ok

        if (
            quality_ok
            and
            self.last_trusted_R is not None
        ):
            step_deg = rotation_distance_deg(
                self.last_trusted_R,
                obs.R_hand,
            )

            if (
                step_deg
                > self.config.max_orientation_step_deg
            ):
                temporal_ok = False
                quality_reason = (
                    "orientation_jump"
                )


        valid = (
            quality_ok
            and
            temporal_ok
        )


        # ---------------------------------------------------------
        # LOST
        # ---------------------------------------------------------

        if self.state == HandTrustState.LOST:

            if not valid:
                return HandTrustDecision(
                    state=self.state,
                    trusted=False,
                    authority=0.0,
                    reason=quality_reason,
                    source_age_s=source_age_s,
                    orientation_step_deg=step_deg,
                    track_changed=track_changed,
                )

            self.state = HandTrustState.REACQUIRE
            self.reacquire_count = 1

            # During reacquisition this is only a candidate.
            self.last_trusted_R = (
                np.asarray(
                    obs.R_hand,
                    dtype=np.float64,
                ).copy()
            )

            return HandTrustDecision(
                state=self.state,
                trusted=False,
                authority=0.0,
                reason=(
                    "track_changed_reacquire"
                    if track_changed
                    else
                    "reacquire_1"
                ),
                source_age_s=source_age_s,
                orientation_step_deg=step_deg,
                track_changed=track_changed,
            )


        # ---------------------------------------------------------
        # REACQUIRE
        # ---------------------------------------------------------

        if self.state == HandTrustState.REACQUIRE:

            if not valid:
                self.state = HandTrustState.LOST
                self.reacquire_count = 0
                self.last_trusted_R = None

                return HandTrustDecision(
                    state=self.state,
                    trusted=False,
                    authority=0.0,
                    reason=(
                        "reacquire_failed_"
                        + quality_reason
                    ),
                    source_age_s=source_age_s,
                    orientation_step_deg=step_deg,
                    track_changed=track_changed,
                )

            self.reacquire_count += 1

            # Advance the candidate orientation so normal movement during
            # reacquisition does not get compared only to its first frame.
            self.last_trusted_R = (
                np.asarray(
                    obs.R_hand,
                    dtype=np.float64,
                ).copy()
            )

            if (
                self.reacquire_count
                >=
                self.config.reacquire_consecutive
            ):
                self.state = HandTrustState.TRACKING

                self.last_trusted_observation = obs

                self.reacquire_count = 0

                return HandTrustDecision(
                    state=self.state,
                    trusted=True,
                    authority=1.0,
                    reason="reacquire_complete",
                    source_age_s=source_age_s,
                    orientation_step_deg=step_deg,
                    track_changed=track_changed,
                )

            return HandTrustDecision(
                state=self.state,
                trusted=False,
                authority=0.0,
                reason=(
                    f"reacquire_"
                    f"{self.reacquire_count}"
                ),
                source_age_s=source_age_s,
                orientation_step_deg=step_deg,
                track_changed=track_changed,
            )


        # ---------------------------------------------------------
        # TRACKING
        # ---------------------------------------------------------

        if self.state == HandTrustState.TRACKING:

            if valid:
                self.last_trusted_observation = obs

                self.last_trusted_R = (
                    np.asarray(
                        obs.R_hand,
                        dtype=np.float64,
                    ).copy()
                )

                self.suspect_bad_count = 0
                self.suspect_recover_count = 0

                return HandTrustDecision(
                    state=self.state,
                    trusted=True,
                    authority=1.0,
                    reason="tracking",
                    source_age_s=source_age_s,
                    orientation_step_deg=step_deg,
                    track_changed=track_changed,
                )

            self.state = HandTrustState.SUSPECT
            self.suspect_bad_count = 1
            self.suspect_recover_count = 0

            return HandTrustDecision(
                state=self.state,
                trusted=False,
                authority=self.config.suspect_authority,
                reason=quality_reason,
                source_age_s=source_age_s,
                orientation_step_deg=step_deg,
                track_changed=track_changed,
            )


        # ---------------------------------------------------------
        # SUSPECT
        # ---------------------------------------------------------

        if self.state == HandTrustState.SUSPECT:

            if valid:
                self.suspect_recover_count += 1
                self.suspect_bad_count = 0

                if (
                    self.suspect_recover_count
                    >=
                    self.config.suspect_recover_consecutive
                ):
                    self.state = HandTrustState.TRACKING

                    self.last_trusted_observation = obs

                    self.last_trusted_R = (
                        np.asarray(
                            obs.R_hand,
                            dtype=np.float64,
                        ).copy()
                    )

                    self.suspect_recover_count = 0

                    return HandTrustDecision(
                        state=self.state,
                        trusted=True,
                        authority=1.0,
                        reason="suspect_recovered",
                        source_age_s=source_age_s,
                        orientation_step_deg=step_deg,
                        track_changed=track_changed,
                    )

                return HandTrustDecision(
                    state=self.state,
                    trusted=False,
                    authority=self.config.suspect_authority,
                    reason="suspect_recovering",
                    source_age_s=source_age_s,
                    orientation_step_deg=step_deg,
                    track_changed=track_changed,
                )

            self.suspect_recover_count = 0
            self.suspect_bad_count += 1

            if (
                self.suspect_bad_count
                >=
                self.config.suspect_bad_frames_to_lost
            ):
                self.state = HandTrustState.LOST

                self.reacquire_count = 0
                self.suspect_bad_count = 0

                self.last_trusted_R = None
                self.last_trusted_observation = None

                return HandTrustDecision(
                    state=self.state,
                    trusted=False,
                    authority=0.0,
                    reason=(
                        "lost_"
                        + quality_reason
                    ),
                    source_age_s=source_age_s,
                    orientation_step_deg=step_deg,
                    track_changed=track_changed,
                )

            return HandTrustDecision(
                state=self.state,
                trusted=False,
                authority=self.config.suspect_authority,
                reason=quality_reason,
                source_age_s=source_age_s,
                orientation_step_deg=step_deg,
                track_changed=track_changed,
            )


        raise RuntimeError(
            f"Unhandled state: {self.state}"
        )
