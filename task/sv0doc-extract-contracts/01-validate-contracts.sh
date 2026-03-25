#!/usr/bin/env bash
set -euo pipefail

CONTRACTS_FILE="${CONTRACTS_FILE:-sv0doc/contracts/semantics.md}"

if [[ ! -f "$CONTRACTS_FILE" ]]; then
    echo "FAIL: contracts file not found: $CONTRACTS_FILE"
    exit 1
fi

echo "OK: contracts file exists ($(wc -l < "$CONTRACTS_FILE") lines)"
