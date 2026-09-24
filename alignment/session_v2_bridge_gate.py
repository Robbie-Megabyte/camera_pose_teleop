#!/usr/bin/env python3

from __future__ import annotations


class SessionV2BridgeGate:
    """
    Gate SONIC bridge creation behind successful
    current-session V2 alignment.

    The bridge factory is called exactly once, and only
    after the alignment controller reports READY.
    """

    def __init__(
        self,
        *,
        controller,
        bridge_factory,
    ):
        self.controller = controller
        self.bridge_factory = (
            bridge_factory
        )

        self.bridge = None
        self.bridge_create_count = 0

    @property
    def ready(self) -> bool:
        return (
            self.bridge is not None
        )

    def process_alignment_frame(
        self,
        joints24,
        *,
        timestamp_s: float,
    ):
        """
        Feed one calibration-only SMPL24 frame.

        Returns:
            status
            bridge
            bridge_created_now
        """

        if self.bridge is not None:
            return (
                self.controller.status(
                    timestamp_s
                ),
                self.bridge,
                False,
            )

        status = (
            self.controller.add_frame(
                joints24,
                timestamp_s=timestamp_s,
            )
        )

        bridge_created_now = False

        if status.state == "ready":
            self.bridge = (
                self.bridge_factory()
            )

            self.bridge_create_count += 1
            bridge_created_now = True

        return (
            status,
            self.bridge,
            bridge_created_now,
        )
