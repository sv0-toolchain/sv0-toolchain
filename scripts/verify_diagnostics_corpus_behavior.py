#!/usr/bin/env python3
"""M3-S-044: run SML bootstrap compile on diagnostics manifest rows; assert needle in output.

Requires SML/NJ and sv0c/sources.cm (same as ./scripts/sv0 test).
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
        print(f"verify_diagnostics_corpus_behavior: missing {manifest}", file=sys.stderr)
        return 1
    sv0c = root / "sv0c"
    lines_out: list[str] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"verify_diagnostics_corpus_behavior: bad line: {raw!r}", file=sys.stderr)
            return 1
        rel, needle = line.split("|", 1)
        rel = rel.strip()
        needle = needle.strip()
        script = (
            f'CM.make "sources.cm"; '
            f'OS.Process.exit(Main.main ((), ["{rel}"]));'
        )
        proc = subprocess.run(
            ["sml"],
            input=script,
            cwd=str(sv0c),
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        combined = (proc.stdout or "") + (proc.stderr or "")
        if needle not in combined:
            print(
                f"verify_diagnostics_corpus_behavior: missing needle {needle!r} for {rel}",
                file=sys.stderr,
            )
            print("--- output (tail) ---", file=sys.stderr)
            print(combined[-2000:], file=sys.stderr)
            return 1
        lines_out.append(f"OK {rel}")
    print(
        "verify_diagnostics_corpus_behavior: OK "
        + f"({len(lines_out)} case(s))",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
