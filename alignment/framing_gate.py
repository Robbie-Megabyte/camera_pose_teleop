#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# COCO-17 / ViTPose ordering used by the existing frontend.
NOSE = 0
LEFT_EYE = 1
RIGHT_EYE = 2
LEFT_EAR = 3
RIGHT_EAR = 4

LEFT_SHOULDER = 5
RIGHT_SHOULDER = 6

LEFT_HIP = 11
RIGHT_HIP = 12

LEFT_KNEE = 13
RIGHT_KNEE = 14

LEFT_ANKLE = 15
RIGHT_ANKLE = 16


HEAD = (
    NOSE,
    LEFT_EYE,
    RIGHT_EYE,
    LEFT_EAR,
    RIGHT_EAR,
)

SHOULDERS = (
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
)

HIPS = (
    LEFT_HIP,
    RIGHT_HIP,
)

KNEES = (
    LEFT_KNEE,
    RIGHT_KNEE,
)

ANKLES = (
    LEFT_ANKLE,
    RIGHT_ANKLE,
)

CRITICAL_BODY = (
    LEFT_SHOULDER,
    RIGHT_SHOULDER,
    LEFT_HIP,
    RIGHT_HIP,
    LEFT_KNEE,
    RIGHT_KNEE,
    LEFT_ANKLE,
    RIGHT_ANKLE,
)


class FramingGateError(
    RuntimeError
):
    pass


@dataclass(frozen=True)
class FramingResult:
    frame_ok: bool
    ready: bool

    good_streak: int
    required_streak: int

    head_visible: bool
    shoulders_visible: bool
    hips_visible: bool
    knees_visible: bool
    ankles_visible: bool

    margins_ok: bool

    reason: str


def _visible(
    kp: np.ndarray,
    index: int,
    confidence_threshold: float,
) -> bool:

    return bool(
        np.isfinite(
            kp[index]
        ).all()
        and
        float(
            kp[index, 2]
        )
        >= confidence_threshold
    )


def evaluate_full_body_framing(
    keypoints17,
    *,
    image_width: int,
    image_height: int,
    confidence_threshold: float = 0.5,
    side_margin_fraction: float = 0.03,
    top_margin_fraction: float = 0.05,
    bottom_margin_fraction: float = 0.05,
) -> FramingResult:

    width = int(
        image_width
    )

    height = int(
        image_height
    )

    if width <= 0 or height <= 0:
        raise FramingGateError(
            "Image dimensions must be positive."
        )

    kp = np.asarray(
        keypoints17,
        dtype=np.float32,
    )

    if kp.shape != (17, 3):
        return FramingResult(
            frame_ok=False,
            ready=False,
            good_streak=0,
            required_streak=1,
            head_visible=False,
            shoulders_visible=False,
            hips_visible=False,
            knees_visible=False,
            ankles_visible=False,
            margins_ok=False,
            reason=(
                "Invalid ViTPose keypoint shape. "
                f"Expected (17,3), got {kp.shape}."
            ),
        )

    head_visible_count = sum(
        _visible(
            kp,
            index,
            confidence_threshold,
        )
        for index in HEAD
    )

    head_visible = (
        head_visible_count >= 1
    )

    shoulders_visible = all(
        _visible(
            kp,
            index,
            confidence_threshold,
        )
        for index in SHOULDERS
    )

    hips_visible = all(
        _visible(
            kp,
            index,
            confidence_threshold,
        )
        for index in HIPS
    )

    knees_visible = all(
        _visible(
            kp,
            index,
            confidence_threshold,
        )
        for index in KNEES
    )

    ankles_visible = all(
        _visible(
            kp,
            index,
            confidence_threshold,
        )
        for index in ANKLES
    )

    if not head_visible:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Head is not reliably visible. "
                "Recenter yourself or adjust the camera."
            ),
        )

    if not shoulders_visible:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Both shoulders are not reliably visible. "
                "Recenter yourself or move farther away."
            ),
        )

    if not hips_visible:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Both hips are not reliably visible. "
                "Keep your full torso in frame."
            ),
        )

    if not knees_visible:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Both knees are not reliably visible. "
                "Move farther from the camera."
            ),
        )

    if not ankles_visible:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Both ankles are not reliably visible. "
                "Move farther from the camera so your "
                "feet remain inside the image."
            ),
        )

    side_margin = (
        float(width)
        * float(
            side_margin_fraction
        )
    )

    top_margin = (
        float(height)
        * float(
            top_margin_fraction
        )
    )

    bottom_limit = (
        float(height - 1)
        -
        float(height)
        * float(
            bottom_margin_fraction
        )
    )

    # Use all currently visible head points for the top check.
    visible_head_y = [
        float(
            kp[index, 1]
        )
        for index in HEAD
        if _visible(
            kp,
            index,
            confidence_threshold,
        )
    ]

    if (
        visible_head_y
        and min(
            visible_head_y
        )
        < top_margin
    ):
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Head is too close to the top image edge. "
                "Move farther away or aim the camera upward."
            ),
        )

    ankle_y = [
        float(
            kp[index, 1]
        )
        for index in ANKLES
    ]

    if max(
        ankle_y
    ) > bottom_limit:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Ankles are too close to the bottom image edge. "
                "Move farther away so your feet stay visible."
            ),
        )

    critical_x = [
        float(
            kp[index, 0]
        )
        for index in CRITICAL_BODY
    ]

    if min(
        critical_x
    ) < side_margin:
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Body is too close to the left image edge. "
                "Recenter yourself."
            ),
        )

    if max(
        critical_x
    ) > (
        float(width - 1)
        - side_margin
    ):
        return FramingResult(
            False,
            False,
            0,
            1,
            head_visible,
            shoulders_visible,
            hips_visible,
            knees_visible,
            ankles_visible,
            False,
            (
                "Body is too close to the right image edge. "
                "Recenter yourself."
            ),
        )

    return FramingResult(
        frame_ok=True,
        ready=True,
        good_streak=1,
        required_streak=1,
        head_visible=head_visible,
        shoulders_visible=shoulders_visible,
        hips_visible=hips_visible,
        knees_visible=knees_visible,
        ankles_visible=ankles_visible,
        margins_ok=True,
        reason="Full-body framing is good.",
    )


class FullBodyFramingGate:
    """
    Consecutive-frame startup gate using real ViTPose-17
    2D observations.

    This deliberately does NOT use GVHMR/SMPL inferred 3D
    joints to decide whether body parts were actually visible.
    """

    def __init__(
        self,
        *,
        image_width: int,
        image_height: int,
        confidence_threshold: float = 0.5,
        consecutive_good_frames: int = 8,
        side_margin_fraction: float = 0.03,
        top_margin_fraction: float = 0.05,
        bottom_margin_fraction: float = 0.05,
    ):

        self.image_width = int(
            image_width
        )

        self.image_height = int(
            image_height
        )

        self.confidence_threshold = float(
            confidence_threshold
        )

        self.consecutive_good_frames = int(
            consecutive_good_frames
        )

        self.side_margin_fraction = float(
            side_margin_fraction
        )

        self.top_margin_fraction = float(
            top_margin_fraction
        )

        self.bottom_margin_fraction = float(
            bottom_margin_fraction
        )

        if (
            self.consecutive_good_frames
            <= 0
        ):
            raise ValueError(
                "consecutive_good_frames must be > 0"
            )

        self.good_streak = 0
        self.ready = False
        self.last_result = None

    def reset(
        self,
    ) -> None:

        self.good_streak = 0
        self.ready = False
        self.last_result = None

    def observe(
        self,
        keypoints17,
    ) -> FramingResult:

        frame = evaluate_full_body_framing(
            keypoints17,
            image_width=(
                self.image_width
            ),
            image_height=(
                self.image_height
            ),
            confidence_threshold=(
                self.confidence_threshold
            ),
            side_margin_fraction=(
                self.side_margin_fraction
            ),
            top_margin_fraction=(
                self.top_margin_fraction
            ),
            bottom_margin_fraction=(
                self.bottom_margin_fraction
            ),
        )

        if frame.frame_ok:
            self.good_streak += 1
        else:
            self.good_streak = 0
            self.ready = False

        if (
            self.good_streak
            >=
            self.consecutive_good_frames
        ):
            self.ready = True

        result = FramingResult(
            frame_ok=(
                frame.frame_ok
            ),
            ready=(
                self.ready
            ),
            good_streak=(
                self.good_streak
            ),
            required_streak=(
                self.consecutive_good_frames
            ),
            head_visible=(
                frame.head_visible
            ),
            shoulders_visible=(
                frame.shoulders_visible
            ),
            hips_visible=(
                frame.hips_visible
            ),
            knees_visible=(
                frame.knees_visible
            ),
            ankles_visible=(
                frame.ankles_visible
            ),
            margins_ok=(
                frame.margins_ok
            ),
            reason=(
                frame.reason
            ),
        )

        self.last_result = result

        return result
