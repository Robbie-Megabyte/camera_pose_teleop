# Camera Pose Teleop

Camera-based whole-body human pose estimation and teleoperation pipeline.

Current pipeline:

Camera
-> YOLOX + ByteTrack
-> ViTPose-H
-> HMR2 visual features
-> GVHMR
-> Pair FASTIK
-> SONIC Protocol V3
-> MuJoCo / Unitree G1

V2 adds automatic camera selection, dynamic capture profiles, full-body startup
framing checks, and session-based neutral-pose gravity alignment.

V2 has been validated end-to-end in MuJoCo.
V2 has also been validated end-to-end on a physical Unitree G1.

## Calibration

Two alignment paths are kept separate:

- `session_v2`
  Current V2 path. A short neutral pose at startup determines the gravity
  alignment for the current camera position and orientation.

- `fixed_v1`
  Protected legacy fixed-camera calibration used by the original working system.

If the camera is moved after V2 alignment is complete, restart the pipeline
and perform the neutral alignment again.

Do not overwrite or remove the fixed V1 calibration/reference artifacts.

## Startup

### Terminal 1 - MuJoCo

~~~bash
cd "$HOME/GR00T-WholeBodyControl"
source .venv_sim/bin/activate

python gear_sonic/scripts/run_sim_loop.py \
  --interface lo
~~~

### Terminal 2 - SONIC

~~~bash
source "$HOME/sonic_deploy_env.sh"

cd "$HOME/GR00T-WholeBodyControl/gear_sonic_deploy"
source scripts/setup_env.sh

bash deploy.sh \
  --cp policy/low_latency/model \
  --obs-config policy/low_latency/observation_config.yaml \
  --input-type zmq \
  --zmq-host localhost \
  sim
~~~

### Terminal 3 - Camera Pose Teleop V2

~~~bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

export CAMERA_ALIGNMENT_MODE=session_v2
unset CAMERA_PROFILE_OVERRIDE

./scripts/run_pose.sh dual
~~~

Stand in a neutral pose with the full body visible while startup framing and
session alignment complete.

### Optional - Raw camera view

~~~bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

python camera/previews/view_dual_raw.py
~~~

### Optional - Keypoint view

~~~bash
cd /path/to/camera_pose_teleop
source "$HOME/GVHMR/.venv/bin/activate"

python camera/previews/view_dual_keypoints.py
~~~

To choose a different camera on the next launch:

~~~bash
CAMERA_RESELECT=1 \
./scripts/run_pose.sh dual
~~~

## Legacy V1

To use the protected fixed-camera path:

~~~bash
export CAMERA_ALIGNMENT_MODE=fixed_v1
./scripts/run_pose.sh dual
~~~


## V3 wrist control

The `v3` branch extends the validated V2 body pipeline with camera-derived
wrist orientation and control.

The V3 wrist path adds:

- WiLoR hand estimation
- forearm-relative wrist orientation
- per-hand observation/trust handling
- bounded Unitree G1 wrist mapping
- wrist command slew and safety handling
- integration with the existing SONIC whole-body reference

The V2 body pipeline remains the baseline architecture.

V3 wrist control has been validated in software and MuJoCo. Combined physical
Unitree G1 validation of the V3 wrist path has not yet been completed.

Launch the V3 runtime from the repository root with:

~~~bash
./scripts/run_pose_v3.sh normal
~~~

Machine-specific paths, environments, downloaded model weights, generated
TensorRT artifacts, caches, logs, and runtime state are intentionally excluded
from Git.
