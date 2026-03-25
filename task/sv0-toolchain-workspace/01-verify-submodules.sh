#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ok=1
for name in sv0doc sv0c sv0vm sv0-mcp; do
  target="$ROOT/$name"
  if [[ ! -e "$target/.git" ]]; then
    echo "FAIL: submodule path missing or not initialized: $name (expected $target/.git)"
    ok=0
  fi
done
if [[ "$ok" -eq 0 ]]; then
  echo "hint: git submodule update --init --recursive"
  exit 1
fi
echo "OK: submodules sv0doc sv0c sv0vm sv0-mcp present"
