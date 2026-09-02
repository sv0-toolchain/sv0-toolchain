#!/usr/bin/env python3
"""SS-U02d (sv0-strings Track U, UP-007 / BL-015): owned-`string` allocation
fault injection on the C backend.

Compiles sv0c/test/behavior/cases/string_alloc_fault.sv0 (4 owned-string
allocations: 3 literals + 1 concat) with the native mega-TU compiler, then
runs it under several SV0_STR_FAIL_AT values:

  unset / past the last alloc  -> exit 42 (no injection)
  1 .. 4                       -> exit 1, "sv0 panic: string: allocation failed"
                                 on stderr (fail closed, no partial value)

Run by `./scripts/sv0 test`.
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
PANIC = "sv0 panic: string: allocation failed"


def _fail(msg: str) -> int:
    print(f"verify_string_alloc_failure: {msg}", file=sys.stderr)
    return 1


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

    print("verify_string_alloc_failure: OK (baseline + 5 injection points)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
