#!/usr/bin/env python3
"""FFI-014 (Epic E): the VM backend must refuse FFI-feature programs.

Runs each fixture in sv0c/test/vm-parity/ffi-vm-reject-manifest.txt through
the native VM bytecode emitter (build/sv0-megatu-vm-native, the same binary
scripts/vm-native-compile / vm_behavioral_parity.py drive) and asserts:

  * nonzero exit (currently 7, the compose main's dedicated code for this
    gate -- see lib/megaTU-main.sv0's phase-6 VM tail patch in
    scripts/build-sv0-megatu-vm-native.sh)
  * "E0553" appears in stderr (a real, typed diagnostic -- not a bare
    nonzero exit with no explanation)

Every one of these fixtures already compiles and runs correctly on the
native C backend (test/behavior/manifest.txt) -- this script is the VM
backend's own regression guard that the same programs are turned away
cleanly instead of miscompiled or crashing the emitter.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SV0C = ROOT / "sv0c"
VM_EMIT = ROOT / "build" / "sv0-megatu-vm-native"
MANIFEST = SV0C / "test" / "vm-parity" / "ffi-vm-reject-manifest.txt"


def main() -> int:
    if not MANIFEST.is_file():
        print(f"verify_vm_ffi_gate: missing {MANIFEST}", file=sys.stderr)
        return 1
    if not VM_EMIT.is_file():
        build = ROOT / "scripts" / "build-sv0-megatu-vm-native.sh"
        r = subprocess.run(["bash", str(build)], capture_output=True, text=True, check=False)
        if not VM_EMIT.is_file():
            print("verify_vm_ffi_gate: native VM emitter build failed", file=sys.stderr)
            print((r.stderr or "")[-2000:], file=sys.stderr)
            return 1

    n = 0
    for raw in MANIFEST.read_text(encoding="utf-8").splitlines():
        rel = raw.strip()
        if not rel or rel.startswith("#"):
            continue
        case = SV0C / rel
        if not case.is_file():
            print(f"verify_vm_ffi_gate: no such fixture: {case}", file=sys.stderr)
            return 1
        proc = subprocess.run(
            [str(VM_EMIT)],
            capture_output=True,
            text=True,
            timeout=60,
            env={**__import__("os").environ, "SV0_DRV_REQUEST": str(case)},
            check=False,
        )
        if proc.returncode == 0:
            print(
                f"verify_vm_ffi_gate: {rel} was ACCEPTED by the VM emitter "
                f"(exit 0) -- the FFI gate did not fire",
                file=sys.stderr,
            )
            return 1
        if "E0553" not in proc.stderr:
            print(
                f"verify_vm_ffi_gate: {rel} rejected (exit {proc.returncode}) "
                f"but missing E0553 in stderr -- not a typed diagnostic",
                file=sys.stderr,
            )
            print("--- stderr ---", file=sys.stderr)
            print(proc.stderr[-2000:], file=sys.stderr)
            return 1
        n += 1
    print(f"verify_vm_ffi_gate: OK ({n} case(s) rejected with E0553)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
