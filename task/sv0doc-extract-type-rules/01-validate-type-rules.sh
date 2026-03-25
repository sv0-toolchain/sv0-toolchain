#!/usr/bin/env bash
set -euo pipefail

TYPE_RULES_FILE="${TYPE_RULES_FILE:-sv0doc/type-system/rules.md}"

if [[ ! -f "$TYPE_RULES_FILE" ]]; then
    echo "FAIL: type rules file not found: $TYPE_RULES_FILE"
    exit 1
fi

echo "OK: type rules file exists ($(wc -l < "$TYPE_RULES_FILE") lines)"
