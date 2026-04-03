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
    bootstrap_sv0 = root / "sv0c" / "lib"
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
        "## Bootstrap compiler in sv0 (`sv0c/lib/`)",
        "",
    ]
    if bootstrap_sv0.is_dir():
        sv0_files = sorted(bootstrap_sv0.rglob("*.sv0"))
        if not sv0_files:
            lines.append("_(no `*.sv0` under sv0c/lib yet)_\n")
        for sv0 in sv0_files:
            lines.append(f"### `{rp(sv0)}`")
            lines.extend(outline_sv0(sv0) or ["- _(no top-level items detected)_"])
            lines.append("")
    else:
        lines.append("_(no sv0c/lib directory yet)_\n")

    index = out_dir / "index.md"
    index.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
