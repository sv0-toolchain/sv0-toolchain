#!/usr/bin/env bash
set -euo pipefail
# Companion to task/sv0-toolchain-roadmap-full.Rmd — assert roadmap milestone files exist.
# Keep this list aligned with § "design milestone → repo task files" in that Rmd, plus
# the M3 checklist inventory and MCP milestone (orientation JSON cites the same paths).
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TASK="$ROOT/task"
need() {
  local f="$1"
  if [[ ! -f "$TASK/$f" ]]; then
    echo "missing roadmap artifact: task/$f" >&2
    exit 1
  fi
}
need sv0-toolchain-roadmap-full.Rmd
need sv0doc-milestone-0.Rmd
need sv0c-milestone-1.Rmd
need sv0vm-milestone-2.Rmd
need sv0-toolchain-milestone-2-prep.Rmd
need sv0-toolchain-milestone-3-self-host.Rmd
need sv0-toolchain-milestone-3-checklist.Rmd
need sv0-toolchain-milestone-4-verification.Rmd
need sv0-toolchain-milestone-5-llvm-crypto.Rmd
need sv0-toolchain-milestone-6-kernel.Rmd
need sv0-toolchain-milestone-cross-cutting.Rmd
need sv0-mcp-milestone-0.Rmd
echo "roadmap milestone task files: OK"
