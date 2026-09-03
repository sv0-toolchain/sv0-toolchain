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

# ── SS-U09: --project entry-point discovery guard ───────────────────────────
#   sv0-strings docs/BUGS.md #4 / SPEC UP-026, AC-036: `--project` used to
#   silently accept two top-level `fn main`, running whichever path sorts last.
#   link.sv0 now counts entry files directly in the project dir and fails
#   closed with a stable E0302 on stderr. A `fn main` in a SUBDIRECTORY
#   (test-runner convention, e.g. sv0-mathlib/test/) is not an entry candidate.
dm="$TMP/ssu09_dup"; mkdir -p "$dm/test"
printf 'fn main() -> i32 { return 7; }\n' > "$dm/main.sv0"
printf 'fn main() -> i32 { return 9; }\n' > "$dm/main_two.sv0"
printf 'fn main() -> i32 { return 0; }\n' > "$dm/test/unit.sv0"
set +e; "$WRAP" --project "$dm" >"$TMP/ssu09_dup.c" 2>"$TMP/ssu09_dup.err"; ec=$?; set -e
if [ "$ec" -eq 0 ] || ! grep -q 'E0302' "$TMP/ssu09_dup.err"; then
  echo "pc3b6: FAIL — SS-U09 dup-entry: exit $ec / stderr missing E0302"; cat "$TMP/ssu09_dup.err"; fail=1
else
  echo "pc3b6: OK   — SS-U09 dup-entry: two top-level fn main -> nonzero + E0302"
fi

ok="$TMP/ssu09_ok"; mkdir -p "$ok/test"
printf 'fn add1(x: i32) -> i32 { return x + 1; }\n' > "$ok/lib.sv0"
printf 'fn main() -> i32 { return add1(41); }\n' > "$ok/main.sv0"
printf 'fn main() -> i32 { return 0; }\n' > "$ok/test/unit.sv0"
set +e; "$WRAP" --project "$ok" >"$TMP/ssu09_ok.c" 2>"$TMP/ssu09_ok.err"; ec=$?; set -e
if [ "$ec" -ne 0 ] || ! grep -q '#include' "$TMP/ssu09_ok.c" || grep -q 'E0302' "$TMP/ssu09_ok.err"; then
  echo "pc3b6: FAIL — SS-U09 subdir-main: one root entry + subdir fn main should emit (exit $ec)"; cat "$TMP/ssu09_ok.err"; fail=1
else
  echo "pc3b6: OK   — SS-U09 subdir-main: root entry + subdir fn main -> emits, no E0302"
fi

# ── SS-U05: advanced contract clauses are reported model-only, never dropped ──
#   sv0-strings SPEC UP-017 / AC-026: native + VM lowering does not turn an
#   `old` / `forall` / `exists` clause into a runtime check. It must not
#   silently drop it either — it emits a stable machine-readable stderr note
#   (`sv0c: note: contract clause ... is model-only`). Here the `ensures` is
#   false at runtime (f returns x+100, not old(x)); a silent drop would let
#   `f(0) + 42 == 142` through with NO signal. The note is the signal.
mo="$TMP/ssu05_modelonly.sv0"
printf 'fn f(x: i32) -> i32\n    ensures(result == old(x))\n{\n    return x + 100;\n}\nfn main() -> i32 { return f(0) + 42; }\n' > "$mo"
set +e; "$WRAP" "$mo" >"$TMP/ssu05.c" 2>"$TMP/ssu05.err"; ec=$?; set -e
if [ "$ec" -ne 0 ] || ! grep -q 'is model-only' "$TMP/ssu05.err" || grep -q 'sv0_ensures' "$TMP/ssu05.c"; then
  echo "pc3b6: FAIL — SS-U05 model-only: exit $ec / missing note / clause wrongly lowered"; cat "$TMP/ssu05.err"; fail=1
else
  bin="$TMP/ssu05.bin"
  if python3 "$ROOT/scripts/native_exe_canonical_compile.py" "$TMP/ssu05.c" "$bin" 2>/dev/null; then
    set +e; "$bin"; rc=$?; set -e
    if [ "$rc" -ne 142 ]; then
      echo "pc3b6: FAIL — SS-U05 model-only: ran to exit $rc (expected 142 — clause not enforced)"; fail=1
    else
      echo "pc3b6: OK   — SS-U05 model-only: old() ensures -> stderr note + not enforced (exit 142)"
    fi
  else
    echo "pc3b6: FAIL — SS-U05 model-only: cc failed"; fail=1
  fi
fi

# a simple (non-advanced) contract stays silent and IS lowered
sc="$TMP/ssu05_simple.sv0"
printf 'fn g(x: i32) -> i32\n    requires(x > 0)\n    ensures(result > 0)\n{\n    return x * 2;\n}\nfn main() -> i32 { return g(21); }\n' > "$sc"
set +e; "$WRAP" "$sc" >"$TMP/ssu05s.c" 2>"$TMP/ssu05s.err"; ec=$?; set -e
if [ "$ec" -ne 0 ] || grep -q 'model-only' "$TMP/ssu05s.err" || ! grep -q 'sv0_ensures' "$TMP/ssu05s.c"; then
  echo "pc3b6: FAIL — SS-U05 simple: spurious note or clause not lowered"; cat "$TMP/ssu05s.err"; fail=1
else
  echo "pc3b6: OK   — SS-U05 simple: plain requires/ensures -> no note, lowered"
fi

if [ "$fail" -ne 0 ]; then echo "pc3b6: acceptance FAILED"; exit 1; fi
echo "pc3b6: acceptance PASSED (native --project + single-file include + contract enforcement + SS-U09 entry guard + SS-U05 model-only note: all fixtures)"
