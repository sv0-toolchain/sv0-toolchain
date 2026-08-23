#!/usr/bin/env bash
set -euo pipefail

MEMORY_FILE="${MEMORY_FILE:-sv0doc/memory-model/ownership.md}"

if [[ ! -f "$MEMORY_FILE" ]]; then
    echo "FAIL: memory model file not found: $MEMORY_FILE"
    exit 1
fi

echo "OK: memory model file exists ($(wc -l < "$MEMORY_FILE") lines)"
