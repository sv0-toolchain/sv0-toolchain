#!/usr/bin/env python3
"""CV-102: every repository agrees with the sv0doc coverage identifier registry.

- ``sv0doc/bytecode/coverage-identifiers.json`` and the generated table in
  ``sv0doc/bytecode/coverage.md`` are current (``gen_coverage_identifiers.py``).
- sv0c and sv0vm carry byte-identical copies of the registry
  (``test/coverage-identifiers.json``) and of the checker
  (``scripts/check_coverage_identifiers.py``).
- The checker passes on sv0c, sv0vm, and sv0cov (opcode 119 reserved for
  ``COVER_HIT``; registry spellings exact).
- sv0cov's VM-binding implementation spells every VM identifier it owns.

    python3 scripts/verify_coverage_identifier_registry.py [--root DIR]
    python3 scripts/verify_coverage_identifier_registry.py --selftest
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REGISTRY = "sv0doc/bytecode/coverage-identifiers.json"
CHECKER = "sv0doc/scripts/check_coverage_identifiers.py"
COPIES = ("sv0c", "sv0vm")
SV0COV_BINDING = "sv0cov/src/sv0cov/formats/vmbinding.py"


def verify(root: Path) -> list[str]:
    errors = []
    r = subprocess.run([sys.executable, str(root / "sv0doc/scripts/gen_coverage_identifiers.py")], capture_output=True, text=True)
    if r.returncode:
        errors.append(f"sv0doc registry/table stale: {r.stderr.strip()}")
    registry = (root / REGISTRY).read_bytes()
    checker = (root / CHECKER).read_bytes()
    for repo in COPIES:
        for rel, want in ((f"{repo}/test/coverage-identifiers.json", registry), (f"{repo}/scripts/check_coverage_identifiers.py", checker)):
            p = root / rel
            if not p.is_file() or p.read_bytes() != want:
                errors.append(f"{rel} differs from its sv0doc original")
    for repo in (*COPIES, "sv0cov"):
        r = subprocess.run([sys.executable, str(root / CHECKER), "--repo", repo, "--root", str(root / repo), "--registry", str(root / REGISTRY)],
                           capture_output=True, text=True)
        if r.returncode:
            errors.append(f"{repo}: {r.stderr.strip()}")
    binding = (root / SV0COV_BINDING).read_text(encoding="utf-8")
    values = {i["name"]: i["value"] for i in json.loads(registry)["identifiers"]}
    for name in ("coverage_capability", "plan_capability", "v1_profile", "vm_binding_schema", "v2_section_tag"):
        if f'"{values[name]}"' not in binding:
            errors.append(f"{SV0COV_BINDING} does not spell {name} {values[name]!r}")
    return errors


def selftest() -> int:
    root = Path(__file__).resolve().parents[1]
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for rel in ("sv0doc/bytecode", "sv0doc/scripts", "sv0c/test", "sv0c/scripts", "sv0vm/test", "sv0vm/scripts", "sv0cov/src/sv0cov/formats"):
            (t / rel).mkdir(parents=True, exist_ok=True)
        for rel in (REGISTRY, CHECKER, "sv0doc/bytecode/coverage.md", "sv0doc/scripts/gen_coverage_identifiers.py", SV0COV_BINDING,
                    "sv0c/lib/bytecode.sv0", "sv0vm/src/bytecode/bytecode.sml"):
            (t / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, t / rel)
        for repo in COPIES:
            shutil.copy2(root / REGISTRY, t / repo / "test/coverage-identifiers.json")
            shutil.copy2(root / CHECKER, t / repo / "scripts/check_coverage_identifiers.py")
        if verify(t):
            failures.append(f"clean tree fails: {verify(t)}")
        mutations = {
            "registry copy": (t / "sv0vm/test/coverage-identifiers.json", lambda s: s.replace("sv0cov.plan.v1", "sv0cov.plan.v2")),
            "opcode collision": (t / "sv0c/lib/bytecode.sv0", lambda s: s.replace("{ return 116; }", "{ return 119; }", 1)),
            "sv0cov spelling": (t / SV0COV_BINDING, lambda s: s.replace('"sv0cov.plan.v1"', '"sv0cov.plan.V1"')),
        }
        for name, (path, fn) in mutations.items():
            original = path.read_text(encoding="utf-8")
            path.write_text(fn(original), encoding="utf-8")
            if not verify(t):
                failures.append(f"{name} mutation not detected")
            path.write_text(original, encoding="utf-8")
    for f in failures:
        print(f"verify_coverage_identifier_registry selftest: {f}", file=sys.stderr)
    if failures:
        return 1
    print("verify_coverage_identifier_registry selftest: clean tree passes; 3 mutations detected")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    errors = verify(args.root.resolve())
    for e in errors:
        print(f"verify_coverage_identifier_registry: {e}", file=sys.stderr)
    if errors:
        return 1
    print("verify_coverage_identifier_registry: sv0doc, sv0c, sv0vm, and sv0cov agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
