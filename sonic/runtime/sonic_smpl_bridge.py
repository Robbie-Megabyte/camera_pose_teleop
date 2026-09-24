#!/usr/bin/env python3

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import sys

import numpy as np
import torch

from pytorch3d.transforms import (
    axis_angle_to_matrix,
    matrix_to_axis_angle,
)

from hmr4d.utils.geo.hmr_global import (
    get_R_c2gv,
    get_tgtcoord_rootparam,
)

def _ensure_sonic_importable():
    """
    Resolve the NVIDIA GEAR-SONIC Python package without tying this
    bridge to one particular checkout location.

    Resolution order:
      1. gear_sonic already importable
      2. SONIC_ROOT environment variable
      3. common local NVIDIA repository locations

    SONIC_ROOT should point to the repository directory containing
    the top-level gear_sonic/ package.
    """

    try:
        import gear_sonic  # noqa: F401
        return None
    except ModuleNotFoundError:
        pass

    candidates = []

    env_root = os.environ.get(
        "SONIC_ROOT"
    )

    if env_root:
        candidates.append(
            Path(
                env_root
            ).expanduser()
        )

    checked = []

    for root in candidates:
        root = root.resolve()

        if root in checked:
            continue

        checked.append(
            root
        )

        package_dir = (
            root
            / "gear_sonic"
        )

        if not package_dir.is_dir():
            continue

        root_str = str(
            root
        )

        if root_str not in sys.path:
            sys.path.insert(
                0,
                root_str,
            )

        try:
            import gear_sonic  # noqa: F401
            return root
        except ModuleNotFoundError:
            continue

    raise ModuleNotFoundError(
        "Could not import gear_sonic. "
        "Set SONIC_ROOT to the NVIDIA "
        "GR00T-WholeBodyControl repository root."
    )


SONIC_IMPORT_ROOT = (
    _ensure_sonic_importable()
)


from gear_sonic.trl.utils.torch_transform import (
    angle_axis_to_quaternion,
    quat_apply,
    quat_inv,
)

from gear_sonic.isaac_utils.rotations import (
    smpl_root_ytoz_up,
    remove_smpl_base_rot,
)


YUP_TO_ZUP = torch.tensor(
    [
        [1.0, 0.0, 0.0],
        [0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0],
    ],
    dtype=torch.float32,
)


@dataclass(frozen=True)
class SonicCalibrationProfile:
    gravity_file: Path | None
    reference_file: Path | None

    alignment_mode: str = "fixed_v1"
    session_alignment_file: Path | None = None

    expected_reference_sha256: str | None = None
    expected_camera: str | None = None

    gravity_result_key: str = "result"
    gravity_expected_result: str = "STEREO_GRAVITY_PASS"

    camera_from_gravity_key: str = "R_left_from_gravity"
    gravity_up_camera_key: str = "gravity_up_left"
    gravity_from_camera_key: str = "R_gravity_from_left"

    @classmethod
    def from_paths(
        cls,
        gravity_file=None,
        reference_file=None,
        alignment_mode="fixed_v1",
        session_alignment_file=None,
        expected_reference_sha256=None,
        expected_camera=None,
        gravity_result_key="result",
        gravity_expected_result="STEREO_GRAVITY_PASS",
        camera_from_gravity_key="R_left_from_gravity",
        gravity_up_camera_key="gravity_up_left",
        gravity_from_camera_key="R_gravity_from_left",
    ):
        if alignment_mode not in (
            "fixed_v1",
            "session_v2",
        ):
            raise ValueError(
                "Unsupported alignment mode: "
                f"{alignment_mode!r}"
            )

        if (
            alignment_mode == "fixed_v1"
            and (
                gravity_file is None
                or reference_file is None
            )
        ):
            raise ValueError(
                "fixed_v1 requires gravity_file "
                "and reference_file"
            )

        if (
            alignment_mode == "session_v2"
            and session_alignment_file is None
        ):
            raise ValueError(
                "session_v2 requires "
                "session_alignment_file"
            )

        return cls(
            gravity_file=(
                Path(gravity_file)
                if gravity_file is not None
                else None
            ),
            reference_file=(
                Path(reference_file)
                if reference_file is not None
                else None
            ),
            alignment_mode=alignment_mode,
            session_alignment_file=(
                Path(session_alignment_file)
                if session_alignment_file
                is not None
                else None
            ),
            expected_reference_sha256=(
                expected_reference_sha256
            ),
            expected_camera=expected_camera,
            gravity_result_key=gravity_result_key,
            gravity_expected_result=gravity_expected_result,
            camera_from_gravity_key=camera_from_gravity_key,
            gravity_up_camera_key=gravity_up_camera_key,
            gravity_from_camera_key=gravity_from_camera_key,
        )


def _sha256(
    path: Path,
) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        for block in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            h.update(block)

    return h.hexdigest()


def build_calibrated_R_c2gv(
    profile: SonicCalibrationProfile,
    device: str | torch.device,
) -> torch.Tensor:

    with np.load(
        profile.gravity_file,
        allow_pickle=False,
    ) as g:

        required = (
            profile.gravity_result_key,
            profile.camera_from_gravity_key,
            profile.gravity_up_camera_key,
            profile.gravity_from_camera_key,
        )

        missing = [
            key
            for key in required
            if key not in g.files
        ]

        if missing:
            raise RuntimeError(
                "Gravity calibration missing keys: "
                f"{missing}"
            )

        result = str(
            np.asarray(
                g[
                    profile.gravity_result_key
                ]
            ).item()
        )

        if (
            result
            != profile.gravity_expected_result
        ):
            raise RuntimeError(
                "Gravity calibration invalid: "
                f"{result}"
            )

        R_camera_from_gravity = np.asarray(
            g[
                profile.camera_from_gravity_key
            ],
            dtype=np.float64,
        )

        gravity_up_camera = np.asarray(
            g[
                profile.gravity_up_camera_key
            ],
            dtype=np.float64,
        )

        R_gravity_from_camera = np.asarray(
            g[
                profile.gravity_from_camera_key
            ],
            dtype=np.float64,
        )

    mapped_up = (
        R_gravity_from_camera
        @ gravity_up_camera
    )

    if not np.allclose(
        mapped_up,
        np.array(
            [0.0, 0.0, 1.0]
        ),
        atol=1e-5,
    ):
        raise RuntimeError(
            "Gravity direction check failed: "
            f"{mapped_up}"
        )

    # Camera-frame orientation relative to the accepted
    # gravity/world frame. The key names come from the
    # calibration profile rather than a hard-coded camera.
    R_w2c_cpu = torch.tensor(
        R_camera_from_gravity,
        dtype=torch.float32,
    )

    R_c2gv = get_R_c2gv(
        R_w2c_cpu,
        axis_gravity_in_w=[
            0.0,
            0.0,
            -1.0,
        ],
    )

    return R_c2gv.to(
        device
    )


SESSION_ALIGNMENT_FORMAT_VERSION = 1


def load_session_R_c2gv(
    profile: SonicCalibrationProfile,
    device: str | torch.device,
) -> tuple[torch.Tensor, float]:

    path = profile.session_alignment_file

    if path is None:
        raise RuntimeError(
            "session_v2 profile has no "
            "session alignment file"
        )

    with np.load(
        path,
        allow_pickle=False,
    ) as z:

        required = (
            "format_version",
            "alignment_mode",
            "R_c2gv",
        )

        missing = [
            key
            for key in required
            if key not in z.files
        ]

        if missing:
            raise RuntimeError(
                "Session alignment missing keys: "
                f"{missing}"
            )

        format_version = int(
            np.asarray(
                z["format_version"]
            ).item()
        )

        alignment_mode = str(
            np.asarray(
                z["alignment_mode"]
            ).item()
        )

        R_c2gv_np = np.asarray(
            z["R_c2gv"],
            dtype=np.float64,
        )

        reference_smooth = (
            float(
                np.asarray(
                    z[
                        "smoothing_history_weight"
                    ]
                ).item()
            )
            if (
                "smoothing_history_weight"
                in z.files
            )
            else 0.8
        )

    if (
        format_version
        != SESSION_ALIGNMENT_FORMAT_VERSION
    ):
        raise RuntimeError(
            "Unsupported session alignment "
            "format version: "
            f"{format_version}"
        )

    if alignment_mode != "session_v2":
        raise RuntimeError(
            "Session alignment mode mismatch: "
            f"{alignment_mode!r}"
        )

    if R_c2gv_np.shape != (3, 3):
        raise RuntimeError(
            "Session R_c2gv must have shape "
            f"(3, 3), got {R_c2gv_np.shape}"
        )

    if not np.all(
        np.isfinite(
            R_c2gv_np
        )
    ):
        raise RuntimeError(
            "Session R_c2gv contains "
            "non-finite values"
        )

    gram = (
        R_c2gv_np.T
        @ R_c2gv_np
    )

    if not np.allclose(
        gram,
        np.eye(3),
        atol=1e-4,
    ):
        raise RuntimeError(
            "Session R_c2gv is not "
            "orthonormal"
        )

    determinant = float(
        np.linalg.det(
            R_c2gv_np
        )
    )

    if not np.isclose(
        determinant,
        1.0,
        atol=1e-4,
    ):
        raise RuntimeError(
            "Session R_c2gv determinant "
            "must be +1, got "
            f"{determinant}"
        )

    R_c2gv = torch.tensor(
        R_c2gv_np,
        dtype=torch.float32,
        device=device,
    )

    return (
        R_c2gv,
        reference_smooth,
    )


def calibrated_body_quat(
    global_orient_camera: torch.Tensor,
    R_c2gv: torch.Tensor,
) -> torch.Tensor:

    global_orient_camera = (
        global_orient_camera
        .reshape(
            -1,
            3,
        )
    )

    R_camera = axis_angle_to_matrix(
        global_orient_camera
    )

    R_gv = (
        R_c2gv.unsqueeze(0)
        @ R_camera
    )

    aa_gv = matrix_to_axis_angle(
        R_gv
    )

    zero_t = torch.zeros_like(
        aa_gv
    )

    aa_ay, _, _ = (
        get_tgtcoord_rootparam(
            aa_gv,
            zero_t,
            tsf="any->ay",
        )
    )

    q = angle_axis_to_quaternion(
        aa_ay
    )

    q = smpl_root_ytoz_up(
        q
    )

    q = remove_smpl_base_rot(
        q,
        w_last=False,
    )

    return q


def native_smpl_to_local_joints(
    joints_camera_yup: torch.Tensor,
    global_orient_camera: torch.Tensor,
) -> torch.Tensor:

    joints24 = (
        joints_camera_yup
        .reshape(
            24,
            3,
        )
    )

    global_orient_camera = (
        global_orient_camera
        .reshape(
            1,
            3,
        )
    )

    joints0 = (
        joints24
        - joints24[
            0:1
        ]
    )

    R_up = YUP_TO_ZUP.to(
        joints0.device
    )

    joints_z = (
        joints0
        @ R_up.T
    )

    q_camera = (
        angle_axis_to_quaternion(
            global_orient_camera
        )
    )

    q_camera_z = (
        smpl_root_ytoz_up(
            q_camera
        )
    )

    q_camera_nobase = (
        remove_smpl_base_rot(
            q_camera_z,
            w_last=False,
        )
    )

    inv = quat_inv(
        q_camera_nobase
    ).repeat(
        joints_z.shape[0],
        1,
    )

    return quat_apply(
        inv,
        joints_z,
    )


class PoseEMA:
    def __init__(
        self,
        history_weight=0.8,
    ):
        self.w = float(
            history_weight
        )

        if not (
            0.0
            <= self.w
            < 1.0
        ):
            raise ValueError(
                "history_weight must be "
                "in [0,1)"
            )

        self.joints = None
        self.quat = None

    def reset(
        self,
    ):
        self.joints = None
        self.quat = None

    def update(
        self,
        joints,
        quat,
    ):
        joints = np.asarray(
            joints,
            dtype=np.float32,
        ).reshape(
            1,
            24,
            3,
        )

        quat = np.asarray(
            quat,
            dtype=np.float32,
        ).reshape(
            1,
            4,
        )

        quat /= (
            np.linalg.norm(
                quat,
                axis=-1,
                keepdims=True,
            )
            + 1e-8
        )

        if self.joints is None:
            self.joints = (
                joints.copy()
            )

            self.quat = (
                quat.copy()
            )

        else:
            w = self.w

            self.joints = (
                w * self.joints
                + (1.0 - w)
                * joints
            )

            q_new = quat.copy()

            if float(
                (
                    self.quat
                    * q_new
                ).sum()
            ) < 0.0:
                q_new *= -1.0

            q = (
                w * self.quat
                + (1.0 - w)
                * q_new
            )

            q /= (
                np.linalg.norm(q)
                + 1e-8
            )

            self.quat = q

        return (
            self.joints.astype(
                np.float32
            ),
            self.quat.astype(
                np.float32
            ),
        )


class SonicSMPLBridge:
    """
    Generic canonical-SMPL24 -> SONIC Protocol-V3 field bridge.

    Estimator-independent input:
        joints_camera_yup: (24,3)
        global_orient_camera: (3,)

    Calibration is supplied as a profile rather than hardcoded.
    """

    def __init__(
        self,
        profile: SonicCalibrationProfile,
        device="cuda",
        history_weight=None,
        sonic_root=None,
        publisher_source_dir=None,
        port=5556,
        topic="pose",
        enable_publisher=False,
    ):
        self.profile = profile
        self.device = torch.device(
            device
        )

        if profile.alignment_mode == "fixed_v1":
            if (
                profile.gravity_file is None
                or profile.reference_file is None
            ):
                raise RuntimeError(
                    "fixed_v1 profile is missing "
                    "legacy calibration paths"
                )

            for path in (
                profile.gravity_file,
                profile.reference_file,
            ):
                if not path.exists():
                    raise FileNotFoundError(
                        path
                    )

            if (
                profile.expected_reference_sha256
                is not None
            ):
                actual = _sha256(
                    profile.reference_file
                )

                if (
                    actual
                    != profile.expected_reference_sha256
                ):
                    raise RuntimeError(
                        "Calibration reference SHA mismatch: "
                        f"{actual}"
                    )

            self.R_c2gv = (
                build_calibrated_R_c2gv(
                    profile,
                    self.device,
                )
            )

            with np.load(
                profile.reference_file,
                allow_pickle=False,
            ) as z:
                R_ref = np.asarray(
                    z["R_c2gv"],
                    dtype=np.float64,
                )

                camera = (
                    str(
                        np.asarray(
                            z["camera"]
                        ).item()
                    )
                    if "camera" in z.files
                    else None
                )

                reference_smooth = (
                    float(
                        np.asarray(
                            z[
                                "smoothing_history_weight"
                            ]
                        )
                    )
                    if (
                        "smoothing_history_weight"
                        in z.files
                    )
                    else 0.8
                )

            R_now = (
                self.R_c2gv
                .detach()
                .cpu()
                .numpy()
            )

            err = float(
                np.max(
                    np.abs(
                        R_now
                        - R_ref
                    )
                )
            )

            if err > 1e-6:
                raise RuntimeError(
                    "Derived calibration does not "
                    "match reference profile: "
                    f"max error={err}"
                )

            if (
                profile.expected_camera
                is not None
                and camera
                != profile.expected_camera
            ):
                raise RuntimeError(
                    "Calibration camera mismatch: "
                    f"{camera!r}"
                )

            self.camera = camera

        elif profile.alignment_mode == "session_v2":
            path = (
                profile.session_alignment_file
            )

            if path is None:
                raise RuntimeError(
                    "session_v2 profile has no "
                    "session alignment path"
                )

            if not path.exists():
                raise FileNotFoundError(
                    path
                )

            (
                self.R_c2gv,
                reference_smooth,
            ) = load_session_R_c2gv(
                profile,
                self.device,
            )

            # A V2 session is intentionally not
            # locked to a specific camera identity.
            self.camera = None

        else:
            raise RuntimeError(
                "Unsupported alignment mode: "
                f"{profile.alignment_mode!r}"
            )

        self.history_weight = (
            reference_smooth
            if history_weight is None
            else float(
                history_weight
            )
        )

        self.ema = PoseEMA(
            self.history_weight
        )

        self.publisher = None

        if enable_publisher:

            if publisher_source_dir is not None:
                source_dir = str(
                    Path(
                        publisher_source_dir
                    )
                )

                if source_dir not in sys.path:
                    sys.path.insert(
                        0,
                        source_dir,
                    )

            from soma_to_smpl import (
                SonicV3Publisher,
            )

            self.publisher = (
                SonicV3Publisher(
                    port=int(port),
                    topic=str(topic),
                    sonic_root=(
                        None
                        if sonic_root is None
                        else str(
                            sonic_root
                        )
                    ),
                )
            )

    @torch.inference_mode()
    def convert(
        self,
        joints_camera_yup,
        global_orient_camera,
    ):
        joints_camera_yup = (
            torch.as_tensor(
                joints_camera_yup,
                dtype=torch.float32,
                device=self.device,
            )
            .reshape(
                24,
                3,
            )
        )

        global_orient_camera = (
            torch.as_tensor(
                global_orient_camera,
                dtype=torch.float32,
                device=self.device,
            )
            .reshape(
                1,
                3,
            )
        )

        joints_local = (
            native_smpl_to_local_joints(
                joints_camera_yup,
                global_orient_camera,
            )
        )

        root_quat = (
            calibrated_body_quat(
                global_orient_camera,
                self.R_c2gv,
            )
        )

        joints_np = (
            joints_local
            .detach()
            .cpu()
            .numpy()
        )

        quat_np = (
            root_quat
            .detach()
            .cpu()
            .numpy()
        )

        (
            joints_smoothed,
            quat_smoothed,
        ) = self.ema.update(
            joints_np,
            quat_np,
        )

        return {
            "smpl_joints":
                joints_smoothed,

            "body_quat":
                quat_smoothed,

            "smpl_pose":
                np.zeros(
                    (
                        1,
                        21,
                        3,
                    ),
                    dtype=np.float32,
                ),

            "wrists":
                np.zeros(
                    (
                        1,
                        6,
                    ),
                    dtype=np.float32,
                ),
        }

    def publish(
        self,
        joints_camera_yup,
        global_orient_camera,
    ):
        fields = self.convert(
            joints_camera_yup,
            global_orient_camera,
        )

        if self.publisher is None:
            raise RuntimeError(
                "Publisher is disabled"
            )

        self.publisher.publish(
            fields
        )

        return fields

    def close(
        self,
    ):
        if self.publisher is not None:
            self.publisher.close()
            self.publisher = None
