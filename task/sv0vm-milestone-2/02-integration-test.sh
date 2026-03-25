#!/usr/bin/env bash
set -euo pipefail

echo "=== sv0vm milestone 2: integration test suite ==="

SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
BUILD_DIR="${BUILD_DIR:-sv0vm/build}"
TEST_DIR="${TEST_DIR:-sv0c/test}"

mkdir -p "$BUILD_DIR"

echo "integration tests (bytecode path):"

run_vm_test() {
    local name="$1"
    local sv0_file="$2"

    echo -n "  $name... "

    if [[ ! -f "$sv0_file" ]]; then
        echo "SKIP (source not found)"
        return
    fi

    # TODO: invoke sv0c --target=vm to compile .sv0 -> .sv0b
    # TODO: invoke sv0vm to execute .sv0b
    # TODO: compare output against expected

    echo "TODO (pipeline not yet connected)"
}

run_vm_test "hello" "$TEST_DIR/integration/hello.sv0"
run_vm_test "gcd" "$TEST_DIR/integration/gcd.sv0"
run_vm_test "contracts" "$TEST_DIR/integration/contracts.sv0"
run_vm_test "patterns" "$TEST_DIR/integration/patterns.sv0"

echo ""
echo "integration tests complete"
