"""C-compiler selection precedence (NEX-021).

Implements TOOL-001…002
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §16.2): the R0
tiers of the compiler-selection precedence are explicit `--cc` → `CC`
environment variable → `cc` resolved from `PATH`. (`sv0.toml`'s
`c-compiler` and `SV0_CC` are R0.1-only tiers and don't exist yet.) An
explicitly selected compiler that is absent or not executable is an error —
the driver never falls through to a different compiler (TOOL-002); only the
*implicit* `CC`/`PATH` tiers fall through to each other.

Run `python3 scripts/native_exe_cc_select.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import shutil
from enum import Enum
from typing import Mapping

from native_exe_errors import BuildError, DiagnosticPhase


class CcSelection(Enum):
    EXPLICIT = "explicit"
    CC_ENV = "cc_env"
    PATH_DEFAULT = "path_default"


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def select_cc(explicit: str | None, env: Mapping[str, str]) -> tuple[str, CcSelection]:
    """Resolve the host C compiler per §16.2's R0 precedence.

    An invalid `explicit` selection is a hard TOOL_DISCOVERY error — no
    fallback to `CC`/`PATH`. `CC`/`PATH` are the implicit tiers and do fall
    through to each other.
    """
    if explicit is not None:
        if not _is_executable_file(explicit):
            raise BuildError(
                DiagnosticPhase.TOOL_DISCOVERY,
                f"configured C compiler does not exist or is not executable: {explicit}",
            )
        return explicit, CcSelection.EXPLICIT

    cc_env = env.get("CC")
    if cc_env:
        resolved = shutil.which(cc_env, path=env.get("PATH"))
        if resolved is None and _is_executable_file(cc_env):
            resolved = cc_env
        if resolved is None:
            raise BuildError(
                DiagnosticPhase.TOOL_DISCOVERY,
                f"CC={cc_env!r} does not resolve to an executable",
            )
        return resolved, CcSelection.CC_ENV

    resolved = shutil.which("cc", path=env.get("PATH"))
    if resolved is None:
        raise BuildError(
            DiagnosticPhase.TOOL_DISCOVERY,
            "no C compiler found: no --cc given, CC is unset, and `cc` is not on PATH",
        )
    return resolved, CcSelection.PATH_DEFAULT


def _selftest() -> int:
    import stat
    import tempfile

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        good = os.path.join(td, "good-cc")
        with open(good, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(good, os.stat(good).st_mode | stat.S_IXUSR)

        not_executable = os.path.join(td, "not-executable")
        with open(not_executable, "w", encoding="utf-8") as f:
            f.write("not a compiler\n")

        missing = os.path.join(td, "does-not-exist")

        # Case 1: explicit --cc wins and is used verbatim.
        path, sel = select_cc(good, {})
        if path != good or sel is not CcSelection.EXPLICIT:
            failures.append(f"explicit: expected ({good}, EXPLICIT), got ({path}, {sel})")

        # Case 2: an invalid explicit --cc is a hard error, no fallback even
        # when CC/PATH would otherwise resolve fine.
        try:
            select_cc(missing, {"CC": good, "PATH": td})
            failures.append("invalid explicit: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.TOOL_DISCOVERY:
                failures.append(f"invalid explicit: expected TOOL_DISCOVERY, got {exc.phase}")

        # Case 2b: an explicit --cc naming a non-executable file is also rejected.
        try:
            select_cc(not_executable, {})
            failures.append("non-executable explicit: expected BuildError, none raised")
        except BuildError:
            pass

        # Case 3: CC env is used when no explicit --cc is given.
        path, sel = select_cc(None, {"CC": good, "PATH": td})
        if path != good or sel is not CcSelection.CC_ENV:
            failures.append(f"CC env: expected ({good}, CC_ENV), got ({path}, {sel})")

        # Case 4: PATH default (`cc`) is used when neither --cc nor CC is given.
        fake_cc_on_path = os.path.join(td, "cc")
        with open(fake_cc_on_path, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(fake_cc_on_path, os.stat(fake_cc_on_path).st_mode | stat.S_IXUSR)
        path, sel = select_cc(None, {"PATH": td})
        if path != fake_cc_on_path or sel is not CcSelection.PATH_DEFAULT:
            failures.append(f"PATH default: expected ({fake_cc_on_path}, PATH_DEFAULT), got ({path}, {sel})")

        # Case 5: nothing resolves -> clean error, not a crash.
        empty_path_dir = os.path.join(td, "empty")
        os.makedirs(empty_path_dir)
        try:
            select_cc(None, {"PATH": empty_path_dir})
            failures.append("nothing resolves: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.TOOL_DISCOVERY:
                failures.append(f"nothing resolves: expected TOOL_DISCOVERY, got {exc.phase}")

    if failures:
        for f in failures:
            print(f"native_exe_cc_select selftest FAIL: {f}")
        return 1

    print("native_exe_cc_select: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_cc_select: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
