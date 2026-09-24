#!/usr/bin/env python3

from __future__ import annotations

import os
from pathlib import Path
import time

from supervisor import V2Supervisor


HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parents[3]


FAKE_COMMAND = [
    "bash",
    "-lc",
    r"""
printf '%s\n' \
'GPU components loaded: PASS' \
'CAMERA OPEN — STAND NEUTRAL' \
'camera negotiated: 1280x720 30.000 fps '\''MJPG'\''/mjpeg via FFmpeg -> BGR24' \
'FULL-BODY FRAMING CHECK: ENABLED' \
'Stable observations: 8/8' \
'FULL-BODY FRAMING: STABLE' \
'prefill 30/30 span=2.000s' \
'FULL-BODY FRAMING: PASS' \
'Warming temporal GVHMR on the real neutral window...' \
'temporal warmup: 100.0 ms' \
'CAMERA POSE TELEOP V2 — NEUTRAL ALIGNMENT' \
'Valid frames: 25 / 25' \
'Angular spread: 0.171 deg' \
'Confidence: 0.979' \
'CAMERA ALIGNMENT PASSED' \
'TELEOP STREAM MAY START.' \
'SONIC bridge: CREATED' \
'Protocol-v3 publisher worker bound to tcp://*:5556 topic=pose'

sleep 60
""",
]


supervisor = V2Supervisor(
    REPO_ROOT,
    command_override=FAKE_COMMAND,
)

result = supervisor.start()

assert result["ok"], result

pid = result["pid"]
pgid = result["pgid"]

deadline = (
    time.monotonic()
    + 4.0
)

while (
    time.monotonic()
    < deadline
):
    state = (
        supervisor.snapshot_state()
    )

    if (
        state[
            "publisher"
        ][
            "state"
        ]
        == "active"
    ):
        break

    time.sleep(
        0.05
    )

state = supervisor.snapshot_state()

assert state["camera"]["state"] == "ready"
assert state["gvhmr"]["state"] == "ready"
assert state["framing"]["state"] == "ready"
assert state["alignment"]["state"] == "ready"
assert state["alignment"]["valid_frames"] == 25
assert state["alignment"]["confidence"] == 0.979
assert state["sonic_bridge"]["state"] == "ready"
assert state["publisher"]["state"] == "active"
assert state["teleop"]["state"] == "running"
assert state["teleop"]["process_alive"] is True
assert state["teleop"]["running"] is True

run_log = state["teleop"]["last_run_log"]

assert run_log is not None
assert Path(run_log).is_file()

print(
    "D3B_SYNTHETIC_STATE_PARSER=PASS"
)

stop_result = supervisor.stop(
    reason="software_test"
)

assert stop_result["ok"]

deadline = (
    time.monotonic()
    + 3.0
)

while (
    time.monotonic()
    < deadline
    and
    supervisor.is_running()
):
    time.sleep(
        0.05
    )

assert not supervisor.is_running()

state = supervisor.snapshot_state()

assert state["teleop"]["state"] == "off"
assert state["teleop"]["process_alive"] is False
assert state["teleop"]["running"] is False
assert state["camera"]["state"] == "off"
assert state["gvhmr"]["state"] == "off"
assert state["sonic_bridge"]["state"] == "off"
assert state["publisher"]["state"] == "off"

try:
    os.killpg(
        pgid,
        0,
    )
except ProcessLookupError:
    group_alive = False
else:
    group_alive = True

assert not group_alive

print(
    "D3B_PROCESS_GROUP_CLEANUP=PASS"
)

logs = supervisor.snapshot_logs()

assert any(
    "CAMERA ALIGNMENT PASSED"
    in item["line"]
    for item in logs
)

assert any(
    "Protocol-v3 publisher worker bound"
    in item["line"]
    for item in logs
)

print(
    "D3B_RUNTIME_LOG_CAPTURE=PASS"
)

persisted = Path(
    run_log
).read_text()

assert (
    "CAMERA ALIGNMENT PASSED"
    in persisted
)

assert (
    "Protocol-v3 publisher worker bound"
    in persisted
)

print(
    "D3C6_PERSISTENT_RUN_LOG=PASS"
)

print(
    "D3B_SUPERVISOR_TEST=PASS"
)
