#!/usr/bin/env python3
"""Guardrail for M3 G6 / M3-S-041 bootstrap staging closure.

Stage-0 compiler integration lives in SML ``sources.cm`` (heap-loaded modules +
``main.sml``). ``lib/main.sv0`` is compiled independently per bootstrap VM entry and
therefore cannot call ``parser.sv0`` without a linker or mega-module — see
``sv0c/doc/driver-pipeline-composition.md``.

This script locks minimal anchors so the documented staging model cannot drift
silently. It does **not** prove a single sv0 TU runs lexer→emit (deferred).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


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
    sources_cm = root / "sv0c" / "sources.cm"
    driver_doc = root / "sv0c" / "doc" / "driver-pipeline-composition.md"
    main_sv0 = root / "sv0c" / "lib" / "main.sv0"
    for path in (sources_cm, driver_doc, main_sv0):
        if not path.is_file():
            print(f"verify_m3_g6_staging_driver_contract: missing {path}", file=sys.stderr)
            return 1
    cm_text = sources_cm.read_text(encoding="utf-8")
    if "sml/main.sml" not in cm_text:
        print(
            "verify_m3_g6_staging_driver_contract: sv0c/sources.cm must list sml/main.sml",
            file=sys.stderr,
        )
        return 1
    doc_text = driver_doc.read_text(encoding="utf-8")
    if "Bootstrap VM-compile unit model" not in doc_text:
        print(
            "verify_m3_g6_staging_driver_contract: driver-pipeline-composition.md "
            "missing section anchor 'Bootstrap VM-compile unit model'",
            file=sys.stderr,
        )
        return 1
    main_text = main_sv0.read_text(encoding="utf-8")
    for needle in (
        "fn DRIVER_FULL_PIPELINE_LEN",
        "driver_tokenize_sketch",
        "fn driver_pipeline_step_name",
    ):
        if needle not in main_text:
            print(
                f"verify_m3_g6_staging_driver_contract: main.sv0 missing {needle!r}",
                file=sys.stderr,
            )
            return 1
    if "parse_program" in main_text:
        print(
            "verify_m3_g6_staging_driver_contract: main.sv0 unexpectedly references "
            "parse_program — staging driver must stay lexer/CLI boundary only",
            file=sys.stderr,
        )
        return 1
    print("verify_m3_g6_staging_driver_contract: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
