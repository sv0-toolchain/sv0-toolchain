#!/usr/bin/env python3
"""Fail if README.md bootstrap table SHA does not match ``git ls-tree HEAD sv0c``.

The meta-repo README lists the pinned **sv0c** submodule next to **bootstrap-sml-final**
for support. This script keeps that line aligned with the actual gitlink at **HEAD**.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RE_README_SHA = re.compile(r"`([0-9a-f]{40})`")


def git_sv0c_gitlink(root: Path) -> str | None:
    """Return lowercase 40-char SHA for submodule **sv0c** at **HEAD**, or None."""
    r = subprocess.run(
        ["git", "ls-tree", "HEAD", "sv0c"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        print(
            f"verify_readme_sv0c_gitlink: git ls-tree failed: {r.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    line = r.stdout.strip()
    if not line:
        print(
            "verify_readme_sv0c_gitlink: no sv0c entry at HEAD (submodule missing?)",
            file=sys.stderr,
        )
        return None
    parts = line.split()
    if len(parts) < 3 or parts[0] != "160000" or parts[1] != "commit":
        print(
            f"verify_readme_sv0c_gitlink: expected submodule gitlink (160000 commit <sha>), got: {line!r}",
            file=sys.stderr,
        )
        return None
    sha = parts[2].lower()
    if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        print(
            f"verify_readme_sv0c_gitlink: invalid sha from git ls-tree: {sha!r}",
            file=sys.stderr,
        )
        return None
    return sha


def readme_pinned_sv0c_sha(readme: Path) -> str | None:
    """Return SHA from the **sv0c commit pinned** table row in README.md."""
    text = readme.read_text(encoding="utf-8")
    for raw in text.splitlines():
        if "sv0c commit pinned" not in raw:
            continue
        m = RE_README_SHA.search(raw)
        if not m:
            print(
                f"verify_readme_sv0c_gitlink: row mentions pinned commit but no `40-hex-sha` backticks: {raw!r}",
                file=sys.stderr,
            )
            return None
        return m.group(1).lower()
    print(
        "verify_readme_sv0c_gitlink: README.md missing bootstrap table row "
        "with **sv0c commit pinned** (see ## bootstrap compiler reference)",
        file=sys.stderr,
    )
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Toolchain repo root (default: parent of scripts/)",
    )
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    readme = root / "README.md"
    if not readme.is_file():
        print(f"verify_readme_sv0c_gitlink: missing {readme}", file=sys.stderr)
        return 1
    git_sha = git_sv0c_gitlink(root)
    doc_sha = readme_pinned_sv0c_sha(readme)
    if git_sha is None or doc_sha is None:
        return 1
    if git_sha != doc_sha:
        print(
            "verify_readme_sv0c_gitlink: README pinned sv0c SHA does not match git submodule at HEAD.\n"
            f"  git ls-tree HEAD sv0c: {git_sha}\n"
            f"  README.md table:       {doc_sha}\n"
            "  Update the bootstrap compiler table in README.md in the same commit as any sv0c submodule bump.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
