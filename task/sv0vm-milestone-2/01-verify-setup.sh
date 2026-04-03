#!/usr/bin/env bash
set -euo pipefail

echo "=== sv0vm milestone 2: environment verification ==="

if ! command -v sml &>/dev/null; then
    echo "FAIL: SML/NJ not found"
    exit 1
fi
echo "OK: sml found"

SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
if [[ ! -d "$SV0VM_ROOT/src" ]]; then
    echo "FAIL: sv0vm source directory not found"
    exit 1
fi
echo "OK: sv0vm source directory exists"

SV0C_ROOT="${SV0C_ROOT:-sv0c}"
if [[ ! -f "$SV0C_ROOT/sml/ir/ir.sml" ]]; then
    echo "WARN: sv0c IR not yet implemented (prerequisite for VM backend)"
fi

echo "environment verification complete"
