#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "testing error module..."
if [[ -f "$SRC_DIR/error/sources.cm" ]]; then
    echo "compiling error module..."
    cd "${SV0C_ROOT:-sv0c}" && echo 'CM.make "src/error/sources.cm";' | sml 2>&1 || {
        echo "FAIL: error module compilation failed"
        exit 1
    }
    echo "OK: error module compiles"
else
    echo "TODO: create sources.cm for error module"
fi
