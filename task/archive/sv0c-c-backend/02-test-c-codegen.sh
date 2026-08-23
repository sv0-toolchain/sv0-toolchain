#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"
echo "running C codegen tests..."
if [[ -f "$TEST_DIR/codegen_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/codegen_test.sml";' | sml 2>&1
    echo "CBACKEND_STATUS=OK"
else
    echo "TODO: create C codegen test suite"
    echo "CBACKEND_STATUS=TODO"
fi
