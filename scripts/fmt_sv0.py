#!/usr/bin/env python3
"""Normalize .sv0 source text: strip trailing whitespace per line, trim trailing blank lines, ensure final newline.

Scope (milestone 2 prep): conservative formatting only; does not re-indent or reflow strings.
Use --check to exit 1 if any file would change."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def format_sv0(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def main() -> int:
    p = argparse.ArgumentParser(description="Format .sv0 files (whitespace normalization).")
    p.add_argument("--check", action="store_true", help="Do not write; exit 1 if a file would change.")
    p.add_argument("paths", nargs="*", type=Path, help=".sv0 files or directories (default: none)")
    args = p.parse_args()
    paths: list[Path] = list(args.paths)
    if not paths:
        print("fmt_sv0: no paths given", file=sys.stderr)
        return 2

    files: list[Path] = []
    for raw in paths:
        path = raw.resolve()
        if path.is_dir():
            files.extend(sorted(path.rglob("*.sv0")))
        elif path.suffix == ".sv0":
            files.append(path)
    if not files:
        return 0

    changed = False
    for f in files:
        try:
            old = f.read_text(encoding="utf-8")
        except OSError as e:
            print(f"fmt_sv0: read {f}: {e}", file=sys.stderr)
            return 1
        new = format_sv0(old)
        if old == new:
            continue
        changed = True
        if args.check:
            print(f"would reformat: {f}", file=sys.stderr)
            continue
        try:
            f.write_text(new, encoding="utf-8")
        except OSError as e:
            print(f"fmt_sv0: write {f}: {e}", file=sys.stderr)
            return 1
    if args.check and changed:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
