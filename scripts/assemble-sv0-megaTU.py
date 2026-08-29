#!/usr/bin/env python3
"""Assemble the sv0 pipeline modules into one mega-TU (`.sv0`) — native-compose (A).

Per `sv0c/doc/archive/native-compose-tradeoffs.md`, the recommended native full-compose is
option (A): concatenate the real `lib/*.sv0` pipeline modules into a single
translation unit whose one `main` drives the phases. Each module is a standalone
bootstrap unit with its own test `fn main` and `fn test_*`; concatenating them
requires stripping those (they collide and a compiler needs no unit tests) and,
for the back-end, namespacing the core types (`Expr`/`Value`/`Instr`/`Ty`) that
several modules redefine *differently* (see the doc). This assembler does the
deterministic source transform; the compose `main` (threading the real phases) is
A2.

Status: A1 assembles the **full 18-module pipeline** into one TU that compiles
(SML→C ~34k lines → cc, binary runs). Collisions are handled by **auto-namespacing**
— any top-level name a module defines that an earlier module already claimed is
renamed `<stem>_<name>` (definition + every word-boundary use within that module),
so the back-end's divergent core types coexist (`lowering_Value`, `codegen_Value`,
…). A placeholder `main` is appended; **A2** replaces it with the real compose main.

Usage:
  scripts/assemble-sv0-megaTU.py --manifest sv0c/lib/megaTU-modules.list --out build/megaTU.sv0
  scripts/assemble-sv0-megaTU.py ... --check   # also SML->C->cc compile the result

The manifest lists module paths relative to `sv0c/` (one per line, `#` comments).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from native_exe_canonical_compile import compile_and_publish
from native_exe_errors import BuildError

# Forced per-module renames (escape hatch for anything auto-namespacing gets wrong):
# {module_stem: {old: new}}, applied as word-boundary substitutions before auto pass.
FORCED_RENAMES: dict[str, dict[str, str]] = {}


def module_defs(body: str) -> set[str]:
    """Top-level names a module DEFINES (fn / struct / enum). sv0 has no top-level
    `type` alias; constants are `fn`. These are the only names that can collide."""
    fns = set(re.findall(r"(?m)^fn\s+([A-Za-z0-9_]+)\s*\(", body))
    types = set(re.findall(r"(?m)^(?:struct|enum)\s+([A-Za-z0-9_]+)", body))
    return fns | types


def strip_top_fn(text: str, name: str) -> str:
    """Remove every top-level `fn <name>(...) { ... }` (balanced braces)."""
    out: list[str] = []
    i = 0
    pat = re.compile(r"(?m)^fn\s+" + re.escape(name) + r"\s*\(")
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        brace = text.index("{", m.end())
        depth = 0
        j = brace
        while j < len(text):
            c = text[j]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        i = j + 1
    return "".join(out)


def strip_tests_and_main(text: str) -> str:
    text = strip_top_fn(text, "main")
    tests = sorted(
        set(re.findall(r"(?m)^fn\s+(test_[A-Za-z0-9_]+)\s*\(", text)),
        key=len,
        reverse=True,
    )
    for nm in tests:
        text = strip_top_fn(text, nm)
    return text


def apply_renames(text: str, renames: dict[str, str]) -> str:
    for old, new in renames.items():
        text = re.sub(r"\b" + re.escape(old) + r"\b", new, text)
    return text


def read_manifest(path: Path) -> list[str]:
    mods: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        mods.append(line)
    return mods


def assemble(sv0c_root: Path, rels: list[str], compose_main: str | None = None) -> str:
    parts: list[str] = [
        "/* Auto-assembled mega-TU — do not edit by hand.",
        "   Source: scripts/assemble-sv0-megaTU.py (native-compose option A).",
        "   Regenerate: ./scripts/sv0 assemble-megatu */",
        "",
    ]
    # Auto-namespacing: modules are standalone (never cross-reference), so any
    # top-level name a module defines that an EARLIER module already claimed is
    # renamed `<stem>_<name>` here (definition + every word-boundary use within
    # this module). The first definer keeps the bare name. Runtime builtins /
    # primitives (vec_new, Vec, i32, …) are defined by no module and never renamed.
    claimed: set[str] = set()
    for rel in rels:
        f = sv0c_root / rel
        if not f.is_file():
            print(f"assemble-megatu: missing module {f}", file=sys.stderr)
            raise SystemExit(1)
        stem = f.stem
        body = strip_tests_and_main(f.read_text(encoding="utf-8"))
        if stem in FORCED_RENAMES:
            body = apply_renames(body, FORCED_RENAMES[stem])
        my = module_defs(body)
        collide = sorted(my & claimed, key=len, reverse=True)
        for name in collide:
            body = re.sub(r"\b" + re.escape(name) + r"\b", f"{stem}_{name}", body)
        for name in my:
            claimed.add(f"{stem}_{name}" if name in set(collide) else name)
        if collide:
            print(f"assemble-megatu: {rel}: namespaced {len(collide)} name(s): "
                  + ", ".join(collide), file=sys.stderr)
        parts.append(f"/* ===== module: {rel} ===== */")
        parts.append(body)
    # Compose main (A2): if `compose_main` is provided it is appended verbatim (it
    # calls the now-visible real phase entry points — tokenize, parse_program,
    # lower, emit_program — by their bare names, which the first-definer keeps).
    # It is NOT auto-namespaced (its calls must reach those bare entry points) and
    # must use unique helper names (mega_*). Otherwise a placeholder main is used.
    if compose_main is not None:
        parts.append("/* ===== compose main (A2) ===== */")
        parts.append(compose_main)
    else:
        parts.append("fn main() -> i32 { return 0; }")
    return "\n".join(parts) + "\n"


def compile_check(sv0c_root: Path, tu: Path) -> int:
    """SML -> C -> cc the assembled TU; return 0 on success."""
    heap = sv0c_root / "build" / "sv0c"
    if not (heap.exists() or heap.is_symlink()):
        print(f"assemble-megatu: missing SML heap {heap} (run: make -C sv0c heap)", file=sys.stderr)
        return 1
    c_out = tu.with_suffix(".c")
    # NEX-055c/REL-004 closure: the legacy /tmp/.sv0_drv_path control file this
    # used to defensively reset (in case a caller-supplied compose-main read it)
    # is retired -- no compose-main in this codebase reads it any more, and a
    # static guard (native_exe_no_new_legacy_control_file.py) fails closed on
    # any new one that would.
    with c_out.open("w") as fh:
        r = subprocess.run(
            ["sml", f"@SMLload={heap}", str(tu.resolve())],
            stdout=fh,
            stderr=subprocess.PIPE,
            cwd=sv0c_root,
            text=True,
            check=False,
        )
    if r.returncode != 0 or c_out.stat().st_size == 0:
        print("assemble-megatu: SML emit FAILED", file=sys.stderr)
        sys.stderr.write(r.stderr[-2000:])
        return 1
    bin_out = tu.with_suffix(".bin")
    try:
        compile_and_publish(str(c_out), str(bin_out))
    except BuildError as exc:
        print("assemble-megatu: cc FAILED on assembled TU", file=sys.stderr)
        errs = [ln for ln in str(exc).splitlines() if "error:" in ln][:10]
        sys.stderr.write("\n".join(errs) + "\n")
        return 1
    # Run it: the compose main returns 0 on success (its A2 smoke); the placeholder
    # main also returns 0. A non-zero exit means the composed phases misbehaved.
    run = subprocess.run([str(bin_out)], capture_output=True, text=True, check=False)
    if run.returncode != 0:
        print(f"assemble-megatu: assembled TU ran but exited {run.returncode} "
              "(compose main smoke failed)", file=sys.stderr)
        sys.stderr.write(run.stderr[-1000:])
        return 1
    nlines = c_out.read_text(encoding="utf-8", errors="replace").count("\n")
    print(f"assemble-megatu: OK — assembled TU compiles (SML->C {nlines} lines -> cc) and runs (exit 0)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--manifest", type=Path,
                    default=Path("sv0c/lib/megaTU-modules.list"))
    ap.add_argument("--out", type=Path, default=Path("build/megaTU.sv0"))
    ap.add_argument("--main", type=Path, default=Path("sv0c/lib/megaTU-main.sv0"),
                    help="Compose-main source appended verbatim (A2). If missing, a "
                         "placeholder `main` is used.")
    ap.add_argument("--check", action="store_true",
                    help="Also SML->C->cc compile the assembled TU.")
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    sv0c_root = root / "sv0c"
    manifest = args.manifest if args.manifest.is_absolute() else root / args.manifest
    if not manifest.is_file():
        print(f"assemble-megatu: missing manifest {manifest}", file=sys.stderr)
        return 1
    rels = read_manifest(manifest)
    if not rels:
        print(f"assemble-megatu: empty manifest {manifest}", file=sys.stderr)
        return 1
    main_path = args.main if args.main.is_absolute() else root / args.main
    compose_main = main_path.read_text(encoding="utf-8") if main_path.is_file() else None
    tu = args.out if args.out.is_absolute() else root / args.out
    tu.parent.mkdir(parents=True, exist_ok=True)
    tu.write_text(assemble(sv0c_root, rels, compose_main), encoding="utf-8")
    kind = "compose main" if compose_main is not None else "placeholder main"
    print(f"assemble-megatu: wrote {tu} ({len(rels)} module(s), {kind})")
    if args.check:
        return compile_check(sv0c_root, tu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
