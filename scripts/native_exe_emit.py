"""Core-compiler stdout/stderr/exit protocol normalization (NEX-012).

Implements PIPE-003…005 and ERR-002
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §13.5):

  - PIPE-003: a core-compiler nonzero exit is a frontend/emission failure —
    checked *before* looking at stdout content at all, so a nonzero exit with
    partial/truncated C on stdout (a mid-emission crash) is still classified
    FRONTEND, never mistaken for a usable partial result.
  - PIPE-004: a zero exit with empty stdout is a separate failure class,
    "emitter-protocol failure" (`EMIT_C`) — the core compiler claimed success
    but produced nothing to compile.
  - PIPE-005: stdout (C) and stderr (diagnostics) stay on separate channels
    all the way through — `classify_emission` never merges them, and
    preserves stderr even on a *successful* emission (a compiler can warn on
    stderr while still emitting valid C on stdout).
  - ERR-002: existing sv0 `E####` diagnostic codes and source spans are
    preserved verbatim — `classify_emission` never rewrites, truncates, or
    summarizes stderr content; it passes it through byte-for-byte into the
    raised `BuildError`.

This module classifies an already-captured `CommandResult` (from
`native_exe_subprocess.run_argv`); it does not invoke anything itself, so it
composes cleanly with both the fake emitter (NEX-004) and, later, the real
core-compiler client (NEX-011).

Run `python3 scripts/native_exe_emit.py --selftest` for the corpus, driven
through `native_exe_fake_emitter.py`'s real §26.2 modes as actual subprocesses.
"""

from __future__ import annotations

from dataclasses import dataclass

from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_subprocess import CommandResult


@dataclass
class EmissionResult:
    c_source: str
    stderr: str  # non-fatal diagnostics/warnings, if any, even on a successful emission


def classify_emission(result: CommandResult) -> EmissionResult:
    """Classify a core-compiler CommandResult per PIPE-003…005.

    Returns an EmissionResult on success; raises BuildError(FRONTEND) for a
    nonzero exit (PIPE-003) or BuildError(EMIT_C) for a zero exit with empty
    stdout (PIPE-004). The raised message always carries the original stderr
    text unmodified (ERR-002).
    """
    if result.returncode != 0:
        message = result.stderr if result.stderr else (
            f"core compiler exited {result.returncode} with no diagnostic on stderr"
        )
        raise BuildError(DiagnosticPhase.FRONTEND, message)

    if result.stdout == "":
        message = "core compiler exited 0 but produced no C output (emitter-protocol failure)"
        if result.stderr:
            message += f"; stderr: {result.stderr}"
        raise BuildError(DiagnosticPhase.EMIT_C, message)

    return EmissionResult(c_source=result.stdout, stderr=result.stderr)


def _selftest() -> int:
    import os
    import sys

    from native_exe_subprocess import run_argv

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_emitter = os.path.join(this_dir, "native_exe_fake_emitter.py")

    def invoke(mode: str) -> CommandResult:
        env = dict(os.environ)
        env["SV0_FAKE_EMITTER_MODE"] = mode
        return run_argv([sys.executable, fake_emitter, "input.sv0"], env=env)

    # Case 1: valid emission succeeds; stderr is empty and preserved as such.
    result = classify_emission(invoke("valid"))
    if "sv0_runtime.h" not in result.c_source or result.stderr != "":
        failures.append(f"valid: c_source_ok={'sv0_runtime.h' in result.c_source} stderr={result.stderr!r}")

    # Case 2 (PIPE-004): zero exit + empty stdout is EMIT_C, not success.
    try:
        classify_emission(invoke("empty"))
        failures.append("empty: expected BuildError, emission succeeded")
    except BuildError as exc:
        if exc.phase is not DiagnosticPhase.EMIT_C:
            failures.append(f"empty: expected EMIT_C, got {exc.phase}")
        if exc.exit_code != 4:
            failures.append(f"empty: expected exit 4, got {exc.exit_code}")

    # Case 3 (PIPE-003): nonzero exit is FRONTEND even though stdout has
    # (truncated) content — exit code governs, not stdout inspection.
    try:
        classify_emission(invoke("partial"))
        failures.append("partial: expected BuildError, emission succeeded")
    except BuildError as exc:
        if exc.phase is not DiagnosticPhase.FRONTEND:
            failures.append(f"partial: expected FRONTEND despite nonempty stdout, got {exc.phase}")
        if exc.exit_code != 4:
            failures.append(f"partial: expected exit 4, got {exc.exit_code}")

    # Case 4 (PIPE-005): a warning on stderr during a *successful* emission is
    # preserved, not merged into stdout and not discarded.
    result = invoke("warn")
    emission = classify_emission(result)
    if "sv0_runtime.h" not in emission.c_source:
        failures.append("warn: c_source lost the runtime marker")
    if "warning" not in emission.stderr:
        failures.append(f"warn: stderr warning was discarded: {emission.stderr!r}")
    if "warning" in emission.c_source:
        failures.append("warn: stderr content leaked into c_source (channels merged)")

    # Case 5 (ERR-002): the diagnostic's exact text (incl. its E#### code)
    # survives unmodified into the BuildError message.
    try:
        classify_emission(invoke("diag"))
        failures.append("diag: expected BuildError, emission succeeded")
    except BuildError as exc:
        if exc.phase is not DiagnosticPhase.FRONTEND:
            failures.append(f"diag: expected FRONTEND, got {exc.phase}")
        if "error[E9999]: fake-emitter simulated frontend failure" not in exc.message:
            failures.append(f"diag: original diagnostic text not preserved verbatim: {exc.message!r}")

    if failures:
        for f in failures:
            print(f"native_exe_emit selftest FAIL: {f}")
        return 1

    print("native_exe_emit: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_emit: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
