#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "checking token definition at $SRC_DIR/lexer/token.sml..."
test -f "$SRC_DIR/lexer/token.sml" && echo "OK: token.sml exists" || echo "TODO: create token.sml"
