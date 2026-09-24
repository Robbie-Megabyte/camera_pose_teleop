#!/usr/bin/env python3

import base64
import socket
import threading
import time

import cv2
import msgpack
import numpy as np
import zmq

from mujoco_image_relay import (
    MujocoImageRelay,
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


source_port = free_tcp_port()
output_port = free_tcp_port()

source_endpoint = (
    f"tcp://127.0.0.1:{source_port}"
)

output_endpoint = (
    f"tcp://127.0.0.1:{output_port}"
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
    "MUJOCO",
    (
        45,
        125,
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

jpeg = encoded.tobytes()

encoded_string = base64.b64encode(
    jpeg
).decode(
    "ascii"
)


relay = MujocoImageRelay(
    source_endpoint=source_endpoint,
    output_endpoint=output_endpoint,
    camera_name="ego_view",
)

stop_event = threading.Event()

thread = threading.Thread(
    target=relay.run,
    kwargs={
        "stop_event":
            stop_event,
    },
    daemon=True,
)

thread.start()


context = zmq.Context()

publisher = context.socket(
    zmq.PUB
)

publisher.setsockopt(
    zmq.LINGER,
    0,
)

publisher.bind(
    source_endpoint
)


subscriber = context.socket(
    zmq.SUB
)

subscriber.setsockopt(
    zmq.LINGER,
    0,
)

subscriber.setsockopt(
    zmq.CONFLATE,
    1,
)

subscriber.setsockopt(
    zmq.SUBSCRIBE,
    b"",
)

subscriber.connect(
    output_endpoint
)


try:
    # ZMQ PUB/SUB slow joiner allowance.
    time.sleep(
        0.5
    )

    payload = {
        "timestamps": {
            "ego_view":
                time.time(),
        },

        "images": {
            "ego_view":
                encoded_string,
        },

        # Matches current MuJoCo image
        # publisher compatibility field.
        "ego_view":
            encoded_string,
    }

    packed = msgpack.packb(
        payload,
        use_bin_type=True,
    )

    received = None

    for _ in range(60):
        publisher.send(
            packed
        )

        if subscriber.poll(
            timeout=50
        ):
            received = subscriber.recv()
            break

        time.sleep(
            0.02
        )

    assert received is not None
    assert received == jpeg

    assert (
        relay.received_messages
        >= 1
    )

    assert (
        relay.forwarded_frames
        >= 1
    )

    assert (
        relay.invalid_messages
        == 0
    )

    assert (
        relay.invalid_frames
        == 0
    )

    print(
        "D5F_RELAY_MSGPACK_RECEIVE=PASS"
    )

    print(
        "D5F_RELAY_BASE64_DECODE=PASS"
    )

    print(
        "D5F_RELAY_JPEG_BYTE_PASSTHROUGH=PASS"
    )

finally:
    stop_event.set()

    thread.join(
        timeout=2
    )

    publisher.close(
        0
    )

    subscriber.close(
        0
    )

    context.term()


assert not thread.is_alive()

print(
    "D5F_RELAY_STOP=PASS"
)

print(
    "D5F_RELAY_TEST=PASS"
)
