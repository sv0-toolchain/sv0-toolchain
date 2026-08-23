#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
TEST_DIR="${TEST_DIR:-sv0c/test}"
echo "running name resolution tests..."
if [[ -f "$TEST_DIR/resolver_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/resolver_test.sml";' | sml 2>&1
    echo "RESOLVER_STATUS=OK"
else
    echo "TODO: create resolver test suite"
    echo "RESOLVER_STATUS=TODO"
fi
