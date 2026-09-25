#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import importlib.util
import math
import os
from pathlib import Path
import sys
import threading
import time

import numpy as np
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_BASE = (
    PROJECT_ROOT
    / "perception/runtime/live_gvhmr_pair_prio2_interactive_test.py"
)

# The unified launcher supplies the current base-runner hash.
DEFAULT_BASE_SHA = ""

DEFAULT_GRAVITY = (
    PROJECT_ROOT
    / "calibration/legacy_fixed/stereo_gravity_1280x720.npz"
)

DEFAULT_REFERENCE = (
    PROJECT_ROOT
    / "calibration/reference/F_LEFT_HMR2_CALIBRATED_ROOT.npz"
)

DEFAULT_SESSION_ALIGNMENT = (
    PROJECT_ROOT
    / ".runtime/calibration/session_alignment.npz"
)

DEFAULT_REFERENCE_SHA = (
    "b06f8a293f34ee7b07f09227bdba8a18a"
    "1937a604038bc9edd88a9c27627c075"
)

DEFAULT_SONIC_ROOT = Path(
    os.environ.get(
        "SONIC_ROOT",
        str(PROJECT_ROOT / ".deps/GR00T-WholeBodyControl"),
    )
)

DEFAULT_PUBLISHER_SOURCE = (
    PROJECT_ROOT
    / "sonic/publisher"
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def parse_wrapper_args():
    ap = argparse.ArgumentParser(
        add_help=False,
    )

    ap.add_argument(
        "--sonic-mode",
        choices=(
            "off",
            "convert",
            "publish",
        ),
        default="publish",
    )

    ap.add_argument(
        "--base-runner",
        default=str(
            DEFAULT_BASE
        ),
    )

    ap.add_argument(
        "--expected-base-sha",
        default=DEFAULT_BASE_SHA,
    )

    ap.add_argument(
        "--sonic-root",
        default=str(
            DEFAULT_SONIC_ROOT
        ),
    )

    ap.add_argument(
        "--publisher-source-dir",
        default=str(
            DEFAULT_PUBLISHER_SOURCE
        ),
    )

    ap.add_argument(
        "--sonic-port",
        type=int,
        default=5556,
    )

    ap.add_argument(
        "--sonic-topic",
        default="pose",
    )

    ap.add_argument(
        "--alignment-mode",
        choices=(
            "fixed_v1",
            "session_v2",
        ),
        default="fixed_v1",
    )

    ap.add_argument(
        "--session-alignment",
        default=str(
            DEFAULT_SESSION_ALIGNMENT
        ),
    )

    ap.add_argument(
        "--gravity-file",
        default=str(
            DEFAULT_GRAVITY
        ),
    )

    ap.add_argument(
        "--calibration-reference",
        default=str(
            DEFAULT_REFERENCE
        ),
    )

    ap.add_argument(
        "--expected-reference-sha",
        default=DEFAULT_REFERENCE_SHA,
    )

    ap.add_argument(
        "--expected-camera",
        default="LEFT",
    )

    ap.add_argument(
        "--gravity-result-key",
        default="result",
    )

    ap.add_argument(
        "--gravity-result-value",
        default="STEREO_GRAVITY_PASS",
    )

    ap.add_argument(
        "--camera-from-gravity-key",
        default="R_left_from_gravity",
    )

    ap.add_argument(
        "--gravity-up-camera-key",
        default="gravity_up_left",
    )

    ap.add_argument(
        "--gravity-from-camera-key",
        default="R_gravity_from_left",
    )

    # Q5_24_V3_WRIST_ARGS_V1
    ap.add_argument(
        "--v3-wrists",
        action="store_true",
        help=(
            "Enable V3 WiLoR/Q4/trust/Q5 wrist output."
        ),
    )

    ap.add_argument(
        "--v3-wrist-calibrate-startup",
        action="store_true",
        help=(
            "Explicitly request one neutral wrist calibration "
            "after successful session_v2 body alignment."
        ),
    )

    ap.add_argument(
        "--v3-wrist-speed-deg-s",
        type=float,
        default=90.0,
        help=(
            "Conservative teleoperation wrist slew cap. "
            "This is NOT the URDF hard velocity limit."
        ),
    )

    ap.add_argument(
        "--v3-wrist-max-dt-s",
        type=float,
        default=0.20,
    )

    ap.add_argument(
        "--v3-q4-pair-max-s",
        type=float,
        default=0.20,
    )

    # Q5_26F_V3_PREVIEW_V1
    ap.add_argument(
        "--v3-preview",
        action="store_true",
        help=(
            "Enable asynchronous latest-only raw camera preview "
            "fanout without reopening the V4L2 device."
        ),
    )

    ap.add_argument(
        "--v3-preview-port",
        type=int,
        default=5602,
        help=(
            "Local ZMQ raw preview port. "
            "Default: 5602."
        ),
    )

    ap.add_argument(
        "--self-check",
        action="store_true",
    )

    args, remaining = (
        ap.parse_known_args()
    )

    return args, remaining


def main():
    args, base_args = (
        parse_wrapper_args()
    )

    # Q5_24_V3_ARG_VALIDATION_V1
    if (
        args.v3_wrist_calibrate_startup
        and not args.v3_wrists
    ):
        raise RuntimeError(
            "--v3-wrist-calibrate-startup requires --v3-wrists"
        )

    # Q5_26F_PREVIEW_ARG_VALIDATION_V1
    if (
        args.v3_preview
        and not args.v3_wrists
    ):
        raise RuntimeError(
            "--v3-preview currently requires --v3-wrists "
            "because it reuses the V3 hand-frame fanout."
        )

    if (
        args.v3_wrist_calibrate_startup
        and
        args.alignment_mode
        != "session_v2"
    ):
        raise RuntimeError(
            "Startup V3 wrist calibration currently requires "
            "--alignment-mode session_v2 so neutral is explicit."
        )

    if (
        args.v3_wrist_speed_deg_s
        <= 0.0
    ):
        raise RuntimeError(
            "--v3-wrist-speed-deg-s must be > 0"
        )

    if (
        args.v3_wrist_max_dt_s
        <= 0.0
    ):
        raise RuntimeError(
            "--v3-wrist-max-dt-s must be > 0"
        )

    if (
        args.v3_q4_pair_max_s
        <= 0.0
    ):
        raise RuntimeError(
            "--v3-q4-pair-max-s must be > 0"
        )


    base_path = Path(
        args.base_runner
    ).expanduser().resolve()

    sonic_root = Path(
        args.sonic_root
    ).expanduser().resolve()

    publisher_source = Path(
        args.publisher_source_dir
    ).expanduser().resolve()

    gravity_file = Path(
        args.gravity_file
    ).expanduser().resolve()

    reference_file = Path(
        args.calibration_reference
    ).expanduser().resolve()

    session_alignment_file = Path(
        args.session_alignment
    ).expanduser().resolve()

    required_paths = [
        base_path,
        sonic_root,
        publisher_source,
    ]

    if args.alignment_mode == "fixed_v1":
        required_paths.extend(
            [
                gravity_file,
                reference_file,
            ]
        )

    for path in required_paths:
        if not path.exists():
            raise RuntimeError(
                f"Required path missing: {path}"
            )

    if not (
        publisher_source
        / "soma_to_smpl.py"
    ).exists():
        raise RuntimeError(
            "SonicV3Publisher source missing: "
            f"{publisher_source}"
        )

    actual_base_sha = sha256(
        base_path
    )

    if (
        args.expected_base_sha
        and actual_base_sha
        != args.expected_base_sha
    ):
        raise RuntimeError(
            "Base runner SHA mismatch. "
            f"Expected {args.expected_base_sha}, "
            f"got {actual_base_sha}"
        )

    if (
        args.alignment_mode
        == "fixed_v1"
        and args.expected_reference_sha
        and sha256(
            reference_file
        )
        != args.expected_reference_sha
    ):
        raise RuntimeError(
            "Calibration reference SHA mismatch"
        )

    # Resolve SONIC before importing the reusable bridge.
    os.environ[
        "SONIC_ROOT"
    ] = str(
        sonic_root
    )

    app_dir = str(
        Path(__file__)
        .resolve()
        .parent
    )

    if app_dir not in sys.path:
        sys.path.insert(
            0,
            app_dir,
        )

    # Q5_24_V3_SANDBOX_PATH_V1
    v3_sandbox_root = str(
        PROJECT_ROOT.parent
    )

    if v3_sandbox_root not in sys.path:
        sys.path.insert(
            0,
            v3_sandbox_root,
        )

    alignment_dir = str(
        PROJECT_ROOT
        / "alignment"
    )

    if alignment_dir not in sys.path:
        sys.path.insert(
            0,
            alignment_dir,
        )

    retargeting_dir = str(
        PROJECT_ROOT
        / "retargeting"
    )

    if retargeting_dir not in sys.path:
        sys.path.insert(
            0,
            retargeting_dir,
        )

    from gvhmr_smpl24_adapter import (
        GVHMRSMPL24Adapter,
    )

    from sonic_smpl_bridge import (
        SonicCalibrationProfile,
        SonicSMPLBridge,
    )

    from session_v2_runtime import (
        SessionV2AlignmentController,
    )

    from session_v2_bridge_gate import (
        SessionV2BridgeGate,
    )

    # Q5_24_V3_IMPORTS_V1
    from v3_fusion.live_wilor_q4_runtime import (
        LiveWilorQ4Runtime,
    )

    from v3_fusion.g1_wrist_control_runtime import (
        G1WristControlRuntime,
    )

    from v3_fusion.sonic_v3_wrist_integration import (
        inject_wrists_into_bridge_fields,
    )


    print(
        "============================================================"
    )
    print(
        "GENERALIZED GVHMR -> SONIC WRAPPER"
    )
    print(
        "============================================================"
    )

    print(
        "base runner:",
        base_path,
    )

    print(
        "base SHA256:",
        actual_base_sha,
    )

    print(
        "SONIC mode:",
        args.sonic_mode,
    )

    print(
        "SONIC root:",
        sonic_root,
    )

    print(
        "publisher source:",
        publisher_source,
    )

    print(
        "alignment mode:",
        args.alignment_mode,
    )

    if args.alignment_mode == "fixed_v1":
        print(
            "gravity file:",
            gravity_file,
        )

        print(
            "calibration reference:",
            reference_file,
        )

    else:
        print(
            "session alignment:",
            session_alignment_file,
        )

    if args.self_check:
        print(
            "WRAPPER STATIC CONTRACT: PASS"
        )
        return

    def make_calibration_profile():
        return (
            SonicCalibrationProfile
            .from_paths(
                gravity_file=gravity_file,
                reference_file=reference_file,
                alignment_mode=(
                    args.alignment_mode
                ),
                session_alignment_file=(
                    session_alignment_file
                ),
                expected_reference_sha256=(
                    args.expected_reference_sha
                    or None
                ),
                expected_camera=(
                    args.expected_camera
                    or None
                ),
                gravity_result_key=(
                    args.gravity_result_key
                ),
                gravity_expected_result=(
                    args.gravity_result_value
                ),
                camera_from_gravity_key=(
                    args.camera_from_gravity_key
                ),
                gravity_up_camera_key=(
                    args.gravity_up_camera_key
                ),
                gravity_from_camera_key=(
                    args.gravity_from_camera_key
                ),
            )
        )

    # fixed_v1 uses the existing protected calibration
    # immediately.
    #
    # session_v2 deliberately does NOT construct its
    # profile until THIS run has produced a new alignment
    # artifact.
    profile = None

    if (
        args.alignment_mode
        == "fixed_v1"
    ):
        profile = (
            make_calibration_profile()
        )


    spec = (
        importlib.util
        .spec_from_file_location(
            "gvhmr_prio2_base",
            base_path,
        )
    )

    if (
        spec is None
        or spec.loader is None
    ):
        raise RuntimeError(
            "Could not load base runner"
        )

    base = (
        importlib.util
        .module_from_spec(
            spec
        )
    )

    spec.loader.exec_module(
        base
    )

    if not hasattr(
        base,
        "make_fastik_predictor",
    ):
        raise RuntimeError(
            "Base runner lacks "
            "make_fastik_predictor()"
        )

    if not hasattr(
        base,
        "main",
    ):
        raise RuntimeError(
            "Base runner lacks main()"
        )

    original_make_fastik = (
        base.make_fastik_predictor
    )

    # ----------------------------------------------------
    # Asynchronous SONIC bridge.
    #
    # The protected temporal predictor returns immediately
    # after depositing one tiny CPU snapshot into a single-slot
    # mailbox.  The worker owns the CUDA SMPL adapter, SONIC
    # bridge and ZMQ publisher.
    #
    # There is deliberately NO FIFO:
    # if a newer temporal result arrives while the bridge is
    # busy, the pending result is replaced by the newest one.
    # ----------------------------------------------------

    expected_dims = {
        "body_pose": 63,
        "betas": 10,
        "global_orient": 3,
        "transl": 3,
    }

    runtime = {
        "adapter": None,
        "bridge": None,
        "alignment_controller": None,
        "alignment_gate": None,
        "alignment_state": (
            "not_used"
            if args.alignment_mode
            == "fixed_v1"
            else "collecting"
        ),
        "worker_thread": None,
        "worker_error": None,

        "mailbox_condition": threading.Condition(),
        "pending": None,

        # V3_HAND_MAILBOX_V1
        #
        # Independent latest-only raw hand ingress.
        # WiLoR will consume this in its own worker in the next step.
        "hand_mailbox_condition": threading.Condition(),
        "hand_pending": None,
        "hand_generation": 0,
        "hand_queued": 0,
        "hand_superseded": 0,

        # Q5_24_HAND_RUNTIME_STATE_V1
        "hand_worker_thread": None,
        "hand_stop": False,
        "hand_error": None,
        "hand_runtime": None,

        "wrist_controller": None,
        "wrist_controller_initialized": False,
        "wrist_calibration_armed": False,

        # Q5_WRIST_CALIBRATION_POSE_WINDOW_V1
        "wrist_calibration_pose_waiting": False,
        "wrist_calibration_pose_deadline": None,
        "wrist_calibration_try_after": None,
        "wrist_calibrations": 0,

        # Q5_26F_PREVIEW_RUNTIME_STATE_V1
        "preview_pending": None,
        "preview_worker_thread": None,
        "preview_ready": threading.Event(),
        "preview_frames": 0,
        "preview_dropped": 0,
        "preview_error": None,
        "generation": 0,
        "stop": False,
        "ready": threading.Event(),

        "queued": 0,
        "superseded": 0,
        "converted": 0,
        "published": 0,

        "enqueue_times_ms": deque(maxlen=600),
        "queue_wait_ms": deque(maxlen=600),
        "bridge_times_ms": deque(maxlen=600),
    }

    def make_wrapped_fastik(
        gvhmr,
    ):
        fast_predict = (
            original_make_fastik(
                gvhmr
            )
        )

        if (
            args.sonic_mode
            == "off"
        ):
            return fast_predict

        # V3_HAND_INGRESS_SINK_V1
        def v3_offer_hand_frame(
            packet,
        ):
            """Cheap producer-side latest-only hand ingress."""

            cond = runtime[
                "hand_mailbox_condition"
            ]

            with cond:
                if (
                    runtime[
                        "hand_pending"
                    ]
                    is not None
                ):
                    runtime[
                        "hand_superseded"
                    ] += 1

                runtime[
                    "hand_generation"
                ] += 1

                runtime[
                    "hand_pending"
                ] = (
                    runtime[
                        "hand_generation"
                    ],
                    packet,
                    time.perf_counter(),
                )

                # Q5_26F_PREVIEW_LATEST_SLOT_V1
                if args.v3_preview:
                    if (
                        runtime[
                            "preview_pending"
                        ]
                        is not None
                    ):
                        runtime[
                            "preview_dropped"
                        ] += 1

                    # Reuse the same packet already copied
                    # for asynchronous WiLoR processing.
                    runtime[
                        "preview_pending"
                    ] = packet

                runtime[
                    "hand_queued"
                ] += 1

                cond.notify_all()

        if not hasattr(
            base,
            "set_v3_hand_frame_sink",
        ):
            raise RuntimeError(
                "V3 base runner lacks set_v3_hand_frame_sink()"
            )

        # Q5_24_HAND_WORKER_V1
        hand_runtime = None
        wrist_controller = None

        if args.v3_wrists:
            hand_runtime = (
                LiveWilorQ4Runtime(
                    pair_max_s=
                        args.v3_q4_pair_max_s,
                )
            )

            wrist_controller = (
                G1WristControlRuntime(
                    teleop_max_speed_rad_s=
                        math.radians(
                            args.v3_wrist_speed_deg_s
                        ),
                    max_dt_s=
                        args.v3_wrist_max_dt_s,
                )
            )

            runtime[
                "hand_runtime"
            ] = hand_runtime

            runtime[
                "wrist_controller"
            ] = wrist_controller

            base.set_v3_hand_frame_sink(
                v3_offer_hand_frame
            )

            def v3_hand_worker():
                while True:
                    cond = runtime[
                        "hand_mailbox_condition"
                    ]

                    with cond:
                        while (
                            runtime[
                                "hand_pending"
                            ]
                            is None
                            and not runtime[
                                "hand_stop"
                            ]
                        ):
                            cond.wait(
                                timeout=0.2
                            )

                        if runtime[
                            "hand_stop"
                        ]:
                            return

                        (
                            generation,
                            packet,
                            queued_at,
                        ) = runtime[
                            "hand_pending"
                        ]

                        # Single-slot mailbox:
                        # while WiLoR is running, producer updates simply
                        # replace this slot. There can never be a second
                        # WiLoR inference in flight.
                        runtime[
                            "hand_pending"
                        ] = None

                    try:
                        hand_runtime.process_hand_packet(
                            packet
                        )

                        runtime[
                            "hand_error"
                        ] = None

                    except Exception as exc:
                        runtime[
                            "hand_error"
                        ] = repr(
                            exc
                        )

                        print(
                            "V3 WiLoR hand worker error:",
                            repr(
                                exc
                            ),
                        )

            hand_worker = (
                threading.Thread(
                    target=v3_hand_worker,
                    name="v3-wilor-latest-worker",
                    daemon=True,
                )
            )

            runtime[
                "hand_worker_thread"
            ] = hand_worker

            hand_worker.start()

            print(
                "V3 wrist hand worker: READY"
            )

            # Q5_26F_PREVIEW_WORKER_V1
            if args.v3_preview:

                def v3_preview_worker():
                    import cv2
                    import zmq

                    endpoint = (
                        "tcp://127.0.0.1:"
                        f"{int(args.v3_preview_port)}"
                    )

                    context = (
                        zmq.Context.instance()
                    )

                    socket = context.socket(
                        zmq.PUB
                    )

                    socket.setsockopt(
                        zmq.SNDHWM,
                        1,
                    )

                    socket.setsockopt(
                        zmq.LINGER,
                        0,
                    )

                    try:
                        socket.bind(
                            endpoint
                        )

                        runtime[
                            "preview_error"
                        ] = None

                        runtime[
                            "preview_ready"
                        ].set()

                        print(
                            "V3 raw preview fanout: READY "
                            f"{endpoint} topic='raw'"
                        )

                        while True:
                            cond = runtime[
                                "hand_mailbox_condition"
                            ]

                            with cond:
                                while (
                                    runtime[
                                        "preview_pending"
                                    ]
                                    is None
                                    and not runtime[
                                        "hand_stop"
                                    ]
                                ):
                                    cond.wait(
                                        timeout=0.2
                                    )

                                if runtime[
                                    "hand_stop"
                                ]:
                                    return

                                packet = runtime[
                                    "preview_pending"
                                ]

                                runtime[
                                    "preview_pending"
                                ] = None

                            frame = packet.get(
                                "frame_bgr"
                            )

                            if frame is None:
                                continue

                            ok, encoded = (
                                cv2.imencode(
                                    ".jpg",
                                    frame,
                                    [
                                        cv2.IMWRITE_JPEG_QUALITY,
                                        80,
                                    ],
                                )
                            )

                            if not ok:
                                continue

                            try:
                                socket.send_multipart(
                                    [
                                        b"raw",
                                        encoded.tobytes(),
                                    ],
                                    flags=zmq.NOBLOCK,
                                )

                                runtime[
                                    "preview_frames"
                                ] += 1

                            except zmq.Again:
                                runtime[
                                    "preview_dropped"
                                ] += 1

                    except Exception as exc:
                        runtime[
                            "preview_error"
                        ] = repr(
                            exc
                        )

                        runtime[
                            "preview_ready"
                        ].set()

                        print(
                            "V3 raw preview worker error:",
                            repr(
                                exc
                            ),
                        )

                    finally:
                        socket.close(
                            linger=0
                        )

                preview_worker = (
                    threading.Thread(
                        target=v3_preview_worker,
                        name="v3-raw-preview-worker",
                        daemon=True,
                    )
                )

                runtime[
                    "preview_worker_thread"
                ] = preview_worker

                preview_worker.start()

                if not runtime[
                    "preview_ready"
                ].wait(
                    timeout=3.0
                ):
                    raise RuntimeError(
                        "V3 raw preview worker "
                        "did not become ready"
                    )

                if runtime[
                    "preview_error"
                ] is not None:
                    raise RuntimeError(
                        "V3 raw preview startup failed: "
                        + runtime[
                            "preview_error"
                        ]
                    )


        else:
            # Important: when V3 wrists are disabled, remove the hook so
            # the copied body runner does not even copy camera frames for
            # hand processing.
            base.set_v3_hand_frame_sink(
                None
            )

        def sonic_worker():
            adapter = None
            bridge = None
            alignment_controller = None
            alignment_gate = None

            try:
                # Adapter is created and used only in this
                # worker, preserving CUDA/thread ownership.
                adapter = (
                    GVHMRSMPL24Adapter(
                        gvhmr_root=Path(
                            os.environ.get(
                                "LIVE_GVHMR_GV",
                                str(
                                    PROJECT_ROOT
                                    / ".deps/GVHMR"
                                ),
                            )
                        ),
                        device="cuda",
                    )
                )

                runtime[
                    "adapter"
                ] = adapter

                def create_sonic_bridge():
                    bridge_profile = profile

                    if bridge_profile is None:
                        # session_v2 reaches here only after
                        # THIS run has successfully written
                        # session_alignment.npz.
                        bridge_profile = (
                            make_calibration_profile()
                        )

                    return SonicSMPLBridge(
                        profile=bridge_profile,
                        device="cuda",
                        history_weight=float(
                            os.environ.get(
                                "SONIC_EMA_WEIGHT",
                                "0.0",
                            )
                        ),
                        sonic_root=sonic_root,
                        publisher_source_dir=(
                            publisher_source
                        ),
                        port=args.sonic_port,
                        topic=args.sonic_topic,
                        enable_publisher=(
                            args.sonic_mode
                            == "publish"
                        ),
                    )

                if (
                    args.alignment_mode
                    == "fixed_v1"
                ):
                    # ------------------------------
                    # Protected V1 startup path.
                    # ------------------------------
                    bridge = (
                        create_sonic_bridge()
                    )

                    runtime[
                        "bridge"
                    ] = bridge

                    print(
                        "SMPL24 adapter worker: READY"
                    )

                    print(
                        "F calibration camera:",
                        bridge.camera,
                    )

                    print(
                        "SONIC EMA history weight:",
                        bridge.history_weight,
                    )

                    if (
                        args.sonic_mode
                        == "publish"
                    ):
                        print(
                            "Protocol-v3 publisher worker "
                            "bound to "
                            f"tcp://*:{args.sonic_port} "
                            f"topic={args.sonic_topic}"
                        )

                else:
                    # ------------------------------
                    # V2 startup.
                    #
                    # Adapter/controller are ready,
                    # but there is intentionally NO
                    # SONIC bridge or publisher yet.
                    # ------------------------------

                    K_runtime = (
                        base.estimate_K(
                            base.WIDTH,
                            base.HEIGHT,
                        )
                    )

                    if torch.is_tensor(
                        K_runtime
                    ):
                        K_runtime = (
                            K_runtime
                            .detach()
                            .cpu()
                            .numpy()
                        )

                    else:
                        K_runtime = (
                            np.asarray(
                                K_runtime,
                                dtype=np.float32,
                            )
                        )

                    session_json_file = (
                        session_alignment_file
                        .with_suffix(
                            ".json"
                        )
                    )

                    alignment_controller = (
                        SessionV2AlignmentController(
                            npz_path=(
                                session_alignment_file
                            ),
                            json_path=(
                                session_json_file
                            ),
                            image_width=(
                                int(base.WIDTH)
                            ),
                            image_height=(
                                int(base.HEIGHT)
                            ),
                            K_fullimg=(
                                K_runtime
                            ),
                            intrinsics_source=(
                                "gvhmr_estimate_K"
                            ),
                            smoothing_history_weight=float(
                                os.environ.get(
                                    "SONIC_EMA_WEIGHT",
                                    "0.0",
                                )
                            ),
                            min_duration_s=2.0,
                            max_duration_s=5.0,

                            # V3_SESSION_ALIGNMENT_MIN_FRAMES_18_V1
                            # Preserve all neutral-pose quality checks
                            # and timing gates; only reduce the number
                            # of accepted neutral samples required.
                            min_frames=18,
                        )
                    )

                    alignment_gate = (
                        SessionV2BridgeGate(
                            controller=(
                                alignment_controller
                            ),
                            bridge_factory=(
                                create_sonic_bridge
                            ),
                        )
                    )

                    runtime[
                        "alignment_controller"
                    ] = alignment_controller

                    runtime[
                        "alignment_gate"
                    ] = alignment_gate

                    runtime[
                        "alignment_state"
                    ] = "collecting"

                    print(
                        "SMPL24 adapter worker: READY"
                    )

                    print()
                    print(
                        "============================================================"
                    )
                    print(
                        "CAMERA POSE TELEOP V2 "
                        "— NEUTRAL ALIGNMENT"
                    )
                    print(
                        "============================================================"
                    )
                    print(
                        "Stand neutral. "
                        "Keep your full body visible."
                    )
                    print(
                        "NO TELEOP DATA IS BEING PUBLISHED."
                    )
                    print(
                        "SONIC bridge: NOT CREATED"
                    )
                    print(
                        "Publisher: NOT CREATED"
                    )
                    print(
                        "============================================================"
                    )

                # This event means WORKER STARTUP READY.
                #
                # In V2 it intentionally does NOT mean
                # alignment/bridge/publisher ready.
                runtime[
                    "ready"
                ].set()

                last_alignment_print_s = (
                    float("-inf")
                )

                while True:
                    cond = runtime[
                        "mailbox_condition"
                    ]

                    with cond:
                        while (
                            runtime["pending"]
                            is None
                            and not runtime["stop"]
                        ):
                            cond.wait(
                                timeout=0.2
                            )

                        if (
                            runtime["pending"]
                            is None
                            and runtime["stop"]
                        ):
                            break

                        # V3_BODY_MAILBOX_UNPACK_V1
                        # Q5_24_BODY_UNPACK_POST_FASTIK_V1
                        (
                            generation,
                            flat_cpu,
                            queued_at,
                            body_capture_sequence,
                            body_capture_ts,
                            body_track_id,
                            post_fastik_cpu,
                        ) = runtime[
                            "pending"
                        ]

                        runtime[
                            "pending"
                        ] = None

                    # V3_BODY_LATEST_METADATA_V1
                    runtime[
                        "body_capture_sequence"
                    ] = body_capture_sequence

                    runtime[
                        "body_capture_ts"
                    ] = body_capture_ts

                    runtime[
                        "body_track_id"
                    ] = body_track_id

                    worker_start = (
                        time.perf_counter()
                    )

                    runtime[
                        "queue_wait_ms"
                    ].append(
                        (
                            worker_start
                            - queued_at
                        )
                        * 1000.0
                    )

                    # 63 + 10 + 3 + 3 = 79 floats.
                    flat_gpu = flat_cpu.to(
                        device="cuda",
                        dtype=torch.float32,
                    )

                    params_last = {}

                    offset = 0

                    for key, dim in (
                        expected_dims.items()
                    ):
                        params_last[
                            key
                        ] = flat_gpu[
                            offset:
                            offset + dim
                        ]

                        offset += dim

                    with torch.inference_mode():
                        joints24 = (
                            adapter.joints24(
                                params_last
                            )
                        )

                    # Q5_24_Q4_BODY_UPDATE_V1
                    if args.v3_wrists:
                        if post_fastik_cpu is None:
                            raise RuntimeError(
                                "V3 post-FASTIK body snapshot missing"
                            )

                        if not np.isfinite(
                            body_capture_ts
                        ):
                            raise RuntimeError(
                                "V3 wrist body timestamp is non-finite"
                            )

                        hand_runtime.update_body(
                            timestamp_s=
                                body_capture_ts,
                            track_id=
                                body_track_id,
                            post_fastik_joints=
                                post_fastik_cpu,
                        )

                        # Q5_WRIST_CALIBRATION_POSE_WINDOW_V1
                        if (
                            runtime[
                                "wrist_calibration_pose_waiting"
                            ]
                            and not runtime[
                                "wrist_controller_initialized"
                            ]
                        ):
                            pose_deadline = runtime[
                                "wrist_calibration_pose_deadline"
                            ]

                            if (
                                pose_deadline is not None
                                and
                                time.monotonic()
                                >= pose_deadline
                            ):
                                hand_runtime.arm_calibration()

                                runtime[
                                    "wrist_calibration_pose_waiting"
                                ] = False

                                runtime[
                                    "wrist_calibration_pose_deadline"
                                ] = None

                                runtime[
                                    "wrist_calibration_armed"
                                ] = True

                                # pair_max_s is currently 0.20 s.
                                # Wait slightly longer than that horizon so
                                # pre-arm hand observations cannot be reused.
                                fresh_delay_s = max(
                                    float(
                                        hand_runtime.pair_max_s
                                    )
                                    + 0.05,
                                    0.25,
                                )

                                runtime[
                                    "wrist_calibration_try_after"
                                ] = (
                                    time.monotonic()
                                    + fresh_delay_s
                                )

                                print()
                                print(
                                    "V3 wrist calibration: ARMED"
                                )
                                print(
                                    "Waiting for a fresh post-arm "
                                    "trusted hand/body pair."
                                )
                                print(
                                    "Fresh-pair barrier: "
                                    f"{fresh_delay_s:.3f} s"
                                )

                        if (
                            runtime[
                                "wrist_calibration_armed"
                            ]
                            and
                            runtime[
                                "wrist_calibration_try_after"
                            ]
                            is not None
                            and
                            time.monotonic()
                            >= runtime[
                                "wrist_calibration_try_after"
                            ]
                            and not runtime[
                                "wrist_controller_initialized"
                            ]
                        ):
                            calibration = (
                                hand_runtime.try_calibrate()
                            )

                            if calibration is not None:
                                wrist_controller.initialize_neutral(
                                    body_capture_ts
                                )

                                runtime[
                                    "wrist_controller_initialized"
                                ] = True

                                runtime[
                                    "wrist_calibration_armed"
                                ] = False

                                runtime[
                                    "wrist_calibrations"
                                ] += 1

                                print()
                                print(
                                    "========================================"
                                )
                                print(
                                    "V3 WRIST CALIBRATION: PASS"
                                )
                                print(
                                    "Q4 explicit neutral locked."
                                )
                                print(
                                    "Q5 physical wrist target initialized "
                                    "to zero-relative neutral."
                                )
                                print(
                                    "========================================"
                                )


                    # ==========================================
                    # V2 CALIBRATION GATE
                    # ==========================================
                    if (
                        args.alignment_mode
                        == "session_v2"
                        and bridge is None
                    ):
                        joints24_cpu = (
                            joints24
                            .detach()
                            .to(
                                device="cpu",
                                dtype=torch.float32,
                            )
                            .numpy()
                        )

                        # Adapter normally returns (24,3),
                        # but safely unwrap singleton batch dims.
                        while (
                            joints24_cpu.ndim
                            > 2
                            and joints24_cpu.shape[0]
                            == 1
                        ):
                            joints24_cpu = (
                                joints24_cpu[0]
                            )

                        alignment_now = (
                            time.perf_counter()
                        )

                        (
                            alignment_status,
                            maybe_bridge,
                            bridge_created_now,
                        ) = (
                            alignment_gate
                            .process_alignment_frame(
                                joints24_cpu,
                                timestamp_s=(
                                    alignment_now
                                ),
                            )
                        )

                        runtime[
                            "alignment_state"
                        ] = (
                            alignment_status.state
                        )

                        elapsed = (
                            alignment_status
                            .elapsed_s
                        )

                        if (
                            alignment_status.state
                            != "collecting"
                            or (
                                elapsed
                                - last_alignment_print_s
                            )
                            >= 0.5
                        ):
                            print()
                            print(
                                alignment_status.message
                            )

                            last_alignment_print_s = (
                                elapsed
                            )

                        if (
                            alignment_status.state
                            == "failed"
                        ):
                            runtime[
                                "worker_error"
                            ] = (
                                "Camera Pose Teleop V2 "
                                "alignment failed: "
                                + alignment_status.message
                                .replace(
                                    "\n",
                                    " | ",
                                )
                            )

                            print()
                            print(
                                "SONIC bridge remains absent."
                            )
                            print(
                                "Publisher remains absent."
                            )
                            print(
                                "Restart Camera Pose Teleop "
                                "to retry alignment."
                            )

                            break

                        if bridge_created_now:
                            bridge = maybe_bridge

                            runtime[
                                "bridge"
                            ] = bridge

                            runtime[
                                "alignment_state"
                            ] = "ready"

                            print()
                            print(
                                "SONIC bridge: CREATED"
                            )

                            print(
                                "SONIC EMA history weight:",
                                bridge.history_weight,
                            )

                            if (
                                bridge.publisher
                                is not None
                            ):
                                print(
                                    "Protocol-v3 publisher "
                                    "worker bound to "
                                    f"tcp://*:"
                                    f"{args.sonic_port} "
                                    f"topic="
                                    f"{args.sonic_topic}"
                                )

                            # Q5_24_ARM_WRIST_CALIBRATION_V1
                            if (
                                args.v3_wrists
                                and
                                args.v3_wrist_calibrate_startup
                            ):
                                # Q5_WRIST_CALIBRATION_POSE_WINDOW_V1
                                #
                                # Body/session alignment requires the normal
                                # arms-down neutral pose, while Q4 wrist
                                # calibration requires bent elbows.  Do not
                                # calibrate from the first frame after body
                                # alignment; give the operator time to change
                                # pose first.
                                pose_delay_s = max(
                                    0.0,
                                    float(
                                        os.environ.get(
                                            "V3_WRIST_CALIBRATION_POSE_DELAY_S",
                                            "5.0",
                                        )
                                    ),
                                )

                                runtime[
                                    "wrist_calibration_pose_waiting"
                                ] = True

                                runtime[
                                    "wrist_calibration_pose_deadline"
                                ] = (
                                    time.monotonic()
                                    + pose_delay_s
                                )

                                runtime[
                                    "wrist_calibration_try_after"
                                ] = None

                                print()
                                print(
                                    "========================================"
                                )
                                print(
                                    "V3 WRIST CALIBRATION: POSE WINDOW"
                                )
                                print(
                                    "Move now to the wrist-neutral pose:"
                                )
                                print(
                                    "  BOTH elbows bent"
                                )
                                print(
                                    "  forearms near/roughly parallel to torso"
                                )
                                print(
                                    "  wrists neutral"
                                )
                                print(
                                    "  BOTH hands clearly visible"
                                )
                                print(
                                    "Calibration will arm in "
                                    f"{pose_delay_s:.1f} seconds."
                                )
                                print(
                                    "Hold that pose until calibration PASS."
                                )
                                print(
                                    "========================================"
                                )

                            # Critical:
                            # do not teleoperate from the
                            # final calibration frame.
                            # Teleop starts with the NEXT fresh
                            # GVHMR result.
                            continue

                        # Still collecting:
                        # no conversion and no publishing.
                        continue

                    if bridge is None:
                        raise RuntimeError(
                            "Internal error: SONIC bridge "
                            "missing outside V2 calibration"
                        )

                    bridge_start = (
                        time.perf_counter()
                    )

                    with torch.inference_mode():
                        fields = bridge.convert(
                            joints24,
                            params_last[
                                "global_orient"
                            ],
                        )

                        # Q5_24_WRIST_FIELD_INJECTION_V1
                        if (
                            args.v3_wrists
                            and
                            runtime[
                                "wrist_controller_initialized"
                            ]
                        ):
                            if np.isfinite(
                                body_capture_ts
                            ):
                                for side in (
                                    "L",
                                    "R",
                                ):
                                    sample = (
                                        hand_runtime.command_sample(
                                            side
                                        )
                                    )

                                    R_target = (
                                        sample[
                                            "R"
                                        ]
                                    )

                                    trust_state = (
                                        sample[
                                            "trust_state"
                                        ]
                                    )

                                    authority = float(
                                        sample[
                                            "authority"
                                        ]
                                    )

                                    # If Q4 cannot provide a compatible
                                    # calibrated pair, fail safe to HOLD.
                                    # We do not feed stale/bad geometry into
                                    # the stateful Q5 mapper.
                                    if R_target is None:
                                        trust_state = "LOST"
                                        authority = 0.0

                                    wrist_controller.update_side(
                                        side,
                                        body_capture_ts,
                                        R_target,
                                        trust_state=
                                            trust_state,
                                        authority=
                                            authority,
                                    )

                            fields = (
                                inject_wrists_into_bridge_fields(
                                    fields,
                                    wrist_controller.sonic_wrists(),
                                    copy_fields=False,
                                )
                            )

                        if (
                            bridge.publisher
                            is not None
                        ):
                            if args.v3_wrists:
                                v3_wrist_diag.record_publish(
                                    fields
                                )

                            bridge.publisher.publish(
                                fields
                            )

                            runtime[
                                "published"
                            ] += 1

                    runtime[
                        "converted"
                    ] += 1

                    runtime[
                        "bridge_times_ms"
                    ].append(
                        (
                            time.perf_counter()
                            - bridge_start
                        )
                        * 1000.0
                    )

            except Exception as exc:
                runtime[
                    "worker_error"
                ] = repr(exc)

                print(
                    "SONIC ASYNC WORKER ERROR:",
                    repr(exc),
                )

                runtime[
                    "ready"
                ].set()

            finally:
                if bridge is not None:
                    bridge.close()

        worker = threading.Thread(
            target=sonic_worker,
            name="sonic-v3-latest-worker",
            daemon=True,
        )

        runtime[
            "worker_thread"
        ] = worker

        worker.start()

        if not runtime[
            "ready"
        ].wait(
            timeout=30.0
        ):
            raise RuntimeError(
                "Timed out waiting for "
                "SONIC async worker startup."
            )

        if (
            runtime[
                "worker_error"
            ]
            is not None
        ):
            raise RuntimeError(
                "SONIC async worker failed "
                "during startup: "
                + runtime[
                    "worker_error"
                ]
            )

        def wrapped_fast_predict(
            data,
            static_cam=True,
        ):
            prediction = fast_predict(
                data,
                static_cam=static_cam,
            )

            # Q5_24_POST_FASTIK_SNAPSHOT_V1
            post_fastik_cpu = None

            if args.v3_wrists:
                post_fastik = prediction.get(
                    "v3_post_fastik_joints_last"
                )

                if post_fastik is None:
                    raise RuntimeError(
                        "V3 wrist mode requires "
                        "v3_post_fastik_joints_last"
                    )

                post_fastik_cpu = (
                    torch.as_tensor(
                        post_fastik
                    )
                    .detach()
                    .to(
                        device="cpu",
                        dtype=torch.float32,
                    )
                    .contiguous()
                )


            # V3_BODY_SOURCE_METADATA_V1
            body_capture_sequence = int(
                data.get(
                    "v3_capture_sequence",
                    -1,
                )
            )

            body_capture_ts = float(
                data.get(
                    "v3_capture_ts",
                    float("nan"),
                )
            )

            body_track_id = int(
                data.get(
                    "v3_track_id",
                    -1,
                )
            )

            t0 = time.perf_counter()

            incam = prediction[
                "smpl_params_incam"
            ]

            pieces = []

            for key, dim in (
                expected_dims.items()
            ):
                if key not in incam:
                    raise RuntimeError(
                        f"Missing GVHMR SMPL key: {key}"
                    )

                value = incam[
                    key
                ]

                if not torch.is_tensor(
                    value
                ):
                    value = torch.as_tensor(
                        value,
                        dtype=torch.float32,
                        device="cuda",
                    )

                if value.shape[-1] != dim:
                    raise RuntimeError(
                        f"{key}: expected final "
                        f"dimension {dim}, "
                        f"got {tuple(value.shape)}"
                    )

                if value.ndim == 1:
                    newest = value
                else:
                    newest = value[
                        -1
                    ]

                pieces.append(
                    newest
                    .detach()
                    .reshape(-1)
                )

            # Safe cross-thread snapshot.
            #
            # This is only 79 float32 values and prevents the
            # worker from retaining/reusing prediction tensors
            # owned by the temporal inference path.
            flat_cpu = (
                torch.cat(
                    pieces,
                    dim=0,
                )
                .to(
                    device="cpu",
                    dtype=torch.float32,
                )
                .contiguous()
            )

            queued_at = (
                time.perf_counter()
            )

            cond = runtime[
                "mailbox_condition"
            ]

            with cond:
                if (
                    runtime[
                        "pending"
                    ]
                    is not None
                ):
                    runtime[
                        "superseded"
                    ] += 1

                runtime[
                    "generation"
                ] += 1

                # V3_BODY_MAILBOX_METADATA_V1
                # Q5_24_BODY_MAILBOX_POST_FASTIK_V1
                runtime[
                    "pending"
                ] = (
                    runtime[
                        "generation"
                    ],
                    flat_cpu,
                    queued_at,
                    body_capture_sequence,
                    body_capture_ts,
                    body_track_id,
                    post_fastik_cpu,
                )

                runtime[
                    "queued"
                ] += 1

                cond.notify()

            runtime[
                "enqueue_times_ms"
            ].append(
                (
                    time.perf_counter()
                    - t0
                )
                * 1000.0
            )

            if (
                runtime[
                    "worker_error"
                ]
                is not None
            ):
                raise RuntimeError(
                    "SONIC async worker failed: "
                    + runtime[
                        "worker_error"
                    ]
                )

            return prediction

        return wrapped_fast_predict

    base.make_fastik_predictor = (
        make_wrapped_fastik
    )

    # Remove wrapper-only arguments before handing control
    # to the protected/base runner.
    sys.argv = [
        str(
            base_path
        ),
        *base_args,
    ]

    try:
        base.main()

    finally:
        cond = runtime[
            "mailbox_condition"
        ]

        with cond:
            runtime[
                "stop"
            ] = True

            cond.notify_all()

        # Q5_24_HAND_WORKER_SHUTDOWN_V1
        if hasattr(
            base,
            "set_v3_hand_frame_sink",
        ):
            base.set_v3_hand_frame_sink(
                None
            )

        hand_cond = runtime[
            "hand_mailbox_condition"
        ]

        with hand_cond:
            runtime[
                "hand_stop"
            ] = True

            hand_cond.notify_all()

        hand_worker = runtime[
            "hand_worker_thread"
        ]

        if hand_worker is not None:
            hand_worker.join(
                timeout=3.0
            )

            if hand_worker.is_alive():
                print(
                    "WARNING: V3 WiLoR hand worker "
                    "did not stop within timeout."
                )

        # Q5_26F_PREVIEW_WORKER_SHUTDOWN_V1
        preview_worker = runtime[
            "preview_worker_thread"
        ]

        if preview_worker is not None:
            preview_worker.join(
                timeout=3.0
            )

            if preview_worker.is_alive():
                print(
                    "WARNING: V3 raw preview worker "
                    "did not stop within timeout."
                )


        worker = runtime[
            "worker_thread"
        ]

        if worker is not None:
            worker.join(
                timeout=10.0
            )

            if worker.is_alive():
                print(
                    "WARNING: SONIC async worker "
                    "did not stop within 10 s."
                )

        enqueue = np.asarray(
            runtime[
                "enqueue_times_ms"
            ],
            dtype=np.float64,
        )

        queue_wait = np.asarray(
            runtime[
                "queue_wait_ms"
            ],
            dtype=np.float64,
        )

        bridge_times = np.asarray(
            runtime[
                "bridge_times_ms"
            ],
            dtype=np.float64,
        )

        print()
        print(
            "============================================================"
        )
        print(
            "SONIC ASYNC BRIDGE RUNTIME"
        )
        print(
            "============================================================"
        )

        print(
            "queued:",
            runtime[
                "queued"
            ],
        )

        print(
            "superseded pending:",
            runtime[
                "superseded"
            ],
        )

        print(
            "converted:",
            runtime[
                "converted"
            ],
        )

        print(
            "published:",
            runtime[
                "published"
            ],
        )

        print(
            "worker error:",
            runtime[
                "worker_error"
            ],
        )

        if enqueue.size:
            print(
                "temporal enqueue mean:",
                f"{enqueue.mean():.3f} ms",
            )

            print(
                "temporal enqueue median:",
                f"{np.median(enqueue):.3f} ms",
            )

            print(
                "temporal enqueue p95:",
                f"{np.percentile(enqueue,95):.3f} ms",
            )

            print(
                "temporal enqueue max:",
                f"{enqueue.max():.3f} ms",
            )

        if queue_wait.size:
            print(
                "worker queue wait median:",
                f"{np.median(queue_wait):.3f} ms",
            )

            print(
                "worker queue wait p95:",
                f"{np.percentile(queue_wait,95):.3f} ms",
            )

        if bridge_times.size:
            print(
                "worker bridge mean:",
                f"{bridge_times.mean():.3f} ms",
            )

            print(
                "worker bridge median:",
                f"{np.median(bridge_times):.3f} ms",
            )

            print(
                "worker bridge p95:",
                f"{np.percentile(bridge_times,95):.3f} ms",
            )

            print(
                "worker bridge max:",
                f"{bridge_times.max():.3f} ms",
            )



if __name__ == "__main__":
    main()
