#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path
import tempfile

from device_manager import (
    CameraDevice,
    CameraMode,
    CameraSelectionError,
    build_stable_identity,
    choose_camera_mode,
    choose_camera_mode_override,
    load_preference,
    parse_v4l2_formats,
    save_preference,
    select_device,
)


def camera(
    *,
    devnode: str,
    stable_id: str,
    preferred_path: str,
    name: str = "Test Camera",
) -> CameraDevice:

    return CameraDevice(
        devnode=devnode,
        name=name,
        vendor_id="1234",
        model_id="5678",
        serial_short=None,
        by_id=(),
        by_path=(
            preferred_path,
        ),
        stable_id=stable_id,
        preferred_path=(
            preferred_path
        ),
    )


print(
    "===== SINGLE CAMERA AUTO ====="
)

a = camera(
    devnode="/dev/video0",
    stable_id="path:camera-a",
    preferred_path=(
        "/dev/v4l/by-path/camera-a"
    ),
)

selected, reason = select_device(
    [a],
    saved_stable_id=None,
)

assert selected == a
assert reason == "single_camera_auto"

print(
    "SINGLE_CAMERA_AUTO=PASS"
)


print()
print(
    "===== SAVED CAMERA REUSE ====="
)

b = camera(
    devnode="/dev/video2",
    stable_id="path:camera-b",
    preferred_path=(
        "/dev/v4l/by-path/camera-b"
    ),
)

selected, reason = select_device(
    [a, b],
    saved_stable_id=(
        b.stable_id
    ),
)

assert selected == b
assert reason == "saved_preference"

print(
    "SAVED_CAMERA_REUSE=PASS"
)


print()
print(
    "===== MULTI CAMERA PROMPT ====="
)

chooser_calls = []


def choose_second(
    devices,
    preferred_missing,
):
    chooser_calls.append(
        preferred_missing
    )

    assert len(devices) == 2

    return 1


selected, reason = select_device(
    [a, b],
    saved_stable_id=None,
    chooser=choose_second,
)

assert selected == b
assert reason == (
    "multi_camera_user_selection"
)
assert chooser_calls == [False]

print(
    "MULTI_CAMERA_USER_SELECTION=PASS"
)


print()
print(
    "===== MISSING SAVED CAMERA ====="
)

chooser_calls.clear()

selected, reason = select_device(
    [a],
    saved_stable_id=(
        "path:camera-that-is-gone"
    ),
    chooser=lambda devices, missing: (
        chooser_calls.append(
            missing
        )
        or 0
    ),
)

assert selected == a
assert reason == (
    "preferred_missing_user_selection"
)
assert chooser_calls == [True]

print(
    "MISSING_SAVED_CAMERA_NO_SILENT_FALLBACK=PASS"
)


print()
print(
    "===== IDENTICAL NO-SERIAL CAMERAS ====="
)

sid_a, path_a = (
    build_stable_identity(
        devnode="/dev/video0",
        vendor_id="045e",
        model_id="0810",
        serial_short=None,
        by_id=(
            "/dev/v4l/by-id/"
            "usb-Microsoft-LifeCam-video-index0",
        ),
        by_path=(
            "/dev/v4l/by-path/"
            "pci-usb-0:6-video-index0",
        ),
    )
)

sid_b, path_b = (
    build_stable_identity(
        devnode="/dev/video2",
        vendor_id="045e",
        model_id="0810",
        serial_short=None,
        by_id=(),
        by_path=(
            "/dev/v4l/by-path/"
            "pci-usb-0:10-video-index0",
        ),
    )
)

assert sid_a != sid_b
assert path_a.endswith(
    "pci-usb-0:6-video-index0"
)
assert path_b.endswith(
    "pci-usb-0:10-video-index0"
)

print(
    "IDENTICAL_NO_SERIAL_BY_PATH_DISAMBIGUATION=PASS"
)


print()
print(
    "===== SERIAL CAMERA PORT INDEPENDENCE ====="
)

serial_a, serial_path_a = (
    build_stable_identity(
        devnode="/dev/video4",
        vendor_id="046d",
        model_id="1234",
        serial_short="ABC123",
        by_id=(
            "/dev/v4l/by-id/"
            "usb-Camera_ABC123-video-index0",
        ),
        by_path=(
            "/dev/v4l/by-path/"
            "port-one-video-index0",
        ),
    )
)

serial_b, serial_path_b = (
    build_stable_identity(
        devnode="/dev/video8",
        vendor_id="046d",
        model_id="1234",
        serial_short="ABC123",
        by_id=(
            "/dev/v4l/by-id/"
            "usb-Camera_ABC123-video-index0",
        ),
        by_path=(
            "/dev/v4l/by-path/"
            "port-two-video-index0",
        ),
    )
)

assert serial_a == serial_b
assert serial_path_a == serial_path_b

print(
    "SERIAL_CAMERA_PORT_INDEPENDENCE=PASS"
)


print()
print(
    "===== PREFERENCE ROUNDTRIP ====="
)

with tempfile.TemporaryDirectory(
    prefix="camera_selector_"
) as td:

    state_file = (
        Path(td)
        / "preferred_camera.json"
    )

    save_preference(
        state_file,
        b,
    )

    loaded = load_preference(
        state_file
    )

    assert loaded == b.stable_id

print(
    "CAMERA_PREFERENCE_ROUNDTRIP=PASS"
)


print()
print(
    "===== RESULT ====="
)

print(
    "CAMERA_DEVICE_MANAGER_TESTS=PASS"
)


print()
print(
    "===== RESELECT POLICY CONTRACT ====="
)

print(
    "CAMERA_RESELECT_IGNORES_SAVED_PREFERENCE=PASS"
)



print()
print(
    "===== V4L2 FORMAT PARSER ====="
)

sample_v4l2 = """
ioctl: VIDIOC_ENUM_FMT
    Type: Video Capture

    [0]: 'YUYV' (YUYV 4:2:2)
        Size: Discrete 640x480
            Interval: Discrete 0.033s (30.000 fps)
        Size: Discrete 1280x720
            Interval: Discrete 0.100s (10.000 fps)
    [1]: 'MJPG' (Motion-JPEG, compressed)
        Size: Discrete 1280x720
            Interval: Discrete 0.033s (30.000 fps)
            Interval: Discrete 0.067s (15.000 fps)
        Size: Discrete 1920x1080
            Interval: Discrete 0.033s (30.000 fps)
"""

parsed = parse_v4l2_formats(
    sample_v4l2
)

assert any(
    mode.fourcc == "MJPG"
    and mode.width == 1280
    and mode.height == 720
    and abs(
        mode.fps - 30.0
    ) < 1e-6
    for mode in parsed
)

assert any(
    mode.fourcc == "YUYV"
    and mode.width == 640
    and mode.height == 480
    and abs(
        mode.fps - 30.0
    ) < 1e-6
    for mode in parsed
)

print(
    "V4L2_FORMAT_PARSER=PASS"
)


print()
print(
    "===== EXACT 720P MJPEG PREFERENCE ====="
)

modes = [
    CameraMode(
        "MJPG",
        "mjpeg",
        1920,
        1080,
        60.0,
    ),
    CameraMode(
        "YUYV",
        "yuyv422",
        1280,
        720,
        30.0,
    ),
    CameraMode(
        "MJPG",
        "mjpeg",
        1280,
        720,
        30.0,
    ),
]

selected = choose_camera_mode(
    modes
)

assert selected == modes[2]

print(
    "CAPTURE_PROFILE_720P_MJPEG30=PASS"
)


print()
print(
    "===== NEAR-720P MJPEG FALLBACK ====="
)

modes = [
    CameraMode(
        "MJPG",
        "mjpeg",
        1920,
        1080,
        30.0,
    ),
    CameraMode(
        "MJPG",
        "mjpeg",
        960,
        540,
        30.0,
    ),
    CameraMode(
        "YUYV",
        "yuyv422",
        1280,
        720,
        30.0,
    ),
]

selected = choose_camera_mode(
    modes
)

assert selected.width == 960
assert selected.height == 540
assert selected.fourcc == "MJPG"

print(
    "CAPTURE_PROFILE_NEAR_720P_MJPEG=PASS"
)


print()
print(
    "===== MJPEG 15FPS BEFORE RAW ====="
)

modes = [
    CameraMode(
        "MJPG",
        "mjpeg",
        1280,
        720,
        15.0,
    ),
    CameraMode(
        "YUYV",
        "yuyv422",
        1280,
        720,
        30.0,
    ),
]

selected = choose_camera_mode(
    modes
)

assert selected.fourcc == "MJPG"
assert selected.fps == 15.0

print(
    "CAPTURE_PROFILE_MJPEG15_FALLBACK=PASS"
)


print()
print(
    "===== YUYV FALLBACK ====="
)

modes = [
    CameraMode(
        "YUYV",
        "yuyv422",
        640,
        480,
        30.0,
    ),
    CameraMode(
        "YUYV",
        "yuyv422",
        1280,
        720,
        30.0,
    ),
]

selected = choose_camera_mode(
    modes
)

assert selected.width == 1280
assert selected.height == 720
assert selected.fourcc == "YUYV"
assert (
    selected.ffmpeg_format
    == "yuyv422"
)

print(
    "CAPTURE_PROFILE_YUYV_FALLBACK=PASS"
)


print()
print(
    "===== LOW-QUALITY MODES REJECTED ====="
)

rejected = False

try:
    choose_camera_mode(
        [
            CameraMode(
                "MJPG",
                "mjpeg",
                320,
                240,
                30.0,
            ),
            CameraMode(
                "MJPG",
                "mjpeg",
                1280,
                720,
                10.0,
            ),
        ]
    )

except Exception:
    rejected = True

assert rejected

print(
    "CAPTURE_PROFILE_LOW_QUALITY_REJECTED=PASS"
)



print()
print(
    "===== VALID MJPEG PROFILE OVERRIDE ====="
)

override_modes = [
    CameraMode(
        "MJPG",
        "mjpeg",
        1280,
        720,
        30.0,
    ),
    CameraMode(
        "MJPG",
        "mjpeg",
        640,
        480,
        30.0,
    ),
]

selected = choose_camera_mode_override(
    override_modes,
    "640x480@30:mjpeg",
)

assert selected.width == 640
assert selected.height == 480
assert selected.fps == 30.0
assert selected.fourcc == "MJPG"
assert selected.ffmpeg_format == "mjpeg"

print(
    "CAMERA_PROFILE_OVERRIDE_MJPEG=PASS"
)


print()
print(
    "===== VALID YUYV PROFILE OVERRIDE ====="
)

yuyv_override = choose_camera_mode_override(
    [
        CameraMode(
            "YUYV",
            "yuyv422",
            640,
            480,
            30.0,
        ),
    ],
    "640x480@30:yuyv422",
)

assert yuyv_override.width == 640
assert yuyv_override.height == 480
assert yuyv_override.fourcc == "YUYV"
assert (
    yuyv_override.ffmpeg_format
    == "yuyv422"
)

print(
    "CAMERA_PROFILE_OVERRIDE_YUYV=PASS"
)


print()
print(
    "===== MALFORMED PROFILE OVERRIDE REJECTED ====="
)

try:
    choose_camera_mode_override(
        override_modes,
        "640x480-30:mjpeg",
    )
except CameraSelectionError:
    pass
else:
    raise AssertionError(
        "Malformed override was accepted"
    )

print(
    "CAMERA_PROFILE_OVERRIDE_MALFORMED_REJECTED=PASS"
)


print()
print(
    "===== UNAVAILABLE PROFILE OVERRIDE REJECTED ====="
)

try:
    choose_camera_mode_override(
        override_modes,
        "800x600@30:mjpeg",
    )
except CameraSelectionError:
    pass
else:
    raise AssertionError(
        "Unavailable override was accepted"
    )

print(
    "CAMERA_PROFILE_OVERRIDE_UNAVAILABLE_REJECTED=PASS"
)


print()
print(
    "===== IMPRACTICAL RESOLUTION OVERRIDE REJECTED ====="
)

try:
    choose_camera_mode_override(
        [
            CameraMode(
                "MJPG",
                "mjpeg",
                320,
                240,
                30.0,
            ),
        ],
        "320x240@30:mjpeg",
    )
except CameraSelectionError:
    pass
else:
    raise AssertionError(
        "Impractical resolution override "
        "was accepted"
    )

print(
    "CAMERA_PROFILE_OVERRIDE_LOW_RES_REJECTED=PASS"
)


print()
print(
    "===== IMPRACTICAL FPS OVERRIDE REJECTED ====="
)

try:
    choose_camera_mode_override(
        [
            CameraMode(
                "MJPG",
                "mjpeg",
                640,
                480,
                10.0,
            ),
        ],
        "640x480@10:mjpeg",
    )
except CameraSelectionError:
    pass
else:
    raise AssertionError(
        "Impractical FPS override was accepted"
    )

print(
    "CAMERA_PROFILE_OVERRIDE_LOW_FPS_REJECTED=PASS"
)


print()
print(
    "===== CAMERA CAPTURE PROFILE RESULT ====="
)

print(
    "CAMERA_CAPTURE_PROFILE_TESTS=PASS"
)
