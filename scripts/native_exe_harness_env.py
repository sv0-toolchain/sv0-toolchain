"""Test harness environment control (TEST-006).

Implements TEST-006
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "Test
harness SHALL control locale, timezone, temp root, cwd, umask, and
compiler selection." Red test: "Harness self-test." This module *is*
that self-test.

Distinct from `native_exe_env.sanitized_child_env` (SEC-006/TOOL-007…008),
which sanitizes the environment a *build's host compiler subprocess* sees
-- a different, already-real thing. This module is about the *test
harness's own ambient process environment* while running
`./scripts/sv0 test`/`test-guards` itself, so every test run is
reproducible regardless of the invoking shell's own locale/timezone/umask.

Two of TEST-006's five properties are already true by construction,
confirmed by direct inspection, not assumed:
  - **temp root**: every `native_exe_*.py` test uses
    `tempfile.TemporaryDirectory()`, which already respects an explicit
    `TMPDIR` -- this module only confirms one is actually set, not a
    silent OS default.
  - **compiler selection**: `native_exe_cc_select.select_cc`'s explicit
    `--cc` -> `CC` -> `PATH` precedence (TOOL-001/002) already makes
    compiler selection fully controllable and already has its own
    dedicated, mutation-tested corpus (NEX-021) -- nothing new needed
    here.

The other three (**locale**, **timezone**, **umask**) were not previously
pinned anywhere -- `scripts/sv0`'s `run_python_guards` now `export`s
`LC_ALL=C`/`TZ=UTC` and sets `umask 022` before running any Python guard;
`verify_harness_env` is the check that a future edit to that wrapper
can't silently drop the pinning without a test noticing. **cwd** is
already independent of the invoking shell by construction: every
Python guard is invoked as `python3 "$ROOT/scripts/<module>.py" --root
"$ROOT" ...` with explicit absolute paths, never a bare relative path
that would depend on the caller's own working directory.

Run `python3 scripts/native_exe_harness_env.py --selftest` for the corpus.
"""

from __future__ import annotations

import os

REQUIRED_LOCALE = "C"
REQUIRED_TZ = "UTC"
REQUIRED_UMASK = 0o022


def _current_umask() -> int:
    """Read the process umask without permanently changing it -- `os.umask`
    is the only POSIX way to *read* it, so this sets a throwaway value and
    immediately restores the real one.
    """
    current = os.umask(0o22)
    os.umask(current)
    return current


def verify_harness_env(env: dict | None = None, umask: int | None = None) -> None:
    """Raise `ValueError` listing every harness-environment property that
    isn't pinned as TEST-006 requires. `env`/`umask` are injectable for
    tests; production callers pass neither (real `os.environ`/`os.umask`).
    """
    env = env if env is not None else os.environ
    umask = umask if umask is not None else _current_umask()

    problems: list[str] = []
    if env.get("LC_ALL") != REQUIRED_LOCALE:
        problems.append(f"LC_ALL={env.get('LC_ALL')!r}, want {REQUIRED_LOCALE!r}")
    if env.get("TZ") != REQUIRED_TZ:
        problems.append(f"TZ={env.get('TZ')!r}, want {REQUIRED_TZ!r}")
    tmpdir = env.get("TMPDIR")
    if not tmpdir:
        problems.append("TMPDIR is not set -- temp root would fall back to an unpinned OS default")
    if umask != REQUIRED_UMASK:
        problems.append(f"umask={oct(umask)}, want {oct(REQUIRED_UMASK)}")

    if problems:
        raise ValueError("test harness environment not pinned as TEST-006 requires: " + "; ".join(problems))


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: a correctly pinned environment passes.
    good_env = {"LC_ALL": "C", "TZ": "UTC", "TMPDIR": "/tmp"}
    try:
        verify_harness_env(good_env, umask=0o022)
    except ValueError as exc:
        failures.append(f"case1: a correctly pinned environment was rejected: {exc}")

    # Case 2: a wrong LC_ALL is caught.
    try:
        verify_harness_env({"LC_ALL": "en_US.UTF-8", "TZ": "UTC", "TMPDIR": "/tmp"}, umask=0o022)
        failures.append("case2: expected ValueError for a wrong LC_ALL, none raised")
    except ValueError as exc:
        if "LC_ALL" not in str(exc):
            failures.append(f"case2: error didn't mention LC_ALL: {exc}")

    # Case 3: a wrong TZ is caught.
    try:
        verify_harness_env({"LC_ALL": "C", "TZ": "America/Los_Angeles", "TMPDIR": "/tmp"}, umask=0o022)
        failures.append("case3: expected ValueError for a wrong TZ, none raised")
    except ValueError as exc:
        if "TZ" not in str(exc):
            failures.append(f"case3: error didn't mention TZ: {exc}")

    # Case 4: a missing TMPDIR is caught.
    try:
        verify_harness_env({"LC_ALL": "C", "TZ": "UTC"}, umask=0o022)
        failures.append("case4: expected ValueError for a missing TMPDIR, none raised")
    except ValueError as exc:
        if "TMPDIR" not in str(exc):
            failures.append(f"case4: error didn't mention TMPDIR: {exc}")

    # Case 5: a wrong umask is caught.
    try:
        verify_harness_env(good_env, umask=0o002)
        failures.append("case5: expected ValueError for a wrong umask, none raised")
    except ValueError as exc:
        if "umask" not in str(exc):
            failures.append(f"case5: error didn't mention umask: {exc}")

    # Case 6: _current_umask reads without permanently changing the real
    # umask (the whole point of the read-then-restore trick).
    before = _current_umask()
    _current_umask()
    after = _current_umask()
    if before != after:
        failures.append(f"case6: _current_umask changed the real umask: {oct(before)} -> {oct(after)}")

    if failures:
        for f in failures:
            print(f"native_exe_harness_env selftest FAIL: {f}")
        return 1

    print("native_exe_harness_env: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--verify" in sys.argv:
        try:
            verify_harness_env()
        except ValueError as exc:
            print(f"native_exe_harness_env: {exc}", file=sys.stderr)
            raise SystemExit(1)
        print("native_exe_harness_env: OK -- harness environment correctly pinned")
        raise SystemExit(0)
    print("native_exe_harness_env: library module; use --selftest or --verify", file=sys.stderr)
    raise SystemExit(2)
