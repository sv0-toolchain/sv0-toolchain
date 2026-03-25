#!/usr/bin/env bash
set -euo pipefail

SV0C_ROOT="${SV0C_ROOT:-sv0c}"
SRC_DIR="$SV0C_ROOT/src"

echo "creating SML/NJ project scaffolding..."

mkdir -p "$SRC_DIR"/{lexer,ast,parser,name_resolution,type_checker,contract_analyzer,ir,backend/c,error}
mkdir -p "$SV0C_ROOT/test"

echo "scaffolding created"
echo "next: create CM files and stub SML modules"
