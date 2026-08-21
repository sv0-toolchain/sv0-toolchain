#!/usr/bin/env bash
# M4-S-011: the z3 driver for sv0 contract verification.
#
# Per the driver-orchestrated design (M4-S-013), the sv0 compiler never spawns
# z3 — it write_file's SMT-LIB2, and this shell wrapper runs z3. The compiler +
# `sv0 verify` call this to discharge verification conditions.
#
# Runs z3 on an SMT-LIB2 query file with FIXED, deterministic options and echoes
# z3's per-(check-sat) verdict lines. A file may hold multiple obligations as
# multiple `(check-sat)` blocks separated by `(reset)`; z3 prints one line each,
# in order, so the caller maps line N to obligation N.
#
#   usage:   scripts/sv0-z3.sh <query.smt2>
#   stdout:  one verdict per (check-sat): `unsat` (proven) | `sat` (refuted) | `unknown`
#   exit:    0  z3 ran
#            2  z3 not on PATH  -> caller degrades every obligation to residual/runtime
#            3  usage / missing file
#
# `unsat` means the negated obligation is unsatisfiable, i.e. the obligation is
# PROVEN. `sat` means a counterexample exists (residual). `unknown`/timeout is
# residual. Determinism: fixed per-query timeout + random seeds so the verify
# corpus never flakes; override the timeout with SV0_Z3_TIMEOUT_MS.
set -euo pipefail

TIMEOUT_MS="${SV0_Z3_TIMEOUT_MS:-5000}"

if ! command -v z3 >/dev/null 2>&1; then
  echo "sv0-z3: z3 not found on PATH — verification degrades to all-runtime" >&2
  exit 2
fi

file="${1:-}"
if [[ -z "$file" || ! -f "$file" ]]; then
  echo "usage: sv0-z3.sh <query.smt2>" >&2
  exit 3
fi

# Deterministic: per-query timeout (ms) + fixed seeds. z3 prints one result line
# per (check-sat) on stdout; diagnostics go to stderr.
z3 -smt2 -t:"$TIMEOUT_MS" sat.random_seed=0 smt.random_seed=0 "$file"
