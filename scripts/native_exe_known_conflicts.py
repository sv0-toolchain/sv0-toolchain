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
            "RESOLVED. Native self-host run of lib/checker.sv0 used to exit 232, "
            "root-caused during NEX-055c: checker.sv0's own internal test aggregator "
            "(fn main()) returned 230+r22, where r22 came from test_infer_lit() -- an "
            "entirely unrelated literal-type-inference test, failing with return code "
            "2. The real bug: infer_lit's lit_tag->type mapping was reassigned at some "
            "point (see infer_lit's own BUGS.md #5 comment -- bool literals moved from "
            "lit_tag 1 to lit_tag 5 once float literals correctly claimed tag 1), but "
            "test_infer_lit()'s assertions were never updated to match, so it asserted "
            "the OLD, now-wrong mapping. A second, independent test exercising the exact "
            "same stale mapping through a different path was found in the same pass: "
            "test_synth_expr()'s r1 case pushed a literal expr with lit_tag=1 expecting "
            "TY_BOOL() (synth_expr's ExprLit case passes ed1[idx] straight to "
            "infer_lit()), asserting the same broken mapping. Fixed both: "
            "test_infer_lit() now asserts infer_lit(1)==TY_FLOAT() and adds the missing "
            "infer_lit(5)==TY_BOOL() case; test_synth_expr()'s r1 literal now pushes "
            "lit_tag=5 (the real bool tag). Verified: lib/checker.sv0 compiles+runs to "
            "exit 0 standalone; stage0 golden + vm-parity .sv0b goldens refreshed and "
            "confirmed deterministic (captured twice, byte-identical); full "
            "./scripts/sv0 test now proceeds past checker.sv0 in the self-host loop. "
            "This also resolves the cascading symptom it caused: the self-host loop no "
            "longer aborts at checker.sv0 before reaching later modules. (It went on "
            "to reach -- and stop at -- the next pre-existing issue in that same "
            "sequence, KC-002; that was fixed in the same pass, see its own entry.)"
        ),
        "severity": "non-blocking",
        "status": "resolved",
    },
    {
        "id": "KC-002",
        "area": "self-host-sv0-loop",
        "description": (
            "RESOLVED. Native self-host run of lib/parser.sv0 used to exit 197 -- "
            "same class as KC-001: a hand-rolled unit-test fixture holding a stale "
            "literal token tag, never updated after a real production fix landed. "
            "Root-caused via the same debug-print technique used for KC-001 (a "
            "temporary build printing the aggregator's own return value, then "
            "bisecting the failing sub-test's own literals): test_parse_assign()'s "
            "tags2/tags3 fixtures (testing `x.y = 1;` / `x.y += 1;`) pushed literal "
            "tag 15 for the '.' in the field-assignment target, but tag 15 is "
            "COLONCOLON ('::', a path separator) -- tag 16 is the real TK_DOT. The "
            "production fix that corrected this exact confusion had already landed "
            "in parse_assign_target_op_pos (see its own in-repo comment, from "
            "BUGS.md #6 / sv0-mathlib) checking `== 16`, but the test fixtures using "
            "the old, wrong tag 15 were never updated to match, so parse_expr "
            "correctly rejected the resulting (invalid) '::' syntax and returned -1 "
            "where the test expected 8. Fixed both fixtures to push tag 16. "
            "Verified: lib/parser.sv0 compiles+runs to exit 0 standalone (was 197); "
            "stage0 golden (parser.c) + vm-parity golden (parser.sv0b) refreshed and "
            "confirmed deterministic; with KC-001 already fixed, the self-host loop "
            "is now fully green (99/99 files; emit+cc+run OK; behavioral parity with "
            "SML) for the first time this whole project has observed it."
        ),
        "severity": "non-blocking",
        "status": "resolved",
    },
    {
        "id": "KC-003",
        "area": "match-codegen",
        "description": (
            "RESOLVED. Every enum `match` used to lower to an if/else-if chain with an "
            "EMPTY final else branch, so the result temp was provably uninitialized on "
            "any tag Clang couldn't prove exhaustive (-Wsometimes-uninitialized, 16 "
            "occurrences across the behavior corpus, confirmed via generated-C "
            "inspection during NEX-049a; GCC's own name for the same gap, "
            "-Wmaybe-uninitialized, surfaced separately once this project's suite "
            "first ran to completion on Linux). Fixed in the post-native-exe cleanup "
            "pass: sv0c/lib/lowering.sv0's match-expression lowering site now emits a "
            "defensive `out = 0;` store immediately after the result temp's "
            "declaration, before the if/else-if chain runs -- the chain's own empty "
            "final else branch is unchanged (the checker's exhaustiveness guarantee is "
            "real and still the reason it's never taken at runtime), but every path "
            "through the chain now assigns the temp a defined value, eliminating the "
            "UB Clang/GCC were correctly flagging. Verified: recompiling "
            "enum_match_payload.sv0 and the rest of the behavior corpus produces zero "
            "-Wsometimes-uninitialized/-Wmaybe-uninitialized warnings; the full "
            "behavior corpus (114 programs) still passes with identical exit codes. "
            "native_exe_warning_policy.py's TRACKED_GAPS entries for this removed "
            "(not reclassified -- the underlying gap is gone)."
        ),
        "severity": "mitigated",
        "status": "resolved",
    },
    {
        "id": "KC-004",
        "area": "strict-aliasing",
        "description": (
            "Two genuine C strict-aliasing violations, confirmed by direct source audit "
            "(native-executable-ub-audit.md, NEX-048a): Site 1, the box-pool pointer-cast "
            "deref in sv0__box_deref_raw; Site 2, a cross-reinterpretation between "
            "lowering.sv0::Value and codegen.sv0::Value's layout-compatible-but-nominally-"
            "distinct C structs. Site 1 FIXED for real (cleanup pass, post-R1): confirmed "
            "by direct reading of every emission site (megaTU-main.sv0's Call codegen) that "
            "the macro's expansion is used strictly as an rvalue -- `T dst = "
            "sv0__box_deref_raw(h, T);`, never an assignment target -- so it was safely "
            "rewritten as a statement expression that memcpy's the pool bytes into a "
            "same-typed local (well-defined regardless of strict-aliasing, mirroring "
            "sv0__box_new_raw's existing pattern), instead of a pointer-cast-and-deref. "
            "Verified: sv0c's own 308/308 unit tests pass; the full 114-program native "
            "behavior corpus passes unmodified; the emitted mega-TU C compiles clean under "
            "`-O2 -Wstrict-aliasing=2` with NO -fno-strict-aliasing at all (no aliasing "
            "diagnostic emitted, confirming the violation is actually gone, not just "
            "silenced). Site 2 remains genuinely unfixed -- a harder, cross-module "
            "type-sharing problem the audit doc itself scopes out of R1 -- and stays "
            "mitigated via -fno-strict-aliasing in the release-profile argv (kept for "
            "Site 2's sake alone now, not Site 1's)."
        ),
        "severity": "mitigated",
        "status": "open",
    },
    {
        "id": "KC-005",
        "area": "self-host-sv0-loop",
        "description": (
            "RESOLVED. Fixing KC-001 and KC-002 unmasked this: the self-host loop's "
            "bootstrap-build step compiles every file in bootstrap-sources.list to VM "
            "bytecode, including lib/driver.sv0 -- a step that had NEVER once succeeded "
            "in this project's history, since KC-001 (then KC-002) always aborted the "
            "loop before it got that far. With both fixed, the loop finally reached "
            "driver.sv0's own VM-bytecode compilation for the first time and failed "
            "there: `sv0c error: vm: unknown function 'sv0_getenv'`. Root cause: "
            "NEX-055c/REL-004 added a getenv(\"SV0_DRV_REQUEST\") call to driver.sv0's "
            "own fn main(); the C backend (megaTU-main.sv0) knows how to emit that call, "
            "but the SML-side VM bytecode compiler (vm_codegen.sml) has no case for it "
            "at all -- a touch point never in scope for getenv, since nothing had ever "
            "needed to VM-compile a getenv-calling file before. Resolved by excluding "
            "lib/driver.sv0 from VM targeting (bootstrap-sources.list, "
            "test/vm-parity/manifest.txt, test/vm-parity/tier2-manifest.txt) rather than "
            "adding getenv support to vm_codegen.sml: driver.sv0 is a native-only CLI "
            "entry point/test harness, not compiler-pipeline logic -- there is no real "
            "host-environment concept on the VM, and no VM program has any actual use "
            "for getenv. Verified: ./scripts/sv0 test passes completely clean (exit 0); "
            "bootstrap-build, vm-parity SML goldens (97/97), stage0 golden (22/22), and "
            "self-host-sv0-loop (99/99) all green; the optional tier-2 leg also green "
            "(17/17, previously always failed on driver.sv0)."
        ),
        "severity": "non-blocking",
        "status": "resolved",
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
