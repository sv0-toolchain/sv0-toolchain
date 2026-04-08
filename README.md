# sv0-toolchain

development workspace for the sv0 programming language compiler and toolchain.

## subprojects

| project | purpose | language | status |
|---|---|---|---|
| [sv0doc](sv0doc/) | **documentation hub**: formal language spec, bytecode spec, roadmap links to vision doc | markdown | **Milestone 0 (task) complete**; bytecode under `bytecode/`; hub text in [sv0doc/README.md](sv0doc/README.md) |
| [sv0c](sv0c/) | compiler implementation + in-repo docs (`doc/`) | SML/NJ | **Milestones 1–2 (task) complete** — C backend + VM backend (`--target=vm`, `--target=vm --project`) |
| [sv0vm](sv0vm/) | bytecode VM interpreter implementation + notes | SML/NJ | **Milestone 2 (task) complete** |
| [sv0-mcp](sv0-mcp/) | MCP server + Neo4j graph to aid developing / debugging the toolchain | Python | **Milestone 0 (task) complete** — see **`task/sv0-mcp-milestone-0.Rmd`** |

**Design milestones 0–2 (task-tracked)** are **met** at the level described in [`task/sv0-toolchain-roadmap-full.Rmd`](task/sv0-toolchain-roadmap-full.Rmd). **Milestone 3** (self-hosting compiler in **sv0**) is **in progress** — see [`task/sv0-toolchain-milestone-3-self-host.Rmd`](task/sv0-toolchain-milestone-3-self-host.Rmd) for definition of done vs remaining transliteration work; it is **not** closable by documentation alone.

**Tracking:** start from [`task/sv0-toolchain-workspace.Rmd`](task/sv0-toolchain-workspace.Rmd) for the full workspace map, env vars, and submodule checks.

**Learning:** small **`.sv0`** sources (numbered tutorials through **`19_loop_invariant.sv0`**) and commands for **`vm-compile`** / **`vm-run`** / **`emit-c`** are under [`sv0c/examples/learn/`](sv0c/examples/learn/README.md). **`vm-compile`** and **`emit-c`** take paths relative to **`sv0c/`**; **`vm-run`** accepts **`sv0c/build/vm/<stem>.sv0b`** relative to this **meta-repo root** (or an absolute path).

**GitHub SSH:** if **`git push`** times out on port 22, use **`./scripts/with-github-ssh443.sh git push …`** (SSH over port 443); see [`task/sv0-toolchain-workspace.Rmd`](task/sv0-toolchain-workspace.Rmd).

## bootstrap compiler reference (support)

The SML bootstrap retirement tag **`bootstrap-sml-final`** is defined on **[sv0c](https://github.com/sv0-toolchain/sv0c) only** (see [`task/sv0-toolchain-milestone-3-self-host.Rmd`](task/sv0-toolchain-milestone-3-self-host.Rmd)). This meta-repo always records the **pinned sv0c commit** next to that tag name so support and triage can correlate a checkout with the compiler sources.

| | |
|---|---|
| **sv0c tag (when cut)** | `bootstrap-sml-final` |
| **sv0c commit pinned on this branch (`main`)** | `88f8ae0d34d8440077e6da00972249795f668d3f` |

**Maintainers:** whenever you bump the **`sv0c`** submodule, **update the SHA in this table in the same commit.** Confirm from the repo root with `git ls-tree HEAD sv0c` (submodule gitlink). **CI / local:** **`./scripts/sv0 test-guards`** runs **`scripts/verify_readme_sv0c_gitlink.py`** and **`scripts/verify_vm_parity_manifest_bootstrap.py`** (among other Python checks) so the README table matches **HEAD** and **`test/vm-parity/manifest.txt`** stays a subset of **`sv0c/lib/bootstrap-sources.list`**.

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
./scripts/sv0 test    # sv0c units; Python guards; sv0vm; C+VM integration; bootstrap .sv0; VM parity (SML .sv0b vs golden/sml); stage0 golden C; doctests
./scripts/sv0 test-guards  # Python only: same guards as start of `sv0 test` incl. vm-parity manifest ⊆ bootstrap (fast; no SML)
./scripts/sv0 doctest  # Markdown doctests only (see task/sv0-toolchain-milestone-2-prep/doctests.md)
./scripts/sv0 fmt     # .sv0 whitespace (scripts/fmt_sv0.py) + shell fmt (fmt-shell)
./scripts/sv0 fmt-shell  # bash -n / shfmt on repo shell scripts only
./scripts/sv0 doc     # generate build/sv0-toolchain-doc/index.md; verify sv0doc paths
./scripts/sv0 bootstrap-build  # VM-compile entries in sv0c/lib/bootstrap-sources.list (exit 0)
./scripts/sv0 test-mcp   # sv0-mcp pytest via uv (skips if uv missing)
./scripts/sv0 repl    # line-at-a-time eval (VM): i32 expr or println("...")
./scripts/sv0 ci      # check + full ./scripts/sv0 test (no sv0-mcp)
./scripts/sv0 ci-all  # ci, then sv0-mcp pytest when uv is installed
./scripts/capture_vm_parity_goldens.sh   # refresh sv0c/test/vm-parity/golden/sml/*.sv0b (SML --target=vm; needs sml)
./scripts/sv0 self-host-sv0-loop       # SML→C→native + diff scripts/sv0-self-host-emit-c.sh (see sv0c/doc/self-host-sv0-loop.md)
./scripts/sv0-self-host-emit-c.sh /abs/path/file.sv0   # bootstrap C emit (stdout); same contract as SV0_SELF_HOST_COMPILER
```

**Neo4j dev graph (sv0-mcp):** after you change **`task/*.Rmd`** milestones or normative **sv0doc** files, run `cd sv0-mcp && ./scripts/sync-graph.sh all` so MCP queries stay in sync (or use the **sv0-graph** MCP **`sync_graph`** tool). If Bolt is not on the default host port **`7688`**, set **`SV0_MCP_NEO4J_URI`** (and the cypher MCP **`NEO4J_URI`**) — see [`sv0-mcp/README.md`](sv0-mcp/README.md) (*custom host ports*).

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
