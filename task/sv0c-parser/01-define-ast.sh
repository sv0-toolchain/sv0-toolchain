#!/usr/bin/env bash
set -euo pipefail
SRC_DIR="${SRC_DIR:-sv0c/sml}"
echo "checking AST definition at $SRC_DIR/ast/ast.sml..."
test -f "$SRC_DIR/ast/ast.sml" && echo "OK: ast.sml exists" || echo "TODO: create ast.sml"
