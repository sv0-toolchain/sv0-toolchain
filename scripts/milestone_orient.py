#!/usr/bin/env python3
"""Print milestone orientation for LLM/human workflows (see task/milestone-orientation.json)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _normalize_id(raw: str) -> str:
    s = raw.strip().lower()
    if s.startswith("m") and len(s) > 1 and s[1].isdigit():
        return "M" + s[1:]
    if s.isdigit():
        return "M" + s
    return raw.strip()


def _find(data: dict, needle: str) -> dict | None:
    milestones = data.get("milestones", [])
    for m in milestones:
        if m.get("id", "").lower() == needle.lower():
            return m
    norm = _normalize_id(needle)
    for m in milestones:
        if m.get("id", "") == norm:
            return m
    return None


def cmd_list(data: dict) -> None:
    print("id\ttitle\tprimary_task")
    for m in data.get("milestones", []):
        first = (m.get("primary_tasks") or [""])[0]
        print(f"{m.get('id', '')}\t{m.get('title', '')}\t{first}")


def cmd_show(data: dict, milestone_id: str) -> int:
    m = _find(data, milestone_id)
    if m is None:
        print(f"milestone_orient: unknown milestone id: {milestone_id!r}", file=sys.stderr)
        print("Run: python3 scripts/milestone_orient.py list", file=sys.stderr)
        return 1
    print(f"id: {m.get('id')}")
    print(f"title: {m.get('title')}")
    print("primary_tasks:")
    for p in m.get("primary_tasks") or []:
        print(f"  - {p}")
    print("submodules_hint:", ", ".join(m.get("submodules_hint") or []) or "(none)")
    print("pre_merge_validation:")
    for c in m.get("pre_merge_validation") or []:
        print(f"  - {c}")
    print(f"closure_authority: {m.get('closure_authority', '')}")
    anti = m.get("anti_patterns") or []
    if anti:
        print("anti_patterns:")
        for a in anti:
            print(f"  - {a}")
    print()
    print("Next: open the primary_tasks files and read completion criteria before claiming milestone progress.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="tabular index of milestone ids")
    p_show = sub.add_parser("show", help="print orientation for one milestone id (e.g. M3, 3, mcp-0)")
    p_show.add_argument("id", help="milestone id")
    args = parser.parse_args()
    path = _root() / "task" / "milestone-orientation.json"
    if not path.is_file():
        print(f"milestone_orient: missing {path}", file=sys.stderr)
        return 2
    data = _load(path)
    if args.cmd == "list":
        cmd_list(data)
        return 0
    if args.cmd == "show":
        return cmd_show(data, args.id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
