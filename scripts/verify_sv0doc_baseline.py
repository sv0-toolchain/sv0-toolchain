#!/usr/bin/env python3
"""Verify milestone-0 / bootstrap spec files exist under sv0doc/ (and bytecode stubs).

`task/sv0c-milestone-1.Rmd` prerequisites and `./scripts/sv0 doc` both expect these
paths relative to the toolchain repo root. Fails fast in CI when a clone omits sv0doc
content or bytecode anchors.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Paths relative to repo root (must stay aligned with sv0 doc + milestone asserts).
REQUIRED_FILES: tuple[str, ...] = (
    "sv0doc/README.md",
    "sv0doc/grammar/sv0.ebnf",
    "sv0doc/type-system/rules.md",
    "sv0doc/contracts/semantics.md",
    "sv0doc/memory-model/ownership.md",
    "sv0doc/keywords/reference.md",
    "sv0doc/bytecode/format.md",
    "sv0doc/bytecode/instructions.md",
)


def main(argv: list[str] | None = None) -> int:
    """Exit 0 if every required file exists and is non-empty."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Toolchain repo root (default: parent of scripts/)",
    )
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    bad = False
    for rel in REQUIRED_FILES:
        p = root / rel
        if not p.is_file():
            print(f"verify_sv0doc_baseline: missing file: {rel}", file=sys.stderr)
            bad = True
            continue
        if p.stat().st_size == 0:
            print(f"verify_sv0doc_baseline: empty file: {rel}", file=sys.stderr)
            bad = True
    if bad:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
