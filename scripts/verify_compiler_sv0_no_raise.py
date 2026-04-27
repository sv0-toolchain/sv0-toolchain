#!/usr/bin/env python3
"""Fail if transliterated compiler ``.sv0`` sources use ``raise`` (M3-S-014 / G1 audit).

The milestone task requires migrating SML-style exceptions to ``Result`` /
``CompileError`` in ``sv0c/lib/``, ``sv0c/lexer/``, and ``sv0c/parser/``.
This guard keeps accidental ``raise`` reintroduction from landing silently.

Allowed roots (relative to ``sv0c/``): ``lib``, ``lexer``, ``parser``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Word-boundary ``raise`` as a statement/expression starter (not substring of identifiers).
_RAISE_RE = re.compile(r"(?m)(^|[^\w])raise(\s|\(|$)")


def iter_sv0_files(sv0c: Path) -> list[Path]:
    """Return sorted ``*.sv0`` under the compiler transliteration roots."""
    roots = [sv0c / "lib", sv0c / "lexer", sv0c / "parser"]
    out: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.sv0")):
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True, help="sv0-toolchain repo root")
    args = ap.parse_args()
    root: Path = args.root.resolve()
    sv0c = root / "sv0c"
    if not sv0c.is_dir():
        print(f"verify_compiler_sv0_no_raise: missing {sv0c}", file=sys.stderr)
        return 1
    paths = iter_sv0_files(sv0c)
    hits: list[tuple[Path, int, str]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"verify_compiler_sv0_no_raise: read {path}: {exc}", file=sys.stderr)
            return 1
        for i, line in enumerate(text.splitlines(), start=1):
            if _RAISE_RE.search(line):
                rel = path.relative_to(root)
                hits.append((rel, i, line.rstrip()))
    if hits:
        print(
            "verify_compiler_sv0_no_raise: `raise` found in compiler .sv0 "
            "(see M3-S-014 / G1 Track C in task/sv0-toolchain-milestone-3-self-host.Rmd):",
            file=sys.stderr,
        )
        for rel, lineno, line in hits:
            print(f"  {rel}:{lineno}: {line}", file=sys.stderr)
        return 1
    print(f"verify_compiler_sv0_no_raise: OK (scanned {len(paths)} path(s) under sv0c/lib|lexer|parser)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
