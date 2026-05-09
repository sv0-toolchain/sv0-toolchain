#!/usr/bin/env python3
"""List references to the bootstrap path segment `sml/` before M3-S-051 cutover.

Informational only — does not modify files. Run from repo root:
  python3 scripts/sml_retirement_preflight_scan.py --root .

Exit 0 always (stdout is the report). Use after editing sources.cm paths during rename.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEXT_SUFFIXES = {
    ".md",
    ".yml",
    ".yaml",
    ".sh",
    ".cm",
    ".Rmd",
    ".json",
    ".txt",
    ".mk",
    "",
}

SKIP_DIR_NAMES = {
    ".git",
    ".cm",
    "__pycache__",
    ".ruff_cache",
    "node_modules",
    "build",
}

NEEDLE = "sml/"


def _walk_report(root: Path) -> list[tuple[Path, int]]:
    hits: list[tuple[Path, int]] = []
    roots = [
        root / "sv0c",
        root / "scripts",
        root / ".github",
        root / "task",
        root / ".cursor",
    ]
    for base in roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_dir():
                if path.name in SKIP_DIR_NAMES:
                    continue
                continue
            try:
                rel = path.relative_to(base)
            except ValueError:
                continue
            parts = path.parts
            if any(p in SKIP_DIR_NAMES for p in parts):
                continue
            suf = path.suffix.lower()
            if suf not in TEXT_SUFFIXES and path.name not in {
                "Makefile",
                "Makefile.ci",
                "sources.cm",
            }:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if NEEDLE not in text:
                continue
            n = text.count(NEEDLE)
            hits.append((path, n))
    hits.sort(key=lambda x: str(x[0]))
    return hits


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root = args.root.resolve()
    print(f"sml_retirement_preflight_scan: root={root}", file=sys.stderr)
    hits = _walk_report(root)
    print(f"Files containing '{NEEDLE}' under scanned subtrees: {len(hits)}\n")
    for path, count in hits:
        try:
            rel = path.relative_to(root)
        except ValueError:
            rel = path
        print(f"{count:5d}  {rel}")
    print(
        "\nNote: after `git mv sml sml-legacy`, replace member paths in sv0c/sources.cm "
        "and re-run this scan until only sml-legacy/ remains where intended.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
