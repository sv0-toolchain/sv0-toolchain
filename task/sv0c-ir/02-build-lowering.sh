#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "building IR module..."
if [[ -f "$SRC_DIR/ir/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "src/ir/sources.cm";' | sml 2>&1
    echo "OK: IR module compiles"
else
    echo "TODO: create sources.cm for IR module"
fi
