#!/usr/bin/env bash
set -euo pipefail
SV0C_ROOT="${SV0C_ROOT:-sv0c}"
echo "running VM codegen tests..."
if [[ -f "$SV0C_ROOT/test/vm_codegen_test.sml" ]]; then
    cd "$SV0C_ROOT" && echo 'use "test/vm_codegen_test.sml";' | sml 2>&1
    echo "VMBACKEND_STATUS=OK"
else
    echo "TODO: create VM codegen test suite"
    echo "VMBACKEND_STATUS=TODO"
fi
