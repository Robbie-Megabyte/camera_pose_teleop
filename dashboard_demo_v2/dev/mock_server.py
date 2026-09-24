#!/usr/bin/env python3

import argparse
import html
import json
import mimetypes
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = DASHBOARD_ROOT / "frontend"
START_TIME = time.monotonic()

LOCK = threading.Lock()

STATE = {
    "simulation": False,
    "teleop": False,
    "physical_state": "off",
    "physical_active": False,
    "physical_live": False,
    "robot_mode": "WALK",
    "events": [],
    "logs": [],
}


def now():
    return time.strftime("%H:%M:%S")


def add_event(message, level="info"):
    with LOCK:
        STATE["events"].append({
            "time": now(),
            "level": level,
            "message": message,
        })
        STATE["events"] = STATE["events"][-80:]


def add_log(line):
    with LOCK:
        STATE["logs"].append({
            "time": now(),
            "line": line,
        })
        STATE["logs"] = STATE["logs"][-160:]


def snapshot():
    with LOCK:
        sim = bool(STATE["simulation"])
        teleop = bool(STATE["teleop"])
        physical_state = STATE["physical_state"]
        physical_active = bool(STATE["physical_active"])
        physical_live = bool(STATE["physical_live"])
        mode = STATE["robot_mode"]

    pipeline_active = sim or teleop or physical_active
    tracking_live = sim or teleop or physical_live

    return {
        "dashboard": {
            "status": "online",
            "uptime_s": round(time.monotonic() - START_TIME, 1),
        },

        "mode": "session_v2",

        "camera": {
            "state": "ready" if pipeline_active else "off",
        },

        "gvhmr": {
            "state": (
                "running"
                if tracking_live
                else ("ready" if pipeline_active else "off")
            ),
            "history_frames": 30 if pipeline_active else 0,
            "history_required": 30,
        },

        "framing": {
            "state": "ready" if pipeline_active else "off",
            "good_streak": 15 if pipeline_active else 0,
            "required_streak": 15,
        },

        "alignment": {
            "state": "ready" if pipeline_active else "off",
            "valid_frames": 30 if pipeline_active else 0,
        },

        "sonic_bridge": {
            "state": "ready" if pipeline_active else "off",
        },

        "publisher": {
            "state": "running" if tracking_live else "off",
            "pose_hz": 15.0 if tracking_live else None,
        },

        "teleop": {
            "state": "running" if teleop else "off",
            "process_alive": teleop,
            "running": teleop,
            "pid": 42420 if teleop else None,
            "last_error": None,
        },

        "simulation": {
            "mujoco": "running" if sim else "off",
            "sonic": "running" if sim else "off",
        },

        "sonic": {
            "state": "running" if sim else "off",
            "process_alive": sim,
            "zmq_live": tracking_live,
        },

        "stack": {
            "state": "running" if sim else "off",
            "active": sim,
            "last_error": None,
        },

        "keypoint_preview": {
            "live": pipeline_active,
        },

        "raw_preview": {
            "live": pipeline_active,
        },

        "mujoco_preview": {
            "live": sim,
        },

        "physical": {
            "state": physical_state,
            "active": physical_active,
            "ready_to_start": physical_state == "ready_to_start",
            "live": physical_live,
            "last_error": None,
        },

        "robot_camera": {
            "live": physical_active,
            "state": "running" if physical_active else "off",
        },

        "robot_modes": {
            "display_mode": mode,
            "mode": mode,
        },

        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "ui_dev_mock": True,
    }


def terminal_snapshot():
    with LOCK:
        logs = list(STATE["logs"])
        physical_state = STATE["physical_state"]

    combined = "\n".join(
        f"[{item['time']}] {item['line']}"
        for item in logs
    )

    if not combined:
        combined = (
            "UI DEVELOPMENT MOCK\n"
            "No real subsystem is running."
        )

    labels = {
        "v2": "V2",
        "mujoco": "MUJOCO",
        "relay": "RELAY",
        "sim_sonic": "SIM SONIC",
        "physical_sonic": "PHYSICAL SONIC",
        "robot_camera": "ROBOT CAMERA",
        "robot_modes": "ROBOT MODES",
        "dashboard": "DASHBOARD",
    }

    sources = {}

    for key, label in labels.items():
        sources[key] = {
            "label": label,
            "path": f"UI DEV MOCK / {label}",
            "text": combined,
        }

    return {
        "ok": True,
        "sources": sources,
        "physical_state": physical_state,
        "physical_error": None,
        "server_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def svg_frame(title, subtitle):
    title = html.escape(title)
    subtitle = html.escape(subtitle)

    body = (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="1280" height="720" viewBox="0 0 1280 720">'
        '<rect width="1280" height="720" fill="#171717"/>'
        '<rect x="32" y="32" width="1216" height="656" rx="18" '
        'fill="#1c1c1c" stroke="#333333" stroke-width="3"/>'
        '<line x1="640" y1="160" x2="640" y2="560" '
        'stroke="#333333" stroke-width="2"/>'
        '<line x1="440" y1="360" x2="840" y2="360" '
        'stroke="#333333" stroke-width="2"/>'
        '<circle cx="640" cy="360" r="92" fill="none" '
        'stroke="#34d399" stroke-width="3"/>'
        '<circle cx="640" cy="360" r="7" fill="#34d399"/>'
        '<text x="640" y="610" text-anchor="middle" '
        'font-family="monospace" font-size="31" fill="#e5e5e5">'
        + title +
        '</text>'
        '<text x="640" y="650" text-anchor="middle" '
        'font-family="monospace" font-size="20" fill="#8c8c8c">'
        + subtitle +
        '</text>'
        '</svg>'
    )

    return body.encode("utf-8")


MODE_MAP = {
    "dev": "DEV",
    "development": "DEV",
    "damping": "DAMPING",
    "zero_torque": "ZERO TORQUE",
    "zero-torque": "ZERO TORQUE",
    "zerotorque": "ZERO TORQUE",
    "walk": "WALK",
    "run": "RUN",
    "climb": "CLIMB",
}


class Handler(BaseHTTPRequestHandler):

    server_version = "CameraPoseTeleopUIDev/1.0"

    def log_message(self, fmt, *args):
        print("[UI-DEV]", fmt % args)

    def send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")

        self.send_response(status)
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
        self.wfile.write(body)

    def send_svg(self, title, subtitle):
        body = svg_frame(title, subtitle)

        self.send_response(200)
        self.send_header(
            "Content-Type",
            "image/svg+xml; charset=utf-8",
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
        self.wfile.write(body)

    def serve_frontend(self, filename):
        path = FRONTEND_ROOT / filename

        if not path.is_file():
            self.send_error(404)
            return

        body = path.read_bytes()

        content_type = (
            mimetypes.guess_type(str(path))[0]
            or "application/octet-stream"
        )

        self.send_response(200)
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
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ("/", "/index.html"):
            self.serve_frontend("index.html")
            return

        static_map = {
            "/app.js": "app.js",
            "/style.css": "style.css",
            "/reference_video_skin.css":
                "reference_video_skin.css",
            "/reference_video_skin.js":
                "reference_video_skin.js",
        }

        if path in static_map:
            self.serve_frontend(static_map[path])
            return

        if path == "/api/health":
            self.send_json({
                "ok": True,
                "service":
                    "camera_pose_teleop_ui_dev_mock",
                "version": "1.0",
                "ui_dev_mock": True,
            })
            return

        if path == "/api/status":
            self.send_json(snapshot())
            return

        if path == "/api/events":
            with LOCK:
                events = list(STATE["events"])

            self.send_json({
                "events": events,
            })
            return

        if path == "/api/logs":
            with LOCK:
                logs = list(STATE["logs"])

            self.send_json({
                "logs": logs,
            })
            return

        if path == "/api/logs/terminal":
            self.send_json(
                terminal_snapshot()
            )
            return

        if path == "/api/robot/connectivity":
            self.send_json({
                "connected": True,
                "reachable": True,
                "ok": True,
                "host": "UI-DEV-MOCK",
                "port": 0,
                "latency_ms": 0.0,
                "error": None,
                "mock": True,
            })
            return

        if path == "/api/robot/modes/status":
            with LOCK:
                mode = STATE["robot_mode"]

            self.send_json({
                "ok": True,
                "display_mode": mode,
                "mode": mode,
                "source": "ui_dev_mock",
                "mock": True,
            })
            return

        frames = {
            "/api/camera/frame.jpg":
                ("KEYPOINT CAMERA", "UI DEV STATIC FRAME"),

            "/api/camera/keypoints.jpg":
                ("KEYPOINT CAMERA", "UI DEV STATIC FRAME"),

            "/api/camera/raw.jpg":
                ("RAW CAMERA", "UI DEV STATIC FRAME"),

            "/api/mujoco/frame.jpg":
                ("SIMULATION", "UI DEV STATIC FRAME"),

            "/api/mujoco/stream.mjpg":
                ("SIMULATION", "UI DEV STATIC FRAME"),

            "/api/robot-camera/frame.jpg":
                ("ROBOT CAMERA", "UI DEV STATIC FRAME"),

            "/api/robot-camera/stream.mjpg":
                ("ROBOT CAMERA", "UI DEV STATIC FRAME"),
        }

        if path in frames:
            title, subtitle = frames[path]
            self.send_svg(title, subtitle)
            return

        self.send_error(404)

    def read_json(self):
        try:
            length = int(
                self.headers.get(
                    "Content-Length",
                    "0",
                )
            )
        except ValueError:
            length = 0

        if length <= 0:
            return {}

        raw = self.rfile.read(
            min(length, 65536)
        )

        try:
            return json.loads(
                raw.decode("utf-8")
            )
        except Exception:
            return {}

    def do_POST(self):
        path = urlparse(self.path).path
        payload = self.read_json()

        if path == "/api/mujoco/camera":
            self.send_json({
                "ok": True,
                "mock": True,
                "command": payload,
            })
            return

        if path == "/api/system/sim/start":
            with LOCK:
                STATE["simulation"] = True
                STATE["physical_state"] = "off"
                STATE["physical_active"] = False
                STATE["physical_live"] = False

            add_event("Mock simulation stack started.")
            add_log("UI DEV: simulation -> RUNNING")

            self.send_json({
                "ok": True,
                "state": "running",
                "mock": True,
            })
            return

        if path == "/api/system/sim/stop":
            with LOCK:
                STATE["simulation"] = False

            add_event("Mock simulation stack stopped.")
            add_log("UI DEV: simulation -> OFF")

            self.send_json({
                "ok": True,
                "state": "off",
                "mock": True,
            })
            return

        if path == "/api/system/robot/deploy":
            with LOCK:
                STATE["simulation"] = False
                STATE["physical_state"] = "ready_to_start"
                STATE["physical_active"] = True
                STATE["physical_live"] = False

            add_event(
                "Mock physical deployment reached READY."
            )
            add_log(
                "UI DEV: physical -> READY_TO_START"
            )

            self.send_json({
                "ok": True,
                "state": "ready_to_start",
                "ready_to_start": True,
                "mock": True,
            })
            return

        if path == "/api/system/robot/start":
            with LOCK:
                ready = (
                    STATE["physical_state"]
                    == "ready_to_start"
                )

                if ready:
                    STATE["physical_state"] = "running"
                    STATE["physical_active"] = True
                    STATE["physical_live"] = True

            if not ready:
                self.send_json(
                    {
                        "ok": False,
                        "error":
                            "Mock physical stack is not ready.",
                        "mock": True,
                    },
                    status=409,
                )
                return

            add_event(
                "Mock physical stack entered ROBOT LIVE."
            )
            add_log(
                "UI DEV: physical -> ROBOT LIVE"
            )

            self.send_json({
                "ok": True,
                "state": "running",
                "live": True,
                "mock": True,
            })
            return

        if path == "/api/system/robot/stop":
            with LOCK:
                STATE["physical_state"] = "off"
                STATE["physical_active"] = False
                STATE["physical_live"] = False

            add_event(
                "Mock physical stack stopped."
            )
            add_log(
                "UI DEV: physical -> OFF"
            )

            self.send_json({
                "ok": True,
                "state": "off",
                "mock": True,
            })
            return

        if path == "/api/teleop/start":
            with LOCK:
                STATE["teleop"] = True

            add_event("Mock V2 process started.")
            add_log("UI DEV: V2 -> RUNNING")

            self.send_json({
                "ok": True,
                "pid": 42420,
                "mock": True,
            })
            return

        if path == "/api/teleop/stop":
            with LOCK:
                already = not STATE["teleop"]
                STATE["teleop"] = False

            add_event("Mock V2 process stopped.")
            add_log("UI DEV: V2 -> OFF")

            self.send_json({
                "ok": True,
                "already_stopped": already,
                "signals":
                    [] if already else ["SIGINT"],
                "mock": True,
            })
            return

        if path.startswith("/api/robot/modes/"):
            action = unquote(
                path.rsplit("/", 1)[-1]
            ).strip().lower()

            mode = MODE_MAP.get(action)

            if mode is None:
                self.send_json(
                    {
                        "ok": False,
                        "error":
                            f"Unknown mock mode: {action}",
                        "mock": True,
                    },
                    status=404,
                )
                return

            with LOCK:
                physical_active = STATE[
                    "physical_active"
                ]

            if physical_active:
                self.send_json(
                    {
                        "ok": False,
                        "error":
                            (
                                "Mock safety interlock: "
                                "stop the physical stack "
                                "before changing robot mode."
                            ),
                        "mock": True,
                    },
                    status=409,
                )
                return

            with LOCK:
                STATE["robot_mode"] = mode

            add_event(
                f"Mock robot mode changed to {mode}."
            )
            add_log(
                f"UI DEV: mode -> {mode}"
            )

            self.send_json({
                "ok": True,
                "requested_mode": mode,
                "display_mode": mode,
                "mock": True,
            })
            return

        if path == "/api/sonic/sim/start":
            with LOCK:
                STATE["simulation"] = True

            self.send_json({
                "ok": True,
                "mock": True,
            })
            return

        if path == "/api/sonic/sim/policy":
            self.send_json({
                "ok": True,
                "mock": True,
            })
            return

        if path == "/api/sonic/sim/stop":
            with LOCK:
                STATE["simulation"] = False

            self.send_json({
                "ok": True,
                "mock": True,
            })
            return

        self.send_json(
            {
                "ok": False,
                "error":
                    "Unknown UI-dev POST endpoint.",
                "mock": True,
            },
            status=404,
        )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Camera Pose Teleop dashboard "
            "UI-only development server."
        )
    )

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

    add_event(
        "UI development mock server started."
    )

    add_log(
        "UI DEV MODE: no robot, camera, SONIC, "
        "GVHMR, ROS or SSH connections."
    )

    server = ThreadingHTTPServer(
        (args.host, args.port),
        Handler,
    )

    print()
    print(
        "============================================================"
    )
    print(
        " CAMERA POSE TELEOP — UI DEVELOPMENT MOCK"
    )
    print(
        "============================================================"
    )
    print(
        " NO ROBOT CONNECTIONS"
    )
    print(
        " NO CAMERA ACCESS"
    )
    print(
        " NO SONIC / GVHMR / ROS / UNITREE SDK"
    )
    print()
    print(
        f" http://{args.host}:{args.port}"
    )
    print(
        "============================================================"
    )
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
