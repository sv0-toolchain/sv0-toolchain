---
name: Phase 5 structs enums
overview: Wire `ItemStruct` / `ItemEnum` through resolver, checker, IR, and C codegen; support struct literals and field access; implement `match` on enum-typed scrutinees and on `bool` / `i32` with literal and wildcard (and binding) arms, lowered to C `if` chains or `switch` where appropriate.
todos:
  - id: p5-tyenv
    content: "Checker: register struct/enum in mod env; astTyToTy for TyName; field/variant metadata"
    status: completed
  - id: p5-struct
    content: "Checker+lowering+codegen: struct literals, ExprField, C struct defs and non-int locals where needed"
    status: completed
  - id: p5-enum
    content: "Checker+lowering+codegen: enum types, variant construction, C tag+payload layout"
    status: completed
  - id: p5-match
    content: "Checker+lowering+codegen: match on enum; match on bool/i32 (literal/wildcard/bind); injectEnsures for new IR"
    status: completed
  - id: p5-tests-docs
    content: test_runner + compiler-passes.md; m1-p5 completed; make test && make e2e
    status: completed
isProject: false
---

# Phase 5: structs, enums, and `match`

## Confirmed scope

- **Match:** enum scrutinee **plus** `bool` and `i32` scrutinees with **literal**, `**_`**, and simple **binding** arms where the grammar already allows (no `match` on arbitrary struct values as scrutinee in this phase).
- **Structs:** top-level `ItemStruct`; `TyName (["StructName"], _)` becomes a **named type** in the checker; **struct literals** `[ExprStruct](sv0c/src/ast/ast.sml)` and **field access** `[ExprField](sv0c/src/ast/ast.sml)`.
- **Enums:** top-level `ItemEnum` with `[VariantUnit` / `VariantTuple` / `VariantStruct](sv0c/src/ast/ast.sml)`; **constructors** as expressions (parser paths + call/tuple forms as already parsed); `**match` on enum** with variant patterns.

## 1. Type representation and module environment

- Extend the checker’s **module type environment** beyond `TyFn` (today `[checker.sml](sv0c/src/type_checker/checker.sml)` `modEnvFromProg` only registers functions). Options consistent with existing `[Types.ty](sv0c/src/type_checker/types.sml)`:
  - Use `**Types.TyNamed (name, [])`** for both structs and enums in this phase, and maintain **parallel maps** (or a small `tycon` registry) for **struct field lists** and **enum variant signatures** (name → payload shape).
- Implement `**astTyToTy`** for resolving `Ast.TyName` against registered struct/enum names (reject unknown with **E0406** or new **E04xx**).

## 2. Resolver

- `[resolver.sml](sv0c/src/name_resolution/resolver.sml)` already walks `ItemStruct` / `ItemEnum` and `ExprStruct` / `ExprMatch`. Verify **match arms** bind pattern locals consistently with `**for`** (enter scope, `bindPatternLocals` where applicable) and that **enum/struct paths** in patterns resolve like types/values.

## 3. Type checker

- **Struct literal:** all fields present (or subset + definite rules), each expr matches declared field type; struct name known.
- **Field access:** base expression type is a **known struct**; field name exists; result type = field type.
- **Enum construction:** callee is a variant with arity matching tuple/struct payload; types agree with enum definition.
- `**match` typing:**
  - **Enum:** scrutinee type = specific enum; each arm pattern compatible with corresponding variant; all arm bodies unify to a common type (same rule as `if`).
  - `**bool` / `i32`:**arms restricted to literals, `**_`**, and possibly **bind-all** patterns the parser already produces; reject unsupported pattern forms with clear **E0402**.
- **Exhaustiveness:** optional for this phase (document as “best effort” or skip); if skipped, still require **otherwise total** for `i32` only when arms cover nothing—prefer **no false guarantee** over wrong runtime behavior.

## 4. IR and lowering

- **Struct values:** either **one C `struct` value** (load/store by field) or **flattened temps per field**; prefer **C struct** + `[Ir.FieldAccess](sv0c/src/ir/ir.sml)` / new `**LoadField`**-style if needed so codegen stays simple.
- **Enum values:** discriminant + payloads—use a **C `struct`** per enum (e.g. `tag` + `union` of variant payloads) or a minimal **tag + flat fields** layout; document choice in `[compiler-passes.md](sv0c/doc/compiler-passes.md)`.
- `**match` lowering:**
  - **Enum** → **if/else** or `**switch` on tag** + bind payloads in each arm.
  - `**bool` / `i32`**→ compare chain or `**switch`** for `i32` when arms are literal-only.

Extend `[injectEnsuresAndRetSlot](sv0c/src/ir/lowering.sml)` for any new IR containers that hold nested instr lists (same pattern as `While` / `Block`).

## 5. C codegen

- Emit `**typedef struct { ... } StructName;**` (and enum carrier structs) **before** function definitions in `[codegen.sml](sv0c/src/backend/c/codegen.sml)` (single translation unit, consistent with current **static** helpers).
- Map struct/enum types to C types in **param lists** and **locals** (today everything is `**int`**—Phase 5 must branch on `Types.ty` or a lowered type hint).

## 6. Tests and docs

- Add cases in `[test/test_runner.sml](sv0c/test/test_runner.sml)`: struct literal + field read; enum `match`; `match` on `bool` / `i32`; reject wrong field / wrong variant arity.
- Extend e2e fixture in `[scripts/export_e2e.sml](sv0c/scripts/export_e2e.sml)` only if it stays readable (avoid fragile SML string literals; reuse `**String.concat` / `String.str #"\n"`** pattern from Phase 4).
- Update `[doc/compiler-passes.md](sv0c/doc/compiler-passes.md)` and mark `**m1-p5`** completed in `[.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md](.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md)` when done.

## Dependency / ordering

Implement **struct types + literals + fields** first (values flow through calls/`let`), then **enums + constructors**, then `**match`**(enum then primitive) so each step keeps `**make test`** / `**make e2e**` green.

## Implementation notes (completed)

- **Parser:** `allowStruct` is threaded through the expression parser so `match e {`, `if e {`, `while e {`, and `for x in e {` do not parse `e {` as a struct literal. **`pathPatternFrom`** parses qualified patterns (`E::A()`, etc.) after `IDENT` + `::`; a bare `IDENT` without `::` remains `PatBind`.
- **Structs:** `parseStructFields` must return the token stream **after** the closing `}` (not the stream that still contains `}`) so following items are not dropped on parse failure recovery.
- **Docs:** See [sv0c/doc/compiler-passes.md](sv0c/doc/compiler-passes.md) for the pipeline description and enum/tag layout summary.
