#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONUNBUFFERED=1
export PIP_DISABLE_PIP_VERSION_CHECK=1

if [ -f "$SCRIPT_DIR/.venv/bin/activate" ]; then
	# shellcheck disable=SC1091
	source "$SCRIPT_DIR/.venv/bin/activate"
fi

exec python3 "$SCRIPT_DIR/nexus.py" "$@"