#!/usr/bin/env bash
set -euo pipefail

# sv0c milestone 1: compile .sv0 -> C -> binary -> run (see task/sv0c-milestone-1.Rmd)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SV0C_ROOT="${SV0C_ROOT:-$WORKSPACE_ROOT/sv0c}"

echo "=== sv0c milestone 1: integration test suite ==="
echo "sv0c root: $SV0C_ROOT"

cd "$SV0C_ROOT"
make heap >/dev/null

COMP=(sml "@SMLload=build/sv0c")
COUT="build/itest_tmp.c"
RUN="build/itest_tmp_run"

compile_one() {
  "${COMP[@]}" "$1" >"$COUT"
}

compile_project() {
  "${COMP[@]}" --project "$1" >"$COUT"
}

cc_link() {
  cc -o "$RUN" "$COUT" -Iruntime runtime/sv0_runtime.c
}

PASS=0
FAIL=0
TOTAL=0

run_case() {
  local name="$1" mode="$2" path="$3" want="$4"
  TOTAL=$((TOTAL + 1))
  echo -n "  $name... "
  if [[ ! -e "$path" ]]; then
    echo "SKIP (missing)"
    return
  fi
  set +e
  if [[ "$mode" == "project" ]]; then
    compile_project "$path"
  else
    compile_one "$path"
  fi
  compile_st=$?
  if [[ "$compile_st" -ne 0 ]]; then
    echo "FAIL (compile)"
    FAIL=$((FAIL + 1))
    set -e
    return
  fi
  cc_link
  link_st=$?
  if [[ "$link_st" -ne 0 ]]; then
    echo "FAIL (cc)"
    FAIL=$((FAIL + 1))
    set -e
    return
  fi
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
}

echo ""
echo "integration tests:"
IT="$SV0C_ROOT/test/integration"

run_case "hello world" one "$IT/hello/hello.sv0" 0
run_case "contracts" one "$IT/contracts/contracts.sv0" 0
run_case "pattern matching" one "$IT/patterns/patterns.sv0" 0
run_case "structs (free fn)" one "$IT/structs/structs.sv0" 0
run_case "field assign and +=" one "$IT/field_assign/field_assign.sv0" 0
run_case "generics placeholder (monomorphic id)" one "$IT/generics/generics.sv0" 0
run_case "enum tuple match" one "$IT/enum_tuple_match/enum_tuple_match.sv0" 0
run_case "string API" one "$IT/string_api/string_api.sv0" 0
run_case "enum struct match" one "$IT/enum_struct_match/enum_struct_match.sv0" 0
run_case "vec API" one "$IT/vec_api/vec_api.sv0" 0
run_case "option/result" one "$IT/option_result/option_result.sv0" 0
run_case "box expr" one "$IT/box_expr/box_expr.sv0" 0
run_case "ast types (Phase 1 pattern)" one "$IT/ast_types/ast_types.sv0" 0
run_case "modules (multi-file project)" project "$IT/modules" 42
run_case "modules_types (cross-module struct/enum via fns)" project "$IT/modules_types" 42
run_case "modules_enum_match (cross-module enum in match; PC-2)" project "$IT/modules_enum_match" 42
run_case "modules_struct_type (imported struct local type; PC-1)" project "$IT/modules_struct_type" 42
run_case "modules_struct_sig (cross-module struct in fn signature; PC-3c)" project "$IT/modules_struct_sig" 42
run_case "struct_field_pattern (plain struct field pattern in match; PC-4b)" project "$IT/struct_field_pattern" 42
run_case "uc_loop_sumsq (imperative loop + mutable accumulator)" project "$IT/uc_loop_sumsq" 42
run_case "uc_calculator (enum-dispatched calculator via match)" project "$IT/uc_calculator" 42
run_case "uc_vec2 (struct + free helper functions)" project "$IT/uc_vec2" 42
run_case "uc_vec_stack (Vec<i32> as a stack)" project "$IT/uc_vec_stack" 42
run_case "uc_option_sum (Option-style enum + unwrap_or)" project "$IT/uc_option_sum" 42
run_case "impl_methods (impl method bodies + self fields + method calls; PC-4c)" project "$IT/impl_methods" 42
run_case "mcall_compound_arg (method call with compound argument; BH-1)" project "$IT/mcall_compound_arg" 42

echo ""
echo "results: $PASS passed, $FAIL failed, $TOTAL total"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
