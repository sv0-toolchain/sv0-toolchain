"""Symlink/scratch/race hardening, driven end to end (NEX-033).

Implements SEC-003…005
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): consolidation,
not new logic — `native_exe_output_path.py` (NEX-026) and
`native_exe_scratch.py` (NEX-008) already mutation-test symlink rejection
and scratch-cleanup scoping at the unit level. This proves both guarantees
hold when driven through the real, assembled
`native_exe_build.build_native_executable`, not just their own isolated
tests:

  - A final output path that's a symlink to a protected file is rejected
    before any tool runs, and the protected file is untouched (AC-018).
  - A neighbor scratch directory (with its own sentinel file) present
    during a real build survives that build's cleanup untouched.

Run `python3 scripts/native_exe_hardening_smoke.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import tempfile

from native_exe_build import build_native_executable
from native_exe_errors import BuildError
from native_exe_scratch import ScratchDir


def _selftest() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        # Case 1 (AC-018): -o naming a symlink to a protected sentinel fails
        # without touching the target, driven through the real pipeline.
        protected = os.path.join(td, "protected_sentinel")
        with open(protected, "w", encoding="utf-8") as f:
            f.write("do not touch\n")
        symlink_out = os.path.join(td, "symlink_output")
        os.symlink(protected, symlink_out)

        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 0;\n}\n")

        try:
            build_native_executable("file", src, symlink_out, td, probe=False)
            failures.append("symlink output: expected BuildError, build succeeded")
        except BuildError:
            pass
        if open(protected, encoding="utf-8").read() != "do not touch\n":
            failures.append("symlink output: the protected target was modified")
        if not os.path.islink(symlink_out):
            failures.append("symlink output: the symlink itself was replaced")

        # Case 2: a neighbor scratch directory (with its own sentinel), living
        # under the SAME parent the real build's own scratch dir will use
        # (via the scratch_base_dir test seam -- genuinely adjacency-sensitive,
        # not just "some unrelated directory elsewhere"), survives that real
        # build's own scratch cleanup untouched.
        shared_base = tempfile.mkdtemp(dir=td)
        neighbor = ScratchDir(base_dir=shared_base)
        with neighbor:
            sentinel = os.path.join(neighbor.path, "SHOULD_NOT_BE_TOUCHED")
            with open(sentinel, "w", encoding="utf-8") as f:
                f.write("neighbor data\n")

            out = os.path.join(td, "hello_out")
            build_native_executable("file", src, out, td, probe=False, scratch_base_dir=shared_base)

            if not os.path.isfile(sentinel):
                failures.append("neighbor scratch sentinel did not survive a real, adjacent build's cleanup")

    if failures:
        for f in failures:
            print(f"native_exe_hardening_smoke selftest FAIL: {f}")
        return 1

    print("native_exe_hardening_smoke: selftest OK (2 case groups)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_hardening_smoke: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
