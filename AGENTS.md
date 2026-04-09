# Agent and LLM orientation (sv0-toolchain)

Use this file as the **first** on-ramp when automating work in this meta-repo. Normative language semantics live in **`sv0doc/`**, not here.

## Start here

1. **`task/sv0-toolchain-workspace.Rmd`** — submodule map, env vars, milestone task table.
2. **`task/sv0-toolchain-roadmap-full.Rmd`** — which design milestone owns which **`task/*.Rmd`** (index only; not a substitute for per-milestone completion criteria).
3. **`./scripts/sv0 milestone-orient list`** then **`./scripts/sv0 milestone-orient show <id>`** — machine-readable pointers to **owning tasks**, **suggested validation**, **closure authority**, and **anti-patterns** (`task/milestone-orientation.json`). **Make:** `make milestone-orient` and `make milestone-orient-show ID=M3`.

**Index consistency:** `verify_workspace_milestone_table.py` (inside **`./scripts/sv0 test-guards`**) enforces **bidirectional** alignment: JSON **`primary_tasks`** ⊆ workspace file, and every **`task/*.Rmd`** under **`## milestone and area tasks`** ⊆ JSON **`primary_tasks`** (union across milestones). Rare exceptions: top-level **`workspace_milestone_table_allowlist`** in **`milestone-orientation.json`**.

## Workflow rules (Cursor)

- **`00-workspace-context.mdc`** — ownership: spec vs compiler vs VM vs MCP.
- **`37-llm-milestone-driven-workflow.mdc`** — **orient → decompose → slice → validate → record** until the **owning task** says the milestone is done.
- **`33-continue-development-workflow.mdc`** — navigation, progress ledger, validation tiering pointers.
- **`34-user-prompts-design-only.mdc`** — built-in **ask-questions** discipline for design-level decisions.
- **`40-validation-and-proof.mdc`** — never claim a check passed without naming the command.

## Slash commands (optional)

- **`.cursor/commands/continue-development.md`** — phased “next slices” work + **progress ledger**.
- **`.cursor/commands/thoroughly-execute-document.md`** — charter-driven execution (pass the governing **`task/*.Rmd`** or doc as input).

## Progress and tracking

- Meta rollup: **`task/sv0-toolchain-progress.md`**
- Submodule detail: **`sv0doc/PROGRESS.md`**, **`sv0c/PROGRESS.md`**, **`sv0vm/PROGRESS.md`**, **`sv0-mcp/PROGRESS.md`**

## Validation (toolchain root)

| Situation | Typical command |
|-----------|-----------------|
| **`task/*.Rmd`** YAML / docs only | `./scripts/sv0 test-guards` |
| One **`sv0c/`** bootstrap **`.sv0`** | `./scripts/sv0 vm-compile <rel>` and/or `./scripts/sv0 emit-c <rel>` |
| Lists, goldens, **`sml/`**, integration | `./scripts/sv0 test-guards` then `./scripts/sv0 test` |

See **`task/milestone-orientation.json`** **`pre_merge_validation`** for milestone-specific defaults.

## What “milestone complete” means

**Completion criteria** are defined in the **owning** **`task/*.Rmd`** files linked from **`task/milestone-orientation.json`**. Passing **`./scripts/sv0 test`** is **necessary** for many integration slices but **not sufficient** to assert **M3** (self-host) or **SML retirement** — read **`task/sv0-toolchain-milestone-3-self-host.Rmd`** and **`28-sml-retirement-and-self-host-bar.mdc`**.
