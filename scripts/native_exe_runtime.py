"""Compiler-relative runtime resolver (NEX-019).

Implements RT-001…003
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §10.5, AE-005):
the driver resolves the runtime bundle (`sv0_runtime.h`/`sv0_runtime.c`) from
the compiler installation, never from the invocation's current working
directory, `CPATH`, or a project-relative search. In this repo's dev-tree
shape, "the compiler installation" is the toolchain root this script lives
under — `resolve_runtime_dir` derives that from `__file__`'s own location,
exactly like every existing `verify_*.py`'s own `--root` default, so runtime
resolution can never be influenced by where the caller happened to `cd`.

Run `python3 scripts/native_exe_runtime.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from native_exe_errors import BuildError, DiagnosticPhase


@dataclass
class RuntimeLocation:
    dir: str
    header: str
    source: str


def resolve_runtime_dir(root: str | None = None) -> RuntimeLocation:
    """Resolve the runtime bundle relative to the toolchain installation.

    `root` defaults to this script's own toolchain root (parent of `scripts/`)
    — never the invocation cwd, an environment variable a caller could set,
    or anything under the source project being compiled.
    """
    base = Path(root) if root is not None else Path(__file__).resolve().parent.parent
    runtime_dir = base / "sv0c" / "runtime"
    header = runtime_dir / "sv0_runtime.h"
    source = runtime_dir / "sv0_runtime.c"

    if not header.is_file() or not source.is_file():
        raise BuildError(
            DiagnosticPhase.RUNTIME,
            f"runtime bundle not found at {runtime_dir} "
            "(compiler-relative resolution never falls back to cwd/CPATH/project paths)",
        )

    return RuntimeLocation(dir=str(runtime_dir), header=str(header), source=str(source))


def _selftest() -> int:
    import tempfile

    failures: list[str] = []
    real_root = str(Path(__file__).resolve().parent.parent)

    # Case 1: resolves correctly regardless of invocation cwd.
    original_cwd = os.getcwd()
    try:
        with tempfile.TemporaryDirectory() as td:
            os.chdir(td)
            loc = resolve_runtime_dir(real_root)
            if not os.path.isfile(loc.header) or not os.path.isfile(loc.source):
                failures.append(f"resolution from unrelated cwd failed: {loc}")
    finally:
        os.chdir(original_cwd)

    # Case 2: a malicious project-local sv0_runtime.h is never selected --
    # resolve_runtime_dir doesn't even look inside a "project" argument,
    # because it never takes one; prove that explicitly by pointing `root`
    # at a fake toolchain root that has NO sv0c/runtime and confirming it
    # fails closed rather than wandering off to find a project-local one.
    with tempfile.TemporaryDirectory() as td:
        fake_project = os.path.join(td, "some_project")
        os.makedirs(fake_project)
        with open(os.path.join(fake_project, "sv0_runtime.h"), "w", encoding="utf-8") as f:
            f.write("/* malicious shadow */\n")
        try:
            resolve_runtime_dir(td)  # `td` has no sv0c/runtime -- must fail, not find the shadow
            failures.append("expected BuildError(RUNTIME) for a root with no runtime bundle, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.RUNTIME:
                failures.append(f"expected RUNTIME phase, got {exc.phase}")

    # Case 3: the real toolchain root resolves to the real, existing files.
    loc = resolve_runtime_dir(real_root)
    if not loc.dir.endswith(os.path.join("sv0c", "runtime")):
        failures.append(f"unexpected runtime dir: {loc.dir}")

    if failures:
        for f in failures:
            print(f"native_exe_runtime selftest FAIL: {f}")
        return 1

    print("native_exe_runtime: selftest OK (3 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_runtime: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
