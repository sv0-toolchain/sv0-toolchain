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
run_case "generics placeholder (monomorphic id)" one "$IT/generics/generics.sv0" 0
run_case "modules (multi-file project)" project "$IT/modules" 42

echo ""
echo "results: $PASS passed, $FAIL failed, $TOTAL total"

if [[ "$FAIL" -gt 0 ]]; then
  exit 1
fi
