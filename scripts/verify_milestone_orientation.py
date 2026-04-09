#!/usr/bin/env python3
"""Validate ``task/milestone-orientation.json`` structure and that ``primary_tasks`` paths exist.

Catches broken links when task files are renamed and keeps milestone orientation data machine-usable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _err(msg: str) -> None:
    print(f"verify_milestone_orientation: {msg}", file=sys.stderr)


def _check_milestone(root: Path, m: dict[str, Any], idx: int) -> list[str]:
    """Return list of error strings."""
    errors: list[str] = []
    mid = m.get("id")
    if not mid or not isinstance(mid, str):
        errors.append(f"milestones[{idx}]: missing or invalid string id")
        return errors
    if not isinstance(m.get("title"), str) or not m["title"].strip():
        errors.append(f"milestone {mid!r}: missing title")
    tasks = m.get("primary_tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append(f"milestone {mid!r}: primary_tasks must be a non-empty list")
        return errors
    for rel in tasks:
        if not isinstance(rel, str) or not rel.strip():
            errors.append(f"milestone {mid!r}: invalid primary_tasks entry")
            continue
        p = (root / rel).resolve()
        if not p.is_file():
            errors.append(f"milestone {mid!r}: primary_tasks file missing: {rel}")
    for key in ("submodules_hint", "pre_merge_validation", "anti_patterns"):
        val = m.get(key, [])
        if val is not None and not isinstance(val, list):
            errors.append(f"milestone {mid!r}: {key} must be a list when present")
    ca = m.get("closure_authority")
    if ca is not None and not isinstance(ca, str):
        errors.append(f"milestone {mid!r}: closure_authority must be a string")
    for i, cmd in enumerate(m.get("pre_merge_validation") or []):
        if not isinstance(cmd, str) or not cmd.strip():
            errors.append(f"milestone {mid!r}: pre_merge_validation[{i}] invalid")
    return errors


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True, help="sv0-toolchain repo root")
    args = ap.parse_args()
    root: Path = args.root.resolve()
    path = root / "task" / "milestone-orientation.json"
    if not path.is_file():
        _err(f"missing {path}")
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        _err(f"invalid JSON in {path}: {e}")
        return 1
    milestones = data.get("milestones")
    if not isinstance(milestones, list) or not milestones:
        _err("top-level 'milestones' must be a non-empty list")
        return 1
    seen: set[str] = set()
    all_errors: list[str] = []
    for i, m in enumerate(milestones):
        if not isinstance(m, dict):
            all_errors.append(f"milestones[{i}]: expected object")
            continue
        mid = m.get("id")
        if isinstance(mid, str):
            key = mid.lower()
            if key in seen:
                all_errors.append(f"duplicate milestone id (case-insensitive): {mid!r}")
            seen.add(key)
        all_errors.extend(_check_milestone(root, m, i))
    if all_errors:
        for line in all_errors:
            _err(line)
        return 1
    print(
        f"verify_milestone_orientation: OK ({len(milestones)} milestone(s); "
        "all primary_tasks paths exist)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
