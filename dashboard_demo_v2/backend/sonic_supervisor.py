"""
Dashboard-owned SONIC simulation supervisor.

Important boundaries
--------------------
This class owns only the PC simulation SONIC process.

It NEVER:
- launches real-robot SONIC;
- chooses a physical network interface;
- modifies GR00T source;
- modifies SONIC policy/config;
- silently toggles Enter;
- silently sends policy-control or damping commands.

The dashboard calls explicit methods, and every state-changing
keyboard action is gated against the parsed state.

Process model
-------------
SONIC requires a real terminal because its input layer uses termios
and non-canonical stdin. Therefore the process is owned through a PTY,
not subprocess.PIPE.

Known SONIC controls:
    ]       request policy CONTROL
    ENTER   toggle reference <-> live ZMQ
    O       graceful controller stop / damping

ENTER is a toggle and must never be sent blindly.
"""

from collections import deque
from pathlib import Path
import errno
import json
import os
import pty
import re
import select
import signal
import subprocess
import threading
import time


class SonicSupervisor:
    """
    Own exactly one SONIC *simulation* process.

    Semantic state:
        off
        starting
        init_done
        policy_requested
        reference
        live
        damping_requested
        stopped
        exited
        error

    `reference` and `live` are only asserted from SONIC output.
    """

    # D6F_SIM_AUTOSTART
    #
    # deploy.sh has an interactive confirmation before it
    # starts g1_deploy_onnx_ref. This supervisor is SIM-only,
    # so that launcher confirmation may be accepted
    # automatically.
    #
    # This is NOT the same as ENTER inside SONIC.
    SIM_DEPLOY_PROMPT = (
        "Proceed with deployment? [Y/n]:"
    )

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
        "returned to reference motion at frame 0",
        "ZMQ streaming disabled, returned to reference motion",
    )

    DAMPING_MARKERS = (
        "[DEBUG] Stopping G1Deploy",
        "[InterfaceManager] EMERGENCY STOP triggered",
        "[ZMQManager] EMERGENCY STOP",
        "Stop",
    )

    EXIT_MARKERS = (
        "[DEBUG] Program exiting normally",
    )


    def __init__(
        self,
        runtime_dir,
        groot_root=None,
    ):
        self.runtime_dir = Path(
            runtime_dir
        ).expanduser().resolve()

        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        if groot_root is None:
            groot_root = (
                Path.home()
                / "GR00T-WholeBodyControl"
            )

        self.groot_root = Path(
            groot_root
        ).expanduser().resolve()

        self.deploy_root = (
            self.groot_root
            / "gear_sonic_deploy"
        )

        self.log_path = (
            self.runtime_dir
            / "sonic_sim.log"
        )

        self.pid_path = (
            self.runtime_dir
            / "sonic_sim.pid"
        )

        self._lock = threading.RLock()

        self._proc = None
        self._master_fd = None
        self._reader_thread = None
        self._wait_thread = None

        self._stop_reader = threading.Event()

        self._state = "off"

        self._launcher_confirmed = False
        self._init_done = False
        self._policy_requested = False
        self._policy_confirmed = False
        self._zmq_live = False
        self._damping_requested = False

        self._last_error = None
        self._returncode = None

        self._started_monotonic = None
        self._last_output_monotonic = None

        self._recent_lines = deque(
            maxlen=200
        )

        self._log_handle = None


    # ========================================================
    # COMMAND
    # ========================================================

    def command(self):
        """
        Exact known-good SONIC simulation launch.

        Deliberately uses the existing deploy.sh and environment
        scripts instead of reconstructing the native binary command.
        """

        deploy = str(
            self.deploy_root
        )

        sonic_env = str(
            Path.home()
            / "sonic_deploy_env.sh"
        )

        return (
            f'source "{sonic_env}" && '
            f'cd "{deploy}" && '
            'source scripts/setup_env.sh && '
            'exec bash deploy.sh '
            '--cp policy/low_latency/model '
            '--obs-config '
            'policy/low_latency/observation_config.yaml '
            '--input-type zmq '
            '--zmq-host localhost '
            'sim'
        )


    # ========================================================
    # STATE
    # ========================================================

    def _alive_locked(self):
        return (
            self._proc is not None
            and
            self._proc.poll() is None
        )


    def snapshot(self):
        with self._lock:
            alive = (
                self._alive_locked()
            )

            pid = (
                self._proc.pid
                if alive
                else None
            )

            pgid = None

            if pid is not None:
                try:
                    pgid = os.getpgid(
                        pid
                    )
                except ProcessLookupError:
                    pgid = None

            age_s = None

            if (
                self._started_monotonic
                is not None
            ):
                age_s = max(
                    0.0,
                    time.monotonic()
                    - self._started_monotonic,
                )

            output_age_s = None

            if (
                self._last_output_monotonic
                is not None
            ):
                output_age_s = max(
                    0.0,
                    time.monotonic()
                    - self._last_output_monotonic,
                )

            return {
                "state":
                    self._state,

                "process_alive":
                    alive,

                "pid":
                    pid,

                "pgid":
                    pgid,

                "launcher_confirmed":
                    self._launcher_confirmed,

                "init_done":
                    self._init_done,

                "policy_requested":
                    self._policy_requested,

                "policy_confirmed":
                    self._policy_confirmed,

                "zmq_live":
                    self._zmq_live,

                "damping_requested":
                    self._damping_requested,

                "returncode":
                    self._returncode,

                "last_error":
                    self._last_error,

                "age_s":
                    age_s,

                "output_age_s":
                    output_age_s,

                "log_path":
                    str(
                        self.log_path
                    ),

                "recent_lines":
                    list(
                        self._recent_lines
                    )[-30:],
            }


    # ========================================================
    # LOG PARSER
    # ========================================================

    @staticmethod
    def _strip_terminal_codes(
        text,
    ):
        ansi = re.compile(
            r"\x1b\[[0-?]*[ -/]*[@-~]"
        )

        return ansi.sub(
            "",
            text,
        ).replace(
            "\r",
            "",
        )


    def _consume_line(
        self,
        line,
    ):
        clean = (
            self._strip_terminal_codes(
                line
            )
            .strip()
        )

        if not clean:
            return

        now = time.monotonic()

        auto_policy = False

        with self._lock:
            self._last_output_monotonic = now

            self._recent_lines.append(
                clean
            )

            # ------------------------------------------------
            # Native controller reached WAIT_FOR_CONTROL.
            # ------------------------------------------------
            if any(
                marker in clean
                for marker in self.INIT_MARKERS
            ):
                self._init_done = True

                if (
                    not self._zmq_live
                    and
                    not self._damping_requested
                ):
                    self._state = "init_done"

                    if (
                        not self._policy_requested
                    ):
                        auto_policy = True


            # ------------------------------------------------
            # Exact source-level confirmation that ] was
            # consumed and ProgramState became CONTROL.
            #
            # ZMQ streaming is still OFF at this point, so
            # CONTROL == loaded-reference operation.
            # ------------------------------------------------
            if any(
                marker in clean
                for marker
                in self.CONTROL_MARKERS
            ):
                self._init_done = True
                self._policy_requested = True
                self._policy_confirmed = True

                self._zmq_live = False

                self._state = "reference"


            # ------------------------------------------------
            # ENTER -> live ZMQ
            # ------------------------------------------------
            if any(
                marker in clean
                for marker in self.LIVE_MARKERS
            ):
                self._init_done = True
                self._policy_requested = True
                self._policy_confirmed = True

                self._zmq_live = True
                self._state = "live"


            # ------------------------------------------------
            # ENTER -> loaded reference, or safety reset.
            # ------------------------------------------------
            if any(
                marker.lower()
                in clean.lower()
                for marker
                in self.REFERENCE_MARKERS
            ):
                self._init_done = True
                self._zmq_live = False

                if self._policy_requested:
                    self._policy_confirmed = True

                self._state = "reference"


            if any(
                marker in clean
                for marker
                in self.DAMPING_MARKERS
            ):
                if (
                    self._damping_requested
                    or
                    "EMERGENCY STOP"
                    in clean
                    or
                    "[DEBUG] Stopping G1Deploy"
                    in clean
                ):
                    self._state = (
                        "damping_requested"
                    )


            if any(
                marker in clean
                for marker
                in self.EXIT_MARKERS
            ):
                self._zmq_live = False
                self._state = "stopped"


        # ----------------------------------------------------
        # Start SONIC means:
        #
        #     launcher
        #       -> Init Done
        #       -> ]
        #       -> CONTROL / reference
        #
        # This is guarded by the exact Init Done marker.
        #
        # ENTER remains completely separate.
        # ----------------------------------------------------
        if auto_policy:
            result = (
                self.request_policy_control()
            )

            if not result.get(
                "ok"
            ):
                with self._lock:
                    if self._alive_locked():
                        self._last_error = (
                            "Failed to enter policy "
                            "control after Init Done: "
                            + str(
                                result.get(
                                    "error",
                                    "unknown error",
                                )
                            )
                        )


    def feed_test_line(
        self,
        line,
    ):
        """
        Parser-only hook used by unit tests.

        Does not launch a process.
        """
        self._consume_line(
            line
        )


    # ========================================================
    # PTY READER
    # ========================================================

    def _maybe_confirm_sim_launcher(
        self,
        buffer,
    ):
        """
        Accept deploy.sh's confirmation prompt for SIM only.

        This supervisor's command() is hard-coded to:
            --zmq-host localhost
            sim

        No physical target is supported here.

        This confirmation starts the native simulation
        controller. It never toggles live ZMQ mode.
        """

        prompt = (
            self.SIM_DEPLOY_PROMPT
            .encode(
                "utf-8"
            )
        )

        if prompt not in buffer:
            return False

        with self._lock:
            if self._launcher_confirmed:
                return False

            if not self._alive_locked():
                return False

            if self._damping_requested:
                return False


        result = self._write_key(
            b"Y\n"
        )


        if not result.get(
            "ok"
        ):
            with self._lock:
                self._last_error = (
                    "Failed to confirm simulation "
                    "deployment prompt."
                )

            return False


        with self._lock:
            self._launcher_confirmed = True

            self._recent_lines.append(
                "[dashboard] simulation "
                "deployment confirmed"
            )


        return True


    def _reader_loop(
        self,
    ):
        buffer = b""

        while (
            not self._stop_reader.is_set()
        ):
            with self._lock:
                fd = self._master_fd

            if fd is None:
                break

            try:
                ready, _, _ = select.select(
                    [fd],
                    [],
                    [],
                    0.2,
                )

                if not ready:
                    continue

                chunk = os.read(
                    fd,
                    65536,
                )

                if not chunk:
                    break

            except OSError as exc:
                if exc.errno in (
                    errno.EIO,
                    errno.EBADF,
                ):
                    break

                with self._lock:
                    self._last_error = (
                        repr(exc)
                    )
                    self._state = "error"

                break

            if self._log_handle:
                try:
                    self._log_handle.write(
                        chunk
                    )
                    self._log_handle.flush()
                except Exception:
                    pass

            buffer += chunk

            self._maybe_confirm_sim_launcher(
                buffer
            )

            while b"\n" in buffer:
                raw, buffer = (
                    buffer.split(
                        b"\n",
                        1,
                    )
                )

                self._consume_line(
                    raw.decode(
                        "utf-8",
                        errors="replace",
                    )
                )

        if buffer:
            self._consume_line(
                buffer.decode(
                    "utf-8",
                    errors="replace",
                )
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
            self._zmq_live = False

            if (
                self._state
                not in (
                    "stopped",
                    "error",
                )
            ):
                self._state = (
                    "exited"
                    if rc == 0
                    else "error"
                )

                if rc != 0:
                    self._last_error = (
                        f"SONIC exited with code {rc}"
                    )

        self._stop_reader.set()

        try:
            if self._master_fd is not None:
                os.close(
                    self._master_fd
                )
        except OSError:
            pass

        with self._lock:
            self._master_fd = None

        try:
            self.pid_path.unlink(
                missing_ok=True
            )
        except Exception:
            pass


    # ========================================================
    # PROCESS START
    # ========================================================

    def start(self):
        """
        Start SONIC simulation only.

        Does NOT send:
            ]
            ENTER
            O
        """

        with self._lock:
            if self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "SONIC is already running.",
                    "status":
                        self.snapshot(),
                }

        required = (
            self.deploy_root
            / "deploy.sh"
        )

        setup_env = (
            self.deploy_root
            / "scripts"
            / "setup_env.sh"
        )

        sonic_env = (
            Path.home()
            / "sonic_deploy_env.sh"
        )

        for path in (
            required,
            setup_env,
            sonic_env,
        ):
            if not path.exists():
                return {
                    "ok": False,
                    "error":
                        f"Missing required file: {path}",
                }

        self.log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        master_fd, slave_fd = (
            pty.openpty()
        )

        try:
            log_handle = open(
                self.log_path,
                "ab",
                buffering=0,
            )

            proc = subprocess.Popen(
                [
                    "bash",
                    "-lc",
                    self.command(),
                ],
                cwd=str(
                    self.deploy_root
                ),
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                start_new_session=True,
                close_fds=True,
            )

        except Exception:
            try:
                os.close(
                    master_fd
                )
            except OSError:
                pass

            try:
                os.close(
                    slave_fd
                )
            except OSError:
                pass

            raise

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
            self._log_handle = log_handle

            self._state = "starting"

            self._launcher_confirmed = False
            self._init_done = False
            self._policy_requested = False
            self._policy_confirmed = False
            self._zmq_live = False
            self._damping_requested = False

            self._last_error = None
            self._returncode = None

            self._started_monotonic = (
                time.monotonic()
            )

            self._last_output_monotonic = None

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
            name="sonic-pty-reader",
            daemon=True,
        )

        self._wait_thread = threading.Thread(
            target=self._wait_loop,
            name="sonic-process-wait",
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
    # PTY INPUT
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
                        "SONIC process is not alive.",
                }

            fd = self._master_fd

        if fd is None:
            return {
                "ok": False,
                "error":
                    "SONIC PTY is unavailable.",
            }

        try:
            os.write(
                fd,
                payload,
            )

        except OSError as exc:
            with self._lock:
                self._last_error = (
                    repr(exc)
                )

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


    def request_policy_control(self):
        """
        Send ] only after SONIC itself printed Init Done.

        We mark policy_requested, but do NOT claim policy CONTROL
        until a later observed state gives us evidence.
        """

        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "SONIC is not running.",
                }

            if not self._init_done:
                return {
                    "ok": False,
                    "error":
                        "SONIC has not reached Init Done.",
                }

            if self._zmq_live:
                return {
                    "ok": False,
                    "error":
                        "SONIC is already live.",
                }

            if self._damping_requested:
                return {
                    "ok": False,
                    "error":
                        "SONIC damping has been requested.",
                }

            self._policy_requested = True
            self._state = (
                "policy_requested"
            )

        return self._write_key(
            b"]"
        )


    def go_live(self):
        """
        Enter is a TOGGLE.

        Therefore send it only from a parsed, confirmed
        reference state.
        """

        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "SONIC is not running.",
                }

            if (
                self._state
                != "reference"
            ):
                return {
                    "ok": False,
                    "error":
                        "Refusing ENTER: SONIC is not "
                        "confirmed in reference mode.",
                    "state":
                        self._state,
                }

            if not self._policy_confirmed:
                return {
                    "ok": False,
                    "error":
                        "Refusing ENTER: policy control "
                        "is not confirmed.",
                }

        return self._write_key(
            b"\n"
        )


    def pause_tracking(self):
        """
        Enter is a TOGGLE.

        Therefore send it only from parsed live state.
        """

        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "SONIC is not running.",
                }

            if not self._zmq_live:
                return {
                    "ok": False,
                    "error":
                        "Refusing ENTER: SONIC is not "
                        "confirmed live.",
                    "state":
                        self._state,
                }

        return self._write_key(
            b"\n"
        )


    def request_damping(self):
        """
        Send uppercase O once.

        This is SONIC's graceful stop/damping path, not a
        stiff standing hold.
        """

        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": False,
                    "error":
                        "SONIC is not running.",
                }

            if self._damping_requested:
                return {
                    "ok": True,
                    "already_requested":
                        True,
                    "status":
                        self.snapshot(),
                }

            self._damping_requested = True
            self._state = (
                "damping_requested"
            )

        return self._write_key(
            b"O"
        )


    # ========================================================
    # PROCESS CLEANUP
    # ========================================================

    def stop_process(
        self,
        graceful_timeout_s=8.0,
    ):
        """
        Stop the dashboard-owned SONIC simulation.

        Before Init Done:
            no native controller is confirmed;
            skip O and stop the process group directly.

        After Init Done:
            request SONIC O first, then escalate only if the
            controller does not exit.
        """

        with self._lock:
            if not self._alive_locked():
                return {
                    "ok": True,
                    "already_stopped": True,
                    "status": self.snapshot(),
                }

            pid = self._proc.pid

            native_started = (
                self._init_done
            )

            need_damping = (
                native_started
                and
                not self._damping_requested
            )


        signals = []


        if need_damping:
            result = self.request_damping()

            if result.get(
                "ok"
            ):
                signals.append(
                    "O"
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
                        return {
                            "ok": True,
                            "signals": signals,
                            "status":
                                self.snapshot(),
                        }

                time.sleep(
                    0.10
                )


        try:
            pgid = os.getpgid(
                pid
            )

            os.killpg(
                pgid,
                signal.SIGINT,
            )

            signals.append(
                "SIGINT"
            )

        except ProcessLookupError:
            return {
                "ok": True,
                "signals": signals,
                "status":
                    self.snapshot(),
            }


        deadline = (
            time.monotonic()
            + 4.0
        )

        while (
            time.monotonic()
            < deadline
        ):
            with self._lock:
                if not self._alive_locked():
                    return {
                        "ok": True,
                        "signals": signals,
                        "status":
                            self.snapshot(),
                    }

            time.sleep(
                0.10
            )


        try:
            os.killpg(
                pgid,
                signal.SIGTERM,
            )

            signals.append(
                "SIGTERM"
            )

        except ProcessLookupError:
            pass


        deadline = (
            time.monotonic()
            + 2.0
        )

        while (
            time.monotonic()
            < deadline
        ):
            with self._lock:
                if not self._alive_locked():
                    return {
                        "ok": True,
                        "signals": signals,
                        "status":
                            self.snapshot(),
                    }

            time.sleep(
                0.10
            )


        try:
            os.killpg(
                pgid,
                signal.SIGKILL,
            )

            signals.append(
                "SIGKILL"
            )

        except ProcessLookupError:
            pass


        return {
            "ok": True,
            "signals": signals,
            "status":
                self.snapshot(),
        }

