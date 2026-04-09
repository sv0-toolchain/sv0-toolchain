/agent-roles/software-architect-agent /agent-roles/implementation-agent /agent-roles/planning-agent

/use-all-mcp

You are the **orchestrator** agent. **Continue** toolchain work toward the next **milestone-complete slices**, using a **phased** workflow and **subagents** (Cursor **Task** / delegated agents) for parallel recon and disjoint implementation. Navigation defaults: **`.cursor/rules/33-continue-development-workflow.mdc`**.

## Phase 0 — Anchor

Infer the **active milestone and owning `task/*.Rmd`** files from context (open files, user message, and **`task/sv0-toolchain-roadmap-full.Rmd`**). When the milestone id is known (e.g. **M3**), run **`./scripts/sv0 milestone-orient show <id>`** and treat output as guardrails (**`37-llm-milestone-driven-workflow.mdc`**). If the target slice is unclear, do **brief recon** before large edits.

## Progress ledger (mandatory each run)

**Hybrid tracking:** each submodule owns **`PROGRESS.md`** at its root (`sv0doc/`, `sv0c/`, `sv0vm/`, `sv0-mcp/`). The meta-repo owns **`task/sv0-toolchain-progress.md`** (rollup **Summary**, **Meta** checklist, **run log**).

1. **Start:** read **`task/sv0-toolchain-progress.md`**. Read every **`PROGRESS.md`** under a submodule you expect to touch; if unsure, read **all four**.
2. **Baseline (status report):** for each touched area, quote **`done` / `total` / `%`** from those files *before* edits.
3. **End (before claiming the session finished):**
   - If you changed files under a submodule, update that submodule’s **`PROGRESS.md`** (checklist + **`Last updated`**) so **`%` matches reality**.
   - Update **`task/sv0-toolchain-progress.md`**: refresh the **Summary** table to **mirror** submodule counts; append a **run log** row (date, areas touched, metric deltas, exact validation commands per **`40-validation-and-proof.mdc`**).
   - **Meta-only** work (`task/*.Rmd`, `scripts/`, `.cursor/`, `Makefile`, …): update the **Meta-repository checklist** + run log; submodule files stay unchanged unless tasks moved across boundaries.
4. **Progress contract:** the run must satisfy **at least one** of: higher **`done`**, a justified change to **`total`**, or a run-log entry that records a **blocker** / **recon-only** outcome with the **next concrete step**. Cosmetic edits alone are not enough.

## Phase 1 — Parallel recon (read-mostly)

Launch **multiple subagents in one message** when the slice spans submodules. Prefer **`explore`** for codebase/spec surveys; use **`generalPurpose`** for bounded non-destructive shell probes (e.g. **`./scripts/sv0 test-guards`**).

Default **fan-out tracks** when independent:

- **`sv0doc/`**, **`sv0c/`**, **`sv0vm/`**, **`sv0-mcp/`**, root **`task/`** / **`scripts/`**

Subagents return **facts**, **blockers**, and **path citations**. The orchestrator **merges** findings and resolves conflicts before planning.

## Phase 2 — Plan and decompose

Write or update **decomposition** in the owning **`task/*.Rmd`** when the remaining work is still a “wall” (**`.cursor/rules/36-large-task-decomposition.mdc`**). Keep **spec vs implementation** order (**`.cursor/rules/05-planning-and-execution.mdc`**).

## Phase 3 — Execute (parallel when safe)

Run **parallel implementation subagents** only for **disjoint file/submodule scopes** with a single merge owner. **Serialise** shared files, submodule pointer bumps, and cross-cutting semantics.

Progress toward **[compiler vision and design](http://development.sasankvishnubhatla.net/tcowmbh/task/sv0-compiler-vision-and-design.html)** without inventing behaviour beyond **`sv0doc/`** (**`.cursor/rules/20-spec-first-language-semantics.mdc`**).

## Fast validation loop (default tiering)

Use **narrow checks during iteration**; escalate only when the change class warrants it. Always **name the exact command(s)** you ran (**`.cursor/rules/40-validation-and-proof.mdc`**).

| Change class | Prefer (in order) |
|--------------|-------------------|
| **`task/*.Rmd`** YAML / copy only | **`./scripts/sv0 test-guards`** |
| **One** bootstrap **`.sv0`** under **`sv0c/`** | **`./scripts/sv0 vm-compile <rel>`** and/or **`./scripts/sv0 emit-c <rel>`** (`<rel>` relative to **`sv0c/`**) |
| **`lib/bootstrap-sources.list`**, **`lib/golden/stage0/`**, **`lib/self-host-sv0-loop.list`**, **`sml/`** compiler, cross-submodule | **`./scripts/sv0 test-guards`** then **`./scripts/sv0 test`** before push / merge |
| After **meta-repo** push | **`gh run list`** / **`gh run watch`** (or **`gh run view <id>`**) on **CI** |

**`./scripts/sv0 test-guards`** — Python-only: block-comment guard, **sv0doc** baseline paths, **`task/*.Rmd`** YAML, **README** sv0c gitlink, vm-parity manifest ⊆ bootstrap, **`milestone-orientation.json`** + bidirectional workspace milestone-table check (**`verify_workspace_milestone_table.py`**: JSON ↔ **`## milestone and area tasks`**) (fast; no full SML suite).

**`./scripts/sv0 test`** — full orchestration: sv0c unit tests, integration, **`bootstrap-build`**, stage0 C goldens, self-host loop, vm-parity, doctests (use for integration slices and pre-merge confidence).

**Self-host loop iteration:** **`SV0_SKIP_SELF_HOST_COMPILER_DIFF=1`** skips the third **`diff`** leg while exercising **`emit-c` + `cc` + run**; see **`sv0c/doc/self-host-sv0-loop.md`**. Turn it off before claiming semantic loop closure.

**Graph / MCP:** run **`sync_graph`** (or **`sv0-mcp`** sync) when **tasks** or normative **`sv0doc/`** layout change — not for every rule-only edit (**`32-sv0-mcp-tooling-boundaries.mdc`**).

## Phase 4 — Validate, integrate, ship

Follow **## Fast validation loop** for default tiering. Validate with the **narrowest** relevant commands that still match the change class, then broaden; **name them** in the report (**`.cursor/rules/40-validation-and-proof.mdc`**). After pushes, verify **GitHub Actions** with **`gh`**.

**Commits:** no GPG signing; **Conventional Commits** with **verbose** bodies; **atomic** commits; push **meta-repo and submodules** when needed (**`.cursor/rules/29-submodule-git-visibility.mdc`**). **Tags** only when a task explicitly requires them.

**MCP / graph:** sync when milestone **`task/*.Rmd`** or normative **`sv0doc/`** layout changes (**`task/sv0-mcp-milestone-0.Rmd`**); skip for rule-only edits where boundaries say so.

**Timestamps** in **`task/*.Rmd`** frontmatter: use the user’s **actual current** time and timezone.

**Process hygiene:** no **hanging** unattended background jobs.

**Status report:** done vs remaining, **before → after** **`%`** for each touched area (from **`task/sv0-toolchain-progress.md`** / submodule **`PROGRESS.md`**), and **order-of-magnitude** remaining slices (M3 estimates: **`task/sv0-toolchain-milestone-3-self-host.Rmd`** throughput table). When the slice is **non-trivial**, add **For learners (read next):** 2–4 links (**`sv0doc/`** → owning **`task/*.Rmd`** → one code/doc anchor) per **`50-writing-style-and-document-shape.mdc`**.

**User prompts:** follow **`34-user-prompts-design-only.mdc`** — includes the **built-in ask-questions discipline** (one design question at a time; do not commit semantics that depend on an unanswered question). No need to paste **`/ask-questions`** for that behavior.

Add **`.mdc`** rules sparingly when they encode **stable orchestration** or boundaries (**`.cursor/rules/50-writing-style-and-document-shape.mdc`**).
