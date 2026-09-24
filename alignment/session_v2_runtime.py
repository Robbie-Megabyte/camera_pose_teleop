#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from neutral_alignment import (
    NeutralAlignmentError,
    NeutralGravityEstimator,
)

from session_alignment_artifact import (
    write_session_alignment,
)


class SessionV2RuntimeError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class SessionV2RuntimeStatus:
    state: str

    elapsed_s: float
    total_frames: int
    candidate_frames: int
    window_resets: int

    npz_path: Path
    json_path: Path

    message: str


class SessionV2AlignmentController:
    """
    Runtime state machine for V2 neutral alignment.

    It receives already-reconstructed canonical SMPL24
    joints in camera coordinates.

    It does NOT:
      - capture camera frames
      - run GVHMR
      - construct the SONIC bridge
      - publish ZMQ
    """

    def __init__(
        self,
        *,
        npz_path,
        json_path,
        image_width: int,
        image_height: int,
        K_fullimg,
        intrinsics_source="gvhmr_estimate_K",
        smoothing_history_weight=0.0,
        min_duration_s=2.0,
        max_duration_s=5.0,
        max_interframe_gap_s=1.0,
        min_frames=20,
    ):
        self.npz_path = Path(
            npz_path
        )

        self.json_path = Path(
            json_path
        )

        self.image_width = int(
            image_width
        )

        self.image_height = int(
            image_height
        )

        self.K_fullimg = np.asarray(
            K_fullimg,
            dtype=np.float32,
        )

        self.intrinsics_source = str(
            intrinsics_source
        )

        self.smoothing_history_weight = float(
            smoothing_history_weight
        )

        self.min_duration_s = float(
            min_duration_s
        )

        self.max_duration_s = float(
            max_duration_s
        )

        self.max_interframe_gap_s = float(
            max_interframe_gap_s
        )

        self.min_frames = int(
            min_frames
        )

        if self.min_duration_s <= 0.0:
            raise ValueError(
                "min_duration_s must be > 0"
            )

        if (
            self.max_duration_s
            < self.min_duration_s
        ):
            raise ValueError(
                "max_duration_s must be >= "
                "min_duration_s"
            )

        if (
            not np.isfinite(
                self.max_interframe_gap_s
            )
            or self.max_interframe_gap_s
            <= 0.0
        ):
            raise ValueError(
                "max_interframe_gap_s "
                "must be finite and > 0"
            )

        if self.min_frames <= 0:
            raise ValueError(
                "min_frames must be > 0"
            )

        self.estimator = (
            NeutralGravityEstimator(
                min_frames=self.min_frames,
            )
        )

        self.state = "collecting"

        self.start_time_s = None
        self.last_time_s = None

        self.estimate = None
        self.last_estimate_error = None
        self.window_resets = 0

        # A session alignment is valid only if THIS controller
        # instance successfully creates it. Never leave an old
        # session artifact available while collecting a new one.
        self.stale_artifacts_removed = []

        for stale_path in (
            self.npz_path,
            self.json_path,
        ):
            if stale_path.exists():
                stale_path.unlink()

                self.stale_artifacts_removed.append(
                    stale_path
                )

    def _elapsed(
        self,
        timestamp_s: float,
    ) -> float:

        if self.start_time_s is None:
            return 0.0

        return max(
            0.0,
            float(timestamp_s)
            - self.start_time_s,
        )

    def status(
        self,
        timestamp_s=None,
    ) -> SessionV2RuntimeStatus:

        if timestamp_s is None:
            timestamp_s = (
                self.last_time_s
                if self.last_time_s
                is not None
                else 0.0
            )

        elapsed = self._elapsed(
            float(timestamp_s)
        )

        if self.state == "ready":
            estimate = self.estimate

            message = (
                "CAMERA ALIGNMENT PASSED\n"
                f"Valid frames: "
                f"{estimate.accepted_frames}\n"
                f"Angular spread: "
                f"{estimate.angular_spread_deg:.3f} deg\n"
                f"Confidence: "
                f"{estimate.confidence:.3f}\n"
                "TELEOP STREAM MAY START."
            )

        elif self.state == "failed":
            reason = (
                self.last_estimate_error
                or "Unknown alignment failure"
            )

            message = (
                "CAMERA ALIGNMENT FAILED\n"
                f"Reason: {reason}\n"
                f"Valid frames: "
                f"{self.estimator.candidate_frames}\n"
                f"Elapsed: {elapsed:.1f} s\n"
                "NO TELEOP DATA IS BEING PUBLISHED.\n"
                "Please stand neutral with your full body "
                "visible and retry."
            )

        else:
            message = (
                "CAMERA POSE TELEOP V2 — NEUTRAL ALIGNMENT\n"
                "Stand neutral. Keep your full body visible.\n"
                f"Alignment: collecting... {elapsed:.1f} s\n"
                f"Valid frames: "
                f"{self.estimator.candidate_frames} / "
                f"{self.estimator.total_frames}\n"
                "NO TELEOP DATA IS BEING PUBLISHED."
            )

            if self.window_resets:
                message += (
                    "\nCalibration window resets: "
                    f"{self.window_resets}"
                )

        return SessionV2RuntimeStatus(
            state=self.state,
            elapsed_s=elapsed,
            total_frames=(
                self.estimator.total_frames
            ),
            candidate_frames=(
                self.estimator.candidate_frames
            ),
            window_resets=(
                self.window_resets
            ),
            npz_path=self.npz_path,
            json_path=self.json_path,
            message=message,
        )

    def _finish(
        self,
    ):
        estimate = (
            self.estimator.estimate()
        )

        write_session_alignment(
            npz_path=self.npz_path,
            json_path=self.json_path,
            estimate=estimate,
            image_width=(
                self.image_width
            ),
            image_height=(
                self.image_height
            ),
            K_fullimg=(
                self.K_fullimg
            ),
            intrinsics_source=(
                self.intrinsics_source
            ),
            smoothing_history_weight=(
                self.smoothing_history_weight
            ),
        )

        self.estimate = estimate
        self.state = "ready"
        self.last_estimate_error = None

    def add_frame(
        self,
        joints24,
        *,
        timestamp_s: float,
    ) -> SessionV2RuntimeStatus:

        timestamp_s = float(
            timestamp_s
        )

        if not np.isfinite(
            timestamp_s
        ):
            raise SessionV2RuntimeError(
                "timestamp_s must be finite"
            )

        if self.state != "collecting":
            return self.status(
                timestamp_s
            )

        if self.start_time_s is None:
            self.start_time_s = (
                timestamp_s
            )

        if self.last_time_s is not None:
            if (
                timestamp_s
                < self.last_time_s
            ):
                raise SessionV2RuntimeError(
                    "timestamp_s moved backwards"
                )

            interframe_gap_s = (
                timestamp_s
                - self.last_time_s
            )

            if (
                interframe_gap_s
                > self.max_interframe_gap_s
            ):
                # Alignment must use one contiguous neutral
                # observation window. Startup countdowns or
                # inference stalls begin a fresh window.
                self.estimator = (
                    NeutralGravityEstimator(
                        min_frames=(
                            self.min_frames
                        ),
                    )
                )

                self.start_time_s = (
                    timestamp_s
                )

                self.last_estimate_error = None
                self.window_resets += 1

        self.last_time_s = timestamp_s

        self.estimator.add_frame(
            joints24
        )

        elapsed = self._elapsed(
            timestamp_s
        )

        enough_time = (
            elapsed
            >= self.min_duration_s
        )

        enough_candidates = (
            self.estimator.candidate_frames
            >= self.estimator.min_frames
        )

        if (
            enough_time
            and enough_candidates
        ):
            try:
                self._finish()

            except NeutralAlignmentError as exc:
                self.last_estimate_error = str(
                    exc
                )

        if (
            self.state == "collecting"
            and elapsed
            >= self.max_duration_s
        ):
            # One final attempt at the deadline.
            try:
                self._finish()

            except NeutralAlignmentError as exc:
                self.last_estimate_error = str(
                    exc
                )

                self.state = "failed"

        return self.status(
            timestamp_s
        )
