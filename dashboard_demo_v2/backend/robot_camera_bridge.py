from __future__ import annotations

from pathlib import Path
import os
import signal
import subprocess
import threading
import time


class RobotCameraBridge:
    """
    Dashboard bridge for the Microsoft LifeCam attached to G1.

    Transport:

        Jetson /dev/v4l/... LifeCam
              |
              | FFmpeg V4L2, MJPEG COPY
              v
             SSH
              |
              v
        dashboard PC
              |
              v
        browser MJPEG endpoint

    There is deliberately NO decode/re-encode step.

    Starting this bridge opens a CAMERA ONLY.
    It does not launch SONIC and sends no robot commands.
    """

    def __init__(
        self,
        runtime_dir,
        host="192.168.0.116",
        user="unitree",
        ssh_key=None,
        device=(
            "/dev/v4l/by-path/"
            "platform-3610000.usb-usb-0:2.3.1:1.0-video-index0"
        ),
        width=1280,
        height=720,
        fps=30,
        stale_after_s=2.0,
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

        if ssh_key is None:
            ssh_key = (
                Path.home()
                / ".ssh"
                / "bacalbasa_g1_dashboard_ed25519"
            )

        self.ssh_key = Path(
            ssh_key
        ).expanduser().resolve()

        self.device = str(
            device
        )

        self.width = int(
            width
        )

        self.height = int(
            height
        )

        self.fps = int(
            fps
        )

        self.stale_after_s = float(
            stale_after_s
        )

        self.log_path = (
            self.runtime_dir
            / "robot_camera.log"
        )

        self._lock = threading.RLock()

        self._condition = threading.Condition(
            self._lock
        )

        self._proc = None
        self._reader_thread = None
        self._stderr_thread = None
        self._wait_thread = None

        self._stop = threading.Event()

        self._frame = None
        self._frame_seq = 0

        self._started_monotonic = None
        self._last_frame_monotonic = None

        self._last_error = None
        self._returncode = None


    # ========================================================
    # COMMAND
    # ========================================================

    def command(
        self,
    ):
        remote = [
            "exec",
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-f",
            "v4l2",
            "-input_format",
            "mjpeg",
            "-framerate",
            str(
                self.fps
            ),
            "-video_size",
            (
                f"{self.width}"
                f"x"
                f"{self.height}"
            ),
            "-i",
            self.device,
            "-an",
            "-c:v",
            "copy",
            "-f",
            "mjpeg",
            "-",
        ]

        quoted = subprocess.list2cmdline(
            remote
        )

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
            quoted,
        ]


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
            now = time.monotonic()

            frame_age = (
                (
                    now
                    - self._last_frame_monotonic
                )
                if self._last_frame_monotonic
                is not None
                else None
            )

            live = bool(
                self._alive_locked()
                and
                frame_age is not None
                and
                frame_age
                <= self.stale_after_s
            )

            return {
                "state":
                    (
                        "live"
                        if live
                        else (
                            "starting"
                            if self._alive_locked()
                            else "off"
                        )
                    ),

                "live":
                    live,

                "process_alive":
                    self._alive_locked(),

                "frame_seq":
                    self._frame_seq,

                "frame_age_s":
                    (
                        round(
                            frame_age,
                            3,
                        )
                        if frame_age
                        is not None
                        else None
                    ),

                "device":
                    self.device,

                "profile":
                    (
                        f"{self.width}x"
                        f"{self.height} @ "
                        f"{self.fps} fps MJPEG"
                    ),

                "last_error":
                    self._last_error,

                "returncode":
                    self._returncode,

                "log_path":
                    str(
                        self.log_path
                    ),
            }


    def get_latest_frame(
        self,
    ):
        with self._lock:
            return self._frame


    def wait_for_frame(
        self,
        after_seq=0,
        timeout_s=2.0,
    ):
        deadline = (
            time.monotonic()
            + float(
                timeout_s
            )
        )

        with self._condition:
            while (
                self._frame_seq
                <= int(
                    after_seq
                )
            ):
                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:
                    break

                self._condition.wait(
                    timeout=remaining
                )

            return (
                self._frame_seq,
                self._frame,
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
                    "ok": True,
                    "already_running": True,
                    "status":
                        self.snapshot(),
                }


        if not self.ssh_key.is_file():
            return {
                "ok": False,
                "error":
                    f"Missing SSH key: {self.ssh_key}",
            }


        # Verify the stable device path without opening it.
        probe = subprocess.run(
            [
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
                f"{self.user}@{self.host}",
                (
                    "test -e "
                    + subprocess.list2cmdline(
                        [
                            self.device,
                        ]
                    )
                ),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=7.0,
        )


        if probe.returncode != 0:
            return {
                "ok": False,
                "error":
                    (
                        "Jetson camera device unavailable: "
                        + (
                            probe.stderr.strip()
                            or self.device
                        )
                    ),
            }


        self.log_path.write_text(
            ""
        )


        try:
            proc = subprocess.Popen(
                self.command(),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                start_new_session=True,
                close_fds=True,
            )

        except Exception as exc:
            return {
                "ok": False,
                "error":
                    (
                        "Could not start robot camera SSH/FFmpeg: "
                        + repr(
                            exc
                        )
                    ),
            }


        with self._lock:
            self._proc = proc

            self._frame = None
            self._frame_seq = 0

            self._started_monotonic = (
                time.monotonic()
            )

            self._last_frame_monotonic = None
            self._last_error = None
            self._returncode = None

            self._stop.clear()


        self._reader_thread = threading.Thread(
            target=self._reader_loop,
            name="robot-camera-reader",
            daemon=True,
        )

        self._stderr_thread = threading.Thread(
            target=self._stderr_loop,
            name="robot-camera-stderr",
            daemon=True,
        )

        self._wait_thread = threading.Thread(
            target=self._wait_loop,
            name="robot-camera-wait",
            daemon=True,
        )

        self._reader_thread.start()
        self._stderr_thread.start()
        self._wait_thread.start()


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }


    # ========================================================
    # READ MJPEG
    # ========================================================

    def _reader_loop(
        self,
    ):
        with self._lock:
            proc = self._proc

        if (
            proc is None
            or
            proc.stdout is None
        ):
            return


        buffer = bytearray()

        SOI = b"\xff\xd8"
        EOI = b"\xff\xd9"


        while not self._stop.is_set():
            try:
                chunk = proc.stdout.read(
                    65536
                )

            except Exception as exc:
                with self._lock:
                    self._last_error = (
                        "Robot camera read failed: "
                        + repr(
                            exc
                        )
                    )

                break


            if not chunk:
                break


            buffer.extend(
                chunk
            )


            # A corrupt/unbounded stream should never consume
            # arbitrary dashboard memory.
            if len(
                buffer
            ) > 8 * 1024 * 1024:
                start = buffer.rfind(
                    SOI
                )

                if start >= 0:
                    del buffer[
                        :start
                    ]

                else:
                    buffer.clear()


            while True:
                start = buffer.find(
                    SOI
                )

                if start < 0:
                    break


                end = buffer.find(
                    EOI,
                    start + 2,
                )

                if end < 0:
                    if start > 0:
                        del buffer[
                            :start
                        ]

                    break


                end += 2

                frame = bytes(
                    buffer[
                        start:end
                    ]
                )

                del buffer[
                    :end
                ]


                with self._condition:
                    self._frame = frame
                    self._frame_seq += 1
                    self._last_frame_monotonic = (
                        time.monotonic()
                    )

                    self._condition.notify_all()


    def _stderr_loop(
        self,
    ):
        with self._lock:
            proc = self._proc

        if (
            proc is None
            or
            proc.stderr is None
        ):
            return


        try:
            with self.log_path.open(
                "a",
                encoding="utf-8",
            ) as log:
                for raw in iter(
                    proc.stderr.readline,
                    b"",
                ):
                    if self._stop.is_set():
                        break

                    text = raw.decode(
                        "utf-8",
                        errors="replace",
                    )

                    log.write(
                        text
                    )

                    log.flush()


        except Exception as exc:
            with self._lock:
                self._last_error = (
                    "Robot camera stderr reader failed: "
                    + repr(
                        exc
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


        with self._condition:
            self._returncode = rc

            if (
                not self._stop.is_set()
                and
                rc != 0
            ):
                self._last_error = (
                    "Robot camera SSH/FFmpeg exited "
                    f"with rc={rc}."
                )

            self._condition.notify_all()


    # ========================================================
    # STOP
    # ========================================================

    def stop(
        self,
    ):
        self._stop.set()


        with self._lock:
            proc = self._proc


        if (
            proc is not None
            and
            proc.poll() is None
        ):
            try:
                pgid = os.getpgid(
                    proc.pid
                )

            except ProcessLookupError:
                pgid = None


            if pgid is not None:
                for sig, wait_s in (
                    (
                        signal.SIGINT,
                        2.0,
                    ),
                    (
                        signal.SIGTERM,
                        1.0,
                    ),
                    (
                        signal.SIGKILL,
                        0.3,
                    ),
                ):
                    if proc.poll() is not None:
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
                        if proc.poll() is not None:
                            break

                        time.sleep(
                            0.05
                        )


        with self._condition:
            self._proc = None
            self._frame = None
            self._last_frame_monotonic = None

            self._condition.notify_all()


        return {
            "ok": True,
            "status":
                self.snapshot(),
        }
