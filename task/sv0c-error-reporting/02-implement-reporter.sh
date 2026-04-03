#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/sml}"
echo "implementing error reporter at $SRC_DIR/error/reporter.sml..."
test -f "$SRC_DIR/error/reporter.sml" && echo "OK: reporter.sml exists" || echo "TODO: create reporter.sml"
