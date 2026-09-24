#!/usr/bin/env bash

ROOT="$(
    cd "$(dirname "${BASH_SOURCE[0]}")/.."
    pwd
)"

HOST="${UI_DEV_HOST:-127.0.0.1}"
PORT="${UI_DEV_PORT:-8088}"

echo
echo "============================================================"
echo " CAMERA POSE TELEOP — UI DEVELOPMENT MODE"
echo "============================================================"
echo " NO ROBOT / CAMERA / SONIC / GVHMR / ROS CONNECTIONS"
echo
echo " Dashboard: http://${HOST}:${PORT}"
echo " Ctrl+C stops only this mock UI server."
echo "============================================================"
echo

exec python3 \
    "$ROOT/dev/mock_server.py" \
    --host "$HOST" \
    --port "$PORT"
