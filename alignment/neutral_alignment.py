#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import torch


# Canonical SMPL24 indices verified against
# sonic/publisher/soma_to_smpl.py.
PELVIS = 0
LEFT_HIP = 1
RIGHT_HIP = 2
SPINE1 = 3
SPINE2 = 6
SPINE3 = 9
NECK = 12
LEFT_SHOULDER = 16
RIGHT_SHOULDER = 17


class NeutralAlignmentError(RuntimeError):
    pass


@dataclass(frozen=True)
class NeutralGravityEstimate:
    gravity_up_camera: np.ndarray

    total_frames: int
    candidate_frames: int
    accepted_frames: int
    rejected_frames: int

    median_residual_deg: float
    angular_spread_deg: float
    inlier_ratio: float
    confidence: float


def _unit(
    vector: np.ndarray,
    *,
    eps: float = 1e-8,
) -> np.ndarray:

    vector = np.asarray(
        vector,
        dtype=np.float64,
    )

    norm = float(
        np.linalg.norm(vector)
    )

    if (
        not np.isfinite(norm)
        or norm <= eps
    ):
        raise NeutralAlignmentError(
            "Degenerate body vector"
        )

    return vector / norm


def _angle_deg(
    a: np.ndarray,
    b: np.ndarray,
) -> float:

    a = _unit(a)
    b = _unit(b)

    dot = float(
        np.clip(
            np.dot(a, b),
            -1.0,
            1.0,
        )
    )

    return math.degrees(
        math.acos(dot)
    )


def gravity_up_camera_to_R_c2gv(
    gravity_up_camera,
) -> np.ndarray:
    """
    Convert camera-frame world/anatomical UP into the
    exact R_c2gv convention used by GVHMR get_R_c2gv().

    Coordinate contract:
        camera x = right
        camera y = down
        camera z = forward

    The input must already be a unit vector. This
    deliberately reproduces GVHMR's float32 arithmetic
    and its +1e-5 normalization epsilon rather than
    constructing an exactly orthonormal matrix.
    """

    up_np = np.asarray(
        gravity_up_camera,
        dtype=np.float32,
    )

    if up_np.shape != (3,):
        raise NeutralAlignmentError(
            "gravity_up_camera must have "
            f"shape (3,), got {up_np.shape}"
        )

    if not np.all(
        np.isfinite(up_np)
    ):
        raise NeutralAlignmentError(
            "gravity_up_camera contains "
            "non-finite values"
        )

    up_norm = float(
        np.linalg.norm(
            up_np.astype(
                np.float64
            )
        )
    )

    if (
        not np.isfinite(up_norm)
        or up_norm <= 1e-8
    ):
        raise NeutralAlignmentError(
            "gravity_up_camera is degenerate"
        )

    if abs(
        up_norm - 1.0
    ) > 1e-3:
        raise NeutralAlignmentError(
            "gravity_up_camera must already "
            "be unit length; got norm "
            f"{up_norm}"
        )

    up = torch.tensor(
        up_np,
        dtype=torch.float32,
    )

    # GVHMR get_R_c2gv() uses world gravity DOWN.
    # If `up` is camera-frame world UP, then:
    #     axis_y_of_gv = -up
    axis_y_of_gv = -up

    axis_z_in_c = torch.tensor(
        [0.0, 0.0, 1.0],
        dtype=torch.float32,
    )

    axis_x_of_gv = torch.cross(
        axis_y_of_gv,
        axis_z_in_c,
        dim=-1,
    )

    axis_x_norm = (
        axis_x_of_gv.norm()
    )

    axis_x_of_gv = (
        axis_x_of_gv
        / (
            axis_x_norm
            + 1e-5
        )
    )

    if float(
        axis_x_norm
    ) < 1e-5:
        axis_x_of_gv = torch.tensor(
            [1.0, 0.0, 0.0],
            dtype=torch.float32,
        )

    axis_z_of_gv = torch.cross(
        axis_x_of_gv,
        axis_y_of_gv,
        dim=-1,
    )

    R_gv2c = torch.stack(
        [
            axis_x_of_gv,
            axis_y_of_gv,
            axis_z_of_gv,
        ],
        dim=-1,
    )

    R_c2gv = (
        R_gv2c.transpose(
            -1,
            -2,
        )
    )

    return (
        R_c2gv
        .cpu()
        .numpy()
        .copy()
    )


class NeutralGravityEstimator:
    """
    Estimate camera-relative anatomical UP from a short
    neutral-standing SMPL24 sequence.

    Input coordinate system:
        canonical SMPL24 joints expressed in the camera frame.

    Output:
        gravity_up_camera

    This module intentionally does NOT:
      - infer camera yaw
      - infer camera translation
      - build SONIC fields
      - write session calibration files
      - depend on GVHMR or SONIC
    """

    def __init__(
        self,
        *,
        min_frames: int = 20,
        max_frame_cue_angle_deg: float = 25.0,
        max_lateral_tilt_deg: float = 30.0,
        max_inlier_angle_deg: float = 15.0,
        max_final_spread_deg: float = 8.0,
    ):
        self.min_frames = int(
            min_frames
        )

        self.max_frame_cue_angle_deg = float(
            max_frame_cue_angle_deg
        )

        self.max_lateral_tilt_deg = float(
            max_lateral_tilt_deg
        )

        self.max_inlier_angle_deg = float(
            max_inlier_angle_deg
        )

        self.max_final_spread_deg = float(
            max_final_spread_deg
        )

        if self.min_frames < 1:
            raise ValueError(
                "min_frames must be >= 1"
            )

        self._candidates = []

        self.total_frames = 0
        self.frame_rejected = 0
        self._rejection_reasons = {}

    @property
    def candidate_frames(self) -> int:
        return len(
            self._candidates
        )

    @property
    def rejection_reasons(self) -> dict:
        return dict(
            self._rejection_reasons
        )

    def reset(self):
        self._candidates.clear()

        self.total_frames = 0
        self.frame_rejected = 0
        self._rejection_reasons.clear()

    def _reject(
        self,
        reason: str,
    ) -> bool:

        self.frame_rejected += 1

        self._rejection_reasons[
            reason
        ] = (
            self._rejection_reasons.get(
                reason,
                0,
            )
            + 1
        )

        return False

    def _frame_candidate(
        self,
        joints24,
    ) -> np.ndarray:

        try:
            joints = np.asarray(
                joints24,
                dtype=np.float64,
            )
        except Exception as exc:
            raise NeutralAlignmentError(
                "Could not convert joints to numpy"
            ) from exc

        if joints.shape != (24, 3):
            raise NeutralAlignmentError(
                "Expected SMPL24 joints with shape "
                f"(24, 3), got {joints.shape}"
            )

        if not np.all(
            np.isfinite(joints)
        ):
            raise NeutralAlignmentError(
                "Non-finite joints"
            )

        pelvis = joints[
            PELVIS
        ]

        hip_mid = 0.5 * (
            joints[LEFT_HIP]
            + joints[RIGHT_HIP]
        )

        shoulder_mid = 0.5 * (
            joints[LEFT_SHOULDER]
            + joints[RIGHT_SHOULDER]
        )

        # Independent anatomical-up cues.
        raw_cues = (
            shoulder_mid - hip_mid,
            joints[NECK] - pelvis,
            joints[SPINE3] - pelvis,
            joints[SPINE3] - joints[SPINE1],
            joints[SPINE2] - pelvis,
        )

        cues = [
            _unit(v)
            for v in raw_cues
        ]

        primary = cues[0]

        # A neutral frame should have its different torso
        # definitions pointing in approximately the same
        # anatomical-up direction.
        cue_errors = [
            _angle_deg(
                primary,
                cue,
            )
            for cue in cues[1:]
        ]

        if (
            cue_errors
            and max(cue_errors)
            > self.max_frame_cue_angle_deg
        ):
            raise NeutralAlignmentError(
                "Torso cues disagree"
            )

        # Shoulder and hip left-right axes should be close
        # to horizontal relative to anatomical UP.
        lateral_axes = (
            (
                joints[RIGHT_SHOULDER]
                - joints[LEFT_SHOULDER]
            ),
            (
                joints[RIGHT_HIP]
                - joints[LEFT_HIP]
            ),
        )

        max_projection = math.sin(
            math.radians(
                self.max_lateral_tilt_deg
            )
        )

        for lateral in lateral_axes:
            lateral = _unit(
                lateral
            )

            vertical_projection = abs(
                float(
                    np.dot(
                        primary,
                        lateral,
                    )
                )
            )

            if (
                vertical_projection
                > max_projection
            ):
                raise NeutralAlignmentError(
                    "Body lateral axis is not "
                    "sufficiently horizontal"
                )

        # Give the long, robust torso-midline cue the
        # highest weight while retaining independent
        # spine estimates as corroboration.
        weights = np.asarray(
            [
                3.0,
                2.0,
                2.0,
                1.0,
                1.0,
            ],
            dtype=np.float64,
        )

        combined = np.sum(
            np.stack(
                cues,
                axis=0,
            )
            * weights[:, None],
            axis=0,
        )

        return _unit(
            combined
        )

    def add_frame(
        self,
        joints24,
    ) -> bool:

        self.total_frames += 1

        try:
            candidate = (
                self._frame_candidate(
                    joints24
                )
            )
        except NeutralAlignmentError as exc:
            return self._reject(
                str(exc)
            )

        self._candidates.append(
            candidate
        )

        return True

    def estimate(
        self,
    ) -> NeutralGravityEstimate:

        count = len(
            self._candidates
        )

        if count < self.min_frames:
            raise NeutralAlignmentError(
                "Not enough valid neutral frames: "
                f"{count} < {self.min_frames}"
            )

        candidates = np.stack(
            self._candidates,
            axis=0,
        )

        # Component-wise median is a robust spherical-mean
        # seed when all vectors occupy one local hemisphere.
        seed = _unit(
            np.median(
                candidates,
                axis=0,
            )
        )

        residuals = np.asarray(
            [
                _angle_deg(
                    seed,
                    vector,
                )
                for vector in candidates
            ],
            dtype=np.float64,
        )

        median = float(
            np.median(
                residuals
            )
        )

        mad = float(
            np.median(
                np.abs(
                    residuals
                    - median
                )
            )
        )

        robust_sigma = (
            1.4826 * mad
        )

        inlier_threshold = float(
            np.clip(
                median
                + 3.0 * robust_sigma,
                3.0,
                self.max_inlier_angle_deg,
            )
        )

        inlier_mask = (
            residuals
            <= inlier_threshold
        )

        inlier_count = int(
            np.count_nonzero(
                inlier_mask
            )
        )

        if (
            inlier_count
            < self.min_frames
        ):
            raise NeutralAlignmentError(
                "Not enough stable neutral frames "
                "after temporal outlier rejection: "
                f"{inlier_count} < {self.min_frames}"
            )

        gravity_up = _unit(
            np.mean(
                candidates[
                    inlier_mask
                ],
                axis=0,
            )
        )

        final_residuals = np.asarray(
            [
                _angle_deg(
                    gravity_up,
                    vector,
                )
                for vector in candidates[
                    inlier_mask
                ]
            ],
            dtype=np.float64,
        )

        median_residual = float(
            np.median(
                final_residuals
            )
        )

        angular_spread = float(
            np.percentile(
                final_residuals,
                95.0,
            )
        )

        if (
            angular_spread
            > self.max_final_spread_deg
        ):
            raise NeutralAlignmentError(
                "Neutral alignment is unstable: "
                "95th-percentile angular spread "
                f"{angular_spread:.3f} deg exceeds "
                f"{self.max_final_spread_deg:.3f} deg"
            )

        rejected_frames = (
            self.total_frames
            - inlier_count
        )

        inlier_ratio = (
            inlier_count
            / self.total_frames
        )

        stability = max(
            0.0,
            1.0
            - angular_spread
            / self.max_final_spread_deg,
        )

        confidence = float(
            np.clip(
                inlier_ratio
                * stability,
                0.0,
                1.0,
            )
        )

        return NeutralGravityEstimate(
            gravity_up_camera=(
                gravity_up.copy()
            ),
            total_frames=(
                self.total_frames
            ),
            candidate_frames=count,
            accepted_frames=(
                inlier_count
            ),
            rejected_frames=(
                rejected_frames
            ),
            median_residual_deg=(
                median_residual
            ),
            angular_spread_deg=(
                angular_spread
            ),
            inlier_ratio=float(
                inlier_ratio
            ),
            confidence=confidence,
        )
