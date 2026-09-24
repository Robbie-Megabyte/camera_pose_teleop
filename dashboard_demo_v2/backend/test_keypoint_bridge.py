#!/usr/bin/env python3

import time

import zmq

from keypoint_bridge import (
    KeypointPreviewBridge,
)


context = zmq.Context.instance()

publisher = context.socket(
    zmq.PUB
)

publisher.setsockopt(
    zmq.LINGER,
    0,
)

port = publisher.bind_to_random_port(
    "tcp://127.0.0.1"
)

endpoint = (
    f"tcp://127.0.0.1:{port}"
)

bridge = KeypointPreviewBridge(
    endpoint=endpoint,
    stale_after_s=0.4,
)

# PUB/SUB slow-joiner allowance.
time.sleep(0.2)

payload = (
    b"\xff\xd8"
    + b"D4B_SYNTHETIC_JPEG"
    + b"\xff\xd9"
)

try:
    received = False

    for _ in range(20):
        publisher.send(
            payload
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

    assert state["state"] == "live"
    assert state["live"] is True
    assert state["received_frames"] >= 1
    assert state["frame_seq"] >= 1
    assert state["invalid_frames"] == 0

    print(
        "D4B_ZMQ_SUBSCRIBE=PASS"
    )

    print(
        "D4B_JPEG_PASSTHROUGH=PASS"
    )

    print(
        "D4B_LATEST_FRAME=PASS"
    )

    time.sleep(0.5)

    state = bridge.snapshot()

    assert state["state"] == "waiting"
    assert state["live"] is False

    assert (
        bridge.get_latest_frame()
        is None
    )

    print(
        "D4B_STALE_FRAME_GATE=PASS"
    )

finally:
    assert bridge.stop()

    publisher.close(0)

print(
    "D4B_KEYPOINT_BRIDGE_TEST=PASS"
)
