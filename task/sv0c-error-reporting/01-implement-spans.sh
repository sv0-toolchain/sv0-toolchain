#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/src}"
echo "implementing source spans at $SRC_DIR/error/span.sml..."
# AI agent creates the SML source file
test -f "$SRC_DIR/error/span.sml" && echo "OK: span.sml exists" || echo "TODO: create span.sml"
