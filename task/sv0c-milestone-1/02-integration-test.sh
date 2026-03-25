#!/usr/bin/env bash
set -euo pipefail

echo "=== sv0c milestone 1: integration test suite ==="

SV0C_ROOT="${SV0C_ROOT:-sv0c}"
BUILD_DIR="${BUILD_DIR:-sv0c/build}"
TEST_DIR="${TEST_DIR:-sv0c/test}"

mkdir -p "$BUILD_DIR"

PASS=0
FAIL=0
TOTAL=0

run_test() {
    local test_name="$1"
    local test_file="$2"
    TOTAL=$((TOTAL + 1))

    echo -n "  $test_name... "

    if [[ ! -f "$test_file" ]]; then
        echo "SKIP (file not found)"
        return
    fi

    # TODO: invoke sv0c to compile .sv0 -> .c
    # TODO: invoke cc to compile .c -> binary
    # TODO: run binary and check exit code
    echo "TODO (not yet implemented)"
}

echo "integration tests:"
run_test "hello world" "$TEST_DIR/integration/hello.sv0"
run_test "contracts" "$TEST_DIR/integration/contracts.sv0"
run_test "pattern matching" "$TEST_DIR/integration/patterns.sv0"
run_test "structs and methods" "$TEST_DIR/integration/structs.sv0"
run_test "generics" "$TEST_DIR/integration/generics.sv0"
run_test "modules" "$TEST_DIR/integration/modules.sv0"

echo ""
echo "results: $PASS passed, $FAIL failed, $TOTAL total"
