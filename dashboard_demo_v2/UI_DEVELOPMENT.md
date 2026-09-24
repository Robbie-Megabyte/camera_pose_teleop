# Camera Pose Teleop Dashboard — UI Development Mode

This mode is for dashboard interface development without the robotics stack.

## What it provides

- the real dashboard frontend
- a lightweight mock backend
- fake simulation and physical-robot states
- fake robot modes
- fake camera / alignment / tracking states
- fake logs and preview images

## Safety boundary

UI Development Mode does NOT:

- connect to a Unitree G1
- use Unitree DDS or the Unitree SDK
- SSH into the robot
- open any camera
- start GVHMR or SONIC
- use ROS
- start MuJoCo
- command robot hardware

Robot-related controls only modify mock state in memory.

## Requirements

Only Python 3 is required.

## Start

From the repository root:

```bash
./camera_pose_teleop/dashboard_demo_v2/scripts/run_ui_dev.sh
```

Default address:

```text
http://127.0.0.1:8088
```

Alternative port:

```bash
UI_DEV_PORT=8099 ./camera_pose_teleop/dashboard_demo_v2/scripts/run_ui_dev.sh
```

Stop with Ctrl+C.

## Real ThinkCentre dashboard

The integrated launcher remains:

```bash
./camera_pose_teleop/dashboard_demo_v2/scripts/run_dashboard_demo.sh
```

## Repository boundary

This dashboard lives under:

```text
camera_pose_teleop/dashboard_demo_v2/
```

It is separate from the unrelated dashboard_slam_a* dashboard.
