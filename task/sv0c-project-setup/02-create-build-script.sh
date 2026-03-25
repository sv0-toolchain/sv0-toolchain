#!/usr/bin/env bash
set -euo pipefail

SV0C_ROOT="${SV0C_ROOT:-sv0c}"

echo "creating build script..."

# TODO: create Makefile with targets:
#   make build    - compile via CM.make
#   make test     - run test suite
#   make heap     - export heap image
#   make clean    - remove build artifacts
#   make run      - compile and run with a .sv0 file argument

echo "build script creation complete"
