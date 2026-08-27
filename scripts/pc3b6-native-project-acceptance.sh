#!/usr/bin/env bash
# PC-3b.6 acceptance: the sv0-native compiler's `--project` mode (PC-3b.5) compiles
# the two cross-module fixtures via collision-free source-concat, and the emitted C
# builds + runs to exit 42.
#
#   modules_enum_match   — cross-module enum + `match`  (uses PC-2e use-alias fallback)
#   modules_struct_type  — cross-module struct local type + field access
#   modules_struct_sig   — cross-module struct in a fn SIGNATURE (param + return; PC-3c)
#   struct_field_pattern — plain struct field pattern in a `match` (PC-4b)
#   uc_*                 — realistic use-case programs (loops, enum dispatch, structs +
#                          free fns, Vec-as-stack, Option-style enums) — parity smoke
# All are single-module `--project` dirs that emit C, cc, and run to exit 42.
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
for fx in modules_enum_match modules_struct_type modules_struct_sig struct_field_pattern \
          uc_loop_sumsq uc_calculator uc_vec2 uc_vec_stack uc_option_sum \
          impl_methods mcall_compound_arg enum_return_let match_guard int_min shadowing nested_struct question_op; do
  dir="$SV0C/test/integration/$fx"
  c="$TMP/$fx.c"; bin="$TMP/$fx.bin"
  if ! "$WRAP" --project "$dir" >"$c" 2>"$TMP/$fx.emit.err" || ! grep -q '#include' "$c"; then
    echo "pc3b6: FAIL — $fx: emit failed"; head -5 "$TMP/$fx.emit.err"; fail=1; continue
  fi
  if ! python3 "$ROOT/scripts/native_exe_canonical_compile.py" "$c" "$bin" 2>"$TMP/$fx.cc.err"; then
    echo "pc3b6: FAIL — $fx: cc failed"; head -5 "$TMP/$fx.cc.err"; fail=1; continue
  fi
  set +e; "$bin"; ec=$?; set -e
  if [ "$ec" -ne 42 ]; then
    echo "pc3b6: FAIL — $fx: ran to exit $ec (expected 42)"; fail=1; continue
  fi
  echo "pc3b6: OK   — $fx: --project emit+cc+run -> exit 42"
done

# ── native SINGLE-FILE include (BH-9) ────────────────────────────────────────
#   `include "relpath";` is a single-file feature: the native compose main reads
#   the source via expand_from_file (read + include-expand), mirroring SML's
#   expandFile. NOT --project (source-concat would double-define the includee).
inc="$SV0C/test/integration/include_basic/main.sv0"
c="$TMP/include_basic.c"; bin="$TMP/include_basic.bin"
if ! "$WRAP" "$inc" >"$c" 2>"$TMP/include_basic.emit.err" || ! grep -q '#include' "$c"; then
  echo "pc3b6: FAIL — include_basic: single-file emit failed"; head -5 "$TMP/include_basic.emit.err"; fail=1
elif ! python3 "$ROOT/scripts/native_exe_canonical_compile.py" "$c" "$bin" 2>"$TMP/include_basic.cc.err"; then
  echo "pc3b6: FAIL — include_basic: cc failed"; head -5 "$TMP/include_basic.cc.err"; fail=1
else
  set +e; "$bin"; ec=$?; set -e
  if [ "$ec" -ne 42 ]; then
    echo "pc3b6: FAIL — include_basic: ran to exit $ec (expected 42)"; fail=1
  else
    echo "pc3b6: OK   — include_basic: single-file include emit+cc+run -> exit 42"
  fi
fi

# ── native runtime CONTRACT enforcement (BH-10a/BH-10b) ──────────────────────
#   The native compose main now routes requires/ensures through lowering, so a
#   violated `requires` aborts via sv0_requires -> exit 1 + a stderr message
#   (matching SML->C), instead of silently returning a value. Single-file.
cv="$SV0C/test/integration/contract_violation/contract_violation.sv0"
c="$TMP/contract_violation.c"; bin="$TMP/contract_violation.bin"
if ! "$WRAP" "$cv" >"$c" 2>"$TMP/cv.emit.err" || ! grep -q 'sv0_requires' "$c"; then
  echo "pc3b6: FAIL — contract_violation: emit missing sv0_requires"; head -5 "$TMP/cv.emit.err"; fail=1
elif ! python3 "$ROOT/scripts/native_exe_canonical_compile.py" "$c" "$bin" 2>"$TMP/cv.cc.err"; then
  echo "pc3b6: FAIL — contract_violation: cc failed"; head -5 "$TMP/cv.cc.err"; fail=1
else
  set +e; "$bin" 2>"$TMP/cv.run.err"; ec=$?; set -e
  if [ "$ec" -ne 1 ] || ! grep -q 'contract violation' "$TMP/cv.run.err"; then
    echo "pc3b6: FAIL — contract_violation: exit $ec / missing message (expected exit 1 + 'contract violation')"; fail=1
  else
    echo "pc3b6: OK   — contract_violation: native requires abort -> exit 1 + message"
  fi
fi

if [ "$fail" -ne 0 ]; then echo "pc3b6: acceptance FAILED"; exit 1; fi
echo "pc3b6: acceptance PASSED (native --project + single-file include + contract enforcement: all fixtures)"
