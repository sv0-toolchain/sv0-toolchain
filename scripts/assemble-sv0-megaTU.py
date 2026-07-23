#!/usr/bin/env python3
"""Assemble the sv0 pipeline modules into one mega-TU (`.sv0`) — native-compose (A).

Per `sv0c/doc/native-compose-tradeoffs.md`, the recommended native full-compose is
option (A): concatenate the real `lib/*.sv0` pipeline modules into a single
translation unit whose one `main` drives the phases. Each module is a standalone
bootstrap unit with its own test `fn main` and `fn test_*`; concatenating them
requires stripping those (they collide and a compiler needs no unit tests) and,
for the back-end, namespacing the core types (`Expr`/`Value`/`Instr`/`Ty`) that
several modules redefine *differently* (see the doc). This assembler does the
deterministic source transform; the compose `main` (threading the real phases) is
A2.

Status: A1 handles the **front-end** module set (lex→parse→resolve), which has no
cross-module collisions once mains/tests are stripped, and appends a placeholder
`main`. Back-end modules + type namespacing land in later A1 increments via the
`rename_types` / `rename_fns` maps.

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

# Per-module renames for later back-end increments: {module_stem: {old: new}}.
# Applied as word-boundary text substitutions within that module only (covers type
# refs, `::` constructors, and `fn`/call sites). Empty for the front-end set.
RENAME_TYPES: dict[str, dict[str, str]] = {}
RENAME_FNS: dict[str, dict[str, str]] = {}


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


def assemble(sv0c_root: Path, rels: list[str]) -> str:
    parts: list[str] = [
        "/* Auto-assembled mega-TU — do not edit by hand.",
        "   Source: scripts/assemble-sv0-megaTU.py (native-compose option A).",
        "   Regenerate: ./scripts/sv0 assemble-megatu */",
        "",
    ]
    for rel in rels:
        f = sv0c_root / rel
        if not f.is_file():
            print(f"assemble-megatu: missing module {f}", file=sys.stderr)
            raise SystemExit(1)
        stem = f.stem
        body = strip_tests_and_main(f.read_text(encoding="utf-8"))
        if stem in RENAME_TYPES:
            body = apply_renames(body, RENAME_TYPES[stem])
        if stem in RENAME_FNS:
            body = apply_renames(body, RENAME_FNS[stem])
        parts.append(f"/* ===== module: {rel} ===== */")
        parts.append(body)
    # A1 placeholder compose main; A2 replaces this with the real phase-threading driver.
    parts.append("fn main() -> i32 { return 0; }")
    return "\n".join(parts) + "\n"


def compile_check(sv0c_root: Path, tu: Path) -> int:
    """SML -> C -> cc the assembled TU; return 0 on success."""
    heap = sv0c_root / "build" / "sv0c"
    if not (heap.exists() or heap.is_symlink()):
        print(f"assemble-megatu: missing SML heap {heap} (run: make -C sv0c heap)", file=sys.stderr)
        return 1
    c_out = tu.with_suffix(".c")
    ctl = Path("/tmp/.sv0_drv_path")
    try:
        ctl.write_text("")
    except OSError:
        pass
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
    rt = sv0c_root / "runtime"
    bin_out = tu.with_suffix(".bin")
    cc = subprocess.run(
        ["cc", "-std=c99", "-O0", "-I", str(rt), str(c_out),
         str(rt / "sv0_runtime.c"), "-o", str(bin_out)],
        capture_output=True, text=True, check=False,
    )
    if cc.returncode != 0:
        print("assemble-megatu: cc FAILED on assembled TU", file=sys.stderr)
        errs = [ln for ln in cc.stderr.splitlines() if "error:" in ln][:10]
        sys.stderr.write("\n".join(errs) + "\n")
        return 1
    nlines = c_out.read_text(encoding="utf-8", errors="replace").count("\n")
    print(f"assemble-megatu: OK — assembled TU compiles (SML->C {nlines} lines -> cc)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    ap.add_argument("--manifest", type=Path,
                    default=Path("sv0c/lib/megaTU-modules.list"))
    ap.add_argument("--out", type=Path, default=Path("build/megaTU.sv0"))
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
    tu = args.out if args.out.is_absolute() else root / args.out
    tu.parent.mkdir(parents=True, exist_ok=True)
    tu.write_text(assemble(sv0c_root, rels), encoding="utf-8")
    print(f"assemble-megatu: wrote {tu} ({len(rels)} module(s))")
    if args.check:
        return compile_check(sv0c_root, tu)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
