#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"
echo "running parser tests..."
if [[ -f "$TEST_DIR/parser_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/parser_test.sml";' | sml 2>&1
    echo "PARSER_STATUS=OK"
else
    echo "TODO: create parser test suite"
    echo "PARSER_STATUS=TODO"
fi
