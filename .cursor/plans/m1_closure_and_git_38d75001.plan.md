---
name: M1 closure and git
overview: Close Milestone 1 by adding the sv0doc acceptance checklist (shipped vs M2), aligning any small README cross-links, then commit **sv0c** (and optionally **sv0doc**) with conventional commits.
todos:
  - id: m1-sv0doc-checklist
    content: Add sv0doc/milestone-1-complete.md (M1 shipped vs M2 deferred; reconcile plan “In scope” list)
    status: completed
  - id: m1-crosslinks
    content: "Optional: link from sv0doc/README.md and one line in sv0c/README.md to the checklist"
    status: completed
  - id: m1-plan-todo
    content: Set m1-doc to completed in .cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md
    status: completed
  - id: m1-verify
    content: Run make test && make e2e from sv0c/ before committing
    status: completed
isProject: false
---

# Complete Milestone 1 closure + git workflow

## What “rest of M1” means (per `[.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md](.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md)`)

- **In scope for this closure:** Acceptance checklist § “Milestone 1 complete” — not Phases 7–8 (those stay **M2** / pending in the plan).
- **Already satisfied (verify when you execute):** Phases 1–6 and 9; `[sv0c/doc/compiler-passes.md](sv0c/doc/compiler-passes.md)` aligned with shipped behavior; `make test` and `make e2e` green from `sv0c/`.

## Work to do (execution phase — after you approve)

1. **Add** `[sv0doc/milestone-1-complete.md](sv0doc/milestone-1-complete.md)` with a short, factual checklist:

- **Shipped in M1:** pipeline stages, loops, structs/enums/match, casts/`println`/`?`, contracts + contract builtins (Phase 9), golden tests under `[sv0c/test/data/golden/](sv0c/test/data/golden/)`, E2E smoke.
- **Deferred to M2:** traits/impls/generics + method dispatch (plan **m1-p7**); modules / qualified paths / core prelude (plan **m1-p8**); and any items called out in the plan’s “Deferred” / “not Phase 6” bullets (e.g. `Vec`/`Box`, heap `string`, generic `Option`/`Result` as full builtins).
- **Reconcile** with the broad “In scope” bullet list in the same plan file (mark each line **M1 shipped**, **M1 partial**, or **M2** so readers are not misled).

1. **Optional one-line** link from `[sv0doc/README.md](sv0doc/README.md)` to `milestone-1-complete.md` (only if it fits existing tone).
2. **Mark** todo `**m1-doc`** as **completed** in `[.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md](.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md)`.
3. **Optional:** add a single sentence to `[sv0c/README.md](sv0c/README.md)` pointing at `milestone-1-complete.md` for “what M1 includes” (keeps sv0c users oriented without duplicating the full checklist).

## Repositories

- `**[sv0c/](sv0c/)`** has its **own** `.git` (workspace root `sv0-toolchain` is **not** a git repo).
- `**[sv0doc/](sv0doc/)`**has its own `.git**.

So “M1 complete” touches **two** trees; your request for **sv0c-only** git commands covers compiler + `sv0c/doc/` only. The new milestone doc lives under **sv0doc** and needs a **separate** commit there if you add it.

## Git commands to run manually — **sv0c** only

Adjust branch name and paths if yours differ. Run from a clean `make test` / `make e2e` after the doc edits you care to include in sv0c.

```bash
cd /path/to/sv0-toolchain/sv0c

git status
git diff

# Stage everything you intend to ship (example: all tracked changes)
git add -A

# Or stage selectively, e.g. only sources + sv0c docs:
# git add src/ test/ doc/ runtime/ Makefile sources.cm README.md

git commit -m "docs(sv0c): mark Milestone 1 compiler slice complete" -m "Reference sv0doc milestone-1-complete checklist; README pointer if added."

# If you prefer splitting compiler vs docs (optional second commit):
# git reset HEAD~1   # only if you committed too much and want to split — use with care
```

**Suggested conventional split (optional, two commits):**

```bash
git add src/ test/ runtime/ sources.cm Makefile
git commit -m "feat(sv0c): complete Milestone 1 bootstrap slice" -m "Phases 1-6 and 9: contracts, builtins, golden tests, diagnostics."

git add doc/ README.md
git commit -m "docs(sv0c): document passes and M1 completion pointers"
```

Then push (set your remote/branch):

```bash
git push -u origin HEAD
```

## Git commands — **sv0doc** (if you add `milestone-1-complete.md`)

```bash
cd /path/to/sv0-toolchain/sv0doc

git status
git add milestone-1-complete.md README.md   # include README only if changed
git commit -m "docs: add Milestone 1 completion checklist" -m "Shipped vs deferred to M2 for sv0c bootstrap compiler."
git push -u origin HEAD
```

## Git commands — **plan file** (optional)

`[.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md](.cursor/plans/sv0c_milestone_1_compiler_6c32a80e.plan.md)` lives under the **toolchain** folder, which is **not** a git repo in this workspace. If you track plans elsewhere, copy or commit that file in whatever repo you use for Cursor/meta; otherwise skip.
