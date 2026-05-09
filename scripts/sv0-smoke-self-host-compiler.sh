#!/usr/bin/env bash
# M3-S-052: delegate to sv0c-local smoke (single implementation for standalone CI + meta-repo).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$ROOT/sv0c/scripts/smoke-self-host-compiler.sh"
