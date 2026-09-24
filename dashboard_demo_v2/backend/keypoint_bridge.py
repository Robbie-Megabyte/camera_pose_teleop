#!/usr/bin/env python3

from __future__ import annotations

import threading
import time

import zmq


class KeypointPreviewBridge:
    """
    Passive latest-frame bridge for the existing V2 ViTPose preview.

    V2 remains the ONLY camera/perception owner.

    Production source:
        ZMQ PUB
        tcp://127.0.0.1:5601
        one JPEG byte message per preview frame

    This class only subscribes and keeps the newest JPEG in memory.
    """

    def __init__(
        self,
        endpoint: str = "tcp://127.0.0.1:5601",
        stale_after_s: float = 2.0,
    ):
        self.endpoint = str(endpoint)
        self.stale_after_s = float(stale_after_s)

        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._latest_frame = None
        self._latest_monotonic = None
        self._frame_seq = 0
        self._received_frames = 0
        self._invalid_frames = 0
        self._last_error = None

        self._thread = threading.Thread(
            target=self._run,
            name="keypoint-preview-bridge",
            daemon=True,
        )

        self._thread.start()

    def _run(self):
        context = zmq.Context.instance()

        sock = context.socket(
            zmq.SUB
        )

        sock.setsockopt(
            zmq.CONFLATE,
            1,
        )

        sock.setsockopt(
            zmq.SUBSCRIBE,
            b"",
        )

        sock.setsockopt(
            zmq.LINGER,
            0,
        )

        sock.setsockopt(
            zmq.RCVTIMEO,
            250,
        )

        try:
            sock.connect(
                self.endpoint
            )

            while not self._stop_event.is_set():
                try:
                    frame = sock.recv()

                except zmq.Again:
                    continue

                except Exception as exc:
                    with self._lock:
                        self._last_error = repr(
                            exc
                        )

                    time.sleep(0.05)
                    continue

                # V2 sends a complete JPEG byte message.
                if (
                    not frame
                    or len(frame) < 4
                    or not frame.startswith(
                        b"\xff\xd8"
                    )
                    or not frame.endswith(
                        b"\xff\xd9"
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

        finally:
            sock.close(0)

    def get_latest_frame(
        self,
        max_age_s=None,
    ):
        if max_age_s is None:
            max_age_s = self.stale_after_s

        now = time.monotonic()

        with self._lock:
            frame = self._latest_frame
            when = self._latest_monotonic

        if frame is None or when is None:
            return None

        if (
            max_age_s is not None
            and now - when > float(max_age_s)
        ):
            return None

        return frame

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
                and age <= self.stale_after_s
            )

            return {
                "state":
                    "live"
                    if live
                    else "waiting",

                "live": live,

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
                    else round(age, 3),

                "last_error":
                    self._last_error,
            }

    def stop(self):
        self._stop_event.set()

        self._thread.join(
            timeout=1.5
        )

        return (
            not self._thread.is_alive()
        )
