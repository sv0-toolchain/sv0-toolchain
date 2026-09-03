# sv0-toolchain

Development workspace for **sv0**, a Rust-like systems language with built-in
contracts (`requires` / `ensures` / `loop_invariant`). This meta-repo pins six
submodules that together form the language, its self-hosting compiler, a bytecode
VM, numeric and strings libraries, and developer tooling.

## the subprojects

| project | what it is | language | status |
|---|---|---|---|
| [**sv0doc**](sv0doc/) | the language + bytecode **specification** (grammar, types, contracts, memory model, keywords) — the source of truth | Markdown | spec complete (M0) |
| [**sv0c**](sv0c/) | the **compiler** — `.sv0` → C and → bytecode. **Self-hosting**: written in sv0, compiles itself; **`sv0 verify`** static contract verification (M4) | sv0 (+ retired SML reference) | self-hosting (M3); advanced verification (M4) complete |
| [**sv0vm**](sv0vm/) | the **bytecode VM** that runs sv0c's `--target=vm` output | SML/NJ | M2 complete |
| [**sv0-mathlib**](sv0-mathlib/) | a contract-first **numeric library** (arith, modular, trig, polar, complex) written in pure sv0 — also a cross-backend conformance load for the compiler | sv0 | `v0.1.0` — SPEC R1 gate closed |
| [**sv0-strings**](sv0-strings/) | a safe **strings library** — sv0-native bytes / UTF-8 / `CStr` plus C23 & POSIX.1-2024 `<string.h>`/`<strings.h>` compatibility façades, built spec-first | sv0 | pre-F0 — SPEC `v0.4.0-draft` |
| [**sv0-mcp**](sv0-mcp/) | Neo4j knowledge graph + MCP servers for AI-assisted development | Python | M0 complete |

**Dependency flow:** sv0doc (spec) → sv0c (compiler) → C backend + VM backend →
sv0vm. sv0-mathlib and sv0-strings consume the compiler (sv0-mathlib's
cross-backend parity feeds back into `./scripts/sv0 test`; sv0-strings is
spec-first and pre-F0). sv0-mcp cross-cuts all of them.

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
5. **[task/README.md](task/README.md)** — the **planning index**: active milestones,
   milestone hubs, and the archive of completed sub-tasks.

**Where docs live:** normative spec → [`sv0doc/`](sv0doc/README.md); compiler
internals → [`sv0c/doc/`](sv0c/doc/README.md); planning & milestone status →
[`task/`](task/README.md).

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

Design **milestones 0–4 are complete.** M0–M2 (spec, C-backend compiler, bytecode
VM); **M3** — a self-hosting compiler written in sv0 — closed 2026-08-05 (the native
sv0-built compiler is the default; the SML bootstrap is a retired reference);
post-M3 hardening (whole-language parity + native-default promotion) done; and
**M4 — advanced verification** (SMT-backed `sv0 verify`, verified contract-mode,
refinement types, modular verification) closed 2026-08-22. The next milestone is
**M5 — LLVM backend + production crypto**. Status detail:
[task/README.md](task/README.md),
[task/sv0-toolchain-progress.md](task/sv0-toolchain-progress.md), and
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
├── sv0-mathlib/     numeric library in pure sv0           (submodule)
├── sv0-strings/     safe strings + C23/POSIX compat lib   (submodule)
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
| **sv0c commit pinned on `main`** | `a5896b5d71bdd60d212d887b2477e80abb3ee654` |

## design document

The language vision and design narrative:
<http://development.sasankvishnubhatla.net/tcowmbh/task/sv0-compiler-vision-and-design.html>

## license

Licensed under either of [Apache License, Version 2.0](LICENSE-APACHE) or
[MIT license](LICENSE-MIT) at your option. This applies to this meta-repo and
to each of the sv0c, sv0vm, sv0doc, sv0-mathlib, sv0-strings, and sv0-mcp
submodules (sv0-mathlib and sv0-strings also carry their own LICENSE files).
