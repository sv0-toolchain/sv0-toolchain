#!/usr/bin/env python3
"""M4-S-011: exercise the z3 driver (scripts/sv0-z3.sh) on known queries.

Skips cleanly (exit 0) when `z3` is not on PATH so local runs without a solver
don't fail; CI installs z3 so this actually runs there. Asserts:
  - a valid obligation's negation is `unsat` (proven),
  - an invalid one is `sat` (refuted),
  - a batch file (multiple `(check-sat)` via `(reset)`) yields one verdict per
    obligation, in order,
  - the SMT-LIB emitter's operator forms (`and`, `+`, `distinct`, `div`, `mod`)
    that verify_vcgen's `cexpr_to_smt` produces are accepted by z3.
"""
from __future__ import annotations
import argparse, shutil, subprocess, sys, tempfile, os
from pathlib import Path

# (name, smt2 text, expected verdict lines)
CASES = [
    ("proven_x_pos_implies_ge1",
     "(set-logic QF_LIA)(declare-const x Int)(assert (> x 0))(assert (not (>= x 1)))(check-sat)",
     ["unsat"]),
    ("refuted_x_gt_y",
     "(set-logic QF_LIA)(declare-const x Int)(declare-const y Int)(assert (not (> x y)))(check-sat)",
     ["sat"]),
    ("batch_unsat_then_sat",
     "(set-logic QF_LIA)(declare-const x Int)(assert (> x 0))(assert (not (>= x 1)))(check-sat)"
     "(reset)(set-logic QF_LIA)(declare-const y Int)(declare-const z Int)(assert (not (> y z)))(check-sat)",
     ["unsat", "sat"]),
    # emitter operator forms: (and (> va 0) (> vb 0)) => (> (+ va vb) 0)
    ("emitter_and_plus",
     "(set-logic QF_LIA)(declare-const va Int)(declare-const vb Int)"
     "(assert (and (> va 0) (> vb 0)))(assert (not (> (+ va vb) 0)))(check-sat)",
     ["unsat"]),
    # emitter distinct: a != b and a == b is unsat
    ("emitter_distinct",
     "(set-logic QF_LIA)(declare-const va Int)(declare-const vb Int)"
     "(assert (distinct va vb))(assert (= va vb))(check-sat)",
     ["unsat"]),
    # emitter div/mod (QF_NIA): even x => (x/2)*2 == x
    ("emitter_div_mod_nia",
     "(set-logic QF_NIA)(declare-const vx Int)"
     "(assert (= (mod vx 2) 0))(assert (not (= (* (div vx 2) 2) vx)))(check-sat)",
     ["unsat"]),
    # M4-S-003/010: the EXACT query verify_vcgen's vc_gen_ensures_query produces
    # for `f(x) requires(x>0) ensures(result>=1) { return x; }` (kept byte-identical
    # to the string asserted in test_vc_gen_ensures) — must be provable (unsat).
    ("vcgen_requires_implies_ensures",
     "(set-logic QF_LIA) (declare-const v0 Int) (declare-const result Int) "
     "(assert (> v0 0)) (assert (= result v0)) (assert (not (>= result 1))) (check-sat)",
     ["unsat"]),
    # the negative case: without the requires, result>=1 is NOT provable (sat).
    ("vcgen_no_requires_residual",
     "(set-logic QF_LIA) (declare-const v0 Int) (declare-const result Int) "
     "(assert (= result v0)) (assert (not (>= result 1))) (check-sat)",
     ["sat"]),
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    driver = root / "scripts" / "sv0-z3.sh"
    if not driver.is_file():
        print(f"verify_z3_driver: missing {driver}", file=sys.stderr)
        return 1

    if shutil.which("z3") is None:
        print("verify_z3_driver: SKIP (z3 not on PATH)", file=sys.stderr)
        return 0

    failures = 0
    with tempfile.TemporaryDirectory() as td:
        for name, smt2, want in CASES:
            qf = os.path.join(td, f"{name}.smt2")
            Path(qf).write_text(smt2 + "\n")
            proc = subprocess.run(["bash", str(driver), qf],
                                  capture_output=True, text=True, timeout=60)
            if proc.returncode != 0:
                print(f"verify_z3_driver: {name} driver exit {proc.returncode}: "
                      f"{(proc.stderr or '').strip()[-300:]}", file=sys.stderr)
                failures += 1
                continue
            got = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            if got != want:
                print(f"verify_z3_driver: {name} got {got}, want {want}", file=sys.stderr)
                failures += 1

    if failures:
        print(f"verify_z3_driver: {failures} failure(s)", file=sys.stderr)
        return 1
    print(f"verify_z3_driver: OK ({len(CASES)} query case(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
