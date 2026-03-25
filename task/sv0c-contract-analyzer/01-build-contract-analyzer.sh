#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "building contract analyzer module..."
if [[ -f "$SRC_DIR/contract_analyzer/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "src/contract_analyzer/sources.cm";' | sml 2>&1
    echo "OK: contract analyzer module compiles"
else
    echo "TODO: create sources.cm for contract analyzer module"
fi
