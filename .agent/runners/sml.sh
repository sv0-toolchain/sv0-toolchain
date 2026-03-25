#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$1"; shift

SML_CMD=""
if command -v sml &>/dev/null; then
    SML_CMD=sml
elif command -v smlnj &>/dev/null; then
    SML_CMD=smlnj
else
    echo "error: SML/NJ not found. install with: brew install smlnj" >&2
    exit 1
fi

exec "$SML_CMD" "$@" < "$SCRIPT"
