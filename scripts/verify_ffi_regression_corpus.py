#!/usr/bin/env python3
"""FFI-015: cross-cutting differential/regression corpus.

Epics A-E (FFI-002..014) added four new diagnostics -- E0550 (deref outside
`unsafe`), E0551 (unsafe ABI type in an `#[extern_c]` signature), E0552
(conflicting `#[extern_c]` re-declaration), E0553 (raw-pointer/unsafe/
extern_c program rejected on the VM backend) -- and this script is the
guard that none of them are false positives: they must never fire on a
program that uses no raw pointers, `unsafe` blocks, or `#[extern_c]`
declarations. "Never fire on innocent code" is exactly as load-bearing as
"do fire on real violations" (already covered per-diagnostic by
test/diagnostics/manifest.txt's own E0550/E0551/E0552 rows and
scripts/verify_vm_ffi_gate.py's E0553 rows) -- a diagnostic that ALSO
fires on safe code is just as broken as one that never fires at all.

Two checks, reusing the existing corpora rather than new fixtures:

  1. C-backend guard: every fixture in test/behavior/manifest.txt whose
     path does not contain "ffi_" (the naming convention every FFI-series
     fixture already follows) is safe by construction. Compile each with
     the native C-backend wrapper and assert none of the four E05xx codes
     appear in its output.

  2. VM-backend guard: every fixture in test/vm-parity/behavioral-manifest.txt
     is already a pre-vetted, VM-compatible, FFI-free corpus (VMF-018).
     Run each through the native VM emitter and assert it is not rejected
     by the FFI gate (exit != 7, no E0553 in stderr).

  3. C-output golden: the task doc's own remaining completion criterion --
     "a safe sv0 program... is byte-identical in its C output before and
     after this feature lands" -- for a representative set of safe
     fixtures (one per major language feature: arith, bool, struct, enum,
     Vec, string, contract, method, for-loop, algorithm), re-emit C and
     byte-diff against test/behavior/golden-c/<name>.c, captured once at
     FFI-015 landing time as the pinned baseline. Guards every FUTURE
     change to the FFI machinery, not just this slice's own landing.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SV0C = ROOT / "sv0c"
C_WRAPPER = ROOT / "build" / "sv0-megatu-compiler-native"
VM_EMIT = ROOT / "build" / "sv0-megatu-vm-native"
BEHAVIOR_MANIFEST = SV0C / "test" / "behavior" / "manifest.txt"
VM_BEHAVIORAL_MANIFEST = SV0C / "test" / "vm-parity" / "behavioral-manifest.txt"
GOLDEN_C_DIR = SV0C / "test" / "behavior" / "golden-c"

FFI_CODES = ("E0550", "E0551", "E0552", "E0553")

# One representative fixture per major language feature -- not the whole
# corpus (that's checks 1/2's job); this is a pinned byte-diff baseline.
GOLDEN_C_FIXTURES = (
    "arith_precedence",
    "bool_and",
    "struct_field",
    "enum_match_payload",
    "vec_ops",
    "string_concat_len",
    "contract_ok",
    "method_calls_method",
    "for_product",
    "algo_gcd_iter",
)


def ensure_built(path: Path, script: str) -> bool:
    if path.is_file():
        return True
    r = subprocess.run(["bash", str(ROOT / "scripts" / script)], capture_output=True, text=True, check=False)
    if not path.is_file():
        print(f"verify_ffi_regression_corpus: failed to build {path}", file=sys.stderr)
        print((r.stderr or "")[-2000:], file=sys.stderr)
        return False
    return True


def check_c_backend() -> int:
    if not ensure_built(C_WRAPPER, "build-sv0-megatu-native.sh"):
        return 1
    n = 0
    for raw in BEHAVIOR_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rel = line.split("|", 1)[0].strip()
        if "ffi_" in rel:
            continue
        case = SV0C / rel
        proc = subprocess.run([str(C_WRAPPER), str(case)], capture_output=True, text=True, timeout=60, check=False)
        combined = (proc.stdout or "") + (proc.stderr or "")
        hit = [c for c in FFI_CODES if c in combined]
        if hit:
            print(
                f"verify_ffi_regression_corpus: C backend: {rel} (safe, no FFI features) "
                f"triggered {hit} -- false positive",
                file=sys.stderr,
            )
            print(combined[-1500:], file=sys.stderr)
            return -1
        n += 1
    print(f"verify_ffi_regression_corpus: C backend OK ({n} safe fixture(s), no E05xx leakage)", file=sys.stderr)
    return n


def check_vm_backend() -> int:
    if not ensure_built(VM_EMIT, "build-sv0-megatu-vm-native.sh"):
        return 1
    n = 0
    for raw in VM_BEHAVIORAL_MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("--project"):
            rel = line.split(None, 1)[1].strip()
            request = f"--project {(ROOT / rel).resolve()}"
        else:
            rel = line
            case = ROOT / rel
            if not case.is_file():
                continue
            request = str(case)
        proc = subprocess.run(
            [str(VM_EMIT)],
            capture_output=True,
            timeout=120,
            env={**os.environ, "SV0_DRV_REQUEST": request},
            check=False,
        )
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode == 7 or "E0553" in stderr:
            print(
                f"verify_ffi_regression_corpus: VM backend: {rel} (pre-vetted VM-safe, no "
                f"FFI features) was rejected by the FFI gate (exit {proc.returncode}) -- false positive",
                file=sys.stderr,
            )
            print(stderr[-1500:], file=sys.stderr)
            return -1
        n += 1
    print(f"verify_ffi_regression_corpus: VM backend OK ({n} safe fixture(s), gate never fired)", file=sys.stderr)
    return n


def check_c_output_golden() -> int:
    if not ensure_built(C_WRAPPER, "build-sv0-megatu-native.sh"):
        return -1
    n = 0
    for name in GOLDEN_C_FIXTURES:
        case = SV0C / "test" / "behavior" / "cases" / f"{name}.sv0"
        golden = GOLDEN_C_DIR / f"{name}.c"
        if not golden.is_file():
            print(f"verify_ffi_regression_corpus: missing golden {golden}", file=sys.stderr)
            return -1
        proc = subprocess.run([str(C_WRAPPER), str(case)], capture_output=True, timeout=60, check=False)
        if proc.returncode != 0:
            print(f"verify_ffi_regression_corpus: {name} failed to compile for golden diff", file=sys.stderr)
            print(proc.stderr.decode("utf-8", errors="replace")[-1500:], file=sys.stderr)
            return -1
        if proc.stdout != golden.read_bytes():
            print(
                f"verify_ffi_regression_corpus: {name}'s C output no longer matches "
                f"{golden} -- a safe program's codegen changed (refresh the golden only "
                f"if this is an intentional, unrelated C-backend change)",
                file=sys.stderr,
            )
            return -1
        n += 1
    print(f"verify_ffi_regression_corpus: C-output golden OK ({n} fixture(s) byte-identical)", file=sys.stderr)
    return n


def main() -> int:
    c = check_c_backend()
    if c < 0:
        return 1
    v = check_vm_backend()
    if v < 0:
        return 1
    g = check_c_output_golden()
    if g < 0:
        return 1
    print(
        f"verify_ffi_regression_corpus: OK ({c} C-backend + {v} VM-backend safe fixture(s) "
        f"+ {g} C-output golden(s))",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
