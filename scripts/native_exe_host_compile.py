"""Host compile/link failure diagnostics + output validation (NEX-025).

Implements TOOL-009…010/ERR-003…004
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §18.4, §16.4):
composes existing pieces rather than reimplementing them — a nonzero `cc`
exit raises `BuildError(HOST_COMPILE, ...)` with the original stderr carried
verbatim (never relabeled as an sv0 semantic error, ERR-003; never
suppressed, ERR-004); a zero exit still routes through
`native_exe_publish.validate_temp_output` (already `HOST_LINK`-classified,
from NEX-007), so a compiler that exits 0 without producing usable output is
still a failure (TOOL-010) — the *classification* differs (`HOST_COMPILE` vs
`HOST_LINK`) but both map to the same exit code (6) per spec §18.2, so this
is a labeling distinction, not a behavioral one.

Run `python3 scripts/native_exe_host_compile.py --selftest` for the corpus.
"""

from __future__ import annotations

from typing import Mapping

from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_publish import validate_temp_output
from native_exe_subprocess import SubprocessError, run_argv


def run_host_compile(argv: list[str], env: Mapping[str, str], tmp_output_path: str) -> None:
    """Run the host compiler and validate its result. Returns on success;
    raises BuildError(HOST_COMPILE) for a nonzero exit (stderr carried
    verbatim), or lets `validate_temp_output`'s BuildError(HOST_LINK)
    propagate for a zero-exit compiler that didn't produce usable output.
    """
    try:
        result = run_argv(list(argv), env=dict(env))
    except SubprocessError as exc:
        raise BuildError(DiagnosticPhase.HOST_COMPILE, f"failed to invoke host compiler: {exc}") from exc

    if result.returncode != 0:
        message = result.stderr if result.stderr else (
            f"host compiler exited {result.returncode} with no diagnostic on stderr"
        )
        raise BuildError(DiagnosticPhase.HOST_COMPILE, message)

    validate_temp_output(tmp_output_path)


def _selftest() -> int:
    import os
    import sys
    import tempfile

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")

    def invoke(mode: str, tmp_out: str):
        env = dict(os.environ)
        env["SV0_FAKE_CC_MODE"] = mode
        return run_host_compile([fake_cc, "program.c", "-o", tmp_out], env, tmp_out)

    # Case 1: happy path returns cleanly.
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "program.tmp-exe")
        try:
            invoke("valid", tmp_out)
        except BuildError as exc:
            failures.append(f"valid: unexpected BuildError: {exc}")

    # Case 2 (ERR-003/004): a nonzero exit is HOST_COMPILE, stderr preserved verbatim.
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "program.tmp-exe")
        try:
            invoke("fail", tmp_out)
            failures.append("fail: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.HOST_COMPILE:
                failures.append(f"fail: expected HOST_COMPILE, got {exc.phase}")
            if exc.exit_code != 6:
                failures.append(f"fail: expected exit 6, got {exc.exit_code}")
            if "simulated compile failure, line 1" not in exc.message:
                failures.append(f"fail: original stderr not preserved verbatim: {exc.message!r}")

    # Case 3 (TOOL-010): a zero exit with no output is still a failure (HOST_LINK, via validate_temp_output).
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "program.tmp-exe")
        try:
            invoke("zero-no-output", tmp_out)
            failures.append("zero-no-output: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.HOST_LINK:
                failures.append(f"zero-no-output: expected HOST_LINK, got {exc.phase}")
            if exc.exit_code != 6:
                failures.append(f"zero-no-output: expected exit 6, got {exc.exit_code}")

    # Case 4: a missing host compiler executable is a clean HOST_COMPILE error.
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "program.tmp-exe")
        try:
            run_host_compile([os.path.join(td, "does-not-exist")], os.environ, tmp_out)
            failures.append("missing compiler: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.HOST_COMPILE:
                failures.append(f"missing compiler: expected HOST_COMPILE, got {exc.phase}")

    if failures:
        for f in failures:
            print(f"native_exe_host_compile selftest FAIL: {f}")
        return 1

    print("native_exe_host_compile: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_host_compile: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
