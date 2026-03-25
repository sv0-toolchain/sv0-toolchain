#!/usr/bin/env bash
set -euo pipefail
# Delegate to roadmap companion (task/sv0-toolchain-roadmap-full.Rmd).
exec "$(cd "$(dirname "$0")" && pwd)/../sv0-toolchain-roadmap-full/01-verify-roadmap-artifacts.sh"
