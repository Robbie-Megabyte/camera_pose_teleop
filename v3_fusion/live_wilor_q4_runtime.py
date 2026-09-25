from __future__ import annotations

import faulthandler
import os
from pathlib import Path
import re
import sys
import threading
import time

import numpy as np
import torch

from v3_fusion.hand_observation import (
    build_hand_observation,
)
from v3_fusion.hand_trust import (
    HandTrustState,
    HandTrustTracker,
)
from v3_fusion.wrist_orientation_runtime import (
    Q4WristOrientationRuntime,
)


SIDES = (
    "L",
    "R",
)

SMPL_ARM = {
    "L": (
        16,
        18,
        20,
    ),
    "R": (
        17,
        19,
        21,
    ),
}

COCO_HAND = {
    "L": (
        7,
        9,
    ),
    "R": (
        8,
        10,
    ),
}


def _sandbox_root() -> Path:
    return (
        Path(__file__)
        .resolve()
        .parents[1]
    )


def _load_production_kp_conf() -> float:
    """Reuse the accepted crop producer threshold when available."""

    src = (
        _sandbox_root()
        / "tests"
        / "extract_production_vitpose_hand_crops.py"
    )

    try:
        text = src.read_text()

        match = re.search(
            r"(?m)^\s*KP_CONF_MIN\s*=\s*([0-9.]+)",
            text,
        )

        if match:
            return float(
                match.group(1)
            )

    except Exception:
        pass

    # Accepted fallback used by the existing Q4 live sandbox.
    return 0.25


DEFAULT_KP_CONF_MIN = float(
    os.environ.get(
        "Q4_HAND_KP_CONF_MIN",
        str(
            _load_production_kp_conf()
        ),
    )
)

DEFAULT_PAIR_MAX_S = float(
    os.environ.get(
        "Q4_LIVE_PAIR_MAX_S",
        "0.20",
    )
)


def hand_proposal(
    elbow,
    wrist,
    width,
    height,
):
    """Exact accepted production hand-crop geometry.

    hand length = 0.75 * forearm
    center      = wrist + 0.5 * hand_length * (elbow -> wrist)
    square side = 1.20 * hand_length
    """

    elbow = np.asarray(
        elbow,
        dtype=np.float64,
    ).reshape(
        2
    )

    wrist = np.asarray(
        wrist,
        dtype=np.float64,
    ).reshape(
        2
    )

    direction = (
        wrist
        -
        elbow
    )

    forearm = float(
        np.linalg.norm(
            direction
        )
    )

    if (
        not np.isfinite(
            forearm
        )
        or
        forearm < 5.0
    ):
        return None

    direction = (
        direction
        /
        forearm
    )

    hand_length = (
        0.75
        *
        forearm
    )

    center = (
        wrist
        +
        0.5
        *
        hand_length
        *
        direction
    )

    side = (
        1.20
        *
        hand_length
    )

    half = (
        side
        /
        2.0
    )

    box = np.array(
        [
            center[0] - half,
            center[1] - half,
            center[0] + half,
            center[1] + half,
        ],
        dtype=np.float32,
    )

    box[
        [0, 2]
    ] = np.clip(
        box[
            [0, 2]
        ],
        0,
        width - 1,
    )

    box[
        [1, 3]
    ] = np.clip(
        box[
            [1, 3]
        ],
        0,
        height - 1,
    )

    if (
        float(
            box[2]
            -
            box[0]
        )
        < 4.0
        or
        float(
            box[3]
            -
            box[1]
        )
        < 4.0
    ):
        return None

    return box


def _box_is_clipped(
    box,
    width,
    height,
):
    if box is None:
        return False

    eps = 1e-4

    return bool(
        float(
            box[0]
        )
        <= eps
        or
        float(
            box[1]
        )
        <= eps
        or
        float(
            box[2]
        )
        >= float(
            width - 1
        )
        - eps
        or
        float(
            box[3]
        )
        >= float(
            height - 1
        )
        - eps
    )


def _extract_joints24(
    value,
):
    if torch.is_tensor(
        value
    ):
        value = (
            value
            .detach()
            .cpu()
            .float()
            .numpy()
        )

    J = np.asarray(
        value,
        dtype=np.float64,
    )

    while (
        J.ndim > 2
        and
        J.shape[0] == 1
    ):
        J = J[0]

    if (
        J.ndim != 2
        or
        J.shape[1] != 3
        or
        J.shape[0] < 22
    ):
        raise ValueError(
            "post-FASTIK joints must resolve to "
            f"(N,3), N>=22; got {J.shape}"
        )

    return J


class LiveWilorQ4Runtime:
    """Production V3 asynchronous hand/Q4/trust state.

    This class deliberately does NOT own a worker thread.

    The V3 SONIC owner already owns the single-slot `hand_pending`
    mailbox added in Q5.23.  Its one hand worker calls
    process_hand_packet() synchronously, guaranteeing that at most
    one WiLoR inference is in flight.

    Hand and body streams advance Q4 independently.
    No automatic calibration occurs.
    """

    def __init__(
        self,
        *,
        pair_max_s=DEFAULT_PAIR_MAX_S,
        kp_conf_min=DEFAULT_KP_CONF_MIN,
    ):
        if not torch.cuda.is_available():
            raise RuntimeError(
                "V3 WiLoR runtime requires CUDA"
            )

        self.pair_max_s = float(
            pair_max_s
        )

        self.kp_conf_min = float(
            kp_conf_min
        )

        self.lock = (
            threading.RLock()
        )

        self.q4 = (
            Q4WristOrientationRuntime(
                alpha_ref=float(
                    os.environ.get(
                        "Q4_LIVE_ALPHA_REF",
                        "0.40",
                    )
                ),
                reference_dt_s=0.100,
                reset_gap_s=0.400,
                canonicalize_bilateral=True,
            )
        )

        self.trust = {
            side:
                HandTrustTracker(
                    side
                )
            for side
            in SIDES
        }

        self.latest_decision = {
            side:
                None
            for side
            in SIDES
        }

        # Timestamp of the newest HAND PACKET processed for each side,
        # including low-confidence/missing-hand packets.
        self.latest_hand_packet_ts = {
            side:
                None
            for side
            in SIDES
        }

        self.latest_hand_sequence = {
            side:
                None
            for side
            in SIDES
        }

        self.latest_boxes = {}

        self.calibration_armed = False
        self.calibration_count = 0
        self.last_calibration = None

        self.last_hand_infer_ms = None
        self.jobs_completed = 0

        root = _sandbox_root()

        wilor_root = (
            root
            / "third_party"
            / "WiLoR"
        )

        if not wilor_root.is_dir():
            raise RuntimeError(
                f"WiLoR root missing: {wilor_root}"
            )

        for p in (
            str(
                root
            ),
            str(
                wilor_root
            ),
        ):
            if p not in sys.path:
                sys.path.insert(
                    0,
                    p,
                )

        from wilor.models import (
            load_wilor,
        )
        from wilor.datasets.vitdet_dataset import (
            ViTDetDataset,
        )

        self.ViTDetDataset = (
            ViTDetDataset
        )

        self.device = (
            torch.device(
                "cuda"
            )
        )

        torch.set_float32_matmul_precision(
            "high"
        )

        previous_cwd = (
            os.getcwd()
        )

        try:
            os.chdir(
                str(
                    wilor_root
                )
            )

            print()
            print(
                "===== V3 WRISTS: LOAD WILOR ====="
            )
            print(
                "WiLoR load_wilor(): START",
                flush=True,
            )

            faulthandler.enable()

            faulthandler.dump_traceback_later(
                20.0,
                repeat=True,
            )

            self.model, self.cfg = (
                load_wilor(
                    checkpoint_path=
                        "./pretrained_models/wilor_final.ckpt",
                    cfg_path=
                        "./pretrained_models/model_config.yaml",
                )
            )

            print(
                "WiLoR load_wilor(): RETURNED",
                flush=True,
            )

        finally:
            faulthandler.cancel_dump_traceback_later()

            os.chdir(
                previous_cwd
            )

        # Exact already-passing fast WiLoR configuration.
        self.model = (
            self.model.half()
        )

        self.model.backbone = (
            torch.compile(
                self.model.backbone
            )
        )

        self.model.backbone.skip_blocks = True

        self.model = (
            self.model.cuda()
        )

        self.model.eval()

        # Q5_26N_EXPLICIT_WILOR_WARMUP_V1
        #
        # torch.compile() is lazy.  Compile both live shapes now,
        # before camera/framing/session calibration:
        #
        #   B=2: both hands valid
        #   B=1: one hand valid / other unavailable
        #
        # Zero-hand packets never call the model.
        #
        # This removes the hidden first-live-hand compilation stall.
        for warm_batch in (
            2,
            1,
        ):
            print(
                f"V3 WiLoR compile warmup B{warm_batch}: START",
                flush=True,
            )

            warm_imgs = torch.zeros(
                (
                    warm_batch,
                    3,
                    256,
                    256,
                ),
                dtype=torch.float16,
                device=self.device,
            )

            torch.cuda.synchronize()

            warm_t0 = (
                time.perf_counter()
            )

            faulthandler.dump_traceback_later(
                30.0,
                repeat=True,
            )

            try:
                with torch.inference_mode():
                    warm_out = (
                        self.model(
                            {
                                "img":
                                    warm_imgs,
                            }
                        )
                    )

                torch.cuda.synchronize()

            finally:
                faulthandler.cancel_dump_traceback_later()

            warm_elapsed_s = (
                time.perf_counter()
                - warm_t0
            )

            warm_kp = (
                warm_out.get(
                    "pred_keypoints_3d"
                )
            )

            if warm_kp is None:
                raise RuntimeError(
                    "WiLoR startup warmup missing "
                    "pred_keypoints_3d"
                )

            expected_shape = (
                warm_batch,
                21,
                3,
            )

            if tuple(
                warm_kp.shape
            ) != expected_shape:
                raise RuntimeError(
                    "WiLoR startup warmup unexpected "
                    f"keypoint shape: {tuple(warm_kp.shape)} "
                    f"expected {expected_shape}"
                )

            if not bool(
                torch.isfinite(
                    warm_kp
                ).all()
            ):
                raise RuntimeError(
                    "WiLoR startup warmup produced "
                    "non-finite keypoints"
                )

            print(
                f"V3 WiLoR compile warmup B{warm_batch}: PASS "
                f"{warm_elapsed_s:.3f}s",
                flush=True,
            )

            del warm_kp
            del warm_out
            del warm_imgs

        # Verify that returning to the normal two-hand shape is
        # now on the already-compiled steady-state path.
        steady_imgs = torch.zeros(
            (
                2,
                3,
                256,
                256,
            ),
            dtype=torch.float16,
            device=self.device,
        )

        torch.cuda.synchronize()

        steady_t0 = (
            time.perf_counter()
        )

        with torch.inference_mode():
            steady_out = (
                self.model(
                    {
                        "img":
                            steady_imgs,
                    }
                )
            )

        torch.cuda.synchronize()

        steady_ms = (
            (
                time.perf_counter()
                - steady_t0
            )
            * 1000.0
        )

        print(
            "V3 WiLoR steady B2 warm check: PASS "
            f"{steady_ms:.3f} ms",
            flush=True,
        )

        del steady_out
        del steady_imgs

        # Q5_26AX_WILOR_LIVE_CUDA_STREAM_V1
        #
        # Keep startup compile/warmup on the original synchronized
        # default-stream path.  Only steady-state live hand inference
        # gets a dedicated stream so it does not issue device-wide
        # synchronization against the independent body temporal worker.
        # Q5_PRIORITY_ABC_WILOR_MINUS1_V1
        # A/B/C scheduling experiment:
        # temporal GVHMR remains on priority -2;
        # steady-state WiLoR uses intermediate priority -1.
        self.live_cuda_stream = torch.cuda.Stream(
            priority=-1
        )

        print(
            "V3 WiLoR live CUDA stream priority:",
            self.live_cuda_stream.priority,
        )

        print(
            "V3 WiLoR fast setup: PASS"
        )
        print(
            "V3 hand kp confidence threshold:",
            self.kp_conf_min,
        )
        print(
            "V3 Q4 hand/body pair threshold:",
            self.pair_max_s,
            "s",
        )

    def _update_invalid_hand(
        self,
        *,
        side,
        sequence,
        capture_ts,
        track_id,
        elbow_conf,
        wrist_conf,
        mark_packet_seen=True,
    ):
        obs = (
            build_hand_observation(
                None,
                side,
                frame_id=int(
                    sequence
                ),
                capture_timestamp=float(
                    capture_ts
                ),
                track_id=track_id,
                detected=False,
                crop_valid=False,
                elbow_conf=(
                    None
                    if elbow_conf is None
                    else float(
                        elbow_conf
                    )
                ),
                wrist_conf=(
                    None
                    if wrist_conf is None
                    else float(
                        wrist_conf
                    )
                ),
            )
        )

        decision = (
            self.trust[
                side
            ].update(
                obs
            )
        )

        self.latest_decision[
            side
        ] = decision

        if mark_packet_seen:
            self.latest_hand_packet_ts[
                side
            ] = float(
                capture_ts
            )

            self.latest_hand_sequence[
                side
            ] = int(
                sequence
            )

        return decision

    def process_hand_packet(
        self,
        packet,
    ):
        """Run one newest hand packet through WiLoR.

        Called by exactly one owner hand worker.
        """

        sequence = int(
            packet[
                "capture_sequence"
            ]
        )

        capture_ts = float(
            packet[
                "capture_ts"
            ]
        )

        track_id = packet.get(
            "track_id"
        )

        frame = np.asarray(
            packet[
                "frame_bgr"
            ]
        )

        kp = np.asarray(
            packet[
                "kp2d"
            ],
            dtype=np.float64,
        )

        if kp.shape != (
            17,
            3,
        ):
            raise ValueError(
                f"expected kp2d (17,3), got {kp.shape}"
            )

        if (
            frame.ndim != 3
            or
            frame.shape[2] != 3
        ):
            raise ValueError(
                f"expected BGR image HxWx3, got {frame.shape}"
            )

        height, width = (
            frame.shape[
                :2
            ]
        )

        boxes = []
        sides = []
        handedness = []
        metadata = {}

        invalid = []

        for side in SIDES:
            elbow_i, wrist_i = (
                COCO_HAND[
                    side
                ]
            )

            elbow = kp[
                elbow_i
            ]

            wrist = kp[
                wrist_i
            ]

            elbow_conf = float(
                elbow[2]
            )

            wrist_conf = float(
                wrist[2]
            )

            metadata[
                side
            ] = {
                "elbow_conf":
                    elbow_conf,
                "wrist_conf":
                    wrist_conf,
            }

            if (
                elbow_conf
                <
                self.kp_conf_min
                or
                wrist_conf
                <
                self.kp_conf_min
            ):
                invalid.append(
                    side
                )
                continue

            box = (
                hand_proposal(
                    elbow[
                        :2
                    ],
                    wrist[
                        :2
                    ],
                    width,
                    height,
                )
            )

            if box is None:
                invalid.append(
                    side
                )
                continue

            boxes.append(
                box
            )

            sides.append(
                side
            )

            handedness.append(
                0.0
                if side == "L"
                else 1.0
            )

            metadata[
                side
            ][
                "box"
            ] = box.copy()

            metadata[
                side
            ][
                "crop_clipped"
            ] = _box_is_clipped(
                box,
                width,
                height,
            )

        with self.lock:
            self.latest_boxes = {
                side:
                    metadata[
                        side
                    ][
                        "box"
                    ].copy()
                for side
                in sides
            }

            for side in invalid:
                m = metadata[
                    side
                ]

                self._update_invalid_hand(
                    side=side,
                    sequence=sequence,
                    capture_ts=capture_ts,
                    track_id=track_id,
                    elbow_conf=m[
                        "elbow_conf"
                    ],
                    wrist_conf=m[
                        "wrist_conf"
                    ],
                )

        if not boxes:
            return {
                "sequence":
                    sequence,
                "capture_ts":
                    capture_ts,
                "sides":
                    (),
                "infer_ms":
                    0.0,
            }

        dataset = (
            self.ViTDetDataset(
                self.cfg,
                frame,
                np.stack(
                    boxes
                ).astype(
                    np.float32
                ),
                np.asarray(
                    handedness,
                    dtype=np.float32,
                ),
                rescale_factor=2.0,
                fp16=True,
            )
        )

        imgs_cpu = (
            torch.stack(
                [
                    torch.as_tensor(
                        dataset[i][
                            "img"
                        ]
                    )
                    for i
                    in range(
                        len(
                            dataset
                        )
                    )
                ]
            )
        )

        t0 = (
            time.perf_counter()
        )

        with torch.cuda.stream(
            self.live_cuda_stream
        ):
            imgs = (
                imgs_cpu
                .to(
                    self.device,
                    non_blocking=True,
                )
                .half()
            )

            with torch.inference_mode():
                out = self.model(
                    {
                        "img":
                            imgs,
                    }
                )

        # Synchronize this hand stream only.
        # Do not wait for unrelated GVHMR/FASTIK CUDA work.
        self.live_cuda_stream.synchronize()

        infer_ms = (
            time.perf_counter()
            -
            t0
        ) * 1000.0

        joints = (
            out[
                "pred_keypoints_3d"
            ]
            .detach()
            .float()
            .cpu()
            .numpy()
        )

        if (
            joints.ndim < 3
            or
            joints.shape[0]
            != len(
                sides
            )
        ):
            raise RuntimeError(
                "WiLoR output count mismatch: "
                f"expected {len(sides)}, got {joints.shape}"
            )

        with self.lock:
            for i, side in enumerate(
                sides
            ):
                m = metadata[
                    side
                ]

                raw_joints = (
                    joints[
                        i
                    ]
                )

                # hand_observation canonicalizes the raw WiLoR left
                # joints once for TRUST evaluation.
                obs = (
                    build_hand_observation(
                        raw_joints,
                        side,
                        frame_id=sequence,
                        capture_timestamp=
                            capture_ts,
                        track_id=track_id,
                        detected=True,
                        crop_valid=True,
                        crop_clipped=bool(
                            m[
                                "crop_clipped"
                            ]
                        ),
                        elbow_conf=float(
                            m[
                                "elbow_conf"
                            ]
                        ),
                        wrist_conf=float(
                            m[
                                "wrist_conf"
                            ]
                        ),
                    )
                )

                decision = (
                    self.trust[
                        side
                    ].update(
                        obs
                    )
                )

                self.latest_decision[
                    side
                ] = decision

                self.latest_hand_packet_ts[
                    side
                ] = capture_ts

                self.latest_hand_sequence[
                    side
                ] = sequence

                if obs.geometry_valid:
                    # IMPORTANT:
                    # raw WiLoR left joints are still canonical/right-like.
                    # Q4 performs its OWN single restoration here.
                    #
                    # This is not a second restoration of the same state:
                    # HandObservation and Q4 maintain independent derived
                    # representations from the same raw WiLoR output.
                    self.q4.update_wilor_joints(
                        side,
                        capture_ts,
                        raw_joints,
                        restore_left_handedness=True,
                    )

        self.last_hand_infer_ms = (
            float(
                infer_ms
            )
        )

        self.jobs_completed += 1

        return {
            "sequence":
                sequence,
            "capture_ts":
                capture_ts,
            "sides":
                tuple(
                    sides
                ),
            "infer_ms":
                float(
                    infer_ms
                ),
        }

    def update_body(
        self,
        *,
        timestamp_s,
        track_id,
        post_fastik_joints,
    ):
        """Advance the independent Q4 forearm stream."""

        timestamp_s = float(
            timestamp_s
        )

        J = (
            _extract_joints24(
                post_fastik_joints
            )
        )

        with self.lock:
            for side in SIDES:
                shoulder_i, elbow_i, wrist_i = (
                    SMPL_ARM[
                        side
                    ]
                )

                self.q4.update_forearm(
                    side,
                    timestamp_s,
                    J[
                        shoulder_i
                    ],
                    J[
                        elbow_i
                    ],
                    J[
                        wrist_i
                    ],
                )

                # Freshness watchdog.
                #
                # Trust is normally updated by actual hand observations.
                # If the independent hand stream stops producing packets,
                # stale data must eventually enter SUSPECT/LOST rather than
                # remaining indefinitely TRACKING.
                hand_ts = (
                    self.latest_hand_packet_ts[
                        side
                    ]
                )

                max_age = float(
                    self.trust[
                        side
                    ].config.max_source_age_s
                )

                stale = bool(
                    hand_ts is None
                    or
                    timestamp_s
                    -
                    float(
                        hand_ts
                    )
                    >
                    max_age
                )

                if stale:
                    self._update_invalid_hand(
                        side=side,
                        sequence=-1,
                        capture_ts=timestamp_s,
                        track_id=track_id,
                        elbow_conf=None,
                        wrist_conf=None,
                        mark_packet_seen=False,
                    )

    def arm_calibration(
        self,
    ):
        """Explicitly arm one bilateral Q4 neutral calibration."""

        with self.lock:
            self.calibration_armed = True

    def try_calibrate(
        self,
    ):
        """Attempt the explicitly armed calibration.

        Returns the calibration result on success, otherwise None.
        """

        with self.lock:
            if not self.calibration_armed:
                return None

            if self.q4.is_calibrated():
                self.calibration_armed = False
                return None

            for side in SIDES:
                decision = (
                    self.latest_decision[
                        side
                    ]
                )

                if (
                    decision is None
                    or
                    decision.state
                    != HandTrustState.TRACKING
                ):
                    return None

            try:
                out = (
                    self.q4.calibrate_both(
                        max_pair_age_s=
                            self.pair_max_s,
                    )
                )

            except RuntimeError:
                return None

            self.calibration_armed = False

            self.calibration_count += 1

            self.last_calibration = out

            return out

    def command_sample(
        self,
        side,
    ):
        """Return the newest Q4 target plus frozen trust authority."""

        side = str(
            side
        ).upper()

        if side not in SIDES:
            raise ValueError(
                side
            )

        with self.lock:
            decision = (
                self.latest_decision[
                    side
                ]
            )

            if decision is None:
                trust_state = (
                    HandTrustState.LOST.value
                )

                authority = 0.0

                trust_reason = (
                    "no_hand_observation"
                )

            else:
                trust_state = (
                    decision.state.value
                )

                authority = float(
                    decision.authority
                )

                trust_reason = (
                    decision.reason
                )

            q4 = (
                self.q4.compute_latest(
                    side,
                    max_pair_age_s=
                        self.pair_max_s,
                )
            )

            usable = bool(
                q4.get(
                    "valid",
                    False,
                )
                and
                q4.get(
                    "calibrated",
                    False,
                )
                and
                "R"
                in q4
            )

            R = (
                np.asarray(
                    q4[
                        "R"
                    ],
                    dtype=np.float64,
                ).copy()
                if usable
                else None
            )

            return {
                "side":
                    side,
                "R":
                    R,
                "q4_valid":
                    bool(
                        q4.get(
                            "valid",
                            False,
                        )
                    ),
                "q4_calibrated":
                    bool(
                        q4.get(
                            "calibrated",
                            False,
                        )
                    ),
                "q4_reason":
                    q4.get(
                        "reason",
                        "ok"
                        if usable
                        else "unavailable",
                    ),
                "trust_state":
                    trust_state,
                "authority":
                    authority,
                "trust_reason":
                    trust_reason,
                "pair_age_s":
                    q4.get(
                        "pair_age_s"
                    ),
            }
