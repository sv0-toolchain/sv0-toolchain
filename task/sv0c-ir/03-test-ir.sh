#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"
echo "running IR tests..."
if [[ -f "$TEST_DIR/ir_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/ir_test.sml";' | sml 2>&1
    echo "IR_STATUS=OK"
else
    echo "TODO: create IR test suite"
    echo "IR_STATUS=TODO"
fi
