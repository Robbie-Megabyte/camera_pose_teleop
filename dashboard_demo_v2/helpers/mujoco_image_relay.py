#!/usr/bin/env python3

from __future__ import annotations

import argparse
import base64
import threading
import time

import msgpack
import zmq


JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def extract_jpeg(
    value,
):
    """
    Convert the MuJoCo SensorServer image field into
    the original JPEG bytes.

    MuJoCo currently sends a base64 string.

    Raw JPEG bytes are also accepted for forward
    compatibility.
    """

    if isinstance(
        value,
        bytearray,
    ):
        value = bytes(
            value
        )

    if isinstance(
        value,
        bytes,
    ):
        if (
            value.startswith(
                JPEG_SOI
            )
            and
            value.endswith(
                JPEG_EOI
            )
        ):
            return value

        try:
            decoded = base64.b64decode(
                value,
                validate=True,
            )

        except Exception:
            return None

        if (
            decoded.startswith(
                JPEG_SOI
            )
            and
            decoded.endswith(
                JPEG_EOI
            )
        ):
            return decoded

        return None

    if isinstance(
        value,
        str,
    ):
        try:
            decoded = base64.b64decode(
                value.encode(
                    "ascii"
                ),
                validate=True,
            )

        except Exception:
            return None

        if (
            decoded.startswith(
                JPEG_SOI
            )
            and
            decoded.endswith(
                JPEG_EOI
            )
        ):
            return decoded

    return None


class MujocoImageRelay:
    """
    Passive adapter:

        GR00T SensorServer PUB
            tcp://127.0.0.1:5555

        → msgpack/base64 decode only

        → raw JPEG PUB
            tcp://127.0.0.1:5610
    """

    def __init__(
        self,
        source_endpoint=(
            "tcp://127.0.0.1:5555"
        ),
        output_endpoint=(
            "tcp://127.0.0.1:5610"
        ),
        camera_name="ego_view",
    ):
        self.source_endpoint = str(
            source_endpoint
        )

        self.output_endpoint = str(
            output_endpoint
        )

        self.camera_name = str(
            camera_name
        )

        self.received_messages = 0
        self.forwarded_frames = 0
        self.invalid_messages = 0
        self.invalid_frames = 0

        self.last_error = None

    def _find_image_value(
        self,
        message,
    ):
        if not isinstance(
            message,
            dict,
        ):
            return None

        images = message.get(
            "images",
            {},
        )

        if isinstance(
            images,
            dict,
        ):
            value = images.get(
                self.camera_name
            )

            if value is not None:
                return value

        # Current MuJoCo publisher also provides
        # a top-level compatibility copy.
        return message.get(
            self.camera_name
        )

    def run(
        self,
        stop_event=None,
    ):
        context = zmq.Context()

        source = context.socket(
            zmq.SUB
        )

        source.setsockopt(
            zmq.LINGER,
            0,
        )

        source.setsockopt(
            zmq.RCVHWM,
            1,
        )

        source.setsockopt(
            zmq.CONFLATE,
            1,
        )

        source.setsockopt(
            zmq.SUBSCRIBE,
            b"",
        )

        source.connect(
            self.source_endpoint
        )

        output = context.socket(
            zmq.PUB
        )

        output.setsockopt(
            zmq.LINGER,
            0,
        )

        output.setsockopt(
            zmq.SNDHWM,
            1,
        )

        output.bind(
            self.output_endpoint
        )

        poller = zmq.Poller()

        poller.register(
            source,
            zmq.POLLIN,
        )

        print(
            "[mujoco-relay] source:",
            self.source_endpoint,
        )

        print(
            "[mujoco-relay] output:",
            self.output_endpoint,
        )

        print(
            "[mujoco-relay] camera:",
            self.camera_name,
        )

        try:
            while True:
                if (
                    stop_event is not None
                    and
                    stop_event.is_set()
                ):
                    break

                events = dict(
                    poller.poll(
                        timeout=250
                    )
                )

                if source not in events:
                    continue

                try:
                    packed = source.recv(
                        flags=zmq.NOBLOCK
                    )

                except zmq.Again:
                    continue

                self.received_messages += 1

                try:
                    message = msgpack.unpackb(
                        packed,
                        raw=False,
                    )

                except Exception as exc:
                    self.invalid_messages += 1
                    self.last_error = repr(
                        exc
                    )
                    continue

                value = self._find_image_value(
                    message
                )

                jpeg = extract_jpeg(
                    value
                )

                if jpeg is None:
                    self.invalid_frames += 1
                    continue

                try:
                    output.send(
                        jpeg,
                        flags=zmq.NOBLOCK,
                    )

                except zmq.Again:
                    continue

                self.forwarded_frames += 1
                self.last_error = None

        except KeyboardInterrupt:
            pass

        finally:
            try:
                poller.unregister(
                    source
                )
            except Exception:
                pass

            source.close(
                0
            )

            output.close(
                0
            )

            context.term()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--source-endpoint",
        default=(
            "tcp://127.0.0.1:5555"
        ),
    )

    parser.add_argument(
        "--output-endpoint",
        default=(
            "tcp://127.0.0.1:5610"
        ),
    )

    parser.add_argument(
        "--camera-name",
        default="ego_view",
    )

    args = parser.parse_args()

    relay = MujocoImageRelay(
        source_endpoint=(
            args.source_endpoint
        ),
        output_endpoint=(
            args.output_endpoint
        ),
        camera_name=(
            args.camera_name
        ),
    )

    relay.run()


if __name__ == "__main__":
    main()
