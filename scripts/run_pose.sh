#!/usr/bin/env bash

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null &&
    pwd
)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

MODE="${1:-normal}"

ALIGNMENT_MODE="${CAMERA_ALIGNMENT_MODE:-session_v2}"
SESSION_ALIGNMENT_FILE="${SESSION_ALIGNMENT_FILE:-$RUNTIME_ROOT/calibration/session_alignment.npz}"

CAMERA_SELECTION_MODE="${CAMERA_SELECTION_MODE:-}"

if [ -z "$CAMERA_SELECTION_MODE" ]; then
    if [ "$ALIGNMENT_MODE" = "fixed_v1" ]; then
        CAMERA_SELECTION_MODE="manual"
    else
        CAMERA_SELECTION_MODE="auto"
    fi
fi

CAMERA_STATE_FILE="${CAMERA_STATE_FILE:-$RUNTIME_ROOT/camera/preferred_camera.json}"
CAMERA_RESELECT="${CAMERA_RESELECT:-0}"

case "$CAMERA_RESELECT" in
    0|1)
        ;;
    *)
        echo "Invalid CAMERA_RESELECT: $CAMERA_RESELECT"
        echo "Expected: 0 or 1"
        false
        ;;
esac

case "$CAMERA_SELECTION_MODE" in
    auto|manual)
        ;;
    *)
        echo "Invalid CAMERA_SELECTION_MODE: $CAMERA_SELECTION_MODE"
        echo "Expected: auto or manual"
        false
        ;;
esac

case "$ALIGNMENT_MODE" in
    fixed_v1|session_v2)
        ;;
    *)
        echo "Invalid CAMERA_ALIGNMENT_MODE: $ALIGNMENT_MODE"
        echo "Expected: fixed_v1 or session_v2"
        false
        ;;
esac

case "$MODE" in
    normal)
        BASE="$CPT_ROOT/perception/runtime/live_gvhmr_pair_prio2_interactive_test.py"
        ;;
    preview)
        BASE="$CPT_ROOT/camera/previews/live_gvhmr_pair_prio2_interactive_test_preview.py"
        ;;
    keypoints)
        BASE="$CPT_ROOT/camera/previews/live_gvhmr_pair_prio2_interactive_keypoint_preview.py"
        ;;
    dual)
        BASE="$CPT_ROOT/camera/previews/live_gvhmr_pair_prio2_interactive_test_dual_preview.py"
        ;;
    *)
        echo "Usage: $0 [normal|preview|keypoints|dual]"
        false
        ;;
esac

WRAPPER="$CPT_ROOT/sonic/runtime/live_gvhmr_pair_prio2_sonic_async_interactive.py"
CAMERA_MANAGER="$CPT_ROOT/camera/device_manager.py"

missing=0

for path in \
    "$GVHMR_ROOT" \
    "$GENMO_ROOT" \
    "$SONIC_ROOT" \
    "$TORCH2TRT_ROOT" \
    "$POSE_PYTHON" \
    "$TRT8_PYTHON_DIR" \
    "$TRT8_LIB_DIR" \
    "$TRT10_LIB_DIR" \
    "$VITPOSE_TRT_STATE" \
    "$HMR2_ONNX" \
    "$HMR2_TRT_CACHE" \
    "$PUBLISHER_SOURCE_DIR/soma_to_smpl.py" \
    "$BASE" \
    "$WRAPPER" \
    "$CAMERA_MANAGER"
do
    if [ ! -e "$path" ]; then
        echo "MISSING: $path"
        missing=1
    fi
done

if [ "$ALIGNMENT_MODE" = "fixed_v1" ]; then
    for path in \
        "$GRAVITY_FILE" \
        "$F_LEFT_FILE"
    do
        if [ ! -e "$path" ]; then
            echo "MISSING V1 CALIBRATION: $path"
            missing=1
        fi
    done
fi

CAMERA_STABLE_ID=""
CAMERA_DISPLAY_NAME=""
CAMERA_SELECTION_REASON=""

if [ "$CAMERA_SELECTION_MODE" = "auto" ]; then
    # Do not allow a CAMERA_DEVICE inherited from local.env
    # to mask a failed or malformed automatic selection.
    CAMERA_DEVICE=""

    mkdir -p "$(dirname "$CAMERA_STATE_FILE")"

    if [ -x "$POSE_PYTHON" ] && [ -f "$CAMERA_MANAGER" ]; then
        CAMERA_SELECT_ARGS=(
            "$CAMERA_MANAGER"
            select
            --state-file "$CAMERA_STATE_FILE"
            --shell
        )

        if [ "$CAMERA_RESELECT" = "1" ]; then
            CAMERA_SELECT_ARGS+=(
                --reselect
            )
        fi

        CAMERA_SELECTION_SHELL="$(
            "$POSE_PYTHON" "${CAMERA_SELECT_ARGS[@]}"
        )"

        CAMERA_SELECTION_RC=$?

        if [ "$CAMERA_SELECTION_RC" -ne 0 ]; then
            echo "Camera auto-selection failed."
            missing=1
        else
            eval "$CAMERA_SELECTION_SHELL"

            if [ -z "${CAMERA_DEVICE:-}" ]; then
                echo "Camera auto-selection produced no CAMERA_DEVICE."
                missing=1
            fi

            if [ -z "${CAMERA_STABLE_ID:-}" ]; then
                echo "Camera auto-selection produced no CAMERA_STABLE_ID."
                missing=1
            fi

            if [ -z "${CAMERA_SELECTION_REASON:-}" ]; then
                echo "Camera auto-selection produced no CAMERA_SELECTION_REASON."
                missing=1
            fi
        fi
    else
        echo "Camera auto-selection unavailable."
        missing=1
    fi
else
    CAMERA_SELECTION_REASON="manual"

    if [ -z "${CAMERA_DEVICE:-}" ]; then
        echo "MISSING: CAMERA_DEVICE for manual camera mode"
        missing=1
    fi
fi

if (
    [ -n "${CAMERA_DEVICE:-}" ] &&
    [ ! -e "$CAMERA_DEVICE" ]
); then
    echo "MISSING CAMERA DEVICE: $CAMERA_DEVICE"
    missing=1
fi

# ------------------------------------------------------------
# Resolve one authoritative capture profile for V2.
#
# fixed_v1 deliberately preserves the protected historical
# 1280x720 MJPEG@30 behavior.
# ------------------------------------------------------------

CAMERA_WIDTH="${CAMERA_WIDTH:-1280}"
CAMERA_HEIGHT="${CAMERA_HEIGHT:-720}"
CAMERA_FPS="${CAMERA_FPS:-30}"
CAMERA_FORMAT="${CAMERA_FORMAT:-mjpeg}"
CAMERA_FOURCC="${CAMERA_FOURCC:-MJPG}"
CAMERA_PROFILE_REASON="fixed_v1_legacy"

if (
    [ "$ALIGNMENT_MODE" = "session_v2" ] &&
    [ "$missing" -eq 0 ]
); then
    CAMERA_PROFILE_ARGS=(
        profile
        --device "$CAMERA_DEVICE"
        --shell
    )

    if [ -n "${CAMERA_PROFILE_OVERRIDE:-}" ]; then
        CAMERA_PROFILE_ARGS+=(
            --override
            "$CAMERA_PROFILE_OVERRIDE"
        )
    fi

    CAMERA_PROFILE_SHELL="$(
        "$POSE_PYTHON"             "$CAMERA_MANAGER"             "${CAMERA_PROFILE_ARGS[@]}"
    )"

    CAMERA_PROFILE_RC=$?

    if [ "$CAMERA_PROFILE_RC" -ne 0 ]; then
        echo "Camera capture-profile resolution failed."
        missing=1
    else
        CAMERA_WIDTH=""
        CAMERA_HEIGHT=""
        CAMERA_FPS=""
        CAMERA_FORMAT=""
        CAMERA_FOURCC=""

        eval "$CAMERA_PROFILE_SHELL"

        if (
            [ -z "${CAMERA_WIDTH:-}" ] ||
            [ -z "${CAMERA_HEIGHT:-}" ] ||
            [ -z "${CAMERA_FPS:-}" ] ||
            [ -z "${CAMERA_FORMAT:-}" ] ||
            [ -z "${CAMERA_FOURCC:-}" ]
        ); then
            echo "Camera capture-profile resolver returned incomplete data."
            missing=1
        else
            if [ -n "${CAMERA_PROFILE_OVERRIDE:-}" ]; then
                CAMERA_PROFILE_REASON="v4l2_override"
            else
                CAMERA_PROFILE_REASON="v4l2_auto"
            fi
        fi
    fi
fi

if [ "$missing" -ne 0 ]; then
    echo
    echo "Environment incomplete."
    echo "Run:"
    echo "  ./scripts/check_environment.sh"
    false
else
    GEN_NVIDIA_LIBS="$(
        find "$GENMO_ROOT/.venv" \
            -type d \
            -path '*/site-packages/nvidia/*/lib' \
            -print 2>/dev/null \
        | sort \
        | paste -sd: -
    )"

    export PYTHONPATH="$TRT8_PYTHON_DIR:$TORCH2TRT_ROOT:$CPT_ROOT/alignment:$CPT_ROOT/retargeting:$CPT_ROOT/sonic/runtime:$GENMO_ROOT:$GVHMR_ROOT${PYTHONPATH:+:$PYTHONPATH}"

    export LD_LIBRARY_PATH="$TRT10_LIB_DIR:$TRT8_LIB_DIR${GEN_NVIDIA_LIBS:+:$GEN_NVIDIA_LIBS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

    export LIVE_GVHMR_GV="$GVHMR_ROOT"
    export LIVE_GVHMR_CAM="$CAMERA_DEVICE"

    export LIVE_GVHMR_WIDTH="$CAMERA_WIDTH"
    export LIVE_GVHMR_HEIGHT="$CAMERA_HEIGHT"
    export LIVE_GVHMR_FPS="$CAMERA_FPS"
    export LIVE_GVHMR_INPUT_FORMAT="$CAMERA_FORMAT"
    export LIVE_GVHMR_FOURCC="$CAMERA_FOURCC"

    # V2 gets the real-2D startup framing gate.
    # Protected fixed_v1 behavior remains unchanged.
    if [ "$ALIGNMENT_MODE" = "session_v2" ]; then
        export LIVE_GVHMR_FRAMING_GATE="1"
    else
        export LIVE_GVHMR_FRAMING_GATE="0"
    fi

    export LIVE_GVHMR_VIT_STATE="$VITPOSE_TRT_STATE"
    export LIVE_GVHMR_HMR_ONNX="$HMR2_ONNX"
    export LIVE_GVHMR_HMR_CACHE="$HMR2_TRT_CACHE"

    export SONIC_ROOT
    export SONIC_EMA_WEIGHT

    mkdir -p "$RUNTIME_ROOT/logs"

    if [ "$ALIGNMENT_MODE" = "session_v2" ]; then
        mkdir -p "$(dirname "$SESSION_ALIGNMENT_FILE")"
    fi

    STAMP="$(date +%Y%m%d_%H%M%S)"
    export LIVE_GVHMR_OUT_PREFIX="$RUNTIME_ROOT/logs/live_${MODE}_${STAMP}"

    BASE_SHA="$(sha256sum "$BASE" | awk '{print $1}')"

    echo "============================================================"
    echo "Camera Pose Teleop"
    echo "============================================================"
    echo "mode:            $MODE"
    echo "camera select:   $CAMERA_SELECTION_MODE"
    echo "camera reselect: $CAMERA_RESELECT"
    echo "camera:          $CAMERA_DEVICE"

    if [ -n "$CAMERA_DISPLAY_NAME" ]; then
        echo "camera name:     $CAMERA_DISPLAY_NAME"
    fi

    if [ -n "$CAMERA_STABLE_ID" ]; then
        echo "camera identity: $CAMERA_STABLE_ID"
    fi

    echo "camera reason:   $CAMERA_SELECTION_REASON"
    echo "capture profile: ${CAMERA_WIDTH}x${CAMERA_HEIGHT} @ ${CAMERA_FPS} fps"
    echo "capture format:  $CAMERA_FORMAT ($CAMERA_FOURCC)"
    echo "profile reason:  $CAMERA_PROFILE_REASON"
    echo "alignment:       $ALIGNMENT_MODE"
    echo "framing gate:    $LIVE_GVHMR_FRAMING_GATE"

    if [ "$ALIGNMENT_MODE" = "session_v2" ]; then
        echo "session output:  $SESSION_ALIGNMENT_FILE"
    else
        echo "gravity file:    $GRAVITY_FILE"
        echo "V1 reference:    $F_LEFT_FILE"
    fi

    echo "pose port:       $SONIC_POSE_PORT"
    echo "pose topic:      $SONIC_POSE_TOPIC"
    echo "EMA weight:      $SONIC_EMA_WEIGHT"
    echo "output:          $LIVE_GVHMR_OUT_PREFIX"
    echo "============================================================"

    cd "$GVHMR_ROOT" || false

    "$POSE_PYTHON" -u "$WRAPPER" \
        --base-runner "$BASE" \
        --expected-base-sha "$BASE_SHA" \
        --sonic-root "$SONIC_ROOT" \
        --publisher-source-dir "$PUBLISHER_SOURCE_DIR" \
        --sonic-mode publish \
        --sonic-port "$SONIC_POSE_PORT" \
        --sonic-topic "$SONIC_POSE_TOPIC" \
        --alignment-mode "$ALIGNMENT_MODE" \
        --session-alignment "$SESSION_ALIGNMENT_FILE" \
        --gravity-file "$GRAVITY_FILE" \
        --calibration-reference "$F_LEFT_FILE" \
        2>&1 \
    | tee "${LIVE_GVHMR_OUT_PREFIX}_console.log"
fi
