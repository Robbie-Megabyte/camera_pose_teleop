from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np


_EPS = 1e-9


def _normalize(v: np.ndarray) -> Optional[np.ndarray]:
    v = np.asarray(v, dtype=np.float64)

    n = float(np.linalg.norm(v))

    if not np.isfinite(n) or n < _EPS:
        return None

    return v / n


def canonicalize_wilor_joints(
    joints: np.ndarray,
    side: str,
) -> np.ndarray:
    """
    Convert WiLoR 21x3 joints to the handedness convention used by
    our already-validated palm-frame tests.

    WiLoR / official-demo convention used previously:

        left  -> mirror X
        right -> unchanged
    """
    J = np.asarray(joints, dtype=np.float64)

    if J.shape != (21, 3):
        raise ValueError(
            f"Expected WiLoR joints with shape (21, 3), got {J.shape}"
        )

    if not np.all(np.isfinite(J)):
        raise ValueError("WiLoR joints contain non-finite values")

    side = str(side).upper()

    if side not in ("L", "R"):
        raise ValueError(f"side must be 'L' or 'R', got {side!r}")

    J = J.copy()

    if side == "L":
        J[:, 0] *= -1.0

    return J


def palm_frame_from_canonical_joints(
    joints: np.ndarray,
) -> Optional[np.ndarray]:
    """
    Reproduce the palm frame already validated in the V3 WiLoR tests.

    MANO / WiLoR joint indices:
        wrist       = 0
        index MCP   = 5
        middle MCP  = 9
        ring MCP    = 13
        pinky MCP   = 17

    Frame:
        +Y = wrist -> MCP-center
        +X = index MCP -> pinky MCP, projected perpendicular to Y
        +Z = X cross Y

    Columns of the returned 3x3 matrix are [X, Y, Z].
    """
    J = np.asarray(joints, dtype=np.float64)

    if J.shape != (21, 3):
        return None

    if not np.all(np.isfinite(J)):
        return None

    wrist = J[0]

    index = J[5]
    middle = J[9]
    ring = J[13]
    pinky = J[17]

    center = np.mean(
        np.stack(
            [
                index,
                middle,
                ring,
                pinky,
            ],
            axis=0,
        ),
        axis=0,
    )

    y = _normalize(center - wrist)

    if y is None:
        return None

    x_raw = index - pinky

    # Remove any longitudinal component.
    x_raw = x_raw - np.dot(x_raw, y) * y

    x = _normalize(x_raw)

    if x is None:
        return None

    z = _normalize(np.cross(x, y))

    if z is None:
        return None

    # Re-orthogonalize exactly as in the validated tests.
    x = _normalize(np.cross(y, z))

    if x is None:
        return None

    R = np.column_stack(
        [
            x,
            y,
            z,
        ]
    )

    if not np.all(np.isfinite(R)):
        return None

    return R


def palm_frame(
    joints: np.ndarray,
    side: str,
) -> Optional[np.ndarray]:
    """
    Convenience wrapper:
        raw WiLoR joints
            -> handedness normalization
            -> canonical palm frame
    """
    try:
        J = canonicalize_wilor_joints(
            joints,
            side,
        )
    except ValueError:
        return None

    return palm_frame_from_canonical_joints(J)


@dataclass
class HandObservation:
    """
    One timestamped WiLoR hand observation.

    This deliberately does NOT decide whether WiLoR has authority over
    the body/robot pose. It only records the hand-side evidence and
    enough metadata for the later V3 trust/fusion layer.
    """

    side: str

    frame_id: Optional[int] = None
    capture_timestamp: Optional[float] = None
    track_id: Optional[Any] = None

    detected: bool = False
    det_conf: Optional[float] = None

    crop_valid: bool = False
    crop_clipped: bool = False

    elbow_conf: Optional[float] = None
    wrist_conf: Optional[float] = None

    geometry_valid: bool = False
    invalid_reason: str = ""

    joints: Optional[np.ndarray] = None

    R_hand: Optional[np.ndarray] = None

    hand_lateral: Optional[np.ndarray] = None
    hand_forward: Optional[np.ndarray] = None
    palm_normal: Optional[np.ndarray] = None

    forward_length: Optional[float] = None
    lateral_length: Optional[float] = None

    determinant: Optional[float] = None
    orthogonality_error: Optional[float] = None


def build_hand_observation(
    joints: Optional[np.ndarray],
    side: str,
    *,
    frame_id: Optional[int] = None,
    capture_timestamp: Optional[float] = None,
    track_id: Optional[Any] = None,
    detected: bool = True,
    det_conf: Optional[float] = None,
    crop_valid: bool = True,
    crop_clipped: bool = False,
    elbow_conf: Optional[float] = None,
    wrist_conf: Optional[float] = None,
) -> HandObservation:
    """
    Convert one WiLoR result into a canonical HandObservation.

    At this stage we use only numerical/geometric validity.
    Confidence, freshness, temporal stability, selected-person identity,
    and fusion authority will be handled by a separate trust layer.
    """
    side = str(side).upper()

    obs = HandObservation(
        side=side,
        frame_id=frame_id,
        capture_timestamp=capture_timestamp,
        track_id=track_id,
        detected=bool(detected),
        det_conf=det_conf,
        crop_valid=bool(crop_valid),
        crop_clipped=bool(crop_clipped),
        elbow_conf=elbow_conf,
        wrist_conf=wrist_conf,
    )

    if side not in ("L", "R"):
        obs.invalid_reason = "invalid_side"
        return obs

    if not detected:
        obs.invalid_reason = "not_detected"
        return obs

    if not crop_valid:
        obs.invalid_reason = "invalid_crop"
        return obs

    if joints is None:
        obs.invalid_reason = "missing_joints"
        return obs

    try:
        J = canonicalize_wilor_joints(
            joints,
            side,
        )
    except ValueError as exc:
        obs.invalid_reason = str(exc)
        return obs

    wrist = J[0]

    mcps = np.stack(
        [
            J[5],
            J[9],
            J[13],
            J[17],
        ],
        axis=0,
    )

    center = np.mean(
        mcps,
        axis=0,
    )

    forward_raw = center - wrist
    lateral_raw = J[5] - J[17]

    obs.forward_length = float(
        np.linalg.norm(forward_raw)
    )

    obs.lateral_length = float(
        np.linalg.norm(lateral_raw)
    )

    R = palm_frame_from_canonical_joints(J)

    if R is None:
        obs.invalid_reason = "degenerate_palm_geometry"
        return obs

    det = float(
        np.linalg.det(R)
    )

    ortho_err = float(
        np.linalg.norm(
            R.T @ R - np.eye(3),
            ord="fro",
        )
    )

    if (
        not np.isfinite(det)
        or
        not np.isfinite(ortho_err)
        or
        det <= 0.0
    ):
        obs.invalid_reason = "invalid_rotation_frame"
        return obs

    obs.joints = J

    obs.R_hand = R

    obs.hand_lateral = R[:, 0].copy()
    obs.hand_forward = R[:, 1].copy()
    obs.palm_normal = R[:, 2].copy()

    obs.determinant = det
    obs.orthogonality_error = ortho_err

    obs.geometry_valid = True
    obs.invalid_reason = ""

    return obs
