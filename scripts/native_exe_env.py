"""Sanitized child environment (NEX-024).

Implements SEC-006/TOOL-007…008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §16.7, OD-006):
the host compiler child process must not be able to have its include/library
search silently substituted by environment variables the parent process
happens to have set. `sanitized_child_env` builds the child environment from
an explicit allowlist rather than filtering a denylist — anything not named
is dropped, so a newly invented injection variable doesn't need a
follow-up patch to stay blocked.

OD-006's allowlist: `PATH`, `LANG`, `LC_ALL`, `TMPDIR`/`TEMP`/`TMP`, and the
macOS SDK variables `SDKROOT`/`DEVELOPER_DIR`. Explicitly never carried
through, regardless of what the parent has set: `CPATH`, `C_INCLUDE_PATH`,
`OBJC_INCLUDE_PATH`, `LIBRARY_PATH`, `LD_LIBRARY_PATH`, `DYLD_LIBRARY_PATH`
— exactly the variables that could substitute the trusted runtime
include/library path from `native_exe_argv_builder`'s `-I<runtime>` (TOOL-007's
other half — the argv builder already puts the trusted `-I` first; this is
what keeps an implicit env-based search from ever competing with it, TOOL-008).

Run `python3 scripts/native_exe_env.py --selftest` for the corpus.
"""

from __future__ import annotations

from typing import Mapping

ALLOWED_ENV_KEYS = (
    "PATH",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "TEMP",
    "TMP",
    "SDKROOT",
    "DEVELOPER_DIR",
)

# Not exhaustive of "everything not allowed" (the allowlist already handles
# that) -- named explicitly so the selftest can prove each one is blocked
# even when the parent environment sets it, not merely "not in the allowlist".
BLOCKED_INJECTION_KEYS = (
    "CPATH",
    "C_INCLUDE_PATH",
    "OBJC_INCLUDE_PATH",
    "LIBRARY_PATH",
    "LD_LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
)


def sanitized_child_env(parent_env: Mapping[str, str]) -> dict[str, str]:
    """Build a child environment containing only the allowlisted keys present
    in `parent_env`. Never a copy-then-strip of the full parent environment —
    an allowlist can't miss a newly invented injection variable.
    """
    return {key: parent_env[key] for key in ALLOWED_ENV_KEYS if key in parent_env}


def _selftest() -> int:
    failures: list[str] = []

    hostile_parent = {key: "/hostile/injected/path" for key in BLOCKED_INJECTION_KEYS}
    hostile_parent.update(
        {
            "PATH": "/usr/bin:/bin",
            "LANG": "en_US.UTF-8",
            "LC_ALL": "C",
            "TMPDIR": "/tmp",
            "SDKROOT": "/some/sdk",
            "DEVELOPER_DIR": "/some/xcode",
            "HOME": "/Users/whoever",  # not allowlisted, not an injection risk either -- just extra noise
            "RANDOM_UNRELATED_VAR": "whatever",
        }
    )

    child = sanitized_child_env(hostile_parent)

    # Case 1: every blocked injection variable is absent, even though the parent set it.
    for key in BLOCKED_INJECTION_KEYS:
        if key in child:
            failures.append(f"{key} leaked into the sanitized child env")

    # Case 2: allowlisted keys present in the parent do pass through.
    for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SDKROOT", "DEVELOPER_DIR"):
        if child.get(key) != hostile_parent[key]:
            failures.append(f"{key} did not pass through correctly: {child.get(key)!r}")

    # Case 3: an unrelated, non-allowlisted key never passes through either.
    if "HOME" in child or "RANDOM_UNRELATED_VAR" in child:
        failures.append("a non-allowlisted key leaked into the sanitized child env")

    # Case 4: an allowlisted key absent from the parent is simply absent, not
    # defaulted to something.
    sparse_child = sanitized_child_env({"PATH": "/usr/bin"})
    if set(sparse_child) != {"PATH"}:
        failures.append(f"expected only PATH in a sparse parent env, got {set(sparse_child)}")

    if failures:
        for f in failures:
            print(f"native_exe_env selftest FAIL: {f}")
        return 1

    print("native_exe_env: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_env: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
