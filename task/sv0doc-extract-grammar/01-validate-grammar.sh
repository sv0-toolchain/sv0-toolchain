#!/usr/bin/env bash
set -euo pipefail

GRAMMAR_FILE="${GRAMMAR_FILE:-sv0doc/grammar/sv0.ebnf}"

if [[ ! -f "$GRAMMAR_FILE" ]]; then
    echo "FAIL: grammar file not found: $GRAMMAR_FILE"
    exit 1
fi

line_count=$(wc -l < "$GRAMMAR_FILE")
if [[ "$line_count" -lt 50 ]]; then
    echo "WARN: grammar file seems too short ($line_count lines)"
    exit 1
fi

echo "OK: grammar file exists ($line_count lines)"

for keyword in "module" "fn" "struct" "enum" "trait" "impl" "let" "match" "if" "while" "for" "requires" "ensures" "newtype" "type" "use" "pub"; do
    if ! grep -q "$keyword" "$GRAMMAR_FILE"; then
        echo "WARN: keyword '$keyword' not found in grammar"
    fi
done

echo "grammar validation complete"
