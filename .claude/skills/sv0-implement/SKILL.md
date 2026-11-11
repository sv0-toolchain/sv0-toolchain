---
name: sv0-implement
description: Implements one ready sv0 checklist slice (TID-###, CV-###, M3-S-### and similar) end to end. It flips the row to wip, makes the smallest complete change, validates with named ./scripts/sv0 commands, and records the result in the row and the progress ledger. Use when the user asks to implement, do, run or continue a slice or the next slice. Slicing a design doc is sv0-slice.
argument-hint: "[slice id | checklist prefix] [--continue]"
---

# sv0-implement

One slice per run. With `--continue`, take the next ready slice after each one. Stop at a design question, a failed retry, or when context passes about 60%.

## House style

The session hooks load caveman, ponytail and i-have-adhd. When they conflict here:

- **Chat** follows i-have-adhd for shape and caveman for wording. Open each turn with `<slice id>, step N of 6: <state>`.
- **Code, comments, commit messages and checklist rows** are persisted. Write them in plain full sentences, matching the surrounding text.
- **ponytail** governs the change (step 4). It wins over any wish to tidy nearby code.

If those rules are not in context (for example in a worktree session), apply the three bullets above anyway.

## 1. Pick the slice

- Slice id given: `get_slice(<id>)`.
- Prefix given, or nothing: `next_slices(checklist=<prefix>, limit=5)`. Take the first one. Prefer a `wip` slice over a `todo` one.
- No MCP: `uv run --directory sv0-mcp sv0-mcp slices <prefix> --ready`, then `uv run --directory sv0-mcp sv0-mcp slice <id>`.

Done when you have the full row and its `file:line`. Show one line: id, title, done when, and an estimate in concrete units.

## 2. Mark it wip

Before any other edit, change the row's status cell to `wip` at the returned `file:line`. Other sessions and the progress dashboard read that cell.

## 3. Re-check the slice against the code

Delegate to one `Explore` subagent per repo the slice touches, with this contract:

> Reply only with lines of the form `path:line — symbol — what exists`, or `not found, searched: <patterns>`. Then `totals: <n>`. No prose.

Read the spec sections in the row's **refs**, and the hub's `D-*` entries they mention.

Stop and report when the code or `sv0doc/` contradicts the slice. Say what the row expected and what you found. Ask the user with `AskUserQuestion` only when the answer changes semantics or a public contract (`.cursor/rules/34-user-prompts-design-only.mdc`). Record the answer as a `D-*` entry in the hub.

Done when every file the change must reach is listed: callers, tests, fixtures, goldens, list files (`lib/bootstrap-sources.list` and similar), docs.

## 4. Make the smallest complete change

- **Red slice:** write the fixtures or tests only. Run them, and show that they fail for the reason the row names.
- **Implementation slice:** follow the ponytail ladder. Reuse what step 3 found before you write anything new. Touch every place step 3 listed.
- Respect submodule ownership: `.cursor/rules/00-workspace-context.mdc`, `30-sv0c-compiler-boundaries.mdc`, `31-sv0vm-vm-boundaries.mdc`. Behaviour that `sv0doc/` does not define is a design question, not a choice you make.
- Work outside the slice goes into the chat report as a candidate slice. Do not do it.

## 5. Validate

Pick the narrowest check in the AGENTS.md **Validation** table that covers the change. Then run the slice's **done when** check. Run anything noisy to a log file and read only the decisive lines:

```bash
./scripts/sv0 test > "$TMPDIR/sv0-test.log" 2>&1; echo "exit=$?"; grep -nE "FAIL|Error|error:" "$TMPDIR/sv0-test.log" | head -20
```

For a long run, delegate to a `general-purpose` subagent with this contract:

> Run `<commands>`. Do not edit files. Reply with one line per command: `<command> — PASS | FAIL | NOT RUN`. Under each FAIL, give at most 20 decisive lines with `file:line`.

A check that failed to start is NOT RUN, never PASS. When a check fails, fix it and run it again once. If it fails a second time, set the row to `blocked (<reason>)` and stop.

Done when the done-when check has run and passed, and you have shown its exact command and result.

## 6. Record

1. Set the row's status to `done — <one-line result>`. Add the commit hash once a commit exists.
2. Update the touched submodule's `PROGRESS.md` and the run log in `task/sv0-toolchain-progress.md`. Follow `## Progress ledger` in `.cursor/commands/continue-development.md`, and name the validation commands you ran.
3. Run `./scripts/sv0 test-guards`.
4. Stop before committing. Offer the commit. Commit in the submodule first, then bump the pointer (`.cursor/rules/29-submodule-git-visibility.mdc`). Add no AI attribution trailer: the repo hooks reject them.

End with what now works, how to try it, and one next action. Example: "TID-003 done: 12 manifest cases fail as intended. Next: `/sv0-implement TID-004` (about 30 min)."
