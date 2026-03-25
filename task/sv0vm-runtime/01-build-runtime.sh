#!/usr/bin/env bash
set -euo pipefail
SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
SRC_DIR="${SRC_DIR:-sv0vm/src}"
echo "building runtime module..."
if [[ -f "$SRC_DIR/runtime/sources.cm" ]]; then
    cd "$SV0VM_ROOT" && echo 'CM.make "src/runtime/sources.cm";' | sml 2>&1
    echo "OK: runtime module compiles"
else
    echo "TODO: create sources.cm for runtime module"
fi
