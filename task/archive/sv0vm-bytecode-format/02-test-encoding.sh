#!/usr/bin/env bash
set -euo pipefail
SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
echo "running bytecode encoding tests..."
if [[ -f "$SV0VM_ROOT/test/bytecode_test.sml" ]]; then
    cd "$SV0VM_ROOT" && echo 'use "test/bytecode_test.sml";' | sml 2>&1
    echo "BYTECODE_STATUS=OK"
else
    echo "TODO: create bytecode test suite"
    echo "BYTECODE_STATUS=TODO"
fi
