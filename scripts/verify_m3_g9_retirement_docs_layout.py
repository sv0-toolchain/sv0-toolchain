#!/usr/bin/env python3
"""M3-S-050 / M3-S-053 / M3-S-052: checklist + recovery anchors + Makefile legacy-bootstrap targets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _must_have(path: Path, needles: list[str]) -> None:
    if not path.is_file():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8")
    for n in needles:
        if n not in text:
            raise ValueError(f"{path}: missing expected substring {n!r}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    try:
        _must_have(
            root / "sv0c" / "Makefile",
            ["legacy-bootstrap-check", "legacy-bootstrap-heap"],
        )
        _must_have(
            root / "sv0c" / "doc" / "sml-retirement-cutover-checklist.md",
            ["bootstrap-sml-final", "sml-legacy/", "sources.cm", "M3-S-051", "sml-retirement-preflight"],
        )
        _must_have(
            root / "sv0c" / "doc" / "cold-bootstrap-recovery.md",
            ["bootstrap-sml-final", "sml-legacy/", "make heap"],
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"verify_m3_g9_retirement_docs_layout: {e}", file=sys.stderr)
        return 1
    print("verify_m3_g9_retirement_docs_layout: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
