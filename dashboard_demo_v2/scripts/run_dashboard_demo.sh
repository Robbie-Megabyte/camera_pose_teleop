#!/usr/bin/env bash

SCRIPT_DIR="$(
    cd "$(
        dirname "${BASH_SOURCE[0]}"
    )" >/dev/null 2>&1
    pwd
)"

DASHBOARD_ROOT="$(
    cd "$SCRIPT_DIR/.." >/dev/null 2>&1
    pwd
)"

REPO_ROOT="$(
    cd "$DASHBOARD_ROOT/../.." >/dev/null 2>&1
    pwd
)"

PYTHON="${POSE_PYTHON:-$HOME/GVHMR/.venv/bin/python}"

HOST="${DASHBOARD_HOST:-127.0.0.1}"
PORT="${DASHBOARD_PORT:-8088}"

cd "$REPO_ROOT" || return 1 2>/dev/null || exit 1

exec "$PYTHON" \
    "$DASHBOARD_ROOT/backend/server.py" \
    --host "$HOST" \
    --port "$PORT"
