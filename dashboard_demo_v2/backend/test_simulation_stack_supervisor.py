from pathlib import Path
import tempfile

from simulation_stack_supervisor import (
    SimulationStackSupervisor,
)


class FakeV2:
    def snapshot_state(self):
        return {
            "teleop": {
                "process_alive": False,
                "running": False,
            }
        }


class FakeSonic:
    def snapshot(self):
        return {
            "process_alive": False,
            "state": "off",
            "zmq_live": False,
        }


class FakePreview:
    def snapshot(self):
        return {
            "live": False,
        }


def main():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)

        dashboard = (
            root
            / "camera_pose_teleop"
            / "dashboard_demo_v2"
        )

        dashboard.mkdir(
            parents=True
        )

        stack = SimulationStackSupervisor(
            dashboard_root=dashboard,
            repo_root=root,
            v2_supervisor=FakeV2(),
            sonic_supervisor=FakeSonic(),
            mujoco_preview=FakePreview(),
        )

        commands = stack.commands()

        assert (
            "--interface"
            in commands[
                "mujoco"
            ]
        )

        assert (
            "lo"
            in commands[
                "mujoco"
            ]
        )

        assert (
            "tcp://127.0.0.1:5555"
            in commands[
                "relay"
            ]
        )

        assert (
            "tcp://127.0.0.1:5610"
            in commands[
                "relay"
            ]
        )

        snap = stack.snapshot()

        assert snap[
            "target"
        ] == "sim"

        assert snap[
            "state"
        ] == "off"

        assert snap[
            "ready"
        ] is False

        print(
            "D7B_STACK_COMMAND_CONTRACT=PASS"
        )

        print(
            "D7B_STACK_INITIAL_STATE=PASS"
        )

        print(
            "D7B_STACK_TEST_SUITE=PASS"
        )


if __name__ == "__main__":
    main()
