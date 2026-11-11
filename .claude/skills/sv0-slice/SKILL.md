---
name: sv0-slice
description: Turns an sv0 design document (a project-specs SPEC.md, a hub task/*.Rmd, an sv0doc/ chapter or a milestone id) into refined checklist slices in task/*-checklist.Rmd, ready for sv0-implement. Use when the user asks to slice, plan, break down or refine a spec or milestone into slices. Not for implementing slices (sv0-implement does that).
argument-hint: "<SPEC.md path | task/<hub>.Rmd | milestone id> [checklist file]"
---

# sv0-slice

Design doc in, approved checklist rows out. Write no product code here.

## House style

The session hooks load caveman, ponytail and i-have-adhd. When they conflict here:

- **Chat** follows i-have-adhd for shape (next action first, numbered steps, `step N of M`, time estimates, at most 5 visible items per group) and caveman for wording.
- **Rows written to files** are persisted docs: full short sentences, no caveman fragments. Match the surrounding rows' style.
- **ponytail** governs what a slice contains (step 4).

If those rules are not in context (for example in a worktree session), apply the three bullets above anyway.

## 1. Resolve the inputs

Find the design doc and its tracking files. Do not ask the user for anything you can look up.

- **SPEC.md:** specs live in `../../project-specs/<name>/SPEC.md` relative to this repo's root. Task files say `~/Documents/project-specs/`, which is an older location for the same tree. Specs run to thousands of lines: read the `§23` requirement catalog and the `§27` phase plan by line range (`grep -n "^## \|^### "` first), not the whole file.
- **Hub task:** `grep -l "project-specs/<name>" task/*.Rmd`. The hub holds gaps (`G-*`), conflicts (`X-*`), decisions (`D-*`) and the refinement log.
- **Checklist:** `checklist_summary` (sv0-graph MCP), or `uv run --directory sv0-mcp sv0-mcp slices --summary`. Note its count before you write. Never read a checklist file whole.
- **Milestone id:** `./scripts/sv0 milestone-orient show <id>`. Treat `closure_authority` and `anti_patterns` as hard limits.
- **Semantics:** `sv0doc/` is normative (`.cursor/rules/20-spec-first-language-semantics.mdc`).

Done when you can name the spec, the hub, the target checklist (existing, or new under step 6), and the ID prefix.

## 2. Inventory requirements

List every requirement ID the spec defines in the target section (for example `MAN-001`, `AC-026`, `§25.2`). For a large spec, delegate to one `Explore` subagent per spec section with this contract:

> Reply only with lines of the form `<req-id> — <spec path>:<line> — <one-line behaviour>`, then `totals: <n>`. No prose, no suggestions.

Then map each requirement against existing slices with `list_slices(checklist=<prefix>, status="any", query=<req-id>)`.

Done when every requirement ID is in exactly one bucket: **covered** (slice id), **uncovered**, or **contradicted** (spec and code or `sv0doc/` disagree).

## 3. Check the code

For each uncovered requirement, find what already exists. One `Explore` subagent per submodule touched, with this contract:

> Reply only with lines of the form `path:line — symbol — what exists`, or `not found, searched: <patterns>`. Then `totals: <n>`.

Done when every uncovered requirement has either a code location or an explicit `not found`.

## 4. Cut slices

Apply the ponytail ladder to each uncovered requirement, in order. Stop at the first rung that holds:

1. Does it need a slice? Requirements already met by existing code get a one-line `done` row citing `path:line`, not new work.
2. Can it join an existing open slice without breaking that slice's stopping point?
3. Otherwise, cut a new slice.

Each new slice must:

- Be one session with one stopping point.
- Touch one repo (`c`, `vm`, `doc`, `root`, `mcp`). Split cross-submodule work, with the spec or doc slice first (`.cursor/rules/05-planning-and-execution.mdc`).
- Be a vertical: tests plus the code that passes them. Where the checklist uses `red` slices, put the failing-fixture slice before its implementation slice.
- Name its deps by slice id only.
- End on a **done when** that a command checks. Example: "`./scripts/sv0 test-guards` passes and `test/tid/manifest/` has 12 failing cases." Never "works" or "is implemented".
- Carry no option, flag or abstraction the spec does not require. Name anything you dropped under "not in this slice" in the hub.

A wide change (renaming a shared symbol, retyping an IR node) cannot land as one green slice. Sequence it as expand, then migrate in batches, then contract, one slice each.

Done when every uncovered requirement maps to a slice id, a `done` row, or a design question.

## 5. Settle design questions, then show the draft

Ask only questions that change semantics, a public contract or milestone scope (`.cursor/rules/34-user-prompts-design-only.mdc`). Use `AskUserQuestion` with one decision per question and the recommended option first. Independent questions may share one call. Record each answer as a `D-*` entry in the hub.

Then show the draft in chat:

1. One line per slice: `ID — title — deps — estimate`. Give the estimate in concrete units (for example "about 45 min" or "one afternoon").
2. At most 5 slices visible per group. Group by band or phase.
3. The requirement coverage counts: covered, new, done-already, open questions.

Done when the user approves the draft. Write nothing to `task/` before that.

## 6. Write the rows

Read `references/checklist-rows.md`, then:

1. Add the rows to the target checklist. Create the file from the template there if none exists.
2. Add a one-line entry to the hub's `## refinement log` with the date and the slice id range.
3. Update `updated:` in both files' frontmatter with the real current timestamp.

## 7. Validate

Run both checks and show their decisive output:

```bash
./scripts/sv0 test-guards
```

```bash
uv run --directory sv0-mcp sv0-mcp slices --summary | grep <checklist-stem>
```

`--summary` ignores a checklist argument, so filter with `grep`. Done when test-guards passes and the checklist's count grew by the number of rows you wrote. End with one next action, for example: "Next: `/sv0-implement TID-016` (about 40 min)."
