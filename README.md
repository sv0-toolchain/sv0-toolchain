# sv0-toolchain

development workspace for the sv0 programming language compiler and toolchain.

## subprojects

| project | purpose | language | status |
|---|---|---|---|
| [sv0doc](sv0doc/) | **documentation hub**: formal language spec, bytecode spec, roadmap links to vision doc | markdown | **Milestone 0 (task) complete**; bytecode under `bytecode/`; hub text in [sv0doc/README.md](sv0doc/README.md) |
| [sv0c](sv0c/) | compiler implementation + in-repo docs (`doc/`) | SML/NJ | **Milestones 1–2 (task) complete** — C backend + VM backend (`--target=vm`, `--target=vm --project`) |
| [sv0vm](sv0vm/) | bytecode VM interpreter implementation + notes | SML/NJ | **Milestone 2 (task) complete** |
| [sv0-mcp](sv0-mcp/) | MCP server + Neo4j graph to aid developing / debugging the toolchain | Python | tracked under **`task/sv0-mcp-milestone-0.Rmd`** |

**Design milestones 0–2 (task-tracked)** are **met** at the level described in [`task/sv0-toolchain-roadmap-full.Rmd`](task/sv0-toolchain-roadmap-full.Rmd). **Milestone 3** (self-hosting compiler in **sv0**) is **in progress** — see [`task/sv0-toolchain-milestone-3-self-host.Rmd`](task/sv0-toolchain-milestone-3-self-host.Rmd) for definition of done vs remaining transliteration work; it is **not** closable by documentation alone.

**Tracking:** start from [`task/sv0-toolchain-workspace.Rmd`](task/sv0-toolchain-workspace.Rmd) for the full workspace map, env vars, and submodule checks.

## agent workflow

this workspace uses the [AI agent workflow structure](http://development.sasankvishnubhatla.net/tcowmbh/note/ai-agent-workflow-structure.html) to organize development work. agent files (`.Rmd`) in `task/` orchestrate implementation through directives and companion scripts.

**Cursor IDE:** numbered rule modules under **`.cursor/rules/`** (start with **`00-workspace-context.mdc`**) spell out boundaries for **sv0c**, **sv0vm**, **sv0-mcp**, spec-first work, and **`.Rmd`** tasks. they sit alongside **`.cursor/rules/agent-directives.mdc`**, which defines how to execute **`task/*.Rmd`** directives.

### milestone structure

```
task/sv0doc-milestone-0.Rmd       milestone 0: extract formal specification
  ├── sv0doc-extract-grammar.Rmd      EBNF grammar
  ├── sv0doc-extract-type-rules.Rmd   type system rules
  ├── sv0doc-extract-contracts.Rmd    contract semantics
  ├── sv0doc-extract-memory-model.Rmd memory model
  └── sv0doc-extract-keywords.Rmd     keyword/operator reference

task/sv0c-milestone-1.Rmd         milestone 1: bootstrap compiler
  ├── sv0c-project-setup.Rmd          SML/NJ project scaffolding
  ├── sv0c-error-reporting.Rmd        error infrastructure
  ├── sv0c-lexer.Rmd                  tokenizer
  ├── sv0c-parser.Rmd                 recursive descent parser + AST
  ├── sv0c-name-resolution.Rmd        scope resolution
  ├── sv0c-type-checker.Rmd           type inference and checking
  ├── sv0c-contract-analyzer.Rmd      contract validation + runtime checks
  ├── sv0c-ir.Rmd                     intermediate representation
  └── sv0c-c-backend.Rmd              C99 code generation

task/sv0vm-milestone-2.Rmd        milestone 2: bytecode VM
  ├── sv0vm-bytecode-format.Rmd       instruction set + binary format
  ├── sv0vm-interpreter.Rmd           stack machine dispatch loop
  ├── sv0vm-runtime.Rmd               memory management + built-ins
  └── sv0vm-vm-backend.Rmd            sv0c VM backend (IR -> bytecode)

task/sv0-toolchain-milestone-2-prep.Rmd   milestone 2 prep: sv0 test, doctest, fmt, doc, lib/ bootstrap track
task/sv0-toolchain-roadmap-full.Rmd       option C roadmap index (milestones 2–6 + cross-cutting)

task/sv0-toolchain-workspace.Rmd   meta: four submodules, env, aggregate commands
task/sv0-mcp-milestone-0.Rmd       MCP server, sync, tests, doc alignment
```

### developer commands (toolchain root)

```bash
make help             # lists make targets; "make test" help matches ./scripts/sv0 test pipeline
./scripts/sv0 check   # compile sv0c + load sv0vm (fast)
./scripts/sv0 test    # sv0c units; block-comment guard; sv0doc baseline; task/*.Rmd YAML lint; sv0vm bytecode; C+VM integration; bootstrap .sv0; stage0 golden C; doctests
./scripts/sv0 doctest  # Markdown doctests only (see task/sv0-toolchain-milestone-2-prep/doctests.md)
./scripts/sv0 fmt     # .sv0 whitespace (scripts/fmt_sv0.py) + shell fmt (fmt-shell)
./scripts/sv0 fmt-shell  # bash -n / shfmt on repo shell scripts only
./scripts/sv0 doc     # generate build/sv0-toolchain-doc/index.md; verify sv0doc paths
./scripts/sv0 bootstrap-build  # VM-compile entries in sv0c/lib/bootstrap-sources.list (exit 0)
./scripts/sv0 test-mcp   # sv0-mcp pytest via uv (skips if uv missing)
./scripts/sv0 repl    # line-at-a-time eval (VM): i32 expr or println("...")
./scripts/sv0 ci      # check + full ./scripts/sv0 test (no sv0-mcp)
./scripts/sv0 ci-all  # ci, then sv0-mcp pytest when uv is installed
```

**Neo4j dev graph (sv0-mcp):** after you change **`task/*.Rmd`** milestones or normative **sv0doc** files, run `cd sv0-mcp && ./scripts/sync-graph.sh all` so MCP queries stay in sync (or use the **sv0-graph** MCP **`sync_graph`** tool).

From **sv0c**: `make check` (compile only), `make integration-vm` (same as `./scripts/sv0 integration-vm`). From **sv0vm**: `make check`, `make test`. From **sv0-mcp**: `uv sync && uv run pytest tests/`.

### running agents

```bash
# via CLI runner
.agent/runner.sh task/sv0c-lexer.Rmd

# dry run (show what would execute)
.agent/runner.sh --dry-run task/sv0c-milestone-1.Rmd

# via Cursor: open any .Rmd file and use /run-ai-tasks-in-doc
```

### dependency flow

```
sv0doc (spec + hub pointers)
  |
  v
sv0c (compiler)
  |
  ├── C backend (milestone 1)
  └── VM backend (milestone 2) ---> sv0vm (interpreter)

sv0-mcp (graph + MCP tools) — cross-cuts spec, compiler, VM, and task/ for development
```

## design document

the language design is documented at:
<http://development.sasankvishnubhatla.net/tcowmbh/task/sv0-compiler-vision-and-design.html>

## directory layout

```
sv0-toolchain/
├── .agent/          agent infrastructure (runner, config, adapters)
├── .cursor/         cursor IDE integration (rules, commands)
├── lib/             shared scripts (shell utilities, SML helpers)
├── scripts/         aggregate driver (`sv0`) for check/test/ci
├── task/            agent workflow files (.Rmd) + companion scripts
├── sv0doc/          specification + documentation hub (git submodule)
├── sv0c/            compiler (git submodule)
├── sv0vm/           bytecode VM (git submodule)
└── sv0-mcp/         MCP server + graph sync (git submodule)
```
