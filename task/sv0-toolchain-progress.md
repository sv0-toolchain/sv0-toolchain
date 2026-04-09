# sv0 toolchain progress rollup (meta-repository)

This file is the **cross-repo rollup** and **session run log** for the **sv0-toolchain** parent checkout. It does **not** replace submodule detail.

## Authority (hybrid 2 + 3)

| Layer | Location | Owns |
|--------|-----------|------|
| **Submodule** | `sv0doc/PROGRESS.md`, `sv0c/PROGRESS.md`, `sv0vm/PROGRESS.md`, `sv0-mcp/PROGRESS.md` | Item checklists, definitions of **done** / **total**, and **local %** for that repository. |
| **Meta** | this file (`task/sv0-toolchain-progress.md`) | **Summary table** (mirrors submodule `%`), **orchestration** rows for meta-only work, and **run log** entries for every agent session that claims toolchain progress. |

**Update order:** change the **submodule** `PROGRESS.md` first when work landed there, then update this rollup in the **same integration** (same meta-repo commit as submodule pointer bumps when applicable).

## Summary (mirror submodule files — edit only after updating sources)

| Area | Source | Done | Total | % |
|------|--------|------|-------|---|
| Specification (`sv0doc`) | `sv0doc/PROGRESS.md` | 0 | 4 | 0% |
| Compiler (`sv0c`) | `sv0c/PROGRESS.md` | 6 | 6 | 100% |
| VM (`sv0vm`) | `sv0vm/PROGRESS.md` | 0 | 3 | 0% |
| MCP / graph (`sv0-mcp`) | `sv0-mcp/PROGRESS.md` | 0 | 3 | 0% |
| Meta orchestration | ## Meta-repository checklist below | 5 | 5 | 100% |

**Overall % (optional):** average of the five rows above once every `Total` is non-zero; otherwise leave blank. *(Example: ~16% with the seed numbers above.)*

## Meta-repository checklist (orchestration)

Countable items for work that stays in the **parent repo** (`task/`, `scripts/`, `.cursor/`, `Makefile`, …). Adjust **Total** when the plan changes; document rationale in the run log.

| ID | Item | Done |
|----|------|------|
| META-1 | Progress ledger files exist and slash commands reference them | 1 |
| META-2 | Roadmap index + verify script path remain consistent (`task/sv0-toolchain-roadmap-full.Rmd`) | 1 |
| META-3 | Milestone orientation: `task/milestone-orientation.json` + `./scripts/sv0 milestone-orient` + rule `37` + `AGENTS.md` | 1 |
| META-4 | `scripts/verify_milestone_orientation.py` wired into `./scripts/sv0 test-guards` + CI smoke step | 1 |
| META-5 | `scripts/verify_workspace_milestone_table.py` (JSON ↔ workspace table) + explicit `./scripts/sv0 test` step in GitHub Actions | 1 |

Set **Done** to `1` when true. Expand the table as new cross-cutting gates appear.

## Run log (newest first)

| ISO date (timezone) | Charter / focus | Areas touched | Metric delta (before → after) | Validation commands (exact) |
|---------------------|-----------------|---------------|------------------------------|-----------------------------|
| 2026-04-09 (America/Denver) | **`continue-development`** — M3 **`lower_stmt_dispatch_core`**; **push** | **sv0c:** `lib/lower_stmt_dispatch_core.sv0`, lists, `lib/golden/stage0/lower_stmt_dispatch_core.c`, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`, `PROGRESS.md`; **meta:** M3 task + checklist + roadmap + run log (meta **pending push**) | Pilots **52→53**; stage0 **62→63**; bootstrap **135→136**; sv0c checklist **6/6** unchanged | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards`, `./scripts/sv0 test`; `git push origin main` **sv0c** **OK** (**`8c9cec7`**); parent **`git push`** **failed** (SSH timeout **`github.com:22`**) — **retry meta** |
| 2026-04-09 (America/Denver) | **`continue-development`** — M3 **`lower_body_dispatch_core`** | **sv0c:** `lib/lower_body_dispatch_core.sv0`, lists, `lib/golden/stage0/lower_body_dispatch_core.c`, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`, `PROGRESS.md`; **meta:** M3 task + checklist + roadmap + run log | Pilots **51→52**; stage0 **61→62**; bootstrap **134→135**; sv0c checklist **6/6** unchanged | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards`, `./scripts/sv0 test` |
| 2026-04-09 (America/Denver) | **CI fix** — README **sv0c** pin vs submodule (**`64688a3`**) | **meta:** `README.md` SHA **`3da2672`→`9e3cb70`** (match **`git ls-tree HEAD sv0c`**); run log | *(no metric change)* | `./scripts/sv0 test-guards` |
| 2026-04-09 (America/Denver) | **`continue-development`** — M3 **`lower_fn_prefix_core`** | **sv0c:** `lib/lower_fn_prefix_core.sv0`, lists, `lib/golden/stage0/lower_fn_prefix_core.c`, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`, `PROGRESS.md`; **meta:** M3 task + checklist + roadmap + run log | Pilots **50→51**; stage0 **60→61**; bootstrap **133→134**; sv0c checklist **6/6** unchanged | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards`, `./scripts/sv0 test` |
| 2026-04-09 (America/Denver) | **`continue-development`** — **`lower_return_body`** integrate; **push** | **sv0c:** commit **`3da2672`**; **meta:** submodule + README + M3/roadmap + run log (**`40e554f`**) | *(same metrics as next row)* | `git push origin main` **failed** (SSH timeout **`github.com:22`**); retry **`sv0c`** then parent |
| 2026-04-09 (America/Denver) | **`continue-development`** — M3 **`lower_return_body_core`** seed | **sv0c:** `lib/lower_return_body_core.sv0`, `lib/bootstrap-sources.list`, `lib/self-host-sv0-loop.list`, `lib/golden/stage0/lower_return_body_core.c`, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`, `PROGRESS.md`; **meta:** M3 task + checklist + roadmap snapshot + run log | Self-host pilots **49→50**; stage0 goldens **59→60**; bootstrap-listed lines **132→133**; sv0c checklist **6/6** unchanged | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards`, `./scripts/sv0 test` |
| 2026-04-09 (America/Denver) | **`continue-development`** — **C-6** local integrate + **push blocked** | **sv0c:** commit **`41b4b358`** (C-6 doc + `PROGRESS.md`); **meta:** submodule pointer + `README.md` pin + prior rollup (**`e1f612e`**) | *(metrics same as prior row — already 6/6)* | `./scripts/sv0 test-guards` (**OK**); `git push origin main` (**failed**: SSH timeout / connection closed **`github.com:22`**) |
| 2026-04-09 (America/Denver) | **`continue-development`** — close **sv0c C-6** (SML retirement **guardrail** doc) | **sv0c:** `doc/self-host-sv0-loop.md` (§ SML retirement guardrail), `PROGRESS.md` (**C-6**=1 — policy documented, **not** retirement executed); **meta:** Summary **6/6** + run log | sv0c checklist **5/6→6/6** (**83%→100%**) | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards` |
| 2026-04-09 (America/Denver) | **`continue-development`** — close **sv0c C-5** + fix roadmap YAML | **sv0c:** `doc/self-host-sv0-loop.md` (pilot vs **`SV0_SELF_HOST_COMPILER`**), `PROGRESS.md` (**C-5**=1); **meta:** `task/sv0-toolchain-roadmap-full.Rmd` **`updated:`** YAML space; Summary + run log | sv0c checklist **4/6→5/6** (**67%→83%**) | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards` |
| 2026-04-09 (America/Denver) | **`thoroughly-execute-document`** — `task/sv0-toolchain-roadmap-full.Rmd` | **meta:** roadmap Rmd snapshot + `/ai` resolution; **`01-verify-roadmap-artifacts.sh`** now checks **M0/M1/M2/M3-checklist/MCP** paths; progress run log | Submodule **%** unchanged (sv0c **4/6**); **META-2** roadmap hygiene | `bash task/sv0-toolchain-roadmap-full/01-verify-roadmap-artifacts.sh`, `./scripts/sv0 milestone-orient list`, `./scripts/sv0 test-guards` |
| 2026-04-09 (America/Denver) | **`continue-development`** — close **sv0c C-4** (transliteration plan + LAYOUT living map) | **sv0c:** `doc/transliteration-plan.md` (C-4 contract + snapshot), `lib/LAYOUT.md` (C-4 cross-link), `PROGRESS.md` (**C-4**=1); **meta:** Summary + run log | sv0c checklist **3/6→4/6** (**50%→67%**); snapshot: bootstrap ~132 lines, pilots **49**, stage0 **59**, vm-parity **101** | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards` |
| 2026-04-09 (America/Denver) | **`continue-development`** — close **sv0c C-3** (VM parity v1 allowlist + docs) | **sv0c:** `test/vm-parity/README.md`, `lib/LAYOUT.md`, `PROGRESS.md` (**C-3**=1); **meta:** this rollup Summary + run log | sv0c checklist **2/6→3/6** (**33%→50%**); vm-parity manifest **101** paths (unchanged) | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards` |
| 2026-04-09 (America/Denver) | **`continue-development`** — ship slice (YAML hygiene, stage0 golden EOF, commits); **push blocked** (SSH timeout to `github.com:22` from agent env) | **meta:** task `updated:` YAML spacing; **sv0c:** golden `lower_store_value_to_slot_core.c` trailing newline; local commits on `sv0c` **7b6232f** + **9e0b8e7** | *(metrics unchanged vs prior row)* | `./scripts/sv0 test-guards`, `./scripts/sv0 test` |
| 2026-04-11 (America/Denver) | **`continue-development`** — sv0c checklist **2/6** + **`storeValueToSlot`** seed | **sv0c:** `PROGRESS.md` (**C-1**, **C-2**); `lib/lower_store_value_to_slot_core.sv0`, lists + golden, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`; **meta:** M3 task + checklist, rollup Summary | sv0c checklist **0/6→2/6** (**33%**); pilots **48→49**; stage0 **58→59** | `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards`, `./scripts/sv0 self-host-check-golden`, `./scripts/sv0 test` |
| 2026-04-10 (America/Denver) | M3 / **`continue-development`** — **`ensGlue`** + **`injectEnsuresAndRetSlot`** harness | **sv0c:** `lib/lower_ens_glue_inject_core.sv0`, lists + `lib/golden/stage0/lower_ens_glue_inject_core.c`, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`, `PROGRESS.md`; **meta:** M3 task + checklist `.Rmd` | Self-host pilots **47→48**; stage0 goldens **57→58**; sv0c **0/6** unchanged | `./scripts/sv0 test-guards`, `./scripts/sv0 self-host-check-golden`, `./scripts/sv0 test` |
| 2026-04-09 (America/Denver) | `task/sv0-toolchain-milestone-3-self-host.Rmd` — **`reqInstrs`** harness slice | **sv0c:** `lib/lower_req_instrs_core.sv0`, `lib/bootstrap-sources.list`, `lib/self-host-sv0-loop.list`, `lib/golden/stage0/lower_req_instrs_core.c`, `doc/transliteration-plan.md`, `lib/LAYOUT.md`, `doc/self-host-sv0-loop.md`, `PROGRESS.md`; **meta:** M3 task + M3 checklist `.Rmd` (decomposition table, refinement log, pilot count) | Self-host pilots **46→47**; stage0 goldens **56→57**; sv0c checklist **0/6** unchanged | `./scripts/sv0 test-guards`, `./scripts/sv0 self-host-check-golden`, `./scripts/sv0 test` |
| 2026-04-09 | Integrate milestone-orient + progress ledger; META-2 closure | meta (full diff: `scripts/sv0`, guards, CI, `AGENTS.md`, `task/milestone-orientation.json`, `.cursor/`, `task/sv0-toolchain-workspace.Rmd`); progress rollup + workspace doc sync | Meta checklist **80%→100%** (META-2 verified via `01-verify-roadmap-artifacts.sh`) | `bash task/sv0-toolchain-roadmap-full/01-verify-roadmap-artifacts.sh`, `./scripts/sv0 test-guards` |
| 2026-04-09 | Reverse workspace↔JSON milestone index | `scripts/verify_workspace_milestone_table.py`, `task/milestone-orientation.json`, `task/sv0-toolchain-workspace.Rmd` frontmatter | Table paths must ⊆ JSON `primary_tasks`; optional `workspace_milestone_table_allowlist` | `python3 scripts/verify_workspace_milestone_table.py --root .`, `./scripts/sv0 test-guards` |
| 2026-04-09 | CI: explicit full `sv0 test` + workspace↔JSON drift guard | meta (`.github/workflows/ci.yml`, `scripts/verify_workspace_milestone_table.py`, `task/sv0-toolchain-workspace.Rmd` YAML) | Meta 75%→80% (META-5); forward inclusion JSON→workspace | `python3 scripts/verify_workspace_milestone_table.py --root .`, `./scripts/sv0 test-guards` |
| 2026-04-09 | Milestone orientation guard + Make + CI | meta (`Makefile`, `.github/workflows/ci.yml`, `scripts/verify_milestone_orientation.py`, `task/sv0-toolchain-workspace.Rmd`) | Meta checklist 67%→75% (META-4); `test-guards` includes JSON/path check | `python3 scripts/verify_milestone_orientation.py --root .`, `./scripts/sv0 test-guards` |
| 2026-04-09 | Milestone-driven LLM workflow | meta (`task/`, `scripts/`, `.cursor/`, `AGENTS.md`, `README.md`) | Meta checklist 50%→67% (META-3 done); orient loop documented | `./scripts/sv0 milestone-orient list`, `./scripts/sv0 milestone-orient show M3`, `./scripts/sv0 test-guards` |
| 2026-04-09 (seed) | Introduce hybrid progress ledger | meta, sv0doc, sv0c, sv0vm, sv0-mcp | Meta rollup 0%→50% (META-1); submodule checklists seeded at 0% | *(none — documentation-only seed)* |
| *(add the next row above this line)* | | | | |

## Progress contract (for agents)

A session **improves tracking** if at least one holds:

1. **Measurable:** `Done` increases for some item, or `Total` changes with an explicit rationale (smaller scope or newly discovered work).
2. **Explainable:** a new **run log** row records a **blocker**, **recon-only** outcome, or **decomposition** update with the next concrete step.

Cosmetic rewording without a run log entry does **not** satisfy the contract.

## Pointers

- LLM milestone loop + anti-patterns: `AGENTS.md`, `.cursor/rules/37-llm-milestone-driven-workflow.mdc`, `task/milestone-orientation.json`, `./scripts/sv0 milestone-orient`
- Milestone bar and decomposition: `task/sv0-toolchain-milestone-3-self-host.Rmd`, `task/sv0-toolchain-milestone-3-checklist.Rmd`
- Roadmap index: `task/sv0-toolchain-roadmap-full.Rmd`
- Cursor commands: `.cursor/commands/continue-development.md`, `.cursor/commands/thoroughly-execute-document.md`
