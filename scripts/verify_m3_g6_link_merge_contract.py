#!/usr/bin/env python3
"""Guardrail for M3 G6 / M3-S-040: link merge primitives in sv0c/lib/link.sv0.

Ensures per-file token-stream merge helpers (`link_merge_parallel_token_streams_reloc_b`,
byte offset for newline concat) remain present after refactors. Does not prove full
`linkProjectDir` arena merge — see `sv0c/doc/link-g6-blockers.md`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

NEEDLES = (
    "fn link_merge_sources_two(",
    "fn link_second_file_byte_offset_after_concat(",
    "fn link_merge_parallel_token_streams_reloc_b(",
    "fn link_reloc_i32_vec_inplace(",
    "fn link_program_item_vecs_append(",
)


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
    link_sv0 = root / "sv0c" / "lib" / "link.sv0"
    if not link_sv0.is_file():
        print(f"verify_m3_g6_link_merge_contract: missing {link_sv0}", file=sys.stderr)
        return 1
    text = link_sv0.read_text(encoding="utf-8")
    for needle in NEEDLES:
        if needle not in text:
            print(
                f"verify_m3_g6_link_merge_contract: link.sv0 missing {needle!r}",
                file=sys.stderr,
            )
            return 1
    print("verify_m3_g6_link_merge_contract: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
