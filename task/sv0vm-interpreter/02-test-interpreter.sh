#!/usr/bin/env bash
set -euo pipefail
SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
echo "running interpreter tests..."
if [[ -f "$SV0VM_ROOT/test/interpreter_test.sml" ]]; then
    cd "$SV0VM_ROOT" && echo 'use "test/interpreter_test.sml";' | sml 2>&1
    echo "INTERPRETER_STATUS=OK"
else
    echo "TODO: create interpreter test suite"
    echo "INTERPRETER_STATUS=TODO"
fi
