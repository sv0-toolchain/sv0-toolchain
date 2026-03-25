#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"

echo "running lexer tests..."
if [[ -f "$TEST_DIR/lexer_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/lexer_test.sml";' | sml 2>&1
    echo "LEXER_STATUS=OK"
else
    echo "TODO: create lexer test suite"
    echo "LEXER_STATUS=TODO"
fi
