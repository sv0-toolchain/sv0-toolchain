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

run_exit_case() {
  local stem="$1"
  local rel="$2"
  local want="$3"
  local sv0b="$SV0C_ROOT/build/vm/${stem}.sv0b"
  echo -n "  $stem... "
  if ! compile_vm "$rel"; then
    failures=$((failures + 1))
    echo "FAIL (compile)"
    return
  fi
  if [[ ! -f "$sv0b" ]]; then
    echo "FAIL (missing $sv0b)"
    failures=$((failures + 1))
    return
  fi
  local out
  out="$(capture_vm "$sv0b")" || true
  if echo "$out" | grep -q "vm_exit:${want}"; then
    echo "PASS (exit $want)"
  else
    echo "FAIL (expected vm_exit:${want})"
    echo "$out" | tail -20
    failures=$((failures + 1))
  fi
}

echo "integration tests (sv0c --target=vm + sv0vm run_sv0b):"

run_exit_case "hello" "test/integration/hello/hello.sv0" 0
run_exit_case "contracts" "test/integration/contracts/contracts.sv0" 0
run_exit_case "patterns" "test/integration/patterns/patterns.sv0" 0
run_exit_case "structs" "test/integration/structs/structs.sv0" 0
run_exit_case "generics" "test/integration/generics/generics.sv0" 0
run_exit_case "call_arg_order" "test/integration/call_arg_order/call_arg_order.sv0" 0

echo -n "  modules (project)... "
if compile_vm_project "test/integration/modules" && [[ -f "$SV0C_ROOT/build/vm/main.sv0b" ]]; then
  out="$(capture_vm "$SV0C_ROOT/build/vm/main.sv0b")" || true
  if echo "$out" | grep -q "vm_exit:42"; then
    echo "PASS (exit 42)"
  else
    echo "FAIL (expected vm_exit:42)"
    echo "$out" | tail -20
    failures=$((failures + 1))
  fi
else
  echo "FAIL (compile or missing main.sv0b)"
  failures=$((failures + 1))
fi

echo -n "  println_ok... "
if compile_vm "test/data/golden/pass/println_ok.sv0" && [[ -f "$SV0C_ROOT/build/vm/println_ok.sv0b" ]]; then
  out="$(capture_vm "$SV0C_ROOT/build/vm/println_ok.sv0b")" || true
  if echo "$out" | grep -qFx "golden" && echo "$out" | grep -q "vm_exit:0"; then
    echo "PASS (println + exit 0)"
  else
    echo "FAIL (expected line golden and vm_exit:0)"
    echo "$out" | tail -20
    failures=$((failures + 1))
  fi
else
  echo "FAIL (compile or missing println_ok.sv0b)"
  failures=$((failures + 1))
fi

if [[ -f "$TEST_DIR/integration/gcd/gcd.sv0" ]]; then
  run_exit_case "gcd" "test/integration/gcd/gcd.sv0" 0
else
  echo "  SKIP: gcd (no test/integration/gcd/gcd.sv0)"
fi

echo ""
if [[ "$failures" -eq 0 ]]; then
  echo "integration tests complete: all passed"
else
  echo "integration tests complete: $failures failed"
  exit 1
fi
