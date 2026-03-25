#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MCP="$ROOT/sv0-mcp"

if [[ ! -f "$MCP/pyproject.toml" ]]; then
  echo "FAIL: sv0-mcp/pyproject.toml not found"
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  (cd "$MCP" && uv sync --all-extras)
  (cd "$MCP" && uv run pytest tests/ -q)
  echo "OK: sv0-mcp uv sync + pytest"
else
  echo "SKIP: uv not in PATH — run: cd sv0-mcp && uv sync && uv run pytest tests/"
  exit 0
fi
