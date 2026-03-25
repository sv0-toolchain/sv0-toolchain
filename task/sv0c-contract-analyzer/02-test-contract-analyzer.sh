#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"
echo "running contract analyzer tests..."
if [[ -f "$TEST_DIR/contract_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/contract_test.sml";' | sml 2>&1
    echo "CONTRACT_STATUS=OK"
else
    echo "TODO: create contract analyzer test suite"
    echo "CONTRACT_STATUS=TODO"
fi
