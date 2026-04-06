#!/usr/bin/env python3
"""Fail if task/*.Rmd YAML front matter has common typos (missing space after ':').

sv0-mcp task sync and strict YAML parsers expect ``key: value`` not ``key:value``
or ``title:\"...\"``. Catches recurring editor glitches on updated/title/state/roadmap_parent.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Lines like updated:"... or title:"... (no space before opening quote)
RE_KEY_NO_SPACE_BEFORE_QUOTE = re.compile(
    r"^(updated|created|title|id|key|type|roadmap_parent):\""
)

# state:active, state:complete (no space after colon)
RE_STATE_COMPACT = re.compile(r"^state:[a-z]")

# roadmap_parent:foo — must be ``roadmap_parent: <id>`` with space
RE_ROADMAP_COMPACT = re.compile(r"^roadmap_parent:\S")


def scan_file(path: Path) -> list[str]:
    """Return human-readable problem lines for path, or empty if OK."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return []
    end = text.find("\n---\n", 4)
    if end == -1:
        return [f"{path}: no closing --- for front matter"]
    fm = text[4:end]
    bad: list[str] = []
    for i, line in enumerate(fm.splitlines(), start=2):
        if RE_KEY_NO_SPACE_BEFORE_QUOTE.match(line):
            bad.append(f"{path}:{i}: missing space after colon: {line!r}")
        if RE_STATE_COMPACT.match(line):
            bad.append(f"{path}:{i}: use 'state: <value>' (space after colon): {line!r}")
        if RE_ROADMAP_COMPACT.match(line):
            bad.append(f"{path}:{i}: use 'roadmap_parent: <key>' (space after colon): {line!r}")
    return bad


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Toolchain root (default: parent of scripts/)",
    )
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    task_dir = root / "task"
    if not task_dir.is_dir():
        print("verify_task_rmd_frontmatter: no task/ directory", file=sys.stderr)
        return 0
    all_bad: list[str] = []
    for path in sorted(task_dir.glob("*.Rmd")):
        all_bad.extend(scan_file(path))
    if all_bad:
        print("verify_task_rmd_frontmatter: fix YAML front matter in task/*.Rmd:", file=sys.stderr)
        for msg in all_bad:
            print(f"  {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
