#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$1"; shift
if [[ -f ".venv/bin/activate" ]]; then
    source .venv/bin/activate
fi
exec python3 "$SCRIPT" "$@"
