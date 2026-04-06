#!/usr/bin/env python3
"""Fail if any .sv0 under selected repo roots has `/*` nested inside a block comment.

The sv0 lexer treats `/` immediately followed by `*` as opening another comment
level. A path fragment like ``parser/**`` inside ``/* ... */`` therefore breaks
lexing: the next ``*/`` may only close the inner level and the rest of the file
is swallowed as a comment. This script approximates the lexer (strings, ``//``,
``/* */``) and reports any nested ``/*`` while already inside a block comment.

With **no arguments**, scans every existing directory among **sv0c/**, **sv0doc/**,
**sv0vm/**, and **sv0-mcp/** under the toolchain repo root (so future **.sv0**
outside **sv0c** is covered automatically).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SCAN_SUBDIRS = ("sv0c", "sv0doc", "sv0vm", "sv0-mcp")


def find_nested_block_opens(path: Path) -> list[tuple[int, str]]:
    """Return (byte_offset, context_snippet) for each problematic nested ``/*``."""
    s = path.read_text(encoding="utf-8")
    n = len(s)
    i = 0
    depth = 0
    issues: list[tuple[int, str]] = []
    while i < n:
        if depth > 0:
            if i + 1 < n and s[i] == "/" and s[i + 1] == "*":
                lo = max(0, i - 24)
                hi = min(n, i + 48)
                snippet = s[lo:hi].replace("\n", " ")
                issues.append((i, snippet))
                depth += 1
                i += 2
                continue
            if i + 1 < n and s[i] == "*" and s[i + 1] == "/":
                depth -= 1
                i += 2
                continue
            i += 1
            continue
        if i + 1 < n and s[i] == "/" and s[i + 1] == "/":
            i += 2
            while i < n and s[i] != "\n":
                i += 1
            continue
        if i + 1 < n and s[i] == "/" and s[i + 1] == "*":
            depth = 1
            i += 2
            continue
        if s[i] == '"':
            i += 1
            while i < n:
                if s[i] == "\\":
                    i = min(i + 2, n)
                    continue
                if s[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if s[i] == "'":
            i += 1
            while i < n:
                if s[i] == "\\":
                    i = min(i + 2, n)
                    continue
                if s[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        i += 1
    return issues


def find_bold_slash_star_snare(path: Path) -> list[int]:
    """Line numbers (1-based) containing ``**/**`` — often opens a nested ``/*`` inside block comments."""
    lines = path.read_text(encoding="utf-8").splitlines()
    bad: list[int] = []
    for i, line in enumerate(lines, start=1):
        if "**/**" in line:
            bad.append(i)
    return bad


def default_scan_roots() -> list[Path]:
    """Return existing toolchain submodule roots that should be scanned by default."""
    roots: list[Path] = []
    for name in DEFAULT_SCAN_SUBDIRS:
        p = (REPO_ROOT / name).resolve()
        if p.is_dir():
            roots.append(p)
    return roots


def iter_sv0_files(roots: list[Path]) -> list[Path]:
    """Unique *.sv0 paths under ``roots`` (by resolved path), sorted for stability."""
    seen: set[Path] = set()
    out: list[Path] = []
    for root in roots:
        r = root.resolve()
        if not r.is_dir():
            continue
        for f in sorted(r.rglob("*.sv0")):
            key = f.resolve()
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
    return out


def display_path(path: Path) -> str:
    """Path relative to repo root when possible."""
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve()))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    """Run the checker; exit 0 if clean, 1 if any file has nested block opens."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "roots",
        type=Path,
        nargs="*",
        metavar="DIR",
        help="Directories to scan for *.sv0 (default: existing sv0c, sv0doc, sv0vm, sv0-mcp under repo)",
    )
    args = p.parse_args(argv)
    roots: list[Path] = list(args.roots) if args.roots else default_scan_roots()
    if args.roots:
        for root in roots:
            if not root.is_dir():
                print(
                    f"check_sv0_block_comment_nesting: not a directory: {root}",
                    file=sys.stderr,
                )
                return 1
    elif not roots:
        print(
            "check_sv0_block_comment_nesting: no default scan roots exist "
            f"(looked under {REPO_ROOT})",
            file=sys.stderr,
        )
        return 1
    bad = False
    for f in iter_sv0_files(roots):
        rel = display_path(f)
        hits = find_nested_block_opens(f)
        snare = find_bold_slash_star_snare(f)
        if not hits and not snare:
            continue
        bad = True
        print(f"{rel}:", file=sys.stderr)
        for off, ctx in hits:
            print(f"  offset {off}: ...{ctx!r}...", file=sys.stderr)
        for ln in snare:
            print(
                f"  line {ln}: contains `**/**` (slash + star opens nested block comment; "
                "reword bold separators)",
                file=sys.stderr,
            )
    if bad:
        print(
            "check_sv0_block_comment_nesting: fix comments or paths so `/` is not "
            "immediately followed by `*` inside `/* ... */` (see "
            "sv0c/doc/transliteration-include.md).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
