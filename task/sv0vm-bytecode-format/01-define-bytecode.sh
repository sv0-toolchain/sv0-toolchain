#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0vm/src}"
echo "checking bytecode definition at $SRC_DIR/bytecode/bytecode.sml..."
test -f "$SRC_DIR/bytecode/bytecode.sml" && echo "OK" || echo "TODO: create bytecode.sml"
