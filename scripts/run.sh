#!/usr/bin/env bash
# Launch the Time Capsule CLI from the repository root.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

exec "$PYTHON" launcher.py "$@"
