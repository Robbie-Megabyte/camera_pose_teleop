#!/usr/bin/env python3

from __future__ import annotations

import socket
import threading
import time


JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"

MAX_BUFFER_BYTES = (
    16
    * 1024
    * 1024
)


class RawPreviewBridge:
    """
    Passive latest-frame receiver for V2's existing raw preview.

    V2 remains the ONLY camera owner.

    Source:
        MJPEG byte stream
        UDP 127.0.0.1:5600

    The bridge only reassembles complete JPEG byte sequences.
    It does not open the camera, decode JPEG, or re-encode JPEG.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5600,
        stale_after_s: float = 2.0,
    ):
        self.host = str(host)
        self.port = int(port)

        self.endpoint = (
            f"udp://{self.host}:{self.port}"
        )

        self.stale_after_s = float(
            stale_after_s
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._socket = None

        self._latest_frame = None
        self._latest_monotonic = None

        self._frame_seq = 0
        self._received_frames = 0
        self._received_packets = 0
        self._discarded_bytes = 0

        self._bound = False
        self._last_error = None

        self._thread = threading.Thread(
            target=self._run,
            name="raw-preview-bridge",
            daemon=True,
        )

        self._thread.start()

    def _store_frame(
        self,
        frame: bytes,
    ):
        if (
            not frame
            or len(frame) < 4
            or not frame.startswith(
                JPEG_SOI
            )
            or not frame.endswith(
                JPEG_EOI
            )
        ):
            return

        now = time.monotonic()

        with self._lock:
            self._latest_frame = bytes(
                frame
            )

            self._latest_monotonic = now
            self._frame_seq += 1
            self._received_frames += 1
            self._last_error = None

    def _run(self):
        sock = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )

        try:
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_RCVBUF,
                4 * 1024 * 1024,
            )

            sock.settimeout(
                0.25
            )

            sock.bind(
                (
                    self.host,
                    self.port,
                )
            )

            with self._lock:
                self._socket = sock
                self._bound = True
                self._last_error = None

            buffer = bytearray()

            while not self._stop_event.is_set():
                try:
                    packet, _address = (
                        sock.recvfrom(
                            65535
                        )
                    )

                except socket.timeout:
                    continue

                except OSError as exc:
                    if self._stop_event.is_set():
                        break

                    with self._lock:
                        self._last_error = repr(
                            exc
                        )

                    time.sleep(0.05)
                    continue

                if not packet:
                    continue

                with self._lock:
                    self._received_packets += 1

                buffer.extend(
                    packet
                )

                while True:
                    start = buffer.find(
                        JPEG_SOI
                    )

                    if start < 0:
                        if (
                            len(buffer)
                            > MAX_BUFFER_BYTES
                        ):
                            with self._lock:
                                self._discarded_bytes += len(
                                    buffer
                                )

                            buffer.clear()

                        break

                    if start > 0:
                        with self._lock:
                            self._discarded_bytes += start

                        del buffer[:start]

                    end = buffer.find(
                        JPEG_EOI,
                        2,
                    )

                    if end < 0:
                        if (
                            len(buffer)
                            > MAX_BUFFER_BYTES
                        ):
                            newest = buffer.rfind(
                                JPEG_SOI
                            )

                            if newest > 0:
                                with self._lock:
                                    self._discarded_bytes += newest

                                del buffer[:newest]

                            elif newest < 0:
                                with self._lock:
                                    self._discarded_bytes += len(
                                        buffer
                                    )

                                buffer.clear()

                        break

                    end += 2

                    frame = bytes(
                        buffer[:end]
                    )

                    del buffer[:end]

                    self._store_frame(
                        frame
                    )

        except Exception as exc:
            with self._lock:
                self._last_error = repr(
                    exc
                )

        finally:
            with self._lock:
                self._bound = False
                self._socket = None

            try:
                sock.close()
            except Exception:
                pass

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
            and now - when
            > float(max_age_s)
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
                "bound": self._bound,

                "endpoint":
                    self.endpoint,

                "frame_seq":
                    self._frame_seq,

                "received_frames":
                    self._received_frames,

                "received_packets":
                    self._received_packets,

                "discarded_bytes":
                    self._discarded_bytes,

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

        with self._lock:
            sock = self._socket

        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass

        self._thread.join(
            timeout=1.5
        )

        return (
            not self._thread.is_alive()
        )
