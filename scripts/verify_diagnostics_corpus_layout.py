#!/usr/bin/env python3
"""M3-S-044: diagnostics corpus file layout (no SML — test-guards).

Ensures sv0c/test/diagnostics/README.md, manifest.txt, and listed case files exist.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    diag = root / "sv0c" / "test" / "diagnostics"
    readme = diag / "README.md"
    manifest = diag / "manifest.txt"
    if not readme.is_file():
        print(f"verify_diagnostics_corpus_layout: missing {readme}", file=sys.stderr)
        return 1
    if not manifest.is_file():
        print(f"verify_diagnostics_corpus_layout: missing {manifest}", file=sys.stderr)
        return 1
    text = manifest.read_text(encoding="utf-8")
    n = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"verify_diagnostics_corpus_layout: bad line (no |): {raw!r}", file=sys.stderr)
            return 1
        rel, _needle = line.split("|", 1)
        rel = rel.strip()
        if not rel:
            print(f"verify_diagnostics_corpus_layout: empty path: {raw!r}", file=sys.stderr)
            return 1
        src = (root / "sv0c" / rel).resolve()
        if not src.is_file():
            print(f"verify_diagnostics_corpus_layout: missing case file {src}", file=sys.stderr)
            return 1
        n += 1
    if n < 1:
        print("verify_diagnostics_corpus_layout: manifest has no entries", file=sys.stderr)
        return 1
    print(f"verify_diagnostics_corpus_layout: OK ({n} case path(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
