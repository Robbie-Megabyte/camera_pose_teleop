from __future__ import annotations

from copy import deepcopy

import numpy as np

from v3_fusion.g1_wrist_control_runtime import (
    G1WristControlRuntime,
)


SONIC_V3_WRIST_SHAPE = (
    1,
    6,
)

SONIC_V3_WRIST_DTYPE = np.float32


def validate_sonic_wrists(
    wrists,
) -> np.ndarray:
    """Validate and normalize the exact SONIC Protocol-v3 wrist field."""

    wrists = np.asarray(
        wrists,
        dtype=SONIC_V3_WRIST_DTYPE,
    )

    if wrists.shape != SONIC_V3_WRIST_SHAPE:
        raise ValueError(
            "SONIC wrists must have shape "
            f"{SONIC_V3_WRIST_SHAPE}, got {wrists.shape}"
        )

    if not np.all(
        np.isfinite(
            wrists
        )
    ):
        raise ValueError(
            "SONIC wrists contain non-finite values"
        )

    return wrists


def inject_wrists_into_bridge_fields(
    fields,
    wrists,
    *,
    copy_fields: bool = True,
):
    """Replace only the bridge's Protocol-v3 `wrists` field.

    Existing body/root/gravity-derived data is deliberately left
    untouched.

    The final protected-bridge promotion will use this same contract:
        fields["wrists"] = (1,6) float32

    No publishing occurs here.
    """

    if not isinstance(
        fields,
        dict,
    ):
        raise TypeError(
            "fields must be a dict"
        )

    required = (
        "smpl_joints",
        "body_quat",
        "smpl_pose",
        "wrists",
    )

    missing = [
        key
        for key in required
        if key not in fields
    ]

    if missing:
        raise KeyError(
            f"bridge fields missing keys: {missing}"
        )

    wrists = validate_sonic_wrists(
        wrists
    )

    if copy_fields:
        out = deepcopy(
            fields
        )
    else:
        out = fields

    out[
        "wrists"
    ] = wrists.copy()

    return out


class SonicV3WristIntegration:
    """Thin integration layer around the completed Q5 controller.

    This object does not modify SMPL body data and does not publish.

    Typical final live use:

        q5.initialize_neutral(calibration_timestamp)

        q5.update_side(...)
        q5.update_side(...)

        fields = body_bridge.convert(...)
        fields = q5_adapter.inject(fields)

        publisher.publish(fields)
    """

    def __init__(
        self,
        *,
        teleop_max_speed_rad_s,
        max_dt_s,
    ):
        self.controller = (
            G1WristControlRuntime(
                teleop_max_speed_rad_s=
                    teleop_max_speed_rad_s,
                max_dt_s=
                    max_dt_s,
            )
        )

    def initialize_neutral(
        self,
        timestamp_s,
    ):
        self.controller.initialize_neutral(
            timestamp_s
        )

    def reset(
        self,
    ):
        self.controller.reset()

    def update_side(
        self,
        side,
        timestamp_s,
        R_canonical,
        *,
        trust_state,
        authority,
    ):
        return self.controller.update_side(
            side,
            timestamp_s,
            R_canonical,
            trust_state=
                trust_state,
            authority=
                authority,
        )

    def wrists(
        self,
    ) -> np.ndarray:
        return validate_sonic_wrists(
            self.controller.sonic_wrists()
        )

    def inject(
        self,
        fields,
        *,
        copy_fields=True,
    ):
        return inject_wrists_into_bridge_fields(
            fields,
            self.wrists(),
            copy_fields=
                copy_fields,
        )
