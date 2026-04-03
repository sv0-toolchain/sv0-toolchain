#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/sml}"
echo "building contract analyzer module..."
if [[ -f "$SRC_DIR/contract_analyzer/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "sml/contract_analyzer/sources.cm";' | sml 2>&1
    echo "OK: contract analyzer module compiles"
elif [[ -f "$SV0C_ROOT/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "sources.cm";' | sml 2>&1
    echo "OK: sv0c compiles (root sources.cm; no sml/contract_analyzer/sources.cm yet)"
else
    echo "TODO: create sources.cm for contract analyzer module"
fi
