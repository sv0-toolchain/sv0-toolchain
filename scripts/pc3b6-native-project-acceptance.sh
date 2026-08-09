#!/usr/bin/env bash
# PC-3b.6 acceptance: the sv0-native compiler's `--project` mode (PC-3b.5) compiles
# the two cross-module fixtures via collision-free source-concat, and the emitted C
# builds + runs to exit 42.
#
#   modules_enum_match   — cross-module enum + `match`  (uses PC-2e use-alias fallback)
#   modules_struct_type  — cross-module struct local type + field access
#
# Depends only on link_project_concat_sources_from_dir (lib/link.sv0) + the PC-2e
# apply_use_clause unmangled fallback (lib/resolver.sv0) — NO arena merge. Builds the
# native mega-TU compiler first (one-time SML->C->cc bootstrap), then drives
# `--project` through the wrapper.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
RT="$SV0C/runtime"
WRAP="$ROOT/build/sv0-megatu-compiler-native"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "pc3b6: building the native full-compose compiler (--project aware)..." >&2
bash "$ROOT/scripts/build-sv0-megatu-native.sh" >"$TMP/build.log" 2>&1 || {
  echo "pc3b6: FAIL — native build failed"; tail -20 "$TMP/build.log"; exit 1; }

fail=0
for fx in modules_enum_match modules_struct_type; do
  dir="$SV0C/test/integration/$fx"
  c="$TMP/$fx.c"; bin="$TMP/$fx.bin"
  if ! "$WRAP" --project "$dir" >"$c" 2>"$TMP/$fx.emit.err" || ! grep -q '#include' "$c"; then
    echo "pc3b6: FAIL — $fx: emit failed"; head -5 "$TMP/$fx.emit.err"; fail=1; continue
  fi
  if ! cc -std=c99 -O0 -w -I "$RT" "$c" "$RT/sv0_runtime.c" -o "$bin" 2>"$TMP/$fx.cc.err"; then
    echo "pc3b6: FAIL — $fx: cc failed"; head -5 "$TMP/$fx.cc.err"; fail=1; continue
  fi
  set +e; "$bin"; ec=$?; set -e
  if [ "$ec" -ne 42 ]; then
    echo "pc3b6: FAIL — $fx: ran to exit $ec (expected 42)"; fail=1; continue
  fi
  echo "pc3b6: OK   — $fx: --project emit+cc+run -> exit 42"
done

if [ "$fail" -ne 0 ]; then echo "pc3b6: acceptance FAILED"; exit 1; fi
echo "pc3b6: acceptance PASSED (native --project: both fixtures -> exit 42)"
