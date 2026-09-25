#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]

OWNER = (
    REPO_ROOT
    / "sonic"
    / "runtime"
    / "live_gvhmr_pair_prio2_sonic_async_interactive.py"
)

BASE = (
    REPO_ROOT
    / "perception"
    / "runtime"
    / "live_gvhmr_pair_prio2_interactive_test.py"
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()

    with path.open("rb") as f:
        while True:
            block = f.read(
                1024 * 1024
            )

            if not block:
                break

            h.update(
                block
            )

    return h.hexdigest()


base_sha = sha256_file(
    BASE
)


# IMPORTANT:
#
# The accepted V2 launcher may already pass wrapper-level options.
# Keep those first, then append the authoritative V3 overrides LAST.
# argparse therefore resolves any duplicated option to the V3 value.

v3_overrides = [
    "--sonic-mode",
    "publish",

    "--base-runner",
    str(BASE),

    "--expected-base-sha",
    base_sha,

    "--sonic-root",
    os.environ["SONIC_ROOT"],

    "--publisher-source-dir",
    str(
        REPO_ROOT
        / "sonic"
        / "publisher"
    ),

    "--sonic-port",
    "5556",

    "--sonic-topic",
    "pose",

    "--alignment-mode",
    "session_v2",

    "--session-alignment",
    os.environ["SESSION_ALIGNMENT_FILE"],

    "--v3-wrists",

    "--v3-wrist-calibrate-startup",

    "--v3-wrist-speed-deg-s",
    "90",

    "--v3-wrist-max-dt-s",
    "0.20",

    "--v3-q4-pair-max-s",
    "0.20",

    "--v3-preview",

    "--v3-preview-port",
    "5602",
]


repo_pythonpath = str(REPO_ROOT)
existing_pythonpath = os.environ.get("PYTHONPATH", "")
os.environ["PYTHONPATH"] = (
    repo_pythonpath
    if not existing_pythonpath
    else repo_pythonpath + os.pathsep + existing_pythonpath
)


argv = [
    sys.executable,
    str(OWNER),

    # Arguments supplied by the accepted V2 launcher.
    *sys.argv[1:],

    # Authoritative V3 overrides.
    *v3_overrides,
]


print()
print(
    "------------------------------------------------------------"
)
print(
    "V3 LIVE PYTHON OWNER SHIM"
)
print(
    "------------------------------------------------------------"
)
print(
    "python=",
    sys.executable,
)
print(
    "owner=",
    OWNER,
)
print(
    "base=",
    BASE,
)
print(
    "base_sha=",
    base_sha,
)
print(
    "alignment=session_v2"
)
print(
    "wrists=enabled"
)
print(
    "wrist_startup_calibration=enabled"
)
print(
    "preview=tcp://127.0.0.1:5602 topic=raw"
)
print(
    "pose=tcp://*:5556 topic=pose"
)
print(
    "cwd=",
    os.getcwd(),
)
print(
    "------------------------------------------------------------"
)
print(
    flush=True
)


os.execv(
    sys.executable,
    argv,
)
