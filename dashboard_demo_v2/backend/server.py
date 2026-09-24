#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import mimetypes
from pathlib import Path
import signal
import socket
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
import threading
import time
from urllib.parse import urlparse

from supervisor import V2Supervisor
from keypoint_bridge import KeypointPreviewBridge
from raw_preview_bridge import RawPreviewBridge
from mujoco_preview_bridge import MujocoPreviewBridge
from robot_camera_bridge import RobotCameraBridge
from robot_mode_controller import RobotModeController
from sonic_supervisor import SonicSupervisor
from simulation_stack_supervisor import SimulationStackSupervisor
from physical_stack_supervisor import (
    PhysicalStackSupervisor,
    RemotePhysicalSonicSupervisor,
)


HERE = Path(__file__).resolve()

DASHBOARD_ROOT = (
    HERE.parents[1]
)

FRONTEND_ROOT = (
    DASHBOARD_ROOT
    / "frontend"
)

REPO_ROOT = (
    HERE.parents[3]
)

START_TIME = time.monotonic()

SUPERVISOR = V2Supervisor(
    REPO_ROOT
)

SONIC = SonicSupervisor(
    runtime_dir=(
        DASHBOARD_ROOT
        / ".runtime"
    ),
    groot_root=(
        Path.home()
        / "GR00T-WholeBodyControl"
    ),
)

KEYPOINT_PREVIEW = KeypointPreviewBridge(
    endpoint="tcp://127.0.0.1:5601",
    stale_after_s=2.0,
)

RAW_PREVIEW = RawPreviewBridge(
    host="127.0.0.1",
    port=5600,
    stale_after_s=2.0,
)

MUJOCO_PREVIEW = MujocoPreviewBridge(
    endpoint="tcp://127.0.0.1:5610",
    stale_after_s=2.0,
)


# ============================================================
# D11B_ROBOT_CAMERA
# ============================================================

ROBOT_CAMERA = RobotCameraBridge(
    runtime_dir=(
        DASHBOARD_ROOT
        / ".runtime"
        / "robot_camera"
    ),
    host="192.168.0.116",
    user="unitree",
    ssh_key=(
        Path.home()
        / ".ssh"
        / "bacalbasa_g1_dashboard_ed25519"
    ),
    device=(
        "/dev/v4l/by-path/"
        "platform-3610000.usb-usb-0:2.3.1:1.0-video-index0"
    ),
    width=1280,
    height=720,
    fps=30,
)



# ============================================================
# D12D_ROBOT_MODES
# ============================================================

ROBOT_MODES = RobotModeController(
    runtime_dir=(
        DASHBOARD_ROOT
        / ".runtime"
        / "robot_modes"
    ),
    host="192.168.0.116",
    user="unitree",
    ssh_key=(
        Path.home()
        / ".ssh"
        / "bacalbasa_g1_dashboard_ed25519"
    ),
    interface="enP8p1s0",
)


STACK = SimulationStackSupervisor(
    dashboard_root=DASHBOARD_ROOT,
    repo_root=REPO_ROOT,
    v2_supervisor=SUPERVISOR,
    sonic_supervisor=SONIC,
    mujoco_preview=MUJOCO_PREVIEW,
)




# ============================================================
# D10B_TWO_STAGE_PHYSICAL
# ============================================================

VALIDATION_SONIC = SonicSupervisor(
    runtime_dir=(
        DASHBOARD_ROOT
        / ".runtime"
        / "sonic_validation"
    ),
    groot_root=(
        Path.home()
        / "GR00T-WholeBodyControl"
    ),
)


PHYSICAL_SONIC = RemotePhysicalSonicSupervisor(
    runtime_dir=(
        DASHBOARD_ROOT
        / ".runtime"
        / "physical_sonic"
    ),
    host="192.168.0.116",
    user="unitree",
    ssh_key=(
        Path.home()
        / ".ssh"
        / "bacalbasa_g1_dashboard_ed25519"
    ),
    pc_pose_host="192.168.0.187",
)


PHYSICAL = PhysicalStackSupervisor(
    dashboard_root=DASHBOARD_ROOT,
    repo_root=REPO_ROOT,
    v2_supervisor=SUPERVISOR,
    validation_sonic=VALIDATION_SONIC,
    physical_sonic=PHYSICAL_SONIC,
    mujoco_preview=MUJOCO_PREVIEW,
    simulation_stack=STACK,
    simulation_sonic=SONIC,
    robot_camera=ROBOT_CAMERA,
)


# ============================================================
# D9C ROBOT CONNECTIVITY
# ============================================================

ROBOT_HOST = "192.168.0.116"
ROBOT_SSH_PORT = 22


def robot_connectivity_status():
    started = time.monotonic()

    connected = False
    error = None

    try:
        with socket.create_connection(
            (
                ROBOT_HOST,
                ROBOT_SSH_PORT,
            ),
            timeout=0.8,
        ):
            connected = True

    except OSError as exc:
        error = (
            f"{type(exc).__name__}: "
            f"{exc}"
        )

    elapsed_ms = (
        time.monotonic()
        - started
    ) * 1000.0

    return {
        "connected": connected,
        "host": ROBOT_HOST,
        "port": ROBOT_SSH_PORT,
        "latency_ms": (
            round(
                elapsed_ms,
                1,
            )
            if connected
            else None
        ),
        "error": error,
    }



# ============================================================
# D10E_TERMINAL_LOGS
# ============================================================

def _latest_log(
    candidates,
):
    existing = [
        Path(
            path
        )
        for path
        in candidates
        if Path(
            path
        ).is_file()
    ]

    if not existing:
        return None

    return max(
        existing,
        key=lambda path:
            path.stat().st_mtime,
    )


def _tail_log(
    path,
    max_bytes=65536,
    max_lines=500,
):
    if path is None:
        return ""

    try:
        with Path(
            path
        ).open(
            "rb"
        ) as handle:
            handle.seek(
                0,
                2,
            )

            size = handle.tell()

            handle.seek(
                max(
                    0,
                    size - int(
                        max_bytes
                    ),
                )
            )

            data = handle.read()

    except Exception as exc:
        return (
            "[dashboard log reader error] "
            + repr(
                exc
            )
        )


    text = data.decode(
        "utf-8",
        errors="replace",
    )

    lines = text.splitlines()

    return "\n".join(
        lines[
            -int(
                max_lines
            ):
        ]
    )


def terminal_logs_snapshot():
    runtime = (
        DASHBOARD_ROOT
        / ".runtime"
    )


    v2_logs = list(
        (
            runtime
            / "v2_runs"
        ).glob(
            "v2_*.log"
        )
    )


    sources = {
        "v2": (
            "V2",
            _latest_log(
                v2_logs
            ),
        ),

        "mujoco": (
            "MUJOCO",
            _latest_log(
                [
                    runtime
                    / "physical_stack"
                    / "mujoco.log",

                    runtime
                    / "simulation_stack"
                    / "mujoco.log",

                    runtime
                    / "mujoco_dashboard_sim.log",
                ]
            ),
        ),

        "relay": (
            "RELAY",
            _latest_log(
                [
                    runtime
                    / "physical_stack"
                    / "relay.log",

                    runtime
                    / "simulation_stack"
                    / "relay.log",

                    runtime
                    / "mujoco_relay.log",
                ]
            ),
        ),

        "sim_sonic": (
            "SIM SONIC",
            _latest_log(
                [
                    runtime
                    / "sonic_validation"
                    / "sonic_sim.log",

                    runtime
                    / "sonic_sim.log",
                ]
            ),
        ),

        "physical_sonic": (
            "PHYSICAL SONIC",
            _latest_log(
                [
                    runtime
                    / "physical_sonic"
                    / "physical_sonic.log",
                ]
            ),
        ),

        "robot_camera": (
            "ROBOT CAMERA",
            _latest_log(
                [
                    runtime
                    / "robot_camera"
                    / "robot_camera.log",
                ]
            ),
        ),

        "robot_modes": (
            "ROBOT MODES",
            _latest_log(
                [
                    runtime
                    / "robot_modes"
                    / "robot_modes.log",
                ]
            ),
        ),

        "dashboard": (
            "DASHBOARD",
            _latest_log(
                [
                    runtime
                    / "dashboard_server.log",

                    runtime
                    / "dashboard.log",
                ]
            ),
        ),
    }


    result = {}

    for key, (
        label,
        path,
    ) in sources.items():
        result[
            key
        ] = {
            "label":
                label,

            "path":
                (
                    str(
                        path
                    )
                    if path
                    is not None
                    else None
                ),

            "text":
                _tail_log(
                    path
                ),
        }


    physical = (
        PHYSICAL.snapshot()
    )


    return {
        "ok": True,

        "sources":
            result,

        "physical_state":
            physical.get(
                "state",
                "off",
            ),

        "physical_error":
            physical.get(
                "last_error"
            ),

        "server_time":
            time.strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
    }



def full_status():
    state = (
        SUPERVISOR
        .snapshot_state()
    )

    sonic_state = SONIC.snapshot()

    state[
        "sonic"
    ] = sonic_state

    simulation = state.get(
        "simulation"
    )

    if not isinstance(
        simulation,
        dict,
    ):
        simulation = {}

    else:
        simulation = dict(
            simulation
        )

    simulation[
        "sonic"
    ] = sonic_state.get(
        "state",
        "off",
    )

    state[
        "simulation"
    ] = simulation

    state[
        "stack"
    ] = STACK.snapshot()

    state[
        "dashboard"
    ] = {
        "status": "online",
        "uptime_s": round(
            time.monotonic()
            - START_TIME,
            1,
        ),
    }

    state[
        "keypoint_preview"
    ] = KEYPOINT_PREVIEW.snapshot()

    state[
        "raw_preview"
    ] = RAW_PREVIEW.snapshot()

    state[
        "mujoco_preview"
    ] = MUJOCO_PREVIEW.snapshot()

    state[
        "server_time"
    ] = time.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    state[
        "physical"
    ] = PHYSICAL.snapshot()

    state[
        "robot_camera"
    ] = ROBOT_CAMERA.snapshot()

    state[
        "robot_modes"
    ] = ROBOT_MODES.snapshot()

    return state


class DashboardHandler(
    BaseHTTPRequestHandler
):
    server_version = (
        "CameraPoseTeleopV2Dashboard/0.9"
    )

    def log_message(
        self,
        fmt,
        *args,
    ):
        print(
            "[dashboard-http] "
            + fmt % args,
            flush=True,
        )

    def send_json(
        self,
        payload,
        status=200,
    ):
        body = json.dumps(
            payload,
            indent=2,
        ).encode("utf-8")

        self.send_response(
            status
        )

        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.send_header(
            "Cache-Control",
            "no-store",
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def send_jpeg(
        self,
        frame,
    ):
        if frame is None:
            self.send_response(
                503
            )

            self.send_header(
                "Cache-Control",
                "no-store",
            )

            self.send_header(
                "Content-Length",
                "0",
            )

            self.end_headers()
            return

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            "image/jpeg",
        )

        self.send_header(
            "Content-Length",
            str(len(frame)),
        )

        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate, max-age=0",
        )

        self.end_headers()

        self.wfile.write(
            frame
        )


    def serve_file(
        self,
        path,
    ):
        if not path.is_file():
            self.send_error(
                404
            )
            return

        body = path.read_bytes()

        content_type = (
            mimetypes.guess_type(
                str(path)
            )[0]
            or
            "application/octet-stream"
        )

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            content_type,
        )

        self.send_header(
            "Content-Length",
            str(len(body)),
        )

        self.send_header(
            "Cache-Control",
            "no-store",
        )

        self.end_headers()

        self.wfile.write(
            body
        )

    def send_mujoco_mjpeg_stream(
        self,
    ):
        """
        Persistent latest-frame MuJoCo MJPEG response.

        The bridge already holds complete JPEG bytes.
        This method does not decode or re-encode frames.
        """

        boundary = "mujoco-frame"

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            (
                "multipart/x-mixed-replace; "
                f"boundary={boundary}"
            ),
        )

        self.send_header(
            "Cache-Control",
            (
                "no-store, no-cache, "
                "must-revalidate, max-age=0"
            ),
        )

        self.send_header(
            "Pragma",
            "no-cache",
        )

        self.send_header(
            "Expires",
            "0",
        )

        self.end_headers()

        last_seq = -1

        try:
            while True:
                seq, frame = (
                    MUJOCO_PREVIEW
                    .wait_for_frame(
                        after_seq=last_seq,
                        timeout_s=1.0,
                        max_age_s=2.0,
                    )
                )

                if frame is None:
                    continue

                last_seq = seq

                header = (
                    f"--{boundary}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n"
                    "Cache-Control: no-store\r\n"
                    "\r\n"
                ).encode(
                    "ascii"
                )

                self.wfile.write(
                    header
                )

                self.wfile.write(
                    frame
                )

                self.wfile.write(
                    b"\r\n"
                )

                self.wfile.flush()

        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
            OSError,
        ):
            return

    def send_robot_camera_mjpeg_stream(
        self,
    ):
        boundary = (
            "robot-camera-frame"
        )

        self.send_response(
            200
        )

        self.send_header(
            "Content-Type",
            (
                "multipart/x-mixed-replace; "
                f"boundary={boundary}"
            ),
        )

        self.send_header(
            "Cache-Control",
            "no-store, no-cache, must-revalidate",
        )

        self.send_header(
            "Pragma",
            "no-cache",
        )

        self.end_headers()


        seq = 0


        try:
            while True:
                seq, frame = (
                    ROBOT_CAMERA
                    .wait_for_frame(
                        after_seq=seq,
                        timeout_s=2.0,
                    )
                )


                if frame is None:
                    time.sleep(
                        0.05
                    )

                    continue


                header = (
                    f"--{boundary}\r\n"
                    "Content-Type: image/jpeg\r\n"
                    f"Content-Length: {len(frame)}\r\n"
                    "\r\n"
                ).encode(
                    "ascii"
                )


                self.wfile.write(
                    header
                )

                self.wfile.write(
                    frame
                )

                self.wfile.write(
                    b"\r\n"
                )

                self.wfile.flush()


        except (
            BrokenPipeError,
            ConnectionResetError,
            ConnectionAbortedError,
        ):
            return


    def do_GET(
        self,
    ):
        path = (
            urlparse(
                self.path
            ).path
        )

        if path in (
            "/api/camera/frame.jpg",
            "/api/camera/keypoints.jpg",
        ):
            self.send_jpeg(
                KEYPOINT_PREVIEW
                .get_latest_frame()
            )
            return

        if path == "/api/camera/raw.jpg":
            self.send_jpeg(
                RAW_PREVIEW
                .get_latest_frame()
            )
            return

        if path == "/api/robot-camera/stream.mjpg":
            self.send_robot_camera_mjpeg_stream()
            return


        if path == "/api/robot-camera/frame.jpg":
            self.send_jpeg(
                ROBOT_CAMERA
                .get_latest_frame()
            )
            return


        if path == "/api/mujoco/stream.mjpg":
            self.send_mujoco_mjpeg_stream()
            return

        if path == "/api/mujoco/frame.jpg":
            self.send_jpeg(
                MUJOCO_PREVIEW
                .get_latest_frame()
            )
            return

        if path == "/api/robot/modes/status":
            self.send_json(
                ROBOT_MODES.status()
            )
            return


        if path == "/api/robot/connectivity":
            data = robot_connectivity_status()

            body = json.dumps(
                data
            ).encode(
                "utf-8"
            )

            self.send_response(
                200
            )

            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )

            self.send_header(
                "Content-Length",
                str(
                    len(
                        body
                    )
                ),
            )

            self.send_header(
                "Cache-Control",
                "no-store",
            )

            self.end_headers()

            self.wfile.write(
                body
            )

            return


        if path == "/api/health":
            self.send_json(
                {
                    "ok": True,
                    "service":
                        "camera_pose_teleop_v2_dashboard",
                    "version":
                        "0.9",
                }
            )
            return

        if path == "/api/status":
            self.send_json(
                full_status()
            )
            return

        if path == "/api/events":
            self.send_json(
                {
                    "events":
                        SUPERVISOR
                        .snapshot_events()
                }
            )
            return

        if path == "/api/logs/terminal":
            self.send_json(
                terminal_logs_snapshot()
            )
            return


        if path == "/api/logs":
            self.send_json(
                {
                    "logs":
                        SUPERVISOR
                        .snapshot_logs()
                }
            )
            return

        if path in (
            "/",
            "/index.html",
        ):
            self.serve_file(
                FRONTEND_ROOT
                / "index.html"
            )
            return

        static_map = {
            "/app.js":
                FRONTEND_ROOT
                / "app.js",

            "/style.css":
                FRONTEND_ROOT
                / "style.css",

            "/reference_video_skin.css":
                FRONTEND_ROOT
                / "reference_video_skin.css",

            "/reference_video_skin.js":
                FRONTEND_ROOT
                / "reference_video_skin.js",
        }

        static_file = (
            static_map.get(path)
        )

        if static_file is not None:
            self.serve_file(
                static_file
            )
            return

        self.send_error(
            404
        )

    def do_POST(
        self,
    ):
        path = (
            urlparse(
                self.path
            ).path
        )

        # -------------------------------------------------
        # MuJoCo presentation-camera control.
        #
        # Browser
        #   -> dashboard HTTP
        #   -> localhost UDP 5611
        #   -> MuJoCo presentation camera
        #
        # This does NOT alter:
        #   physics
        #   DDS
        #   SONIC
        #   V2
        # -------------------------------------------------

        if (
            path
            == "/api/mujoco/camera"
        ):
            try:
                length = int(
                    self.headers.get(
                        "Content-Length",
                        "0",
                    )
                )

                if (
                    length < 0
                    or
                    length > 4096
                ):
                    raise ValueError(
                        "Invalid request size."
                    )

                raw = (
                    self.rfile.read(
                        length
                    )
                    if length
                    else b"{}"
                )

                command = json.loads(
                    raw.decode(
                        "utf-8"
                    )
                )

                if not isinstance(
                    command,
                    dict,
                ):
                    raise ValueError(
                        "Command must be an object."
                    )

                op = command.get(
                    "op"
                )

                if op == "orbit":
                    command = {
                        "op": "orbit",

                        "dx": float(
                            command.get(
                                "dx",
                                0.0,
                            )
                        ),

                        "dy": float(
                            command.get(
                                "dy",
                                0.0,
                            )
                        ),
                    }

                elif op == "zoom":
                    command = {
                        "op": "zoom",

                        "delta": float(
                            command.get(
                                "delta",
                                0.0,
                            )
                        ),
                    }

                elif op == "reset":
                    command = {
                        "op": "reset",
                    }

                elif op == "preset":
                    name = command.get(
                        "name"
                    )

                    if name not in {
                        "front",
                        "side",
                        "rear",
                        "reset",
                    }:
                        raise ValueError(
                            "Unknown camera preset."
                        )

                    command = {
                        "op": "preset",
                        "name": name,
                    }

                else:
                    raise ValueError(
                        "Unknown camera operation."
                    )

                payload = json.dumps(
                    command,
                    separators=(
                        ",",
                        ":",
                    ),
                ).encode(
                    "utf-8"
                )

                sock = socket.socket(
                    socket.AF_INET,
                    socket.SOCK_DGRAM,
                )

                try:
                    sock.sendto(
                        payload,
                        (
                            "127.0.0.1",
                            5611,
                        ),
                    )

                finally:
                    sock.close()

                self.send_json(
                    {
                        "ok": True,
                        "queued": True,
                    }
                )

            except Exception as exc:
                self.send_json(
                    {
                        "ok": False,
                        "error": str(exc),
                    },
                    status=400,
                )

            return

        # -------------------------------------------------
        # SONIC simulation supervisor
        # -------------------------------------------------

        # -------------------------------------------------
        # Complete one-button SIMULATION stack
        # -------------------------------------------------

        # -------------------------------------------------
        # D12D ROBOT MODE ACTIONS
        # -------------------------------------------------

        if path.startswith(
            "/api/robot/modes/"
        ):
            action = path.rsplit(
                "/",
                1,
            )[-1]


            physical = (
                PHYSICAL.snapshot()
            )


            # Primary ownership interlock.
            #
            # Every robot-mode action requires the complete
            # Bacalbasa physical stack to be OFF.
            if (
                physical.get(
                    "state"
                )
                != "off"
                or
                physical.get(
                    "active"
                )
            ):
                self.send_json(
                    {
                        "ok": False,
                        "error":
                            (
                                "Robot mode changes are "
                                "locked while Bacalbasa "
                                "owns the physical robot. "
                                "Use Stop System first."
                            ),
                    },
                    status=409,
                )

                return


            result = (
                ROBOT_MODES.action(
                    action
                )
            )


            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        # -------------------------------------------------
        # TWO-STAGE PHYSICAL ROBOT STACK
        # -------------------------------------------------

        if (
            path
            == "/api/system/robot/deploy"
        ):
            result = PHYSICAL.deploy()

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/system/robot/start"
        ):
            result = PHYSICAL.start_live()

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/system/robot/stop"
        ):
            result = PHYSICAL.stop(
                reason="dashboard_button"
            )

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/system/sim/start"
        ):
            result = STACK.start()

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/system/sim/stop"
        ):
            result = STACK.stop(
                reason="dashboard_button"
            )

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/sonic/sim/start"
        ):
            result = SONIC.start()

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/sonic/sim/policy"
        ):
            result = (
                SONIC
                .request_policy_control()
            )

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/sonic/sim/stop"
        ):
            result = (
                SONIC
                .stop_process()
            )

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )

            return


        if (
            path
            == "/api/teleop/start"
        ):
            result = (
                SUPERVISOR.start()
            )

            self.send_json(
                result,
                status=(
                    200
                    if result.get(
                        "ok"
                    )
                    else 409
                ),
            )
            return

        if (
            path
            == "/api/teleop/stop"
        ):
            result = (
                SUPERVISOR.stop(
                    reason=(
                        "dashboard_button"
                    )
                )
            )

            self.send_json(
                result
            )
            return

        self.send_json(
            {
                "ok": False,
                "error":
                    "Unknown POST endpoint.",
            },
            status=404,
        )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--host",
        default="127.0.0.1",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8088,
    )

    args = parser.parse_args()

    server = ThreadingHTTPServer(
        (
            args.host,
            args.port,
        ),
        DashboardHandler,
    )

    # MJPEG responses are long-lived HTTP request threads.
    # An open browser stream must never prevent shutdown.
    server.daemon_threads = True

    stop_event = (
        threading.Event()
    )

    def request_stop(
        signum,
        frame,
    ):
        del signum, frame

        if stop_event.is_set():
            return

        stop_event.set()

        print(
            "\nDashboard shutdown requested.",
            flush=True,
        )

        threading.Thread(
            target=server.shutdown,
            daemon=True,
        ).start()

    signal.signal(
        signal.SIGINT,
        request_stop,
    )

    signal.signal(
        signal.SIGTERM,
        request_stop,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        "CAMERA POSE TELEOP V2 — DASHBOARD DEMO",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    print(
        f"Dashboard: http://{args.host}:{args.port}",
        flush=True,
    )

    print(
        "V2 supervisor: ENABLED",
        flush=True,
    )

    print(
        "Production command:",
        "run_pose.sh dual",
        flush=True,
    )

    print(
        "Camera is opened ONLY after Start V2.",
        flush=True,
    )

    print(
        "============================================================",
        flush=True,
    )

    try:
        server.serve_forever(
            poll_interval=0.25
        )

    finally:
        STACK.stop(
            reason="dashboard_shutdown"
        )

        SUPERVISOR.stop(
            reason=(
                "dashboard_shutdown"
            )
        )

        SONIC.stop_process(
            graceful_timeout_s=8.0
        )

        KEYPOINT_PREVIEW.stop()
        RAW_PREVIEW.stop()
        MUJOCO_PREVIEW.stop()
        ROBOT_CAMERA.stop()

        server.server_close()

        print(
            "Dashboard backend stopped.",
            flush=True,
        )


if __name__ == "__main__":
    main()
