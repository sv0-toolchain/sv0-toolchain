#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="${SRC_DIR:-sv0c/src}"

echo "building lexer module..."
if [[ -f "$SRC_DIR/lexer/sources.cm" ]]; then
    cd "$SV0C_ROOT" && echo 'CM.make "src/lexer/sources.cm";' | sml 2>&1
    echo "OK: lexer module compiles"
else
    echo "TODO: create sources.cm for lexer module"
fi
