#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"
echo "running type checker tests..."
if [[ -f "$TEST_DIR/checker_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/checker_test.sml";' | sml 2>&1
    echo "TYPECHECKER_STATUS=OK"
else
    echo "TODO: create type checker test suite"
    echo "TYPECHECKER_STATUS=TODO"
fi
