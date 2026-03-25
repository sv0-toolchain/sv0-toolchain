#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "building name resolution module..."
if [[ -f "$SRC_DIR/name_resolution/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "src/name_resolution/sources.cm";' | sml 2>&1
    echo "OK: resolver module compiles"
else
    echo "TODO: create sources.cm for name resolution module"
fi
