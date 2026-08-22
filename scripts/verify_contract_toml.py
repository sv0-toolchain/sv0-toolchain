#!/usr/bin/env python3
"""M4-S-025: sv0.toml `[build] contract-mode` is honored, and a `--contract-mode`
flag overrides it.

Sets up a temp project with a proven + an unproven contract and an sv0.toml
selecting `verified`, then checks:
  - `sv0 compile <file>`                     uses the file → verified (1 ensures kept),
  - `sv0 compile --contract-mode=runtime …`  the flag overrides → runtime (2 ensures).

Skips (exit 0) without z3 (verified mode needs the solver to prove anything). CI
installs z3.
"""
from __future__ import annotations
import argparse, shutil, subprocess, sys, tempfile
from pathlib import Path

FIXTURE = """\
fn proven(x: i32) -> i32
    requires(x > 0)
    ensures(result >= 1)
{
    return x;
}

fn unproven(x: i32) -> i32
    requires(x > 0)
    ensures(result >= 100)
{
    return x;
}

fn main() -> i32 {
    return proven(5) + unproven(5);
}
"""


def ensures_count(root: Path, args: list[str]) -> tuple[int, str]:
    proc = subprocess.run([str(root / "scripts" / "sv0")] + args,
                          capture_output=True, text=True, timeout=1200)
    if proc.returncode != 0:
        return (-1, proc.stderr[-800:])
    return (proc.stdout.count("sv0_ensures"), "")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()

    if shutil.which("z3") is None:
        print("verify_contract_toml: SKIP (z3 not on PATH)", file=sys.stderr)
        return 0

    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        src = proj / "demo.sv0"
        src.write_text(FIXTURE)
        (proj / "sv0.toml").write_text('[build]\ncontract-mode = "verified"\n')

        failures = 0
        file_ens, err1 = ensures_count(root, ["compile", str(src)])
        if file_ens != 1:
            print(f"verify_contract_toml: sv0.toml=verified gave {file_ens} sv0_ensures, want 1\n{err1}",
                  file=sys.stderr)
            failures += 1
        flag_ens, err2 = ensures_count(root, ["compile", "--contract-mode=runtime", str(src)])
        if flag_ens != 2:
            print(f"verify_contract_toml: --contract-mode=runtime gave {flag_ens} sv0_ensures, want 2 "
                  f"(flag must override sv0.toml)\n{err2}", file=sys.stderr)
            failures += 1

    if failures:
        return 1
    print("verify_contract_toml: OK (sv0.toml verified → 1 ensures; --contract-mode=runtime override → 2)",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
