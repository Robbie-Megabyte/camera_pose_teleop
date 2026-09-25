# Camera Pose Teleop

Camera Pose Teleop is a camera-based whole-body teleoperation pipeline for the
Unitree G1. The system reconstructs human body motion from an external RGB
camera, retargets it to the robot, and streams the resulting reference to
SONIC for simulation or physical deployment.

The `main` branch contains the working **V2 body teleoperation pipeline**.

> The `v3` branch is a separate experimental wrist/hand extension and is not
> currently considered production-ready.

## Pipeline

```text
External RGB camera
        |
        v
FFmpeg / V4L2 latest-frame capture
        |
        v
YOLOX person detection
        |
        v
ByteTrack tracking / operator selection
        |
        v
ViTPose-H COCO17
        |
        v
HMR2 visual features
        |
        v
Causal GVHMR
        |
        v
Pair FASTIK
        |
        v
V2 camera / gravity alignment
        |
        v
SONIC Protocol V3 / ZMQ
        |
        v
SONIC
        |
        +------------------+
        |                  |
        v                  v
     MuJoCo           Unitree G1
```

The production path is designed around **latest-frame processing**. Camera
frames must not be queued and replayed later, because stale frames directly
increase teleoperation latency.

## V2

V2 extends the original fixed-camera pipeline with:

- automatic camera discovery and selection;
- dynamic camera capture-profile selection;
- full-body startup framing checks;
- neutral-pose session alignment;
- runtime camera/gravity alignment;
- delayed SONIC bridge activation until alignment is ready;
- the protected V1 fixed-camera calibration path as a fallback;
- raw and keypoint preview fan-out without reopening the physical camera.

The body-estimation and SONIC control architecture remains based on the proven
V1 path.

## Validation Status

The V2 body pipeline has been validated through:

- PC perception and visualization;
- live camera/session alignment;
- end-to-end MuJoCo simulation;
- physical Unitree G1 teleoperation.

The experimental wrist/hand work is maintained separately on the `v3` branch.

## Repository Layout

This repository is already the Camera Pose Teleop project root. After cloning,
do **not** expect another nested `camera_pose_teleop/` directory.

```text
camera_pose_teleop/
├── alignment/          Camera/session alignment logic
├── calibration/        Portable calibration and protected V1 references
├── camera/             Camera discovery, capture and preview tools
├── configs/            Configuration templates
├── dashboard_demo_v2/  V2 dashboard/demo integration
├── docs/               Project documentation
├── patches/            Required compatibility/source patches
├── perception/         Main body-perception runtime
├── retargeting/        Human/SMPL-to-robot adaptation
├── scripts/            Operator-facing launchers
├── setup/              Reproducible setup system under development
├── simulation/         Simulation-specific configuration
├── sonic/              SONIC bridge, publisher and runtime integration
└── third_party/        External dependency provenance
```

## Clone

```bash
git clone https://github.com/Robbie-Megabyte/camera_pose_teleop.git
cd camera_pose_teleop
git switch main
```

All commands below assume that the current directory is the cloned repository
root.

## Installation Status

A reproducible multi-machine setup system is being built under `setup/`.

The target setup covers:

- the perception/development PC;
- SONIC and MuJoCo simulation;
- the Jetson runtime;
- Unitree SDK / DDS integration;
- native toolchains;
- model assets and checksums;
- network validation;
- end-to-end verification.

Until that setup system is complete, cloning this repository alone does **not**
install the external runtime dependencies, model assets, or SONIC environment.

The current working deployment uses external GVHMR and
GR00T-WholeBodyControl/SONIC environments in addition to this repository.

## Runtime Paths

For the current known-good installation, define the external dependency roots
once per shell:

```bash
export CPT_ROOT="$PWD"
export GVHMR_ROOT="$HOME/GVHMR"
export GROOT_ROOT="$HOME/GR00T-WholeBodyControl"
```

`CPT_ROOT` must point to the root of this cloned repository.

## Startup — MuJoCo Simulation

The normal local V2 simulation uses three terminals.

### Terminal 1 — MuJoCo

```bash
export GROOT_ROOT="$HOME/GR00T-WholeBodyControl"

cd "$GROOT_ROOT"
source .venv_sim/bin/activate

python gear_sonic/scripts/run_sim_loop.py \
  --interface lo
```

### Terminal 2 — SONIC

```bash
export GROOT_ROOT="$HOME/GR00T-WholeBodyControl"

source "$HOME/sonic_deploy_env.sh"

cd "$GROOT_ROOT/gear_sonic_deploy"
source scripts/setup_env.sh

bash deploy.sh \
  --cp policy/low_latency/model \
  --obs-config policy/low_latency/observation_config.yaml \
  --input-type zmq \
  --zmq-host localhost \
  sim
```

### Terminal 3 — Camera Pose Teleop V2

From the cloned repository root:

```bash
cd /path/to/camera_pose_teleop

source "$HOME/GVHMR/.venv/bin/activate"

export CAMERA_ALIGNMENT_MODE=session_v2
unset CAMERA_PROFILE_OVERRIDE

./scripts/run_pose.sh dual
```

During startup, stand in a neutral pose with the full body visible while the
framing check and session alignment complete.

The preferred launcher is:

```bash
./scripts/run_pose.sh <mode>
```

Supported V2 modes include:

```text
normal
preview
keypoints
dual
```

`session_v2` is the normal movable-camera alignment path.

## Camera Selection

List the cameras visible to Camera Pose Teleop:

```bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

python camera/device_manager.py list
```

Force camera selection again on the next launch:

```bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

export CAMERA_ALIGNMENT_MODE=session_v2
CAMERA_RESELECT=1 ./scripts/run_pose.sh dual
```

## Preview Windows

The main pipeline should remain the **single owner of the physical teleoperation
camera**.

The standalone preview clients below consume the pipeline fan-out and do not
open the camera again.

### Raw camera view

```bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

python camera/previews/view_dual_raw.py
```

### Keypoint view

```bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

python camera/previews/view_dual_keypoints.py
```

## V2 Dashboard

From the cloned repository root:

```bash
./dashboard_demo_v2/scripts/run_dashboard_demo.sh
```

The local dashboard is then served at:

```text
http://127.0.0.1:8088
```

## Calibration

Two alignment paths are intentionally kept separate.

### `session_v2`

This is the normal V2 path.

A short neutral pose at startup establishes the gravity alignment for the
current camera position and orientation.

If the camera is moved after alignment completes, restart Camera Pose Teleop
and perform the neutral alignment again.

```bash
export CAMERA_ALIGNMENT_MODE=session_v2
./scripts/run_pose.sh dual
```

### `fixed_v1`

This is the protected legacy fixed-camera calibration path.

```bash
export CAMERA_ALIGNMENT_MODE=fixed_v1
./scripts/run_pose.sh dual
```

Do not overwrite the fixed V1 reference/calibration artifacts with
session-generated calibration.

## Runtime State

Generated runtime state is intentionally kept outside version control,
including:

- session alignment output;
- local configuration;
- logs;
- caches;
- downloaded model weights;
- generated TensorRT / ONNX Runtime artifacts;
- build products;
- machine-specific state.

Canonical calibration/reference files that belong to the repository are kept
separately from generated session state.

## Physical Unitree G1 Deployment

The physical deployment uses the same PC perception stream but replaces the
local simulation endpoint with the Jetson/Unitree runtime:

```text
Camera Pose Teleop on PC
        |
        v
Protocol V3 / ZMQ
        |
        v
SONIC on Jetson
        |
        v
Unitree SDK2 / DDS
        |
        v
Unitree G1
```

Physical deployment requires the matching Jetson runtime, SONIC build, Unitree
SDK/DDS configuration, network configuration, and robot-side safety procedure.

Do not treat the local MuJoCo commands above as physical-robot launch commands.

The reproducible setup system under `setup/` will document and validate these
machine-specific requirements without automatically changing Jetson
kernel/BSP/firmware components.

## Development Branches

### `main`

Working V2 body teleoperation baseline and the active reproducible-setup work.

### `v3`

Experimental hand/wrist extension built on V2.

V3 adds WiLoR-based hand observations, forearm-relative wrist orientation,
trust/reacquisition logic, G1 wrist mapping, and SONIC wrist integration.
It remains under development and should not be treated as the production body
pipeline.

## Setup Development

The setup implementation lives under:

```text
setup/
```

The intended architecture separates reusable components from machine profiles,
with dedicated manifests and validation for PC, Jetson and robot-side
requirements.

Setup development is intentionally kept on `main` because it is isolated under
its own top-level directory and targets reproducibility of the V2 baseline.
