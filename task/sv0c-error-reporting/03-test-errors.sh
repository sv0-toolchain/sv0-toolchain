#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/sml}"
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
echo "testing error module..."
if [[ -f "$SRC_DIR/error/sources.cm" ]]; then
    echo "compiling error module..."
    cd "$SV0C_ROOT" && echo 'CM.make "sml/error/sources.cm";' | sml 2>&1 || {
        echo "FAIL: error module compilation failed"
        exit 1
    }
    echo "OK: error module compiles"
elif [[ -f "$SV0C_ROOT/sources.cm" ]]; then
    echo "compiling sv0c via root sources.cm..."
    cd "$SV0C_ROOT" && echo 'CM.make "sources.cm";' | sml 2>&1 || {
        echo "FAIL: sv0c compilation failed"
        exit 1
    }
    echo "OK: sv0c compiles (root sources.cm; no sml/error/sources.cm yet)"
else
    echo "TODO: create sources.cm for error module"
fi
