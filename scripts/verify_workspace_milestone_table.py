#!/usr/bin/env python3
"""Bidirectional consistency: ``milestone-orientation.json`` ↔ workspace milestone table.

**Forward:** every ``primary_tasks`` path in ``task/milestone-orientation.json`` appears in
``task/sv0-toolchain-workspace.Rmd`` (substring match — catches dropped table rows after JSON edits).

**Reverse:** every ``task/…/*.Rmd`` path found under ``## milestone and area tasks`` (until the next
``## `` heading) is listed as a ``primary_tasks`` entry for some milestone in the JSON (catches
table rows that agents ignore because they are missing from ``milestone-orientation.json``).

Optional JSON field ``workspace_milestone_table_allowlist``: list of ``task/*.Rmd`` paths that may
appear in that section without being ``primary_tasks`` (use sparingly; prefer extending milestones).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TASK_RMD_RE = re.compile(r"task/[a-zA-Z0-9_.-]+\.Rmd")


def _err(msg: str) -> None:
    print(f"verify_workspace_milestone_table: {msg}", file=sys.stderr)


def _milestone_table_section(body: str) -> str:
    """Return lines from `## milestone and area tasks` until the next `## ` heading (exclusive)."""
    lines = body.splitlines()
    start: int | None = None
    for idx, line in enumerate(lines):
        if line.startswith("## milestone and area tasks"):
            start = idx + 1
            break
    if start is None:
        _err(
            "missing '## milestone and area tasks' heading in sv0-toolchain-workspace.Rmd"
        )
        return ""
    chunk: list[str] = []
    for j in range(start, len(lines)):
        line = lines[j]
        if line.startswith("## ") and line.strip() != "## milestone and area tasks":
            break
        chunk.append(line)
    return "\n".join(chunk)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True, help="sv0-toolchain repo root")
    args = ap.parse_args()
    root: Path = args.root.resolve()
    jpath = root / "task" / "milestone-orientation.json"
    wpath = root / "task" / "sv0-toolchain-workspace.Rmd"
    for p in (jpath, wpath):
        if not p.is_file():
            _err(f"missing {p}")
            return 1
    data = json.loads(jpath.read_text(encoding="utf-8"))
    milestones = data.get("milestones")
    if not isinstance(milestones, list):
        _err("milestones must be a list")
        return 1
    json_paths: set[str] = set()
    for m in milestones:
        if not isinstance(m, dict):
            continue
        for rel in m.get("primary_tasks") or []:
            if isinstance(rel, str) and rel.strip():
                json_paths.add(rel.strip())
    raw_allow = data.get("workspace_milestone_table_allowlist")
    allow: set[str] = set()
    if isinstance(raw_allow, list):
        for x in raw_allow:
            if isinstance(x, str) and x.strip():
                allow.add(x.strip())
    elif raw_allow is not None:
        _err(
            "workspace_milestone_table_allowlist must be a list of strings when present"
        )
        return 1

    body = wpath.read_text(encoding="utf-8")
    # Forward: JSON primary_tasks ⊆ full workspace file
    forward_missing = sorted(p for p in json_paths if p not in body)
    if forward_missing:
        _err(
            "primary_tasks from task/milestone-orientation.json not found in "
            "task/sv0-toolchain-workspace.Rmd:"
        )
        for p in forward_missing:
            _err(f"  - {p}")
        return 1

    section = _milestone_table_section(body)
    if not section.strip():
        return 1
    table_paths = set(TASK_RMD_RE.findall(section))
    # Reverse: table paths ⊆ json_paths ∪ allowlist
    reverse_extra = sorted(
        p for p in table_paths if p not in json_paths and p not in allow
    )
    if reverse_extra:
        _err(
            "task/*.Rmd paths under '## milestone and area tasks' are not covered by "
            "milestone-orientation.json primary_tasks (add a milestone entry or allowlist):"
        )
        for p in reverse_extra:
            _err(f"  - {p}")
        return 1

    print(
        f"verify_workspace_milestone_table: OK (forward: {len(json_paths)} JSON path(s) in file; "
        f"reverse: {len(table_paths)} table path(s) ⊆ JSON∪allowlist)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
