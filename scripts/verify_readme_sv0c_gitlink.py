#!/usr/bin/env python3
"""Fail if README.md bootstrap table SHA does not match the **sv0c** submodule gitlink.

Prefer the **index** entry from ``git ls-files -s sv0c`` so ``./scripts/sv0 test-guards``
can run **before** ``git commit`` when README and the submodule pointer are staged
together (``HEAD`` still points at the previous commit). If the index has no
``sv0c`` line, fall back to ``git ls-tree HEAD sv0c``.

If the workspace root is **not** a git repository (exported tree, sparse checkout
without ``.git``, etc.), submodule gitlinks cannot be read: the script **skips**
the SHA comparison after verifying that README.md still contains a well-formed
**sv0c commit pinned** row with a 40-hex SHA.

The meta-repo README lists the pinned **sv0c** submodule next to **bootstrap-sml-final**
for support. This script keeps that line aligned with the gitlink being committed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

RE_README_SHA = re.compile(r"`([0-9a-f]{40})`")


def git_work_tree_available(root: Path) -> bool:
    """Return True when *root* is inside a git work tree (``git`` installed and repo present)."""
    r = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        return False
    return r.stdout.strip() == "true"


def _parse_ls_tree_submodule_line(line: str) -> str | None:
    parts = line.split()
    if len(parts) < 3 or parts[0] != "160000" or parts[1] != "commit":
        print(
            "verify_readme_sv0c_gitlink: expected submodule gitlink "
            f"(160000 commit <sha>), got: {line!r}",
            file=sys.stderr,
        )
        return None
    sha = parts[2].lower()
    if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        print(
            f"verify_readme_sv0c_gitlink: invalid sha from git: {sha!r}",
            file=sys.stderr,
        )
        return None
    return sha


def git_sv0c_index_gitlink(root: Path) -> str | None:
    """Return lowercase 40-char SHA for **sv0c** from the git index, or None."""
    r = subprocess.run(
        ["git", "ls-files", "-s", "sv0c"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode != 0:
        print(
            f"verify_readme_sv0c_gitlink: git ls-files -s failed: {r.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    line = r.stdout.strip()
    if not line:
        return None
    parts = line.split()
    # "160000 <sha> 0\tsv0c" -> mode, object id, stage, path
    if len(parts) < 3 or parts[0] != "160000":
        print(
            f"verify_readme_sv0c_gitlink: unexpected ls-files line: {line!r}",
            file=sys.stderr,
        )
        return None
    sha = parts[1].lower()
    if len(sha) != 40 or not all(c in "0123456789abcdef" for c in sha):
        print(
            f"verify_readme_sv0c_gitlink: invalid index sha: {sha!r}",
            file=sys.stderr,
        )
        return None
    return sha


def git_sv0c_head_gitlink(root: Path) -> str | None:
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
    return _parse_ls_tree_submodule_line(line)


def git_sv0c_effective_gitlink(root: Path) -> tuple[str | None, str]:
    """Submodule SHA to compare README against, and a label for error messages."""
    idx = git_sv0c_index_gitlink(root)
    if idx is not None:
        return idx, "git index (git ls-files -s sv0c)"
    head = git_sv0c_head_gitlink(root)
    return head, "HEAD (git ls-tree HEAD sv0c)"


def readme_pinned_sv0c_sha(readme: Path) -> str | None:
    """Return SHA from the **sv0c commit pinned** table row in README.md."""
    text = readme.read_text(encoding="utf-8")
    for raw in text.splitlines():
        if "sv0c commit pinned" not in raw:
            continue
        m = RE_README_SHA.search(raw)
        if not m:
            print(
                "verify_readme_sv0c_gitlink: row mentions pinned commit but no "
                f"`40-hex-sha` backticks: {raw!r}",
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
    doc_sha = readme_pinned_sv0c_sha(readme)
    if doc_sha is None:
        return 1
    if not git_work_tree_available(root):
        print(
            "verify_readme_sv0c_gitlink: OK (skip submodule gitlink check — "
            "not a git repository; README.md sv0c pinned SHA row present)",
            file=sys.stderr,
        )
        return 0
    git_sha, git_label = git_sv0c_effective_gitlink(root)
    if git_sha is None:
        return 1
    if git_sha != doc_sha:
        print(
            "verify_readme_sv0c_gitlink: README pinned sv0c SHA does not match "
            f"submodule gitlink ({git_label}).\n"
            f"  {git_label}: {git_sha}\n"
            f"  README.md table:       {doc_sha}\n"
            "  Update the bootstrap compiler table in README.md in the same commit "
            "as any sv0c submodule bump.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
