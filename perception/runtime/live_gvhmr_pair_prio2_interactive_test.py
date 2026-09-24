#!/usr/bin/env python3

from __future__ import annotations

import os
import subprocess
import threading
import time

from collections import (
    Counter,
    deque,
)

from concurrent.futures import (
    ThreadPoolExecutor,
)

from pathlib import Path

import cv2
import hydra
import numpy as np
import onnxruntime as ort
import torch

from hydra import (
    compose,
    initialize_config_module,
)

from torch2trt import TRTModule

from hmr4d.configs import (
    register_store_gvhmr,
)

from hmr4d.model.gvhmr.gvhmr_pl_demo import (
    DemoPL,
)

from hmr4d.utils.geo.hmr_cam import (
    estimate_K,
    get_bbx_xys_from_xyxy,
    normalize_kp2d,
)

from hmr4d.utils.geo_transform import (
    compute_cam_angvel,
)

from hmr4d.model.gvhmr.utils.postprocess import (
    pp_static_joint_cam,
)

from hmr4d.utils.geo.quaternion import (
    qbetween,
    qmul,
    qrot,
    qslerp,
)

from pytorch3d.transforms import (
    matrix_to_axis_angle,
    matrix_to_quaternion,
)

import hmr4d.utils.matrix as matrix

from gem.utils.yolox_detector import (
    YOLOXDetector,
    ByteTracker,
)

from scripts.demo.onnx_runners import (
    run_hmr2_single_frame,
    run_vitpose_single_frame,
)


GV = Path(
    os.environ["LIVE_GVHMR_GV"]
)

CAMERA_DEVICE = os.environ[
    "LIVE_GVHMR_CAM"
]

VIT_STATE = Path(
    os.environ["LIVE_GVHMR_VIT_STATE"]
)

HMR_ONNX = Path(
    os.environ["LIVE_GVHMR_HMR_ONNX"]
)

HMR_CACHE = Path(
    os.environ["LIVE_GVHMR_HMR_CACHE"]
)

OUT_PREFIX = Path(
    os.environ["LIVE_GVHMR_OUT_PREFIX"]
)


WIDTH = int(
    os.environ.get(
        "LIVE_GVHMR_WIDTH",
        "1280",
    )
)

HEIGHT = int(
    os.environ.get(
        "LIVE_GVHMR_HEIGHT",
        "720",
    )
)

CAPTURE_FPS = float(
    os.environ.get(
        "LIVE_GVHMR_FPS",
        "30",
    )
)

CAMERA_INPUT_FORMAT = os.environ.get(
    "LIVE_GVHMR_INPUT_FORMAT",
    "mjpeg",
)

CAMERA_FOURCC = os.environ.get(
    "LIVE_GVHMR_FOURCC",
    "MJPG",
)

# FFmpeg continues capturing at 30 Hz.
# Only delivery into the neural frontend is rate-limited.
FRONTEND_TARGET_FPS = 15.0

HISTORY = 30
YOLO_PERIOD = 30

TEST_DURATION_S = float("inf")

DEBUG_VIDEO_FPS = 10.0


class _NullVideoWriter:
    """Interactive mode: no endless debug video."""

    def __init__(self, *args, **kwargs):
        pass

    def isOpened(self):
        return True

    def write(self, frame):
        pass

    def release(self):
        pass


COCO_EDGES = (
    (5, 7),
    (7, 9),
    (6, 8),
    (8, 10),
    (5, 6),
    (5, 11),
    (6, 12),
    (11, 12),
    (11, 13),
    (13, 15),
    (12, 14),
    (14, 16),
)




# FASTIK_POSITION_ONLY_COMPILED_V1

PARENTS = [
    -1,
    0, 0, 0,
    1, 2, 3,
    4, 5, 6,
    7, 8,
    9, 9, 9,
    12, 13, 14,
    16, 17, 18, 19,
]

CHAINS = [
    (
        [0, 1, 4, 7, 10],
        [7, 10],
        [3, 4],
    ),
    (
        [0, 2, 5, 8, 11],
        [8, 11],
        [3, 4],
    ),
    (
        [9, 13, 16, 18, 20],
        [20],
        [4],
    ),
    (
        [9, 14, 17, 19, 21],
        [21],
        [4],
    ),
]

CONTACT_JOINTS = [
    7,
    10,
    8,
    11,
    20,
    21,
]

def forward_kinematics_chain(
    local_mat,
):
    J = local_mat.shape[-3]

    out = [
        local_mat[
            ...,
            0,
            :,
            :,
        ]
    ]

    for j in range(
        1,
        J,
    ):
        out.append(
            out[
                j - 1
            ]
            @ local_mat[
                ...,
                j,
                :,
                :,
            ]
        )

    return torch.stack(
        out,
        dim=-3,
    )

def position_only_chain(
    local_mat,
    target_pos,
    chain,
    target_ind,
):
    global_full = (
        matrix.forward_kinematics(
            local_mat,
            PARENTS,
        )
    )

    lm = (
        local_mat[
            ...,
            chain,
            :,
            :,
        ]
        .clone()
    )

    lm[
        ...,
        0,
        :,
        :,
    ] = (
        global_full[
            ...,
            chain[0],
            :,
            :,
        ]
    )

    global_mat = (
        forward_kinematics_chain(
            lm
        )
    )

    J_N = len(
        chain
    )

    for _ in range(
        2
    ):

        for i in range(
            1,
            J_N - 1,
        ):

            pos = (
                matrix.get_position(
                    global_mat
                )[
                    ...,
                    i,
                    :,
                ]
            )

            rot = (
                matrix.get_rotation(
                    global_mat
                )[
                    ...,
                    i,
                    :,
                    :,
                ]
            )

            quat = (
                matrix_to_quaternion(
                    rot
                )
            )

            x_vec = torch.zeros(
                quat.shape[:-1]
                + (
                    3,
                ),
                device=quat.device,
                dtype=quat.dtype,
            )

            y_vec = torch.zeros(
                quat.shape[:-1]
                + (
                    3,
                ),
                device=quat.device,
                dtype=quat.dtype,
            )

            x_vec[
                ...,
                0,
            ] = 1.0

            y_vec[
                ...,
                1,
            ] = 1.0

            x_sum = torch.zeros_like(
                x_vec
            )

            y_sum = torch.zeros_like(
                y_vec
            )

            count = 0

            for target_i, j in enumerate(
                target_ind
            ):

                if i >= j:
                    continue

                end_pos = (
                    matrix.get_position(
                        global_mat
                    )[
                        ...,
                        j,
                        :,
                    ]
                )

                solved_q = (
                    qslerp(
                        quat,
                        qmul(
                            qbetween(
                                end_pos
                                - pos,
                                target_pos[
                                    ...,
                                    target_i,
                                    :,
                                ]
                                - pos,
                            ),
                            quat,
                        ),
                        (
                            i
                            + 1
                        )
                        / J_N,
                    )
                )

                x_sum = (
                    x_sum
                    + qrot(
                        solved_q,
                        x_vec,
                    )
                )

                y_sum = (
                    y_sum
                    + qrot(
                        solved_q,
                        y_vec,
                    )
                )

                count += 1

            if count > 0:

                x_avg = (
                    matrix.normalize(
                        x_sum
                        / count
                    )
                )

                y_avg = (
                    matrix.normalize(
                        y_sum
                        / count
                    )
                )

                z_avg = torch.cross(
                    x_avg,
                    y_avg,
                    dim=-1,
                )

                solved_rot = (
                    torch.stack(
                        [
                            x_avg,
                            y_avg,
                            z_avg,
                        ],
                        dim=-1,
                    )
                )

                parent_rot = (
                    matrix.get_rotation(
                        global_mat
                    )[
                        ...,
                        i - 1,
                        :,
                        :,
                    ]
                )

                solved_local_rot = (
                    matrix.get_mat_BtoA(
                        parent_rot,
                        solved_rot,
                    )
                )

                new_lm = (
                    lm.clone()
                )

                new_lm[
                    ...,
                    i,
                    :-1,
                    :-1,
                ] = solved_local_rot

                lm = new_lm

                global_mat = (
                    forward_kinematics_chain(
                        lm
                    )
                )

    return lm

def position_only_four_chains(
    local_last,
    ll_pos,
    rl_pos,
    lh_pos,
    rh_pos,
):
    lm = (
        local_last.clone()
    )

    targets = [
        ll_pos,
        rl_pos,
        lh_pos,
        rh_pos,
    ]

    for (
        chain,
        _source_ids,
        target_ind,
    ), target_pos in zip(
        CHAINS,
        targets,
    ):

        solved_chain = (
            position_only_chain(
                lm,
                target_pos,
                chain,
                target_ind,
            )
        )

        chain_rot = (
            matrix.get_rotation(
                solved_chain
            )
        )

        new_lm = (
            lm.clone()
        )

        new_lm[
            :,
            :,
            chain[
                1:
            ],
            :-1,
            :-1,
        ] = (
            chain_rot[
                :,
                :,
                1:,
            ]
        )

        lm = new_lm

    return (
        matrix_to_axis_angle(
            matrix.get_rotation(
                lm[
                    :,
                    :,
                    1:,
                ]
            )
        )
        .flatten(
            2
        )
    )

def position_only_pair(
    local_mat,
    left_target,
    right_target,
    left_chain,
    right_chain,
    target_ind,
):
    global_full = (
        matrix.forward_kinematics(
            local_mat,
            PARENTS,
        )
    )

    left_lm = (
        local_mat[
            ...,
            left_chain,
            :,
            :,
        ]
        .clone()
    )

    right_lm = (
        local_mat[
            ...,
            right_chain,
            :,
            :,
        ]
        .clone()
    )

    lm = torch.cat(
        (
            left_lm,
            right_lm,
        ),
        dim=0,
    )

    left_root = (
        global_full[
            ...,
            left_chain[0],
            :,
            :,
        ]
    )

    right_root = (
        global_full[
            ...,
            right_chain[0],
            :,
            :,
        ]
    )

    roots = torch.cat(
        (
            left_root,
            right_root,
        ),
        dim=0,
    )

    lm[
        ...,
        0,
        :,
        :,
    ] = roots

    target_pos = torch.cat(
        (
            left_target,
            right_target,
        ),
        dim=0,
    )

    global_mat = (
        forward_kinematics_chain(
            lm
        )
    )

    J_N = lm.shape[-3]

    for _ in range(2):

        for i in range(
            1,
            J_N - 1,
        ):

            pos = (
                matrix.get_position(
                    global_mat
                )[
                    ...,
                    i,
                    :,
                ]
            )

            rot = (
                matrix.get_rotation(
                    global_mat
                )[
                    ...,
                    i,
                    :,
                    :,
                ]
            )

            quat = (
                matrix_to_quaternion(
                    rot
                )
            )

            x_vec = torch.zeros(
                quat.shape[:-1]
                + (
                    3,
                ),
                device=quat.device,
                dtype=quat.dtype,
            )

            y_vec = torch.zeros(
                quat.shape[:-1]
                + (
                    3,
                ),
                device=quat.device,
                dtype=quat.dtype,
            )

            x_vec[
                ...,
                0,
            ] = 1.0

            y_vec[
                ...,
                1,
            ] = 1.0

            x_sum = torch.zeros_like(
                x_vec
            )

            y_sum = torch.zeros_like(
                y_vec
            )

            count = 0

            for target_i, j in enumerate(
                target_ind
            ):

                if i >= j:
                    continue

                end_pos = (
                    matrix.get_position(
                        global_mat
                    )[
                        ...,
                        j,
                        :,
                    ]
                )

                solved_q = (
                    qslerp(
                        quat,
                        qmul(
                            qbetween(
                                end_pos
                                - pos,
                                target_pos[
                                    ...,
                                    target_i,
                                    :,
                                ]
                                - pos,
                            ),
                            quat,
                        ),
                        (
                            i + 1
                        )
                        / J_N,
                    )
                )

                x_sum = (
                    x_sum
                    + qrot(
                        solved_q,
                        x_vec,
                    )
                )

                y_sum = (
                    y_sum
                    + qrot(
                        solved_q,
                        y_vec,
                    )
                )

                count += 1

            if count > 0:

                x_avg = (
                    matrix.normalize(
                        x_sum
                        / count
                    )
                )

                y_avg = (
                    matrix.normalize(
                        y_sum
                        / count
                    )
                )

                z_avg = torch.cross(
                    x_avg,
                    y_avg,
                    dim=-1,
                )

                solved_rot = (
                    torch.stack(
                        [
                            x_avg,
                            y_avg,
                            z_avg,
                        ],
                        dim=-1,
                    )
                )

                parent_rot = (
                    matrix.get_rotation(
                        global_mat
                    )[
                        ...,
                        i - 1,
                        :,
                        :,
                    ]
                )

                solved_local_rot = (
                    matrix.get_mat_BtoA(
                        parent_rot,
                        solved_rot,
                    )
                )

                new_lm = lm.clone()

                new_lm[
                    ...,
                    i,
                    :-1,
                    :-1,
                ] = solved_local_rot

                lm = new_lm

                global_mat = (
                    forward_kinematics_chain(
                        lm
                    )
                )

    return lm


def position_only_two_pairs(
    local_last,
    ll_pos,
    rl_pos,
    lh_pos,
    rh_pos,
):
    lm = local_last.clone()

    # ----------------------------------------------------------
    # LEFT + RIGHT LEGS
    # ----------------------------------------------------------

    leg_pair = position_only_pair(
        lm,
        ll_pos,
        rl_pos,
        CHAINS[0][0],
        CHAINS[1][0],
        CHAINS[0][2],
    )

    leg_rot = (
        matrix.get_rotation(
            leg_pair
        )
    )

    new_lm = lm.clone()

    new_lm[
        :,
        :,
        CHAINS[0][0][1:],
        :-1,
        :-1,
    ] = (
        leg_rot[
            0:1,
            :,
            1:,
        ]
    )

    new_lm[
        :,
        :,
        CHAINS[1][0][1:],
        :-1,
        :-1,
    ] = (
        leg_rot[
            1:2,
            :,
            1:,
        ]
    )

    lm = new_lm

    # ----------------------------------------------------------
    # LEFT + RIGHT WRISTS
    # ----------------------------------------------------------

    wrist_pair = position_only_pair(
        lm,
        lh_pos,
        rh_pos,
        CHAINS[2][0],
        CHAINS[3][0],
        CHAINS[2][2],
    )

    wrist_rot = (
        matrix.get_rotation(
            wrist_pair
        )
    )

    new_lm = lm.clone()

    new_lm[
        :,
        :,
        CHAINS[2][0][1:],
        :-1,
        :-1,
    ] = (
        wrist_rot[
            0:1,
            :,
            1:,
        ]
    )

    new_lm[
        :,
        :,
        CHAINS[3][0][1:],
        :-1,
        :-1,
    ] = (
        wrist_rot[
            1:2,
            :,
            1:,
        ]
    )

    lm = new_lm

    return (
        matrix_to_axis_angle(
            matrix.get_rotation(
                lm[
                    :,
                    :,
                    1:,
                ]
            )
        )
        .flatten(
            2
        )
    )


def make_fastik_predictor(
    gvhmr,
):
    pipeline = (
        gvhmr.pipeline
    )

    endecoder = (
        pipeline.endecoder
    )

    torch._dynamo.reset()

    compiled_ccd = torch.compile(
        position_only_two_pairs,
        backend="inductor",
        mode="default",
        fullgraph=False,
    )

    print(
        "PAIR-BATCHED FASTIK predictor: configured"
    )

    print(
        "PAIR-BATCHED FASTIK first temporal warmup "
        "will compile the CCD graph."
    )


    @torch.no_grad()
    def fast_predict(
        data,
        static_cam=True,
    ):
        if not static_cam:
            raise RuntimeError(
                "FASTIK live test requires "
                "static_cam=True"
            )


        # Exact DemoPL.predict batching contract.
        batch = {
            "length":
                data[
                    "length"
                ][
                    None
                ],

            "obs":
                normalize_kp2d(
                    data[
                        "kp2d"
                    ],
                    data[
                        "bbx_xys"
                    ],
                )[
                    None
                ],

            "bbx_xys":
                data[
                    "bbx_xys"
                ][
                    None
                ],

            "K_fullimg":
                data[
                    "K_fullimg"
                ][
                    None
                ],

            "cam_angvel":
                data[
                    "cam_angvel"
                ][
                    None
                ],

            "f_imgseq":
                data[
                    "f_imgseq"
                ][
                    None
                ],
        }


        batch = {
            key:
                value.cuda()
            for key, value
            in batch.items()
        }


        # Keep the entire learned GVHMR path unchanged.
        # Only skip stock postproc so we can substitute
        # the validated faster IK implementation.
        outputs = (
            pipeline.forward(
                batch,
                train=False,
                postproc=False,
                static_cam=True,
            )
        )


        # Same static-camera translational postprocess
        # used by stock pipeline.forward(postproc=True).
        outputs[
            "pred_smpl_params_global"
        ][
            "transl"
        ] = pp_static_joint_cam(
            outputs,
            endecoder,
        )


        static_conf = (
            outputs[
                "static_conf_logits"
            ]
            .sigmoid()
        )


        # Same full-history FK used by stock process_ik.
        post_w_j3d, local_mat, _ = (
            endecoder.fk_v2(
                **outputs[
                    "pred_smpl_params_global"
                ],
                get_intermediate=True,
            )
        )


        # Same full-history recursive contact-target rollout.
        post_target = (
            post_w_j3d.clone()
        )


        for i in range(
            1,
            post_w_j3d.size(
                1
            ),
        ):

            prev = (
                post_target[
                    :,
                    i - 1,
                    CONTACT_JOINTS,
                ]
            )

            this = (
                post_w_j3d[
                    :,
                    i,
                    CONTACT_JOINTS,
                ]
            )

            c_prev = (
                static_conf[
                    :,
                    i - 1,
                    :,
                    None,
                ]
            )


            post_target[
                :,
                i,
                CONTACT_JOINTS,
            ] = (
                prev
                * c_prev
                + this
                * (
                    1
                    - c_prev
                )
            )


        # Stock IK was shown experimentally to give the
        # identical newest-frame result when solved only
        # on this final frame after target rollout.
        local_last = (
            local_mat[
                :,
                -1:,
            ]
            .clone()
        )


        ll_pos = (
            post_target[
                :,
                -1:,
                [
                    7,
                    10,
                ],
            ]
        )

        rl_pos = (
            post_target[
                :,
                -1:,
                [
                    8,
                    11,
                ],
            ]
        )

        lh_pos = (
            post_target[
                :,
                -1:,
                [
                    20,
                ],
            ]
        )

        rh_pos = (
            post_target[
                :,
                -1:,
                [
                    21,
                ],
            ]
        )


        body_pose_last = (
            compiled_ccd(
                local_last,
                ll_pos,
                rl_pos,
                lh_pos,
                rh_pos,
            )
        )


        # Stock process_ik writes the corrected body pose
        # to BOTH global and in-camera result dictionaries.
        #
        # The live consumer only uses the newest frame,
        # but preserve the normal sequence-shaped output.
        for group in (
            "pred_smpl_params_global",
            "pred_smpl_params_incam",
        ):

            body_pose = (
                outputs[
                    group
                ][
                    "body_pose"
                ]
                .clone()
            )

            body_pose[
                :,
                -1:,
            ] = body_pose_last

            outputs[
                group
            ][
                "body_pose"
            ] = body_pose


        # Exact DemoPL.predict outward contract.
        return {
            "smpl_params_global": {
                key:
                    value[
                        0
                    ]
                for key, value
                in outputs[
                    "pred_smpl_params_global"
                ].items()
            },

            "smpl_params_incam": {
                key:
                    value[
                        0
                    ]
                for key, value
                in outputs[
                    "pred_smpl_params_incam"
                ].items()
            },

            "K_fullimg":
                data[
                    "K_fullimg"
                ],

            "net_outputs":
                outputs,
        }


    return fast_predict


def percentile(
    values,
    q,
):
    if not values:
        return float("nan")

    return float(
        np.percentile(
            np.asarray(
                values,
                dtype=np.float64,
            ),
            q,
        )
    )


def print_stats(
    name,
    values,
    unit,
):
    if not values:
        print(
            f"{name}: no samples"
        )
        return

    arr = np.asarray(
        values,
        dtype=np.float64,
    )

    print(
        f"{name}: "
        f"n={len(arr)} "
        f"mean={arr.mean():.3f}{unit} "
        f"median={np.median(arr):.3f}{unit} "
        f"p95={np.percentile(arr, 95):.3f}{unit} "
        f"max={arr.max():.3f}{unit}"
    )


class LatestFrameCamera:
    """
    Background FFmpeg/V4L2 latest-frame reader.

    FFmpeg acquires the launcher-resolved V4L2 profile,
    decodes to BGR24, and writes raw frames to stdout.

    The inference loop still consumes only the newest frame.
    There is deliberately no FIFO of old camera frames.
    """

    def __init__(
        self,
        device,
    ):
        self.device = device

        self.frame_bytes = (
            WIDTH
            * HEIGHT
            * 3
        )

        self.lock = threading.Lock()

        self.running = True

        self.sequence = 0
        self.timestamp_s = None
        self.frame = None

        # Camera thread continues acquiring at CAPTURE_FPS.
        # The consumer receives only the newest frame at the
        # requested frontend cadence.
        self.delivery_period_s = (
            1.0
            / float(
                FRONTEND_TARGET_FPS
            )
        )

        self.last_delivery_monotonic = None

        self.reader_error = None

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",

            "-f",
            "v4l2",

            "-input_format",
            CAMERA_INPUT_FORMAT,

            "-framerate",
            str(
                CAPTURE_FPS
            ),

            "-video_size",
            f"{WIDTH}x{HEIGHT}",

            "-i",
            device,

            "-an",

            "-pix_fmt",
            "bgr24",

            "-f",
            "rawvideo",

            "pipe:1",
        ]

        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=(
                self.frame_bytes
                * 2
            ),
        )

        if self.proc.stdout is None:
            self.stop()

            raise RuntimeError(
                "FFmpeg camera stdout "
                "is unavailable."
            )

        self.thread = threading.Thread(
            target=self._reader,
            daemon=True,
        )

        self.thread.start()

        deadline = (
            time.monotonic()
            + 5.0
        )

        ready = False

        while (
            time.monotonic()
            < deadline
        ):
            with self.lock:
                ready = (
                    self.frame
                    is not None
                )

                reader_error = (
                    self.reader_error
                )

            if ready:
                break

            if reader_error is not None:
                self.stop()

                raise RuntimeError(
                    "FFmpeg camera reader failed: "
                    f"{reader_error}"
                )

            if (
                self.proc.poll()
                is not None
            ):
                self.stop()

                raise RuntimeError(
                    "FFmpeg camera process "
                    "exited before first frame."
                )

            time.sleep(
                0.01
            )

        if not ready:
            self.stop()

            raise RuntimeError(
                "FFmpeg camera opened but no "
                "BGR frame arrived within "
                "5 seconds."
            )

        print(
            "camera negotiated: "
            f"{WIDTH}x{HEIGHT} "
            f"{float(CAPTURE_FPS):.3f} fps "
            f"'{CAMERA_FOURCC}'/{CAMERA_INPUT_FORMAT} "
            "via FFmpeg -> BGR24"
        )


    def _read_exact_frame(
        self,
    ):
        if self.proc.stdout is None:
            return None

        chunks = []

        remaining = (
            self.frame_bytes
        )

        while (
            self.running
            and remaining > 0
        ):
            chunk = (
                self.proc.stdout.read(
                    remaining
                )
            )

            if not chunk:
                return None

            chunks.append(
                chunk
            )

            remaining -= len(
                chunk
            )

        if remaining != 0:
            return None

        return b"".join(
            chunks
        )


    def _reader(
        self,
    ):
        try:
            while self.running:

                raw = (
                    self._read_exact_frame()
                )

                if raw is None:
                    break

                frame = (
                    np.frombuffer(
                        raw,
                        dtype=np.uint8,
                    )
                    .reshape(
                        HEIGHT,
                        WIDTH,
                        3,
                    )
                )

                timestamp_s = (
                    time.monotonic()
                )

                with self.lock:
                    self.sequence += 1

                    self.timestamp_s = (
                        timestamp_s
                    )

                    self.frame = (
                        frame
                    )

        except Exception as exc:
            with self.lock:
                self.reader_error = (
                    repr(
                        exc
                    )
                )


    def latest(
        self,
        after_sequence,
    ):
        now = (
            time.monotonic()
        )

        with self.lock:
            if (
                self.frame is None
                or self.sequence
                <= after_sequence
            ):
                return None

            if (
                self.last_delivery_monotonic
                is not None
                and
                (
                    now
                    - self.last_delivery_monotonic
                )
                < self.delivery_period_s
            ):
                return None

            # Important: do not queue an older frame.
            # At each 15-Hz delivery instant we return whatever
            # the 30-Hz FFmpeg reader currently considers newest.
            self.last_delivery_monotonic = (
                now
            )

            return (
                int(
                    self.sequence
                ),
                float(
                    self.timestamp_s
                ),
                self.frame.copy(),
            )


    def stop(
        self,
    ):
        self.running = False

        proc = getattr(
            self,
            "proc",
            None,
        )

        if (
            proc is not None
            and proc.poll()
            is None
        ):
            proc.terminate()

        thread = getattr(
            self,
            "thread",
            None,
        )

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(
                timeout=2.0
            )

        if (
            proc is not None
            and proc.poll()
            is None
        ):
            proc.kill()

        if proc is not None:
            try:
                proc.wait(
                    timeout=2.0
                )
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            if proc.stdout is not None:
                proc.stdout.close()



class ViTPoseTRT8Runner:
    def __init__(
        self,
        state_path,
    ):
        print(
            "Loading ViTPose TRT8..."
        )

        self.module = TRTModule()

        state = torch.load(
            state_path,
        )

        self.module.load_state_dict(
            state
        )

        self.module.eval()

        print(
            "ViTPose TRT8: PASS"
        )

    @torch.inference_mode()
    def __call__(
        self,
        **kwargs,
    ):
        x = kwargs["imgs"]

        if not torch.is_tensor(
            x
        ):
            x = torch.from_numpy(
                np.asarray(
                    x,
                    dtype=np.float32,
                )
            )

        x = (
            x.contiguous()
            .to(
                device="cuda",
                dtype=torch.float32,
            )
        )

        y = self.module(
            x
        )

        if isinstance(
            y,
            (tuple, list),
        ):
            y = y[0]

        return {
            "heatmaps":
                y.detach()
                .cpu()
                .numpy()
        }


class HMR2TRT10Runner:
    def __init__(
        self,
        onnx_path,
        cache_path,
    ):
        print(
            "Loading cached HMR2 TRT10..."
        )

        trt_options = {
            "device_id":
                0,

            "trt_fp16_enable":
                True,

            "trt_engine_cache_enable":
                True,

            "trt_engine_cache_path":
                str(
                    cache_path
                ),

            "trt_timing_cache_enable":
                True,

            "trt_timing_cache_path":
                str(
                    cache_path
                ),

            "trt_max_workspace_size":
                512
                * 1024
                * 1024,

            "trt_min_subgraph_size":
                1,

            "trt_profile_min_shapes":
                "imgs:1x3x256x256",

            "trt_profile_opt_shapes":
                "imgs:1x3x256x256",

            "trt_profile_max_shapes":
                "imgs:1x3x256x256",
        }

        t0 = time.monotonic()

        self.session = (
            ort.InferenceSession(
                str(
                    onnx_path
                ),
                providers=[
                    (
                        "TensorrtExecutionProvider",
                        trt_options,
                    ),
                    (
                        "CUDAExecutionProvider",
                        {
                            "device_id": 0
                        },
                    ),
                    "CPUExecutionProvider",
                ],
            )
        )

        self.output_names = [
            output.name
            for output
            in self.session.get_outputs()
        ]

        print(
            "HMR2 providers:",
            self.session.get_providers(),
        )

        print(
            "HMR2 session load: "
            f"{time.monotonic() - t0:.3f}s"
        )

        if (
            self.session
            .get_providers()[0]
            !=
            "TensorrtExecutionProvider"
        ):
            raise RuntimeError(
                "HMR2 TensorRT EP "
                "is not active."
            )

        print(
            "HMR2 TRT10: PASS"
        )

    def __call__(
        self,
        **kwargs,
    ):
        x = kwargs["imgs"]

        if torch.is_tensor(
            x
        ):
            x = (
                x.detach()
                .cpu()
                .numpy()
            )

        x = np.asarray(
            x,
            dtype=np.float32,
        )

        output = self.session.run(
            self.output_names,
            {
                "imgs": x
            },
        )[0]

        return {
            "f_imgseq":
                output
        }


def load_gvhmr(
    device="cuda",
):
    print(
        "Loading temporal GVHMR..."
    )

    with initialize_config_module(
        version_base="1.3",
        config_module="hmr4d.configs",
    ):
        register_store_gvhmr()

        cfg = compose(
            config_name="demo",
            overrides=[
                "video_name=live_accel_causal30",
                "static_cam=true",
                "verbose=false",
                "use_dpvo=false",
            ],
        )

    model = hydra.utils.instantiate(
        cfg.model,
        _recursive_=False,
    )

    model.load_pretrained_model(
        cfg.ckpt_path
    )

    model = (
        model.eval()
        .to(
            device
        )
    )

    print(
        "GVHMR checkpoint:",
        cfg.ckpt_path,
    )

    print(
        "GVHMR model: PASS"
    )

    return model


def last_tensor_dict(
    data,
):
    result = {}

    for key, value in data.items():
        if torch.is_tensor(
            value
        ):
            cpu = (
                value.detach()
                .cpu()
            )

            if (
                cpu.ndim > 0
                and cpu.shape[0] > 0
            ):
                cpu = (
                    cpu[-1]
                    .clone()
                )
            else:
                cpu = cpu.clone()

            result[key] = cpu

    return result


def make_temporal_data(
    snapshot,
    K_fullimg,
):
    F = len(
        snapshot
    )

    bbx = torch.stack(
        [
            item["bbx_xys"]
            for item
            in snapshot
        ],
        dim=0,
    )

    kp2d = torch.stack(
        [
            item["kp2d"]
            for item
            in snapshot
        ],
        dim=0,
    )

    f_imgseq = torch.stack(
        [
            item["f_imgseq"]
            for item
            in snapshot
        ],
        dim=0,
    )

    K_seq = (
        K_fullimg
        .unsqueeze(0)
        .repeat(
            F,
            1,
            1,
        )
    )

    R_eye = (
        torch.eye(
            3,
            dtype=torch.float32,
        )
        .unsqueeze(0)
        .repeat(
            F,
            1,
            1,
        )
    )

    cam_angvel = (
        compute_cam_angvel(
            R_eye
        )
        .cpu()
    )

    return {
        "length":
            torch.tensor(
                F,
                dtype=torch.long,
            ),

        "bbx_xys":
            bbx,

        "kp2d":
            kp2d,

        "K_fullimg":
            K_seq,

        "cam_angvel":
            cam_angvel,

        "f_imgseq":
            f_imgseq,
    }


def draw_frontend_overlay(
    frame,
    bbx_xys,
    kp2d,
    phase,
    track_id,
    frontend_ms,
):
    out = frame.copy()

    bb = (
        bbx_xys
        .detach()
        .cpu()
        .numpy()
    )

    cx, cy, size = [
        float(v)
        for v
        in bb
    ]

    x1 = int(
        round(
            cx - size / 2.0
        )
    )

    y1 = int(
        round(
            cy - size / 2.0
        )
    )

    x2 = int(
        round(
            cx + size / 2.0
        )
    )

    y2 = int(
        round(
            cy + size / 2.0
        )
    )

    cv2.rectangle(
        out,
        (x1, y1),
        (x2, y2),
        (255, 255, 255),
        1,
    )

    kp = (
        kp2d
        .detach()
        .cpu()
        .numpy()
    )

    for a, b in COCO_EDGES:
        if (
            kp[a, 2] > 0.35
            and kp[b, 2] > 0.35
        ):
            cv2.line(
                out,
                (
                    int(
                        kp[a, 0]
                    ),
                    int(
                        kp[a, 1]
                    ),
                ),
                (
                    int(
                        kp[b, 0]
                    ),
                    int(
                        kp[b, 1]
                    ),
                ),
                (255, 255, 255),
                2,
            )

    for x, y, conf in kp:
        if conf > 0.35:
            cv2.circle(
                out,
                (
                    int(x),
                    int(y),
                ),
                4,
                (255, 255, 255),
                -1,
            )

    cv2.putText(
        out,
        phase,
        (24, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.85,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    cv2.putText(
        out,
        (
            f"track={track_id} "
            f"frontend={frontend_ms:.1f}ms"
        ),
        (24, 72),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    return out


def main():
    torch.set_grad_enabled(
        False
    )

    print(
        "============================================================"
    )

    print(
        "LIVE ACCELERATED GVHMR — CAUSAL 30"
    )

    print(
        "============================================================"
    )

    print(
        "history=30, future=0"
    )

    print(
        "latest-only camera ingestion"
    )

    print(
        "one temporal inference in flight"
    )

    print(
        "SONIC OFF / MuJoCo OFF"
    )

    print()

    vitpose = (
        ViTPoseTRT8Runner(
            VIT_STATE
        )
    )

    hmr2 = (
        HMR2TRT10Runner(
            HMR_ONNX,
            HMR_CACHE,
        )
    )

    print(
        "Loading YOLOX CUDA..."
    )

    yolox = (
        YOLOXDetector(
            device="cuda"
        )
    )

    if (
        "CUDAExecutionProvider"
        not in
        yolox.sess.get_providers()
    ):
        raise RuntimeError(
            "YOLOX CUDA provider "
            "is not active."
        )

    tracker = (
        ByteTracker(
            max_lost=30
        )
    )

    print(
        "YOLOX + ByteTrack: PASS"
    )

    gvhmr = load_gvhmr()

    fast_predict = (
        make_fastik_predictor(
            gvhmr
        )
    )

    torch.cuda.synchronize()

    print()
    print(
        "GPU components loaded: PASS"
    )

    print()
    print(
        "CAMERA OPEN — STAND NEUTRAL"
    )

    print(
        "Full body and feet visible."
    )

    camera = (
        LatestFrameCamera(
            CAMERA_DEVICE
        )
    )

    K_fullimg = (
        estimate_K(
            WIDTH,
            HEIGHT,
        )
        .float()
        .cpu()
    )

    print(
        "GVHMR K_fullimg "
        "(official estimate_K):"
    )

    print(
        K_fullimg.numpy()
    )

    track_state = {
        "bbox": None,
        "track_id": -1,
        "sample_index": 0,
        "yolo_calls": 0,
        "kp_bbox_updates": 0,
    }

    # ----------------------------------------------------
    # V2 STARTUP FULL-BODY FRAMING GATE
    #
    # Uses the existing real ViTPose-17 2D observations.
    # It is intentionally latched off once one fresh,
    # continuously well-framed startup history is built.
    #
    # fixed_v1 never enables this flag.
    # ----------------------------------------------------

    framing_gate_enabled = (
        os.environ.get(
            "LIVE_GVHMR_FRAMING_GATE",
            "0",
        )
        .strip()
        .lower()
        in (
            "1",
            "true",
            "yes",
            "on",
        )
    )

    framing_gate = None

    framing_state = {
        "startup_complete":
            not framing_gate_enabled,

        "ready_announced":
            False,

        "last_reason":
            None,

        "last_print_s":
            -1.0e9,
    }

    if framing_gate_enabled:
        from framing_gate import (
            FullBodyFramingGate,
        )

        framing_gate = (
            FullBodyFramingGate(
                image_width=WIDTH,
                image_height=HEIGHT,
                confidence_threshold=float(
                    os.environ.get(
                        "LIVE_GVHMR_FRAMING_CONFIDENCE",
                        "0.5",
                    )
                ),
                consecutive_good_frames=int(
                    os.environ.get(
                        "LIVE_GVHMR_FRAMING_GOOD_FRAMES",
                        "8",
                    )
                ),
            )
        )

        print()
        print(
            "FULL-BODY FRAMING CHECK: ENABLED"
        )

        print(
            "Using existing ViTPose-17 2D "
            "visibility evidence."
        )

        print(
            "Calibration will not begin until "
            "framing is stable."
        )

    window = deque(
        maxlen=HISTORY
    )

    frontend_log = deque(maxlen=300)
    temporal_results = deque(maxlen=300)

    last_camera_sequence = -1

    writer = None

    temporal_condition = (
        threading.Condition()
    )

    temporal_pending = None
    temporal_stop = False
    temporal_thread = None
    temporal_generation = 0

    temporal_max_pending_source_age_ms = (
        100.0
    )

    # Disposable GPU-contention experiment:
    # run all PyTorch temporal work on a dedicated
    # high-priority CUDA stream.
    temporal_cuda_stream = torch.cuda.Stream(
        priority=-2
    )

    print(
        "Temporal CUDA stream priority:",
        temporal_cuda_stream.priority,
    )

    temporal_worker_state = {
        "busy": False,
        "error": None,
        "jobs_started": 0,
        "jobs_completed": 0,
        "superseded_pending": 0,
        "frontend_samples_while_busy": 0,
        "latest_available_sequence": -1,
        "total_infer_s": 0.0,
        "stale_pending_dropped": 0,
        "freshness_wait_count": 0,
        "total_freshness_wait_s": 0.0,
    }

    video_path = Path(
        str(
            OUT_PREFIX
        )
        + "_2d.mp4"
    )

    pt_path = Path(
        str(
            OUT_PREFIX
        )
        + ".pt"
    )

    def process_frame(
        sequence,
        capture_ts,
        frame_bgr,
    ):
        t0 = time.monotonic()

        sample_index = (
            track_state[
                "sample_index"
            ]
        )

        need_detection = (
            track_state["bbox"]
            is None
            or
            sample_index
            % YOLO_PERIOD
            == 0
        )

        if need_detection:
            boxes, scores = (
                yolox.detect(
                    frame_bgr
                )
            )

            boxes = np.asarray(
                boxes,
                dtype=np.float32,
            ).reshape(
                -1,
                4,
            )

            scores = np.asarray(
                scores,
                dtype=np.float32,
            ).reshape(
                -1,
            )

            track_state[
                "yolo_calls"
            ] += 1

        else:
            boxes = np.empty(
                (0, 4),
                dtype=np.float32,
            )

            scores = np.empty(
                (0,),
                dtype=np.float32,
            )

        # Match GENMO: ByteTrack is advanced on every
        # logical sample and its returned track is consumed.
        tracked = tracker.update(
            boxes,
            scores,
        )

        if tracked:
            best = max(
                tracked,
                key=lambda item:
                    float(item[2])
                    * max(
                        1.0,
                        float(
                            item[0][2]
                            - item[0][0]
                        ),
                    )
                    * max(
                        1.0,
                        float(
                            item[0][3]
                            - item[0][1]
                        ),
                    ),
            )

            track_state[
                "bbox"
            ] = np.asarray(
                best[0],
                dtype=np.float32,
            ).copy()

            track_state[
                "track_id"
            ] = int(
                best[1]
            )

        track_state[
            "sample_index"
        ] += 1

        if (
            track_state["bbox"]
            is None
        ):
            return None

        bbox = (
            track_state[
                "bbox"
            ]
            .copy()
        )

        bbox[
            [0, 2]
        ] = np.clip(
            bbox[
                [0, 2]
            ],
            0,
            WIDTH - 1,
        )

        bbox[
            [1, 3]
        ] = np.clip(
            bbox[
                [1, 3]
            ],
            0,
            HEIGHT - 1,
        )

        bbx_xys = (
            get_bbx_xys_from_xyxy(
                torch.from_numpy(
                    bbox[None]
                ).float(),
                base_enlarge=1.2,
            )[0]
            .float()
            .cpu()
        )

        kp2d = (
            run_vitpose_single_frame(
                vitpose,
                "trt",
                frame_bgr,
                bbx_xys,
            )
        )

        frame_rgb = (
            cv2.cvtColor(
                frame_bgr,
                cv2.COLOR_BGR2RGB,
            )
        )

        f_imgseq = (
            run_hmr2_single_frame(
                hmr2,
                "onnx",
                frame_rgb,
                bbx_xys,
            )
        )

        kp2d = (
            torch.as_tensor(
                kp2d
            )
            .detach()
            .cpu()
            .float()
            .reshape(
                17,
                3,
            )
        )

        f_imgseq = (
            torch.as_tensor(
                f_imgseq
            )
            .detach()
            .cpu()
            .float()
            .reshape(
                1024,
            )
        )

        # -------------------------------------------------
        # V2 STARTUP FRAMING OBSERVATION
        #
        # Important:
        # This checks REAL 2D ViTPose observations, not
        # inferred GVHMR/SMPL joints.
        # -------------------------------------------------

        if (
            framing_gate is not None
            and not framing_state[
                "startup_complete"
            ]
        ):
            framing_result = (
                framing_gate.observe(
                    kp2d.numpy()
                )
            )

            framing_now = (
                time.monotonic()
            )

            if not framing_result.ready:
                # No partly-framed samples may survive into
                # the future 30-frame startup history.
                window.clear()

                framing_state[
                    "ready_announced"
                ] = False

                reason_changed = (
                    framing_result.reason
                    != framing_state[
                        "last_reason"
                    ]
                )

                print_due = (
                    framing_now
                    - framing_state[
                        "last_print_s"
                    ]
                    >= 0.75
                )

                if (
                    reason_changed
                    or print_due
                ):
                    print()
                    print(
                        "FULL-BODY FRAMING: NOT READY"
                    )

                    print(
                        framing_result.reason
                    )

                    print(
                        "Stable observations: "
                        f"{framing_result.good_streak}/"
                        f"{framing_result.required_streak}"
                    )

                    print(
                        "Calibration has NOT started."
                    )

                    framing_state[
                        "last_reason"
                    ] = (
                        framing_result.reason
                    )

                    framing_state[
                        "last_print_s"
                    ] = framing_now

                return None

            if not framing_state[
                "ready_announced"
            ]:
                print()
                print(
                    "FULL-BODY FRAMING: STABLE"
                )

                print(
                    "Building a fresh "
                    f"{HISTORY}-frame GVHMR history..."
                )

                framing_state[
                    "ready_announced"
                ] = True

                framing_state[
                    "last_reason"
                ] = None

        # GENMO keypoint-derived bbox update.
        #
        # Keep the current frame's bbx_xys untouched so
        # kp2d, f_imgseq and bbx_xys remain one paired
        # logical sample. This updates tracking state only
        # for the NEXT frame.
        visible = (
            kp2d[:, 2]
            > 0.5
        )

        if visible.any():
            vis_kp = (
                kp2d[
                    visible,
                    :2,
                ]
            )

            xmin = (
                vis_kp[:, 0]
                .min()
                .item()
            )

            ymin = (
                vis_kp[:, 1]
                .min()
                .item()
            )

            xmax = (
                vis_kp[:, 0]
                .max()
                .item()
            )

            ymax = (
                vis_kp[:, 1]
                .max()
                .item()
            )

            cx = (
                xmin + xmax
            ) / 2.0

            cy = (
                ymin + ymax
            ) / 2.0

            w = (
                xmax - xmin
            ) * 1.1

            h = (
                ymax - ymin
            ) * 1.1

            # Avoid a degenerate box if only a tiny number
            # of joints happen to exceed the threshold.
            if (
                w > 2.0
                and
                h > 2.0
            ):
                track_state[
                    "bbox"
                ] = np.asarray(
                    [
                        cx - w / 2.0,
                        cy - h / 2.0,
                        cx + w / 2.0,
                        cy + h / 2.0,
                    ],
                    dtype=np.float32,
                )

                track_state[
                    "kp_bbox_updates"
                ] += 1

        end_ts = (
            time.monotonic()
        )

        return {
            "capture_sequence":
                int(
                    sequence
                ),

            "capture_ts":
                float(
                    capture_ts
                ),

            "track_id":
                int(
                    track_state[
                        "track_id"
                    ]
                ),

            "bbx_xys":
                bbx_xys,

            "kp2d":
                kp2d,

            "f_imgseq":
                f_imgseq,

            "frontend_ms":
                (
                    end_ts - t0
                )
                * 1000.0,

            "frontend_age_ms":
                (
                    end_ts
                    - capture_ts
                )
                * 1000.0,
        }

    def run_temporal(
        snapshot,
        jpeg_bytes,
        phase,
        elapsed_s,
    ):
        data = (
            make_temporal_data(
                snapshot,
                K_fullimg,
            )
        )

        newest_capture_ts = (
            snapshot[-1][
                "capture_ts"
            ]
        )

        oldest_capture_ts = (
            snapshot[0][
                "capture_ts"
            ]
        )

        newest_sequence = (
            snapshot[-1][
                "capture_sequence"
            ]
        )

        torch.cuda.synchronize()

        t0 = time.monotonic()

        with torch.cuda.stream(
            temporal_cuda_stream
        ):
            prediction = (
                fast_predict(
                    data,
                    static_cam=True,
                )
            )

        temporal_cuda_stream.synchronize()

        t1 = time.monotonic()

        return {
            "phase":
                str(
                    phase
                ),

            "test_elapsed_s":
                float(
                    elapsed_s
                ),

            "capture_sequence":
                int(
                    newest_sequence
                ),

            "capture_ts":
                float(
                    newest_capture_ts
                ),

            "window_start_capture_ts":
                float(
                    oldest_capture_ts
                ),

            "window_span_s":
                float(
                    newest_capture_ts
                    - oldest_capture_ts
                ),

            "temporal_start_ts":
                float(
                    t0
                ),

            "temporal_end_ts":
                float(
                    t1
                ),

            "infer_ms":
                float(
                    (
                        t1 - t0
                    )
                    * 1000.0
                ),

            "source_age_ms":
                float(
                    (
                        t1
                        - newest_capture_ts
                    )
                    * 1000.0
                ),

            "track_id":
                int(
                    snapshot[-1][
                        "track_id"
                    ]
                ),

            "frame_jpeg":
                jpeg_bytes,

            "smpl_params_incam":
                last_tensor_dict(
                    prediction[
                        "smpl_params_incam"
                    ]
                ),

            "smpl_params_global":
                last_tensor_dict(
                    prediction[
                        "smpl_params_global"
                    ]
                ),
        }


    def temporal_worker_loop():
        nonlocal temporal_pending
        nonlocal temporal_stop

        previous_temporal_end_ts = None

        freshness_wait_start_ts = None

        while True:
            with temporal_condition:
                temporal_condition.wait_for(
                    lambda:
                        temporal_stop
                        or
                        temporal_pending
                        is not None
                )

                if temporal_stop:
                    return

                pending_capture_ts = float(
                    temporal_pending[
                        "snapshot"
                    ][-1][
                        "capture_ts"
                    ]
                )

                pending_source_age_ms = (
                    time.monotonic()
                    - pending_capture_ts
                ) * 1000.0

                if (
                    pending_source_age_ms
                    >
                    temporal_max_pending_source_age_ms
                ):
                    temporal_worker_state[
                        "stale_pending_dropped"
                    ] += 1

                    temporal_pending = None

                    if (
                        freshness_wait_start_ts
                        is None
                    ):
                        freshness_wait_start_ts = (
                            time.monotonic()
                        )

                    continue

                job = temporal_pending
                temporal_pending = None

                if (
                    freshness_wait_start_ts
                    is None
                ):
                    freshness_wait_ms = 0.0

                else:
                    freshness_wait_ms = (
                        time.monotonic()
                        - freshness_wait_start_ts
                    ) * 1000.0

                    temporal_worker_state[
                        "freshness_wait_count"
                    ] += 1

                    temporal_worker_state[
                        "total_freshness_wait_s"
                    ] += (
                        freshness_wait_ms
                        / 1000.0
                    )

                    freshness_wait_start_ts = None

                temporal_worker_state[
                    "busy"
                ] = True

                temporal_worker_state[
                    "jobs_started"
                ] += 1

            # Preserve the old diagnostic frame_jpeg
            # behavior, but do the JPEG encode only for
            # windows actually consumed by the temporal
            # worker. Superseded mailbox windows never pay
            # this cost.
            ok, encoded = (
                cv2.imencode(
                    ".jpg",
                    job[
                        "frame_bgr"
                    ],
                    [
                        int(
                            cv2.IMWRITE_JPEG_QUALITY
                        ),
                        92,
                    ],
                )
            )

            jpeg_bytes = (
                encoded.tobytes()
                if ok
                else b""
            )

            try:
                result = run_temporal(
                    job[
                        "snapshot"
                    ],
                    jpeg_bytes,
                    job[
                        "phase"
                    ],
                    job[
                        "elapsed_s"
                    ],
                )

            except Exception as exc:
                with temporal_condition:
                    temporal_worker_state[
                        "busy"
                    ] = False

                    temporal_worker_state[
                        "error"
                    ] = exc

                    temporal_stop = True

                    temporal_condition.notify_all()

                return

            if (
                previous_temporal_end_ts
                is None
            ):
                restart_gap_ms = float(
                    "nan"
                )

            else:
                restart_gap_ms = (
                    result[
                        "temporal_start_ts"
                    ]
                    -
                    previous_temporal_end_ts
                ) * 1000.0

            previous_temporal_end_ts = (
                result[
                    "temporal_end_ts"
                ]
            )

            result[
                "mailbox_generation"
            ] = int(
                job[
                    "generation"
                ]
            )

            result[
                "pending_source_age_at_take_ms"
            ] = float(
                pending_source_age_ms
            )

            result[
                "freshness_wait_ms"
            ] = float(
                freshness_wait_ms
            )

            result[
                "temporal_restart_gap_ms"
            ] = float(
                restart_gap_ms
            )

            with temporal_condition:
                temporal_worker_state[
                    "busy"
                ] = False

                temporal_worker_state[
                    "jobs_completed"
                ] += 1

                temporal_worker_state[
                    "total_infer_s"
                ] += (
                    result[
                        "infer_ms"
                    ]
                    / 1000.0
                )

                result[
                    "newest_capture_sequence_available_at_completion"
                ] = int(
                    temporal_worker_state[
                        "latest_available_sequence"
                    ]
                )

                result[
                    "superseded_pending_total"
                ] = int(
                    temporal_worker_state[
                        "superseded_pending"
                    ]
                )

                result[
                    "frontend_samples_while_temporal_busy_total"
                ] = int(
                    temporal_worker_state[
                        "frontend_samples_while_busy"
                    ]
                )

                temporal_results.append(
                    result
                )

                # Match the old shutdown semantics:
                # finish the currently-running inference,
                # but do not start an extra pending window
                # after the timed test has ended.
                if temporal_stop:
                    return

    try:
        print()
        print(
            "Filling paired 30-sample "
            "causal window..."
        )

        prefill_timeout_s = (
            float(
                os.environ.get(
                    "LIVE_GVHMR_FRAMING_TIMEOUT_S",
                    "120.0",
                )
            )
            if framing_gate_enabled
            else 20.0
        )

        prefill_deadline = (
            time.monotonic()
            + prefill_timeout_s
        )

        while (
            len(window)
            < HISTORY
            and
            time.monotonic()
            < prefill_deadline
        ):
            newest = camera.latest(
                last_camera_sequence
            )

            if newest is None:
                time.sleep(
                    0.001
                )
                continue

            (
                sequence,
                capture_ts,
                frame_bgr,
            ) = newest

            last_camera_sequence = (
                sequence
            )

            packet = process_frame(
                sequence,
                capture_ts,
                frame_bgr,
            )

            if packet is None:
                continue

            window.append(
                packet
            )

            if (
                len(window) % 5
                == 0
                or len(window)
                == HISTORY
            ):
                span = (
                    window[-1][
                        "capture_ts"
                    ]
                    -
                    window[0][
                        "capture_ts"
                    ]
                )

                print(
                    "prefill "
                    f"{len(window):2d}/"
                    f"{HISTORY} "
                    f"span={span:.3f}s"
                )

        if (
            len(window)
            < HISTORY
        ):
            raise RuntimeError(
                "Could not fill a valid "
                "30-sample human window."
            )

        if (
            framing_gate is not None
            and not framing_state[
                "startup_complete"
            ]
        ):
            framing_state[
                "startup_complete"
            ] = True

            print()
            print(
                "========================================"
            )

            print(
                "FULL-BODY FRAMING: PASS"
            )

            print(
                f"Fresh GVHMR history: "
                f"{len(window)}/{HISTORY}"
            )

            print(
                "Startup framing gate is now latched."
            )

            print(
                "========================================"
            )

        print()
        print(
            "Warming temporal GVHMR "
            "on the real neutral window..."
        )

        warm = run_temporal(
            list(
                window
            ),
            b"",
            "WARMUP",
            -1.0,
        )

        print(
            "temporal warmup: "
            f"{warm['infer_ms']:.1f} ms"
        )

        print()
        print(
            "Keep standing NEUTRAL."
        )

        for count in (
            3,
            2,
            1,
        ):
            print(
                f"START IN {count}..."
            )

            countdown_end = (
                time.monotonic()
                + 1.0
            )

            while (
                time.monotonic()
                < countdown_end
            ):
                newest = camera.latest(
                    last_camera_sequence
                )

                if newest is None:
                    time.sleep(
                        0.001
                    )
                    continue

                (
                    sequence,
                    capture_ts,
                    frame_bgr,
                ) = newest

                last_camera_sequence = (
                    sequence
                )

                packet = process_frame(
                    sequence,
                    capture_ts,
                    frame_bgr,
                )

                if packet is not None:
                    window.append(
                        packet
                    )

        print()
        print(
            "========================================"
        )

        print(
            "START — NEUTRAL, ARMS DOWN"
        )

        print(
            "========================================"
        )

        writer = _NullVideoWriter(
            str(
                video_path
            ),
            cv2.VideoWriter_fourcc(
                *"mp4v"
            ),
            DEBUG_VIDEO_FPS,
            (
                WIDTH,
                HEIGHT,
            ),
        )

        if not writer.isOpened():
            raise RuntimeError(
                "Could not open debug "
                "video writer."
            )

        temporal_thread = (
            threading.Thread(
                target=temporal_worker_loop,
                name="gvhmr-temporal-worker",
                daemon=True,
            )
        )

        temporal_thread.start()

        test_start = (
            time.monotonic()
        )

        last_phase = None
        next_video_t = 0.0

        while True:
            worker_error = (
                temporal_worker_state[
                    "error"
                ]
            )

            if worker_error is not None:
                raise RuntimeError(
                    "Temporal worker failed."
                ) from worker_error

            now = time.monotonic()

            elapsed_s = (
                now - test_start
            )

            if (
                elapsed_s
                >= TEST_DURATION_S
            ):
                break

            newest = camera.latest(
                last_camera_sequence
            )

            if newest is None:
                time.sleep(
                    0.001
                )
                continue

            (
                sequence,
                capture_ts,
                frame_bgr,
            ) = newest

            last_camera_sequence = (
                sequence
            )

            packet = process_frame(
                sequence,
                capture_ts,
                frame_bgr,
            )

            if packet is None:
                continue

            window.append(
                packet
            )

            frontend_log.append(
                {
                    "capture_sequence":
                        packet[
                            "capture_sequence"
                        ],

                    "capture_ts":
                        packet[
                            "capture_ts"
                        ],

                    "track_id":
                        packet[
                            "track_id"
                        ],

                    "frontend_ms":
                        packet[
                            "frontend_ms"
                        ],

                    "frontend_age_ms":
                        packet[
                            "frontend_age_ms"
                        ],
                }
            )

            phase = "LIVE TRACKING"

            if phase != last_phase:
                print()
                print(
                    "========================================"
                )

                print(
                    "ACTION NOW:",
                    phase,
                )

                print(
                    "========================================"
                )

                last_phase = phase

            vis = draw_frontend_overlay(
                frame_bgr,
                packet[
                    "bbx_xys"
                ],
                packet[
                    "kp2d"
                ],
                phase,
                packet[
                    "track_id"
                ],
                packet[
                    "frontend_ms"
                ],
            )

            while (
                elapsed_s
                >= next_video_t
            ):
                writer.write(
                    vis
                )

                next_video_t += (
                    1.0
                    / DEBUG_VIDEO_FPS
                )

            if (
                len(window)
                == HISTORY
            ):
                with temporal_condition:
                    temporal_generation += 1

                    temporal_worker_state[
                        "latest_available_sequence"
                    ] = int(
                        packet[
                            "capture_sequence"
                        ]
                    )

                    if (
                        temporal_worker_state[
                            "busy"
                        ]
                    ):
                        temporal_worker_state[
                            "frontend_samples_while_busy"
                        ] += 1

                    if (
                        temporal_pending
                        is not None
                    ):
                        temporal_worker_state[
                            "superseded_pending"
                        ] += 1

                    temporal_pending = {
                        "generation":
                            int(
                                temporal_generation
                            ),

                        "snapshot":
                            list(
                                window
                            ),

                        # Cheap copy here; JPEG compression
                        # happens only if the worker actually
                        # consumes this generation.
                        "frame_bgr":
                            frame_bgr.copy(),

                        "phase":
                            str(
                                phase
                            ),

                        "elapsed_s":
                            float(
                                elapsed_s
                            ),
                    }

                    temporal_condition.notify()


        with temporal_condition:
            temporal_stop = True
            temporal_condition.notify_all()

        if (
            temporal_thread
            is not None
        ):
            temporal_thread.join()
            temporal_thread = None

        worker_error = (
            temporal_worker_state[
                "error"
            ]
        )

        if worker_error is not None:
            raise RuntimeError(
                "Temporal worker failed."
            ) from worker_error

        test_wall_s = (
            time.monotonic()
            - test_start
        )

        restart_gaps_ms = [
            float(
                item[
                    "temporal_restart_gap_ms"
                ]
            )
            for item
            in temporal_results
            if np.isfinite(
                item.get(
                    "temporal_restart_gap_ms",
                    float("nan"),
                )
            )
        ]

        temporal_duty_cycle = (
            temporal_worker_state[
                "total_infer_s"
            ]
            /
            max(
                test_wall_s,
                1e-9,
            )
        )

        print()
        print(
            "===== TEMPORAL SCHEDULING ====="
        )

        print(
            "jobs started:",
            temporal_worker_state[
                "jobs_started"
            ],
        )

        print(
            "jobs completed:",
            temporal_worker_state[
                "jobs_completed"
            ],
        )

        print(
            "pending windows superseded:",
            temporal_worker_state[
                "superseded_pending"
            ],
        )

        print(
            "stale pending windows dropped:",
            temporal_worker_state[
                "stale_pending_dropped"
            ],
        )

        print(
            "freshness waits:",
            temporal_worker_state[
                "freshness_wait_count"
            ],
        )

        if (
            temporal_worker_state[
                "freshness_wait_count"
            ]
            > 0
        ):
            mean_freshness_wait_ms = (
                temporal_worker_state[
                    "total_freshness_wait_s"
                ]
                * 1000.0
                /
                temporal_worker_state[
                    "freshness_wait_count"
                ]
            )

            print(
                "freshness wait mean:",
                f"{mean_freshness_wait_ms:.3f} ms",
            )

        print(
            "frontend samples while temporal busy:",
            temporal_worker_state[
                "frontend_samples_while_busy"
            ],
        )

        print(
            "max pending source age:",
            f"{temporal_max_pending_source_age_ms:.1f} ms",
        )

        print(
            "temporal duty cycle:",
            f"{temporal_duty_cycle * 100.0:.2f}%",
        )

        if restart_gaps_ms:
            print(
                "restart gap mean:",
                f"{np.mean(restart_gaps_ms):.3f} ms",
            )

            print(
                "restart gap median:",
                f"{np.median(restart_gaps_ms):.3f} ms",
            )

            print(
                "restart gap p95:",
                f"{np.percentile(restart_gaps_ms, 95):.3f} ms",
            )

            print(
                "restart gap max:",
                f"{np.max(restart_gaps_ms):.3f} ms",
            )

        else:
            print(
                "restart gap: insufficient completed jobs"
            )

        print()
        print(
            "MOTION SEQUENCE COMPLETE"
        )

    finally:
        if writer is not None:
            writer.release()

        if (
            temporal_thread
            is not None
            and
            temporal_thread.is_alive()
        ):
            with temporal_condition:
                temporal_stop = True
                temporal_condition.notify_all()

            temporal_thread.join()

        camera.stop()

    print()
    print(
        "============================================================"
    )

    print(
        "LIVE RESULTS"
    )

    print(
        "============================================================"
    )

    front_ms = [
        item["frontend_ms"]
        for item
        in frontend_log
    ]

    front_age_ms = [
        item["frontend_age_ms"]
        for item
        in frontend_log
    ]

    infer_ms = [
        item["infer_ms"]
        for item
        in temporal_results
    ]

    window_spans = [
        item["window_span_s"]
        for item
        in temporal_results
    ]

    source_age_ms = [
        item["source_age_ms"]
        for item
        in temporal_results
    ]

    if len(
        frontend_log
    ) >= 2:
        sample_time = (
            frontend_log[-1][
                "capture_ts"
            ]
            -
            frontend_log[0][
                "capture_ts"
            ]
        )

        frontend_fps = (
            (
                len(
                    frontend_log
                )
                - 1
            )
            / sample_time
            if sample_time > 0
            else float("nan")
        )

    else:
        frontend_fps = (
            float("nan")
        )

    sequence_steps = []

    if len(
        frontend_log
    ) >= 2:
        sequence_steps = [
            (
                frontend_log[i][
                    "capture_sequence"
                ]
                -
                frontend_log[i - 1][
                    "capture_sequence"
                ]
            )
            for i
            in range(
                1,
                len(
                    frontend_log
                ),
            )
        ]

    track_ids = [
        item["track_id"]
        for item
        in frontend_log
        if item["track_id"] >= 0
    ]

    track_changes = sum(
        int(
            a != b
        )
        for a, b
        in zip(
            track_ids[:-1],
            track_ids[1:],
        )
    )

    print(
        "frontend successful samples:",
        len(
            frontend_log
        ),
    )

    print(
        "frontend effective capture-time FPS:",
        f"{frontend_fps:.3f}",
    )

    print(
        "temporal GVHMR outputs:",
        len(
            temporal_results
        ),
    )

    print(
        "temporal output rate over 20s:",
        f"{len(temporal_results) / TEST_DURATION_S:.3f} Hz",
    )

    print(
        "track IDs:",
        dict(
            Counter(
                track_ids
            )
        ),
    )

    print(
        "track-ID changes:",
        track_changes,
    )

    print(
        "YOLOX calls:",
        track_state[
            "yolo_calls"
        ],
    )

    print(
        "keypoint bbox updates:",
        track_state[
            "kp_bbox_updates"
        ],
    )

    if sequence_steps:
        print(
            "camera sequence stride: "
            f"mean={np.mean(sequence_steps):.3f} "
            f"p95={np.percentile(sequence_steps, 95):.3f} "
            f"max={np.max(sequence_steps):.0f}"
        )

    print()

    print_stats(
        "frontend wall",
        front_ms,
        "ms",
    )

    print_stats(
        "frontend source age",
        front_age_ms,
        "ms",
    )

    print_stats(
        "GVHMR inference",
        infer_ms,
        "ms",
    )

    print_stats(
        "30-sample real window span",
        [
            span * 1000.0
            for span
            in window_spans
        ],
        "ms",
    )

    print_stats(
        "GVHMR newest-source age",
        source_age_ms,
        "ms",
    )

    if window_spans:
        print()

        print(
            "Ideal 30-frame / 30-Hz "
            "first-to-last span: "
            f"{29 / 30:.3f}s"
        )

        print(
            "Measured window-span "
            "mean/p95: "
            f"{np.mean(window_spans):.3f}s / "
            f"{percentile(window_spans, 95):.3f}s"
        )

    phase_counts = Counter(
        item["phase"]
        for item
        in temporal_results
    )

    print(
        "temporal outputs by phase:",
        dict(
            phase_counts
        ),
    )

    payload = {
        "format_version":
            1,

        "description":
            (
                "Live accelerated GVHMR "
                "causal-30 capture"
            ),

        "history_frames":
            HISTORY,

        "future_frames":
            0,

        "static_cam":
            True,

        "capture_requested_fps":
            CAPTURE_FPS,

        "K_fullimg":
            K_fullimg.clone(),

        "frontend_log":
            frontend_log,

        "temporal_results":
            temporal_results,
    }

    torch.save(
        payload,
        pt_path,
    )

    print()
    print(
        "PT:",
        pt_path,
    )

    print(
        "2D DEBUG VIDEO:",
        video_path,
    )

    print()

    if (
        len(
            temporal_results
        )
        > 0
        and
        len(
            frontend_log
        )
        > 0
    ):
        print(
            "LIVE CAUSAL GVHMR CAPTURE: PASS"
        )

    else:
        print(
            "LIVE CAUSAL GVHMR CAPTURE: INCOMPLETE"
        )


if __name__ == "__main__":
    main()
