#!/usr/bin/env python3

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np

from neutral_alignment import (
    NeutralGravityEstimate,
    gravity_up_camera_to_R_c2gv,
)


SESSION_ALIGNMENT_FORMAT_VERSION = 1
SESSION_ALIGNMENT_MODE = "session_v2"
ALIGNMENT_METHOD = "neutral_smpl24_v1"


class SessionAlignmentArtifactError(
    RuntimeError
):
    pass


def _validate_K(
    K_fullimg,
) -> np.ndarray:

    K = np.asarray(
        K_fullimg,
        dtype=np.float32,
    )

    if K.shape != (3, 3):
        raise SessionAlignmentArtifactError(
            "K_fullimg must have shape "
            f"(3, 3), got {K.shape}"
        )

    if not np.all(
        np.isfinite(K)
    ):
        raise SessionAlignmentArtifactError(
            "K_fullimg contains "
            "non-finite values"
        )

    if (
        float(K[0, 0]) <= 0.0
        or float(K[1, 1]) <= 0.0
    ):
        raise SessionAlignmentArtifactError(
            "K_fullimg focal lengths "
            "must be positive"
        )

    return K


def write_session_alignment(
    *,
    npz_path,
    json_path,
    estimate: NeutralGravityEstimate,
    image_width: int,
    image_height: int,
    K_fullimg,
    intrinsics_source: str = (
        "gvhmr_estimate_K"
    ),
    smoothing_history_weight: float = 0.8,
):
    """
    Write the V2 neutral-pose session alignment.

    The NPZ is the machine-readable runtime artifact.
    The JSON is a human-readable metadata companion.
    """

    npz_path = Path(
        npz_path
    )

    json_path = Path(
        json_path
    )

    image_width = int(
        image_width
    )

    image_height = int(
        image_height
    )

    if (
        image_width <= 0
        or image_height <= 0
    ):
        raise SessionAlignmentArtifactError(
            "Image dimensions must "
            "be positive"
        )

    smooth = float(
        smoothing_history_weight
    )

    if (
        not np.isfinite(smooth)
        or smooth < 0.0
        or smooth > 1.0
    ):
        raise SessionAlignmentArtifactError(
            "smoothing_history_weight "
            "must be finite and in [0, 1]"
        )

    if not isinstance(
        intrinsics_source,
        str,
    ) or not intrinsics_source:
        raise SessionAlignmentArtifactError(
            "intrinsics_source must be "
            "a non-empty string"
        )

    up = np.asarray(
        estimate.gravity_up_camera,
        dtype=np.float32,
    )

    if up.shape != (3,):
        raise SessionAlignmentArtifactError(
            "gravity_up_camera must "
            f"have shape (3,), got {up.shape}"
        )

    R_c2gv = (
        gravity_up_camera_to_R_c2gv(
            up
        )
        .astype(
            np.float32,
            copy=False,
        )
    )

    K = _validate_K(
        K_fullimg
    )

    created_utc = (
        datetime.now(
            timezone.utc
        )
        .isoformat()
    )

    npz_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    npz_tmp = npz_path.with_name(
        npz_path.name + ".tmp.npz"
    )

    json_tmp = json_path.with_name(
        json_path.name + ".tmp"
    )

    np.savez(
        npz_tmp,
        format_version=np.array(
            SESSION_ALIGNMENT_FORMAT_VERSION,
            dtype=np.int64,
        ),
        alignment_mode=np.array(
            SESSION_ALIGNMENT_MODE
        ),
        alignment_method=np.array(
            ALIGNMENT_METHOD
        ),
        created_utc=np.array(
            created_utc
        ),
        gravity_up_camera=up,
        R_c2gv=R_c2gv,
        image_size=np.array(
            [
                image_width,
                image_height,
            ],
            dtype=np.int64,
        ),
        K_fullimg=K,
        intrinsics_source=np.array(
            intrinsics_source
        ),
        smoothing_history_weight=np.array(
            smooth,
            dtype=np.float64,
        ),
        total_frames=np.array(
            estimate.total_frames,
            dtype=np.int64,
        ),
        candidate_frames=np.array(
            estimate.candidate_frames,
            dtype=np.int64,
        ),
        accepted_frames=np.array(
            estimate.accepted_frames,
            dtype=np.int64,
        ),
        rejected_frames=np.array(
            estimate.rejected_frames,
            dtype=np.int64,
        ),
        median_residual_deg=np.array(
            estimate.median_residual_deg,
            dtype=np.float64,
        ),
        angular_spread_deg=np.array(
            estimate.angular_spread_deg,
            dtype=np.float64,
        ),
        inlier_ratio=np.array(
            estimate.inlier_ratio,
            dtype=np.float64,
        ),
        confidence=np.array(
            estimate.confidence,
            dtype=np.float64,
        ),
    )

    metadata = {
        "format_version":
            SESSION_ALIGNMENT_FORMAT_VERSION,
        "alignment_mode":
            SESSION_ALIGNMENT_MODE,
        "alignment_method":
            ALIGNMENT_METHOD,
        "created_utc":
            created_utc,

        "gravity_up_camera":
            [
                float(x)
                for x in up
            ],

        "R_c2gv":
            [
                [
                    float(x)
                    for x in row
                ]
                for row in R_c2gv
            ],

        "image_size": {
            "width": image_width,
            "height": image_height,
        },

        "K_fullimg":
            [
                [
                    float(x)
                    for x in row
                ]
                for row in K
            ],

        "intrinsics_source":
            intrinsics_source,

        "smoothing_history_weight":
            smooth,

        "quality": {
            "total_frames":
                int(
                    estimate.total_frames
                ),
            "candidate_frames":
                int(
                    estimate.candidate_frames
                ),
            "accepted_frames":
                int(
                    estimate.accepted_frames
                ),
            "rejected_frames":
                int(
                    estimate.rejected_frames
                ),
            "median_residual_deg":
                float(
                    estimate.median_residual_deg
                ),
            "angular_spread_deg":
                float(
                    estimate.angular_spread_deg
                ),
            "inlier_ratio":
                float(
                    estimate.inlier_ratio
                ),
            "confidence":
                float(
                    estimate.confidence
                ),
        },
    }

    with json_tmp.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            metadata,
            f,
            indent=2,
            sort_keys=True,
        )

        f.write("\n")

    npz_tmp.replace(
        npz_path
    )

    json_tmp.replace(
        json_path
    )

    return {
        "npz_path": npz_path,
        "json_path": json_path,
        "R_c2gv": R_c2gv.copy(),
        "gravity_up_camera": up.copy(),
    }
