#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "building VM backend module..."
mkdir -p "$SRC_DIR/backend/vm"
if [[ -f "$SRC_DIR/backend/vm/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "src/backend/vm/sources.cm";' | sml 2>&1
    echo "OK: VM backend module compiles"
else
    echo "TODO: create sources.cm for VM backend module"
fi
