#!/usr/bin/env python3
"""Guardrail for M3 G6 / M3-S-041: stable pipeline shape in sv0c/lib/main.sv0.

``driver-pipeline-composition.md`` expects a nine-step spine (tokenize, parse,
then PHASE_* count). This script fails CI if those numeric contracts drift
without an intentional doc/task update.

Runs under ``./scripts/sv0 test-guards`` / ``sv0 test`` — not a substitute for
a single-TU lexer→emit driver (still tracked Partial until composition lands).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXPECT_PIPELINE_LEN = 9
EXPECT_PHASE_COUNT = 7


def _fn_body_after(text: str, fn_name: str) -> str | None:
    """Return braces body of ``fn fn_name`` at top level (first match)."""
    pat = re.compile(
        rf"fn\s+{re.escape(fn_name)}\s*\([^)]*\)\s*(?:->\s*[^{{]+)?\{{",
        re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return None
    start = m.end()
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    if depth != 0:
        return None
    return text[start : i - 1]


def _first_return_int(body: str) -> int | None:
    for line in body.splitlines():
        m = re.match(r"\s*return\s+(-?\d+)\s*;", line)
        if m:
            return int(m.group(1))
    return None


def check_driver_pipeline_order(driver_text: str) -> list[str]:
    """Verify drv_compile_file calls tokenize -> parse -> emit_c in order."""
    errors: list[str] = []
    body = _fn_body_after(driver_text, "drv_compile_file")
    if body is None:
        errors.append(
            "drv_compile_file: could not parse function body in driver.sv0"
        )
        return errors

    calls = ("drv_tokenize(", "drv_parse(", "drv_emit_c(")
    positions: dict[str, int] = {}
    for call in calls:
        idx = body.find(call)
        if idx == -1:
            errors.append(f"drv_compile_file: missing call to {call.rstrip('(')}")
        else:
            positions[call] = idx

    if len(positions) == len(calls):
        if not positions["drv_tokenize("] < positions["drv_parse("]:
            errors.append("drv_compile_file: drv_tokenize must precede drv_parse")
        if not positions["drv_parse("] < positions["drv_emit_c("]:
            errors.append("drv_compile_file: drv_parse must precede drv_emit_c")

    return errors


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
    main_sv0 = root / "sv0c" / "lib" / "main.sv0"
    if not main_sv0.is_file():
        print(f"verify_m3_g6_pipeline_contract: missing {main_sv0}", file=sys.stderr)
        return 1
    text = main_sv0.read_text(encoding="utf-8")

    pl_body = _fn_body_after(text, "DRIVER_FULL_PIPELINE_LEN")
    pc_body = _fn_body_after(text, "PHASE_COUNT")
    if pl_body is None:
        print(
            "verify_m3_g6_pipeline_contract: could not parse DRIVER_FULL_PIPELINE_LEN",
            file=sys.stderr,
        )
        return 1
    if pc_body is None:
        print(
            "verify_m3_g6_pipeline_contract: could not parse PHASE_COUNT",
            file=sys.stderr,
        )
        return 1

    pc_val = _first_return_int(pc_body)
    if pc_val is None:
        print(
            "verify_m3_g6_pipeline_contract: PHASE_COUNT has no int return",
            file=sys.stderr,
        )
        return 1

    if pc_val != EXPECT_PHASE_COUNT:
        print(
            f"verify_m3_g6_pipeline_contract: PHASE_COUNT expected {EXPECT_PHASE_COUNT}, "
            f"got {pc_val} — update driver-pipeline-composition.md + this script.",
            file=sys.stderr,
        )
        return 1

    pl_flat = "".join(pl_body.split())
    if "return2+PHASE_COUNT()" not in pl_flat and "return2+PHASE_COUNT();" not in pl_flat:
        if "2+PHASE_COUNT()" not in pl_flat:
            print(
                "verify_m3_g6_pipeline_contract: DRIVER_FULL_PIPELINE_LEN must be "
                "`return 2 + PHASE_COUNT();` (stable contract vs PHASE_COUNT).",
                file=sys.stderr,
            )
            return 1

    derived_len = 2 + pc_val
    if derived_len != EXPECT_PIPELINE_LEN:
        print(
            f"verify_m3_g6_pipeline_contract: implied pipeline len {derived_len} "
            f"!= {EXPECT_PIPELINE_LEN}",
            file=sys.stderr,
        )
        return 1
    pl_val = derived_len

    if "fn driver_pipeline_step_name(step: i32)" not in text:
        print(
            "verify_m3_g6_pipeline_contract: missing driver_pipeline_step_name",
            file=sys.stderr,
        )
        return 1
    for needle in ("tokenize", "parse", "resolve", "emit-vm"):
        if needle not in text:
            print(
                f"verify_m3_g6_pipeline_contract: main.sv0 missing {needle!r} substring",
                file=sys.stderr,
            )
            return 1

    driver_sv0 = root / "sv0c" / "lib" / "driver.sv0"
    if not driver_sv0.is_file():
        print(
            f"verify_m3_g6_pipeline_contract: missing {driver_sv0}", file=sys.stderr
        )
        return 1
    driver_text = driver_sv0.read_text(encoding="utf-8")
    order_errors = check_driver_pipeline_order(driver_text)
    if order_errors:
        for err in order_errors:
            print(f"verify_m3_g6_pipeline_contract: {err}", file=sys.stderr)
        return 1

    print(
        "verify_m3_g6_pipeline_contract: OK "
        f"(DRIVER_FULL_PIPELINE_LEN={pl_val}, PHASE_COUNT={pc_val})",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
