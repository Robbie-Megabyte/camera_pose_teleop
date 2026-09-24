#!/usr/bin/env bash

CPT_ROOT="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null &&
    pwd
)"

LOCAL_ENV="$CPT_ROOT/configs/local.env"

if [ -f "$LOCAL_ENV" ]; then
    # shellcheck disable=SC1090
    source "$LOCAL_ENV"
fi

DEPS_ROOT="${DEPS_ROOT:-$CPT_ROOT/.deps}"
ARTIFACTS_ROOT="${ARTIFACTS_ROOT:-$CPT_ROOT/.artifacts}"
RUNTIME_ROOT="${RUNTIME_ROOT:-$CPT_ROOT/.runtime}"

GVHMR_ROOT="${GVHMR_ROOT:-$DEPS_ROOT/GVHMR}"
GENMO_ROOT="${GENMO_ROOT:-$DEPS_ROOT/GENMO}"
SONIC_ROOT="${SONIC_ROOT:-$DEPS_ROOT/GR00T-WholeBodyControl}"
TORCH2TRT_ROOT="${TORCH2TRT_ROOT:-$DEPS_ROOT/torch2trt}"

POSE_PYTHON="${POSE_PYTHON:-$GVHMR_ROOT/.venv/bin/python}"

VITPOSE_TRT_STATE="${VITPOSE_TRT_STATE:-$ARTIFACTS_ROOT/vitpose/vitpose_huge_b1_fp16_trt861_state.pth}"
HMR2_ONNX="${HMR2_ONNX:-$GENMO_ROOT/inputs/onnx/hmr2.onnx}"
HMR2_TRT_CACHE="${HMR2_TRT_CACHE:-$ARTIFACTS_ROOT/hmr2/trt_cache}"

GRAVITY_FILE="$CPT_ROOT/calibration/legacy_fixed/stereo_gravity_1280x720.npz"
F_LEFT_FILE="$CPT_ROOT/calibration/reference/F_LEFT_HMR2_CALIBRATED_ROOT.npz"

PUBLISHER_SOURCE_DIR="$CPT_ROOT/sonic/publisher"

SONIC_POSE_PORT="${SONIC_POSE_PORT:-5556}"
SONIC_POSE_TOPIC="${SONIC_POSE_TOPIC:-pose}"
SONIC_EMA_WEIGHT="${SONIC_EMA_WEIGHT:-0.0}"

RAW_PREVIEW_PORT="${RAW_PREVIEW_PORT:-5600}"
KEYPOINT_PREVIEW_PORT="${KEYPOINT_PREVIEW_PORT:-5601}"
