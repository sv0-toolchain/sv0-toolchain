# sv0 Milestone 3: L0 Closure Plan

**Last updated:** 2026-07-03

**Situation:** All slice gates G1–GX are **Done**. SML is retired to `sml-legacy/`.
The `bootstrap-sml-final` tag exists. **`lib/driver.sv0`** now passes all 49
self-host tests (exit 0). **P2 COMPLETE (2026-07-03):** `build-sv0-self-host-compiler.sh`
now builds a real native binary (`build/sv0-driver-native`) from `lib/driver.sv0` via
SML→C→cc; the binary supports CLI mode (reads input path from `/tmp/.sv0_drv_path`);
CI remains green with SML-backed default. Parity diff is deferred to P3. **M3 L0 is
still open** because the four criteria in `## completion criteria` of the task file
are not yet satisfied by the current implementation.

**Authority:** `task/sv0-toolchain-milestone-3-self-host.Rmd` is the source of truth
for completion criteria and evidence. This document is the ordered engineering
execution plan only.

---

## Why L0 Is Still Open

The gate slice tables (M3-S-001…M3-S-055) tracked *scaffolding and parity building
blocks* — not functional end-to-end pipelines. The G6 "staging driver" (M3-S-041
Done) deliberately did **not** wire `parse_program` into `main.sv0`
(`verify_m3_g6_staging_driver_contract.py` enforces this). The four open L0
prerequisites are:

| # | Criterion | Current state | What's missing |
|---|-----------|--------------|----------------|
| P1 | **Composed sv0 driver** — `main` in sv0 calls lexer→emit | `lib/driver.sv0` has full lexer→parser→resolver→checker→emit pipeline with 49 passing tests; `lib/main.sv0` still has no phase calls | Wire `driver_compile_file` from `driver.sv0` into `main.sv0` for both --emit-c and --target=vm modes |
| P2 | **Native `SV0_SELF_HOST_COMPILER` binary** ✓ | `build/sv0-driver-native` built from `lib/driver.sv0` (SML→C→cc); CLI mode via `/tmp/.sv0_drv_path`; CI uses SML default | Parity diff deferred to P3; wire native wrapper into CI default once parity is clean |
| P3 | **Semantic pipeline parity** — sv0 pipeline matches SML on all L0 programs | `linkProjectDir` AST merge unimplemented; `check_program` is single-unit; resolver/checker have known gaps | Per-file parse+arena relocation; multi-module checker; lowering tail cases |
| P4 | **VM parity tier-2 (native emitter)** | Tier-2 harness uses a surrogate shell script, not sv0-emitted bytecode | Replace surrogate with sv0-emitted VM bytecode once P2 exists |

P1 blocks P2, which blocks P4. P3 is partially parallelizable with P1/P2.

---

## Execution Order

```
Phase A — Composed driver (P1):
  A1. Decide composition model (Option A: #include mega-TU  vs  Option B: multi-unit C link)
  A2. Implement driver_compile_file calling all 6 phases in order
  A3. Wire driver_compile_file into main() for both --emit-c and --target=vm modes
  A4. Update staging driver contract script; confirm CI green

Phase B — Native binary (P2):
  B1. ✓ Rewrite build-sv0-self-host-compiler.sh to produce a real native binary
       (build/sv0-driver-native + build/sv0-self-host-compiler-native wrapper)
  B2. ✓ Native binary self-test passes (49 tests, exit 0); smoke: vm_add_chain
       compiles + runs via native driver. Diff vs SML deferred (inline exprs ≠ IR temps).
  B3. Wire native binary as CI default once P3 parity diff is clean.

Phase C — Parity gaps (P3, parallel with A/B):
  C1. linkProjectDir: per-file parse_program + arena relocation + item-row merge
  C2. Resolver: TyArray size expr, enum variant aliases, trait/impl method bodies
  C3. Checker: multi-module check_program (depends on C1)
  C4. Lowering: PatStruct bind edge cases, scrut_cty local/param resolution
  C5. include_expand: expand/expandFile with real host file I/O

Phase D — VM tier-2 native (P4):
  D1. Run native binary (from B) on all tier-2 programs; capture bytecode
  D2. Diff against golden/sml/; fix any mismatches
  D3. Replace tier-2 surrogate shell script with native emitter invocation
  D4. CI must run D3 without SV0_SKIP_SELF_HOST_COMPILER_DIFF=1

Phase E — M3 completion declaration:
  E1. All completion criteria evidence checked in task Rmd
  E2. README milestone status → Done
  E3. sv0-toolchain-milestone-3-checklist.Rmd fully checked
```

---

## Phase A: Composed sv0 Driver

### A1. Choose Composition Model

Two options. Pick one before writing any code:

**Option A — `include` mega-TU (faster, recommended first)**

`lib/main.sv0` gains `include "..."` directives for all phase modules at the top.
**Confirmed viable:** `sml-legacy/main.sml` calls `IncludeExpand.expandFile` on
every file it compiles (line 54 and 90), so the directives are expanded before
lexing. The syntax is `include "lexer.sv0"` (not `#include`) — matching the SML
`include_expand.sml` which looks for lines of the form `include "<path>"`.

```sv0
include "lexer.sv0"
include "parser.sv0"
include "resolver.sv0"
include "checker.sv0"
include "lowering.sv0"
include "link.sv0"
include "codegen.sv0"
include "vm_codegen.sv0"
```

The resulting expanded file is large (~15k lines) but the SML compiler handles it.
The `.sv0b` / `.c` output contains a `main` function that calls all phases.

Advantages: works with today's `include_expand.sv0` (already tested in G2, lines
290–333); no new linker/packaging infrastructure needed; path to Done is a single
`lib/main.sv0` edit + `driver_compile_file` implementation.

Disadvantage: all-or-nothing expansion — any compile error in any included file
fails the whole mega-TU.

**Option B — Multi-unit native C link (cleaner, requires new rules)**

Each `lib/*.sv0` is compiled to a `.c` file independently (already done by
`bootstrap-build`). A new linking step combines these `.c` files with the C runtime
into a single executable. Requires: defining shared C header conventions across sv0
compilation units (each today has its own `main`-equivalent entry + runtime
init assumptions); a Makefile or script rule to link them.

Advantage: no mega-TU; each module stays small. Disadvantage: new infrastructure;
no existing template in the repo.

**Decision record:** Update this document and the task Rmd with the chosen approach
before starting A2.

---

### A2. Implement `driver_compile_file`

Add to `lib/main.sv0` (or the mega-TU entrypoint, depending on A1 choice):

```sv0
// Compile one sv0 source file through the full pipeline.
// Phase order (mirrors SML sml-legacy/main.sml compileProgram):
//   1. tokenize  — lexer.sv0  :: tokenize
//   2. parse     — parser.sv0 :: parse_program
//   3. resolve   — resolver.sv0 :: resolve_program
//   4. check     — checker.sv0 :: check_program
//   5. lower     — lowering.sv0 :: lower
//   6. emit      — codegen.sv0 :: emit  (backend=C)
//                  vm_codegen.sv0 :: emit_program  (backend=VM)
//
// Returns 0 on success, non-zero on first error.
fn driver_compile_file(src_path: string, out_path: string, backend: i32) -> i32 {
    ...
}
```

**Critical:** The `verify_m3_g6_staging_driver_contract.py` script currently asserts
that `parse_program` does NOT appear in `main.sv0`. This invariant must be dropped
(or the script updated) when A2 lands. Update the script and the refinement log.

Interdata types between phases (all already defined in their respective modules):
- lexer output: `source: string`, `tok_tags: Vec<i32>`, `starts: Vec<i32>`, `ends: Vec<i32>`
- parser output: item arena vecs + body/type arena vecs + `pp: Vec<i32>`
- resolver output: `name_env: Vec<i32>` (import aliases, struct/enum name maps)
- checker output: `type_env: Vec<i32>` (or no output — errors passed via return code)
- lowering output: `block_labels`, `block_param_names`, `block_param_ctys`, `block_instrs`
- emit output: written to `out_path` (C text or `.sv0b` bytecode)

---

### A3. Wire into `main()`

Update `fn main() -> i32` in `lib/main.sv0` to:
1. Parse CLI args (already done via `classify_cli`)
2. Dispatch to `driver_compile_file` (single file) or `driver_compile_project`
   (--project dir, requires C1 from Phase C first)
3. Print diagnostics and exit with appropriate code

For now, `--project` mode can return an error "not implemented" if C1 is not yet
done; single-file mode must be fully functional.

---

### A4. CI Validation

After A1–A3 land:

```bash
./scripts/sv0 compile-run lib/link.sv0   # must still exit 0
./scripts/sv0 test                       # must be green
```

Update `verify_m3_g6_staging_driver_contract.py` to remove the `parse_program`
absence check and instead assert that `driver_compile_file` IS present in `main.sv0`.

---

## Phase B: Native Binary

### B1. Rewrite `build-sv0-self-host-compiler.sh`

Current script produces a wrapper that delegates to the SML heap. Replace it with a
script that:

1. Runs `driver_compile_file` (via the P1 driver, built from SML bootstrap) on each
   `lib/*.sv0` source in dependency order and concatenates / links the output.
2. Compiles the emitted C with the host C compiler.
3. Writes a binary to `build/sv0-self-host-compiler`.

```bash
#!/usr/bin/env bash
# Build a native sv0 compiler binary from sv0 sources.
# Prerequisite: Phase A (composed driver) must be complete.
# Usage: ./scripts/build-sv0-self-host-compiler.sh
set -euo pipefail
...
```

The script must NOT call `sv0-self-host-emit-c.sh` (the SML delegate). If the
script calls the SML heap at all, it is not a native build.

---

### B2. Third-Leg Parity Check

Run:
```bash
SV0_SELF_HOST_COMPILER="$(pwd)/build/sv0-self-host-compiler" \
  ./scripts/sv0 self-host-sv0-loop
```

All three legs must produce identical C output. Diff failures indicate either:
- A phase in the sv0 driver produces different output than SML for some input
  → Fix the driver (Phase C parity gaps)
- The native binary itself has a bug
  → Fix the binary

Do not advance to B3 until the diff is clean for all programs in
`sv0c/self-host-sv0-loop.list`.

---

### B3. CI Wiring

Remove `SV0_SKIP_SELF_HOST_COMPILER_DIFF=1` from CI if it was added as a temporary
bypass. The `self-host-native.yml` workflow (already in `.github/workflows/`) should
run the native build and third-leg diff without any skip flags.

---

## Phase C: Parity Gaps

These can be worked in parallel with Phase A/B. Each item here closes a gap between
the sv0 pipeline and SML `compileProjectDir`.

### C1. `linkProjectDir` AST Merge

**Why needed:** SML `linkProjectDir` (in `sml-legacy/link/link.sml`) calls
`parseFile` on each `.sv0` file in a directory, runs `mapProgramUnit` on each, and
concatenates the resulting `Ast.program` lists. The sv0 equivalents exist for
individual pieces but the full orchestration loop is missing.

**What exists already:**
- `link_apply_map_link_pass_program_source` — full map pass for one file ✓
- `link_merge_parallel_token_streams_reloc_b` — token stream relocation ✓
- `link_program_item_vecs_append` — item arena concatenation ✓
- `link_project_concat_sources_offsets_from_listing` — source offset bookkeeping ✓

**What's missing:**
- A loop that calls `parse_program` on each file's source slice, applies the offset
  via `link_reloc_i32_vec_inplace`, runs `link_apply_map_link_pass_program_source`,
  then calls `link_program_item_vecs_append` to merge into an output arena.

**Function to write** in `lib/link.sv0`:
```sv0
// SML: link.sml :: linkProjectDir
// Parse each file in the listing, relocate arena indices by per-file source offset,
// run the mangle pass, and merge all item/expr/type arenas into the output vecs.
// Output arenas (out_item_tags, ...) are cleared and populated by this call.
fn link_project_dir_from_listing(
    listing: Vec<i32>,         // listing vec from link_project_listing_from_entry
    offsets: Vec<i32>,         // per-file start offsets in the merged source
    merged_source: string,     // full concatenated source
    merged_starts: Vec<i32>, merged_ends: Vec<i32>,  // lexer output for merged source
    // output arenas:
    out_item_tags: Vec<i32>, out_item_names: Vec<i32>, ...
    out_body_et: Vec<i32>, out_body_ed1: Vec<i32>, ...
    out_pty_tt: Vec<i32>, out_pty_td1: Vec<i32>, ...
) -> i32 { ... }
```

Test: two-file project where file A defines `fn Foo()` and file B calls `Foo()`.
After `link_project_dir_from_listing`, the merged item arena must contain
`link__Foo` (mangled name) and the expression arena must reference `link__Foo` at
the call site.

---

### C2. Resolver Gaps

`lib/resolver.sv0` has known incomplete cases:

- **TyArray size expr:** `resolve_ty` for `TyArray` may not resolve the size
  expression through the full expr resolver. Add to `resolve_ty` case for tag 5
  (TyArray).
- **Enum variant aliases:** `resolve_top_item` for enum variants may miss some alias
  plumbing for variant constructors with payloads. Cross-check against SML
  `NameResolution.resolveTopItem` for `ItemEnum`.
- **Trait/impl method bodies:** `resolve_top_item` has no-ops for impl method bodies
  beyond the parent row. SML resolves each method body independently.

For each gap: write a failing test first, then fix.

---

### C3. Multi-Module `check_program`

`lib/checker.sv0` `check_program` operates on a single merged program. For
multi-module projects, after C1 produces a merged arena, `check_program` should
work correctly on the merged output — but any cross-module type references require
the resolver to have populated the name env correctly (depends on C2).

Test: compile a two-file project where file A defines a struct `Foo` and file B
uses it in a function signature. The checker must resolve `Foo` to `link__Foo`
(the mangled name) through the merged name env.

---

### C4. Lowering Tail Cases

`lib/lowering.sv0` has two known partial cases:

- **`PatStruct` bind edge cases:** `lower_match_arms` with `PatStruct` when field
  patterns include nested patterns. Compare against SML `Lower.lowerPat`.
- **`scrut_cty` local/param resolution:** `match_scrut_cty` in `lowering.sv0` may
  resolve 1-segment scrutinees to coarse cty "pointer" instead of the precise enum
  typedef when the scrutinee is a local variable or parameter. Fix by threading
  the fn/param type table into `lower_tag_match`.

---

### C5. `include_expand.sv0` Host I/O

`lib/include_expand.sv0` currently has `expand` and `expandFile` implemented but
may not be wired to actual file I/O in the bootstrap context. Verify that
`expand_from_file` (or equivalent) actually calls `read_file` and test it on a
real `#include` directive in a multi-file project.

This is needed for Option A (mega-TU via `#include`) in Phase A.

---

## Phase D: VM Parity Tier-2 Native

After Phase B produces a working native binary:

### D1–D2: Run and Fix

```bash
SV0_SELF_HOST_COMPILER="$(pwd)/build/sv0-self-host-compiler" \
  ./scripts/sv0-vm-tier2-emit-bootstrap.sh
```

Diff each `.sv0b` output against `sv0c/test/vm-parity/golden/sml/`. Fix
mismatches. Common causes: encode_strings byte order, pool index off-by-one,
function table entry format.

### D3: Replace Surrogate

`scripts/sv0-vm-tier2-emit-bootstrap.sh` currently calls the SML heap to emit
bytecode. Replace the invocation with the native binary. Update CI accordingly.

---

## Phase E: M3 Completion Declaration

Evidence checklist (from `## stakeholder closure checklist` in the task Rmd):

| Evidence | How to satisfy |
|----------|---------------|
| Full pipeline in sv0 | `driver_compile_file` compiles all programs in `self-host-sv0-loop.list` producing byte-identical C to SML |
| Self-compile (native) | `build/sv0-self-host-compiler` was produced by the sv0 pipeline (not SML) AND compiles sv0 sources correctly |
| VM parity v1 | All tier-2 programs cmp-clean vs `golden/sml/` using native emitter |
| Diagnostics baseline | `verify_diagnostics_corpus_behavior.py` passes |
| SML retired | `bootstrap-sml-final` tag exists, `sml-legacy/` present, default build is sv0-only |

All five must be satisfied simultaneously. Update the task Rmd
`## stakeholder closure checklist` table, then update `README.md` and
`task/sv0-toolchain-milestone-3-checklist.Rmd`.

---

## Key Files (Current State)

| File | Current state | L0 role |
|------|--------------|---------|
| `sv0c/lib/driver.sv0` | **49 self-host tests passing (exit 0)** — full lex→parse→resolve→check→emit pipeline with test suite | Phase A source: `drv_compile_file` to be exposed as the P1 entry point |
| `sv0c/lib/main.sv0` | Constants + `driver_tokenize_sketch`; no phase calls | Phase A target: add `driver_compile_file` wiring to call `driver.sv0`'s pipeline |
| `sv0c/lib/link.sv0` | Map passes done; merge primitives done; orchestration loop missing | Phase C target: add `link_project_dir_from_listing` |
| `sv0c/lib/resolver.sv0` | Mostly complete; TyArray/enum/trait gaps | Phase C2 |
| `sv0c/lib/checker.sv0` | Single-unit; multi-module after C1 merge should work | Phase C3 verify |
| `sv0c/lib/lowering.sv0` | PatStruct/scrut_cty tail cases | Phase C4 |
| `sv0c/lib/include_expand.sv0` | `expand`/`expandFile` present | Phase C5 verify; Phase A1 (Option A) |
| `scripts/build-sv0-self-host-compiler.sh` | Wraps SML delegate shell script | Phase B1 replace |
| `scripts/sv0-vm-tier2-emit-bootstrap.sh` | Uses SML heap to emit bytecode | Phase D3 replace |
| `.github/workflows/self-host-native.yml` | Workflow exists; runs with delegate binary | Phase B3: remove skip flag |
| `scripts/verify_m3_g6_staging_driver_contract.py` | Asserts `parse_program` NOT in `main.sv0` | Phase A4: update to assert it IS present |

---

## What to Start Right Now

1. **Read `sv0c/lib/main.sv0`** and `sv0c/lib/include_expand.sv0` to confirm Option A
   (`#include` mega-TU) is viable — check whether `expand_from_file` calls
   `read_file` and whether the SML bootstrap compiler handles `#include` before
   parsing.

2. **Decision: A vs B.** If Option A is confirmed viable, start A2 immediately.
   If not, scope Option B's packaging rules and estimate cost.

3. **In parallel:** Start C1 (`link_project_dir_from_listing`) — all building
   blocks exist; it is an orchestration loop, not new algorithm work.

The single highest-leverage action is writing `driver_compile_file` in `lib/main.sv0`
(or the mega-TU) and getting `./scripts/sv0 compile-run lib/main.sv0` to actually
run a full lexer→emit pass on a test file.
