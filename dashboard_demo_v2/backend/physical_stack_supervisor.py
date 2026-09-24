from __future__ import annotations

from collections import deque
from pathlib import Path
import errno
import os
import pty
import re
import select
import shlex
import signal
import subprocess
import threading
import time


ANSI_RE = re.compile(
    rb"\x1b\[[0-?]*[ -/]*[@-~]"
)


class StackCancelled(Exception):
    pass


class ValidationFailed(Exception):
    pass


class RemotePhysicalSonicSupervisor:
    """
    Own the physical SONIC process through SSH + PTY.

    Important:
      start()
        starts SONIC and waits for no operator key itself.

      request_policy_control()
        is the ONLY method allowed to send ']'.

      go_live()
        is the ONLY method allowed to send ENTER.

    ENTER remains a toggle and is guarded against parsed state.
    """

    INIT_MARKERS = (
        "Init Done",
    )

    CONTROL_MARKERS = (
        "[Control] DEBUG: "
        "operator_state.start=true, "
        "transitioning to CONTROL state",
    )

    LIVE_MARKERS = (
        "ZMQ STREAMING MODE: ENABLED",
    )

    REFERENCE_MARKERS = (
        "ZMQ STREAMING MODE: DISABLED",
        "ZMQ STREAMING MODE: FORCE DISABLED",
        "returned to reference motion",
        "ZMQ streaming disabled, returned to reference motion",
    )


    def __init__(
        self,
        runtime_dir,
        host="192.168.0.116",
        user="unitree",
        ssh_key=None,
        pc_pose_host="192.168.0.187",
    ):
        self.runtime_dir = Path(
            runtime_dir
        ).expanduser().resolve()

        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.host = str(
            host
        )

        self.user = str(
            user
        )

        self.pc_pose_host = str(
            pc_pose_host
        )

        if ssh_key is None:
            ssh_key = (
                Path.home()
                / ".ssh"
                / "bacalbasa_g1_dashboard_ed25519"
            )

        self.ssh_key = Path(
            ssh_key
        ).expanduser().resolve()

        self.remote_root = (
            "/home/unitree/"
            "bacalbasa_runtime/"
            "GR00T-WholeBodyControl/"
            "gear_sonic_deploy"
        )

        self.log_path = (
            self.runtime_dir
            / "physical_sonic.log"
        )

        self.pid_path = (
            self.runtime_dir
            / "physical_ssh.pid"
        )

        self._lock = threading.RLock()

        self._proc = None
        self._master_fd = None
        self._reader_thread = None
        self._wait_thread = None

        self._stop_reader = threading.Event()

        self._state = "off"

        self._init_done = False
        self._policy_requested = False
        self._policy_confirmed = False
        self._zmq_live = False

        self._last_error = None
        self._returncode = None

        self._remote_pid = None

        self._recent_lines = deque(
            maxlen=160
        )


    # ========================================================
    # COMMAND
    # ========================================================

    def ssh_base(
        self,
    ):
        return [
            "ssh",
            "-i",
            str(
                self.ssh_key
            ),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=4",
            "-o",
            "ServerAliveInterval=2",
            "-o",
            "ServerAliveCountMax=3",
            f"{self.user}@{self.host}",
        ]


    def remote_command(
        self,
    ):
        return (
            f'cd "{self.remote_root}" && '
            'source /opt/ros/humble/setup.bash && '
            'export RMW_IMPLEMENTATION=rmw_fastrtps_cpp && '
            'export ROS_LOCALHOST_ONLY=1 && '
            'export '
            'FASTRTPS_DEFAULT_PROFILES_FILE='
            '"$PWD/src/g1/g1_deploy_onnx_ref/config/fastrtps_profile.xml" && '
            'export TensorRT_ROOT=/home/unitree/TensorRT && '
            'export '
            'LD_LIBRARY_PATH='
            '"/opt/onnxruntime/lib:'
            '/usr/local/lib:'
            '/usr/local/cuda/targets/aarch64-linux/lib:'
            '/usr/local/cuda/lib64:'
            '/usr/local/cuda/lib:'
            '/usr/lib/aarch64-linux-gnu/nvidia:'
            '/home/unitree/TensorRT/lib:'
            '${LD_LIBRARY_PATH:-}" && '
            'MISSING="$(ldd ./target/release/g1_deploy_onnx_ref '
            '| grep "not found" || true)"; '
            'if [ -n "$MISSING" ]; then '
            'echo "BACALBASA_LDD_MISSING=$MISSING"; '
            'exit 126; '
            'fi; '
            'echo "BACALBASA_REMOTE_SONIC_PID=$$" && '
            'exec ./target/release/g1_deploy_onnx_ref '
            'enP8p1s0 '
            'policy/low_latency/model_decoder.onnx '
            'reference/example/ '
            '--obs-config '
            'policy/low_latency/observation_config.yaml '
            '--encoder-file '
            'policy/low_latency/model_encoder.onnx '
            '--planner-file '
            'planner/target_vel/V2/planner_sonic.onnx '
            '--input-type zmq '
            '--output-type all '
            f'--zmq-host {shlex.quote(self.pc_pose_host)} '
            '--zmq-port 5556 '
            '--zmq-topic pose'
        )


    def command(
        self,
    ):
        return (
            self.ssh_base()[:-1]
            + [
                "-tt",
                f"{self.user}@{self.host}",
                "bash",
                "-lc",
                shlex.quote(
                    self.remote_command()
                ),
            ]
        )


    # ========================================================
    # STATE
    # ========================================================

    def _alive_locked(
        self,
    ):
        return (
            self._proc is not None
            and
            self._proc.poll() is None
        )


    def snapshot(
        self,
    ):
        with self._lock:
            return {
                "state":
                    self._state,

                "process_alive":
                    self._alive_locked(),

                "init_done":
                    self._init_done,

                "policy_requested":
                    self._policy_requested,

                "policy_confirmed":
                    self._policy_confirmed,

                "zmq_live":
                    self._zmq_live,

                "remote_pid":
                    self._remote_pid,

                "last_error":
                    self._last_error,

                "returncode":
                    self._returncode,

                "recent_lines":
                    list(
                        self._recent_lines
                    ),
            }


    # ========================================================
    # SSH CHECKS
    # ========================================================

    def connectivity(
        self,
    ):
        if not self.ssh_key.exists():
            return {
                "ok": False,
                "error":
                    f"Missing SSH key: {self.ssh_key}",
            }

        try:
            result = subprocess.run(
                (
                    self.ssh_base()
                    + [
                        "true",
                    ]
                ),
                text=True,
                capture_output=True,
                timeout=6.0,
            )

        except Exception as exc:
            return {
                "ok": False,
                "error": repr(
                    exc
                ),
            }

        if result.returncode != 0:
            return {
                "ok": False,
                "error":
                    (
                        result.stderr.strip()
                        or
                        result.stdout.strip()
                        or
                        "SSH connectivity failed."
                    ),
            }

        return {
            "ok": True,
        }


    def existing_controller(
        self,
    ):
        command = (
            "ps -eo pid,args | "
            "grep '[g]1_deploy_onnx_ref' "
            "|| true"
        )

        try:
            result = subprocess.run(
                (
                    self.ssh_base()
                    + [
                        command,
                    ]
                ),
                text=True,
                capture_output=True,
                timeout=6.0,
            )

        except Exception as exc:
            return {
                "ok": False,
                "error": repr(
                    exc
                ),
            }

        if result.returncode != 0:
            return {
                "ok": False,
                "error":
                    result.stderr.strip(),
            }

        text = result.stdout.strip()

        return {
            "ok": True,
            "running": bool(
                text
            ),
            "output": text,
        }


    # ========================================================
    # OUTPUT PARSER
    # ========================================================

    def _handle_line(
        self,
        raw,
    ):
        raw = ANSI_RE.sub(
            b"",
            raw
        )

        text = (
            raw
            .decode(
                "utf-8",
                errors="replace",
            )
            .replace(
                "\r",
                "",
            )
            .strip()
        )

        if not text:
            return


        # Avoid huge persistent logs from the incoming pose
        # debug spam while still draining the PTY continuously.
        noisy = (
            "Received ZMQ message"
            in text
            or
            "total_size: 6 buffers"
            in text
        )


        if not noisy:
            with open(
                self.log_path,
                "a",
                encoding="utf-8",
            ) as handle:
                handle.write(
                    text
                    + "\n"
                )

            with self._lock:
                self._recent_lines.append(
                    text
                )


        if (
            text.startswith(
                "BACALBASA_REMOTE_SONIC_PID="
            )
        ):
            try:
                pid = int(
                    text.split(
                        "=",
                        1,
                    )[1]
                )

            except Exception:
                pid = None

            with self._lock:
                self._remote_pid = pid


        if any(
            marker in text
            for marker in self.INIT_MARKERS
        ):
            with self._lock:
                self._init_done = True

                if (
                    not self._policy_requested
                    and
                    not self._policy_confirmed
                ):
                    self._state = "init_done"


        if any(
            marker in text
            for marker in self.CONTROL_MARKERS
        ):
            with self._lock:
                self._policy_confirmed = True
                self._state = "reference"


        if any(
            marker in text
            for marker in self.LIVE_MARKERS
        ):
            with self._lock:
                self._zmq_live = True
                self._state = "live"


        if any(
            marker in text
            for marker in self.REFERENCE_MARKERS
        ):
            with self._lock:
                self._zmq_live = False

                if self._policy_confirmed:
                    self._state = "reference"


    def _reader_loop(
        self,
    ):
        buffer = b""

        while not self._stop_reader.is_set():
            with self._lock:
                fd = self._master_fd
                alive = self._alive_locked()

            if fd is None:
                break

            if not alive:
                # Drain whatever remains.
                timeout = 0.05
            else:
                timeout = 0.20

            try:
                ready, _, _ = select.select(
                    [
                        fd,
                    ],
                    [],
                    [],
                    timeout,
                )

            except (
                OSError,
                ValueError,
            ):
                break

            if not ready:
                if not alive:
                    break

                continue

            try:
                chunk = os.read(
                    fd,
                    65536,
                )

            except OSError as exc:
                if exc.errno in (
                    errno.EIO,
                    errno.EBADF,
                ):
                    break

                with self._lock:
                    self._last_error = repr(
                        exc
                    )

                break

            if not chunk:
                break

            buffer += chunk

            while b"\n" in buffer:
                line, buffer = buffer.split(
                    b"\n",
                    1,
                )

                self._handle_line(
                    line
                )

        if buffer:
            self._handle_line(
                buffer
            )


    def _wait_loop(
        self,
    ):
        with self._lock:
            proc = self._proc

        if proc is None:
            return

        rc = proc.wait()

        with self._lock:
            self._returncode = rc

            if self._state not in (
                "off",
                "stopped",
            ):
                self._state = (
                    "exited"
                    if rc == 0
                    else "error"
                )

                if (
                    rc != 0
                    and
                    not self._last_error
                ):
                    self._last_error = (
                        f"Physical SONIC SSH exited rc={rc}"
                    )


    # ========================================================
    # START
    # ========================================================

    def start(
        self,
    ):
        with self._lock:
            if self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is already running.",
                }


        check = self.connectivity()

        if not check.get(
            "ok"
        ):
            return check


        existing = self.existing_controller()

        if not existing.get(
            "ok"
        ):
            return existing

        if existing.get(
            "running"
        ):
            return {
                "ok": False,
                "error":
                    (
                        "A physical g1_deploy_onnx_ref "
                        "process is already running on the Jetson: "
                        + existing.get(
                            "output",
                            "",
                        )
                    ),
            }


        self.log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        master_fd, slave_fd = (
            pty.openpty()
        )

        try:
            proc = subprocess.Popen(
                self.command(),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )

        finally:
            try:
                os.close(
                    slave_fd
                )
            except OSError:
                pass


        with self._lock:
            self._proc = proc
            self._master_fd = master_fd

            self._state = "starting"

            self._init_done = False
            self._policy_requested = False
            self._policy_confirmed = False
            self._zmq_live = False

            self._remote_pid = None
            self._last_error = None
            self._returncode = None

            self._recent_lines.clear()
            self._stop_reader.clear()


        self.pid_path.write_text(
            str(
                proc.pid
            )
            + "\n"
        )


        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="physical-sonic-pty-reader",
            daemon=True,
        )

        self._wait_thread = threading.Thread(
            target=self._wait_loop,
            name="physical-sonic-wait",
            daemon=True,
        )

        self._reader_thread.start()
        self._wait_thread.start()


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }


    # ========================================================
    # GUARDED KEYS
    # ========================================================

    def _write_key(
        self,
        payload,
    ):
        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is not alive.",
                }

            fd = self._master_fd

        if fd is None:
            return {
                "ok": False,
                "error":
                    "Physical SONIC PTY unavailable.",
            }

        try:
            os.write(
                fd,
                payload,
            )

        except OSError as exc:
            return {
                "ok": False,
                "error":
                    f"PTY write failed: {exc}",
            }

        return {
            "ok": True,
            "status":
                self.snapshot(),
        }


    def request_policy_control(
        self,
    ):
        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is not running.",
                }

            if not self._init_done:
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC has not reached Init Done.",
                }

            if self._zmq_live:
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is already live.",
                }

            if self._policy_confirmed:
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is already in CONTROL/reference.",
                }

            self._policy_requested = True
            self._state = "policy_requested"


        return self._write_key(
            b"]"
        )


    def go_live(
        self,
    ):
        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is not running.",
                }

            if (
                self._state
                != "reference"
            ):
                return {
                    "ok": False,
                    "error":
                        (
                            "Refusing ENTER: physical SONIC "
                            "is not confirmed in reference mode."
                        ),
                    "state":
                        self._state,
                }

            if not self._policy_confirmed:
                return {
                    "ok": False,
                    "error":
                        "Refusing ENTER: CONTROL is not confirmed.",
                }


        return self._write_key(
            b"\n"
        )


    # ========================================================
    # STOP
    # ========================================================

    def _kill_owned_remote(
        self,
    ):
        with self._lock:
            pid = self._remote_pid

        if pid is None:
            return

        check = (
            f'PID={int(pid)}; '
            'if [ -r "/proc/$PID/cmdline" ]; then '
            'CMD="$(tr "\\0" " " < "/proc/$PID/cmdline")"; '
            'case "$CMD" in '
            '*g1_deploy_onnx_ref*) '
            'kill -TERM "$PID" 2>/dev/null || true ;; '
            'esac; '
            'fi'
        )

        try:
            subprocess.run(
                self.ssh_base()
                + [
                    check,
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5.0,
            )

        except Exception:
            pass


    def stop_process(
        self,
        graceful_timeout_s=8.0,
    ):
        with self._lock:
            alive = self._alive_locked()
            controlled = (
                self._policy_confirmed
                or
                self._zmq_live
            )

            proc = self._proc


        if not alive:
            with self._lock:
                self._state = "off"

            return {
                "ok": True,
                "already_stopped": True,
            }


        # Only send O if physical CONTROL had actually been
        # confirmed. At READY_TO_START we have intentionally
        # not sent ], so stopping that stage does not issue O.
        if controlled:
            self._write_key(
                b"O"
            )

            deadline = (
                time.monotonic()
                + float(
                    graceful_timeout_s
                )
            )

            while (
                time.monotonic()
                < deadline
            ):
                with self._lock:
                    if not self._alive_locked():
                        break

                time.sleep(
                    0.10
                )


        with self._lock:
            alive = self._alive_locked()


        if alive and proc is not None:
            try:
                pgid = os.getpgid(
                    proc.pid
                )

            except ProcessLookupError:
                pgid = None


            if pgid is not None:
                for sig, wait_s in (
                    (
                        signal.SIGTERM,
                        2.0,
                    ),
                    (
                        signal.SIGKILL,
                        0.5,
                    ),
                ):
                    with self._lock:
                        if not self._alive_locked():
                            break

                    try:
                        os.killpg(
                            pgid,
                            sig,
                        )

                    except ProcessLookupError:
                        break

                    deadline = (
                        time.monotonic()
                        + wait_s
                    )

                    while (
                        time.monotonic()
                        < deadline
                    ):
                        with self._lock:
                            if not self._alive_locked():
                                break

                        time.sleep(
                            0.10
                        )


        self._kill_owned_remote()


        self._stop_reader.set()

        with self._lock:
            fd = self._master_fd

        if fd is not None:
            try:
                os.close(
                    fd
                )
            except OSError:
                pass


        with self._lock:
            self._master_fd = None
            self._proc = None
            self._state = "off"

            self._init_done = False
            self._policy_requested = False
            self._policy_confirmed = False
            self._zmq_live = False


        try:
            self.pid_path.unlink(
                missing_ok=True
            )
        except Exception:
            pass


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }



class PhysicalStackSupervisor:
    """
    Two-stage physical deployment.

    DEPLOY:
        MuJoCo validation
        relay
        V2 session_v2
        validation SIM SONIC
        validation SIM -> reference
        MuJoCo key 9
        validation SIM -> live V2
        physical Jetson SONIC -> Init Done

        STOP HERE.

        Physical ] and ENTER have NOT been sent.

    START:
        physical ]
        wait confirmed CONTROL/reference
        physical ENTER
        wait confirmed live ZMQ
    """

    ACTIVE_STATES = {
        "starting_robot_camera",
        "waiting_robot_camera",
        "starting_mujoco",
        "starting_relay",
        "waiting_mujoco",
        "starting_v2",
        "waiting_v2",
        "starting_validation_sonic",
        "waiting_validation_reference",
        "releasing_mujoco",
        "validation_going_live",
        "waiting_validation_live",
        "validating_simulation",
        "validation_failed",
        "physical_init_failed",
        "starting_physical_sonic",
        "waiting_physical_init",
        "ready_to_start",
        "starting_physical_control",
        "waiting_physical_reference",
        "starting_physical_live",
        "live",
        "stopping",
    }


    def __init__(
        self,
        dashboard_root,
        repo_root,
        v2_supervisor,
        validation_sonic,
        physical_sonic,
        mujoco_preview,
        simulation_stack,
        simulation_sonic,
        robot_camera,
    ):
        self.dashboard_root = Path(
            dashboard_root
        ).resolve()

        self.repo_root = Path(
            repo_root
        ).resolve()

        self.v2 = v2_supervisor
        self.validation_sonic = validation_sonic
        self.physical_sonic = physical_sonic

        self.mujoco_preview = mujoco_preview

        self.simulation_stack = simulation_stack
        self.simulation_sonic = simulation_sonic
        self.robot_camera = robot_camera

        self.sim_python = (
            Path.home()
            / "GR00T-WholeBodyControl"
            / ".venv_sim"
            / "bin"
            / "python"
        )

        self.mujoco_script = (
            self.dashboard_root
            / "helpers"
            / "mujoco_dashboard_sim.py"
        )

        self.relay_script = (
            self.dashboard_root
            / "helpers"
            / "mujoco_image_relay.py"
        )

        self.runtime_dir = (
            self.dashboard_root
            / ".runtime"
            / "physical_stack"
        )

        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # The MuJoCo helper already watches this exact
        # simulation_stack path.
        sim_runtime = (
            self.dashboard_root
            / ".runtime"
            / "simulation_stack"
        )

        sim_runtime.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.mujoco_release_request = (
            sim_runtime
            / "mujoco_release.request"
        )

        self.mujoco_release_ack = (
            sim_runtime
            / "mujoco_release.ack"
        )

        self._lock = threading.RLock()

        self._state = "off"
        self._last_error = None
        self._started_at = None

        self._thread = None
        self._cancel = threading.Event()

        self._mujoco_proc = None
        self._relay_proc = None


    # ========================================================
    # PROCESS HELPERS
    # ========================================================

    @staticmethod
    def _alive(
        proc,
    ):
        return (
            proc is not None
            and
            proc.poll() is None
        )


    def commands(
        self,
    ):
        return {
            "mujoco": [
                str(
                    self.sim_python
                ),
                "-u",
                str(
                    self.mujoco_script
                ),
                "--interface",
                "lo",
                "--camera-port",
                "5555",
                "--control-port",
                "5611",
                "--width",
                "640",
                "--height",
                "400",
            ],

            "relay": [
                str(
                    self.sim_python
                ),
                "-u",
                str(
                    self.relay_script
                ),
                "--source-endpoint",
                "tcp://127.0.0.1:5555",
                "--output-endpoint",
                "tcp://127.0.0.1:5610",
                "--camera-name",
                "ego_view",
            ],
        }


    def _set_state(
        self,
        state,
    ):
        with self._lock:
            self._state = state


    def snapshot(
        self,
    ):
        with self._lock:
            state = self._state

            mujoco_alive = self._alive(
                self._mujoco_proc
            )

            relay_alive = self._alive(
                self._relay_proc
            )


        v2 = self.v2.snapshot_state()

        teleop = v2.get(
            "teleop",
            {}
        )

        validation = (
            self.validation_sonic
            .snapshot()
        )

        physical = (
            self.physical_sonic
            .snapshot()
        )

        robot_camera = (
            self.robot_camera
            .snapshot()
        )

        return {
            "state":
                state,

            "active":
                state
                in self.ACTIVE_STATES,

            "ready_to_start":
                state
                == "ready_to_start",

            "live":
                state
                == "live",

            "last_error":
                self._last_error,

            "started_at":
                self._started_at,

            "v2_process_alive":
                bool(
                    teleop.get(
                        "process_alive"
                    )
                ),

            "v2_ready":
                bool(
                    teleop.get(
                        "running"
                    )
                ),

            "mujoco_process_alive":
                mujoco_alive,

            "relay_process_alive":
                relay_alive,

            "mujoco_preview_live":
                bool(
                    self.mujoco_preview
                    .snapshot()
                    .get(
                        "live"
                    )
                ),

            "validation_sonic":
                validation,

            "physical_sonic":
                physical,

            "robot_camera":
                robot_camera,

            # Explicit safety contract exposed to frontend.
            "physical_policy_sent":
                bool(
                    physical.get(
                        "policy_requested"
                    )
                ),

            "physical_live":
                bool(
                    physical.get(
                        "zmq_live"
                    )
                ),
        }


    def _launch_process(
        self,
        command,
        log_name,
    ):
        log_path = (
            self.runtime_dir
            / log_name
        )

        log = open(
            log_path,
            "wb",
            buffering=0,
        )

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(
                    self.dashboard_root
                ),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
            )

        finally:
            log.close()

        return proc


    def _stop_owned_process(
        self,
        proc,
    ):
        if not self._alive(
            proc
        ):
            return

        try:
            pgid = os.getpgid(
                proc.pid
            )

        except ProcessLookupError:
            return


        for sig, wait_s in (
            (
                signal.SIGINT,
                4.0,
            ),
            (
                signal.SIGTERM,
                2.0,
            ),
            (
                signal.SIGKILL,
                0.5,
            ),
        ):
            if not self._alive(
                proc
            ):
                break

            try:
                os.killpg(
                    pgid,
                    sig,
                )

            except ProcessLookupError:
                break

            deadline = (
                time.monotonic()
                + wait_s
            )

            while (
                time.monotonic()
                < deadline
            ):
                if not self._alive(
                    proc
                ):
                    break

                time.sleep(
                    0.10
                )


    # ========================================================
    # WAITS
    # ========================================================

    def _check_cancelled(
        self,
    ):
        if self._cancel.is_set():
            raise StackCancelled()


    def _wait_until(
        self,
        predicate,
        timeout_s,
        description,
        health=None,
    ):
        deadline = (
            time.monotonic()
            + float(
                timeout_s
            )
        )

        while (
            time.monotonic()
            < deadline
        ):
            self._check_cancelled()

            if (
                health is not None
                and
                not health()
            ):
                raise RuntimeError(
                    description
                    + " process exited."
                )

            if predicate():
                return

            time.sleep(
                0.20
            )

        raise RuntimeError(
            "Timed out waiting for "
            + description
        )


    # ========================================================
    # D10E PHYSICAL VALIDATION
    # ========================================================

    def _mujoco_has_fallen(
        self,
    ):
        path = (
            self.runtime_dir
            / "mujoco.log"
        )

        if not path.exists():
            return False

        try:
            with path.open(
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
                        size - 131072,
                    )
                )

                data = handle.read()

        except Exception:
            return False


        return (
            b"Robot has fallen"
            in data
        )


    def _validate_current_simulation(
        self,
        duration_s=5.0,
    ):
        """
        Validate the CURRENT physical-preflight MuJoCo run.

        Historical log warnings are irrelevant because the
        physical stack now truncates mujoco.log at each launch.

        This gate occurs BEFORE physical SONIC starts.
        """

        deadline = (
            time.monotonic()
            + float(
                duration_s
            )
        )


        while (
            time.monotonic()
            < deadline
        ):
            self._check_cancelled()


            if not self._alive(
                self._mujoco_proc
            ):
                raise ValidationFailed(
                    "MuJoCo validation process exited."
                )


            if not self._alive(
                self._relay_proc
            ):
                raise ValidationFailed(
                    "MuJoCo preview relay exited."
                )


            validation = (
                self.validation_sonic
                .snapshot()
            )


            if not validation.get(
                "process_alive"
            ):
                raise ValidationFailed(
                    "Validation SONIC exited."
                )


            if not validation.get(
                "zmq_live"
            ):
                raise ValidationFailed(
                    "Validation SONIC lost live V2 tracking."
                )


            if self._mujoco_has_fallen():
                raise ValidationFailed(
                    "MuJoCo validation robot fell. "
                    "Physical SONIC was NOT started."
                )


            time.sleep(
                0.20
            )


    # ========================================================
    # MUJOCO 9
    # ========================================================

    def _release_mujoco_robot(
        self,
    ):
        self.mujoco_release_request.unlink(
            missing_ok=True
        )

        self.mujoco_release_ack.unlink(
            missing_ok=True
        )

        self.mujoco_release_request.write_text(
            "9\n"
        )


        self._wait_until(
            lambda:
                self.mujoco_release_ack
                .exists(),
            10.0,
            "MuJoCo key 9 release",
            health=lambda:
                self._alive(
                    self._mujoco_proc
                ),
        )


        result = (
            self.mujoco_release_ack
            .read_text()
            .strip()
        )

        self.mujoco_release_request.unlink(
            missing_ok=True
        )

        self.mujoco_release_ack.unlink(
            missing_ok=True
        )

        if result != "released":
            raise RuntimeError(
                "MuJoCo key 9 failed: "
                + result
            )


    # ========================================================
    # DEPLOY STAGE
    # ========================================================

    def deploy(
        self,
    ):
        with self._lock:
            if (
                self._state
                in self.ACTIVE_STATES
            ):
                return {
                    "ok": False,
                    "error":
                        "Physical stack is already active.",
                    "status":
                        self.snapshot(),
                }


            sim = self.simulation_stack.snapshot()

            if sim.get(
                "active"
            ):
                return {
                    "ok": False,
                    "error":
                        "Simulation stack is already active.",
                }


            if (
                self.simulation_sonic
                .snapshot()
                .get(
                    "process_alive"
                )
            ):
                return {
                    "ok": False,
                    "error":
                        "Simulation SONIC is already active.",
                }


            if (
                self.v2
                .snapshot_state()
                .get(
                    "teleop",
                    {}
                )
                .get(
                    "process_alive"
                )
            ):
                return {
                    "ok": False,
                    "error":
                        "A V2 process is already running.",
                }


            if (
                self.physical_sonic
                .snapshot()
                .get(
                    "process_alive"
                )
            ):
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is already active.",
                }


            self._last_error = None
            self._started_at = time.time()

            self._cancel.clear()
            self._state = "starting_mujoco"


            self._thread = threading.Thread(
                target=self._run_deploy,
                name="physical-stack-deploy",
                daemon=True,
            )

            self._thread.start()


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }


    def _run_deploy(
        self,
    ):
        try:
            commands = self.commands()

            # -----------------------------------------------
            # G1 ROBOT CAMERA
            #
            # CAMERA ONLY.
            # No SONIC keys and no physical control.
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "starting_robot_camera"
            )

            result = (
                self.robot_camera
                .start()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "Robot camera start failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            self._set_state(
                "waiting_robot_camera"
            )


            self._wait_until(
                lambda:
                    bool(
                        self.robot_camera
                        .snapshot()
                        .get(
                            "live"
                        )
                    ),
                20.0,
                "G1 robot camera",
                health=lambda:
                    bool(
                        self.robot_camera
                        .snapshot()
                        .get(
                            "process_alive"
                        )
                    ),
            )


            # -----------------------------------------------
            # MuJoCo
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "starting_mujoco"
            )

            self._mujoco_proc = (
                self._launch_process(
                    commands[
                        "mujoco"
                    ],
                    "mujoco.log",
                )
            )


            self._check_cancelled()

            self._set_state(
                "starting_relay"
            )

            self._relay_proc = (
                self._launch_process(
                    commands[
                        "relay"
                    ],
                    "relay.log",
                )
            )


            self._set_state(
                "waiting_mujoco"
            )

            self._wait_until(
                lambda:
                    bool(
                        self.mujoco_preview
                        .snapshot()
                        .get(
                            "live"
                        )
                    ),
                30.0,
                "MuJoCo preview",
                health=lambda:
                    (
                        self._alive(
                            self._mujoco_proc
                        )
                        and
                        self._alive(
                            self._relay_proc
                        )
                    ),
            )


            # -----------------------------------------------
            # ONE V2 publisher
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "starting_v2"
            )

            result = self.v2.start()

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "V2 start failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            self._set_state(
                "waiting_v2"
            )


            def v2_alive():
                return bool(
                    self.v2
                    .snapshot_state()
                    .get(
                        "teleop",
                        {}
                    )
                    .get(
                        "process_alive"
                    )
                )


            def v2_ready():
                return bool(
                    self.v2
                    .snapshot_state()
                    .get(
                        "teleop",
                        {}
                    )
                    .get(
                        "running"
                    )
                )


            self._wait_until(
                v2_ready,
                600.0,
                "V2 camera/alignment readiness",
                health=v2_alive,
            )


            # -----------------------------------------------
            # Validation SIM SONIC
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "starting_validation_sonic"
            )

            result = (
                self.validation_sonic
                .start()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "Validation SONIC start failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            def validation_alive():
                return bool(
                    self.validation_sonic
                    .snapshot()
                    .get(
                        "process_alive"
                    )
                )


            # SonicSupervisor may already request policy after
            # Init Done. Support both behaviours explicitly.
            self._wait_until(
                lambda:
                    (
                        self.validation_sonic
                        .snapshot()
                        .get(
                            "init_done"
                        )
                        or
                        self.validation_sonic
                        .snapshot()
                        .get(
                            "state"
                        )
                        in {
                            "init_done",
                            "policy_requested",
                            "reference",
                            "live",
                        }
                    ),
                300.0,
                "validation SONIC Init Done",
                health=validation_alive,
            )


            snap = (
                self.validation_sonic
                .snapshot()
            )

            if (
                snap.get(
                    "state"
                )
                == "init_done"
                and
                not snap.get(
                    "policy_requested"
                )
            ):
                result = (
                    self.validation_sonic
                    .request_policy_control()
                )

                if not result.get(
                    "ok"
                ):
                    raise RuntimeError(
                        "Validation SONIC ] failed: "
                        + str(
                            result.get(
                                "error",
                                "unknown error",
                            )
                        )
                    )


            self._set_state(
                "waiting_validation_reference"
            )

            self._wait_until(
                lambda:
                    (
                        self.validation_sonic
                        .snapshot()
                        .get(
                            "state"
                        )
                        == "reference"
                    ),
                300.0,
                "validation SONIC reference",
                health=validation_alive,
            )


            # Exact existing simulation order:
            #
            # validation ] -> MuJoCo 9 -> validation ENTER

            self._set_state(
                "releasing_mujoco"
            )

            self._release_mujoco_robot()


            self._set_state(
                "validation_going_live"
            )

            result = (
                self.validation_sonic
                .go_live()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "Validation SONIC ENTER failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            self._set_state(
                "waiting_validation_live"
            )

            self._wait_until(
                lambda:
                    bool(
                        self.validation_sonic
                        .snapshot()
                        .get(
                            "zmq_live"
                        )
                    ),
                30.0,
                "validation simulation live tracking",
                health=validation_alive,
            )


            # -----------------------------------------------
            # CURRENT-RUN SAFETY VALIDATION
            #
            # Keep the validation simulation live for several
            # seconds before even launching physical SONIC.
            #
            # A MuJoCo fall here means:
            #
            #     physical SONIC NOT STARTED
            #     physical ] NOT SENT
            #     physical ENTER NOT SENT
            #
            # Camera/V2/simulation remain available so the
            # operator can inspect the failure.
            # -----------------------------------------------

            self._set_state(
                "validating_simulation"
            )

            self._validate_current_simulation(
                duration_s=5.0
            )


            # -----------------------------------------------
            # Physical SONIC: INIT ONLY.
            #
            # CRITICAL SAFETY BOUNDARY:
            #
            # NO ]
            # NO ENTER
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "starting_physical_sonic"
            )

            result = (
                self.physical_sonic
                .start()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "Physical SONIC start failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            def physical_alive():
                return bool(
                    self.physical_sonic
                    .snapshot()
                    .get(
                        "process_alive"
                    )
                )


            self._set_state(
                "waiting_physical_init"
            )

            self._wait_until(
                lambda:
                    bool(
                        self.physical_sonic
                        .snapshot()
                        .get(
                            "init_done"
                        )
                    ),
                300.0,
                "physical SONIC Init Done",
                health=physical_alive,
            )


            # Prove the safety boundary before publishing READY.
            physical = (
                self.physical_sonic
                .snapshot()
            )

            if (
                physical.get(
                    "policy_requested"
                )
                or
                physical.get(
                    "policy_confirmed"
                )
                or
                physical.get(
                    "zmq_live"
                )
            ):
                raise RuntimeError(
                    "Safety invariant violated: physical "
                    "CONTROL/live was entered during Deploy."
                )


            self._set_state(
                "ready_to_start"
            )


        except StackCancelled:
            return


        except ValidationFailed as exc:
            with self._lock:
                self._last_error = str(
                    exc
                )

                self._state = (
                    "validation_failed"
                )


            # Safety invariant:
            # validation occurs before physical SONIC launch.
            #
            # Do not tear down V2 / cameras automatically.
            # The operator should be able to inspect them.
            try:
                self.physical_sonic.stop_process(
                    graceful_timeout_s=2.0
                )
            except Exception:
                pass


        except Exception as exc:
            validation = (
                self.validation_sonic
                .snapshot()
            )

            v2_alive = bool(
                self.v2
                .snapshot_state()
                .get(
                    "teleop",
                    {}
                )
                .get(
                    "process_alive"
                )
            )


            # If validation was already healthy and only the
            # PHYSICAL INIT stage failed, preserve the cameras
            # and validation simulation for diagnosis.
            if (
                validation.get(
                    "zmq_live"
                )
                and
                v2_alive
                and
                self._alive(
                    self._mujoco_proc
                )
            ):
                with self._lock:
                    self._last_error = str(
                        exc
                    )

                    self._state = (
                        "physical_init_failed"
                    )

                try:
                    self.physical_sonic.stop_process(
                        graceful_timeout_s=2.0
                    )
                except Exception:
                    pass

            else:
                with self._lock:
                    self._last_error = str(
                        exc
                    )

                    self._state = "error"

                self._cleanup()


    # ========================================================
    # START PHYSICAL CONTROL
    # ========================================================

    def start_live(
        self,
    ):
        with self._lock:
            if (
                self._state
                != "ready_to_start"
            ):
                return {
                    "ok": False,
                    "error":
                        (
                            "Physical stack is not in "
                            "READY_TO_START."
                        ),
                    "status":
                        self.snapshot(),
                }


            physical = (
                self.physical_sonic
                .snapshot()
            )

            if not physical.get(
                "init_done"
            ):
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC lost Init Done readiness.",
                }


            if physical.get(
                "policy_requested"
            ):
                return {
                    "ok": False,
                    "error":
                        "Physical ] was already requested.",
                }


            if physical.get(
                "zmq_live"
            ):
                return {
                    "ok": False,
                    "error":
                        "Physical SONIC is already live.",
                }


            self._state = (
                "starting_physical_control"
            )


            self._thread = threading.Thread(
                target=self._run_start_live,
                name="physical-stack-start-live",
                daemon=True,
            )

            self._thread.start()


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }


    def _run_start_live(
        self,
    ):
        try:
            self._check_cancelled()


            # -----------------------------------------------
            # PHYSICAL ]
            # -----------------------------------------------

            result = (
                self.physical_sonic
                .request_policy_control()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "Physical ] failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            self._set_state(
                "waiting_physical_reference"
            )


            def physical_alive():
                return bool(
                    self.physical_sonic
                    .snapshot()
                    .get(
                        "process_alive"
                    )
                )


            self._wait_until(
                lambda:
                    (
                        self.physical_sonic
                        .snapshot()
                        .get(
                            "state"
                        )
                        == "reference"
                    ),
                45.0,
                "physical CONTROL/reference confirmation",
                health=physical_alive,
            )


            # -----------------------------------------------
            # PHYSICAL ENTER
            #
            # go_live() itself refuses ENTER unless parsed
            # CONTROL/reference has been confirmed.
            # -----------------------------------------------

            self._set_state(
                "starting_physical_live"
            )

            result = (
                self.physical_sonic
                .go_live()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "Physical ENTER failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            self._wait_until(
                lambda:
                    bool(
                        self.physical_sonic
                        .snapshot()
                        .get(
                            "zmq_live"
                        )
                    ),
                30.0,
                "physical live ZMQ confirmation",
                health=physical_alive,
            )


            self._set_state(
                "live"
            )


        except StackCancelled:
            return


        except Exception as exc:
            with self._lock:
                self._last_error = str(
                    exc
                )

                self._state = "error"


    # ========================================================
    # CLEANUP
    # ========================================================

    def _cleanup(
        self,
    ):
        # Physical first.
        try:
            self.physical_sonic.stop_process(
                graceful_timeout_s=8.0
            )
        except Exception:
            pass


        # Validation simulation.
        try:
            self.validation_sonic.stop_process(
                graceful_timeout_s=8.0
            )
        except Exception:
            pass


        # V2 camera / publisher.
        try:
            self.v2.stop(
                reason="physical_stack_stop"
            )
        except Exception:
            pass


        self._stop_owned_process(
            self._relay_proc
        )

        self._relay_proc = None


        self._stop_owned_process(
            self._mujoco_proc
        )

        self._mujoco_proc = None


        # G1 camera last. Keep it visible during all earlier
        # physical/simulation shutdown operations.
        try:
            self.robot_camera.stop()
        except Exception:
            pass


    def stop(
        self,
        reason="dashboard_button",
    ):
        del reason

        self._cancel.set()


        with self._lock:
            thread = self._thread

            if (
                self._state
                == "off"
                and
                not self._alive(
                    self._mujoco_proc
                )
                and
                not self._alive(
                    self._relay_proc
                )
                and
                not self.v2
                    .snapshot_state()
                    .get(
                        "teleop",
                        {}
                    )
                    .get(
                        "process_alive"
                    )
                and
                not self.validation_sonic
                    .snapshot()
                    .get(
                        "process_alive"
                    )
                and
                not self.physical_sonic
                    .snapshot()
                    .get(
                        "process_alive"
                    )
            ):
                return {
                    "ok": True,
                    "already_stopped": True,
                    "status":
                        self.snapshot(),
                }


            self._state = "stopping"


        if (
            thread is not None
            and
            thread.is_alive()
            and
            thread
            is not threading.current_thread()
        ):
            thread.join(
                timeout=2.0
            )


        self._cleanup()


        with self._lock:
            self._state = "off"
            self._thread = None
            self._started_at = None
            self._last_error = None


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }
