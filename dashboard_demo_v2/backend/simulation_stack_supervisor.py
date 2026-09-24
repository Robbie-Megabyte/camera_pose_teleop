from pathlib import Path
import os
import signal
import subprocess
import threading
import time


class StackCancelled(Exception):
    pass


class SimulationStackSupervisor:
    """
    One-button owner for the complete simulation workflow.

    Launch order:
        MuJoCo
        relay
        V2
        SONIC -> reference
        SONIC -> live ZMQ

    Stop order:
        SONIC -> damping / stop
        V2
        relay
        MuJoCo

    This class is SIMULATION ONLY.
    """

    ACTIVE_STATES = {
        "starting_mujoco",
        "starting_relay",
        "waiting_mujoco",
        "starting_v2",
        "waiting_v2",
        "starting_sonic",
        "waiting_sonic_reference",
        "releasing_mujoco",
        "going_live",
        "running",
        "stopping",
    }


    def __init__(
        self,
        dashboard_root,
        repo_root,
        v2_supervisor,
        sonic_supervisor,
        mujoco_preview,
    ):
        self.dashboard_root = Path(
            dashboard_root
        ).resolve()

        self.repo_root = Path(
            repo_root
        ).resolve()

        self.v2 = v2_supervisor
        self.sonic = sonic_supervisor
        self.mujoco_preview = mujoco_preview

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
            / "simulation_stack"
        )

        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        # D7C_MUJOCO_RELEASE_9
        self.mujoco_release_request = (
            self.runtime_dir
            / "mujoco_release.request"
        )

        self.mujoco_release_ack = (
            self.runtime_dir
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
    # COMMAND CONTRACT
    # ========================================================

    def commands(self):
        return {
            "mujoco": [
                str(self.sim_python),
                "-u",
                str(self.mujoco_script),
                "--interface",
                "lo",
                "--camera-port",
                "5555",
                "--control-port",
                "5611",
                "--width",
                "1152",
                "--height",
                "720",
            ],

            "relay": [
                str(self.sim_python),
                "-u",
                str(self.relay_script),
                "--source-endpoint",
                "tcp://127.0.0.1:5555",
                "--output-endpoint",
                "tcp://127.0.0.1:5610",
                "--camera-name",
                "ego_view",
            ],
        }


    # ========================================================
    # STATE
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


    def _set_state(
        self,
        state,
    ):
        with self._lock:
            self._state = state


    def snapshot(self):
        with self._lock:
            mujoco_alive = self._alive(
                self._mujoco_proc
            )

            relay_alive = self._alive(
                self._relay_proc
            )

            v2 = self.v2.snapshot_state()

            sonic = self.sonic.snapshot()

            return {
                "target": "sim",

                "state":
                    self._state,

                "active":
                    (
                        self._state
                        in self.ACTIVE_STATES
                    ),

                "ready":
                    (
                        self._state
                        == "running"
                    ),

                "last_error":
                    self._last_error,

                "started_at":
                    self._started_at,

                "mujoco": {
                    "process_alive":
                        mujoco_alive,

                    "pid":
                        (
                            self._mujoco_proc.pid
                            if mujoco_alive
                            else None
                        ),
                },

                "relay": {
                    "process_alive":
                        relay_alive,

                    "pid":
                        (
                            self._relay_proc.pid
                            if relay_alive
                            else None
                        ),
                },

                "v2_process_alive":
                    bool(
                        v2.get(
                            "teleop",
                            {}
                        ).get(
                            "process_alive"
                        )
                    ),

                "v2_ready":
                    bool(
                        v2.get(
                            "teleop",
                            {}
                        ).get(
                            "running"
                        )
                    ),

                "sonic_process_alive":
                    bool(
                        sonic.get(
                            "process_alive"
                        )
                    ),

                "sonic_state":
                    sonic.get(
                        "state",
                        "off",
                    ),

                "tracking_live":
                    bool(
                        sonic.get(
                            "zmq_live"
                        )
                    ),
            }


    # ========================================================
    # PROCESS OWNERSHIP
    # ========================================================

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
            "ab",
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
            return []

        signals = []

        try:
            pgid = os.getpgid(
                proc.pid
            )

        except ProcessLookupError:
            return signals


        for sig, name, wait_s in (
            (
                signal.SIGINT,
                "SIGINT",
                4.0,
            ),
            (
                signal.SIGTERM,
                "SIGTERM",
                2.0,
            ),
            (
                signal.SIGKILL,
                "SIGKILL",
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

                signals.append(
                    name
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

        return signals


    # ========================================================
    # WAIT HELPERS
    # ========================================================

    def _check_cancelled(self):
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
    # D7C_MUJOCO_RELEASE_9
    # ========================================================

    def _release_mujoco_robot(
        self,
    ):
        """
        Trigger the exact MuJoCo keyboard-9 path and wait for
        the helper to acknowledge that it executed.

        This happens only AFTER SONIC reference/control has
        been confirmed and BEFORE SONIC ENTER/live ZMQ.
        """

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
                self.mujoco_release_ack.exists(),
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
    # START
    # ========================================================

    def start(self):
        with self._lock:
            if (
                self._state
                in self.ACTIVE_STATES
            ):
                return {
                    "ok": False,
                    "error":
                        "Simulation stack is already active.",
                    "status":
                        self.snapshot(),
                }


            v2 = self.v2.snapshot_state()

            if (
                v2.get(
                    "teleop",
                    {}
                ).get(
                    "process_alive"
                )
            ):
                return {
                    "ok": False,
                    "error":
                        "Manual V2 process is already running.",
                }


            sonic = self.sonic.snapshot()

            if sonic.get(
                "process_alive"
            ):
                return {
                    "ok": False,
                    "error":
                        "Manual SONIC process is already running.",
                }


            self._last_error = None
            self._started_at = time.time()

            self._cancel.clear()

            self._state = (
                "starting_mujoco"
            )


            self._thread = threading.Thread(
                target=self._run_start,
                name="simulation-stack-start",
                daemon=True,
            )

            self._thread.start()


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }


    def _run_start(self):
        try:
            self.mujoco_release_request.unlink(
                missing_ok=True
            )

            self.mujoco_release_ack.unlink(
                missing_ok=True
            )

            commands = self.commands()

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


            self._wait_until(
                lambda:
                    self._alive(
                        self._mujoco_proc
                    ),
                4.0,
                "MuJoCo startup",
            )


            # -----------------------------------------------
            # Relay
            # -----------------------------------------------

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
            # V2
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
                snap = (
                    self.v2
                    .snapshot_state()
                )

                return bool(
                    snap.get(
                        "teleop",
                        {}
                    ).get(
                        "process_alive"
                    )
                )


            def v2_ready():
                snap = (
                    self.v2
                    .snapshot_state()
                )

                return bool(
                    snap.get(
                        "teleop",
                        {}
                    ).get(
                        "running"
                    )
                )


            # Camera/framing/alignment may require the human
            # to move into a valid full-body position.
            self._wait_until(
                v2_ready,
                600.0,
                "V2 camera/alignment readiness",
                health=v2_alive,
            )


            # -----------------------------------------------
            # SONIC -> REFERENCE
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "starting_sonic"
            )

            result = (
                self.sonic.start()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "SONIC start failed: "
                    + str(
                        result.get(
                            "error",
                            "unknown error",
                        )
                    )
                )


            self._set_state(
                "waiting_sonic_reference"
            )


            def sonic_alive():
                return bool(
                    self.sonic
                    .snapshot()
                    .get(
                        "process_alive"
                    )
                )


            self._wait_until(
                lambda:
                    (
                        self.sonic
                        .snapshot()
                        .get(
                            "state"
                        )
                        == "reference"
                    ),
                300.0,
                "SONIC reference mode",
                health=sonic_alive,
            )


            # -----------------------------------------------
            # SONIC REFERENCE -> MUJOCO RELEASE
            #
            # Exact validated order:
            #
            #       ] -> 9 -> ENTER
            #
            # sonic.start() has already produced/confirmed ].
            # We now execute MuJoCo key 9 and wait for its ACK.
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "releasing_mujoco"
            )

            self._release_mujoco_robot()


            # -----------------------------------------------
            # REFERENCE -> LIVE ZMQ
            #
            # This is simulation-only and go_live() itself is
            # guarded: ENTER is accepted only from confirmed
            # REFERENCE mode.
            # -----------------------------------------------

            self._check_cancelled()

            self._set_state(
                "going_live"
            )

            result = (
                self.sonic.go_live()
            )

            if not result.get(
                "ok"
            ):
                raise RuntimeError(
                    "SONIC Go Live failed: "
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
                        self.sonic
                        .snapshot()
                        .get(
                            "zmq_live"
                        )
                    ),
                30.0,
                "SONIC live ZMQ",
                health=sonic_alive,
            )


            self._set_state(
                "running"
            )


        except StackCancelled:
            return


        except Exception as exc:
            with self._lock:
                self._last_error = str(
                    exc
                )

                self._state = "error"

            self._cleanup()


    # ========================================================
    # STOP
    # ========================================================

    def _cleanup(self):
        # SONIC first: safe damping / controller shutdown.
        try:
            self.sonic.stop_process(
                graceful_timeout_s=8.0
            )
        except Exception:
            pass


        # Then stop V2 producer.
        try:
            self.v2.stop(
                reason=(
                    "simulation_stack_stop"
                )
            )
        except Exception:
            pass


        # Presentation transport.
        self._stop_owned_process(
            self._relay_proc
        )

        self._relay_proc = None


        # Physics last.
        self._stop_owned_process(
            self._mujoco_proc
        )

        self._mujoco_proc = None


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
                not self.sonic
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
            thread is not threading.current_thread()
        ):
            thread.join(
                timeout=2.0
            )


        self._cleanup()


        with self._lock:
            self._state = "off"
            self._thread = None
            self._started_at = None


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }
