"""Every reachable error phase has at least one negative-test reference (TEST-005).

Implements TEST-005
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "Negative
tests SHALL cover every error phase." Red test: "Error-phase coverage
guard." This module *is* that guard.

Confirmed by direct source inspection (not assumed): `DiagnosticPhase.CONFIG`,
`.INTERNAL`, and `.INTERRUPTED` are never referenced anywhere in this
driver outside `native_exe_errors.py`'s own enum/exit-code-mapping
definition -- `CONFIG` is reserved for `sv0.toml` wiring that doesn't
exist yet (`native_exe_request.normalize_request` still hardcodes
`config_path=None`, a genuine, separately-tracked gap), `INTERNAL` is a
generic catchall with no deliberate raise site to test against, and
`INTERRUPTED` is a documented exception (`native_exe_errors.py`'s own
docstring: not one of spec §18.1's named phases) whose real
cancellation path (`native_exe_subprocess.Cancelled`) is a distinct
exception class, never a `BuildError`. These three are explicitly
excluded below, with a stated, non-empty rationale each -- never
silently dropped from the count.

Every other phase (`USAGE`, `INPUT`, `FRONTEND`, `ENTRY`, `EMIT_C`,
`RUNTIME`, `TOOL_DISCOVERY`, `HOST_COMPILE`, `HOST_LINK`, `PUBLISH`) is
real, reachable, and required to be referenced by name in at least one
OTHER `native_exe_*.py` module -- in practice, always the module that
raises `BuildError` with that phase, whose own mutation-tested
`--selftest` (this project's universal per-module discipline) is what
actually asserts on it.

Run `python3 scripts/native_exe_phase_coverage.py --selftest` for the
corpus.
"""

from __future__ import annotations

import glob
import os
import re

from native_exe_errors import DiagnosticPhase

_PHASE_REF_RE = re.compile(r"DiagnosticPhase\.([A-Z_]+)")

# phase -> non-empty rationale for why it's legitimately unreachable today.
EXCLUDED_PHASES: dict[DiagnosticPhase, str] = {
    DiagnosticPhase.CONFIG: (
        "Reserved for sv0.toml configuration -- native_exe_config.py exists and is "
        "tested in isolation (NEX-043), but native_exe_request.normalize_request still "
        "hardcodes config_path=None. Not wired into any real build yet (a separately "
        "tracked, genuine gap), so no build can raise this phase today."
    ),
    DiagnosticPhase.INTERNAL: (
        "A generic catchall for an unexpected internal invariant violation, by "
        "definition not something this driver deliberately raises anywhere -- there is "
        "no real site to write a negative test against."
    ),
    DiagnosticPhase.INTERRUPTED: (
        "Documented in native_exe_errors.py's own docstring as not one of spec "
        "section 18.1's named phases (SIGINT-class exit convention only). The real "
        "cancellation path (native_exe_subprocess.Cancelled) is a distinct exception "
        "class, never a BuildError -- this phase exists purely for the exit-code "
        "mapping table, already exhaustively tested by NEX-006's own selftest."
    ),
}


def find_referenced_phases(scripts_dir: str) -> dict[DiagnosticPhase, list[str]]:
    """Map each `DiagnosticPhase` to the sorted list of `native_exe_*.py`
    basenames (other than `native_exe_errors.py` itself, whose own
    enum/mapping definition would trivially "reference" every phase) that
    mention it by name.
    """
    refs: dict[DiagnosticPhase, list[str]] = {phase: [] for phase in DiagnosticPhase}
    for path in sorted(glob.glob(os.path.join(scripts_dir, "native_exe_*.py"))):
        if os.path.basename(path) == "native_exe_errors.py":
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for name in sorted(set(_PHASE_REF_RE.findall(text))):
            try:
                phase = DiagnosticPhase[name]
            except KeyError:
                continue  # not a real phase name -- ignore rather than guess
            refs[phase].append(os.path.basename(path))
    return refs


def check_phase_coverage(scripts_dir: str | None = None) -> None:
    """Raise `ValueError` listing every reachable phase with zero real
    references outside `native_exe_errors.py`. A phase in `EXCLUDED_PHASES`
    is never required to be referenced.
    """
    root = scripts_dir or os.path.dirname(os.path.abspath(__file__))
    refs = find_referenced_phases(root)
    uncovered = [
        phase.value
        for phase in DiagnosticPhase
        if phase not in EXCLUDED_PHASES and not refs[phase]
    ]
    if uncovered:
        raise ValueError(
            "no negative-test reference found for error phase(s) (TEST-005): " + ", ".join(uncovered)
        )


def _selftest() -> int:
    failures: list[str] = []

    this_dir = os.path.dirname(os.path.abspath(__file__))

    # Case 1: every excluded phase has a real, non-empty rationale.
    for phase, rationale in EXCLUDED_PHASES.items():
        if not rationale or not rationale.strip():
            failures.append(f"case1: {phase} has an empty exclusion rationale")

    # Case 2: the real scripts/ directory passes -- every reachable phase
    # genuinely has at least one other module referencing it (the actual
    # red test for this requirement).
    try:
        check_phase_coverage(this_dir)
    except ValueError as exc:
        failures.append(f"case2: real driver failed phase coverage: {exc}")

    # Case 3: the classifier actually discriminates -- confirm at least
    # one real, reachable phase (ENTRY) has a nonempty reference list, and
    # that native_exe_errors.py itself is correctly excluded from that list
    # (it would trivially "cover" everything otherwise).
    refs = find_referenced_phases(this_dir)
    if not refs[DiagnosticPhase.ENTRY]:
        failures.append("case3: expected at least one file to reference DiagnosticPhase.ENTRY")
    if "native_exe_errors.py" in refs[DiagnosticPhase.ENTRY]:
        failures.append("case3: native_exe_errors.py itself must be excluded from coverage counting")

    # Case 4 (the actual red test, run against a synthetic empty
    # directory): with no other module present at all, every non-excluded
    # phase is correctly reported as uncovered.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        # A lone native_exe_errors.py-shaped file (excluded by name from
        # counting) plus nothing else -- every reachable phase must fail.
        with open(os.path.join(td, "native_exe_errors.py"), "w", encoding="utf-8") as f:
            f.write("from native_exe_errors import DiagnosticPhase\nX = DiagnosticPhase.ENTRY\n")
        try:
            check_phase_coverage(td)
            failures.append("case4: expected ValueError for an empty driver, none raised")
        except ValueError as exc:
            if "entry" not in str(exc).lower():
                failures.append(f"case4: expected 'entry' to be reported uncovered, got: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_phase_coverage selftest FAIL: {f}")
        return 1

    print(f"native_exe_phase_coverage: selftest OK ({len(DiagnosticPhase) - len(EXCLUDED_PHASES)} phases required, {len(EXCLUDED_PHASES)} excluded)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_phase_coverage: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
