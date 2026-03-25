---
name: sv0c milestone 1 compiler
overview: "sv0c bootstrap compiler in SML/NJ: tasks 1–9 delivered a vertical slice; remaining M1 work is phased (m1-p1…p9) through expressions, calls, contracts, loops, data, builtins, polish — traits/modules default to M2 per shippable-M1 agreement."
todos:
  - id: doc-update
    content: Update sv0doc/milestone-0-review.md with design question resolutions and document the milestone 1 plan
    status: completed
  - id: task-1
    content: "Task 1: Project Setup -- sources.cm, stub modules, Makefile, main.sml entry point"
    status: completed
  - id: task-2
    content: "Task 2: Error Reporting -- span.sig/sml, diagnostic.sig/sml with source snippets"
    status: completed
  - id: task-3
    content: "Task 3: Lexer -- token.sml (43 keywords, no SOME/NONE/OK/ERR), lexer.sig/sml, lexer_test.sml"
    status: completed
  - id: task-4
    content: "Task 4: Parser + AST -- ast.sml datatypes, recursive descent + Pratt parsing, parser_test.sml"
    status: completed
  - id: task-5
    content: "Task 5: Name Resolution -- scoped symbol table, module path resolution, resolver_test.sml"
    status: completed
  - id: task-6
    content: "Task 6: Type Checker -- type representation, unification engine, trait resolution, checker_test.sml"
    status: completed
  - id: task-7
    content: "Task 7: Contract Analyzer -- validation + runtime check lowering, contract_test.sml"
    status: completed
  - id: task-8
    content: "Task 8: IR -- basic block IR datatypes, AST-to-IR lowering, ir_test.sml"
    status: completed
  - id: task-9
    content: "Task 9: C Backend -- IR-to-C99 codegen, sv0_runtime.h/c, end-to-end integration tests"
    status: completed
  - id: m1-p0
    content: "M1 Phase 0 (done): lexer/parser/resolver + checker/IR/codegen vertical slice, make test/e2e"
    status: completed
  - id: m1-p1
    content: "M1 Phase 1: binops/unary, if/else, semantically checked blocks; IR branches + C codegen; tests"
    status: completed
  - id: m1-p2
    content: "M1 Phase 2: direct fn calls, multi-fn programs, call graph + static helpers; resolver callee; tests + e2e"
    status: completed
  - id: m1-p3
    content: "M1 Phase 3: contract lowering (requires/ensures/loop_invariant) to sv0_runtime; analyzer pass; tests"
    status: completed
  - id: m1-p4
    content: "M1 Phase 4: while/for range (Q4 desugar), loop/break/continue; IR loops or desugar to gotos; tests"
    status: completed
  - id: m1-p5
    content: "M1 Phase 5: structs (fields, literals, access), enums + minimal match; type env for constructors"
    status: completed
  - id: m1-p6
    content: "M1 Phase 6: integral `as` casts, string literals + TyString, `println` intrinsic (literal arg), `?` on user enums Ok/Err (single-field); Vec/Box/heap string deferred"
    status: completed
  - id: m1-p7
    content: "M2 (was M1 Phase 7): traits/impls/generics (single bound), method dispatch (Q8); optional for shippable M1"
    status: pending
  - id: m1-p8
    content: "M2 (was M1 Phase 8): modules (use, qualified paths), core prelude (Q10); optional for shippable M1"
    status: pending
  - id: m1-p9
    content: "M1 Phase 9: contract builtins (result, old, forall, exists, no_alias), diagnostics E01–E05 polish, golden E2E suite"
    status: completed
  - id: m1-doc
    content: "M1 closure: sv0doc milestone-1-complete checklist + align doc/compiler-passes.md with final behavior"
    status: completed
isProject: false
---

# sv0c Milestone 1: Bootstrap Compiler

## Bootstrap Subset Scope

**In scope:** All primitives, let/mut bindings, functions, if/else/match/while/for/loop, structs, enums, basic generics (type params + single trait bounds), basic trait def/impl, operator desugaring, contracts (requires/ensures/loop_invariant -- runtime checks only), contract builtins (result, old, forall, exists, no_alias), Option/Result/Vec/Box/string as builtins, println/print intrinsics, all operators, patterns, modules (module/use), `?` operator, `as` casts.

**Deferred:** GATs, const generic expressions, trait objects, `impl Trait`, closures, refined types, `#[derive]`, negative impls, function overloading, `unsafe`/raw pointers, Send/Sync, `where` clauses (parse but treat as inline bounds).

## Architecture

- **Pipeline:** Source -> Lexer -> Parser -> Name Resolver -> Type Checker -> Contract Analyzer -> IR Lowering -> C Backend -> cc -> binary
- **Build system:** Single top-level `sv0c/sources.cm` (CM Group) listing all files in dependency order
- **Module pattern:** `signature FOO = sig ... end` in `.sig`, `structure Foo :> FOO = struct ... end` in `.sml`
- **Error codes:** E01xx lexer, E02xx parser, E03xx name resolution, E04xx types, E05xx contracts

## Design Question Resolutions

- **Q1 (string literals):** `"hello"` has type `&string` with static lifetime; `let s: string = "hello"` copies to heap
- **Q2 (integer overflow):** Panic in runtime contract mode, wrap in disabled mode
- **Q3 (closures):** Deferred -- not in bootstrap subset
- **Q4 (for-loop):** `for x in 0..n` desugars to while-loop with counter; range-only in milestone 1
- **Q5 (? operator):** Hardcoded for Result/Option, no Try trait
- **Q6 (builtins):** Vec/Box/string as compiler-known types with registered methods
- **Q7 (println):** Compiler intrinsic; format string must be literal; emits printf-based C
- **Q8 (reborrowing):** `&mut T` reborrowable as `&T`; receiver resolution tries T, &T, &mut T
- **Q9 (borrow scopes):** Lexical scopes only in milestone 1; full NLL deferred
- **Q10 (modules):** One file = one module; `core::option`/`core::result` implicitly imported

## Key Files

- [sv0c/sources.cm](sv0c/sources.cm) -- CM build file
- [sv0c/src/main.sml](sv0c/src/main.sml) -- entry point wiring all passes
- [sv0c/src/error/](sv0c/src/error/) -- span.sig, span.sml, diagnostic.sig, diagnostic.sml
- [sv0c/src/lexer/](sv0c/src/lexer/) -- token.sml, lexer.sig, lexer.sml
- [sv0c/src/ast/](sv0c/src/ast/) -- ast.sml (complete AST datatypes)
- [sv0c/src/parser/](sv0c/src/parser/) -- parser.sig, parser.sml (recursive descent + Pratt)
- [sv0c/src/name_resolution/](sv0c/src/name_resolution/) -- env.sig, env.sml, resolver.sig, resolver.sml
- [sv0c/src/type_checker/](sv0c/src/type_checker/) -- types.sml, unify.sig, unify.sml, checker.sig, checker.sml
- [sv0c/src/contract_analyzer/](sv0c/src/contract_analyzer/) -- analyzer.sig, analyzer.sml
- [sv0c/src/ir/](sv0c/src/ir/) -- ir.sml, lowering.sig, lowering.sml
- [sv0c/src/backend/c/](sv0c/src/backend/c/) -- codegen.sig, codegen.sml
- [sv0c/runtime/](sv0c/runtime/) -- sv0_runtime.h, sv0_runtime.c
- [sv0doc/milestone-0-review.md](sv0doc/milestone-0-review.md) -- design question resolutions

## Corrections from Task Rmds

- **Lexer Rmd lists SOME/NONE/OK/ERR as keyword tokens** -- remove these; grammar D19 makes them identifiers
- **Parser Rmd precedence order differs from grammar** -- use grammar's 14-level order as source of truth
- **Project Setup Rmd proposes per-module sources.cm** -- use single flat sources.cm instead

## Tasks 6–9 (execution plan — vertical slice first)

### Task 6: Type checker (this milestone slice)

- **Types:** Reuse [types.sml](sv0c/src/type_checker/types.sml) `Types.ty` for checking; map `Ast.ty` built from name resolution (single-segment primitives + `unit`/`bool`/ints).
- **Unify:** [unify.sml](sv0c/src/type_checker/unify.sml) — structural equality on ground types (no inference yet); extend later with `TyVar` substitution.
- **Checker:** [checker.sml](sv0c/src/type_checker/checker.sml) — value environment from `fn` params and `let` (`PatBind` only in slice); synthesize types for literals, paths, `return`, blocks with optional tail expr; require return/tail type = declared `fn` return. Unsupported constructs raise `Fail` with `E04xx`.
- **Tests:** In [test_runner.sml](sv0c/test/test_runner.sml): well-typed `main`, `let` + `return`, reject wrong literal type vs `i32`.

### Task 7: Contract analyzer (slice)

- **Behavior:** If `contracts` empty, pass-through. If non-empty, validate that contract expressions typecheck as `bool` in the same pre-body environment as `requires`/`ensures` (params only); no IR insertion yet beyond leaving AST unchanged (runtime hooks reserved for later).
- **Tests:** Fn with `requires true` passes; mismatch raises `E05xx` when we add stricter rules — for slice, optional `requires true` only.

### Task 8: IR lowering (slice)

- **Input:** Typechecked AST (at least one `ItemFn` with `ExprBlock` body).
- **Output:** `Ir.program` as a **flat list of instrs** in one block per function for the supported subset: `StmtLet` + literal rhs, `StmtSemi (ExprReturn _)`, block tail literal or path.
- **Tests:** Lowering produces `Return` with expected `VInt` / `VVar` for sample programs.

### Task 9: C backend + E2E

- **Codegen:** Map `i32`/`unit` fn to `int`/`void` `main` (and `static` helpers if multiple fns later). Emit `#include "sv0_runtime.h"`, assignments, `return`.
- **E2E:** `make e2e` — SML script writes `build/e2e_generated.c`, `cc` links [sv0_runtime.h](sv0c/runtime/sv0_runtime.h) / [sv0_runtime.c](sv0c/runtime/sv0_runtime.c), run binary and assert exit code (e.g. 42).
- **Docs:** Extend [doc/compiler-passes.md](sv0c/doc/compiler-passes.md) with checker/IR/codegen notes.

**Ordering:** Implement 6 → 7 → 8 → 9; after each task run `make test`; after 9 run `make e2e`.

**Status (executed):** A vertical slice is implemented: checker + unify for ground types, lowering for `let`/literal/`return`, C codegen with `make e2e`, tests in `test_runner.sml`. Trait resolution, full inference, contract IR lowering, and multi-fn codegen beyond `static` helpers remain future work.

---

## Milestone 1 completion roadmap (full bootstrap subset)

The paragraph **Bootstrap Subset Scope** above is the **long-term target**. The compiler today implements **Phase 0** only. Extend **checker → IR → codegen** together per phase, run `**make test`**and `**make e2e`** after each phase, and add **golden** `.sv0` fixtures under [sv0c/test/data/](sv0c/test/data/) when a feature stabilizes.

**Shippable Milestone 1 (agreed):** finish **Phases 1–6** and **9**. **Phases 7–8** (traits/generics/modules) are **M2** unless completed early — record that split in **sv0doc** when you ship.

### Phase 0 — shipped (baseline)

- Parse, resolve, typecheck, lower, emit C for: `fn` with explicit return type, `let` + `PatBind` + literal, `return`, block tail or last `return`, empty `unit` body.
- `requires` expression typechecks as `bool`; analyzer is a no-op.
- `make e2e` proves **cc + run** with exit code **42**.

### Phase 1 — expressions and `if` (binops foundation)

**Checker:** Integer binops (`+ - * / %`, shifts, bitwise per grammar) starting from `**i32`**; widen rules consistently to other widths. Unary `-`, `!`, `~`. `if cond { } else { }`: `cond : bool`; both arms same type in tail position (no implicit union).

**IR / codegen:** Use existing labels/branches in [ir.sml](sv0c/src/ir/ir.sml); lower `if` to linearized blocks or C **if/else** with consistent returns.

**Tests:** Reject `bool` + `i32`; accept `i32 + i32`. E2E: `if` returning `i32`.

### Phase 2 — calls and multi-fn

**Resolver:** Resolve callee (`ExprPath` / name) to same-module `fn`; arity or function type in environment.

**Checker:** `ExprCall`: check args against `TyFn`; two-pass over items for mutual recursion if needed.

**IR:** `Call` with value args; one `Ir.block` per `ItemFn`; emit **static** helpers before `main` or use C forward declarations.

**Codegen:** `static int foo(int a, …)` for `i32` params; map `Types.ty` → C types.

**Tests:** `foo(x+1)` and `main` returns `foo(41)`; `make e2e` exit **42**.

### Phase 3 — contract lowering

**Analyzer or lowering:** For each `ItemFn` with contracts: `**sv0_requires(cond, "name")`**at entry; `**sv0_ensures`** on every exit (including `if` branches) — may need IR exit marking or epilogue. `**loop_invariant**`: after Phase 4, at loop head; until then keep **E0502** or no-op.

**Runtime:** [sv0_runtime.h](sv0c/runtime/sv0_runtime.h) / `.c` linked in all e2e builds.

**Tests:** `requires true` / `ensures true` runs; `requires false` fails at runtime.

### Phase 4 — loops (`while`, `for` range per Q4) — done

**Lowering:** `for x in lo..hi` per [milestone-0-review Q4](sv0doc/milestone-0-review.md) (half-open `lo..hi`); `while`; `loop` as infinite `while`; `break` / `continue`; `loop_invariant(e)` on `while` lowered to `sv0_requires` at each iteration head.

**Checker:** `break` / `continue` only inside loops; `for` requires `PatBind` and `lo..hi`; `break expr` rejected (E0415).

**Parser note:** A `while` / `for` / `loop` used as a **statement** before another statement in the same block needs a trailing **`;`** (expression-statement rule).

**Codegen:** C `while`, `break`/`continue`, braced per-iteration scope for `for`; `sv0_requires` for while invariants.

### Phase 5 — structs, enums, minimal `match`

**Resolver / checker:** `ItemStruct` / `ItemEnum` in type env; struct literals and field access; enum constructors with arity.

**IR:** Struct literals as field assignments; `FieldAccess`; `match` on enum → C `switch` or if-chain.

**Codegen:** Emit C `struct` definitions before functions.

### Phase 6 — builtins and intrinsics (Q6, Q7, Q5) — **done (partial)**

**Shipped:** Integral **`as`** (E0440 for non-integral). **String literals** → `TyString`. **`println("literal")`** — intrinsic pre-registered in resolver (E0302 if user defines `fn println`); checker E0444 if not a single string literal; lowering → `sv0_println` in [`sv0_runtime.h`](sv0c/runtime/sv0_runtime.h). **`?`** on user **`enum`** with **`Ok(T)`** / **`Err(E)`** single-field variants; function return must be that same enum (E0441–E0443); lowering returns whole enum on Err, binds `p0` on Ok. Unary tuple `(e)` peeled in checker/lowering for `(expr as T)`.

**Deferred to later (Q6 / prelude):** **`Vec` / `Box`**, heap **`string`**, **`print`**, generic **`Option`/`Result`**, method registry — need layout + runtime + traits slice.

### Phase 7 — traits / impl / generics → **M2 default**

Type params, `TyVar` + substitution, trait resolution (**monomorphize or vtables** — pick one, document in [doc/compiler-passes.md](sv0c/doc/compiler-passes.md)). `**ExprMethodCall`** with simplified autoref (Q8).

### Phase 8 — modules → **M2 default**

`use` / `module`, qualified paths (remove E0305 for values/types), implicit **core** prelude; single C translation unit with prefixed symbols at first.

### Phase 9 — contract builtins and polish (part of shippable M1) — **done**

**Shipped:** **`old` / `forall` / `exists` / `no_alias`** + **`&` / `&mut`** in contracts (checker E0521–E0526, lowering E0540–E0541); **`result`** unchanged from earlier ensures work. Resolver intrinsics + quantifier binding; lowering: `_sv0old_*`, tmp ordering (body before ensures). Runtime **`sv0_no_alias`**. Messages include **`(hint: …)`** where useful; CLI **`sv0c error:`**. Golden suite: [`sv0c/test/data/golden/`](../../sv0c/test/data/golden/) + **`[golden]`** in `test_runner.sml`.

### Milestone 1 “complete” checklist (acceptance)

- **Phases 1–6** and **9** done; **7–8** done or documented as **M2** in sv0doc.
- `**make test`**and `**make e2e`** green; at least one **multi-stage** e2e (calls + `if` + loop).
- [doc/compiler-passes.md](sv0c/doc/compiler-passes.md) matches shipped behavior.
- **sv0doc** file (e.g. `milestone-1-complete.md`): **done** vs **deferred to M2** vs original **In scope** list.

### Execution order (implementation)

1. **1 → 2 → 3** — binops, `if`, calls, multi-fn, contract lowering.
2. **4 → 5** — loops, then structs/enums/`match`.
3. **6** — builtins, println, `?`, `as`.
4. **9** — contract builtins + diagnostics + golden tests.
5. **7 → 8** — only if pulling forward into M1; otherwise **M2**.

After **each** phase: set todo `**m1-pN`** to **completed** in this file, update **compiler-passes.md**, extend **tests**.
