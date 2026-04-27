#!/usr/bin/env python3
"""Verify G1 Track C (M3-S-004 … M3-S-014) slice path sets contain no ``raise`` token.

Active slice IDs are listed one per line in ``scripts/m3_g1_active_slices.txt`` (repo root
relative). CI grows this list slice-by-slice; when **M3-S-014** is included, the script also
asserts the full ``sv0c/lib|lexer|parser`` ``*.sv0`` scan (same coverage as
``verify_compiler_sv0_no_raise.py``) for that slice row.

See ``task/sv0-toolchain-milestone-3-self-host.Rmd`` **## M3 G1 slice status (Track C)**.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# Paths are relative to the sv0-toolchain repo root.
SLICE_PATHS: dict[str, list[str] | None] = {
    "M3-S-004": ["sv0c/lib/parser.sv0"],
    "M3-S-005": ["sv0c/lib/parser.sv0"],
    "M3-S-006": ["sv0c/lib/parser.sv0"],
    "M3-S-007": ["sv0c/lib/checker.sv0"],
    "M3-S-008": ["sv0c/lib/checker.sv0"],
    "M3-S-009": ["sv0c/lib/lowering.sv0"],
    "M3-S-010": ["sv0c/lib/resolver.sv0"],
    "M3-S-011": ["sv0c/lib/vm_codegen.sv0"],
    "M3-S-012": [
        "sv0c/lib/codegen.sv0",
        "sv0c/lib/bytecode.sv0",
        "sv0c/lib/env.sv0",
    ],
    "M3-S-013": [
        "sv0c/lib/link.sv0",
        "sv0c/lib/lexer.sv0",
        "sv0c/lib/include_expand.sv0",
        "sv0c/lib/unify.sv0",
        "sv0c/lib/diagnostic.sv0",
    ],
    "M3-S-014": None,
}


def _load_compiler_module(root: Path):
    spec = importlib.util.spec_from_file_location(
        "_v_compiler_raise",
        root / "scripts" / "verify_compiler_sv0_no_raise.py",
    )
    if spec is None or spec.loader is None:
        print("verify_m3_g1_track_c: cannot load verify_compiler_sv0_no_raise.py", file=sys.stderr)
        sys.exit(1)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_active_slice_ids(root: Path) -> list[str]:
    p = root / "scripts" / "m3_g1_active_slices.txt"
    if not p.is_file():
        return []
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, required=True, help="sv0-toolchain repo root")
    args = ap.parse_args()
    root: Path = args.root.resolve()
    active = _load_active_slice_ids(root)
    if not active:
        print("verify_m3_g1_track_c: OK (no scripts/m3_g1_active_slices.txt or empty — skip)")
        return 0

    vmod = _load_compiler_module(root)
    raise_re = vmod.RAISE_RE
    sv0c = root / "sv0c"
    if not sv0c.is_dir():
        print(f"verify_m3_g1_track_c: missing {sv0c}", file=sys.stderr)
        return 1

    def collect_hits(paths: list[Path]) -> list[tuple[Path, int, str]] | None:
        hits: list[tuple[Path, int, str]] = []
        for path in paths:
            if not path.is_file():
                print(
                    f"verify_m3_g1_track_c: missing file {path.relative_to(root)}",
                    file=sys.stderr,
                )
                return None
            text = path.read_text(encoding="utf-8")
            for i, line in enumerate(text.splitlines(), start=1):
                if raise_re.search(line):
                    hits.append((path.relative_to(root), i, line.rstrip()))
        return hits

    for sid in active:
        if sid not in SLICE_PATHS:
            print(f"verify_m3_g1_track_c: unknown slice id {sid!r} in m3_g1_active_slices.txt", file=sys.stderr)
            return 1
        rels = SLICE_PATHS[sid]
        if rels is None:
            paths = vmod.iter_sv0_files(sv0c)
        else:
            paths = [(root / r).resolve() for r in rels]
        hits = collect_hits(paths)
        if hits is None:
            return 1
        if hits:
            print(
                f"verify_m3_g1_track_c: slice {sid}: `raise` found in scoped .sv0:",
                file=sys.stderr,
            )
            for rel, lineno, line in hits:
                print(f"  {rel}:{lineno}: {line}", file=sys.stderr)
            return 1
        n = len(paths)
        print(f"verify_m3_g1_track_c: slice {sid}: OK ({n} path(s))")

    print(f"verify_m3_g1_track_c: OK ({len(active)} active slice(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
