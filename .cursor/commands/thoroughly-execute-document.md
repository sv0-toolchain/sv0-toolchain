/agent-roles/software-architect-agent /agent-roles/implementation-agent /agent-roles/planning-agent

/use-all-mcp

You are the **orchestrator** agent. Follow a **phased** workflow and use **subagents** (Cursor **Task** / delegated agents) for parallel work. Do not blur phases: recon and planning complete before broad edits; merge subagent output before committing.

## Input

Treat the **document passed into this command** (the slash-command input) as the governing charter. Parse it for scope, acceptance criteria, owning **`task/*.Rmd`** links, and validation hooks (**`/run:`** companion scripts, **`./scripts/sv0`**, **`make`** targets).

## Phase 1 — Parallel recon (read-mostly)

Launch **multiple subagents in one message** when useful. Prefer **`explore`** (read-only) for broad codebase/spec discovery; use **`generalPurpose`** when recon must run bounded shell checks (e.g. **`git status`**, **`./scripts/sv0 test-guards`**) that do not change state.

Fan out by **independent tracks** when the charter spans them, for example:

- **`sv0doc/`** (normative spec/layout)
- **`sv0c/`** (compiler)
- **`sv0vm/`** (VM)
- **`sv0-mcp/`** (graph / MCP)
- root **`task/`**, **`scripts/`**, **`.cursor/rules/`**

Each subagent returns: **facts** (paths, commands, current state), **blockers**, and **citations** (file paths and sections). The orchestrator **reconciles contradictions**; do not commit while two recon reports disagree on facts.

## Phase 2 — Plan and decompose

Synthesize a **short execution plan**: ordered steps, spec → task → implementation → tests (**`.cursor/rules/05-planning-and-execution.mdc`**). **Decompose** large items in the owning **`task/*.Rmd`** and cross-link inventories (**`.cursor/rules/36-large-task-decomposition.mdc`**). If the input document is **`task/sv0-toolchain-roadmap-full.Rmd`**, also follow **`.cursor/rules/35-sv0-roadmap-full-execution.mdc`**.

You may use a **planning subagent** to draft the decomposition, but the orchestrator **approves** the plan and owns alignment with **`sv0doc/`** and milestone scope.

## Phase 3 — Execute (parallel when independent)

Implement **the next completable slices**. When slices touch **disjoint paths** (e.g. doc-only vs compiler-only), you may run **parallel implementation subagents** with **non-overlapping write scopes** and a single merge owner (the orchestrator).

**Serialise** (do not parallelise) when edits share files, submodule pointers, or normative semantics—one agent owns the integration commit sequence (**`.cursor/rules/29-submodule-git-visibility.mdc`**).

## Fast validation loop (default tiering)

Use **narrow checks during iteration**; escalate only when the charter or change class requires it. Always **name the exact command(s)** you ran (**`.cursor/rules/40-validation-and-proof.mdc`**).

| Change class | Prefer (in order) |
|--------------|-------------------|
| **`task/*.Rmd`** YAML / copy only | **`./scripts/sv0 test-guards`** |
| **One** bootstrap **`.sv0`** under **`sv0c/`** | **`./scripts/sv0 vm-compile <rel>`** and/or **`./scripts/sv0 emit-c <rel>`** (`<rel>` relative to **`sv0c/`**) |
| **`lib/bootstrap-sources.list`**, **`lib/golden/stage0/`**, **`lib/self-host-sv0-loop.list`**, **`sml/`** compiler, cross-submodule | **`./scripts/sv0 test-guards`** then **`./scripts/sv0 test`** before declaring the document slice **integrated** |
| After **meta-repo** push | **`gh run list`** / **`gh run watch`** (or **`gh run view <id>`**) on **CI** |

**`./scripts/sv0 test-guards`** — Python-only: block-comment guard, **sv0doc** baseline paths, **`task/*.Rmd`** YAML, **README** sv0c gitlink, vm-parity manifest ⊆ bootstrap (fast; no full SML suite).

**`./scripts/sv0 test`** — full orchestration: sv0c unit tests, integration, **`bootstrap-build`**, stage0 C goldens, self-host loop, vm-parity, doctests (use when the governing **`task/*.Rmd`** / charter touches integration or multiple lists).

**Self-host loop iteration:** **`SV0_SKIP_SELF_HOST_COMPILER_DIFF=1`** skips the third **`diff`** leg while exercising **`emit-c` + `cc` + run**; see **`sv0c/doc/self-host-sv0-loop.md`**.

**Graph / MCP:** refresh when **tasks** or normative **`sv0doc/`** layout change (**`task/sv0-mcp-milestone-0.Rmd`**); skip for rule-only churn (**`32-sv0-mcp-tooling-boundaries.mdc`**).

## Phase 4 — Validate, integrate, ship

Follow **## Fast validation loop** for default tiering. Run the **narrowest** checks first, then broaden as needed; **name the exact command** in your report (**`.cursor/rules/40-validation-and-proof.mdc`**). After pushes, check **GitHub Actions** with **`gh`** and fix failures before declaring progress.

**Commits:** no GPG signing; **Conventional Commits** with a **verbose body**; **atomic** commits; push **meta-repo and submodules** when submodule commits exist. **Tags** only when the governing document or task explicitly calls for them.

**MCP / graph:** refresh per **`task/sv0-mcp-milestone-0.Rmd`** when milestone tasks or normative **`sv0doc/`** layout change; skip graph sync for rule-only churn (**`.cursor/rules/32-sv0-mcp-tooling-boundaries.mdc`**).

**Timestamps** in edited **`task/*.Rmd`** frontmatter must match the user’s **actual current** time and timezone.

**Process hygiene:** do not leave **hanging** shells or background jobs without monitoring; prefer bounded waits and explicit completion.

**Status report:** what changed, what remains, and **order-of-magnitude slice count** (see **`task/sv0-toolchain-milestone-3-self-host.Rmd`** throughput table when estimating M3 transliteration).

**User prompts:** only for **design-level or high-impact** decisions; otherwise proceed (**`.cursor/rules/34-user-prompts-design-only.mdc`**).

Create or refine **`.mdc`** rules only when it **reduces ambiguity** for future runs (**`.cursor/rules/50-writing-style-and-document-shape.mdc`**); avoid duplicating **`sv0doc/`** normative text in rules.
