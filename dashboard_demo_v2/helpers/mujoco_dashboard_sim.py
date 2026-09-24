#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import math
import socket
import threading
import time

import mujoco
import numpy as np

from gear_sonic.utils.mujoco_sim.base_sim import (
    BaseSimulator,
)

from gear_sonic.utils.mujoco_sim.configs import (
    SimLoopConfig,
)


DEFAULT_AZIMUTH = 120.0
DEFAULT_ELEVATION = -30.0
DEFAULT_DISTANCE = 2.0

MIN_ELEVATION = -80.0
MAX_ELEVATION = 20.0

MIN_DISTANCE = 0.85
MAX_DISTANCE = 6.0


class OrbitState:
    """
    Thread-safe presentation-camera state.

    This affects rendering only.
    It does not affect MuJoCo physics,
    SONIC, DDS, or robot state.
    """

    def __init__(self):
        self._lock = threading.RLock()

        self.azimuth = (
            DEFAULT_AZIMUTH
        )

        self.elevation = (
            DEFAULT_ELEVATION
        )

        self.distance = (
            DEFAULT_DISTANCE
        )

    @staticmethod
    def _clamp(
        value,
        lower,
        upper,
    ):
        return max(
            lower,
            min(
                upper,
                value,
            ),
        )

    def reset(self):
        with self._lock:
            self.azimuth = (
                DEFAULT_AZIMUTH
            )

            self.elevation = (
                DEFAULT_ELEVATION
            )

            self.distance = (
                DEFAULT_DISTANCE
            )

    def preset(
        self,
        name,
    ):
        name = str(
            name
        ).lower()

        with self._lock:

            if name == "front":
                self.azimuth = 180.0
                self.elevation = -20.0
                self.distance = 2.2

            elif name == "side":
                self.azimuth = 90.0
                self.elevation = -20.0
                self.distance = 2.2

            elif name == "rear":
                self.azimuth = 0.0
                self.elevation = -20.0
                self.distance = 2.2

            elif name == "reset":
                self.azimuth = (
                    DEFAULT_AZIMUTH
                )

                self.elevation = (
                    DEFAULT_ELEVATION
                )

                self.distance = (
                    DEFAULT_DISTANCE
                )

            else:
                raise ValueError(
                    f"Unknown preset: {name}"
                )

    def orbit(
        self,
        dx,
        dy,
    ):
        dx = float(
            dx
        )

        dy = float(
            dy
        )

        with self._lock:

            self.azimuth = (
                self.azimuth
                - dx * 0.35
            ) % 360.0

            self.elevation = (
                self._clamp(
                    self.elevation
                    - dy * 0.25,
                    MIN_ELEVATION,
                    MAX_ELEVATION,
                )
            )

    def zoom(
        self,
        delta,
    ):
        delta = float(
            delta
        )

        with self._lock:

            scale = math.exp(
                delta * 0.10
            )

            self.distance = (
                self._clamp(
                    self.distance
                    * scale,
                    MIN_DISTANCE,
                    MAX_DISTANCE,
                )
            )

    def apply(
        self,
        command,
    ):
        if not isinstance(
            command,
            dict,
        ):
            raise TypeError(
                "Command must be an object."
            )

        op = command.get(
            "op"
        )

        if op == "orbit":
            self.orbit(
                command.get(
                    "dx",
                    0.0,
                ),
                command.get(
                    "dy",
                    0.0,
                ),
            )

        elif op == "zoom":
            self.zoom(
                command.get(
                    "delta",
                    0.0,
                )
            )

        elif op == "reset":
            self.reset()

        elif op == "preset":
            self.preset(
                command.get(
                    "name",
                    "",
                )
            )

        else:
            raise ValueError(
                f"Unknown camera op: {op}"
            )

    def snapshot(self):
        with self._lock:
            return {
                "azimuth":
                    float(
                        self.azimuth
                    ),

                "elevation":
                    float(
                        self.elevation
                    ),

                "distance":
                    float(
                        self.distance
                    ),
            }


def camera_control_loop(
    state,
    port,
    stop_event,
):
    """
    Local UDP camera-control receiver.

    Presentation-only controls:
      orbit
      zoom
      preset
      reset
    """

    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_DGRAM,
    )

    sock.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    sock.bind(
        (
            "127.0.0.1",
            int(port),
        )
    )

    sock.settimeout(
        0.25
    )

    print(
        "[mujoco-dashboard] "
        f"camera control udp://127.0.0.1:{port}"
    )

    try:
        while not stop_event.is_set():

            try:
                payload, _addr = (
                    sock.recvfrom(
                        4096
                    )
                )

            except socket.timeout:
                continue

            try:
                command = json.loads(
                    payload.decode(
                        "utf-8"
                    )
                )

                state.apply(
                    command
                )

            except Exception as exc:
                print(
                    "[mujoco-dashboard] "
                    "camera command rejected:",
                    repr(exc),
                )

    finally:
        sock.close()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--interface",
        default="lo",
    )

    parser.add_argument(
        "--camera-port",
        type=int,
        default=5555,
    )

    parser.add_argument(
        "--control-port",
        type=int,
        default=5611,
    )

    parser.add_argument(
        "--width",
        type=int,
        default=1152,
    )

    parser.add_argument(
        "--height",
        type=int,
        default=720,
    )

    args = parser.parse_args()


    # --------------------------------------------------------
    # Load the exact existing SONIC/MuJoCo WBC config.
    # Only the presentation/render settings are overridden.
    # --------------------------------------------------------

    config = SimLoopConfig()

    config.interface = (
        args.interface
    )

    config.env_type = "sim"
    config.simulator = "mujoco"

    config.enable_onscreen = False
    config.enable_offscreen = True

    wbc_config = (
        config.load_wbc_yaml()
    )

    wbc_config[
        "ENV_NAME"
    ] = config.env_name

    wbc_config[
        "INTERFACE"
    ] = args.interface

    wbc_config[
        "ENABLE_ONSCREEN"
    ] = False

    wbc_config[
        "ENABLE_OFFSCREEN"
    ] = True


    # --------------------------------------------------------
    # Dashboard presentation camera.
    #
    # 1152x720 preserves the dashboard's 16:10 presentation
    # while remaining inside the G1 scene's existing
    # 1280x720 MuJoCo offscreen framebuffer.
    #
    # This is NOT tied to the human-camera dimensions.
    # --------------------------------------------------------

    orbit_state = OrbitState()

    camera = mujoco.MjvCamera()

    mujoco.mjv_defaultCamera(
        camera
    )

    camera.type = (
        mujoco.mjtCamera
        .mjCAMERA_TRACKING
    )

    camera.azimuth = (
        DEFAULT_AZIMUTH
    )

    camera.elevation = (
        DEFAULT_ELEVATION
    )

    camera.distance = (
        DEFAULT_DISTANCE
    )

    camera.lookat[:] = np.array(
        [
            0.0,
            0.0,
            0.5,
        ],
        dtype=float,
    )


    camera_configs = {
        "ego_view": {
            "height":
                int(
                    args.height
                ),

            "width":
                int(
                    args.width
                ),

            "params":
                camera,
        },
    }


    # --------------------------------------------------------
    # Same GR00T BaseSimulator, same physics and DDS bridge.
    # --------------------------------------------------------

    sim = BaseSimulator(
        config=wbc_config,
        env_name=config.env_name,
        onscreen=False,
        offscreen=True,
        enable_image_publish=True,
        camera_configs=camera_configs,
    )


    # ========================================================
    # D7C_MUJOCO_RELEASE_9
    # ========================================================
    #
    # Historical/validated simulation startup requires:
    #
    #     SONIC ] -> MuJoCo 9 -> SONIC ENTER
    #
    # This helper owns BaseSimulator, so invoking the existing
    # BaseSimulator keyboard API here follows the same
    # Unitree/MuJoCo code path as pressing keyboard key 9.
    #
    # The stack supervisor communicates through two tiny
    # runtime-local files:
    #
    #     mujoco_release.request
    #     mujoco_release.ack
    #
    # They are session/runtime artifacts only.
    # --------------------------------------------------------

    release_dir = (
        Path(__file__)
        .resolve()
        .parents[1]
        / ".runtime"
        / "simulation_stack"
    )

    release_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    release_request = (
        release_dir
        / "mujoco_release.request"
    )

    release_ack = (
        release_dir
        / "mujoco_release.ack"
    )


    def dashboard_release_worker():
        while True:
            if release_request.exists():
                try:
                    sim.handle_keyboard_button(
                        "9"
                    )

                    release_ack.write_text(
                        "released\n"
                    )

                    release_request.unlink(
                        missing_ok=True
                    )

                    print(
                        "[mujoco-dashboard] "
                        "D7C key 9 applied: "
                        "simulation robot released",
                        flush=True,
                    )

                except Exception as exc:
                    release_ack.write_text(
                        "error:"
                        + repr(exc)
                        + "\n"
                    )

                    print(
                        "[mujoco-dashboard] "
                        "D7C key 9 failed:",
                        repr(exc),
                        flush=True,
                    )

                return

            time.sleep(
                0.02
            )


    threading.Thread(
        target=dashboard_release_worker,
        name="mujoco-dashboard-release",
        daemon=True,
    ).start()


    pelvis_id = (
        sim.sim_env
        .mj_model
        .body(
            "pelvis"
        )
        .id
    )

    camera.trackbodyid = (
        pelvis_id
    )


    # --------------------------------------------------------
    # Replace ONLY the render-cache method on this instance.
    #
    # Reason:
    # mujoco.Renderer.render() returns RGB.
    # Existing ImageUtils uses cv2.imencode, which expects BGR.
    #
    # Convert RGB -> BGR here so the existing blue/turquoise
    # scene stays blue/turquoise rather than becoming brown.
    #
    # No second renderer.
    # No GR00T source edit.
    # --------------------------------------------------------

    def dashboard_update_render_caches():

        view = (
            orbit_state.snapshot()
        )

        camera.azimuth = (
            view["azimuth"]
        )

        camera.elevation = (
            view["elevation"]
        )

        camera.distance = (
            view["distance"]
        )

        renderer = (
            sim.sim_env
            .renderers[
                "ego_view"
            ]
        )

        renderer.update_scene(
            sim.sim_env.mj_data,
            camera=camera,
        )

        image_rgb = (
            renderer.render()
        )

        image_bgr = (
            np.ascontiguousarray(
                image_rgb[
                    ...,
                    ::-1
                ]
            )
        )

        render_caches = {
            "ego_view_image":
                image_bgr,
        }

        if (
            sim.sim_env
            .image_publish_process
            is not None
        ):
            sim.sim_env.image_publish_process.update_shared_memory(
                render_caches
            )

        return render_caches


    sim.sim_env.update_render_caches = (
        dashboard_update_render_caches
    )


    # --------------------------------------------------------
    # Browser camera-control receiver.
    # --------------------------------------------------------

    stop_event = (
        threading.Event()
    )

    control_thread = (
        threading.Thread(
            target=camera_control_loop,
            args=(
                orbit_state,
                args.control_port,
                stop_event,
            ),
            daemon=True,
            name=(
                "mujoco-dashboard-camera-control"
            ),
        )
    )

    control_thread.start()


    print(
        "[mujoco-dashboard] "
        f"render={args.width}x{args.height}"
    )

    print(
        "[mujoco-dashboard] "
        "camera=third-person pelvis tracking"
    )

    print(
        "[mujoco-dashboard] "
        "color=RGB-to-BGR corrected"
    )


    try:
        sim.start_image_publish_subprocess(
            camera_port=(
                args.camera_port
            )
        )

        time.sleep(
            1.0
        )

        sim.start()

    except KeyboardInterrupt:
        print(
            "[mujoco-dashboard] "
            "interrupted"
        )

    finally:
        stop_event.set()

        control_thread.join(
            timeout=1.0
        )

        sim.close()


if __name__ == "__main__":
    main()
