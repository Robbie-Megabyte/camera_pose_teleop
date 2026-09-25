# Camera Pose Teleop

> **V3 development status**
>
> The `v3` branch is an experimental wrist/hand extension of the working V2
> body teleoperation pipeline. It is **not currently considered production-ready
> or fully working**.
>
> The latest combined MuJoCo validation shows that the previous persistent
> wrist-lock behavior has been improved, but important control-quality issues
> remain. Body and wrist motion can become visibly segmented, and wrist-only
> movement can produce abrupt compensating motion in the robot arm.
>
> These issues must be resolved before V3 is considered validated and before
> combined V3 wrist control is tested on the physical Unitree G1.

Camera-based whole-body human pose estimation and teleoperation for the
Unitree G1.

## V3 Pipeline

V3 preserves the V2 body pipeline and adds a hand/wrist side branch.

```text
    RGB CAMERA
        |
        v
    latest-frame FFmpeg/V4L2
        |
        v
    YOLOX + ByteTrack
        |
        v
    selected operator
        |
        v
    ViTPose-H COCO17
        |
        +-----------------------------+
        |                             |
        v                             v
    body branch                  elbow/wrist geometry
        |                             |
        v                             v
    HMR2                         body-guided hand crops
        |                             |
        v                             v
    causal GVHMR                 WiLoR FAST
        |                        two-hand batch
        v                             |
    Pair FASTIK                       v
        |                        raw 3D hand joints
        |                             |
        |                        rigid palm H
        |                             |
        +---------- body F -----------+
                   |
                   v
             forearm-relative
       canonical wrist orientation
                   |
                   v
        per hand trust/authority
                   |
                   v
              G1 mapping
             limits + slew
                   |
                   v
         Body + 6 Wrist Joints
                   |
                   v
              SONIC / ZMQ
                   |
                   v
              MuJoCo / physical G1

```

The wrist branch reuses the already selected V2 operator and body pose. It
does not run a second independent person-selection pipeline.

The final V3 target is simultaneous body + wrist teleoperation while
preserving the latency, stability, and safety behavior of the V2 body path.

## V2 Baseline

V3 is built on top of the validated V2 Camera Pose Teleop body pipeline.

V2 includes:

- automatic camera selection;
- dynamic capture-profile selection;
- startup full-body framing checks;
- neutral-pose session alignment;
- runtime camera/gravity alignment;
- the protected fixed-camera V1 fallback path;
- latest-frame-only perception scheduling;
- SONIC Protocol V3 publication;
- MuJoCo simulation;
- physical Unitree G1 teleoperation.

The V2 body pipeline is the reference baseline and should remain behaviorally
unchanged while V3 wrist control is developed.

## Calibration

Two alignment paths are kept separate.

### `session_v2`

The default V2/V3 path.

A short neutral pose at startup determines the gravity alignment for the
current camera position and orientation.

If the camera is moved after alignment is complete, restart the pipeline and
perform the neutral startup alignment again.

### `fixed_v1`

Protected legacy fixed-camera calibration used by the original working system.

The fixed V1 calibration/reference artifacts should not be overwritten by
session-generated calibration.

## V3 Wrist Control

The V3 extension currently contains:

- body-guided WiLoR hand estimation;
- canonical left/right hand observations;
- per-hand trust states and loss/reacquisition handling;
- calibrated forearm-relative 3-DOF wrist orientation;
- stateful Unitree G1 wrist mapping with physical joint limits;
- command slew and authority handling;
- integration of six wrist joints into the existing SONIC motion stream.

The current implementation should be treated as development software.
MuJoCo testing is still being used to resolve motion smoothness and
whole-arm coupling before physical V3 wrist validation.

## Repository Layout

The repository root is the Camera Pose Teleop project root.

```text
alignment/      Camera/session alignment
calibration/    Calibration and protected reference artifacts
camera/         Camera discovery and preview tools
configs/        Configuration templates
docs/           Project documentation
patches/        Required source patches
perception/     Body perception runtime
retargeting/    Body retargeting
scripts/        Launch scripts
simulation/     Simulation helpers
sonic/          SONIC bridge and runtime
tests/          Deterministic V3 tests
third_party/    Third-party integration files
v3_fusion/      V3 hand/wrist fusion and wrist-control runtime
```

Local environments, generated model artifacts, runtime logs, caches,
machine-specific configuration, and development diagnostics are intentionally
excluded from Git.

## Running V3

The V3 runtime is launched from the repository root with:

```bash
./scripts/run_pose_v3.sh normal
```

The runtime depends on the same external V2 components and model stack used by
the body pipeline, plus the V3 hand/wrist dependencies.

A reproducible setup system for the PC, robot-side runtime, and Jetson
environment is being developed separately from generated runtime state.

## Current Validation Boundary

### V2

Validated:

- software/runtime regression;
- live camera alignment;
- MuJoCo end-to-end operation;
- physical Unitree G1 teleoperation.

### V3

Validated so far:

- wrist-orientation geometry;
- live WiLoR hand processing;
- hand trust and reacquisition logic;
- G1 wrist mapping;
- anti-windup recovery behavior;
- software integration with the V2 body path;
- combined MuJoCo execution.

Still unresolved:

- visibly segmented body/wrist motion under the current combined load;
- abrupt whole-arm response during some wrist-only movements;
- final smooth wrist-command delivery;
- combined physical Unitree G1 validation.

V3 should therefore be considered **experimental until these issues are
resolved and the combined physical validation stage is completed**.
