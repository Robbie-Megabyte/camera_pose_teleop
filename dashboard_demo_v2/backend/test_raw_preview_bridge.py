#!/usr/bin/env python3

import socket
import time

import cv2
import numpy as np

from raw_preview_bridge import (
    RawPreviewBridge,
)


probe = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM,
)

probe.bind(
    (
        "127.0.0.1",
        0,
    )
)

port = probe.getsockname()[1]
probe.close()

bridge = RawPreviewBridge(
    host="127.0.0.1",
    port=port,
    stale_after_s=0.4,
)

sender = socket.socket(
    socket.AF_INET,
    socket.SOCK_DGRAM,
)

frame = np.zeros(
    (
        360,
        640,
        3,
    ),
    dtype=np.uint8,
)

cv2.putText(
    frame,
    "D4D RAW BRIDGE TEST",
    (
        55,
        180,
    ),
    cv2.FONT_HERSHEY_SIMPLEX,
    1.0,
    (
        255,
        255,
        255,
    ),
    2,
    cv2.LINE_AA,
)

ok, encoded = cv2.imencode(
    ".jpg",
    frame,
)

assert ok

payload = encoded.tobytes()

try:
    for _ in range(30):
        if bridge.snapshot()["bound"]:
            break

        time.sleep(0.03)

    assert bridge.snapshot()["bound"]

    received = False

    for _ in range(20):
        for offset in range(
            0,
            len(payload),
            1316,
        ):
            sender.sendto(
                payload[
                    offset:
                    offset + 1316
                ],
                (
                    "127.0.0.1",
                    port,
                ),
            )

        time.sleep(0.03)

        if (
            bridge.get_latest_frame(
                max_age_s=1.0
            )
            == payload
        ):
            received = True
            break

    assert received

    state = bridge.snapshot()

    assert state["live"] is True
    assert state["frame_seq"] >= 1
    assert state["received_frames"] >= 1
    assert state["received_packets"] >= 1
    assert state["last_error"] is None

    print("D4D_RAW_UDP_RECEIVE=PASS")
    print("D4D_RAW_JPEG_REASSEMBLY=PASS")
    print("D4D_RAW_BYTE_PASSTHROUGH=PASS")

    time.sleep(0.5)

    assert (
        bridge.snapshot()["live"]
        is False
    )

    assert (
        bridge.get_latest_frame()
        is None
    )

    print("D4D_RAW_STALE_GATE=PASS")

finally:
    sender.close()

    assert bridge.stop()

print("D4D_RAW_BRIDGE_TEST=PASS")
