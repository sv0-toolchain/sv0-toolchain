#!/usr/bin/env python3
"""Canonical host-compile CLI for legacy test scripts (NEX-058, GOV-008).

`GOV-008` ("the canonical host-link implementation SHALL be shared by user
commands and integration tests") was already closed for the
`native_exe_*.py` driver itself back in R0 -- `native_exe_argv_builder.
build_dev_profile_argv` is its one canonical argv construction site. What
remained was three *legacy* shell scripts
(`scripts/pc3b6-native-project-acceptance.sh`,
`scripts/sv0-megatu-native-parity.sh`,
`scripts/sv0-megatu-corpus-parity.sh`) that still hand-rolled their own
`cc -std=c99 -O0 -w ...` recipes, independent of the driver, with a
blanket `-w` that §26.6 forbids at the stable gate.

This is a thin CLI wrapper around the SAME canonical pieces
`build_native_executable` itself uses for its host-compile step
(`native_exe_runtime.resolve_runtime_dir`, `native_exe_cc_select.select_cc`,
`native_exe_argv_builder.build_dev_profile_argv`,
`native_exe_env.sanitized_child_env`, `native_exe_host_compile.run_host_compile`,
`native_exe_publish.publish_atomically`) -- not a new implementation of
host linking, and not the full `build_native_executable` pipeline either:
these three scripts emit C themselves (exercising the CORE COMPILER's own
`--project`/single-file/include-expansion behavior, which predates and is
independent of the native-exe driver's own entry validation), so only the
"compile the already-emitted C" half is shared here, not the whole
pipeline.

Usage: `python3 scripts/native_exe_canonical_compile.py <c_file> <output_path>`
Exit 0 on success (matching the old `cc ... || fail` shell pattern); a
BuildError's message goes to stderr and the process exits 1.

Run `python3 scripts/native_exe_canonical_compile.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import sys
import tempfile

from native_exe_argv_builder import build_dev_profile_argv
from native_exe_cc_select import select_cc
from native_exe_env import sanitized_child_env
from native_exe_errors import BuildError
from native_exe_host_compile import run_host_compile
from native_exe_publish import publish_atomically
from native_exe_runtime import resolve_runtime_dir


def compile_and_publish(c_file: str, output_path: str) -> None:
    """Compile an already-emitted `c_file` (paired with the canonical
    runtime source) to `output_path`, via the exact same argv/env/
    validation/publish path `build_native_executable` uses for its own
    host-compile step. Raises `BuildError` on any failure.
    """
    runtime = resolve_runtime_dir()
    cc_path, _ = select_cc(None, os.environ)
    # Compile straight to a temp leaf beside the real output, then publish
    # atomically -- same ART-002/003 discipline as the real driver, not a
    # direct-to-final-path compile.
    with tempfile.TemporaryDirectory() as scratch:
        tmp_output = os.path.join(scratch, "out.tmp-exe")
        argv = build_dev_profile_argv(cc_path, runtime, c_file, tmp_output)
        env = sanitized_child_env(os.environ)
        run_host_compile(argv, env, tmp_output)
        publish_atomically(tmp_output, output_path)


def _selftest() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        c_file = os.path.join(td, "program.c")
        with open(c_file, "w", encoding="utf-8") as f:
            f.write('#include "sv0_runtime.h"\nint main(void) { sv0_println("hi"); return 42; }\n')
        out = os.path.join(td, "out")

        try:
            compile_and_publish(c_file, out)
        except BuildError as exc:
            failures.append(f"case1: canonical compile of a valid C file failed: {exc}")
        else:
            import subprocess

            proc = subprocess.run([out], capture_output=True, text=True)
            if proc.returncode != 42 or "hi" not in proc.stdout:
                failures.append(f"case1: compiled binary misbehaved: rc={proc.returncode} stdout={proc.stdout!r}")

        # Case 2: a C file with a real compile error fails closed, not silently.
        bad_c = os.path.join(td, "bad.c")
        with open(bad_c, "w", encoding="utf-8") as f:
            f.write("this is not valid C at all {{{\n")
        out2 = os.path.join(td, "out2")
        try:
            compile_and_publish(bad_c, out2)
            failures.append("case2: expected BuildError for invalid C, none raised")
        except BuildError:
            pass
        if os.path.exists(out2):
            failures.append("case2: no output should exist for a failed compile")

    if failures:
        for f in failures:
            print(f"native_exe_canonical_compile selftest FAIL: {f}")
        return 1

    print("native_exe_canonical_compile: selftest OK (2 cases)")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    args = [a for a in sys.argv[1:] if a != "--selftest"]
    if len(args) != 2:
        print("usage: native_exe_canonical_compile.py <c_file> <output_path>", file=sys.stderr)
        return 2
    c_file, output_path = args
    try:
        compile_and_publish(c_file, output_path)
    except BuildError as exc:
        print(f"native_exe_canonical_compile: {exc.message}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
