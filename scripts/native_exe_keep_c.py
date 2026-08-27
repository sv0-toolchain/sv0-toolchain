"""`--keep-c` retention on both link success and link failure (NEX-040).

Implements CLI-015/ART-012
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "`--keep-c`
in R0.1 copies the exact staging C atomically to the documented retained-C
path on either link success or link failure after successful emission."
`build_native_executable`'s `keep_c_path` parameter (added directly to that
function, not a separate wrapper, since retention has to happen *inside*
the same pipeline run to see the same staging C) writes the retained copy
right after `validate_staging_c` succeeds — unconditionally, before host
compile runs — so a later host-compile/link failure never erases it.

Run `python3 scripts/native_exe_keep_c.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import stat
import tempfile

from native_exe_build import build_native_executable
from native_exe_errors import BuildError
from native_exe_staging import hash_staging_c


def _make_failing_cc_wrapper(td: str, fake_cc: str) -> str:
    """A tiny wrapper baking `SV0_FAKE_CC_MODE=fail` into the executable
    itself -- `sanitized_child_env` correctly strips that env var before the
    real host-compiler invocation (it isn't allowlisted, by design), so a
    var set by the test process never reaches the subprocess (see
    `native_exe_preservation.py`'s `_make_cc_wrapper` for the same pattern).
    """
    wrapper = os.path.join(td, "fake_cc_fail.sh")
    with open(wrapper, "w", encoding="utf-8") as f:
        f.write(f"#!/bin/sh\nexport SV0_FAKE_CC_MODE=fail\nexec python3 {fake_cc} \"$@\"\n")
    os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return wrapper


def _selftest() -> int:
    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")

    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("hi");\n    return 0;\n}\n')

        # Case 1: retained C on a SUCCESSFUL build matches exactly what was staged.
        out1 = os.path.join(td, "hello_out")
        keep1 = os.path.join(td, "retained_success.c")
        build_native_executable("file", src, out1, td, probe=False, keep_c_path=keep1)
        if not os.path.isfile(keep1):
            failures.append("success case: retained C was not written")
        elif not os.path.isfile(out1):
            failures.append("success case: build did not actually succeed")

        # Case 2: retained C on a FAILED host-compile/link ALSO matches exactly
        # what was staged (ART-012's literal point -- retention survives a
        # later failure, since it happens before host compile ever runs).
        out2 = os.path.join(td, "hello_out2")
        keep2 = os.path.join(td, "retained_failure.c")
        failing_cc = _make_failing_cc_wrapper(td, fake_cc)
        try:
            build_native_executable(
                "file", src, out2, td, probe=False, keep_c_path=keep2, explicit_cc=failing_cc
            )
            failures.append("failure case: expected a host-compile BuildError, build succeeded")
        except BuildError:
            pass
        if not os.path.isfile(keep2):
            failures.append("failure case: retained C was NOT written despite the later host-compile failure")

        # Case 3: both retained copies hash-match each other (same source, same
        # staging C both times) -- proves retention isn't silently mangling content.
        if os.path.isfile(keep1) and os.path.isfile(keep2):
            c1 = open(keep1, encoding="utf-8").read()
            c2 = open(keep2, encoding="utf-8").read()
            if hash_staging_c(c1) != hash_staging_c(c2):
                failures.append("retained C differs between the success and failure runs of the same source")

    if failures:
        for f in failures:
            print(f"native_exe_keep_c selftest FAIL: {f}")
        return 1

    print("native_exe_keep_c: selftest OK (3 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_keep_c: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
