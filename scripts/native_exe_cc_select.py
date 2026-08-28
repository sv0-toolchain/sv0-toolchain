"""C-compiler selection precedence (NEX-021, NEX-064).

Implements TOOL-001…002
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §16.2): the
full precedence is explicit `--cc` → `sv0.toml` `c-compiler` → `SV0_CC`
environment variable → `CC` environment variable → `cc` resolved from
`PATH`. `--cc` and `sv0.toml`'s `c-compiler` are unified into this
function's single `explicit` parameter before it's ever called
(`native_exe_request.normalize_request` picks between them, CLI winning,
per §11.4) — from `select_cc`'s own point of view they're one tier. An
explicitly selected compiler (that unified tier) that is absent or not
executable is an error — the driver never falls through to a different
compiler (TOOL-002). `SV0_CC`/`CC`/`PATH` are the three *implicit* tiers:
each is tried in order only when the one before it is entirely unset, but
once a tier's variable IS set, an invalid value is still a hard error, not
a silent skip to the next tier -- "falls through" means "absent", not
"invalid".

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
    SV0_CC_ENV = "sv0_cc_env"
    CC_ENV = "cc_env"
    PATH_DEFAULT = "path_default"


def _is_executable_file(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.X_OK)


def _resolve_env_var(name: str, value: str, env: Mapping[str, str]) -> str:
    """Resolve one environment-variable-sourced compiler name/path via
    `PATH` (or accept it directly if it's already an executable file).
    Raises `BuildError(TOOL_DISCOVERY)` -- an environment-variable tier
    that's SET but resolves to nothing is a hard error, not a silent skip
    to the next tier (see this module's own docstring).
    """
    resolved = shutil.which(value, path=env.get("PATH"))
    if resolved is None and _is_executable_file(value):
        resolved = value
    if resolved is None:
        raise BuildError(DiagnosticPhase.TOOL_DISCOVERY, f"{name}={value!r} does not resolve to an executable")
    return resolved


def select_cc(explicit: str | None, env: Mapping[str, str]) -> tuple[str, CcSelection]:
    """Resolve the host C compiler per §16.2's full 5-tier precedence
    (`--cc`/`sv0.toml` unified as `explicit` → `SV0_CC` → `CC` → `PATH`).

    An invalid `explicit` selection is a hard TOOL_DISCOVERY error — no
    fallback to `SV0_CC`/`CC`/`PATH`. `SV0_CC`/`CC`/`PATH` are the implicit
    tiers and fall through to each other only when unset (not when invalid).
    """
    if explicit is not None:
        if not _is_executable_file(explicit):
            raise BuildError(
                DiagnosticPhase.TOOL_DISCOVERY,
                f"configured C compiler does not exist or is not executable: {explicit}",
            )
        return explicit, CcSelection.EXPLICIT

    sv0_cc_env = env.get("SV0_CC")
    if sv0_cc_env:
        return _resolve_env_var("SV0_CC", sv0_cc_env, env), CcSelection.SV0_CC_ENV

    cc_env = env.get("CC")
    if cc_env:
        return _resolve_env_var("CC", cc_env, env), CcSelection.CC_ENV

    resolved = shutil.which("cc", path=env.get("PATH"))
    if resolved is None:
        raise BuildError(
            DiagnosticPhase.TOOL_DISCOVERY,
            "no C compiler found: no --cc/sv0.toml given, SV0_CC and CC are unset, and `cc` is not on PATH",
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

        # Case 3b (NEX-064): SV0_CC wins over CC when both are set --
        # the spec's own stated tier order (SV0_CC above CC).
        another_good = os.path.join(td, "another-good-cc")
        with open(another_good, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(another_good, os.stat(another_good).st_mode | stat.S_IXUSR)
        path, sel = select_cc(None, {"SV0_CC": another_good, "CC": good, "PATH": td})
        if path != another_good or sel is not CcSelection.SV0_CC_ENV:
            failures.append(f"SV0_CC over CC: expected ({another_good}, SV0_CC_ENV), got ({path}, {sel})")

        # Case 3c: SV0_CC alone (no CC) still resolves correctly.
        path, sel = select_cc(None, {"SV0_CC": good, "PATH": td})
        if path != good or sel is not CcSelection.SV0_CC_ENV:
            failures.append(f"SV0_CC alone: expected ({good}, SV0_CC_ENV), got ({path}, {sel})")

        # Case 3d: an invalid SV0_CC is a hard error -- it does NOT silently
        # fall through to a perfectly valid CC (matching CC's own existing
        # invalid-value-is-fatal behavior, never "invalid means skip").
        try:
            select_cc(None, {"SV0_CC": missing, "CC": good, "PATH": td})
            failures.append("invalid SV0_CC: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.TOOL_DISCOVERY:
                failures.append(f"invalid SV0_CC: expected TOOL_DISCOVERY, got {exc.phase}")

        # Case 3e: an explicit --cc still wins outright over SV0_CC (the
        # unified explicit tier is strictly above every environment tier).
        path, sel = select_cc(good, {"SV0_CC": another_good})
        if path != good or sel is not CcSelection.EXPLICIT:
            failures.append(f"explicit over SV0_CC: expected ({good}, EXPLICIT), got ({path}, {sel})")

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

    print("native_exe_cc_select: selftest OK (11 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_cc_select: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
