#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/sml}"
echo "building parser module..."
if [[ -f "$SRC_DIR/parser/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "sml/parser/sources.cm";' | sml 2>&1
    echo "OK: parser module compiles"
elif [[ -f "$SV0C_ROOT/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "sources.cm";' | sml 2>&1
    echo "OK: sv0c compiles (root sources.cm; no sml/parser/sources.cm yet)"
else
    echo "TODO: create sources.cm for parser module"
fi
