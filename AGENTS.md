# Agent and LLM orientation (sv0-toolchain)

Use this file as the **first** on-ramp when automating work in this meta-repo. Normative language semantics live in **`sv0doc/`**, not here.

## Start here

1. **`task/sv0-toolchain-workspace.Rmd`** — submodule map, env vars, milestone task table.
2. **`task/sv0-toolchain-roadmap-full.Rmd`** — which design milestone owns which **`task/*.Rmd`** (index only; not a substitute for per-milestone completion criteria).
3. **`./scripts/sv0 milestone-orient list`** then **`./scripts/sv0 milestone-orient show <id>`** — machine-readable pointers to **owning tasks**, **suggested validation**, **closure authority**, **anti-patterns**, and optional **automation / ground-truth / human-checkpoint** depth (`task/milestone-orientation.json`). **Make:** `make milestone-orient` and `make milestone-orient-show ID=M3`.
4. **`task/agent-workflow-and-milestone-tracking.md`** — how this repo’s phased workflows relate to common agentic patterns (workflows vs agents, gates, routing) and how optional JSON fields deepen tracking **without** replacing owning-task prose.

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
| **`task/*.Rmd`** YAML / docs only | `./scripts/sv0 test-guards` (includes **`verify_task_rmd_frontmatter.py`** + optional **`sv0-track`** anchors via **`verify_task_rmd_tracking.py`** + **`verify_compiler_sv0_no_raise.py`** for M3-S-014) |
| **M3-S-014 spot-check** (compiler **`.sv0`** roots only) | `python3 scripts/verify_compiler_sv0_no_raise.py --root .` |
| **Local progress UI** (milestones + digest) | `./scripts/sv0 progress-dashboard` then open **<http://127.0.0.1:8765/>** (optional port arg; **`SV0_PROGRESS_DASHBOARD_REFRESH`** sec server TTL). UI: summary strip, per-task **collapsible cards** (checklists inside), **issues-only** filter, raw JSON under **Developer**. **`uv run sv0-mcp serve`** also spawns the same server by default (**`SV0_MCP_PROGRESS_DASHBOARD=0`** to disable; see **`sv0-mcp/README.md`**) |
| **Docker Neo4j + progress UI** (optional dev stack) | **`./scripts/sv0 mcp-light-stack up`** (or **`make mcp-light-up`**); tear down with **`down`** / **`make mcp-light-down`**. Uses **`SV0_MCP_TOOLCHAIN_ROOT`** (default meta-repo root) and **`SV0_MCP_PROGRESS_DASHBOARD_REFRESH`** (default **300**). See **`sv0-mcp/README.md`** for compose resource caps. |
| One **`sv0c/`** bootstrap **`.sv0`** | `./scripts/sv0 vm-compile <rel>` and/or `./scripts/sv0 emit-c <rel>` |
| **`sv0c/lib/lowering.sv0`** (match env / goldens) | `./scripts/sv0 vm-compile lib/lowering.sv0`; `./scripts/sv0 self-host-capture-stage0 lib/lowering.sv0`; copy **`build/self-host-compare/stage0/lowering.c`** → **`sv0c/lib/golden/stage0/lowering.c`**; SML **`--target=vm`** on **`lib/lowering.sv0`** then copy **`sv0c/build/vm/lowering.sv0b`** → **`sv0c/test/vm-parity/golden/sml/lowering.sv0b`**; `./scripts/sv0 test-guards` then **`SV0_SKIP_SELF_HOST_COMPILER_DIFF=1 ./scripts/sv0 test`** (or full **`./scripts/sv0 test`** before claiming semantic self-host closure) |
| **`sv0c/test/integration/**` VM project cases (e.g. **`import_use_match`**) | **`bash task/sv0vm-milestone-2/02-integration-test.sh`** (subset of **`./scripts/sv0 test`**; see **`sv0c/test/integration/README.md`**) |
| Lists, goldens, **`sml/`**, integration | `./scripts/sv0 test-guards` then `./scripts/sv0 test` |
| After **push** to GitHub (code or tests) | `gh run list --limit 3` then `gh run watch <id>` until success (see **`40-validation-and-proof.mdc`**) |

See **`task/milestone-orientation.json`** **`pre_merge_validation`** for milestone-specific defaults.

## What “milestone complete” means

**Completion criteria** are defined in the **owning** **`task/*.Rmd`** files linked from **`task/milestone-orientation.json`**. Passing **`./scripts/sv0 test`** is **necessary** for many integration slices but **not sufficient** to assert **M3** (self-host) or **SML retirement** — read **`task/sv0-toolchain-milestone-3-self-host.Rmd`** and **`28-sml-retirement-and-self-host-bar.mdc`**.
