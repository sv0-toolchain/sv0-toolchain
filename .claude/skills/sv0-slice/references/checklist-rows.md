# Checklist rows

sv0-graph (`sv0-mcp/src/sv0_mcp/slices.py`) parses these rows. The tools `list_slices`, `next_slices` and `get_slice`, and `sv0-implement`, depend on this format. Keep it exact.

## Row rules

- Header row: `| ID | slice | refs | repo | deps | status | done when |`. The parser needs an `ID` (or `slice`) column, a `status` column and a `deps` column. Other columns are kept as cells.
- **ID:** `<PREFIX>-<number>[letter]`, for example `TID-016` or `TID-016a`. Use a letter suffix for a slice inserted after an existing one, so other ids stay stable. Never renumber or reuse an id.
- **slice:** starts with a bold title ending in a period: `**red: manifest v1 corpus.**`. One to three sentences follow.
- **refs:** spec requirement ids and `AC-*` scenarios, comma-separated.
- **repo:** `c` = sv0c, `vm` = sv0vm, `doc` = sv0doc, `root` = sv0-toolchain, `mcp` = sv0-mcp.
- **deps:** slice ids only, comma-separated, or `—`. `next_slices` treats a slice as ready only when every dep is `done`.
- **status:** the first word is one of `todo`, `wip`, `done`, `blocked`, `deferred`. Text may follow: `blocked (D-3)`, or `done — <one-line result> (<commit>)`.
- **done when:** one checkable stopping point that names a command or a file state.
- Keep a `|` inside a cell escaped as `\|`.

## New checklist file

Use this only when no checklist exists for the spec. Name it `task/<hub-key>-checklist.Rmd`.

```markdown
---
created: "<ISO-8601 timestamp with offset>"
updated: "<same>"
id: task-<hub-key>-checklist
key: <hub-key>-checklist
state: draft
tags:
  - sv0
  - checklist
  - planning
title: "<area> (<PREFIX>): development slice backlog (<PREFIX>-###)"
type: task
roadmap_parent: <hub roadmap_parent>
---

# <area> (<PREFIX>): development slice backlog

## purpose

The trackable **`<PREFIX>-###`** slice index for <area>. Each slice is one
focused session with one stopping point (the **done when** column). Strategy,
gaps, conflicts and decisions live in the hub **`task/<hub-key>.Rmd`**. The
contract is `~/Documents/project-specs/<name>/SPEC.md` `<spec version>`.

## how to use

- Status: **todo** / **wip** / **done** / **blocked (D-n)** / **deferred**.
- Repo column: `c` = sv0c, `vm` = sv0vm, `doc` = sv0doc, `root` = sv0-toolchain, `mcp` = sv0-mcp.
- Flip status and record a one-line result and commit as slices land.

## <band or phase name>

| ID | slice | refs | repo | deps | status | done when |
|----|-------|------|------|------|--------|-----------|
```

Link the new file from the hub's `## related`. If you also add it to the workspace milestone table in `task/sv0-toolchain-workspace.Rmd`, add it to `primary_tasks` in `task/milestone-orientation.json` as well. `./scripts/sv0 test-guards` checks that both lists match.
