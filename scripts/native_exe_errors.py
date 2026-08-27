"""Centralized error phase -> exit-class mapping (NEX-006).

Implements the diagnostic-phase table from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §18.1/§18.2. Every
failure the driver can produce belongs to exactly one named phase, and every
phase maps to exactly one process exit code — this module is the single
source of truth for that mapping (ERR-001: "failures SHALL use the phase and
exit classes in Section 18"), so no driver code should hand-roll a `sys.exit`
number.

`BuildError` is the exception later driver slices should raise to report any
non-success outcome: it carries the `DiagnosticPhase` and renders its own
`exit_code` from this table, so the mapping cannot drift out of sync between
where an error is raised and where the process actually exits.

`DiagnosticPhase.INTERRUPTED` is not one of §18.1's named phases (SIGINT is a
signal, not a diagnostic classification) but is included here because its
exit code (130) is part of the same §18.2 table and driver cancellation
handling (NEX-034) needs a single place to look it up too.

Run `python3 scripts/native_exe_errors.py --selftest` for the parameterized
per-phase corpus (NEX-006's red test).
"""

from __future__ import annotations

from enum import Enum

EXIT_SUCCESS = 0


class DiagnosticPhase(Enum):
    USAGE = "usage"
    INPUT = "input"
    CONFIG = "config"
    FRONTEND = "frontend"
    ENTRY = "entry"
    EMIT_C = "emit-c"
    RUNTIME = "runtime"
    TOOL_DISCOVERY = "tool-discovery"
    HOST_COMPILE = "host-compile"
    HOST_LINK = "host-link"
    PUBLISH = "publish"
    INTERNAL = "internal"
    INTERRUPTED = "interrupted"


# spec §18.2's exit-class table.
_PHASE_EXIT_CODES: dict[DiagnosticPhase, int] = {
    DiagnosticPhase.USAGE: 2,
    DiagnosticPhase.INPUT: 3,
    DiagnosticPhase.CONFIG: 3,
    DiagnosticPhase.FRONTEND: 4,
    DiagnosticPhase.ENTRY: 4,
    DiagnosticPhase.EMIT_C: 4,
    DiagnosticPhase.TOOL_DISCOVERY: 5,
    DiagnosticPhase.HOST_COMPILE: 6,
    DiagnosticPhase.HOST_LINK: 6,
    DiagnosticPhase.RUNTIME: 7,
    DiagnosticPhase.PUBLISH: 8,
    DiagnosticPhase.INTERNAL: 70,
    DiagnosticPhase.INTERRUPTED: 130,
}

assert set(_PHASE_EXIT_CODES) == set(DiagnosticPhase), "every DiagnosticPhase must map to an exit code"


def exit_code_for(phase: DiagnosticPhase) -> int:
    return _PHASE_EXIT_CODES[phase]


class BuildError(Exception):
    """Raised by driver code for any non-success outcome; carries its own exit code."""

    def __init__(self, phase: DiagnosticPhase, message: str) -> None:
        super().__init__(message)
        self.phase = phase
        self.message = message

    @property
    def exit_code(self) -> int:
        return exit_code_for(self.phase)

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return f"BuildError(phase={self.phase.value!r}, exit_code={self.exit_code}, message={self.message!r})"


def _selftest() -> int:
    failures: list[str] = []

    expected = {
        DiagnosticPhase.USAGE: 2,
        DiagnosticPhase.INPUT: 3,
        DiagnosticPhase.CONFIG: 3,
        DiagnosticPhase.FRONTEND: 4,
        DiagnosticPhase.ENTRY: 4,
        DiagnosticPhase.EMIT_C: 4,
        DiagnosticPhase.TOOL_DISCOVERY: 5,
        DiagnosticPhase.HOST_COMPILE: 6,
        DiagnosticPhase.HOST_LINK: 6,
        DiagnosticPhase.RUNTIME: 7,
        DiagnosticPhase.PUBLISH: 8,
        DiagnosticPhase.INTERNAL: 70,
        DiagnosticPhase.INTERRUPTED: 130,
    }

    # One parameterized case per phase (NEX-006's literal red test).
    for phase, code in expected.items():
        got = exit_code_for(phase)
        if got != code:
            failures.append(f"{phase.value}: expected exit {code}, got {got}")
        err = BuildError(phase, f"simulated {phase.value} failure")
        if err.exit_code != code:
            failures.append(f"BuildError({phase.value}).exit_code: expected {code}, got {err.exit_code}")

    # Every DiagnosticPhase member is covered — a forgotten new phase fails loudly.
    if set(expected) != set(DiagnosticPhase):
        failures.append(
            f"selftest table out of sync with DiagnosticPhase: "
            f"missing={set(DiagnosticPhase) - set(expected)} extra={set(expected) - set(DiagnosticPhase)}"
        )

    # Success is 0 and is not aliased to any failure phase's code.
    if EXIT_SUCCESS != 0:
        failures.append(f"EXIT_SUCCESS must be 0, got {EXIT_SUCCESS}")
    if EXIT_SUCCESS in expected.values():
        failures.append("EXIT_SUCCESS collides with a failure phase's exit code")

    if failures:
        for f in failures:
            print(f"native_exe_errors selftest FAIL: {f}")
        return 1

    print(f"native_exe_errors: selftest OK ({len(expected)} phases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_errors: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
