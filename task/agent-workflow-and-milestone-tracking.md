# Agent workflow and milestone tracking (sv0-toolchain)

This note ties together **milestone orientation data** (`task/milestone-orientation.json`), the **progress ledger** (`task/sv0-toolchain-progress.md` plus submodule `PROGRESS.md` files), and **external guidance** on building reliable LLM-driven automation.

## External reference

Anthropic’s [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) (Dec 2024) distinguishes **workflows** (LLMs and tools follow **predefined code paths**) from **agents** (the LLM **dynamically** directs process and tool use). It recommends **starting simple**, adding multi-step agentic systems only when simpler approaches fail, and following three principles: **simplicity**, **transparency** (show planning steps), and a strong **agent–computer interface** (clear tool docs and tests).

Common **workflow** patterns they name include **prompt chaining** (decompose into steps with gates), **routing** (classify then dispatch), **parallelization** (sectioning or voting), **orchestrator–workers**, and **evaluator–optimizer** (generate / evaluate loops when criteria are clear).

## How this repository maps


| Anthropic idea                 | sv0-toolchain expression                                                                                                                                                                                                                                         |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Workflow / prompt chaining** | Slash commands (e.g. **continue-development**, **thoroughly-execute-document**) with explicit phases: recon → plan → execute → validate → record. Owning `**task/*.Rmd`** files define completion criteria, not ad-hoc chat goals.                               |
| **Gates**                      | `**./scripts/sv0 test-guards`** for fast structural checks; `**./scripts/sv0 test**` (and narrower `**vm-compile**` / `**emit-c**` / `**self-host-capture-stage0**`) for integration truth; `**gh run watch**` after pushes (`**40-validation-and-proof.mdc**`). |
| **Routing**                    | `**./scripts/sv0 milestone-orient show <id>`** picks the **owning task** and `**submodules_hint`**; workspace rules (`**00-workspace-context.mdc**`) route semantics to `**sv0doc/**`, implementation to `**sv0c/**`, `**sv0vm/**`, `**sv0-mcp/**`.              |
| **Parallelization**            | Safe **only** for disjoint paths (e.g. read-only recon across submodules). **Serialise** shared files, submodule pointers, and normative semantics.                                                                                                              |
| **Orchestrator–workers**       | The **orchestrator** (parent agent) merges subagent output; **Task** / delegated agents match “workers” when scopes are explicit and non-overlapping.                                                                                                            |
| **Evaluator–optimizer**        | **Tests and CI logs** are the evaluator: red `**./scripts/sv0 test`** or GitHub Actions → fix → re-run. This is the strongest fit for **coding** slices (see Anthropic appendix on coding agents).                                                               |
| **Ground truth**               | **Tool and script results** (terminal output, golden files, parity artifacts), `**sv0doc/`** for **normative** language behavior — not model confidence.                                                                                                         |
| **Human checkpoints**          | `**34-user-prompts-design-only.mdc`**: one design question at a time when intent would otherwise be invented; stakeholder bars in tasks (e.g. **M3** / SML retirement) that scripts cannot close alone.                                                          |


**Net:** this workspace is **mostly workflow-first**, with **selective** autonomy inside a bounded slice. Full “agent until M3 is done” is explicitly **not** the model (`**37-llm-milestone-driven-workflow.mdc`**).

## Deeper milestone tracking (`milestone-orientation.json`)

Beyond `**primary_tasks**`, `**pre_merge_validation**`, `**closure_authority**`, and `**anti_patterns**`, each milestone entry may include:

- `**automation_profile**` — One-line description of how automation and humans typically share work for that milestone.
- `**ground_truth**` — Bullet list of **what counts as evidence** (commands, directories, or authorities).
- `**human_checkpoints`** — When to **stop** for human judgment before coding or shipping.
- `**success_signals`** — Observable signals that the milestone **advanced** responsibly (not a substitute for reading the owning `**task/*.Rmd`**).

Run `**./scripts/sv0 milestone-orient show M3**` (or any id) to print these fields alongside the existing orientation block.

## What to read next

1. `**AGENTS.md**` — entrypoints and validation table.
2. `**task/milestone-orientation.json**` — machine index; keep in sync with `**task/sv0-toolchain-workspace.Rmd**` milestone table (`**verify_workspace_milestone_table.py**`).
3. **Owning `task/*.Rmd`** for the milestone you are driving — sole source for **definition of done**.
4. `**sv0doc/`** — normative semantics when the change is language- or bytecode-visible.