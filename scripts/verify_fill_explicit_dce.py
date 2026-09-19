#!/usr/bin/env python3
"""SS-U11 / NEW-003 (task/sv0c-non-eliding-write.Rmd): DCE-stress proof
that sv0_fill_explicit's stores survive dead-code elimination where a
naive (pre-SS-U11) fill lowering would not.

Compiling correctly and running to the right exit code (already covered
by sv0c/test/behavior/cases/fill_explicit_intrinsic.sv0) proves
CORRECTNESS, not the non-elision GUARANTEE itself -- the guarantee is
specifically about what happens to writes to a buffer that is otherwise
dead, which no ordinary "compile + run + check exit code" test can
observe (that is exactly the point: if the guarantee holds, the buffer's
final memory contents are unobservable by the program itself either way).

The only way to actually verify the guarantee is to inspect the compiled
code. This script:

  1. Compiles test/dce-stress/fill_explicit_dce_stress.c at -O2 with -S
     (assembly output) using the real toolchain compiler.
  2. Asserts `naive_fill_wrapper` (the pre-SS-U11-shaped fill, writing to
     a buffer that is immediately freed and never read) does NOT appear
     as a callable symbol in the optimized assembly at all -- proof the
     compiler considered its entire effect provably unobservable and
     eliminated it outright (real, observed clang/gcc -O2 behavior for
     this exact shape, not a hypothetical).
  3. Asserts `explicit_fill_wrapper` (the sv0_fill_explicit path, same
     dead-buffer shape) DOES appear, and that its compiled body contains
     a genuine memory-store instruction sequence -- proof the write
     survived optimization even though nothing ever reads the result.

A regression here means the C-side non-elision guarantee has silently
stopped holding -- e.g. if `sv0_fill_explicit`'s `volatile` qualifier
were ever accidentally dropped, or a future compiler/optimization flag
change legalized removing it.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SV0C = ROOT / "sv0c"
SRC = SV0C / "test" / "dce-stress" / "fill_explicit_dce_stress.c"
RUNTIME_DIR = SV0C / "runtime"

# A conservative, cross-platform-tolerant signal that a function's
# compiled body performs at least one memory-store operation. Matches
# both AArch64 (`str`, `stur`) and x86-64 (AT&T `mov ..., (%reg)` /
# `movq ..., (%reg)`) store shapes without pinning an exact instruction
# count or register allocation, which varies by compiler/version.
STORE_INSN = re.compile(
    r"^\s*(str[bhwx]?\b|stur\b|mov[bwlq]?\s+\S+,\s*[-0-9]*\(%\w+\))",
    re.IGNORECASE,
)


def find_function_body(asm: str, label: str) -> str | None:
    """Returns the assembly lines belonging to `label`'s function body
    (from its label to the next top-level label / directive that starts
    a new function), or None if `label` never appears at all -- the
    signal a whole function was eliminated."""
    lines = asm.splitlines()
    start = None
    for i, line in enumerate(lines):
        # Matches both `_label:` (Mach-O) and `label:` (ELF) definitions.
        if re.match(rf"^_?{re.escape(label)}:", line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        # A new global/local function label ends this one's body.
        if re.match(r"^_?[A-Za-z_][A-Za-z0-9_]*:\s*(;.*)?$", lines[j]) and (
            "naive_fill" in lines[j]
            or "explicit_fill_wrapper" in lines[j]
            or "main:" in lines[j]
            or lines[j].startswith("_main:")
        ):
            end = j
            break
    return "\n".join(lines[start:end])


def main() -> int:
    if not SRC.exists():
        print(f"verify_fill_explicit_dce: missing {SRC}", file=sys.stderr)
        return 1

    cc = os.environ.get("CC", "cc")
    asm_path = ROOT / "build" / "fill_explicit_dce_stress.s"
    asm_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        cc,
        "-std=c11",
        "-O2",
        "-I",
        str(RUNTIME_DIR),
        "-S",
        str(SRC),
        "-o",
        str(asm_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print("verify_fill_explicit_dce: compile failed", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return 1

    asm = asm_path.read_text()
    errors = []

    # naive_fill_wrapper (and naive_fill, its only caller-visible effect)
    # must be fully eliminated: neither symbol should exist anywhere in
    # the optimized output.
    for naive_label in ("naive_fill_wrapper", "naive_fill"):
        if find_function_body(asm, naive_label) is not None:
            errors.append(
                f"'{naive_label}' still appears in the -O2 assembly -- "
                "the compiler no longer eliminates a dead naive fill on "
                "this toolchain. This is NOT a bug in sv0_fill_explicit; "
                "it means the baseline this test compares against has "
                "changed and the test itself needs re-grounding (confirm "
                "the compiler version / flags actually still perform "
                "this optimization before assuming a regression)."
            )

    # explicit_fill_wrapper must survive, with real store instructions
    # inside its body -- proof the write was not elided.
    body = find_function_body(asm, "explicit_fill_wrapper")
    if body is None:
        errors.append(
            "'explicit_fill_wrapper' does not appear in the -O2 assembly "
            "at all -- sv0_fill_explicit's non-elision guarantee has "
            "been broken (the whole call was eliminated, exactly like "
            "the naive path)."
        )
    else:
        store_lines = [ln for ln in body.splitlines() if STORE_INSN.match(ln)]
        if not store_lines:
            errors.append(
                "'explicit_fill_wrapper' appears in the -O2 assembly but "
                "its compiled body has no recognizable store instruction "
                "-- sv0_fill_explicit's writes appear to have been "
                "eliminated even though the call itself was not."
            )

    if errors:
        print("verify_fill_explicit_dce: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        print(f"  (assembly written to {asm_path} for inspection)", file=sys.stderr)
        return 1

    print(
        "verify_fill_explicit_dce: OK -- naive_fill_wrapper fully "
        "eliminated at -O2 (dead store), explicit_fill_wrapper's "
        f"sv0_fill_explicit call retained {len(store_lines)} store "
        "instruction(s) despite an identically-dead destination buffer "
        f"(cc={cc})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
