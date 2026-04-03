#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/sml}"
echo "checking IR definition at $SRC_DIR/ir/ir.sml..."
test -f "$SRC_DIR/ir/ir.sml" && echo "OK: ir.sml exists" || echo "TODO: create ir.sml"
