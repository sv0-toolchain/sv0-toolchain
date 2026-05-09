#!/usr/bin/env python3
"""M3-S-047 layout: canonical recipe script + doc exist (no build execution — test-guards)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    need = [
        root / "scripts" / "build-sv0-self-host-compiler.sh",
        root / "sv0c" / "doc" / "native-self-host-compiler-recipe.md",
    ]
    for p in need:
        if not p.is_file():
            print(f"verify_m3_g8_native_recipe_paths: missing {p}", file=sys.stderr)
            return 1
    print(
        "verify_m3_g8_native_recipe_paths: OK (recipe script + doc)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
