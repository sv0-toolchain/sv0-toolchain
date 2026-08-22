#!/usr/bin/env python3
"""M4-S-014: verification determinism.

Static verification must be reproducible: the same source must always yield the
same per-contract statuses, or a verify corpus/CI gate would flake. Determinism
has two sources here — the compiler's VC emission (a pure function of the parsed
program) and z3's verdict (pinned via `scripts/sv0-z3.sh`: `sat.random_seed=0
smt.random_seed=0` + a fixed timeout). This runs `./scripts/sv0 verify --json` on
a representative corpus module several times and asserts byte-identical output
every run.

Skips cleanly (exit 0) when `z3` is not on PATH (no solver ⇒ nothing to prove).
CI installs z3, so this actually runs there.
"""
from __future__ import annotations
import argparse, shutil, subprocess, sys
from pathlib import Path

# A module that exercises branches, nested branches, a loop, requires, and
# multiple ensures — the widest determinism surface in the corpus.
TARGET = "sv0c/test/verify/corpus/pilot_numeric.sv0"
RUNS = 3


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()

    target = root / TARGET
    if not target.is_file():
        print(f"verify_determinism: missing {target}", file=sys.stderr)
        return 1

    if shutil.which("z3") is None:
        print("verify_determinism: SKIP (z3 not on PATH)", file=sys.stderr)
        return 0

    outputs: list[str] = []
    for i in range(max(2, args.runs)):
        proc = subprocess.run(
            ["bash", str(root / "scripts" / "sv0"), "verify", "--json", str(target)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            print(f"verify_determinism: run {i} exit {proc.returncode}\n"
                  f"{(proc.stdout + proc.stderr)[-1200:]}", file=sys.stderr)
            return 1
        outputs.append(proc.stdout.strip())

    first = outputs[0]
    for i, out in enumerate(outputs[1:], start=1):
        if out != first:
            print(f"verify_determinism: run {i} differs from run 0\n"
                  f"--- run 0 ---\n{first}\n--- run {i} ---\n{out}", file=sys.stderr)
            return 1

    print(f"verify_determinism: OK ({len(outputs)} identical runs on {Path(TARGET).name})",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
