#!/usr/bin/env python3

import socket
import time

import cv2
import numpy as np
import zmq

from mujoco_preview_bridge import (
    MujocoPreviewBridge,
)


def free_tcp_port():
    sock = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    sock.bind(
        (
            "127.0.0.1",
            0,
        )
    )

    port = sock.getsockname()[1]
    sock.close()

    return port


port = free_tcp_port()

endpoint = (
    f"tcp://127.0.0.1:{port}"
)

bridge = MujocoPreviewBridge(
    endpoint=endpoint,
    stale_after_s=0.4,
)


context = zmq.Context()

publisher = context.socket(
    zmq.PUB
)

publisher.setsockopt(
    zmq.LINGER,
    0,
)

publisher.bind(
    endpoint
)


frame = np.zeros(
    (
        240,
        320,
        3,
    ),
    dtype=np.uint8,
)

cv2.putText(
    frame,
    "DASHBOARD",
    (
        30,
        125,
    ),
    cv2.FONT_HERSHEY_SIMPLEX,
    0.9,
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

jpeg = encoded.tobytes()


try:
    time.sleep(
        0.4
    )

    received = False

    for _ in range(40):
        publisher.send(
            jpeg
        )

        time.sleep(
            0.03
        )

        if (
            bridge.get_latest_frame(
                max_age_s=1.0
            )
            == jpeg
        ):
            received = True
            break

    assert received

    state = bridge.snapshot()

    assert state["live"] is True
    assert state["frame_seq"] >= 1
    assert state["received_frames"] >= 1
    assert state["invalid_frames"] == 0

    print(
        "D5F_DASH_ZMQ_RECEIVE=PASS"
    )

    print(
        "D5F_DASH_JPEG_PASSTHROUGH=PASS"
    )

    time.sleep(
        0.5
    )

    assert (
        bridge.snapshot()["live"]
        is False
    )

    assert (
        bridge.get_latest_frame()
        is None
    )

    print(
        "D5F_DASH_STALE_GATE=PASS"
    )

finally:
    publisher.close(
        0
    )

    context.term()

    assert bridge.stop()


print(
    "D5F_DASH_BRIDGE_TEST=PASS"
)
