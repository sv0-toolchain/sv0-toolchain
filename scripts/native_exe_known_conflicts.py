"""Known spec/compiler/runtime conflict registry (GOV-007).

Implements GOV-007
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "Conflicts
among language spec, compiler, and runtime SHALL be tracked and shall
block affected release claims." Red test: "Issue/waiver audit."

This project has real, known conflicts of exactly this kind, discovered
over the course of this work and previously only recorded informally in
commit messages and session memory -- never as a durable, in-repo
registry a release process could actually consult. This module is that
registry: a small, argv-native data structure (matching
`native_exe_warning_policy.py`'s own precedent for "small data module,
not a shell flag string") plus `check_no_blocking_conflicts`, wired into
`native_exe_release_evidence.assemble_release_evidence` as a real gate --
a `severity: "blocking"` conflict with `status: "open"` genuinely blocks
release-evidence assembly, giving this requirement real teeth rather than
being a static list nobody consults.

Run `python3 scripts/native_exe_known_conflicts.py --selftest` for the
corpus.
"""

from __future__ import annotations

_VALID_SEVERITIES = {"blocking", "non-blocking", "mitigated"}
_VALID_STATUSES = {"open", "resolved"}

KNOWN_CONFLICTS = [
    {
        "id": "KC-001",
        "area": "self-host-sv0-loop",
        "description": (
            "Native self-host run of lib/checker.sv0 exits 232. Pre-existing and "
            "confirmed unrelated to native-executable driver work: reproduced "
            "identically on a git-stash'd clean tree before NEX-016's megaTU-main.sv0 "
            "change, and observed consistently across multiple unrelated sessions."
        ),
        "severity": "non-blocking",
        "status": "open",
    },
    {
        "id": "KC-002",
        "area": "self-host-sv0-loop",
        "description": (
            "Native self-host run of lib/parser.sv0 exits 197. Same class as KC-001: "
            "pre-existing, confirmed unrelated to native-executable driver work by the "
            "same clean-tree reproduction method."
        ),
        "severity": "non-blocking",
        "status": "open",
    },
    {
        "id": "KC-003",
        "area": "match-codegen",
        "description": (
            "Every enum `match` lowers to an if/else-if chain with an EMPTY final else "
            "branch, so the result temp is provably uninitialized on any tag Clang can't "
            "prove exhaustive (-Wsometimes-uninitialized, 16 occurrences across the "
            "behavior corpus, confirmed via generated-C inspection during NEX-049a). "
            "Currently unreachable at runtime only because sv0's own checker enforces "
            "match exhaustiveness ahead of codegen -- a real, latent correctness gap, "
            "not yet fixed (filed as a follow-up task, not this registry's job to fix)."
        ),
        "severity": "mitigated",
        "status": "open",
    },
    {
        "id": "KC-004",
        "area": "strict-aliasing",
        "description": (
            "Two genuine C strict-aliasing violations, confirmed by direct source audit "
            "(native-executable-ub-audit.md, NEX-048a): the box-pool pointer-cast deref in "
            "sv0__box_deref_raw, and a cross-reinterpretation between lowering.sv0::Value "
            "and codegen.sv0::Value's layout-compatible-but-nominally-distinct C structs. "
            "Mitigated via -fno-strict-aliasing in the release-profile argv, not fixed at "
            "the representation level."
        ),
        "severity": "mitigated",
        "status": "open",
    },
]


class BlockingConflictError(Exception):
    """Raised when an open, `severity: "blocking"` conflict exists -- a
    release claim SHALL NOT proceed while one is open (GOV-007)."""


def validate_known_conflicts(conflicts: list[dict]) -> None:
    """Raise `ValueError` if `conflicts` is malformed: every entry needs a
    non-empty `id`/`area`/`description`, a `severity` in
    `{"blocking", "non-blocking", "mitigated"}`, a `status` in
    `{"open", "resolved"}`, and no duplicate `id`.
    """
    seen_ids: set[str] = set()
    for entry in conflicts:
        for key in ("id", "area", "description"):
            if not entry.get(key):
                raise ValueError(f"known-conflict entry missing/empty {key!r}: {entry!r}")
        if entry["id"] in seen_ids:
            raise ValueError(f"known-conflict registry has a duplicate id: {entry['id']!r}")
        seen_ids.add(entry["id"])
        if entry.get("severity") not in _VALID_SEVERITIES:
            raise ValueError(f"{entry['id']}: invalid severity {entry.get('severity')!r}")
        if entry.get("status") not in _VALID_STATUSES:
            raise ValueError(f"{entry['id']}: invalid status {entry.get('status')!r}")


def check_no_blocking_conflicts(conflicts: list[dict] = KNOWN_CONFLICTS) -> None:
    """Raise `BlockingConflictError` if any entry is `severity: "blocking"`
    and `status: "open"` -- the actual enforcement GOV-007 asks for
    ("SHALL block affected release claims"), not just a static list.
    """
    blocking = [c for c in conflicts if c["severity"] == "blocking" and c["status"] == "open"]
    if blocking:
        ids = ", ".join(c["id"] for c in blocking)
        raise BlockingConflictError(
            f"open blocking conflict(s) in the known-conflict registry, release claims "
            f"SHALL NOT proceed (GOV-007): {ids}"
        )


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: the real, shipped registry is well-formed.
    try:
        validate_known_conflicts(KNOWN_CONFLICTS)
    except ValueError as exc:
        failures.append(f"case1: the real registry failed validation: {exc}")

    # Case 2: the real registry has no open blocking conflict today (all
    # four known entries are non-blocking/mitigated) -- release evidence
    # assembly should not be gated right now.
    try:
        check_no_blocking_conflicts()
    except BlockingConflictError as exc:
        failures.append(f"case2: the real registry unexpectedly blocked: {exc}")

    # Case 3: an open, blocking conflict genuinely blocks (the actual red
    # test -- this requirement has to have real teeth).
    synthetic = [{"id": "KC-999", "area": "x", "description": "y", "severity": "blocking", "status": "open"}]
    try:
        check_no_blocking_conflicts(synthetic)
        failures.append("case3: expected BlockingConflictError, none raised")
    except BlockingConflictError:
        pass

    # Case 4: a RESOLVED blocking conflict does not block (status matters,
    # not just severity).
    resolved = [{"id": "KC-998", "area": "x", "description": "y", "severity": "blocking", "status": "resolved"}]
    try:
        check_no_blocking_conflicts(resolved)
    except BlockingConflictError as exc:
        failures.append(f"case4: a resolved conflict should not block: {exc}")

    # Case 5: a duplicate id is rejected.
    try:
        validate_known_conflicts(
            [
                {"id": "KC-1", "area": "a", "description": "b", "severity": "mitigated", "status": "open"},
                {"id": "KC-1", "area": "c", "description": "d", "severity": "mitigated", "status": "open"},
            ]
        )
        failures.append("case5: expected ValueError for a duplicate id, none raised")
    except ValueError:
        pass

    # Case 6: an invalid severity is rejected.
    try:
        validate_known_conflicts([{"id": "KC-2", "area": "a", "description": "b", "severity": "urgent", "status": "open"}])
        failures.append("case6: expected ValueError for an invalid severity, none raised")
    except ValueError:
        pass

    if failures:
        for f in failures:
            print(f"native_exe_known_conflicts selftest FAIL: {f}")
        return 1

    print("native_exe_known_conflicts: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_known_conflicts: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
