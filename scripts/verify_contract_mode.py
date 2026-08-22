#!/usr/bin/env python3
"""M4-S-023/024: verified contract-mode — proven checks are stripped, soundly.

`./scripts/sv0 emit-verified <file>` runs static verification, then recompiles
emitting the C with the PROVEN `ensures` runtime checks removed while keeping the
unproven ones and all `requires` preconditions. This checks, on
sv0c/test/verify/contract_mode_demo.sv0:

  - runtime mode (plain native compile) emits 2 `sv0_ensures` (both functions),
  - verified mode emits 1 `sv0_ensures` (only `unproven`'s survives) and still
    2 `sv0_requires` (preconditions are never stripped),
  - the stripped C still compiles (cc) — i.e. verified-mode output is valid.

Skips (exit 0) when z3 is not on PATH: with no solver nothing is proven, so
verified mode keeps every check (still sound) and the "stripped" assertion can't
hold. CI installs z3.
"""
from __future__ import annotations
import argparse, shutil, subprocess, sys, tempfile
from pathlib import Path

FIXTURE = "sv0c/test/verify/contract_mode_demo.sv0"


def count(text: str, needle: str) -> int:
    return text.count(needle)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()

    fixture = root / FIXTURE
    if not fixture.is_file():
        print(f"verify_contract_mode: missing fixture {fixture}", file=sys.stderr)
        return 1
    if shutil.which("z3") is None:
        print("verify_contract_mode: SKIP (z3 not on PATH)", file=sys.stderr)
        return 0

    sv0 = str(root / "scripts" / "sv0")

    # verified mode (also builds the native compiler + verify binary on first use)
    vproc = subprocess.run([sv0, "emit-verified", str(fixture)],
                           capture_output=True, text=True, timeout=1200)
    if vproc.returncode != 0:
        print(f"verify_contract_mode: emit-verified exit {vproc.returncode}\n{vproc.stderr[-1200:]}",
              file=sys.stderr)
        return 1
    verified_c = vproc.stdout

    # runtime baseline via the native compiler wrapper (no --verified)
    wrapper = root / "build" / "sv0-megatu-compiler-native"
    rproc = subprocess.run([str(wrapper), str(fixture)],
                           capture_output=True, text=True, timeout=600)
    if rproc.returncode != 0:
        print(f"verify_contract_mode: runtime compile exit {rproc.returncode}\n{rproc.stderr[-800:]}",
              file=sys.stderr)
        return 1
    runtime_c = rproc.stdout

    failures = 0
    r_ens = count(runtime_c, "sv0_ensures")
    v_ens = count(verified_c, "sv0_ensures")
    v_req = count(verified_c, "sv0_requires")
    if r_ens != 2:
        print(f"verify_contract_mode: runtime sv0_ensures = {r_ens}, want 2", file=sys.stderr)
        failures += 1
    if v_ens != 1:
        print(f"verify_contract_mode: verified sv0_ensures = {v_ens}, want 1 (proven stripped)",
              file=sys.stderr)
        failures += 1
    if v_req != 2:
        print(f"verify_contract_mode: verified sv0_requires = {v_req}, want 2 (preconditions kept)",
              file=sys.stderr)
        failures += 1

    # the stripped C must still compile
    with tempfile.TemporaryDirectory() as td:
        cpath = Path(td) / "verified.c"
        cpath.write_text(verified_c)
        binpath = Path(td) / "verified_run"
        cc = subprocess.run(
            ["cc", "-std=c99", "-O0", "-I", str(root / "sv0c" / "runtime"),
             "-o", str(binpath), str(cpath), str(root / "sv0c" / "runtime" / "sv0_runtime.c")],
            capture_output=True, text=True, timeout=120,
        )
        if cc.returncode != 0:
            print(f"verify_contract_mode: stripped C failed to compile\n{cc.stderr[-1000:]}",
                  file=sys.stderr)
            failures += 1

    if failures:
        return 1
    print("verify_contract_mode: OK (verified mode stripped 1/2 proven ensures, kept requires, "
          "output compiles)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
