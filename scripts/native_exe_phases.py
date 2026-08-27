"""Build-state phase machine for the sv0c native runtime executable driver (NEX-003).

Implements the atomic-publication state machine from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §12.5:

    ABSENT -> EMITTING_C -> C_READY -> HOST_COMPILING -> TEMP_EXECUTABLE_READY
           -> VALIDATED -> PUBLISHED

    Any failure before PUBLISHED:
      -> FAILED -> cleanup scratch -> leave prior final output unchanged

PIPE-001 requires this order be preserved; this module makes an out-of-order
transition (skipping a phase, going backward, or continuing after a terminal
phase) an immediate `PhaseError` instead of a possibility silently reached by
driver code later. `PUBLISHED` and `FAILED` are terminal — nothing may follow
either.

Run `python3 scripts/native_exe_phases.py --selftest` for the phase-order
event-snapshot corpus (NEX-003's red test).
"""

from __future__ import annotations

from enum import Enum


class Phase(Enum):
    ABSENT = "ABSENT"
    EMITTING_C = "EMITTING_C"
    C_READY = "C_READY"
    HOST_COMPILING = "HOST_COMPILING"
    TEMP_EXECUTABLE_READY = "TEMP_EXECUTABLE_READY"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


# The only forward path through a successful build (spec §12.5).
LINEAR_ORDER: list[Phase] = [
    Phase.ABSENT,
    Phase.EMITTING_C,
    Phase.C_READY,
    Phase.HOST_COMPILING,
    Phase.TEMP_EXECUTABLE_READY,
    Phase.VALIDATED,
    Phase.PUBLISHED,
]

TERMINAL_PHASES = {Phase.PUBLISHED, Phase.FAILED}


class PhaseError(Exception):
    """Raised on any transition that would violate the spec §12.5 state machine."""


class PhaseSequencer:
    """Tracks one build's phase transitions and enforces the spec's ordering.

    `events` is the exact recorded sequence of phases reached, in order — the
    thing NEX-003's "phase-order event snapshot" test compares against a
    known-good list. Any driver code (fake or real) should route every phase
    change through `advance` rather than setting phase state directly, so the
    ordering guarantee holds regardless of how the phase was reached.
    """

    def __init__(self) -> None:
        self.current: Phase = Phase.ABSENT
        self.events: list[Phase] = [Phase.ABSENT]

    def advance(self, to: Phase) -> None:
        if self.current in TERMINAL_PHASES:
            raise PhaseError(
                f"cannot transition out of terminal phase {self.current.value} "
                f"(attempted -> {to.value})"
            )

        if to == Phase.FAILED:
            self.current = Phase.FAILED
            self.events.append(Phase.FAILED)
            return

        if to not in LINEAR_ORDER:
            raise PhaseError(f"{to.value} is not a valid target phase")

        cur_idx = LINEAR_ORDER.index(self.current)
        to_idx = LINEAR_ORDER.index(to)
        if to_idx != cur_idx + 1:
            raise PhaseError(
                f"invalid transition {self.current.value} -> {to.value}: "
                "phases advance exactly one linear step at a time toward "
                "PUBLISHED, or transition to FAILED from any non-terminal phase"
            )

        self.current = to
        self.events.append(to)


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: the full happy path produces the exact expected event snapshot.
    seq = PhaseSequencer()
    for phase in LINEAR_ORDER[1:]:
        seq.advance(phase)
    if seq.events != LINEAR_ORDER:
        failures.append(f"happy-path snapshot mismatch: {seq.events} != {LINEAR_ORDER}")
    if seq.current is not Phase.PUBLISHED:
        failures.append(f"expected terminal PUBLISHED, got {seq.current}")

    # Case 2: skipping a phase (ABSENT -> C_READY directly) is rejected.
    seq = PhaseSequencer()
    try:
        seq.advance(Phase.C_READY)
        failures.append("expected PhaseError skipping EMITTING_C, got none")
    except PhaseError:
        pass

    # Case 3: going backward is rejected.
    seq = PhaseSequencer()
    seq.advance(Phase.EMITTING_C)
    seq.advance(Phase.C_READY)
    try:
        seq.advance(Phase.EMITTING_C)
        failures.append("expected PhaseError going backward, got none")
    except PhaseError:
        pass

    # Case 4: FAILED is reachable from any non-terminal phase, and is itself terminal.
    for start in LINEAR_ORDER[:-1]:  # every non-terminal phase, incl. ABSENT
        seq = PhaseSequencer()
        idx = LINEAR_ORDER.index(start)
        for phase in LINEAR_ORDER[1 : idx + 1]:
            seq.advance(phase)
        seq.advance(Phase.FAILED)
        if seq.events[-1] is not Phase.FAILED:
            failures.append(f"FAILED not recorded from {start.value}")
        try:
            seq.advance(Phase.EMITTING_C)
            failures.append(f"expected PhaseError continuing after FAILED (from {start.value})")
        except PhaseError:
            pass

    # Case 5: PUBLISHED is terminal — nothing follows, not even FAILED.
    seq = PhaseSequencer()
    for phase in LINEAR_ORDER[1:]:
        seq.advance(phase)
    try:
        seq.advance(Phase.FAILED)
        failures.append("expected PhaseError transitioning out of PUBLISHED")
    except PhaseError:
        pass

    if failures:
        for f in failures:
            print(f"native_exe_phases selftest FAIL: {f}")
        return 1

    print("native_exe_phases: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_phases: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
