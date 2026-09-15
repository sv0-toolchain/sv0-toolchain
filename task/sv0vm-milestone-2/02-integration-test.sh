#!/usr/bin/env bash
set -euo pipefail

echo "=== sv0vm milestone 2: integration test suite ==="

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SV0C_ROOT="${SV0C_ROOT:-$ROOT/sv0c}"
SV0VM_ROOT="${SV0VM_ROOT:-$ROOT/sv0vm}"
TEST_DIR="${TEST_DIR:-$SV0C_ROOT/test}"

mkdir -p "$SV0C_ROOT/build/vm"

compile_vm() {
  local rel="$1"
  local log
  log="$(mktemp)"
  if ! ( cd "$SV0C_ROOT" && echo "CM.make \"sources.cm\"; Main.main ((), [\"--target=vm\", \"$rel\"]);" | sml >"$log" 2>&1 ); then
    echo "FAIL: sml invocation for $rel"
    tail -40 "$log"
    rm -f "$log"
    return 1
  fi
  if grep -q 'Error:' "$log"; then
    echo "FAIL: compile errors for $rel"
    tail -40 "$log"
    rm -f "$log"
    return 1
  fi
  rm -f "$log"
  return 0
}

compile_vm_project() {
  local dir="$1"
  local log
  log="$(mktemp)"
  if ! ( cd "$SV0C_ROOT" && echo "CM.make \"sources.cm\"; Main.main ((), [\"--target=vm\", \"--project\", \"$dir\"]);" | sml >"$log" 2>&1 ); then
    echo "FAIL: sml project compile for $dir"
    tail -40 "$log"
    rm -f "$log"
    return 1
  fi
  if grep -q 'Error:' "$log"; then
    echo "FAIL: compile errors for project $dir"
    tail -40 "$log"
    rm -f "$log"
    return 1
  fi
  rm -f "$log"
  return 0
}

capture_vm() {
  local sv0b="$1"
  cd "$SV0VM_ROOT" && SV0B="$sv0b" sml < scripts/run_sv0b.sml 2>&1
}

failures=0
PASS_N=0
TOTAL=0

echo ""
echo "integration tests (sv0c --target=vm + sv0vm run_sv0b):"

# --- Batched single-file exit cases -----------------------------------
# All independent, single-file, exit-code-only checks: compiled through ONE
# sml process (Main.compileFileVm via List.app) and run through ONE sml
# process (Interpreter.runFile via List.app), instead of a fresh `sml` cold
# start per file per phase -- same batching run_bootstrap_build uses.
IT="$SV0C_ROOT/test/integration"
declare -a B_STEM=() B_REL=() B_WANT=()
add_batch_case() {
  local stem="$1" rel="$2" want="$3"
  TOTAL=$((TOTAL + 1))
  if [[ ! -e "$SV0C_ROOT/$rel" ]]; then
    echo "  $stem... SKIP (missing)"
    return
  fi
  B_STEM+=("$stem"); B_REL+=("$rel"); B_WANT+=("$want")
}

add_batch_case "hello" "test/integration/hello/hello.sv0" 0
add_batch_case "contracts" "test/integration/contracts/contracts.sv0" 0
# BH-10c: a runtime `requires` violation aborts cleanly on the VM (vm_exit:1).
add_batch_case "contract_violation" "test/integration/contract_violation/contract_violation.sv0" 1
add_batch_case "shadowing" "test/integration/shadowing/shadowing.sv0" 42
add_batch_case "question_op" "test/integration/question_op/question_op.sv0" 42
add_batch_case "no_alias_requires" "test/data/golden/pass/no_alias_requires.sv0" 0
add_batch_case "patterns" "test/integration/patterns/patterns.sv0" 0
add_batch_case "structs" "test/integration/structs/structs.sv0" 0
add_batch_case "field_assign" "test/integration/field_assign/field_assign.sv0" 0
add_batch_case "generics" "test/integration/generics/generics.sv0" 0
add_batch_case "call_arg_order" "test/integration/call_arg_order/call_arg_order.sv0" 0
add_batch_case "enum_tuple_match" "test/integration/enum_tuple_match/enum_tuple_match.sv0" 0
add_batch_case "string_api" "test/integration/string_api/string_api.sv0" 0
add_batch_case "enum_struct_match" "test/integration/enum_struct_match/enum_struct_match.sv0" 0
add_batch_case "vec_api" "test/integration/vec_api/vec_api.sv0" 0
add_batch_case "option_result" "test/integration/option_result/option_result.sv0" 0
add_batch_case "box_expr" "test/integration/box_expr/box_expr.sv0" 0
add_batch_case "ast_types" "test/integration/ast_types/ast_types.sv0" 0
add_batch_case "g4_resolver_checker" "test/integration/g4_resolver_checker/g4_resolver_checker.sv0" 0
# int_min: 2^31 literal wraps to INT_MIN on the VM (BH-7). stem must match the .sv0 basename.
add_batch_case "int_min" "test/integration/int_min/int_min.sv0" 42
if [[ -f "$TEST_DIR/integration/gcd/gcd.sv0" ]]; then
  add_batch_case "gcd" "test/integration/gcd/gcd.sv0" 0
else
  echo "  SKIP: gcd (no test/integration/gcd/gcd.sv0)"
fi

if ((${#B_REL[@]} > 0)); then
  tab=$'\t'
  paths_sml=""
  for rel in "${B_REL[@]}"; do
    rel_esc="${rel//\\/\\\\}"
    rel_esc="${rel_esc//\"/\\\"}"
    paths_sml+="${paths_sml:+, }\"$rel_esc\""
  done
  compile_script=$(cat <<SML
CM.make "sources.cm";
fun doCompile p = (Main.compileFileVm p; print ("BRES\t" ^ p ^ "\tOK\n"))
  handle _ => print ("BRES\t" ^ p ^ "\tERR\n");
val () = List.app doCompile [${paths_sml}];
OS.Process.exit OS.Process.success;
SML
)
  clog="$(mktemp)"
  compile_ok=1
  if ! (cd "$SV0C_ROOT" && printf '%s\n' "$compile_script" | sml >"$clog" 2>&1); then
    compile_ok=0
  fi

  cases_sml=""
  for i in "${!B_STEM[@]}"; do
    cases_sml+="${cases_sml:+, }(\"${B_STEM[$i]}\",\"$SV0C_ROOT/build/vm/${B_STEM[$i]}.sv0b\")"
  done
  run_script=$(cat <<SML
use "src/main.sml";
fun runOne (stem, path) =
  (let val e = Interpreter.runFile path
   in print ("VMRES\t" ^ stem ^ "\t" ^ Int.toString e ^ "\n") end)
  handle _ => print ("VMRES\t" ^ stem ^ "\tERR\n");
val () = List.app runOne [${cases_sml}];
OS.Process.exit OS.Process.success;
SML
)
  rlog="$(mktemp)"
  (cd "$SV0VM_ROOT" && printf '%s\n' "$run_script" | sml >"$rlog" 2>&1) || true

  for i in "${!B_STEM[@]}"; do
    stem="${B_STEM[$i]}"
    rel="${B_REL[$i]}"
    want="${B_WANT[$i]}"
    echo -n "  $stem... "
    if ((compile_ok == 0)) || ! grep -qF "BRES${tab}${rel}${tab}OK" "$clog"; then
      echo "FAIL (compile)"
      failures=$((failures + 1))
      continue
    fi
    line="$(grep -F "VMRES${tab}${stem}${tab}" "$rlog" | tail -1)"
    status="${line##*"${tab}"}"
    if [[ "$status" == "$want" ]]; then
      echo "PASS (exit $want)"
      PASS_N=$((PASS_N + 1))
    else
      echo "FAIL (expected vm_exit:${want}, got ${status:-none})"
      failures=$((failures + 1))
    fi
  done

  if ((compile_ok == 0)); then
    echo "compile log (tail):"
    tail -60 "$clog"
  fi
  rm -f "$clog" "$rlog"
fi

# --- Special-cased: project-mode (shared build/vm/main.sv0b output, so they
# can't share a compile batch) and println_ok (needs the run's own stdout,
# not just its exit code) -- few enough cases that a dedicated sml call each
# isn't worth batching. -------------------------------------------------

echo -n "  modules (project)... "
TOTAL=$((TOTAL + 1))
if compile_vm_project "test/integration/modules" && [[ -f "$SV0C_ROOT/build/vm/main.sv0b" ]]; then
  out="$(capture_vm "$SV0C_ROOT/build/vm/main.sv0b")" || true
  if echo "$out" | grep -q "vm_exit:42"; then
    echo "PASS (exit 42)"
    PASS_N=$((PASS_N + 1))
  else
    echo "FAIL (expected vm_exit:42)"
    echo "$out" | tail -20
    failures=$((failures + 1))
  fi
else
  echo "FAIL (compile or missing main.sv0b)"
  failures=$((failures + 1))
fi

echo -n "  import_use_match (project)... "
TOTAL=$((TOTAL + 1))
if compile_vm_project "test/integration/import_use_match" && [[ -f "$SV0C_ROOT/build/vm/main.sv0b" ]]; then
  out="$(capture_vm "$SV0C_ROOT/build/vm/main.sv0b")" || true
  if echo "$out" | grep -q "vm_exit:0"; then
    echo "PASS (exit 0)"
    PASS_N=$((PASS_N + 1))
  else
    echo "FAIL (expected vm_exit:0)"
    echo "$out" | tail -20
    failures=$((failures + 1))
  fi
else
  echo "FAIL (compile or missing main.sv0b)"
  failures=$((failures + 1))
fi

echo -n "  println_ok... "
TOTAL=$((TOTAL + 1))
if compile_vm "test/data/golden/pass/println_ok.sv0" && [[ -f "$SV0C_ROOT/build/vm/println_ok.sv0b" ]]; then
  out="$(capture_vm "$SV0C_ROOT/build/vm/println_ok.sv0b")" || true
  if echo "$out" | grep -qFx "golden" && echo "$out" | grep -q "vm_exit:0"; then
    echo "PASS (println + exit 0)"
    PASS_N=$((PASS_N + 1))
  else
    echo "FAIL (expected line golden and vm_exit:0)"
    echo "$out" | tail -20
    failures=$((failures + 1))
  fi
else
  echo "FAIL (compile or missing println_ok.sv0b)"
  failures=$((failures + 1))
fi

echo ""
if [[ "$failures" -eq 0 ]]; then
  echo "integration tests complete: all passed"
else
  echo "integration tests complete: $failures failed"
  exit 1
fi
