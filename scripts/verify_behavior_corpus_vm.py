#!/usr/bin/env python3
"""Behavioral PASS corpus — VM leg.

Runs every program in sv0c/test/behavior/manifest.txt on the bytecode VM and
asserts the exit matches. Two batched SML processes (fast — no per-program SML
startup):
  1. compile all programs to .sv0b with the SML `--target=vm` path
     (Main.compileFileVm — the complete reference VM emitter; the native VM
     emitter panics on some constructs such as contracts).
  2. run every .sv0b on sv0vm in one process, comparing vm_exit masked to 0-255
     (a process-exit) against the manifest's expected exit.

Complements verify_behavior_corpus_native.py (the C leg). Run by `./scripts/sv0 test`.
"""
from __future__ import annotations
import argparse, subprocess, sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    sv0c = root / "sv0c"
    sv0vm = root / "sv0vm"
    manifest = sv0c / "test" / "behavior" / "manifest.txt"
    if not manifest.is_file():
        print(f"verify_behavior_corpus_vm: missing {manifest}", file=sys.stderr)
        return 1

    rows: list[tuple[str, str, int]] = []  # (stem, abs_sv0_path, want)
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Format: rel | exit [ | leg ]   leg in {both (default), native}.
        # The VM leg SKIPS rows tagged "native" (features the VM backend does not
        # yet support, e.g. chained field access — see the behavior README).
        parts = [s.strip() for s in line.split("|")]
        rel, want_s = parts[0], parts[1]
        leg = parts[2] if len(parts) > 2 and parts[2] else "both"
        if leg == "native":
            continue
        case = sv0c / rel
        if not case.is_file():
            print(f"verify_behavior_corpus_vm: missing case {case}", file=sys.stderr)
            return 1
        rows.append((case.stem, str(case), int(want_s)))

    (sv0c / "build" / "vm").mkdir(parents=True, exist_ok=True)

    # Phase 1: compile all to build/vm/<stem>.sv0b in one SML process.
    paths_sml = ", ".join(f'"{p}"' for _s, p, _w in rows)
    compile_script = (
        'CM.make "sources.cm";\n'
        "fun doCompile p = (Main.compileFileVm p; print (\"CRES\\t\" ^ p ^ \"\\tOK\\n\"))\n"
        "  handle _ => print (\"CRES\\t\" ^ p ^ \"\\tERR\\n\");\n"
        f"val () = List.app doCompile [{paths_sml}];\n"
        "OS.Process.exit OS.Process.success;\n"
    )
    cproc = subprocess.run(["sml"], input=compile_script, cwd=str(sv0c),
                           capture_output=True, text=True, timeout=1200)
    cres: dict[str, str] = {}
    for ln in (cproc.stdout or "").splitlines():
        if ln.startswith("CRES\t"):
            _, p, st = ln.split("\t", 2)
            cres[p] = st
    for stem, p, _w in rows:
        if cres.get(p) != "OK":
            print(f"verify_behavior_corpus_vm: VM compile failed for {stem}", file=sys.stderr)
            print((cproc.stdout or "")[-1500:], file=sys.stderr)
            print((cproc.stderr or "")[-800:], file=sys.stderr)
            return 1

    # Phase 2: run every .sv0b on sv0vm in one process.
    entries = [(stem, str(sv0c / "build" / "vm" / f"{stem}.sv0b"), want) for stem, _p, want in rows]
    cases_sml = ", ".join(f'("{s}","{p}")' for s, p, _w in entries)
    run_script = (
        'use "src/main.sml";\n'
        "fun runOne (stem, path) =\n"
        "  (let val e = Interpreter.runFile path\n"
        '   in print (\"VMRES\\t\" ^ stem ^ \"\\t\" ^ Int.toString e ^ \"\\n\") end)\n'
        '  handle _ => print (\"VMRES\\t\" ^ stem ^ \"\\tERR\\n\");\n'
        f"val () = List.app runOne [{cases_sml}];\n"
        "OS.Process.exit OS.Process.success;\n"
    )
    rproc = subprocess.run(["sml"], input=run_script, cwd=str(sv0vm),
                           capture_output=True, text=True, timeout=1200)
    got: dict[str, str] = {}
    for ln in (rproc.stdout or "").splitlines():
        if ln.startswith("VMRES\t"):
            _, stem, val = ln.split("\t", 2)
            got[stem] = val

    failures = 0
    for stem, _p, want in entries:
        v = got.get(stem)
        if v is None or v == "ERR":
            print(f"verify_behavior_corpus_vm: {stem} " +
                  ("raised on the VM" if v == "ERR" else "produced no VM result"), file=sys.stderr)
            failures += 1
            continue
        masked = ((int(v) % 256) + 256) % 256
        if masked != want:
            print(f"verify_behavior_corpus_vm: {stem} vm_exit={v} (masked {masked}), expected {want}",
                  file=sys.stderr)
            failures += 1
    if failures:
        print(f"verify_behavior_corpus_vm: {failures} failure(s)", file=sys.stderr)
        return 1
    print(f"verify_behavior_corpus_vm: OK ({len(entries)} program(s) on the VM)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
