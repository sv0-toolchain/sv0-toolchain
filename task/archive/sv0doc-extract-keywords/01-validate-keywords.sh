#!/usr/bin/env bash
set -euo pipefail

KEYWORDS_FILE="${KEYWORDS_FILE:-sv0doc/keywords/reference.md}"

if [[ ! -f "$KEYWORDS_FILE" ]]; then
    echo "FAIL: keywords file not found: $KEYWORDS_FILE"
    exit 1
fi

echo "OK: keywords file exists ($(wc -l < "$KEYWORDS_FILE") lines)"
