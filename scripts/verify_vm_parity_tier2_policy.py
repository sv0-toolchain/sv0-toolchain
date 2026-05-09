#!/usr/bin/env python3
"""M3-S-045 tier-2 VM parity — policy guard (no bytecode emission).

Ensures tier2-manifest.txt exists, each path is listed in vm-parity manifest.txt,
and golden/sml/<stem>.sv0b exists for each stem (same goldens tier-1 uses until a
native bytecode emitter exists).

Compare harness: ./scripts/sv0 run_test calls run_vm_parity_tier2_emit_compare when
SV0_VM_BYTECODE_EMITTER is set (see sv0c/test/vm-parity/README.md § Tier 2).
This Python script remains the CI-safe policy-only check (no SML).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _lines(p: Path) -> list[str]:
    out: list[str] = []
    for raw in p.read_text(encoding="utf-8").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s.replace(" ", ""))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    tier_m = root / "sv0c" / "test" / "vm-parity" / "tier2-manifest.txt"
    vm_m = root / "sv0c" / "test" / "vm-parity" / "manifest.txt"
    golden_dir = root / "sv0c" / "test" / "vm-parity" / "golden" / "sml"
    if not tier_m.is_file():
        print(f"verify_vm_parity_tier2_policy: missing {tier_m}", file=sys.stderr)
        return 1
    if not vm_m.is_file():
        print(f"verify_vm_parity_tier2_policy: missing {vm_m}", file=sys.stderr)
        return 1
    vm_set = set(_lines(vm_m))
    tier_paths = _lines(tier_m)
    if not tier_paths:
        print("verify_vm_parity_tier2_policy: tier2-manifest empty", file=sys.stderr)
        return 1
    for rel in tier_paths:
        if rel not in vm_set:
            print(
                f"verify_vm_parity_tier2_policy: {rel} not in manifest.txt",
                file=sys.stderr,
            )
            return 1
        stem = Path(rel).stem
        g = golden_dir / f"{stem}.sv0b"
        if not g.is_file():
            print(
                f"verify_vm_parity_tier2_policy: missing golden {g}",
                file=sys.stderr,
            )
            return 1
    print(
        f"verify_vm_parity_tier2_policy: OK ({len(tier_paths)} tier-2 path(s))",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
