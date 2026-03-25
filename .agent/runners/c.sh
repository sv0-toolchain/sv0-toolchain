#!/usr/bin/env bash
set -euo pipefail
SCRIPT="$1"; shift
BINARY="${SCRIPT%.c}"
cc -o "$BINARY" "$SCRIPT" && exec "$BINARY" "$@"
