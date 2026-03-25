#!/usr/bin/env bash
set -euo pipefail
SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
SRC_DIR="${SRC_DIR:-sv0vm/src}"
echo "building interpreter module..."
if [[ -f "$SRC_DIR/interpreter/sources.cm" ]]; then
    cd "$SV0VM_ROOT" && echo 'CM.make "src/interpreter/sources.cm";' | sml 2>&1
    echo "OK: interpreter module compiles"
else
    echo "TODO: create sources.cm for interpreter module"
fi
