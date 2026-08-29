"""Accepted generated-C/runtime warning policy (NEX-049a).

Implements TEST-008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §26.6): before
R1's stable gate, the driver must identify (a) the warning flags common to
supported GCC/Clang versions, (b) warnings fixed in generated C/runtime,
(c) warnings suppressed narrowly with a rationale, and (d) warnings that
become errors in the stable gate. "Global warning suppression is not an
R1 completion strategy" — so this module holds two disjoint, small,
explicit lists rather than a blanket `-w`/`-Wno-everything` escape hatch.

Argv-native (per §16.6: no shell flag-string parsing) — every entry here
is exactly one argv element, used directly by `native_exe_argv_builder`
(NEX-049b/051a), never assembled from a parsed string.

Run `python3 scripts/native_exe_warning_policy.py --selftest` for the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass

# Warning flags common to supported GCC/Clang versions, enabled at the
# stable gate. Deliberately small and explicit -- §26.6 forbids treating
# "no blanket suppression" as satisfied by just not suppressing anything
# while also not actually turning anything on.
ACCEPTED_WARNING_FLAGS: list[str] = ["-Wall", "-Wextra"]


@dataclass(frozen=True)
class Suppression:
    flag: str
    rationale: str


# Warnings suppressed narrowly, each with a one-line rationale -- never a
# blanket `-w` or `-Wno-everything`. Populated from NEX-049b's real
# full-corpus warning run (never speculatively) against every fixture in
# `sv0c/test/behavior/manifest.txt`.
SUPPRESSED_WARNINGS: list[Suppression] = [
    Suppression(
        "-Wno-parentheses-equality",
        "megaTU always wraps every comparison in its own parens "
        "(`if ((e.tag == 0))`) as a uniform emission style, independent of "
        "surrounding syntax; stylistic, not a correctness signal -- "
        "observed on the majority of behavior-corpus fixtures with any "
        "conditional.",
    ),
    Suppression(
        "-Wno-unused-variable",
        "megaTU emits one C local per sv0 binding uniformly, including "
        "loop counters and match bindings that end up unused in the "
        "specific fixture's control flow (e.g. `for_count.sv0`'s `i`, "
        "`match_guard.sv0`'s `n`); a real leftover binding would be a "
        "checker-level dead-code diagnostic, not a codegen bug.",
    ),
    Suppression(
        "-Wno-unused-but-set-variable",
        "same root cause as -Wno-unused-variable -- a binding that is "
        "assigned by generated C but never subsequently read in that "
        "fixture's control flow (e.g. `let_shadow.sv0`'s shadowed `x_1`).",
    ),
    Suppression(
        "-Wno-integer-overflow",
        "overflow_wrap_mask.sv0 deliberately exercises "
        "`2147483647 + 1` at a constant-foldable site to test that "
        "INT_MAX+1 wraps to INT_MIN -- direct, additional evidence for "
        "native-executable-ub-audit.md's Site 4 finding (no documented "
        "sv0 overflow policy exists yet). This suppression reflects "
        "today's accepted behavior, not a resolved policy decision; "
        "revisit when NEX-050/051 resolve Site 4.",
    ),
    Suppression(
        "-Wno-overflow",
        "GCC's name for the exact same overflow_wrap_mask.sv0 site as "
        "-Wno-integer-overflow above (Clang's name) -- confirmed on a "
        "real Linux/GCC CI run (this project's own suite had never once "
        "reached this far in CI before KC-001/002/005 were fixed, so a "
        "GCC-only warning name was never seen until now). Same rationale "
        "as -Wno-integer-overflow exactly; not a second finding.",
    ),
    Suppression(
        "-Wno-builtin-declaration-mismatch",
        "fn_power.sv0's own recursive integer `pow(b, e)` -- a genuine, "
        "correct sv0 user function -- collides by name with GCC's "
        "implicitly-recognized libc builtin `double pow(double, double)` "
        "(recognized even with no `#include <math.h>`; Clang does not "
        "warn on this same collision, which is why it was never seen "
        "before this project's suite first ran to completion on "
        "Linux/GCC). Not a codegen defect: the emitted C is correct and "
        "the fixture's own behavior-corpus entry (exit 81) already "
        "passes on both compilers -- sv0 simply has no separate "
        "namespace from C identifiers at the emission level, so a user "
        "function sharing a name with a libc builtin will always trigger "
        "this on GCC. A real, narrow limitation worth knowing about, not "
        "a bug to fix here.",
    ),
]

# Warnings that are real, tracked correctness gaps -- deliberately NOT
# suppressed (suppressing would hide a genuine issue), but also not a
# blocking failure for this report: each entry names the gap and its
# follow-up tracking so the warning stays visible without perpetually
# failing NEX-049b's corpus-clean check on a fix that hasn't landed yet.
@dataclass(frozen=True)
class TrackedGap:
    flag: str
    rationale: str


# KC-003 (the enum-match missing-else-branch gap that used to live here as
# two entries, -Wsometimes-uninitialized/-Wmaybe-uninitialized) is FIXED,
# not just reclassified: lower_match_arms' own if/else-if chain still ends
# in an empty else (the checker's exhaustiveness guarantee is real and
# still the reason it's never taken), but the match result temp is now
# defensively zero-initialized right after its declaration
# (sv0c/lib/lowering.sv0, the match-expression lowering site) instead of
# being left genuinely uninitialized, so every path through the chain now
# assigns it a defined value. Confirmed: recompiling enum_match_payload.sv0
# and the rest of the corpus produces zero -Wsometimes-uninitialized/
# -Wmaybe-uninitialized warnings under -Wall -Wextra. Empty on purpose --
# see native_exe_warning_report.py's own selftest comment for why an empty
# TRACKED_GAPS is the successful end state here, not a dead classification
# branch.
TRACKED_GAPS: list[TrackedGap] = []


class WarningPolicyError(Exception):
    """Raised when the policy itself is malformed (empty rationale, or an
    accepted flag and a suppression flag disagreeing about the same warning).
    """


def validate_policy(
    accepted: list[str] | None = None,
    suppressed: list[Suppression] | None = None,
    tracked: list[TrackedGap] | None = None,
) -> None:
    """Confirm the accepted/suppressed/tracked lists are pairwise disjoint
    (by warning name, ignoring the `-W`/`-Wno-` prefix) and every
    suppression/tracked-gap entry carries a non-empty rationale. Raises
    `WarningPolicyError` otherwise -- called at import-adjacent validation
    time (here, and by the selftest), not silently skipped.
    """
    accepted = ACCEPTED_WARNING_FLAGS if accepted is None else accepted
    suppressed = SUPPRESSED_WARNINGS if suppressed is None else suppressed
    tracked = TRACKED_GAPS if tracked is None else tracked

    def _bare_name(flag: str) -> str:
        return flag.removeprefix("-Wno-").removeprefix("-W")

    accepted_set = {_bare_name(f) for f in accepted}
    suppressed_set = {_bare_name(s.flag) for s in suppressed}
    tracked_set = {_bare_name(t.flag) for t in tracked}

    for label_a, set_a, label_b, set_b in [
        ("accepted", accepted_set, "suppressed", suppressed_set),
        ("accepted", accepted_set, "tracked", tracked_set),
        ("suppressed", suppressed_set, "tracked", tracked_set),
    ]:
        overlap = set_a & set_b
        if overlap:
            raise WarningPolicyError(f"flag(s) both {label_a} and {label_b}: {sorted(overlap)}")

    for s in suppressed:
        if not s.rationale or not s.rationale.strip():
            raise WarningPolicyError(f"suppression {s.flag!r} has an empty rationale")

    for t in tracked:
        if not t.rationale or not t.rationale.strip():
            raise WarningPolicyError(f"tracked gap {t.flag!r} has an empty rationale")


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: the real, shipped policy validates clean.
    try:
        validate_policy()
    except WarningPolicyError as exc:
        failures.append(f"case1: shipped policy failed validation: {exc}")

    # Case 2: accepted/suppressed lists are genuinely disjoint (not just
    # coincidentally so because suppressed is currently empty).
    fake_suppressed = [Suppression("-Wall", "deliberately overlapping, for the test")]
    try:
        validate_policy(accepted=["-Wall", "-Wextra"], suppressed=fake_suppressed)
        failures.append("case2: expected WarningPolicyError for an overlapping flag, none raised")
    except WarningPolicyError:
        pass

    # Case 3: an empty-rationale suppression entry is rejected.
    bad_suppression = [Suppression("-Wno-unused-parameter", "")]
    try:
        validate_policy(accepted=["-Wall"], suppressed=bad_suppression)
        failures.append("case3: expected WarningPolicyError for an empty rationale, none raised")
    except WarningPolicyError:
        pass

    # Case 4: a whitespace-only rationale is rejected too (not just falsy-empty).
    whitespace_suppression = [Suppression("-Wno-unused-parameter", "   ")]
    try:
        validate_policy(accepted=["-Wall"], suppressed=whitespace_suppression)
        failures.append("case4: expected WarningPolicyError for a whitespace-only rationale, none raised")
    except WarningPolicyError:
        pass

    # Case 5: a well-formed, non-overlapping, rationale-bearing suppression
    # validates clean (proves the check isn't rejecting everything).
    good_suppression = [Suppression("-Wno-unused-parameter", "megaTU emitter always names every parameter")]
    try:
        validate_policy(accepted=["-Wall", "-Wextra"], suppressed=good_suppression)
    except WarningPolicyError as exc:
        failures.append(f"case5: a well-formed suppression was rejected: {exc}")

    # Case 6: an empty-rationale TRACKED gap is rejected too (same rule as
    # suppressions -- a tracked gap without a rationale is just as
    # dishonest as a suppression without one).
    bad_tracked = [TrackedGap("-Wsome-real-gap", "")]
    try:
        validate_policy(accepted=["-Wall"], tracked=bad_tracked)
        failures.append("case6: expected WarningPolicyError for an empty tracked-gap rationale, none raised")
    except WarningPolicyError:
        pass

    # Case 7: a suppression and a tracked gap on the SAME warning name is
    # rejected -- a warning is either confirmed-harmless-and-suppressed OR
    # a known-real-gap-left-visible, never both at once (that would let a
    # real gap quietly become "suppressed" under cover of a tracked entry).
    try:
        validate_policy(
            accepted=["-Wall"],
            suppressed=[Suppression("-Wno-foo", "test")],
            tracked=[TrackedGap("-Wfoo", "test")],
        )
        failures.append("case7: expected WarningPolicyError for the same warning suppressed AND tracked")
    except WarningPolicyError:
        pass

    if failures:
        for f in failures:
            print(f"native_exe_warning_policy selftest FAIL: {f}")
        return 1

    print("native_exe_warning_policy: selftest OK (7 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_warning_policy: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
