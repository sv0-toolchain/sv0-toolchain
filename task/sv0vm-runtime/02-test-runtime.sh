#!/usr/bin/env bash
set -euo pipefail
SV0VM_ROOT="${SV0VM_ROOT:-sv0vm}"
echo "running runtime tests..."
if [[ -f "$SV0VM_ROOT/test/runtime_test.sml" ]]; then
    cd "$SV0VM_ROOT" && echo 'use "test/runtime_test.sml";' | sml 2>&1
    echo "RUNTIME_STATUS=OK"
else
    echo "TODO: create runtime test suite"
    echo "RUNTIME_STATUS=TODO"
fi
