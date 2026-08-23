# Contributing to sv0-toolchain

This is the developer/maintainer guide. For an orientation to the project, start
with the [README](README.md). For LLM/agent on-ramping, see [AGENTS.md](AGENTS.md)
and `./scripts/sv0 milestone-orient`.

## the `sv0` driver

`./scripts/sv0` (from the toolchain root) drives everything. Run it with no
arguments for the full command list. The ones you'll use most:

```bash
./scripts/sv0 check          # fast smoke: sv0c heap + native compiler + load sv0vm
./scripts/sv0 test           # full gate: units, Python guards, C+VM integration,
                             #   bootstrap .sv0, VM parity, stage0 goldens, self-host loop, doctests
./scripts/sv0 test-guards    # the Python guards only (fast, no SML)
./scripts/sv0 ci             # check + full test
./scripts/sv0 fmt            # .sv0 + shell formatting
./scripts/sv0 doctest        # Markdown doctests
```

Inner loop (paths relative to `sv0c/`):

```bash
./scripts/sv0 emit-c <rel>          # print the C a file compiles to
./scripts/sv0 vm-compile <rel>      # compile to bytecode (--target=vm)
./scripts/sv0 vm-run <sv0b>         # run bytecode on sv0vm
./scripts/sv0 self-host-sv0-loop    # the sv0→sv0 self-hosting loop (native, behavioral parity)
```

Per-submodule: `make -C sv0c check test`, `make -C sv0vm check test`,
`cd sv0-mcp && uv sync && uv run pytest tests/`.

## git hooks

Install once per clone (idempotent; wires `core.hooksPath` for both the parent
and the `sv0c` submodule):

```bash
make hooks            # or: ./scripts/install-git-hooks.sh
```

The tracked source is `scripts/git-hooks/` + `scripts/verify_commit_msg_no_ai_signoff.py`.

| hook | when | checks |
|---|---|---|
| `commit-msg` | every commit (parent + sv0c) | **rejects AI/agent sign-off** — `Co-Authored-By:`/`Signed-off-by:`/`Generated with …` lines naming an AI, and the `🤖` signature. Topic mentions (e.g. `fix: Claude API retry`) pass. |
| `pre-commit` | every commit (fast) | `.sv0` formatting + block-comment guard, `bash -n` on shell, `ruff` on sv0-mcp Python, and documentation pins + fast guards (`./scripts/sv0 test-guards`). |
| `pre-push` | every push (slow, needs SML) | full test suite — parent `./scripts/sv0 test`; sv0c `make check test`. |

Bypass one run with `--no-verify`, or disable for a shell with `SV0_SKIP_HOOKS=1`.

## submodule bumps (maintainers)

When you bump a submodule, update the pinned SHA in the [README](README.md)
**sv0c** table in the same commit. CI enforces the README↔gitlink match via
`scripts/verify_readme_sv0c_gitlink.py`. Confirm the staged gitlink with
`git ls-files -s sv0c`.

If `git push` over SSH port 22 times out, use
`./scripts/with-github-ssh443.sh git push …` (SSH over 443).

## the agent task system

Development is organized with `.Rmd` task files under `task/` (the
[AI agent workflow structure](http://development.sasankvishnubhatla.net/tcowmbh/note/ai-agent-workflow-structure.html)).
Each `.Rmd` orchestrates a slice of work through directives + companion scripts.

```bash
.agent/runner.sh --dry-run task/sv0-toolchain-milestone-5-llvm-crypto.Rmd  # inspect a task
.agent/runner.sh task/archive/sv0c-lexer.Rmd                               # run a (completed) task
```

Cursor IDE: numbered rule modules live under `.cursor/rules/` (start at
`00-workspace-context.mdc`); open any `.Rmd` and use `/run-ai-tasks-in-doc`.

**Start at [`task/README.md`](task/README.md)** — the planning index (active work,
milestone hubs, and the archive of completed sub-tasks). Milestone map:

```
task/sv0doc-milestone-0.Rmd                    M0 spec extraction                     complete
task/sv0c-milestone-1.Rmd                      M1 bootstrap compiler (SML)            complete
task/sv0vm-milestone-2.Rmd                     M2 bytecode VM (+ -2-prep)             complete
task/sv0-toolchain-milestone-3-self-host.Rmd   M3 self-hosting compiler (+ checklist) complete
task/sv0-toolchain-milestone-4-verification.Rmd M4 advanced verification (+ checklist) complete
task/sv0-toolchain-milestone-5-llvm-crypto.Rmd M5 LLVM + production crypto (+ checklist) active (current)
task/sv0-toolchain-milestone-6-kernel.Rmd      M6 kernel development                  draft
task/sv0-toolchain-milestone-cross-cutting.Rmd macros/std/packaging (multi-milestone) draft
task/sv0-toolchain-roadmap-full.Rmd            roadmap index (all milestones)
task/sv0-toolchain-workspace.Rmd               workspace map, env vars, milestone table
task/sv0-toolchain-progress.md                 run log + progress rollup
task/archive/                                  completed granular sub-tasks (provenance)
```

## the dev graph (sv0-mcp)

After editing `task/*.Rmd` milestones or normative `sv0doc/` files, resync the
Neo4j graph so MCP queries stay current:

```bash
cd sv0-mcp && ./scripts/sync-graph.sh all      # after: docker compose up -d neo4j
```

If Bolt is not on the default host port `7688`, set `SV0_MCP_NEO4J_URI` (and the
cypher MCP `NEO4J_URI`) — see [sv0-mcp/README.md](sv0-mcp/README.md).
