#!/usr/bin/env python3

from __future__ import annotations

import threading
import time

import zmq


JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


class MujocoPreviewBridge:
    """
    Passive subscriber to the MuJoCo JPEG relay.

    The relay already supplies complete JPEG bytes.
    This class does not decode or re-encode them.
    """

    def __init__(
        self,
        endpoint=(
            "tcp://127.0.0.1:5610"
        ),
        stale_after_s=2.0,
    ):
        self.endpoint = str(
            endpoint
        )

        self.stale_after_s = float(
            stale_after_s
        )

        self._lock = threading.RLock()

        self._frame_condition = (
            threading.Condition(
                self._lock
            )
        )
        self._stop_event = threading.Event()

        self._latest_frame = None
        self._latest_monotonic = None

        self._frame_seq = 0
        self._received_frames = 0
        self._invalid_frames = 0

        self._last_error = None

        self._thread = threading.Thread(
            target=self._run,
            name="mujoco-preview-bridge",
            daemon=True,
        )

        self._thread.start()

    def _run(self):
        context = zmq.Context()

        socket = context.socket(
            zmq.SUB
        )

        socket.setsockopt(
            zmq.LINGER,
            0,
        )

        socket.setsockopt(
            zmq.RCVHWM,
            1,
        )

        socket.setsockopt(
            zmq.CONFLATE,
            1,
        )

        socket.setsockopt(
            zmq.SUBSCRIBE,
            b"",
        )

        socket.connect(
            self.endpoint
        )

        poller = zmq.Poller()

        poller.register(
            socket,
            zmq.POLLIN,
        )

        try:
            while not self._stop_event.is_set():

                events = dict(
                    poller.poll(
                        timeout=250
                    )
                )

                if socket not in events:
                    continue

                try:
                    frame = socket.recv(
                        flags=zmq.NOBLOCK
                    )

                except zmq.Again:
                    continue

                if (
                    len(frame) < 4
                    or
                    not frame.startswith(
                        JPEG_SOI
                    )
                    or
                    not frame.endswith(
                        JPEG_EOI
                    )
                ):
                    with self._lock:
                        self._invalid_frames += 1

                    continue

                now = time.monotonic()

                with self._lock:
                    self._latest_frame = bytes(
                        frame
                    )

                    self._latest_monotonic = now

                    self._frame_seq += 1
                    self._received_frames += 1
                    self._last_error = None

                    self._frame_condition.notify_all()

        except Exception as exc:
            with self._lock:
                self._last_error = repr(
                    exc
                )

        finally:
            try:
                poller.unregister(
                    socket
                )
            except Exception:
                pass

            socket.close(
                0
            )

            context.term()

    def get_latest_frame(
        self,
        max_age_s=None,
    ):
        if max_age_s is None:
            max_age_s = (
                self.stale_after_s
            )

        now = time.monotonic()

        with self._lock:
            frame = self._latest_frame
            when = self._latest_monotonic

        if frame is None or when is None:
            return None

        if (
            max_age_s is not None
            and
            now - when
            > float(max_age_s)
        ):
            return None

        return frame

    def wait_for_frame(
        self,
        after_seq=-1,
        timeout_s=1.0,
        max_age_s=None,
    ):
        """
        Wait for a JPEG newer than after_seq.

        Returns:
            (frame_seq, jpeg_bytes)

        or:
            (current_seq, None)

        The JPEG is returned byte-for-byte.
        There is no decode and no re-encode.
        """

        if max_age_s is None:
            max_age_s = (
                self.stale_after_s
            )

        deadline = (
            time.monotonic()
            + float(
                timeout_s
            )
        )

        with self._frame_condition:
            while (
                not self._stop_event.is_set()
            ):
                seq = self._frame_seq
                frame = self._latest_frame
                when = self._latest_monotonic

                if (
                    frame is not None
                    and
                    when is not None
                    and
                    seq > int(
                        after_seq
                    )
                ):
                    age = (
                        time.monotonic()
                        - when
                    )

                    if (
                        max_age_s is None
                        or
                        age
                        <= float(
                            max_age_s
                        )
                    ):
                        return (
                            seq,
                            frame,
                        )

                remaining = (
                    deadline
                    - time.monotonic()
                )

                if remaining <= 0:
                    break

                self._frame_condition.wait(
                    timeout=remaining
                )

            return (
                self._frame_seq,
                None,
            )

    def snapshot(self):
        now = time.monotonic()

        with self._lock:
            when = self._latest_monotonic

            age = (
                None
                if when is None
                else max(
                    0.0,
                    now - when,
                )
            )

            live = (
                age is not None
                and
                age <= self.stale_after_s
            )

            return {
                "state":
                    "live"
                    if live
                    else "waiting",

                "live":
                    live,

                "endpoint":
                    self.endpoint,

                "frame_seq":
                    self._frame_seq,

                "received_frames":
                    self._received_frames,

                "invalid_frames":
                    self._invalid_frames,

                "frame_age_s":
                    None
                    if age is None
                    else round(
                        age,
                        3,
                    ),

                "last_error":
                    self._last_error,
            }

    def stop(self):
        self._stop_event.set()

        with self._frame_condition:
            self._frame_condition.notify_all()

        self._thread.join(
            timeout=1.5
        )

        return (
            not self._thread.is_alive()
        )
