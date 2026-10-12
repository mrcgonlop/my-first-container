#!/usr/bin/env bash
# Install Wine and DOSBox-X for Time Capsule (Linux and Windows, x86_64 or ARM64).
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python

exec "$PYTHON" scripts/setup.py "$@"
