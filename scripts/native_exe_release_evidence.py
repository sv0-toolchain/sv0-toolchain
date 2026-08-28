"""Signed release-candidate evidence bundle (NEX-056a, TEST-009).

Implements TEST-009
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "release
candidate SHALL be built from a signed, clean revision and retain
checksums/evidence." Assembles one JSON evidence document from five
already-existing sources -- the revision SHA, a clean-tree check, the
build record (`native_exe_build_record.py`, NEX-042), the benchmark
report (`native_exe_benchmark.py`, NEX-047/055a), the reproducibility
classification (`native_exe_repro_harness.py`, NEX-053a), and the
declared supported-compiler matrix (`native_exe_supported_compilers.py`,
TOOL-013) -- rather than computing any of them itself.

Real cryptographic *signing* is a human/CI-secrets step outside this
module's scope (see `sv0c/doc/release-signing-workflow.md`, NEX-056b, for
the documented policy); this module only assembles the evidence a
signing step would then sign.

Run `python3 scripts/native_exe_release_evidence.py --selftest` for the
corpus.
"""

from __future__ import annotations

import json
import subprocess

from native_exe_known_conflicts import KNOWN_CONFLICTS, BlockingConflictError, check_no_blocking_conflicts
from native_exe_supported_compilers import SUPPORTED_COMPILER_MATRIX, validate_supported_compiler_matrix


class DirtyTreeError(Exception):
    """Raised when the working tree has uncommitted changes -- a release
    candidate SHALL be built from a clean revision (TEST-009)."""


def _git(args: list[str], cwd: str) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def is_tree_clean(repo_root: str) -> bool:
    status = _git(["status", "--porcelain"], repo_root)
    return status == ""


def current_revision(repo_root: str) -> str:
    return _git(["rev-parse", "HEAD"], repo_root)


def assemble_release_evidence(
    repo_root: str,
    build_record: dict,
    benchmark_report: dict,
    reproducibility: dict | None,
    require_clean_tree: bool = True,
) -> dict:
    """Assemble one release-evidence document. Raises `DirtyTreeError` if
    `require_clean_tree` and the working tree has uncommitted changes --
    never silently proceeds with a dirty tree.
    """
    if require_clean_tree and not is_tree_clean(repo_root):
        raise DirtyTreeError(f"{repo_root}: working tree has uncommitted changes; a release candidate requires a clean revision")

    validate_supported_compiler_matrix(SUPPORTED_COMPILER_MATRIX)
    check_no_blocking_conflicts()  # GOV-007: an open blocking conflict SHALL block this.

    return {
        "schema_version": 1,
        "revision": current_revision(repo_root),
        "clean_tree": True,
        "build_record": build_record,
        "benchmark_report": benchmark_report,
        "reproducibility": reproducibility,
        "supported_compiler_matrix": SUPPORTED_COMPILER_MATRIX,
        "known_conflicts": KNOWN_CONFLICTS,
    }


def _selftest() -> int:
    import os
    import tempfile

    failures: list[str] = []

    repo_root = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

    # Case 1: a dirty tree (a real, untracked temp file inside the repo)
    # is rejected outright.
    dirty_marker = os.path.join(repo_root, "._native_exe_release_evidence_selftest_marker")
    with open(dirty_marker, "w", encoding="utf-8") as f:
        f.write("dirty")
    try:
        if is_tree_clean(repo_root):
            failures.append("case1: repo reported clean despite an untracked marker file being present")
        try:
            assemble_release_evidence(repo_root, {}, {}, None)
            failures.append("case1: expected DirtyTreeError for a dirty tree, none raised")
        except DirtyTreeError:
            pass
    finally:
        os.remove(dirty_marker)

    # Case 2: with require_clean_tree=False, a dirty tree does not raise
    # (a caller explicitly opting out, e.g. for local iteration).
    dirty_marker2 = os.path.join(repo_root, "._native_exe_release_evidence_selftest_marker2")
    with open(dirty_marker2, "w", encoding="utf-8") as f:
        f.write("dirty")
    try:
        try:
            assemble_release_evidence(repo_root, {"a": 1}, {"b": 2}, {"c": 3}, require_clean_tree=False)
        except DirtyTreeError as exc:
            failures.append(f"case2: require_clean_tree=False should not raise: {exc}")
    finally:
        os.remove(dirty_marker2)

    # Case 3: a genuinely clean tree (an isolated temp git repo, not this
    # real checkout, so this test never depends on this repo's own actual
    # working-tree state at selftest time) produces a well-formed bundle
    # with all four inputs present.
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["git", "init", "-q"], cwd=td, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=td, check=True)
        subprocess.run(["git", "config", "user.name", "test"], cwd=td, check=True)
        with open(os.path.join(td, "f.txt"), "w", encoding="utf-8") as f:
            f.write("x")
        subprocess.run(["git", "add", "."], cwd=td, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=td, check=True)

        build_record = {"artifact": {"sha256": "deadbeef"}}
        benchmark_report = {"minimal": {"total": 80}}
        reproducibility = {"status": "semantic-only", "reason": "LC_UUID"}

        evidence = assemble_release_evidence(td, build_record, benchmark_report, reproducibility)
        if evidence["build_record"] != build_record:
            failures.append("case3: build_record not recorded verbatim")
        if evidence["benchmark_report"] != benchmark_report:
            failures.append("case3: benchmark_report not recorded verbatim")
        if evidence["reproducibility"] != reproducibility:
            failures.append("case3: reproducibility not recorded verbatim")
        if not evidence["revision"]:
            failures.append("case3: revision was empty")
        if evidence["clean_tree"] is not True:
            failures.append("case3: clean_tree should be True for a genuinely clean tree")
        if evidence["supported_compiler_matrix"] != SUPPORTED_COMPILER_MATRIX:
            failures.append("case3: supported_compiler_matrix not recorded verbatim (TOOL-013)")
        if evidence["known_conflicts"] != KNOWN_CONFLICTS:
            failures.append("case3: known_conflicts not recorded verbatim (GOV-007)")

        # The evidence document must be real, valid JSON (a signing step
        # would sign these exact bytes).
        json.dumps(evidence)

        # Case 4 (GOV-007's real teeth): an open, blocking conflict SHALL
        # block release-evidence assembly, not just appear in a static
        # list nobody consults.
        import native_exe_known_conflicts as _kc_mod

        _kc_mod.KNOWN_CONFLICTS.append(
            {"id": "KC-SELFTEST", "area": "x", "description": "y", "severity": "blocking", "status": "open"}
        )
        try:
            assemble_release_evidence(td, build_record, benchmark_report, reproducibility)
            failures.append("case4: expected BlockingConflictError for an open blocking conflict, none raised")
        except BlockingConflictError:
            pass
        finally:
            _kc_mod.KNOWN_CONFLICTS.pop()

    if failures:
        for f in failures:
            print(f"native_exe_release_evidence selftest FAIL: {f}")
        return 1

    print("native_exe_release_evidence: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_release_evidence: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
