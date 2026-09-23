# Changelog

Notable changes to the **sv0-toolchain** meta-repository and its pinned core
submodules (`sv0doc`, `sv0c`, `sv0vm`, `sv0-mcp`). The `sv0-mathlib` and
`sv0-strings` libraries version independently (see their own repos).

The project uses semantic versioning from `v0.1.0` onward.

## v0.1.0 — 2026-09-23

First tagged release of the sv0 toolchain: a Rust-like systems language with
built-in contracts (`requires` / `ensures` / `loop_invariant`), a **self-hosting**
compiler, two code-generation backends, a bytecode VM, SMT-backed static
verification, and native executable output.

All four core components are pinned and tagged at **v0.1.0**.

### Components
- **sv0doc** — the formal language + bytecode specification (grammar, type system,
  contracts, memory model). The source of truth.
- **sv0c** — the compiler, written in sv0 and self-hosting: `sv0 → C` (native
  mega-TU) and `sv0 → bytecode` backends; SMT-backed `sv0 verify` with verified
  contract-mode, refinement types, and modular verification; native executable
  output (`sv0 native-compile` / `--emit=exe`).
- **sv0vm** — the bytecode VM that runs `sv0c --target=vm` output; f64/i64 support
  with cross-backend behavioral parity.
- **sv0-mcp** — Neo4j knowledge graph + MCP servers for development.

### Milestones delivered
- **M0** — formal specification.
- **M1** — bootstrap compiler (SML reference, since retired to a reference).
- **M2** — bytecode VM + sv0c VM backend.
- **M3** — self-hosting compiler in sv0 (self-host loop 99/99; the native binary
  is the default compiler).
- **M4** — advanced verification (SMT-backed `sv0 verify`, verified contract-mode,
  refinement types, modular/trait/cast contracts).
- Plus the **native-executable-output** program (`sv0 → C → host cc → binary`)
  with build records, a reproducibility harness, and a sanitizer matrix.

### Proven on real libraries
This toolchain compiles and verifies two independently released libraries, each
with a full F0→R1 evidence chain (traceability, fuzz, sanitizer, release manifest):
- **sv0-mathlib v0.2.0**
- **sv0-strings v1.1.0**

### Known limitations
- **No LLVM backend or production crypto yet** — that is Milestone 5 (planned, not
  started). Code generation is via the C and VM backends.
- **VM f64 byte-reproducibility across CI jobs** is not guaranteed on SML/NJ
  (documented; the VM float fixture leg is advisory). Behavioral parity holds.
- **No prebuilt binary distribution yet** — build from source (see `INSTALL.md`).

### Verification
`./scripts/sv0 test` (full gate) and GitHub CI (CI + VM parity tier-2) green at the
tagged commit.
