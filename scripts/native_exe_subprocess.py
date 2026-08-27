"""Direct argv-only subprocess abstraction for the native-executable driver (NEX-009).

Implements TOOL-003 ("host compiler SHALL be invoked directly with an argv
array") and SEC-001 ("no child process SHALL be launched through a shell") from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`. `run_argv` is the
**only** sanctioned way later driver slices (core-compiler invocation,
host-compiler invocation) spawn a child process — it structurally cannot
invoke a shell: `shell` is not a parameter at all, `subprocess.run` is always
called with `shell=False`, and passing a bare string instead of a list of
tokens is a `TypeError`, not a convenience that silently degrades into a
shell command.

This is deliberately a thin wrapper, not a process-management framework —
timeouts, cancellation/process-group handling, and environment sanitization
are later slices (NEX-024, NEX-034) that build on top of this rather than
duplicate it (spec principle 10: "one implementation of host linking").

Run `python3 scripts/native_exe_subprocess.py --selftest` for the corpus,
including NEX-009's literal red test: a shell-metacharacter sentinel embedded
in a single argv element never gets created as a side effect.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass


class SubprocessError(Exception):
    """Raised for a usage error or unrecoverable process-launch failure."""


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_argv(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
) -> CommandResult:
    """Run `argv` directly — never through a shell. `argv` must be a non-empty
    list of strings; a bare string is rejected outright rather than silently
    becoming a shell command line.
    """
    if isinstance(argv, str):
        raise TypeError(
            "run_argv requires a list of argv tokens, never a shell command string "
            f"(got a str: {argv!r})"
        )
    if not argv or not all(isinstance(tok, str) for tok in argv):
        raise TypeError(f"argv must be a non-empty list[str], got {argv!r}")

    try:
        proc = subprocess.run(
            list(argv),
            shell=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SubprocessError(f"executable not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SubprocessError(f"timed out after {timeout}s: {argv}") from exc

    return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _selftest() -> int:
    import os
    import sys
    import tempfile

    failures: list[str] = []

    # Case 1: a bare string is rejected, never silently treated as a shell command.
    try:
        run_argv("echo hello")  # type: ignore[arg-type]
        failures.append("expected TypeError for a bare string argv, got none")
    except TypeError:
        pass

    # Case 2: empty argv is rejected.
    try:
        run_argv([])
        failures.append("expected TypeError for empty argv, got none")
    except TypeError:
        pass

    # Case 3: a normal argv round-trips correctly (sanity check on the happy path).
    r = run_argv([sys.executable, "-c", "import sys; print(sys.argv[1]); sys.exit(0)", "hello"])
    if r.returncode != 0 or r.stdout.strip() != "hello":
        failures.append(f"happy path: rc={r.returncode} stdout={r.stdout!r}")

    # Case 4 (NEX-009's literal red test): a shell-metacharacter payload passed
    # as ONE argv element never gets interpreted — the sentinel is never created,
    # and the receiving process sees the string byte-for-byte, unsplit.
    with tempfile.TemporaryDirectory() as td:
        sentinel = os.path.join(td, "SHOULD_NOT_EXIST")
        hostile = f"; $(touch {sentinel}) && `touch {sentinel}` | touch {sentinel} > {sentinel}"
        r = run_argv([sys.executable, "-c", "import sys; print(sys.argv[1])", hostile])
        if os.path.exists(sentinel):
            failures.append("shell-metacharacter argv element was interpreted (sentinel created)")
        if r.stdout.strip() != hostile:
            failures.append(f"hostile argv element was not passed through literally: {r.stdout!r}")

    # Case 5: a missing executable raises SubprocessError, not a bare OSError leak.
    try:
        run_argv(["/definitely/not/a/real/executable/path"])
        failures.append("expected SubprocessError for a missing executable, got none")
    except SubprocessError:
        pass

    # Case 6: stdout and stderr never mix into one stream.
    r = run_argv([sys.executable, "-c", "import sys; print('OUT'); print('ERR', file=sys.stderr)"])
    if "ERR" in r.stdout or "OUT" in r.stderr:
        failures.append(f"stdout/stderr channels leaked into each other: stdout={r.stdout!r} stderr={r.stderr!r}")

    if failures:
        for f in failures:
            print(f"native_exe_subprocess selftest FAIL: {f}")
        return 1

    print("native_exe_subprocess: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_subprocess: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
