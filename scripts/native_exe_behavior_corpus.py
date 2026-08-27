#!/usr/bin/env python3
"""Native-executable behavior corpus, driven through our own driver (NEX-028).

Implements TEST-004
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "native
executable corpus SHALL cover every current behavior manifest row supported
by the C backend." `scripts/verify_behavior_corpus_native.py` already proves
every row in `sv0c/test/behavior/manifest.txt` compiles+links+runs via a
separate, hand-rolled emit+cc+run recipe. This script proves the same thing
through `native_exe_build.build_native_executable` — the actual assembled
driver — retiring the GOV-008 duplicated-recipe risk flagged when that
script was first audited (spec §4.2: "duplicating the C compile/link recipe
across scripts after the canonical driver lands" is explicitly the thing to
avoid).

Run directly (`python3 scripts/native_exe_behavior_corpus.py --root .`) for
the full sweep, or `--selftest` for a fast 3-row smoke subset.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from native_exe_build import build_native_executable


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


def run_corpus(root: Path, rows: list[tuple[str, int]] | None = None) -> int:
    sv0c = root / "sv0c"
    manifest_path = sv0c / "test" / "behavior" / "manifest.txt"
    if rows is None:
        rows = _read_manifest(manifest_path)

    n = 0
    for rel, want in rows:
        case = sv0c / rel
        if not case.is_file():
            print(f"native_exe_behavior_corpus: missing case {case}", file=sys.stderr)
            return 1

        import tempfile

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "out.bin")
            try:
                build_native_executable("file", str(case), out, td, probe=(n == 0))
            except Exception as exc:  # noqa: BLE001 - report any failure, don't hide it
                print(f"native_exe_behavior_corpus: build failed for {rel}: {exc}", file=sys.stderr)
                return 1
            got = subprocess.run([out], capture_output=True).returncode
            if got != want:
                print(f"native_exe_behavior_corpus: {rel} exited {got}, expected {want}", file=sys.stderr)
                return 1
        n += 1

    print(f"native_exe_behavior_corpus: OK ({n} program(s))", file=sys.stderr)
    return 0


def _selftest() -> int:
    root = Path(__file__).resolve().parent.parent
    manifest_path = root / "sv0c" / "test" / "behavior" / "manifest.txt"
    all_rows = _read_manifest(manifest_path)
    # A fast smoke subset for --selftest; the full sweep is the real gate,
    # invoked separately (it's slow -- 100+ real compiles) and not run on
    # every test-guards pass.
    subset = all_rows[:3] if len(all_rows) >= 3 else all_rows
    if not subset:
        print("native_exe_behavior_corpus selftest FAIL: manifest has no rows", file=sys.stderr)
        return 1
    return run_corpus(root, subset)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--selftest", action="store_true", help="Run a fast 3-row smoke subset instead of the full corpus")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    return run_corpus(args.root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
