#!/usr/bin/env bash
set -euo pipefail

SV0C_ROOT="${SV0C_ROOT:-sv0c}"

echo "verifying sv0c project structure..."

required_dirs=(
    "$SV0C_ROOT/sml-legacy/lexer"
    "$SV0C_ROOT/sml-legacy/ast"
    "$SV0C_ROOT/sml-legacy/parser"
    "$SV0C_ROOT/sml-legacy/name_resolution"
    "$SV0C_ROOT/sml-legacy/type_checker"
    "$SV0C_ROOT/sml-legacy/contract_analyzer"
    "$SV0C_ROOT/sml-legacy/ir"
    "$SV0C_ROOT/sml-legacy/backend/c"
    "$SV0C_ROOT/sml-legacy/error"
)

for dir in "${required_dirs[@]}"; do
    if [[ -d "$dir" ]]; then
        echo "  OK: $dir"
    else
        echo "  FAIL: missing $dir"
        exit 1
    fi
done

echo "project structure verified"
echo "SETUP_STATUS=OK"
