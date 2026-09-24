#!/usr/bin/env python3

from __future__ import annotations

import subprocess

import cv2
import numpy as np


WINDOW = "G1 - Raw Camera"

UDP_URL = (
    "udp://127.0.0.1:5600"
    "?fifo_size=1024"
    "&overrun_nonfatal=1"
)

cmd = [
    "ffmpeg",
    "-hide_banner",
    "-loglevel",
    "error",

    "-fflags",
    "nobuffer",

    "-flags",
    "low_delay",

    "-probesize",
    "32",

    "-analyzeduration",
    "0",

    "-f",
    "mjpeg",

    "-i",
    UDP_URL,

    "-an",

    "-c:v",
    "copy",

    "-f",
    "mjpeg",

    "pipe:1",
]

proc = subprocess.Popen(
    cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    bufsize=0,
)

if proc.stdout is None:
    raise RuntimeError(
        "Could not open FFmpeg output."
    )

cv2.namedWindow(
    WINDOW,
    cv2.WINDOW_NORMAL
    | cv2.WINDOW_GUI_NORMAL
    | cv2.WINDOW_FREERATIO,
)

cv2.resizeWindow(
    WINDOW,
    960,
    540,
)

print(
    "Connected to raw camera on UDP 5600"
)

print(
    "Resolution is detected from each JPEG frame."
)

print(
    "Window is freely resizable."
)

print(
    "Press q to close."
)

buffer = bytearray()

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def next_jpeg():
    while True:
        start = buffer.find(
            JPEG_SOI
        )

        if start >= 0:
            end = buffer.find(
                JPEG_EOI,
                start + 2,
            )

            if end >= 0:
                end += 2

                jpeg = bytes(
                    buffer[start:end]
                )

                del buffer[:end]

                return jpeg

            if start > 0:
                del buffer[:start]

        chunk = proc.stdout.read(
            65536
        )

        if not chunk:
            return None

        buffer.extend(
            chunk
        )

        if len(buffer) > 16 * 1024 * 1024:
            newest_start = buffer.rfind(
                JPEG_SOI
            )

            if newest_start > 0:
                del buffer[:newest_start]
            else:
                buffer.clear()


try:
    while True:
        encoded = next_jpeg()

        if encoded is None:
            break

        frame = cv2.imdecode(
            np.frombuffer(
                encoded,
                dtype=np.uint8,
            ),
            cv2.IMREAD_COLOR,
        )

        if frame is None:
            continue

        cv2.imshow(
            WINDOW,
            frame,
        )

        if (
            cv2.waitKey(1)
            & 0xFF
            == ord("q")
        ):
            break

finally:
    cv2.destroyAllWindows()

    if proc.poll() is None:
        proc.terminate()

    try:
        proc.wait(
            timeout=2
        )
    except subprocess.TimeoutExpired:
        proc.kill()
