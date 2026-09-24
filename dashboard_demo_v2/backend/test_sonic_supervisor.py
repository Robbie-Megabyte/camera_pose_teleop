from pathlib import Path
import os
import tempfile

from sonic_supervisor import SonicSupervisor


def make_supervisor():
    temp = tempfile.TemporaryDirectory()

    supervisor = SonicSupervisor(
        runtime_dir=Path(
            temp.name
        )
    )

    return temp, supervisor


def test_command_contract():
    temp, supervisor = (
        make_supervisor()
    )

    try:
        command = (
            supervisor.command()
        )

        assert (
            "sonic_deploy_env.sh"
            in command
        )

        assert (
            "source scripts/setup_env.sh"
            in command
        )

        assert (
            "bash deploy.sh"
            in command
        )

        assert (
            "--cp policy/low_latency/model"
            in command
        )

        assert (
            "--obs-config "
            "policy/low_latency/"
            "observation_config.yaml"
            in command
        )

        assert (
            "--input-type zmq"
            in command
        )

        assert (
            "--zmq-host localhost"
            in command
        )

        assert (
            command.rstrip().endswith(
                "sim"
            )
        )

        assert (
            " real"
            not in command
        )

        print(
            "D6B_SIM_COMMAND_CONTRACT=PASS"
        )

    finally:
        temp.cleanup()


def test_parser():
    temp, supervisor = (
        make_supervisor()
    )

    try:
        supervisor.feed_test_line(
            "Init Done"
        )

        snap = supervisor.snapshot()

        assert snap[
            "state"
        ] == "init_done"

        assert snap[
            "init_done"
        ] is True

        assert snap[
            "zmq_live"
        ] is False

        print(
            "D6B_INIT_DONE_PARSE=PASS"
        )


        supervisor._policy_requested = True

        supervisor.feed_test_line(
            "ZMQ STREAMING MODE: DISABLED"
        )

        snap = supervisor.snapshot()

        assert snap[
            "state"
        ] == "reference"

        assert snap[
            "policy_confirmed"
        ] is True

        assert snap[
            "zmq_live"
        ] is False

        print(
            "D6B_REFERENCE_PARSE=PASS"
        )


        supervisor.feed_test_line(
            "ZMQ STREAMING MODE: ENABLED"
        )

        snap = supervisor.snapshot()

        assert snap[
            "state"
        ] == "live"

        assert snap[
            "policy_confirmed"
        ] is True

        assert snap[
            "zmq_live"
        ] is True

        print(
            "D6B_LIVE_PARSE=PASS"
        )


        supervisor.feed_test_line(
            "ZMQ STREAMING MODE: FORCE DISABLED"
        )

        snap = supervisor.snapshot()

        assert snap[
            "state"
        ] == "reference"

        assert snap[
            "zmq_live"
        ] is False

        print(
            "D6B_FORCE_DISABLE_PARSE=PASS"
        )


        supervisor._damping_requested = True

        supervisor.feed_test_line(
            "[DEBUG] Stopping G1Deploy..."
        )

        snap = supervisor.snapshot()

        assert snap[
            "state"
        ] == "damping_requested"

        print(
            "D6B_DAMPING_PARSE=PASS"
        )


        supervisor.feed_test_line(
            "[DEBUG] Program exiting normally..."
        )

        snap = supervisor.snapshot()

        assert snap[
            "state"
        ] == "stopped"

        print(
            "D6B_STOP_PARSE=PASS"
        )

    finally:
        temp.cleanup()


def test_toggle_guards():
    temp, supervisor = (
        make_supervisor()
    )

    try:
        # No live process -> every control command must reject.
        result = supervisor.go_live()

        assert result[
            "ok"
        ] is False

        result = (
            supervisor.pause_tracking()
        )

        assert result[
            "ok"
        ] is False

        result = (
            supervisor.request_policy_control()
        )

        assert result[
            "ok"
        ] is False

        print(
            "D6B_DEAD_PROCESS_GUARDS=PASS"
        )


        # Pure state checks prove Enter cannot be sent blindly.
        supervisor._proc = object()

        # Replace alive check only for this parser/guard unit test.
        supervisor._alive_locked = (
            lambda: True
        )

        writes = []

        supervisor._write_key = (
            lambda payload:
            (
                writes.append(
                    payload
                )
                or
                {
                    "ok": True,
                }
            )
        )


        supervisor._state = (
            "init_done"
        )

        supervisor._init_done = True

        supervisor._policy_confirmed = False
        supervisor._zmq_live = False

        result = (
            supervisor.go_live()
        )

        assert result[
            "ok"
        ] is False

        assert writes == []

        print(
            "D6B_ENTER_NOT_SENT_FROM_INIT=PASS"
        )


        supervisor._state = (
            "reference"
        )

        supervisor._policy_confirmed = True

        result = (
            supervisor.go_live()
        )

        assert result[
            "ok"
        ] is True

        assert writes == [
            b"\n"
        ]

        print(
            "D6B_ENTER_ALLOWED_FROM_REFERENCE=PASS"
        )


        writes.clear()

        supervisor._state = "live"
        supervisor._zmq_live = True

        result = (
            supervisor.pause_tracking()
        )

        assert result[
            "ok"
        ] is True

        assert writes == [
            b"\n"
        ]

        print(
            "D6B_PAUSE_ENTER_ALLOWED_FROM_LIVE=PASS"
        )


        writes.clear()

        supervisor._state = (
            "reference"
        )

        supervisor._zmq_live = False

        result = (
            supervisor.pause_tracking()
        )

        assert result[
            "ok"
        ] is False

        assert writes == []

        print(
            "D6B_ENTER_NOT_SENT_FROM_REFERENCE_PAUSE=PASS"
        )

    finally:
        temp.cleanup()




def test_sim_autostart_state_machine():
    temp, supervisor = (
        make_supervisor()
    )

    try:
        # Synthetic alive process + intercepted PTY writes.
        class FakeProc:
            pid = 999999

        supervisor._proc = FakeProc()

        supervisor._alive_locked = (
            lambda: True
        )

        writes = []

        supervisor._write_key = (
            lambda payload:
            (
                writes.append(
                    payload
                )
                or
                {
                    "ok": True,
                }
            )
        )


        # deploy.sh prompt has no newline.
        confirmed = (
            supervisor
            ._maybe_confirm_sim_launcher(
                b"abc Proceed with deployment? [Y/n]: "
            )
        )

        assert confirmed is True

        assert writes == [
            b"Y\n"
        ]

        assert (
            supervisor.snapshot()[
                "launcher_confirmed"
            ]
            is True
        )

        print(
            "D6F_SIM_PROMPT_AUTO_CONFIRM=PASS"
        )


        # Same buffered prompt must never send Y twice.
        supervisor._maybe_confirm_sim_launcher(
            b"Proceed with deployment? [Y/n]: "
        )

        assert writes == [
            b"Y\n"
        ]

        print(
            "D6F_SIM_PROMPT_SINGLE_SHOT=PASS"
        )


        writes.clear()

        # Exact Init Done causes guarded policy-start key.
        supervisor.feed_test_line(
            "Init Done"
        )

        assert writes == [
            b"]"
        ]

        snap = supervisor.snapshot()

        assert (
            snap[
                "policy_requested"
            ]
            is True
        )

        assert (
            snap[
                "state"
            ]
            == "policy_requested"
        )

        print(
            "D6F_INIT_AUTO_POLICY_KEY=PASS"
        )


        writes.clear()

        # Exact C++ state-transition marker proves CONTROL.
        supervisor.feed_test_line(
            "[Control] DEBUG: "
            "operator_state.start=true, "
            "transitioning to CONTROL state"
        )

        snap = supervisor.snapshot()

        assert (
            snap[
                "state"
            ]
            == "reference"
        )

        assert (
            snap[
                "policy_confirmed"
            ]
            is True
        )

        assert (
            snap[
                "zmq_live"
            ]
            is False
        )

        assert writes == []

        print(
            "D6F_CONTROL_TO_REFERENCE_PARSE=PASS"
        )


        # Critically: no ENTER was produced.
        assert (
            b"\n"
            not in writes
        )

        print(
            "D6F_ENTER_AUTOMATICALLY_SENT=NO"
        )

    finally:
        temp.cleanup()


def main():
    test_command_contract()
    test_parser()
    test_toggle_guards()
    test_sim_autostart_state_machine()

    print(
        "D6B_TEST_SUITE=PASS"
    )


if __name__ == "__main__":
    main()
