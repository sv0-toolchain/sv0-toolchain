#!/usr/bin/env python3
"""Generate a small static doc bundle under build/sv0-toolchain-doc/."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def outline_sv0(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if re.match(r"^(pub\s+)?(fn|struct|enum|trait|impl)\s", s):
            out.append(f"- `{s[:120]}{'…' if len(s) > 120 else ''}`")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    root: Path = args.root.resolve()
    out_dir = root / "build" / "sv0-toolchain-doc"
    out_dir.mkdir(parents=True, exist_ok=True)

    sv0doc = root / "sv0doc"
    rewrite = root / "sv0c" / "rewrite"
    def rp(p: Path) -> str:
        try:
            return str(p.relative_to(root))
        except ValueError:
            return str(p)

    lines: list[str] = [
        "# sv0 toolchain — generated documentation index",
        "",
        "This file is produced by `./scripts/sv0 doc` (see `task/sv0-toolchain-milestone-2-prep.Rmd`).",
        "",
        "## Normative specification (sv0doc)",
        "",
        f"- README: `{rp(sv0doc / 'README.md')}`",
        f"- Grammar: `{rp(sv0doc / 'grammar' / 'sv0.ebnf')}`",
        f"- Bytecode: `{rp(sv0doc / 'bytecode')}`",
        "",
        "## Bootstrap compiler in sv0 (rewrite track)",
        "",
    ]
    if rewrite.is_dir():
        for sv0 in sorted(rewrite.glob("*.sv0")):
            lines.append(f"### `{rp(sv0)}`")
            lines.extend(outline_sv0(sv0) or ["- _(no top-level items detected)_"])
            lines.append("")
    else:
        lines.append("_(no rewrite/ directory yet)_\n")

    index = out_dir / "index.md"
    index.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
