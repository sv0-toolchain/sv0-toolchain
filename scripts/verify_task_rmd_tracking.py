#!/usr/bin/env python3
"""Verify optional ``<!-- sv0-track: ... -->`` anchors in ``task/*.Rmd``.

Runs under ``./scripts/sv0 test-guards`` / CI smoke. See
``scripts/task_rmd_tracking.py`` and ``.cursor/rules/10-rmd-agent-documents.mdc``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Import sibling module when executed as ``python3 scripts/verify_....py``.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import task_rmd_tracking  # noqa: E402


def verify_all(*, root: Path, strict: bool) -> int:
    task_dir = root / "task"
    if not task_dir.is_dir():
        print("verify_task_rmd_tracking: no task/ directory", file=sys.stderr)
        return 0
    ec = 0
    for path in sorted(task_dir.glob("*.Rmd")):
        result = task_rmd_tracking.parse_task_rmd_file(path)
        if result.errors:
            ec = 1
            print("verify_task_rmd_tracking: errors in", path, file=sys.stderr)
            for msg in result.errors:
                print(f"  {msg}", file=sys.stderr)
        if strict and result.warnings:
            ec = 1
            print(
                "verify_task_rmd_tracking: strict mode — warnings in",
                path,
                file=sys.stderr,
            )
            for msg in result.warnings:
                print(f"  {msg}", file=sys.stderr)
        elif result.warnings and not strict:
            for msg in result.warnings:
                print(f"verify_task_rmd_tracking: warning: {msg}", file=sys.stderr)
    return ec


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Toolchain root (default: parent of scripts/)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Treat unknown JSON keys (warnings) as failures",
    )
    ap.add_argument(
        "--digest",
        type=Path,
        default=None,
        help=(
            "Write JSON digest of parsed task/*.Rmd files "
            "to this path (for dashboards)"
        ),
    )
    ap.add_argument(
        "--selftest",
        action="store_true",
        help="Run synthetic parse fixtures in task_rmd_tracking.py",
    )
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()

    if args.selftest:
        st_errs = task_rmd_tracking.run_selftests()
        if st_errs:
            print("verify_task_rmd_tracking: selftest failed:", file=sys.stderr)
            for e in st_errs:
                print(f"  {e}", file=sys.stderr)
            return 1
        print("verify_task_rmd_tracking: selftest OK")

    ec = verify_all(root=root, strict=args.strict)
    if args.digest is not None:
        task_dir = root / "task"
        rows: list[dict[str, object]] = []
        if task_dir.is_dir():
            for path in sorted(task_dir.glob("*.Rmd")):
                parsed = task_rmd_tracking.parse_task_rmd_file(path)
                rows.append(task_rmd_tracking.result_to_jsonable(parsed))
        args.digest.parent.mkdir(parents=True, exist_ok=True)
        out = json.dumps(rows, indent=2) + "\n"
        args.digest.write_text(out, encoding="utf-8")
    if ec != 0:
        msg = (
            "verify_task_rmd_tracking: fix sv0-track anchors / "
            "checklist binding in task/*.Rmd"
        )
        print(msg, file=sys.stderr)
    return ec


if __name__ == "__main__":
    raise SystemExit(main())
