# sv0-toolchain

Development workspace for **sv0**, a Rust-like systems language with built-in
contracts (`requires` / `ensures` / `loop_invariant`). This meta-repo pins four
submodules that together form the language, its self-hosting compiler, a bytecode
VM, and developer tooling.

## the subprojects

| project | what it is | language | status |
|---|---|---|---|
| [**sv0doc**](sv0doc/) | the language + bytecode **specification** (grammar, types, contracts, memory model, keywords) — the source of truth | Markdown | spec complete (M0) |
| [**sv0c**](sv0c/) | the **compiler** — `.sv0` → C and → bytecode. **Self-hosting**: written in sv0, compiles itself | sv0 (+ retired SML reference) | self-hosting; M3 complete + post-M3 hardening done |
| [**sv0vm**](sv0vm/) | the **bytecode VM** that runs sv0c's `--target=vm` output | SML/NJ | M2 complete |
| [**sv0-mcp**](sv0-mcp/) | Neo4j knowledge graph + MCP servers for AI-assisted development | Python | M0 complete |

**Dependency flow:** sv0doc (spec) → sv0c (compiler) → C backend + VM backend →
sv0vm. sv0-mcp cross-cuts all of them.

## start here

New to the toolchain? Read in this order:

1. **[sv0c/README.md](sv0c/README.md)** — how the compiler is structured and how
   to run it. This is the heart of the project.
2. **[sv0c/examples/learn/](sv0c/examples/learn/README.md)** — numbered `.sv0`
   tutorials (`01_hello.sv0` … `22_*.sv0`, plus a multi-file project) you can
   compile and run.
3. **[sv0doc/](sv0doc/README.md)** — the language spec, when you want the precise
   rules ([type system](sv0doc/type-system/rules.md),
   [contracts](sv0doc/contracts/semantics.md),
   [memory model](sv0doc/memory-model/ownership.md)).
4. **[sv0c/doc/](sv0c/doc/README.md)** — deeper compiler documentation (pass-by-pass
   walkthrough, self-hosting, archived milestone history).

## quickstart

```bash
git clone --recurse-submodules <this-repo>
cd sv0-toolchain

./scripts/sv0 test                 # full gate: units, integration, VM parity, self-host loop
./scripts/sv0 vm-compile sv0c/examples/learn/01_hello.sv0   # compile a program to bytecode
./scripts/sv0 vm-run build/vm/01_hello.sv0b                 # run it on sv0vm
./scripts/sv0 emit-c <path-relative-to-sv0c/>              # see the C a file compiles to
./scripts/sv0 repl                 # line-at-a-time evaluation
```

`./scripts/sv0` is the single driver for the whole workspace; run it with no
arguments for the full command list. See **[CONTRIBUTING.md](CONTRIBUTING.md)**
for the developer workflow, git hooks, the agent task system, and maintainer
notes.

## status

Design **milestones 0–2** (spec, C-backend compiler, bytecode VM) are complete,
and **milestone 3** — a self-hosting compiler written in sv0 — is closed
(closure ruling 2026-08-05). The **native sv0-built compiler is now the default**;
the original SML bootstrap is a retired reference. Post-M3 hardening
(whole-language parity + native-default promotion) is complete. Details:
[task/sv0-toolchain-progress.md](task/sv0-toolchain-progress.md) and
[task/sv0-toolchain-roadmap-full.Rmd](task/sv0-toolchain-roadmap-full.Rmd).

## repository layout

```
sv0-toolchain/
├── scripts/         the `sv0` driver + CI verifiers
├── task/            project tracking: milestones, roadmap, progress (.Rmd + progress.md)
├── lib/             shared shell/SML helpers
├── .agent/ .cursor/ agent + IDE integration
├── sv0doc/          specification + documentation hub   (submodule)
├── sv0c/            compiler                              (submodule)
├── sv0vm/           bytecode VM                           (submodule)
└── sv0-mcp/         MCP server + graph sync               (submodule)
```

## pinned sv0c commit

This meta-repo records the sv0c submodule commit next to the SML retirement tag
so a checkout can be correlated with the compiler sources. Maintainers: bump this
SHA in the same commit as any `sv0c` submodule bump (CI enforces the match via
`scripts/verify_readme_sv0c_gitlink.py`; confirm with `git ls-files -s sv0c`).

| | |
|---|---|
| **sv0c tag (when cut)** | `bootstrap-sml-final` |
| **sv0c commit pinned on `main`** | `2e20dcf918e21c3a54fa4300e9039653a429693a` |

## design document

The language vision and design narrative:
<http://development.sasankvishnubhatla.net/tcowmbh/task/sv0-compiler-vision-and-design.html>
