#!/usr/bin/env python3
"""BH-8: run the NATIVE mega-TU compiler on diagnostics manifest rows; assert needle.

The native twin of verify_diagnostics_corpus_behavior.py (which runs the SML
bootstrap). Compiles each `rel | needle` row with build/sv0-megatu-compiler-native
and asserts the needle appears in combined stdout+stderr AND the compile is
rejected (nonzero exit) — the native checker must now diagnose, not silently
accept. Builds the native compiler first if it is missing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    manifest = root / "sv0c" / "test" / "diagnostics" / "manifest.txt"
    if not manifest.is_file():
        print(f"verify_diagnostics_corpus_behavior_native: missing {manifest}", file=sys.stderr)
        return 1
    wrapper = root / "build" / "sv0-megatu-compiler-native"
    if not wrapper.is_file():
        build = root / "scripts" / "build-sv0-megatu-native.sh"
        r = subprocess.run(["bash", str(build)], capture_output=True, text=True, check=False)
        if not wrapper.is_file():
            print("verify_diagnostics_corpus_behavior_native: native build failed", file=sys.stderr)
            print((r.stderr or "")[-2000:], file=sys.stderr)
            return 1

    n = 0
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"verify_diagnostics_corpus_behavior_native: bad line: {raw!r}", file=sys.stderr)
            return 1
        rel, needle = (s.strip() for s in line.split("|", 1))
        case = root / "sv0c" / rel
        proc = subprocess.run(
            [str(wrapper), str(case)],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode == 0:
            print(
                f"verify_diagnostics_corpus_behavior_native: {rel} was ACCEPTED "
                f"(exit 0) — native checker did not diagnose",
                file=sys.stderr,
            )
            return 1
        if needle not in combined:
            print(
                f"verify_diagnostics_corpus_behavior_native: missing needle {needle!r} for {rel}",
                file=sys.stderr,
            )
            print("--- output (tail) ---", file=sys.stderr)
            print(combined[-2000:], file=sys.stderr)
            return 1
        n += 1
    print(f"verify_diagnostics_corpus_behavior_native: OK ({n} case(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
