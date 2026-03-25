#!/usr/bin/env bash
set -euo pipefail

SV0C_ROOT="${SV0C_ROOT:-sv0c}"
BUILD_DIR="${BUILD_DIR:-sv0c/build}"

echo "=== sv0c end-to-end compilation tests ==="

mkdir -p "$BUILD_DIR/c" "$BUILD_DIR/bin"

compile_and_run() {
    local name="$1"
    local sv0_file="$2"
    local expected_output="$3"

    echo -n "  $name... "

    if [[ ! -f "$sv0_file" ]]; then
        echo "SKIP (source not found)"
        return
    fi

    # TODO: invoke sv0c pipeline
    # sv0c $sv0_file -o $BUILD_DIR/c/${name}.c
    # cc -o $BUILD_DIR/bin/$name $BUILD_DIR/c/${name}.c $BUILD_DIR/c/sv0_runtime.c
    # actual=$($BUILD_DIR/bin/$name 2>&1)
    # if [[ "$actual" == "$expected_output" ]]; then echo "OK"; else echo "FAIL"; fi

    echo "TODO (pipeline not yet connected)"
}

compile_and_run "hello" "$SV0C_ROOT/test/integration/hello.sv0" "hello, sv0"
compile_and_run "gcd" "$SV0C_ROOT/test/integration/gcd.sv0" "4"
compile_and_run "shapes" "$SV0C_ROOT/test/integration/shapes.sv0" ""
compile_and_run "pairs" "$SV0C_ROOT/test/integration/pairs.sv0" ""

echo ""
echo "end-to-end tests complete"
