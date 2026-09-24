#!/usr/bin/env python3

from __future__ import annotations

from collections import deque
import copy
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
from typing import Optional


class SupervisorError(RuntimeError):
    pass


class V2Supervisor:
    """
    Owns exactly one Camera Pose Teleop V2 process group.

    Production launch:
        bash camera_pose_teleop/scripts/run_pose.sh dual

    The launch is placed in its own POSIX session/process group so
    Stop V2 can signal the complete tree, including the wrapper,
    tee and FFmpeg descendants.

    This class does not modify the V2 perception/control source.
    """

    def __init__(
        self,
        repo_root: Path,
        *,
        command_override=None,
    ):
        self.repo_root = Path(
            repo_root
        ).expanduser().resolve()

        self.run_pose = (
            self.repo_root
            / "camera_pose_teleop"
            / "scripts"
            / "run_pose.sh"
        )

        self.command_override = (
            None
            if command_override is None
            else list(command_override)
        )

        self.runtime_root = (
            self.repo_root
            / "camera_pose_teleop"
            / "dashboard_demo_v2"
            / ".runtime"
        )

        self.run_logs_root = (
            self.runtime_root
            / "v2_runs"
        )

        self.run_logs_root.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._lock = threading.RLock()

        self._proc: Optional[
            subprocess.Popen
        ] = None

        self._reader_thread = None

        self._run_log_handle = None
        self._run_log_path = None

        self._stop_requested = False
        self._fatal_seen = False

        self._logs = deque(
            maxlen=1500
        )

        self._events = deque(
            maxlen=300
        )

        self._state = (
            self._fresh_state()
        )

        self._restore_latest_run_log()

        self._event(
            "info",
            "V2 supervisor initialized.",
        )

    @staticmethod
    def _fresh_state():
        return {
            "mode": "v2",
            "teleop": {
                "state": "off",

                # process_alive means the launch process group
                # currently exists.
                #
                # running means REAL V2 teleoperation has
                # reached the active Protocol V3 publisher.
                "process_alive": False,
                "running": False,

                "pid": None,
                "pgid": None,
                "started_at": None,
                "last_exit_code": None,
                "last_error": None,
                "last_run_log": None,
            },
            "camera": {
                "state": "off",
                "device": None,
                "profile": None,
            },
            "gvhmr": {
                "state": "off",
                "history_frames": 0,
                "history_required": 30,
            },
            "framing": {
                "state": "waiting",
                "good_streak": 0,
                "required_streak": 0,
            },
            "alignment": {
                "state": "waiting",
                "valid_frames": 0,
                "candidate_frames": 0,
                "confidence": None,
                "angular_spread_deg": None,
            },
            "sonic_bridge": {
                "state": "off",
            },
            "publisher": {
                "state": "off",
                "pose_hz": None,
            },
            "simulation": {
                "mujoco": "off",
                "sonic": "off",
            },
        }

    def _restore_latest_run_log(
        self,
    ):
        logs = sorted(
            self.run_logs_root.glob(
                "v2_*.log"
            ),
            key=lambda p: (
                p.stat().st_mtime
            ),
        )

        if not logs:
            return

        latest = logs[-1]

        try:
            lines = latest.read_text(
                errors="replace"
            ).splitlines()

        except Exception:
            return

        for line in lines[-1500:]:
            self._logs.append(
                {
                    "time": "--:--:--",
                    "line": line,
                }
            )

        self._state[
            "teleop"
        ][
            "last_run_log"
        ] = str(latest)


    def _event(
        self,
        level: str,
        message: str,
    ):
        item = {
            "time": time.strftime(
                "%H:%M:%S"
            ),
            "level": str(level),
            "message": str(message),
        }

        with self._lock:
            self._events.append(
                item
            )

    def _append_log(
        self,
        line: str,
    ):
        rendered = str(line)

        with self._lock:
            self._logs.append(
                {
                    "time":
                        time.strftime(
                            "%H:%M:%S"
                        ),
                    "line":
                        rendered,
                }
            )

            handle = (
                self._run_log_handle
            )

            if handle is not None:
                try:
                    handle.write(
                        rendered + "\n"
                    )
                    handle.flush()

                except Exception:
                    pass

    def _set(
        self,
        section: str,
        key: str,
        value,
    ) -> bool:
        with self._lock:
            old = (
                self._state[
                    section
                ].get(key)
            )

            self._state[
                section
            ][key] = value

        return old != value

    def _transition(
        self,
        section: str,
        key: str,
        value,
        *,
        message=None,
        level="info",
    ):
        changed = self._set(
            section,
            key,
            value,
        )

        if (
            changed
            and message is not None
        ):
            self._event(
                level,
                message,
            )

    def snapshot_state(
        self,
    ):
        with self._lock:
            state = copy.deepcopy(
                self._state
            )

            proc = self._proc

        if (
            proc is not None
            and proc.poll() is None
        ):
            state[
                "teleop"
            ]["process_alive"] = True

        return state

    def snapshot_events(
        self,
    ):
        with self._lock:
            return copy.deepcopy(
                list(self._events)
            )

    def snapshot_logs(
        self,
    ):
        with self._lock:
            return copy.deepcopy(
                list(self._logs)
            )

    def is_running(
        self,
    ) -> bool:
        with self._lock:
            proc = self._proc

        return (
            proc is not None
            and proc.poll() is None
        )

    def _mark_fatal(
        self,
        message: str,
    ):
        with self._lock:
            self._fatal_seen = True

            self._state[
                "teleop"
            ][
                "last_error"
            ] = message

        self._event(
            "error",
            message,
        )

    def _parse_runtime_line(
        self,
        line: str,
    ):
        text = line.strip()

        if not text:
            return

        lower = text.lower()

        if text.startswith(
            "camera:"
        ):
            device = (
                text.split(
                    ":",
                    1,
                )[1].strip()
            )

            if device:
                self._set(
                    "camera",
                    "device",
                    device,
                )

        if text.startswith(
            "capture profile:"
        ):
            profile = (
                text.split(
                    ":",
                    1,
                )[1].strip()
            )

            if profile:
                self._set(
                    "camera",
                    "profile",
                    profile,
                )

        if (
            "camera open"
            in lower
            and
            "stand neutral"
            in lower
        ):
            self._transition(
                "camera",
                "state",
                "starting",
                message=(
                    "Camera opening."
                ),
            )

        if (
            "camera negotiated:"
            in lower
        ):
            self._transition(
                "camera",
                "state",
                "ready",
                message=(
                    "Camera stream ready."
                ),
            )

        if (
            "gpu components loaded: pass"
            in lower
        ):
            self._transition(
                "gvhmr",
                "state",
                "ready",
                message=(
                    "GPU perception components ready."
                ),
            )

        if (
            "full-body framing check: enabled"
            in lower
        ):
            self._transition(
                "framing",
                "state",
                "waiting",
                message=(
                    "V2 full-body framing gate enabled."
                ),
            )

        if (
            "full-body framing: not ready"
            in lower
        ):
            self._transition(
                "framing",
                "state",
                "waiting",
            )

        match = re.search(
            r"Stable observations:\s*"
            r"(\d+)\s*/\s*(\d+)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            self._set(
                "framing",
                "good_streak",
                int(match.group(1)),
            )

            self._set(
                "framing",
                "required_streak",
                int(match.group(2)),
            )

        if (
            "full-body framing: stable"
            in lower
        ):
            self._transition(
                "framing",
                "state",
                "stable",
                message=(
                    "Full-body framing stable; "
                    "building fresh causal history."
                ),
            )

        match = re.search(
            r"prefill\s+(\d+)\s*/\s*(\d+)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            self._set(
                "gvhmr",
                "history_frames",
                int(match.group(1)),
            )

            self._set(
                "gvhmr",
                "history_required",
                int(match.group(2)),
            )

            self._transition(
                "gvhmr",
                "state",
                "building_history",
            )

        if (
            "full-body framing: pass"
            in lower
        ):
            self._transition(
                "framing",
                "state",
                "ready",
                message=(
                    "Full-body framing gate passed."
                ),
            )

        if (
            "warming temporal gvhmr"
            in lower
        ):
            self._transition(
                "gvhmr",
                "state",
                "warming",
                message=(
                    "Temporal GVHMR warmup started."
                ),
            )

        if (
            lower.startswith(
                "temporal warmup:"
            )
        ):
            self._transition(
                "gvhmr",
                "state",
                "ready",
                message=(
                    "Temporal GVHMR ready."
                ),
            )

        if (
            "camera pose teleop v2"
            in lower
            and
            "neutral alignment"
            in lower
        ):
            self._transition(
                "alignment",
                "state",
                "collecting",
                message=(
                    "Neutral session alignment collecting."
                ),
            )

            self._transition(
                "teleop",
                "state",
                "aligning",
            )

        match = re.search(
            r"Valid frames:\s*(\d+)"
            r"(?:\s*/\s*(\d+))?",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            self._set(
                "alignment",
                "valid_frames",
                int(match.group(1)),
            )

            if (
                match.group(2)
                is not None
            ):
                self._set(
                    "alignment",
                    "candidate_frames",
                    int(match.group(2)),
                )

        match = re.search(
            r"Angular spread:\s*"
            r"([0-9.]+)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            self._set(
                "alignment",
                "angular_spread_deg",
                float(match.group(1)),
            )

        match = re.search(
            r"Confidence:\s*"
            r"([0-9.]+)",
            text,
            flags=re.IGNORECASE,
        )

        if match:
            self._set(
                "alignment",
                "confidence",
                float(match.group(1)),
            )

        if (
            "camera alignment passed"
            in lower
        ):
            self._transition(
                "alignment",
                "state",
                "ready",
                message=(
                    "V2 session alignment passed."
                ),
            )

            self._transition(
                "teleop",
                "state",
                "ready",
            )

        if (
            "camera alignment failed"
            in lower
        ):
            self._transition(
                "alignment",
                "state",
                "failed",
                message=(
                    "V2 session alignment failed."
                ),
                level="error",
            )

            self._mark_fatal(
                "V2 session alignment failed."
            )

        if (
            "sonic bridge: not created"
            in lower
        ):
            self._transition(
                "sonic_bridge",
                "state",
                "off",
            )

        if (
            "publisher: not created"
            in lower
        ):
            self._transition(
                "publisher",
                "state",
                "off",
            )

        if (
            "sonic bridge: created"
            in lower
        ):
            self._transition(
                "sonic_bridge",
                "state",
                "ready",
                message=(
                    "SONIC bridge created."
                ),
            )

        if (
            "protocol-v3 publisher worker bound"
            in lower
        ):
            self._transition(
                "publisher",
                "state",
                "active",
                message=(
                    "Protocol V3 pose publisher active."
                ),
            )

            self._transition(
                "teleop",
                "state",
                "running",
                message=(
                    "Camera Pose Teleop V2 is running."
                ),
            )

            self._set(
                "teleop",
                "running",
                True,
            )

        fatal_markers = (
            "traceback (most recent call last)",
            "sonic async worker error",
            "sonic async worker failed",
            "environment incomplete.",
            "camera auto-selection failed.",
            "missing camera device:",
        )

        if any(
            marker in lower
            for marker in fatal_markers
        ):
            self._mark_fatal(
                text
            )

    def _reader_loop(
        self,
        proc,
    ):
        try:
            stdout = proc.stdout

            if stdout is None:
                self._mark_fatal(
                    "V2 process stdout is unavailable."
                )
                return

            for raw in stdout:
                line = raw.rstrip(
                    "\r\n"
                )

                self._append_log(
                    line
                )

                self._parse_runtime_line(
                    line
                )

        except Exception as exc:
            self._mark_fatal(
                "Supervisor log-reader failure: "
                + repr(exc)
            )

        finally:
            try:
                rc = proc.wait()
            except Exception:
                rc = proc.poll()

            self._on_process_exit(
                proc,
                rc,
            )

    def _on_process_exit(
        self,
        proc,
        rc,
    ):
        with self._lock:
            if (
                self._proc
                is not proc
            ):
                return

            stopped = bool(
                self._stop_requested
            )

            fatal = bool(
                self._fatal_seen
            )

            self._proc = None

            self._state[
                "teleop"
            ][
                "process_alive"
            ] = False

            self._state[
                "teleop"
            ][
                "running"
            ] = False

            self._state[
                "teleop"
            ][
                "pid"
            ] = None

            self._state[
                "teleop"
            ][
                "pgid"
            ] = None

            self._state[
                "teleop"
            ][
                "last_exit_code"
            ] = rc

            self._state[
                "camera"
            ][
                "state"
            ] = "off"

            self._state[
                "gvhmr"
            ][
                "state"
            ] = "off"

            self._state[
                "sonic_bridge"
            ][
                "state"
            ] = "off"

            self._state[
                "publisher"
            ][
                "state"
            ] = "off"

            if stopped:
                self._state[
                    "teleop"
                ][
                    "state"
                ] = "off"

            elif (
                fatal
                or
                rc not in (
                    0,
                    None,
                )
            ):
                self._state[
                    "teleop"
                ][
                    "state"
                ] = "error"

                if (
                    self._state[
                        "teleop"
                    ][
                        "last_error"
                    ]
                    is None
                ):
                    self._state[
                        "teleop"
                    ][
                        "last_error"
                    ] = (
                        "V2 process exited "
                        f"with code {rc}."
                    )

            else:
                self._state[
                    "teleop"
                ][
                    "state"
                ] = "off"

        with self._lock:
            handle = (
                self._run_log_handle
            )

            self._run_log_handle = None
            self._run_log_path = None

        if handle is not None:
            try:
                handle.close()
            except Exception:
                pass

        if stopped:
            self._event(
                "info",
                "V2 process group stopped.",
            )
        elif (
            fatal
            or
            rc not in (
                0,
                None,
            )
        ):
            self._event(
                "error",
                f"V2 process exited with code {rc}.",
            )
        else:
            self._event(
                "info",
                "V2 process exited.",
            )

    def start(
        self,
    ):
        with self._lock:
            if (
                self._proc is not None
                and
                self._proc.poll()
                is None
            ):
                return {
                    "ok": False,
                    "error":
                        "V2 is already running.",
                }

            preserved_exit = (
                self._state[
                    "teleop"
                ][
                    "last_exit_code"
                ]
            )

            self._state = (
                self._fresh_state()
            )

            self._state[
                "teleop"
            ][
                "last_exit_code"
            ] = preserved_exit

            self._state[
                "teleop"
            ][
                "state"
            ] = "starting"

            self._state[
                "camera"
            ][
                "state"
            ] = "starting"

            self._state[
                "gvhmr"
            ][
                "state"
            ] = "loading"

            self._logs.clear()

            self._stop_requested = False
            self._fatal_seen = False

        if (
            self.command_override
            is None
        ):
            if not self.run_pose.is_file():
                message = (
                    "V2 launcher missing: "
                    + str(self.run_pose)
                )

                self._mark_fatal(
                    message
                )

                self._transition(
                    "teleop",
                    "state",
                    "error",
                )

                return {
                    "ok": False,
                    "error": message,
                }

            command = [
                "bash",
                str(self.run_pose),
                "dual",
            ]

        else:
            command = list(
                self.command_override
            )

        env = os.environ.copy()

        run_stamp = time.strftime(
            "%Y%m%d_%H%M%S"
        )

        run_log_path = (
            self.run_logs_root
            / f"v2_{run_stamp}.log"
        )

        try:
            run_log_handle = (
                run_log_path.open(
                    "w",
                    encoding="utf-8",
                    buffering=1,
                )
            )

        except Exception as exc:
            message = (
                "Could not create persistent "
                "V2 run log: "
                + repr(exc)
            )

            self._mark_fatal(
                message
            )

            self._transition(
                "teleop",
                "state",
                "error",
            )

            return {
                "ok": False,
                "error": message,
            }

        with self._lock:
            self._run_log_handle = (
                run_log_handle
            )

            self._run_log_path = (
                run_log_path
            )

            self._state[
                "teleop"
            ][
                "last_run_log"
            ] = str(
                run_log_path
            )

        env[
            "CAMERA_ALIGNMENT_MODE"
        ] = "session_v2"

        env[
            "SONIC_EMA_WEIGHT"
        ] = "0.0"

        env[
            "PYTHONUNBUFFERED"
        ] = "1"

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(
                    self.repo_root
                ),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                start_new_session=True,
            )

            pgid = os.getpgid(
                proc.pid
            )

        except Exception as exc:
            try:
                run_log_handle.close()
            except Exception:
                pass

            with self._lock:
                self._run_log_handle = None
                self._run_log_path = None

            message = (
                "Could not start V2: "
                + repr(exc)
            )

            self._mark_fatal(
                message
            )

            self._transition(
                "teleop",
                "state",
                "error",
            )

            return {
                "ok": False,
                "error": message,
            }

        with self._lock:
            self._proc = proc

            self._state[
                "teleop"
            ][
                "process_alive"
            ] = True

            self._state[
                "teleop"
            ][
                "running"
            ] = False

            self._state[
                "teleop"
            ][
                "pid"
            ] = int(proc.pid)

            self._state[
                "teleop"
            ][
                "pgid"
            ] = int(pgid)

            self._state[
                "teleop"
            ][
                "started_at"
            ] = time.strftime(
                "%Y-%m-%d %H:%M:%S"
            )

        self._event(
            "info",
            (
                "Starting V2 process group "
                f"PID={proc.pid} PGID={pgid}."
            ),
        )

        reader = threading.Thread(
            target=self._reader_loop,
            args=(proc,),
            name="v2-dashboard-log-reader",
            daemon=True,
        )

        with self._lock:
            self._reader_thread = (
                reader
            )

        reader.start()

        return {
            "ok": True,
            "pid": int(proc.pid),
            "pgid": int(pgid),
        }

    @staticmethod
    def _group_exists(
        pgid: int,
    ) -> bool:
        try:
            os.killpg(
                pgid,
                0,
            )
            return True

        except ProcessLookupError:
            return False

        except PermissionError:
            return True

    @staticmethod
    def _signal_group(
        pgid: int,
        sig,
    ):
        try:
            os.killpg(
                pgid,
                sig,
            )
            return True

        except ProcessLookupError:
            return False

    def stop(
        self,
        *,
        reason="dashboard_stop",
    ):
        with self._lock:
            proc = self._proc

            if (
                proc is None
                or
                proc.poll()
                is not None
            ):
                self._state[
                    "teleop"
                ][
                    "process_alive"
                ] = False

                self._state[
                    "teleop"
                ][
                    "running"
                ] = False

                if (
                    self._state[
                        "teleop"
                    ][
                        "state"
                    ]
                    != "error"
                ):
                    self._state[
                        "teleop"
                    ][
                        "state"
                    ] = "off"

                return {
                    "ok": True,
                    "already_stopped": True,
                }

            pgid = (
                self._state[
                    "teleop"
                ][
                    "pgid"
                ]
            )

            self._stop_requested = True

            self._state[
                "teleop"
            ][
                "state"
            ] = "stopping"

        self._event(
            "info",
            (
                "Stopping V2 process group "
                f"PGID={pgid} reason={reason}."
            ),
        )

        escalation = []

        if pgid is not None:
            if self._signal_group(
                int(pgid),
                signal.SIGINT,
            ):
                escalation.append(
                    "SIGINT"
                )

        try:
            proc.wait(
                timeout=8.0
            )

        except subprocess.TimeoutExpired:
            if (
                pgid is not None
                and
                self._group_exists(
                    int(pgid)
                )
            ):
                self._signal_group(
                    int(pgid),
                    signal.SIGTERM,
                )

                escalation.append(
                    "SIGTERM"
                )

            try:
                proc.wait(
                    timeout=4.0
                )

            except subprocess.TimeoutExpired:
                if (
                    pgid is not None
                    and
                    self._group_exists(
                        int(pgid)
                    )
                ):
                    self._signal_group(
                        int(pgid),
                        signal.SIGKILL,
                    )

                    escalation.append(
                        "SIGKILL"
                    )

                try:
                    proc.wait(
                        timeout=2.0
                    )
                except subprocess.TimeoutExpired:
                    pass

        if (
            pgid is not None
            and
            self._group_exists(
                int(pgid)
            )
        ):
            self._signal_group(
                int(pgid),
                signal.SIGKILL,
            )

            if (
                "SIGKILL"
                not in escalation
            ):
                escalation.append(
                    "SIGKILL"
                )

        self._on_process_exit(
            proc,
            proc.poll(),
        )

        with self._lock:
            reader = (
                self._reader_thread
            )

        if (
            reader is not None
            and
            reader is not threading.current_thread()
        ):
            reader.join(
                timeout=2.0
            )

        return {
            "ok": True,
            "already_stopped": False,
            "signals": escalation,
        }
