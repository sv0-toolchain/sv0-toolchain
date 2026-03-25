#!/usr/bin/env bash
set -euo pipefail

echo "=== sv0c milestone 1: environment verification ==="

if ! command -v sml &>/dev/null; then
    echo "FAIL: SML/NJ not found"
    echo "install with: brew install smlnj"
    exit 1
fi
echo "OK: sml found at $(command -v sml)"
sml @SMLversion 2>&1 | head -1 || true

if ! command -v cc &>/dev/null; then
    echo "FAIL: C compiler not found"
    exit 1
fi
echo "OK: cc found at $(command -v cc)"

SV0C_ROOT="${SV0C_ROOT:-sv0c}"
if [[ ! -d "$SV0C_ROOT/src" ]]; then
    echo "FAIL: sv0c source directory not found at $SV0C_ROOT/src"
    exit 1
fi
echo "OK: sv0c source directory exists"

echo ""
echo "environment verification complete"
