#!/usr/bin/env bash

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null &&
    pwd
)"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/common.sh"

fail=0

check_path() {
    label="$1"
    path="$2"

    if [ -e "$path" ]; then
        printf 'PASS  %-22s %s\n' "$label" "$path"
    else
        printf 'FAIL  %-22s %s\n' "$label" "$path"
        fail=1
    fi
}

echo "================ SOURCE / RUNTIME PATHS ================"

check_path "GVHMR" "$GVHMR_ROOT"
check_path "GENMO" "$GENMO_ROOT"
check_path "SONIC" "$SONIC_ROOT"
check_path "torch2trt" "$TORCH2TRT_ROOT"
check_path "pose Python" "$POSE_PYTHON"
check_path "TRT8 Python" "$TRT8_PYTHON_DIR"
check_path "TRT8 libraries" "$TRT8_LIB_DIR"
check_path "TRT10 libraries" "$TRT10_LIB_DIR"

echo
echo "================ MODEL / CALIBRATION ARTIFACTS ================"

check_path "ViTPose TRT state" "$VITPOSE_TRT_STATE"
check_path "HMR2 ONNX" "$HMR2_ONNX"
check_path "HMR2 ONNX data" "${HMR2_ONNX}.data"
check_path "HMR2 TRT cache" "$HMR2_TRT_CACHE"
check_path "gravity" "$GRAVITY_FILE"
check_path "F_LEFT" "$F_LEFT_FILE"
check_path "publisher helper" "$PUBLISHER_SOURCE_DIR/soma_to_smpl.py"

echo
echo "================ CALIBRATION HASHES ================"

if [ -f "$GRAVITY_FILE" ]; then
    actual="$(sha256sum "$GRAVITY_FILE" | awk '{print $1}')"
    expected="e269df619bc7e7a27741b93dacfe57e6fde45f1969023fd8882f58b5c611e9e9"
    if [ "$actual" = "$expected" ]; then
        echo "PASS  gravity SHA256"
    else
        echo "FAIL  gravity SHA256"
        echo "      expected: $expected"
        echo "      actual:   $actual"
        fail=1
    fi
fi

if [ -f "$F_LEFT_FILE" ]; then
    actual="$(sha256sum "$F_LEFT_FILE" | awk '{print $1}')"
    expected="b06f8a293f34ee7b07f09227bdba8a18a1937a604038bc9edd88a9c27627c075"
    if [ "$actual" = "$expected" ]; then
        echo "PASS  F_LEFT SHA256"
    else
        echo "FAIL  F_LEFT SHA256"
        echo "      expected: $expected"
        echo "      actual:   $actual"
        fail=1
    fi
fi

echo
echo "================ PYTHON STACK ================"

if [ -x "$POSE_PYTHON" ]; then
    "$POSE_PYTHON" - <<'PY'
modules = [
    "torch",
    "onnxruntime",
    "cv2",
    "numpy",
    "hydra",
    "zmq",
    "pytorch3d",
    "smplx",
]

for name in modules:
    try:
        module = __import__(name)
        version = getattr(module, "__version__", "installed")
        print(f"PASS  {name:16s} {version}")
    except Exception as exc:
        print(f"FAIL  {name:16s} {exc!r}")
PY
else
    echo "FAIL  pose Python is not executable"
    fail=1
fi

echo
echo "================ CAMERA CONFIGURATION ================"

if [ -z "${CAMERA_DEVICE:-}" ]; then
    echo "INFO  CAMERA_DEVICE is not configured."
else
    echo "INFO  configured camera: $CAMERA_DEVICE"

    if [ -e "$CAMERA_DEVICE" ]; then
        echo "PASS  camera device path exists"
    else
        echo "FAIL  configured camera device path does not exist"
        fail=1
    fi
fi

echo
echo "================ RESULT ================"

if [ "$fail" -eq 0 ]; then
    echo "ENVIRONMENT CHECK: PASS"
else
    echo "ENVIRONMENT CHECK: FAIL"
fi
