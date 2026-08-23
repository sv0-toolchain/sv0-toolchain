# task/ — planning & milestone tracking

This directory is the **planning layer** of the toolchain: one `.Rmd` file per
milestone or work area, each with YAML front-matter (`state:`) and, where relevant,
a sibling directory of verification shell scripts. Agents run a task with
`.agent/runner.sh task/<name>.Rmd`; humans orient with
`./scripts/sv0 milestone-orient list`.

- **Normative spec** lives in **`sv0doc/`** (grammar, types, contracts, memory model).
- **Compiler internals** live in **`sv0c/doc/`** (pass-by-pass, self-host, cli-parity).
- **Planning / status** lives here.

## active

| task | state | what |
|---|---|---|
| [`sv0-toolchain-milestone-5-llvm-crypto.Rmd`](sv0-toolchain-milestone-5-llvm-crypto.Rmd) | draft | **next milestone** — LLVM IR backend + production crypto |
| [`sv0-toolchain-milestone-6-kernel.Rmd`](sv0-toolchain-milestone-6-kernel.Rmd) | draft | `asm!`, boot/link, HAL, minimal kernel |
| [`sv0-toolchain-milestone-cross-cutting.Rmd`](sv0-toolchain-milestone-cross-cutting.Rmd) | draft | macros, literate `.sv0.md`, `std`/concurrency, packaging |
| [`sv0-vsc-extension-plan.Rmd`](sv0-vsc-extension-plan.Rmd) · [`…-checklist.Rmd`](sv0-vsc-extension-checklist.Rmd) | draft | VS Code extension |

## index & rollups

| task | what |
|---|---|
| [`sv0-toolchain-roadmap-full.Rmd`](sv0-toolchain-roadmap-full.Rmd) | roadmap across all milestones (M0–M6 + cross-cutting) |
| [`sv0-toolchain-workspace.Rmd`](sv0-toolchain-workspace.Rmd) | workspace map, env vars, aggregate commands, milestone table |
| [`milestone-orientation.json`](milestone-orientation.json) | machine-readable milestone index (`./scripts/sv0 milestone-orient`) |
| [`sv0-toolchain-progress.md`](sv0-toolchain-progress.md) | run log + progress rollup |
| [`agent-workflow-and-milestone-tracking.md`](agent-workflow-and-milestone-tracking.md) | how the `.Rmd` task system + tracking work |

## completed milestones (hubs kept here; sub-tasks archived)

| milestone | hub | state |
|---|---|---|
| M0 — formal spec | [`sv0doc-milestone-0.Rmd`](sv0doc-milestone-0.Rmd) | complete |
| M1 — bootstrap compiler (SML) | [`sv0c-milestone-1.Rmd`](sv0c-milestone-1.Rmd) | complete |
| M2 — bytecode VM + prep | [`sv0vm-milestone-2.Rmd`](sv0vm-milestone-2.Rmd) · [`…-milestone-2-prep.Rmd`](sv0-toolchain-milestone-2-prep.Rmd) | complete |
| M3 — self-hosting compiler | [`…-milestone-3-self-host.Rmd`](sv0-toolchain-milestone-3-self-host.Rmd) · [checklist](sv0-toolchain-milestone-3-checklist.Rmd) | complete |
| M4 — advanced verification | [`…-milestone-4-verification.Rmd`](sv0-toolchain-milestone-4-verification.Rmd) · [checklist](sv0-toolchain-milestone-4-checklist.Rmd) | complete |
| MCP-0 — dev graph | [`sv0-mcp-milestone-0.Rmd`](sv0-mcp-milestone-0.Rmd) | complete |

## archive/

[`archive/`](archive/) holds the **completed granular sub-tasks** (with their
verification-script dirs) that fed the milestones above — the M0/M1/M2 component
tasks (lexer, parser, resolver, checker, IR, C backend, VM, spec extraction, …), the
M4 Epic A–E sub-tasks (`sv0c-contract-vcgen`, `-smt-backend`, `-verify-cli`,
`-refinement-types`, `-verify-pilots`), and `m4-closure-evidence.md`. They are done;
kept for provenance. The milestone hubs above are the entry points.
