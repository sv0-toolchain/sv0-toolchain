# M4 (advanced verification) — closure evidence

Maps each completion criterion from `sv0-toolchain-milestone-4-verification.Rmd`
to the shipped implementation, tests, and gate/CI evidence. All 26 `M4-S-###`
slices are **done** (see `sv0-toolchain-milestone-4-checklist.Rmd`); the full
`./scripts/sv0 test` gate and GitHub CI (CI + VM parity tier-2) are green.

Prepared 2026-08-22. Pinned SHAs at closeout: sv0c `<see README gitlink>`,
sv0doc `f4dabf6`. The whole verification pipeline runs from source text, is sound
(only a solid `unsat` strips a check), deterministic, and gated.

## criterion → evidence

### 1. SMT backend (Z3-via-SMT-LIB2; sat/unsat/unknown/timeout; deterministic; graceful degradation)
- **Slices:** M4-S-010 (SMT-LIB2 emitter + query wrap), M4-S-011 (z3 driver), M4-S-013 (host-process decision), M4-S-014 (determinism).
- **Code:** `sv0c/lib/verify_vcgen.sv0` `cexpr_to_smt` / `vc_build_query` / `vc_build_check` (QF_LIA, auto QF_NIA on `*`/`/`/`%`); `scripts/sv0-z3.sh` (`-t:` timeout + `sat.random_seed=0 smt.random_seed=0`; one verdict per `(check-sat)`; **exit 2 when z3 absent** → callers degrade to all-runtime).
- **Design:** driver-orchestrated — the compiler `write_file`s the query, the `sv0` shell driver runs z3; no FFI/subprocess builtin (M4-S-013).
- **Tests/CI:** `scripts/verify_z3_driver.py` (8 query cases incl. emitter ops + batch; skips if z3 absent), `scripts/verify_determinism.py` (3 identical runs). z3 installed in CI (`ci.yml`) so these run on Linux.

### 2. `sv0 verify` report + JSON
- **Slices:** M4-S-020 (end-to-end), M4-S-021 (§3.2 report + reason), M4-S-022 (JSON).
- **Code:** `verify_all_fns` in `verify_vcgen.sv0` emits one obligation record per clause; `run_verify` in `scripts/sv0` renders `<file>:<line>  <clause>  [verified|runtime]  -- <reason>`; `sv0 verify --json` emits `{file,contracts[],summary}`.
- **Tests/CI:** `scripts/verify_sv0_verify_e2e.py` (text + `--json`, cross-checked) — green on Linux CI.

### 3. contract-mode (`runtime`/`verified`/`disabled`; flag + sv0.toml)
- **Slices:** M4-S-023 (flag), M4-S-024 (strip proven checks in lowering), M4-S-025 (sv0.toml).
- **Code:** `lower()` gained `contract_mode` + `proven_lines` — verified mode skips `Instr::Ensures` whose clause source line is in the proven set (requires + unproven kept); native `--verified <proof> <src>` / `--disabled <src>` control prefixes; `sv0 compile [--contract-mode=…]` + `sv0 emit-verified`; precedence flag > `[build] contract-mode` in sv0.toml > `runtime`.
- **Tests/CI:** `scripts/verify_contract_mode.py` (runtime 2 ensures → verified 1, stripped C compiles), `scripts/verify_contract_toml.py` (sv0.toml vs flag override) — green.

### 4. Phase 2 — intra-function verification (linear int + bool)
- **Slices:** M4-S-001 (IR), 002 (extraction), 003 (straight-line VC), 004 (branches / if-else path conditions), 005 (loops via `loop_invariant`: entry ∧ preservation, sibling conjunction), 006 (`old` + result binding, with a soundness guard).
- **Code:** `extract_cexpr`, `vc_collect_paths` (branch disjunction), `verify_loop_payload` + `vc_subst` (loop transition), `vc_body_has_effect` (soundness guard).
- **Corpus:** `arithmetic.sv0`, `branches.sv0`, `loops.sv0`, `oldstate.sv0`.

### 5. Phase 3 — refinement types + modular + trait/cast
- **Slices:** M4-S-030 (refined-type syntax), 031 (refinement checking at bindings), 032 (modular caller→callee requires), 033 (trait-contract contravariance / LSP), 034 (narrowing-cast contracts).
- **Code:** `parse_type_alias_item` `where` predicate (stored in alias `id3`) + `verify_fn_refinements`/`extract_refine`; `verify_fn_calls`/`extract_call_req` (param→arg subst); `verify_trait_contracts` (override obligations, needed bodyless trait-method parsing + impl trait-name recording); `verify_fn_casts` (fits-in-target, needed cast target-type-name in ExprCast `ed3`).
- **Corpus:** `refined_check.sv0`, `modular.sv0`, `trait_contracts.sv0`, `casts.sv0`.

### 6. pilots + gated verification corpus
- **Slices:** M4-S-040 (corpus format + verifier), 041 (pilot), 042 (CI), 043 (pilot-target decision).
- **Code/data:** `scripts/verify_corpus.py` checks each contract's `[verified]`/`[runtime]` against an inline `//@` annotation, both directions; **57 contracts across 11 files** under `sv0c/test/verify/corpus/`. Pilot `pilot_numeric.sv0` (abs/min/max/clamp/sum — 9 obligations verified end-to-end). Wired into `./scripts/sv0 test` (skips if z3 absent) → runs in CI. **Pilot target = numeric/std** (crypto deferred; needs nonlinear + bitvector — rationale in `sv0c-verify-pilots.Rmd`).

### 7. spec reflects shipped behavior
- **Slices:** M4-S-050 (semantics §3–4), M4-S-051 (type-system refinement section).
- **Docs:** `sv0doc/contracts/semantics.md` §3.2/3.3/4/5.4/6.2 updated (real report shape + reasons, `sv0 compile`/`emit-verified`, z3-driver notes, call/refine/override/cast obligations); `sv0doc/type-system/rules.md` §2.8 finalized (grammar + `self` binder + parse/check status).

## known limitations (documented, non-blocking)
- Nonlinear arithmetic (QF_NIA) is unreliable; bitwise/shift/bitvector ops are outside the supported fragment (→ sound RESIDUAL) — this is why the pilot is numeric, not crypto.
- Trait-contract contravariance assumes the trait and impl methods share parameter names.
- Refinement checking is **verify-only**; full compilation still rejects a type alias used as a parameter type (a pre-existing checker gap, orthogonal to verification).
- Loop VC-gen handles straight-line-assignment bodies; nested loops and invariant→ensures "use" wiring are future work.
