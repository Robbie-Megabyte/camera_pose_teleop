
from __future__ import annotations

from pathlib import Path
import base64
import json
import shlex
import subprocess
import threading
import time


class RobotModeController:

    ACTIONS = {
        "developer",
        "restore_ai",
        "damp",
        "zero_torque",
        "walk",
        "run",
        "climb",
        "stop_motion",
        "sit",
        "stand_from_squat",
        "recover_from_lie",
    }


    def __init__(
        self,
        runtime_dir,
        host="192.168.0.116",
        user="unitree",
        ssh_key=None,
        interface="enP8p1s0",
    ):
        self.runtime_dir = Path(
            runtime_dir
        ).expanduser().resolve()

        self.runtime_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.host = str(host)
        self.user = str(user)
        self.interface = str(interface)

        if ssh_key is None:
            ssh_key = (
                Path.home()
                / ".ssh"
                / "bacalbasa_g1_dashboard_ed25519"
            )

        self.ssh_key = Path(
            ssh_key
        ).expanduser().resolve()

        self.sdk_root = (
            "/home/unitree/"
            "bacalbasa_runtime/"
            "GR00T-WholeBodyControl/"
            "external_dependencies/"
            "unitree_sdk2_python"
        )

        self.log_path = (
            self.runtime_dir
            / "robot_modes.log"
        )

        self._lock = threading.RLock()

        self._busy = False
        self._last_action = None
        self._last_result = None
        self._last_error = None


    def snapshot(
        self,
    ):
        with self._lock:
            return {
                "busy":
                    self._busy,

                "last_action":
                    self._last_action,

                "last_result":
                    self._last_result,

                "last_error":
                    self._last_error,

                "log_path":
                    str(
                        self.log_path
                    ),
            }


    # --------------------------------------------------------
    # SSH
    # --------------------------------------------------------

    def _ssh_base(
        self,
    ):
        return [
            "ssh",
            "-i",
            str(
                self.ssh_key
            ),
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "ConnectTimeout=4",
            "-o",
            "ServerAliveInterval=2",
            "-o",
            "ServerAliveCountMax=3",
            f"{self.user}@{self.host}",
        ]


    def _append_log(
        self,
        text,
    ):
        stamp = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        with self.log_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                f"[{stamp}] {text}\n"
            )


    # --------------------------------------------------------
    # SECOND OWNERSHIP INTERLOCK
    # --------------------------------------------------------

    def _physical_controller_running(
        self,
    ):
        command = (
            "ps -eo pid,args "
            "| grep '[g]1_deploy_onnx_ref' "
            "|| true"
        )

        try:
            result = subprocess.run(
                self._ssh_base()
                + [
                    command,
                ],
                text=True,
                capture_output=True,
                timeout=7.0,
            )

        except Exception as exc:
            return {
                "ok": False,
                "error":
                    (
                        "Could not verify physical "
                        "controller: "
                        + repr(
                            exc
                        )
                    ),
            }

        if result.returncode != 0:
            return {
                "ok": False,
                "error":
                    (
                        result.stderr.strip()
                        or
                        "Physical controller check failed."
                    ),
            }

        output = result.stdout.strip()

        return {
            "ok": True,
            "running":
                bool(
                    output
                ),
            "output":
                output,
        }


    # --------------------------------------------------------
    # REMOTE PYTHON
    # --------------------------------------------------------

    def _run_sdk_script(
        self,
        source,
        timeout_s=15.0,
    ):
        encoded = base64.b64encode(
            source.encode(
                "utf-8"
            )
        ).decode(
            "ascii"
        )

        python_code = (
            "import base64;"
            "exec(base64.b64decode("
            + repr(
                encoded
            )
            + "))"
        )

        remote = (
            "export PYTHONPATH="
            + shlex.quote(
                self.sdk_root
            )
            + ':"${PYTHONPATH:-}"; '
            + "python3 -c "
            + shlex.quote(
                python_code
            )
        )

        try:
            result = subprocess.run(
                self._ssh_base()
                + [
                    remote,
                ],
                text=True,
                capture_output=True,
                timeout=float(
                    timeout_s
                ),
            )

        except Exception as exc:
            return {
                "ok": False,
                "error":
                    repr(
                        exc
                    ),
            }

        stdout = (
            result.stdout.strip()
        )

        stderr = (
            result.stderr.strip()
        )

        marker = (
            "BACALBASA_MODE_JSON="
        )

        payload = None

        for line in stdout.splitlines():
            if not line.startswith(
                marker
            ):
                continue

            try:
                payload = json.loads(
                    line[
                        len(
                            marker
                        ):
                    ]
                )

            except Exception:
                payload = None

        if payload is None:
            return {
                "ok": False,
                "returncode":
                    result.returncode,

                "error":
                    (
                        stderr
                        or
                        stdout
                        or
                        (
                            "Remote SDK exited rc="
                            + str(
                                result.returncode
                            )
                        )
                    ),
            }

        payload[
            "returncode"
        ] = result.returncode

        if (
            result.returncode != 0
            and
            payload.get(
                "ok"
            )
        ):
            payload[
                "ok"
            ] = False

        if stderr:
            payload[
                "stderr"
            ] = stderr

        return payload


    # --------------------------------------------------------
    # READ CURRENT MOTION-SWITCHER MODE
    # --------------------------------------------------------

    # ========================================================
    # D12R_MOTION_SWITCHER_MODE
    # ========================================================

    def status(
        self,
    ):
        '''
        Current-mode reader for this deployed G1 firmware.

        Current-mode reader using the physical G1's verified
        Unitree interfaces.

        - MotionSwitcher.CheckMode identifies Developer/released state.
        - The installed vendored LocoClient incorrectly targets "loco".
        - This physical G1 exposes the working locomotion RPC service
          as "sport".
        - sport API 7001 returns the live FSM ID.

        Physically captured mappings:
            0   -> ZERO TORQUE
            1   -> DAMPING
            501 -> WALK
            802 -> RUN
            812 -> CLIMB

        Read-only.
        '''

        source = f'''
import json

from unitree_sdk2py.core.channel import (
    ChannelFactoryInitialize
)

from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
    MotionSwitcherClient
)

from unitree_sdk2py.rpc.client import (
    Client
)


ChannelFactoryInitialize(
    0,
    {self.interface!r},
)


# ============================================================
# MOTION SWITCHER
# ============================================================

motion = MotionSwitcherClient()

if hasattr(
    motion,
    "SetTimeout",
):
    motion.SetTimeout(
        5.0
    )

motion.Init()

motion_code, motion_mode = (
    motion.CheckMode()
)


def extract_name(
    value,
):
    if isinstance(
        value,
        str,
    ):
        value = value.strip()

        return (
            value
            if value
            else None
        )

    if isinstance(
        value,
        dict,
    ):
        for key in (
            "name",
            "alias",
            "mode",
        ):
            item = value.get(
                key
            )

            if (
                isinstance(
                    item,
                    str,
                )
                and
                item.strip()
            ):
                return (
                    item.strip()
                )

    return None


name = extract_name(
    motion_mode
)


released = (
    motion_code == 0
    and
    name is None
)


# ============================================================
# LIVE SPORT FSM
# ============================================================

fsm_code = None
fsm_raw = None
fsm_id = None
fsm_error = None


if released:

    display_mode = (
        "DEVELOPMENT"
    )


else:

    sport = Client(
        "sport",
        False,
    )

    if hasattr(
        sport,
        "SetTimeout",
    ):
        sport.SetTimeout(
            3.0
        )

    sport._SetApiVerson(
        "1.0.0.0"
    )

    sport._RegistApi(
        7001,
        0,
    )

    try:
        fsm_code, fsm_raw = (
            sport._Call(
                7001,
                "{{}}",
            )
        )

        if (
            fsm_code == 0
            and
            fsm_raw is not None
        ):
            payload = (
                json.loads(
                    fsm_raw
                )
                if isinstance(
                    fsm_raw,
                    str,
                )
                else fsm_raw
            )

            if isinstance(
                payload,
                dict,
            ):
                value = payload.get(
                    "data"
                )

                if value is not None:
                    fsm_id = int(
                        value
                    )

    except Exception as exc:
        fsm_error = repr(
            exc
        )


    fsm_names = dict((
        (0,   "ZERO TORQUE"),
        (1,   "DAMPING"),
        (3,   "SIT"),
        (501, "WALK"),
        (702, "RECOVERY"),
        (706, "TRANSITION"),
        (802, "RUN"),
        (812, "CLIMB"),
    ))


    if fsm_id is not None:
        display_mode = (
            fsm_names.get(
                fsm_id,
                "FSM "
                + str(
                    fsm_id
                ),
            )
        )

    elif name is not None:
        display_mode = (
            name.upper()
        )

    else:
        display_mode = (
            "UNKNOWN"
        )


result = dict(
    ok=(
        released
        or
        fsm_code == 0
    ),

    display_mode=display_mode,

    motion_owner=motion_mode,
    motion_name=name,
    motion_code=motion_code,
    released=released,

    fsm_id=fsm_id,
    fsm_code=fsm_code,
    fsm_raw=fsm_raw,
    fsm_error=fsm_error,

    sport_service="sport",
    source="motion_switcher+sport_fsm",
)


print(
    "BACALBASA_MODE_JSON="
    + json.dumps(
        result,
        default=str,
    )
)
'''

        result = self._run_sdk_script(
            source,
            timeout_s=10.0,
        )

        with self._lock:
            if result.get(
                "ok"
            ):
                self._last_result = (
                    result
                )

                self._last_error = None

            else:
                self._last_error = (
                    result.get(
                        "error"
                    )
                )

        return result


    # --------------------------------------------------------
    # EXPLICIT ACTION
    # --------------------------------------------------------

    def action(
        self,
        action,
    ):
        action = str(
            action
        )

        if action not in self.ACTIONS:
            return {
                "ok": False,
                "error":
                    (
                        "Unsupported robot mode "
                        "action: "
                        + action
                    ),
            }

        with self._lock:
            if self._busy:
                return {
                    "ok": False,
                    "error":
                        (
                            "Another robot mode "
                            "request is in progress."
                        ),
                }

            self._busy = True
            self._last_action = action
            self._last_error = None

        try:
            # Even if the dashboard state were stale,
            # refuse commands whenever physical SONIC
            # exists on the Jetson.
            check = (
                self
                ._physical_controller_running()
            )

            if not check.get(
                "ok"
            ):
                result = check

            elif check.get(
                "running"
            ):
                result = {
                    "ok": False,
                    "error":
                        (
                            "Refusing robot mode change "
                            "because g1_deploy_onnx_ref "
                            "is already running on the "
                            "Jetson."
                        ),
                }

            else:
                result = (
                    self
                    ._execute_action(
                        action
                    )
                )

            with self._lock:
                self._last_result = result

                if result.get(
                    "ok"
                ):
                    self._last_error = None

                else:
                    self._last_error = (
                        result.get(
                            "error"
                        )
                    )

            self._append_log(
                action
                + " -> "
                + json.dumps(
                    result,
                    default=str,
                    sort_keys=True,
                )
            )

            return result

        finally:
            with self._lock:
                self._busy = False


    # --------------------------------------------------------
    # SDK COMMAND IMPLEMENTATION
    # --------------------------------------------------------

    # ========================================================
    # D12J_DIRECT_TARGET_MODES
    # ========================================================

    def _execute_action(
        self,
        action,
    ):
        '''
        Every dashboard button represents a TARGET state.

        Developer:
            release the Unitree motion service.

        Damping / Zero Torque / Stop Motion:
            make sure Unitree AI/high-level motion ownership
            is active first, then execute the requested G1
            locomotion command.

        This means the user never needs a separate
        "Exit Developer" step.
        '''

        source = f'''
import json
import time

from unitree_sdk2py.core.channel import ChannelFactoryInitialize

from unitree_sdk2py.rpc.client import (
    Client
)

from unitree_sdk2py.comm.motion_switcher.motion_switcher_client import (
    MotionSwitcherClient
)


ACTION = {action!r}


ChannelFactoryInitialize(
    0,
    {self.interface!r},
)


def mode_name(value):
    if isinstance(
        value,
        str,
    ):
        return value.strip().lower()

    if isinstance(
        value,
        dict,
    ):
        for key in (
            "name",
            "alias",
            "mode",
            "form",
        ):
            item = value.get(
                key
            )

            if (
                isinstance(
                    item,
                    str,
                )
                and
                item.strip()
            ):
                return (
                    item
                    .strip()
                    .lower()
                )

    return None


def mode_is_released(value):
    if value is None:
        return True

    if isinstance(
        value,
        str,
    ):
        return not bool(
            value.strip()
        )

    if isinstance(
        value,
        dict,
    ):
        return not any(
            (
                str(v).strip()
                if v is not None
                else ""
            )
            for v
            in value.values()
        )

    return False


result = {{
    "ok":
        False,

    "action":
        ACTION,
}}


# ============================================================
# MOTION SWITCHER
# ============================================================

motion = MotionSwitcherClient()

if hasattr(
    motion,
    "SetTimeout",
):
    motion.SetTimeout(
        8.0
    )

motion.Init()

before_code, before_mode = (
    motion.CheckMode()
)

result[
    "before_motion_code"
] = before_code

result[
    "before_motion_mode"
] = before_mode


# ============================================================
# TARGET: DEVELOPER / SDK
# ============================================================

if ACTION == "developer":

    if (
        before_code == 0
        and
        mode_is_released(
            before_mode
        )
    ):
        code = 0

    else:
        code, _ = (
            motion.ReleaseMode()
        )


    result.update({{
        "ok":
            code == 0,

        "code":
            code,

        "requested_mode":
            "developer",

        "display_mode":
            "DEVELOPMENT",
    }})


# ============================================================
# LEGACY TARGET: AI
#
# Kept for backend compatibility, but D12J UI will no longer
# expose a separate Exit Developer button.
# ============================================================

elif ACTION == "restore_ai":

    current_name = (
        mode_name(
            before_mode
        )
    )


    if (
        before_code == 0
        and
        current_name == "ai"
    ):
        code = 0

    else:
        code, _ = (
            motion.SelectMode(
                "ai"
            )
        )


    result.update({{
        "ok":
            code == 0,

        "code":
            code,

        "requested_mode":
            "ai",

        "display_mode":
            "AI",
    }})


# ============================================================
# TARGETS REQUIRING THE HIGH-LEVEL G1 LOCO SERVICE
# ============================================================

else:

    current_name = (
        mode_name(
            before_mode
        )
    )


    # --------------------------------------------------------
    # If Developer/SDK ownership is active, or another Unitree
    # motion mode owns the robot, select AI automatically.
    # --------------------------------------------------------

    if (
        before_code != 0
        or
        current_name != "ai"
    ):
        select_code, _ = (
            motion.SelectMode(
                "ai"
            )
        )

        result[
            "select_ai_code"
        ] = select_code


        if select_code != 0:
            result.update({{
                "ok":
                    False,

                "code":
                    select_code,

                "error":
                    (
                        "Could not activate Unitree "
                        "AI/high-level motion service."
                    ),
            }})

            print(
                "BACALBASA_MODE_JSON="
                + json.dumps(
                    result,
                    default=str,
                )
            )

            raise SystemExit(
                0
            )


        # Wait briefly for motion ownership to become AI.
        ai_ready = False
        after_mode = None


        for _ in range(
            20
        ):
            time.sleep(
                0.15
            )

            check_code, after_mode = (
                motion.CheckMode()
            )

            if (
                check_code == 0
                and
                mode_name(
                    after_mode
                )
                == "ai"
            ):
                ai_ready = True
                break


        result[
            "after_select_mode"
        ] = after_mode


        if not ai_ready:
            result.update({{
                "ok":
                    False,

                "code":
                    -1,

                "error":
                    (
                        "Unitree motion service did not "
                        "confirm AI ownership after SelectMode."
                    ),
            }})

            print(
                "BACALBASA_MODE_JSON="
                + json.dumps(
                    result,
                    default=str,
                )
            )

            raise SystemExit(
                0
            )


    # --------------------------------------------------------
    # Requested G1 target
    # --------------------------------------------------------

    # Installed LocoClient targets obsolete service "loco".
    # Physical G1 uses "sport".
    loco = Client(
        "sport",
        False,
    )

    if hasattr(
        loco,
        "SetTimeout",
    ):
        loco.SetTimeout(
            8.0
        )

    loco._SetApiVerson(
        "1.0.0.0"
    )

    loco._RegistApi(
        7101,
        0,
    )

    loco._RegistApi(
        7105,
        0,
    )


    def set_fsm_id(
        fsm_id,
    ):
        parameter = json.dumps(
            dict(
                data=int(
                    fsm_id
                )
            )
        )

        code, _ = loco._Call(
            7101,
            parameter,
        )

        return code


    def set_velocity(
        vx,
        vy,
        omega,
        duration=1.0,
    ):
        parameter = json.dumps(
            dict(
                velocity=[
                    float(vx),
                    float(vy),
                    float(omega),
                ],
                duration=float(
                    duration
                ),
            )
        )

        code, _ = loco._Call(
            7105,
            parameter,
        )

        return code


    if ACTION == "damp":
        code = (
            set_fsm_id(
                1
            )
        )

        requested = (
            "fsm_1_damp"
        )

        display = (
            "DAMPING"
        )


    elif ACTION == "zero_torque":
        code = (
            set_fsm_id(
                0
            )
        )

        requested = (
            "fsm_0_zero_torque"
        )

        display = (
            "ZERO TORQUE"
        )


    elif ACTION == "walk":
        code = (
            set_fsm_id(
                501
            )
        )

        requested = (
            "fsm_501_walk"
        )

        display = (
            "WALK"
        )


    elif ACTION == "run":
        code = (
            set_fsm_id(
                802
            )
        )

        requested = (
            "fsm_802_run"
        )

        display = (
            "RUN"
        )


    elif ACTION == "climb":
        code = (
            set_fsm_id(
                812
            )
        )

        requested = (
            "fsm_812_climb"
        )

        display = (
            "CLIMB"
        )


    elif ACTION == "stop_motion":
        code = (
            set_velocity(
                0.0,
                0.0,
                0.0,
                1.0,
            )
        )

        requested = (
            "velocity_zero"
        )

        # Stop Motion is an action, not a persistent FSM.
        display = None


    elif ACTION == "sit":
        code = (
            set_fsm_id(
                3
            )
        )

        requested = (
            "fsm_3_sit"
        )

        display = (
            "SIT"
        )


    elif ACTION == "stand_from_squat":
        code = (
            set_fsm_id(
                706
            )
        )

        requested = (
            "fsm_706_squat_to_stand"
        )

        display = (
            "SQUAT / STAND TRANSITION"
        )


    elif ACTION == "recover_from_lie":
        code = (
            set_fsm_id(
                702
            )
        )

        requested = (
            "fsm_702_lie_to_stand"
        )

        display = (
            "RECOVERY"
        )


    else:
        raise RuntimeError(
            "Unexpected action: "
            + ACTION
        )


    result.update({{
        "ok":
            code == 0,

        "code":
            code,

        "requested_mode":
            requested,

        "display_mode":
            display,
    }})


print(
    "BACALBASA_MODE_JSON="
    + json.dumps(
        result,
        default=str,
    )
)
'''

        return self._run_sdk_script(
            source,
            timeout_s=18.0,
        )
