#!/usr/bin/env python3
"""SS-U02d / SS-U17 (sv0-strings Track U, UP-007 / BL-015 / BACKEND-004):
owned-`string` allocation fault injection on BOTH backends.

Compiles sv0c/test/behavior/cases/string_alloc_fault.sv0 with the native
mega-TU compiler and runs it under several SV0_STR_FAIL_AT values:

  C backend  (4 owned-string allocations: 3 literals + 1 concat)
    unset / past the last alloc  -> exit 42 (no injection)
    1 .. 4                       -> exit 1, "sv0 panic: string: allocation failed"

  VM backend  (SS-U17: literals are table-loaded, so only the 1 runtime
               concat allocation is counted)
    unset / >= 2                 -> exit 42 (no injection)
    1                            -> exit 1, same panic on stderr

Both legs produce the identical typed error, so BACKEND-004 ("injection
SHALL exist on both backends with equivalent typed errors") holds. Run by
`./scripts/sv0 test`.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from native_exe_canonical_compile import compile_and_publish  # noqa: E402
from native_exe_errors import BuildError  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CASE = ROOT / "sv0c" / "test" / "behavior" / "cases" / "string_alloc_fault.sv0"
WRAPPER = ROOT / "build" / "sv0-megatu-compiler-native"
VM_EMITTER = ROOT / "build" / "sv0-megatu-vm-native"
SV0VM_DIR = ROOT / "sv0vm"
RUN_SV0B = SV0VM_DIR / "scripts" / "run_sv0b.sml"
PANIC = "sv0 panic: string: allocation failed"


def _fail(msg: str) -> int:
    print(f"verify_string_alloc_failure: {msg}", file=sys.stderr)
    return 1


def _verify_vm() -> int:
    """SS-U17: the VM peer of the C fault injector. Emit string_alloc_fault.sv0
    with the native VM emitter and run it through sv0vm; only the one runtime
    concat allocation is counted (literals are table-loaded)."""
    if not VM_EMITTER.is_file():
        return _fail(f"missing VM emitter {VM_EMITTER}")
    if not RUN_SV0B.is_file():
        return _fail(f"missing {RUN_SV0B}")
    with tempfile.TemporaryDirectory() as td:
        sv0b = os.path.join(td, "out.sv0b")
        emit = subprocess.run(
            [str(VM_EMITTER)],
            env={**os.environ, "SV0_DRV_REQUEST": str(CASE)},
            capture_output=True, timeout=180,
        )
        if emit.returncode != 0:
            return _fail(f"VM emit failed:\n{(emit.stderr or b'').decode('utf-8', 'replace')[-1200:]}")
        Path(sv0b).write_bytes(emit.stdout)

        def run_vm(fail_at: str | None):
            env = dict(os.environ)
            env["SV0B"] = sv0b
            if fail_at is None:
                env.pop("SV0_STR_FAIL_AT", None)
            else:
                env["SV0_STR_FAIL_AT"] = fail_at
            with open(RUN_SV0B) as fh:
                return subprocess.run(
                    ["sml"], stdin=fh, cwd=str(SV0VM_DIR),
                    capture_output=True, text=True, env=env, timeout=180,
                )

        r = run_vm(None)
        if "vm_exit:42" not in (r.stdout or ""):
            return _fail(f"VM baseline: expected vm_exit:42, got {r.stdout!r} / {r.stderr!r}")
        r = run_vm("2")
        if "vm_exit:42" not in (r.stdout or ""):
            return _fail(f"VM SV0_STR_FAIL_AT=2: expected vm_exit:42 (past the 1 runtime alloc)")
        r = run_vm("1")
        if "vm_exit:1" not in (r.stdout or ""):
            return _fail(f"VM SV0_STR_FAIL_AT=1: expected vm_exit:1, got {r.stdout!r}")
        if PANIC not in (r.stderr or ""):
            return _fail(f"VM SV0_STR_FAIL_AT=1: missing {PANIC!r} on stderr; got {r.stderr!r}")
    return 0


def main() -> int:
    if not CASE.is_file():
        return _fail(f"missing case {CASE}")
    if not WRAPPER.is_file():
        subprocess.run(["bash", str(ROOT / "scripts" / "build-sv0-megatu-native.sh")],
                       capture_output=True, text=True, check=False)
    if not WRAPPER.is_file():
        return _fail("native compiler build failed")

    with tempfile.TemporaryDirectory() as td:
        cpath = os.path.join(td, "out.c")
        binp = os.path.join(td, "out.bin")
        emit = subprocess.run([str(WRAPPER), str(CASE)], capture_output=True,
                              text=True, timeout=120)
        if emit.returncode != 0:
            return _fail(f"emit failed:\n{(emit.stderr or '')[-1200:]}")
        Path(cpath).write_text(emit.stdout)
        try:
            compile_and_publish(cpath, binp)
        except BuildError as exc:
            return _fail(f"cc failed:\n{str(exc)[-1200:]}")

        def run(fail_at: str | None):
            env = dict(os.environ)
            if fail_at is None:
                env.pop("SV0_STR_FAIL_AT", None)
            else:
                env["SV0_STR_FAIL_AT"] = fail_at
            return subprocess.run([binp], capture_output=True, text=True, env=env)

        # No injection -> clean exit 42.
        r = run(None)
        if r.returncode != 42:
            return _fail(f"baseline exited {r.returncode}, expected 42")

        # Past the last allocation -> also clean.
        r = run("99")
        if r.returncode != 42:
            return _fail(f"SV0_STR_FAIL_AT=99 exited {r.returncode}, expected 42")

        # Each of the 4 real allocations, when failed, aborts fail-closed.
        for n in range(1, 5):
            r = run(str(n))
            if r.returncode != 1:
                return _fail(f"SV0_STR_FAIL_AT={n} exited {r.returncode}, expected 1")
            if PANIC not in (r.stderr or ""):
                return _fail(f"SV0_STR_FAIL_AT={n}: missing {PANIC!r} on stderr; "
                             f"got {r.stderr!r}")

    vm_rc = _verify_vm()
    if vm_rc != 0:
        return vm_rc

    print("verify_string_alloc_failure: OK (C: baseline + 5 injection points; "
          "VM: baseline + runtime-alloc injection -- BACKEND-004 parity)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
