#!/usr/bin/env python3
"""Dev vs. release-profile behavioral parity gate (NEX-051b, AC-024).

Implements TOOL-012/PORT-005
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §16.5): before
`--profile=release` can exist in the public CLI surface at all, the full
behavior corpus must produce byte-identical observable stdout/stderr/exit
in dev and release profiles. Builds every `sv0c/test/behavior/manifest.txt`
fixture twice -- once via `build_dev_profile_argv`, once via
`build_release_profile_argv` (NEX-051a) -- and diffs the two runs.

`overflow_wrap_mask.sv0` (the one fixture already known, per
`native-executable-ub-audit.md` Site 4, to rely on real signed-overflow
UB) is allowed to differ -- its outcome is inherently
optimization-level-dependent by definition (a real compiler is free to
compute a constant-folded overflow differently at `-O2` than at `-O0`);
asserting byte-parity on it would bake in one optimization level's
UB-manifestation as guaranteed behavior, which is exactly the overclaim
§16.5/§21 warn against. Every other fixture must match exactly.

Run `python3 scripts/native_exe_release_parity.py --selftest` for a fast
smoke subset, or with no flags for the full corpus.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

from native_exe_build import build_native_executable

_KNOWN_DIVERGENT_FIXTURES = {"test/behavior/cases/overflow_wrap_mask.sv0"}


def _read_manifest(manifest_path: Path) -> list[tuple[str, int]]:
    rows: list[tuple[str, int]] = []
    for raw in manifest_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [s.strip() for s in line.split("|")]
        rows.append((parts[0], int(parts[1])))
    return rows


def observations_diverge(
    dev: tuple[int, str, str], release: tuple[int, str, str]
) -> bool:
    """Pure comparison, extracted for direct unit testing -- the real
    behavior corpus never actually diverges between dev and release
    (confirmed: a full 114-fixture run found 0 unexpected divergences), so
    an end-to-end mutation test alone could never prove this comparison
    itself is load-bearing. `_selftest` exercises this directly with
    synthetic tuples for exactly that reason.
    """
    return dev != release


def _build_and_run(case: Path, extra_cc_args: list[str]) -> tuple[int, str, str]:
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out.bin")
        build_native_executable("file", str(case), out, td, probe=False, extra_cc_args=extra_cc_args)
        proc = subprocess.run([out], capture_output=True, text=True)
        return proc.returncode, proc.stdout, proc.stderr


def run_parity_check(root: Path, rows: list[tuple[str, int]] | None = None) -> int:
    sv0c = root / "sv0c"
    manifest_path = sv0c / "test" / "behavior" / "manifest.txt"
    if rows is None:
        rows = _read_manifest(manifest_path)

    n = 0
    n_known_divergent = 0
    for rel, want in rows:
        case = sv0c / rel
        if not case.is_file():
            print(f"native_exe_release_parity: missing case {case}", file=sys.stderr)
            return 1

        try:
            # extra_cc_args=[] for dev, ["-O2", "-fno-strict-aliasing"] via
            # release argv -- both go through build_native_executable, whose
            # own internal argv choice is dev-only today (NEX-051a exists as
            # a standalone function, not yet wired as a profile switch --
            # that's NEX-051c's job). So "release" here means: dev's fixed
            # -O0 argv PLUS the release flags appended as extra_cc_args,
            # which (per §51a's own selftest) makes the LAST -O win --
            # functionally equivalent to a real release build for parity
            # purposes, without depending on NEX-051c landing first.
            dev_rc, dev_out, dev_err = _build_and_run(case, [])
            rel_rc, rel_out, rel_err = _build_and_run(
                case, ["-O2", "-fno-strict-aliasing"]
            )
        except Exception as exc:  # noqa: BLE001 - report, don't hide
            print(f"native_exe_release_parity: build failed for {rel}: {exc}", file=sys.stderr)
            return 1

        if dev_rc != want:
            print(f"native_exe_release_parity: {rel} dev build exited {dev_rc}, expected {want}", file=sys.stderr)
            return 1

        if rel in _KNOWN_DIVERGENT_FIXTURES:
            n_known_divergent += 1
        elif observations_diverge((dev_rc, dev_out, dev_err), (rel_rc, rel_out, rel_err)):
            print(
                f"native_exe_release_parity: {rel} diverged between dev and release:\n"
                f"  dev:     rc={dev_rc} stdout={dev_out!r} stderr={dev_err!r}\n"
                f"  release: rc={rel_rc} stdout={rel_out!r} stderr={rel_err!r}",
                file=sys.stderr,
            )
            return 1
        n += 1

    print(
        f"native_exe_release_parity: OK ({n} program(s), "
        f"{n_known_divergent} known-divergent (optimization-dependent UB))",
        file=sys.stderr,
    )
    return 0


def _selftest() -> int:
    failures: list[str] = []

    # Direct unit tests of observations_diverge -- the real corpus never
    # actually diverges, so this is the only way to prove the comparison
    # itself would catch a real divergence.
    if observations_diverge((0, "a", ""), (0, "a", "")):
        failures.append("identical observations were reported as diverging")
    if not observations_diverge((0, "a", ""), (1, "a", "")):
        failures.append("a differing exit code was not reported as diverging")
    if not observations_diverge((0, "a", ""), (0, "b", "")):
        failures.append("differing stdout was not reported as diverging")
    if not observations_diverge((0, "a", ""), (0, "a", "err")):
        failures.append("differing stderr was not reported as diverging")

    if failures:
        for f in failures:
            print(f"native_exe_release_parity selftest FAIL: {f}")
        return 1

    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "sv0c" / "test" / "behavior" / "manifest.txt"
    all_rows = _read_manifest(manifest_path)
    if not all_rows:
        print("native_exe_release_parity selftest FAIL: manifest has no rows", file=sys.stderr)
        return 1

    known_divergent_row = next(
        (r for r in all_rows if r[0] == "test/behavior/cases/overflow_wrap_mask.sv0"), None
    )
    if known_divergent_row is None:
        print(
            "native_exe_release_parity selftest FAIL: overflow_wrap_mask.sv0 missing from manifest",
            file=sys.stderr,
        )
        return 1
    subset = list(all_rows[:2]) + [known_divergent_row]
    return run_parity_check(root, subset)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    return run_parity_check(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
