#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Callable, Iterable


class CameraSelectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class CameraDevice:
    devnode: str
    name: str
    vendor_id: str
    model_id: str
    serial_short: str | None
    by_id: tuple[str, ...]
    by_path: tuple[str, ...]
    stable_id: str
    preferred_path: str

    @property
    def location_hint(self) -> str:
        if self.serial_short:
            return f"serial {self.serial_short}"

        if self.by_path:
            return Path(
                self.by_path[0]
            ).name

        return self.devnode

    @property
    def display_name(self) -> str:
        return (
            f"{self.name} "
            f"[{self.location_hint}]"
        )


def _run(
    args: list[str],
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def _udev_properties(
    devnode: str,
) -> dict[str, str]:

    result = _run(
        [
            "udevadm",
            "info",
            "--query=property",
            f"--name={devnode}",
        ]
    )

    if result.returncode != 0:
        return {}

    props: dict[str, str] = {}

    for raw in result.stdout.splitlines():
        if "=" not in raw:
            continue

        key, value = raw.split(
            "=",
            1,
        )

        props[key] = value

    return props


def _stable_links(
    directory: Path,
) -> dict[str, list[str]]:

    result: dict[str, list[str]] = {}

    if not directory.is_dir():
        return result

    for link in sorted(
        directory.iterdir()
    ):
        if not link.is_symlink():
            continue

        try:
            resolved = str(
                link.resolve(
                    strict=True
                )
            )
        except FileNotFoundError:
            continue

        result.setdefault(
            resolved,
            [],
        ).append(
            str(link)
        )

    return result


def _video_index_from_links(
    links: Iterable[str],
) -> int:

    for link in links:
        match = re.search(
            r"video-index(\d+)$",
            link,
        )

        if match:
            return int(
                match.group(1)
            )

    return 0


def build_stable_identity(
    *,
    devnode: str,
    vendor_id: str,
    model_id: str,
    serial_short: str | None,
    by_id: tuple[str, ...],
    by_path: tuple[str, ...],
) -> tuple[str, str]:

    # A real hardware serial survives USB-port changes.
    if serial_short:
        endpoint_index = (
            _video_index_from_links(
                by_id
                or by_path
            )
        )

        stable_id = (
            "serial:"
            f"{vendor_id}:"
            f"{model_id}:"
            f"{serial_short}:"
            f"video-index{endpoint_index}"
        )

        if by_id:
            preferred_path = by_id[0]
        elif by_path:
            preferred_path = by_path[0]
        else:
            preferred_path = devnode

        return (
            stable_id,
            preferred_path,
        )

    # Without a real serial, by-id can collide for two
    # identical USB cameras. Physical USB topology is then
    # the only stable way Linux gives us to distinguish them.
    if by_path:
        stable_id = (
            "path:"
            + Path(
                by_path[0]
            ).name
        )

        return (
            stable_id,
            by_path[0],
        )

    # Last-resort fallback. It is deliberately explicit:
    # /dev/videoN is not considered persistent.
    return (
        "volatile:"
        + Path(devnode).name,
        devnode,
    )


def discover_cameras(
) -> list[CameraDevice]:

    by_id_map = _stable_links(
        Path(
            "/dev/v4l/by-id"
        )
    )

    by_path_map = _stable_links(
        Path(
            "/dev/v4l/by-path"
        )
    )

    devices: list[CameraDevice] = []

    for path in sorted(
        Path("/dev").glob(
            "video*"
        )
    ):
        devnode = str(path)

        props = (
            _udev_properties(
                devnode
            )
        )

        capabilities = props.get(
            "ID_V4L_CAPABILITIES",
            "",
        )

        # Ignore metadata-only companion nodes.
        if "capture" not in capabilities:
            continue

        by_id = tuple(
            sorted(
                by_id_map.get(
                    devnode,
                    [],
                )
            )
        )

        by_path = tuple(
            sorted(
                by_path_map.get(
                    devnode,
                    [],
                )
            )
        )

        serial_short = (
            props.get(
                "ID_SERIAL_SHORT",
                "",
            ).strip()
            or None
        )

        vendor_id = props.get(
            "ID_VENDOR_ID",
            "unknown",
        )

        model_id = props.get(
            "ID_MODEL_ID",
            "unknown",
        )

        name = (
            props.get(
                "ID_V4L_PRODUCT"
            )
            or props.get(
                "ID_MODEL"
            )
            or path.name
        )

        stable_id, preferred_path = (
            build_stable_identity(
                devnode=devnode,
                vendor_id=vendor_id,
                model_id=model_id,
                serial_short=(
                    serial_short
                ),
                by_id=by_id,
                by_path=by_path,
            )
        )

        devices.append(
            CameraDevice(
                devnode=devnode,
                name=name,
                vendor_id=vendor_id,
                model_id=model_id,
                serial_short=(
                    serial_short
                ),
                by_id=by_id,
                by_path=by_path,
                stable_id=(
                    stable_id
                ),
                preferred_path=(
                    preferred_path
                ),
            )
        )

    devices.sort(
        key=lambda item: (
            item.name.lower(),
            item.stable_id,
        )
    )

    return devices


def load_preference(
    state_file: Path,
) -> str | None:

    if not state_file.exists():
        return None

    try:
        data = json.loads(
            state_file.read_text()
        )
    except Exception as exc:
        raise CameraSelectionError(
            "Could not read saved camera "
            f"preference {state_file}: {exc}"
        ) from exc

    stable_id = data.get(
        "stable_id"
    )

    if not isinstance(
        stable_id,
        str,
    ):
        raise CameraSelectionError(
            "Saved camera preference "
            "does not contain a valid stable_id"
        )

    return stable_id


def save_preference(
    state_file: Path,
    device: CameraDevice,
) -> None:

    state_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = {
        "format_version": 1,
        "stable_id": (
            device.stable_id
        ),
        "display_name": (
            device.display_name
        ),
        "preferred_path": (
            device.preferred_path
        ),
    }

    tmp = state_file.with_suffix(
        state_file.suffix
        + ".tmp"
    )

    tmp.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    tmp.replace(
        state_file
    )


def interactive_chooser(
    devices: list[CameraDevice],
    *,
    preferred_missing: bool,
) -> int:

    print(
        "",
        file=sys.stderr,
    )

    if preferred_missing:
        print(
            "The previously selected camera "
            "is not connected.",
            file=sys.stderr,
        )

        print(
            "Camera Pose Teleop will NOT "
            "silently switch cameras.",
            file=sys.stderr,
        )

    print(
        "Available RGB capture cameras:",
        file=sys.stderr,
    )

    for index, device in enumerate(
        devices,
        start=1,
    ):
        print(
            f"  [{index}] "
            f"{device.display_name}",
            file=sys.stderr,
        )

        print(
            f"      device: "
            f"{device.preferred_path}",
            file=sys.stderr,
        )

        print(
            f"      stable: "
            f"{device.stable_id}",
            file=sys.stderr,
        )

    while True:
        try:
            print(
                "Select camera number: ",
                end="",
                file=sys.stderr,
                flush=True,
            )

            raw = input().strip()

        except EOFError as exc:
            raise CameraSelectionError(
                "Camera selection requires "
                "interactive input"
            ) from exc

        try:
            selected = int(raw)
        except ValueError:
            print(
                "Please enter a number.",
                file=sys.stderr,
            )
            continue

        if (
            1
            <= selected
            <= len(devices)
        ):
            return (
                selected - 1
            )

        print(
            "Selection out of range.",
            file=sys.stderr,
        )


def select_device(
    devices: list[CameraDevice],
    *,
    saved_stable_id: str | None,
    chooser: Callable[
        [list[CameraDevice], bool],
        int,
    ] | None = None,
) -> tuple[
    CameraDevice,
    str,
]:

    if not devices:
        raise CameraSelectionError(
            "No usable V4L2 video-capture "
            "camera was detected"
        )

    if saved_stable_id is not None:
        for device in devices:
            if (
                device.stable_id
                == saved_stable_id
            ):
                return (
                    device,
                    "saved_preference",
                )

        # A remembered camera disappearing is
        # intentionally NOT an automatic fallback.
        if chooser is None:
            raise CameraSelectionError(
                "Saved camera is missing and "
                "no chooser was provided"
            )

        selected_index = chooser(
            devices,
            True,
        )

        return (
            devices[
                selected_index
            ],
            "preferred_missing_user_selection",
        )

    if len(devices) == 1:
        return (
            devices[0],
            "single_camera_auto",
        )

    if chooser is None:
        raise CameraSelectionError(
            "Multiple cameras detected and "
            "no chooser was provided"
        )

    selected_index = chooser(
        devices,
        False,
    )

    return (
        devices[
            selected_index
        ],
        "multi_camera_user_selection",
    )


def print_devices(
    devices: list[CameraDevice],
) -> None:

    print(
        f"usable capture cameras: "
        f"{len(devices)}"
    )

    for index, device in enumerate(
        devices,
        start=1,
    ):
        print()
        print(
            f"[{index}] "
            f"{device.display_name}"
        )
        print(
            f"  devnode:   "
            f"{device.devnode}"
        )
        print(
            f"  selected:  "
            f"{device.preferred_path}"
        )
        print(
            f"  stable id: "
            f"{device.stable_id}"
        )
        print(
            f"  by-id:     "
            f"{list(device.by_id)}"
        )
        print(
            f"  by-path:   "
            f"{list(device.by_path)}"
        )



@dataclass(frozen=True)
class CameraMode:
    fourcc: str
    ffmpeg_format: str
    width: int
    height: int
    fps: float

    @property
    def description(self) -> str:
        return (
            f"{self.width}x{self.height} "
            f"{self.fps:.3f} fps "
            f"{self.fourcc}"
        )


_FFMPEG_FORMATS = {
    "MJPG": "mjpeg",
    "YUYV": "yuyv422",
}


def parse_v4l2_formats(
    text: str,
) -> list[CameraMode]:

    format_re = re.compile(
        r"^\s*\[\d+\]:\s*'([^']+)'"
    )

    size_re = re.compile(
        r"^\s*Size:\s*Discrete\s+"
        r"(\d+)x(\d+)"
    )

    fps_re = re.compile(
        r"^\s*Interval:.*"
        r"\(([\d.]+)\s+fps\)"
    )

    current_fourcc: str | None = None
    current_size: tuple[int, int] | None = None

    modes: list[CameraMode] = []

    for line in text.splitlines():

        match = format_re.match(line)

        if match:
            current_fourcc = (
                match.group(1)
                .strip()
                .upper()
            )

            current_size = None
            continue

        match = size_re.match(line)

        if match:
            current_size = (
                int(match.group(1)),
                int(match.group(2)),
            )

            continue

        match = fps_re.match(line)

        if (
            match
            and current_fourcc is not None
            and current_size is not None
        ):
            ffmpeg_format = (
                _FFMPEG_FORMATS.get(
                    current_fourcc
                )
            )

            if ffmpeg_format is None:
                continue

            fps = float(
                match.group(1)
            )

            modes.append(
                CameraMode(
                    fourcc=current_fourcc,
                    ffmpeg_format=(
                        ffmpeg_format
                    ),
                    width=(
                        current_size[0]
                    ),
                    height=(
                        current_size[1]
                    ),
                    fps=fps,
                )
            )

    unique: dict[
        tuple[str, int, int, float],
        CameraMode,
    ] = {}

    for mode in modes:
        key = (
            mode.fourcc,
            mode.width,
            mode.height,
            round(
                mode.fps,
                6,
            ),
        )

        unique[key] = mode

    return sorted(
        unique.values(),
        key=lambda mode: (
            mode.fourcc,
            mode.width,
            mode.height,
            mode.fps,
        ),
    )


def probe_camera_modes(
    device: str,
) -> list[CameraMode]:

    result = _run(
        [
            "v4l2-ctl",
            f"--device={device}",
            "--list-formats-ext",
        ]
    )

    if result.returncode != 0:
        raise CameraSelectionError(
            "Could not query capture modes for "
            f"{device}: "
            f"{result.stderr.strip()}"
        )

    modes = parse_v4l2_formats(
        result.stdout
    )

    if not modes:
        raise CameraSelectionError(
            "No supported MJPEG/YUYV capture "
            f"modes were found for {device}"
        )

    return modes


def _mode_category(
    mode: CameraMode,
) -> int:

    is_mjpeg = (
        mode.fourcc == "MJPG"
    )

    at_least_30 = (
        mode.fps >= 29.0
    )

    exact_720p = (
        mode.width == 1280
        and mode.height == 720
    )

    if (
        is_mjpeg
        and exact_720p
        and at_least_30
    ):
        return 0

    if (
        is_mjpeg
        and at_least_30
    ):
        return 1

    if is_mjpeg:
        return 2

    if at_least_30:
        return 3

    return 4


def choose_camera_mode(
    modes: list[CameraMode],
) -> CameraMode:

    usable = [
        mode
        for mode in modes
        if (
            mode.width >= 640
            and mode.height >= 360
            and mode.fps >= 14.0
            and mode.fourcc
            in _FFMPEG_FORMATS
        )
    ]

    if not usable:
        raise CameraSelectionError(
            "Camera has no practical supported "
            "capture mode. Need at least "
            "640x360, 15-ish fps, and "
            "MJPEG or YUYV."
        )

    target_width = 1280
    target_height = 720
    target_area = (
        target_width
        * target_height
    )

    target_aspect = (
        target_width
        / target_height
    )

    def score(
        mode: CameraMode,
    ) -> tuple[
        int,
        float,
        float,
        float,
        int,
    ]:

        aspect = (
            mode.width
            / mode.height
        )

        aspect_error = abs(
            aspect
            - target_aspect
        )

        area = (
            mode.width
            * mode.height
        )

        area_error = abs(
            area
            - target_area
        ) / target_area

        fps_error = abs(
            mode.fps
            - 30.0
        )

        # Last tie-breaker prefers more image pixels.
        return (
            _mode_category(
                mode
            ),
            aspect_error,
            area_error,
            fps_error,
            -area,
        )

    return min(
        usable,
        key=score,
    )


def choose_camera_mode_override(
    modes: list[CameraMode],
    override: str,
) -> CameraMode:
    """
    Resolve an explicit, validated camera mode.

    Syntax:
        WIDTHxHEIGHT@FPS:FORMAT

    Example:
        640x480@30:mjpeg

    The requested mode must actually be advertised by
    the selected V4L2 camera. Nothing is fabricated.
    """

    value = str(
        override
    ).strip()

    try:
        geometry_fps, requested_format = (
            value.rsplit(
                ":",
                1,
            )
        )

        geometry, fps_text = (
            geometry_fps.rsplit(
                "@",
                1,
            )
        )

        width_text, height_text = (
            geometry.lower().split(
                "x",
                1,
            )
        )

        requested_width = int(
            width_text
        )

        requested_height = int(
            height_text
        )

        requested_fps = float(
            fps_text
        )

        requested_format = (
            requested_format
            .strip()
            .lower()
        )

    except Exception as exc:
        raise CameraSelectionError(
            "Invalid CAMERA_PROFILE_OVERRIDE "
            f"{value!r}. Expected "
            "WIDTHxHEIGHT@FPS:FORMAT, for example "
            "640x480@30:mjpeg."
        ) from exc

    if (
        requested_width <= 0
        or requested_height <= 0
        or requested_fps <= 0.0
        or not requested_format
    ):
        raise CameraSelectionError(
            "Invalid CAMERA_PROFILE_OVERRIDE "
            f"{value!r}. Width, height and FPS "
            "must be positive."
        )

    supported_formats = set(
        _FFMPEG_FORMATS.values()
    )

    if (
        requested_width < 640
        or requested_height < 360
        or requested_fps < 14.0
        or requested_format
        not in supported_formats
    ):
        raise CameraSelectionError(
            "Requested camera profile is not "
            "a practical supported capture mode: "
            f"{value}. Need at least 640x360, "
            "15-ish fps, and MJPEG or YUYV."
        )

    matches = [
        mode
        for mode in modes
        if (
            mode.width
            == requested_width
            and mode.height
            == requested_height
            and abs(
                mode.fps
                - requested_fps
            )
            <= 0.05
            and mode.ffmpeg_format.lower()
            == requested_format
            and mode.fourcc
            in _FFMPEG_FORMATS
        )
    ]

    if not matches:
        available = sorted(
            {
                (
                    mode.width,
                    mode.height,
                    mode.fps,
                    mode.ffmpeg_format,
                    mode.fourcc,
                )
                for mode in modes
            }
        )

        relevant = [
            (
                width,
                height,
                fps,
                ffmpeg_format,
                fourcc,
            )
            for (
                width,
                height,
                fps,
                ffmpeg_format,
                fourcc,
            )
            in available
            if (
                width
                == requested_width
                and height
                == requested_height
            )
        ]

        if relevant:
            choices = ", ".join(
                (
                    f"{width}x{height}"
                    f"@{fps:.3f}:"
                    f"{ffmpeg_format}"
                    f" ({fourcc})"
                )
                for (
                    width,
                    height,
                    fps,
                    ffmpeg_format,
                    fourcc,
                )
                in relevant
            )

            detail = (
                " Modes at the requested resolution: "
                + choices
            )

        else:
            detail = (
                " The camera advertises no mode at "
                f"{requested_width}x"
                f"{requested_height}."
            )

        raise CameraSelectionError(
            "Requested camera profile is not "
            "advertised by this camera: "
            f"{value}.{detail}"
        )

    # Prefer a deterministic first match if multiple V4L2
    # entries normalize to the same FFmpeg input format.
    return sorted(
        matches,
        key=lambda mode: (
            mode.fourcc,
            mode.width,
            mode.height,
            mode.fps,
        ),
    )[0]


def resolve_camera_mode(
    device: str,
) -> CameraMode:

    modes = probe_camera_modes(
        device
    )

    return choose_camera_mode(
        modes
    )


def print_camera_modes(
    modes: list[CameraMode],
) -> None:

    for mode in modes:
        print(
            "  "
            + mode.description
            + " -> "
            + mode.ffmpeg_format
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Camera Pose Teleop "
            "V4L2 camera selector"
        )
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser(
        "list",
        help=(
            "List usable V4L2 "
            "capture cameras"
        ),
    )

    profile_parser = sub.add_parser(
        "profile",
        help=(
            "Resolve a compatible capture "
            "profile for one camera"
        ),
    )

    profile_parser.add_argument(
        "--device",
        required=True,
    )

    profile_parser.add_argument(
        "--shell",
        action="store_true",
    )

    profile_parser.add_argument(
        "--list-modes",
        action="store_true",
    )

    profile_parser.add_argument(
        "--override",
        default=None,
        help=(
            "Require one exact advertised mode: "
            "WIDTHxHEIGHT@FPS:FORMAT, e.g. "
            "640x480@30:mjpeg"
        ),
    )

    select_parser = (
        sub.add_parser(
            "select",
            help=(
                "Resolve/select a camera"
            ),
        )
    )

    select_parser.add_argument(
        "--state-file",
        required=True,
        type=Path,
    )

    select_parser.add_argument(
        "--shell",
        action="store_true",
    )

    select_parser.add_argument(
        "--reselect",
        action="store_true",
        help=(
            "Ignore any saved camera preference "
            "and ask the user to choose again"
        ),
    )

    args = parser.parse_args()

    devices = discover_cameras()

    if args.command == "list":
        print_devices(
            devices
        )
        return

    if args.command == "profile":
        try:
            modes = probe_camera_modes(
                args.device
            )

            if args.override:
                selected_mode = (
                    choose_camera_mode_override(
                        modes,
                        args.override,
                    )
                )
            else:
                selected_mode = (
                    choose_camera_mode(
                        modes
                    )
                )

        except CameraSelectionError as exc:
            print(
                "CAMERA PROFILE FAILED:",
                exc,
                file=sys.stderr,
            )

            raise SystemExit(2)

        if args.list_modes:
            print(
                "Supported practical input modes:",
                file=sys.stderr,
            )

            print_camera_modes(
                modes
            )

        if args.shell:
            values = {
                "CAMERA_WIDTH":
                    str(
                        selected_mode.width
                    ),

                "CAMERA_HEIGHT":
                    str(
                        selected_mode.height
                    ),

                "CAMERA_FPS":
                    (
                        f"{selected_mode.fps:.6f}"
                    ),

                "CAMERA_FORMAT":
                    (
                        selected_mode.ffmpeg_format
                    ),

                "CAMERA_FOURCC":
                    (
                        selected_mode.fourcc
                    ),
            }

            for key, value in values.items():
                print(
                    f"{key}="
                    f"{shlex.quote(value)}"
                )

        else:
            print(
                "Selected capture profile:",
                selected_mode.description,
            )

            print(
                "FFmpeg input format:",
                selected_mode.ffmpeg_format,
            )

        return

    try:
        if args.reselect:
            saved = None
        else:
            saved = load_preference(
                args.state_file
            )

        def chooser(
            available: list[CameraDevice],
            preferred_missing: bool,
        ) -> int:
            return interactive_chooser(
                available,
                preferred_missing=(
                    preferred_missing
                ),
            )

        selected, reason = (
            select_device(
                devices,
                saved_stable_id=saved,
                chooser=chooser,
            )
        )

        save_preference(
            args.state_file,
            selected,
        )

    except CameraSelectionError as exc:
        print(
            "CAMERA SELECTION FAILED:",
            exc,
            file=sys.stderr,
        )

        raise SystemExit(2)

    if args.shell:
        values = {
            "CAMERA_DEVICE": (
                selected.preferred_path
            ),
            "CAMERA_STABLE_ID": (
                selected.stable_id
            ),
            "CAMERA_DISPLAY_NAME": (
                selected.display_name
            ),
            "CAMERA_SELECTION_REASON": (
                reason
            ),
        }

        for key, value in values.items():
            print(
                f"{key}="
                f"{shlex.quote(value)}"
            )

    else:
        print(
            "Selected:",
            selected.display_name,
        )

        print(
            "device:",
            selected.preferred_path,
        )

        print(
            "stable id:",
            selected.stable_id,
        )

        print(
            "reason:",
            reason,
        )


if __name__ == "__main__":
    main()
