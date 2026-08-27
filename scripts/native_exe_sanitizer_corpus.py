#!/usr/bin/env python3
"""Full behavior corpus under ASan/UBSan (NEX-050c).

Implements TEST-007
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §26.7): the
CI-job content behind NEX-050c — every row in
`sv0c/test/behavior/manifest.txt` (the full, real PASS corpus, not just
NEX-048b's dedicated stress fixtures) built and run under
`native_exe_sanitizer_build.SANITIZE_FLAGS`, asserting both the expected
exit code AND zero sanitizer stderr output. A sanitizer finding on any
ordinary corpus fixture would mean the runtime/emitter has a real bug the
unsanitized behavior-corpus run (`native_exe_behavior_corpus.py`) can't see.

Mirrors `native_exe_behavior_corpus.py`'s row-reading/loop shape exactly —
this is the sanitized sibling of that check, not a reimplementation of its
own manifest-reading logic.

Run directly (`python3 scripts/native_exe_sanitizer_corpus.py --root .`)
for the full sweep, or `--selftest` for a fast 3-row smoke subset.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from native_exe_build import build_native_executable
from native_exe_sanitizer_build import SANITIZE_FLAGS

# Fixtures already in the behavior corpus that deliberately rely on real C
# UB (native-executable-ub-audit.md's Site 4: no documented sv0 overflow
# policy exists) and are therefore EXPECTED to trip a specific UBSan
# diagnostic -- not a new bug this job discovered, but the exact,
# already-known gap NEX-048/049's audit and warning-policy work already
# surfaced. Any OTHER, unexpected sanitizer output on any fixture (this
# one included, if the diagnostic text ever changes) is still a hard
# failure; this is a narrow, substring-matched allow-list, not a blanket
# "ignore this fixture's stderr."
KNOWN_SANITIZER_FINDINGS: dict[str, str] = {
    "test/behavior/cases/overflow_wrap_mask.sv0": "signed integer overflow",
}


def _read_manifest(manifest_path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [s.strip() for s in line.split("|")]
        rel, want_s = parts[0], parts[1]
        rows.append((rel, int(want_s)))
    return rows


def run_sanitized_corpus(root: Path, rows: list[tuple[str, int]] | None = None) -> int:
    sv0c = root / "sv0c"
    manifest_path = sv0c / "test" / "behavior" / "manifest.txt"
    if rows is None:
        rows = _read_manifest(manifest_path)

    n = 0
    n_known = 0
    for rel, want in rows:
        case = sv0c / rel
        if not case.is_file():
            print(f"native_exe_sanitizer_corpus: missing case {case}", file=sys.stderr)
            return 1

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "out.bin")
            try:
                build_native_executable(
                    "file", str(case), out, td, probe=(n == 0), extra_cc_args=SANITIZE_FLAGS
                )
            except Exception as exc:  # noqa: BLE001 - report any failure, don't hide it
                print(f"native_exe_sanitizer_corpus: build failed for {rel}: {exc}", file=sys.stderr)
                return 1
            proc = subprocess.run([out], capture_output=True, text=True)
            if proc.returncode != want:
                print(
                    f"native_exe_sanitizer_corpus: {rel} exited {proc.returncode}, expected {want}",
                    file=sys.stderr,
                )
                return 1
            stderr = proc.stderr.strip()
            if stderr:
                expected_substring = KNOWN_SANITIZER_FINDINGS.get(rel)
                if expected_substring is None or expected_substring not in stderr:
                    print(
                        f"native_exe_sanitizer_corpus: {rel} produced unexpected sanitizer output:\n{proc.stderr}",
                        file=sys.stderr,
                    )
                    return 1
                n_known += 1
        n += 1

    print(
        f"native_exe_sanitizer_corpus: OK ({n} program(s), "
        f"{n_known} known/expected finding(s), 0 unexpected sanitizer findings)",
        file=sys.stderr,
    )
    return 0


def _selftest() -> int:
    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "sv0c" / "test" / "behavior" / "manifest.txt"
    all_rows = _read_manifest(manifest_path)
    if not all_rows:
        print("native_exe_sanitizer_corpus selftest FAIL: manifest has no rows", file=sys.stderr)
        return 1

    # A fast smoke subset for --selftest; the full sweep is the real CI-job
    # content (slow -- 100+ real sanitized compiles), invoked separately.
    # Deliberately includes overflow_wrap_mask.sv0 by its HARDCODED name
    # (not looked up via KNOWN_SANITIZER_FINDINGS itself) so the allow-list
    # branch is actually exercised here even if that dict were emptied by
    # a regression -- coupling the sample selection to the same data under
    # test would make a mutation of that data silently shrink the sample
    # instead of being caught.
    known_finding_rel = "test/behavior/cases/overflow_wrap_mask.sv0"
    known_finding_row = next((r for r in all_rows if r[0] == known_finding_rel), None)
    if known_finding_row is None:
        print(f"native_exe_sanitizer_corpus selftest FAIL: {known_finding_rel} missing from manifest", file=sys.stderr)
        return 1
    subset = list(all_rows[:2]) + [known_finding_row]
    return run_sanitized_corpus(root, subset)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument(
        "--selftest", action="store_true", help="Run a fast 3-row smoke subset instead of the full corpus"
    )
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    return run_sanitized_corpus(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
