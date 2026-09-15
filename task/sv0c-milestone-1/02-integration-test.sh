#!/usr/bin/env bash
set -euo pipefail

# sv0c milestone 1: compile .sv0 -> C -> binary -> run (see task/sv0c-milestone-1.Rmd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SV0C_ROOT="${SV0C_ROOT:-$WORKSPACE_ROOT/sv0c}"

echo "=== sv0c milestone 1: integration test suite ==="
echo "sv0c root: $SV0C_ROOT"

cd "$SV0C_ROOT"
mkdir -p build

RUN="build/itest_tmp_run"

cc_link() {
  cc -o "$RUN" "$1" -Iruntime runtime/sv0_runtime.c
}

PASS=0
FAIL=0
TOTAL=0

echo ""
echo "integration tests:"
IT="$SV0C_ROOT/test/integration"

declare -a C_NAME=() C_MODE=() C_PATH=() C_WANT=()
add_case() {
  local name="$1" mode="$2" path="$3" want="$4"
  TOTAL=$((TOTAL + 1))
  if [[ ! -e "$path" ]]; then
    echo "  $name... SKIP (missing)"
    return
  fi
  C_NAME+=("$name"); C_MODE+=("$mode"); C_PATH+=("$path"); C_WANT+=("$want")
}

add_case "hello world" one "$IT/hello/hello.sv0" 0
add_case "contracts" one "$IT/contracts/contracts.sv0" 0
add_case "pattern matching" one "$IT/patterns/patterns.sv0" 0
add_case "structs (free fn)" one "$IT/structs/structs.sv0" 0
add_case "field assign and +=" one "$IT/field_assign/field_assign.sv0" 0
add_case "generics placeholder (monomorphic id)" one "$IT/generics/generics.sv0" 0
add_case "enum tuple match" one "$IT/enum_tuple_match/enum_tuple_match.sv0" 0
add_case "string API" one "$IT/string_api/string_api.sv0" 0
add_case "enum struct match" one "$IT/enum_struct_match/enum_struct_match.sv0" 0
add_case "vec API" one "$IT/vec_api/vec_api.sv0" 0
add_case "option/result" one "$IT/option_result/option_result.sv0" 0
add_case "box expr" one "$IT/box_expr/box_expr.sv0" 0
add_case "ast types (Phase 1 pattern)" one "$IT/ast_types/ast_types.sv0" 0
add_case "include (single-file expand; BH-9)" one "$IT/include_basic/main.sv0" 42
add_case "int min (2^31 literal wrap; BH-7)" one "$IT/int_min/int_min.sv0" 42
add_case "let shadowing (BH-12)" one "$IT/shadowing/shadowing.sv0" 42
add_case "nested struct literal (BH-11)" one "$IT/nested_struct/nested_struct.sv0" 42
add_case "question operator (BH-11a)" one "$IT/question_op/question_op.sv0" 42
add_case "modules (multi-file project)" project "$IT/modules" 42
add_case "modules_types (cross-module struct/enum via fns)" project "$IT/modules_types" 42
add_case "modules_enum_match (cross-module enum in match; PC-2)" project "$IT/modules_enum_match" 42
add_case "modules_struct_type (imported struct local type; PC-1)" project "$IT/modules_struct_type" 42
add_case "modules_struct_sig (cross-module struct in fn signature; PC-3c)" project "$IT/modules_struct_sig" 42
add_case "struct_field_pattern (plain struct field pattern in match; PC-4b)" project "$IT/struct_field_pattern" 42
add_case "uc_loop_sumsq (imperative loop + mutable accumulator)" project "$IT/uc_loop_sumsq" 42
add_case "uc_calculator (enum-dispatched calculator via match)" project "$IT/uc_calculator" 42
add_case "uc_vec2 (struct + free helper functions)" project "$IT/uc_vec2" 42
add_case "uc_vec_stack (Vec<i32> as a stack)" project "$IT/uc_vec_stack" 42
add_case "uc_option_sum (Option-style enum + unwrap_or)" project "$IT/uc_option_sum" 42
add_case "impl_methods (impl method bodies + self fields + method calls; PC-4c)" project "$IT/impl_methods" 42
add_case "mcall_compound_arg (method call with compound argument; BH-1)" project "$IT/mcall_compound_arg" 42
add_case "enum_return_let (enum-returning fn into typed let; BH-11b)" project "$IT/enum_return_let" 42
add_case "match_guard (match guards + top-level bind patterns; BH-13)" project "$IT/match_guard" 42

if ((${#C_PATH[@]} > 0)); then
  # Batch every case's compile through ONE sml process instead of a fresh
  # `sml "@SMLload=build/sv0c"` cold start per case: each case calls
  # Main.compileFile/compileProjectDir (the same functions the heap's CLI
  # entry point dispatches to) directly, with its emitted C wrapped in a
  # BEGIN/END marker pair so the single combined stdout stream can be split
  # back into one .c file per case afterward. cc + run still happen per case
  # (unavoidable -- cc is a separate program), same as before.
  #
  # Note: this uses `CM.make "sources.cm"` (the plain top-level REPL reading
  # stdin) rather than the prebuilt heap image -- the heap's exported entry
  # point (Main.main) auto-runs on argv and exits immediately without ever
  # reading stdin, so it can't host a multi-case batch script the way a
  # plain `sml` REPL can (same technique run_bootstrap_build uses).
  outdir="$(mktemp -d)"
  batch_script="CM.make \"sources.cm\";
"
  for i in "${!C_PATH[@]}"; do
    path_esc="${C_PATH[$i]//\\/\\\\}"
    path_esc="${path_esc//\"/\\\"}"
    if [[ "${C_MODE[$i]}" == "project" ]]; then
      call="Main.compileProjectDir \"$path_esc\""
    else
      call="Main.compileFile \"$path_esc\""
    fi
    batch_script+="(print \"\\n===SV0BEGIN ${i}===\\n\"; ($call) handle _ => (); print \"\\n===SV0END ${i}===\\n\");
"
  done
  batch_script+="OS.Process.exit OS.Process.success;
"
  blog="$(mktemp)"
  printf '%s\n' "$batch_script" | sml >"$blog" 2>&1 || true

  awk -v outdir="$outdir" '
    /^===SV0BEGIN [0-9]+===$/ { tag=$2; sub(/===$/,"",tag); file=outdir "/" tag ".c"; capturing=1; next }
    /^===SV0END [0-9]+===$/ { if (capturing) close(file); capturing=0; next }
    capturing { print > file }
  ' "$blog"
  rm -f "$blog"

  for i in "${!C_PATH[@]}"; do
    name="${C_NAME[$i]}"
    want="${C_WANT[$i]}"
    cfile="$outdir/${i}.c"
    echo -n "  $name... "
    if [[ ! -s "$cfile" ]]; then
      echo "FAIL (compile)"
      FAIL=$((FAIL + 1))
      continue
    fi
    set +e
    cc_link "$cfile"
    link_st=$?
    set -e
    if [[ "$link_st" -ne 0 ]]; then
      echo "FAIL (cc)"
      FAIL=$((FAIL + 1))
      continue
    fi
    set +e
    "$RUN"
    st=$?
    set -e
    if [[ "$st" -eq "$want" ]]; then
      echo "PASS"
      PASS=$((PASS + 1))
    else
      echo "FAIL (exit $st, expected $want)"
      FAIL=$((FAIL + 1))
    fi
  done
  rm -rf "$outdir"
fi

echo ""
echo "results: $PASS passed, $FAIL failed, $TOTAL total"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
