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
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from native_exe_build import build_native_executable


def _job_count() -> int:
    env = os.environ.get("SV0_JOBS")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return os.cpu_count() or 4


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


def _run_one(sv0c: Path, rel: str, want: int, probe: bool) -> str | None:
    """Returns None on success, else an error message."""
    case = sv0c / rel
    if not case.is_file():
        return f"missing case {case}"
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "out.bin")
        try:
            build_native_executable("file", str(case), out, td, probe=probe)
        except Exception as exc:  # noqa: BLE001 - report any failure, don't hide it
            return f"build failed for {rel}: {exc}"
        got = subprocess.run([out], capture_output=True).returncode
        if got != want:
            return f"{rel} exited {got}, expected {want}"
    return None


def run_corpus(root: Path, rows: list[tuple[str, int]] | None = None) -> int:
    sv0c = root / "sv0c"
    manifest_path = sv0c / "test" / "behavior" / "manifest.txt"
    if rows is None:
        rows = _read_manifest(manifest_path)
    if not rows:
        print("native_exe_behavior_corpus: OK (0 program(s))", file=sys.stderr)
        return 0

    # Probe the host compiler once, synchronously, before fanning out --
    # build_native_executable's `probe` step is a one-time capability check
    # (NEX-021/022), not build logic; running it once up front means every
    # parallel worker below can safely pass probe=False.
    first_rel, first_want = rows[0]
    err = _run_one(sv0c, first_rel, first_want, probe=True)
    failures: list[str] = [err] if err is not None else []

    rest = rows[1:]
    if rest:
        with ThreadPoolExecutor(max_workers=_job_count()) as pool:
            futures = [pool.submit(_run_one, sv0c, rel, want, False) for rel, want in rest]
            for fut in futures:
                e = fut.result()
                if e is not None:
                    failures.append(e)

    if failures:
        for e in failures:
            print(f"native_exe_behavior_corpus: {e}", file=sys.stderr)
        print(f"native_exe_behavior_corpus: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    print(f"native_exe_behavior_corpus: OK ({len(rows)} program(s))", file=sys.stderr)
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
