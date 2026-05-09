#!/usr/bin/env python3
"""M3-S-054 / M3-S-055: GX bootstrap policy docs exist with expected anchors."""

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
            root / "sv0doc" / "compiler" / "bootstrap-generics-policy.md",
            ["M3-S-054", "T0-2d", "Deferred work:"],
        )
        _must_have(
            root / "sv0doc" / "compiler" / "bootstrap-deferred-surface.md",
            ["M3-S-055", "T0-7", "T0-9"],
        )
        _must_have(
            root / "sv0doc" / "type-system" / "rules.md",
            ["bootstrap-generics-policy.md"],
        )
    except (FileNotFoundError, ValueError) as e:
        print(f"verify_m3_gx_bootstrap_policy_docs: {e}", file=sys.stderr)
        return 1
    print("verify_m3_gx_bootstrap_policy_docs: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
