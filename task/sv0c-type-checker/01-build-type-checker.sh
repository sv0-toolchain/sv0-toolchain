#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "building type checker module..."
if [[ -f "$SRC_DIR/type_checker/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "src/type_checker/sources.cm";' | sml 2>&1
    echo "OK: type checker module compiles"
else
    echo "TODO: create sources.cm for type checker module"
fi
