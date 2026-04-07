#!/usr/bin/env python3
"""Fail if ``test/vm-parity/manifest.txt`` lists a path missing from ``lib/bootstrap-sources.list``.

``./scripts/sv0 test`` runs ``bootstrap-build`` from the bootstrap list, then compares
``build/vm/<stem>.sv0b`` to vm-parity goldens for every manifest entry. A path on the
manifest but not in the bootstrap list breaks CI on a clean checkout.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_paths(list_path: Path) -> list[str]:
    """Return non-empty, non-comment lines (stripped)."""
    out: list[str] = []
    for raw in list_path.read_text(encoding="utf-8").splitlines():
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
    sv0c = root / "sv0c"
    manifest = sv0c / "test" / "vm-parity" / "manifest.txt"
    bootstrap = sv0c / "lib" / "bootstrap-sources.list"
    for p in (manifest, bootstrap):
        if not p.is_file():
            print(f"verify_vm_parity_manifest_bootstrap: missing {p}", file=sys.stderr)
            return 1
    manifest_rels = load_paths(manifest)
    bootstrap_set = set(load_paths(bootstrap))
    missing = [rel for rel in manifest_rels if rel not in bootstrap_set]
    if missing:
        print(
            "verify_vm_parity_manifest_bootstrap: manifest paths not in "
            "lib/bootstrap-sources.list (bootstrap-build will not emit their .sv0b):",
            file=sys.stderr,
        )
        for rel in missing:
            print(f"  - {rel}", file=sys.stderr)
        print(
            "Add each path to sv0c/lib/bootstrap-sources.list (same order as manifest is optional).",
            file=sys.stderr,
        )
        return 1
    print(
        f"verify_vm_parity_manifest_bootstrap: OK ({len(manifest_rels)} manifest path(s) ⊆ bootstrap list)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
