#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# SPDX-FileCopyrightText: 2026 Sasank Vishnubhatla
"""Cross-host canonical coverage record (sv0cov CV-409; SPEC 25.1; COV-PORT-002/003).

``--write OUT`` builds every sv0cov semantic fixture and constructs.sv0 with
coverage instrumented through the real drivers on both backends
(``sv0 native-compile`` and ``sv0 vm-native-compile`` / ``vm-run``), runs
them, merges each backend's profile through the repository launcher
``sv0cov/scripts/sv0cov`` under a controlled PATH holding only the running
interpreter as ``python3.<minor>`` (SPEC 20.6.4: a 3.13 cell has no
``python3.14`` entry), and
writes, per program: the map digest, each backend's resolved per-point counts
digest, and each backend's semantic projection digest. Host facts go under
``host`` and are informational.

``--compare A B ...`` requires every record's ``programs`` to be identical:
canonical coverage meaning and projection bytes are platform-independent.

    python3 scripts/verify_coverage_host_record.py --write build/coverage-host.json
    python3 scripts/verify_coverage_host_record.py --compare a.json b.json ...
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLAN = ROOT / "sv0c" / "test" / "coverage" / "plan"
LAUNCHER = ROOT / "sv0cov" / "scripts" / "sv0cov"
sys.dont_write_bytecode = True
sys.path.insert(0, str(PLAN))
sys.path.insert(0, str(ROOT / "sv0cov" / "src"))
RUN_ID = "0123456789abcdef0123456789abcdef"  # run_vm_profile's; --compare needs no submodule


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _cell_path(t: Path) -> str:
    """A PATH whose only Python is this interpreter, under its own exact basename."""
    d = t / "cell-python"
    d.mkdir()
    (d / f"python3.{sys.version_info.minor}").symlink_to(os.path.realpath(sys.executable))
    return f"{d}:/usr/bin:/bin:/usr/sbin:/sbin"


def _projection(map_path: Path, profile: Path, work: Path, path: str) -> str:
    """Merge one map and one profile with the launcher; the evidence's semantic projection digest."""
    from sv0cov.model.indexed import read_indexed

    work.mkdir()
    (work / map_path.name).write_bytes(map_path.read_bytes())
    (work / profile.name).write_bytes(profile.read_bytes())
    p = subprocess.run([str(LAUNCHER), "merge", "--expect-run", RUN_ID, "--output", "-", "."], cwd=work, capture_output=True, timeout=300,
                       env={"PATH": path, "HOME": str(work)})
    if p.returncode:
        raise SystemExit(f"{work.name}: sv0cov merge exited {p.returncode}: {p.stderr.decode(errors='replace')[-600:]}")
    return read_indexed(p.stdout)["semantic_projection_sha256"]


def record(t: Path) -> dict:
    from run_hits import programs
    from run_vm_profile import RUN_ID as PLAN_RUN_ID, build_vm, sv0, transport, vm_run
    from sv0cov.resolve import resolve

    assert PLAN_RUN_ID == RUN_ID

    out = {}
    path = _cell_path(t)
    for name, request in programs():
        args = request.split(" ", 1) if request.startswith("--project") else [request]
        d = t / name
        (d / "vm").mkdir(parents=True)
        exe, sv0b = d / name, d / "vm" / f"{name}.sv0b"
        nmap, vmap = d / f"{name}.sv0covmap.json", d / "vm" / f"{name}.sv0covmap.json"
        p = sv0("native-compile", "--coverage=instrument", "-o", str(exe), *args)
        err = build_vm(args, sv0b)
        if p.returncode or err:
            raise SystemExit(f"{name}: build failed: {p.stderr.strip()} {err or ''}")
        if nmap.read_bytes() != vmap.read_bytes():
            raise SystemExit(f"{name}: the generated-C and VM maps differ")
        npdir, vpdir = d / "native-profiles", d / "vm-profiles"
        npdir.mkdir()
        vpdir.mkdir()
        rn = subprocess.run([str(exe)], capture_output=True, env=transport(npdir), timeout=60)
        rc, vout = vm_run(sv0b, d / "vm" / f"{name}.sv0covbind.json", transport(vpdir))
        if rc != rn.returncode:
            raise SystemExit(f"{name}: native exit {rn.returncode}, VM exit {rc}: {vout[-300:]}")
        (nprof,), (vprof,) = list(npdir.iterdir()), list(vpdir.iterdir())
        counts = {}
        for side, prof in (("native", nprof), ("vm", vprof)):
            c = resolve(nmap.read_bytes(), [prof.read_bytes()]).counts()
            counts[side] = _sha(json.dumps(sorted(c.items()), separators=(",", ":")).encode())
        out[name] = {
            "exit": rn.returncode,
            "map_sha256": _sha(nmap.read_bytes()),
            "native_counts_sha256": counts["native"],
            "native_projection_sha256": _projection(nmap, nprof, d / "merge-native", path),
            "vm_counts_sha256": counts["vm"],
            "vm_projection_sha256": _projection(nmap, vprof, d / "merge-vm", path),
        }
        if counts["native"] != counts["vm"]:
            raise SystemExit(f"{name}: native and VM counts differ")
    return out


def compare(paths: list[Path]) -> int:
    recs = [(p, json.loads(p.read_bytes())) for p in paths]
    base_path, base = recs[0]
    bad = 0
    for p, r in recs:
        print(f"{p.name}: {r['host']}")
        if r["programs"] != base["programs"]:
            bad += 1
            for name in sorted(set(base["programs"]) | set(r["programs"])):
                if base["programs"].get(name) != r["programs"].get(name):
                    print(f"  {name} differs from {base_path.name}: {r['programs'].get(name)} vs {base['programs'].get(name)}")
    if bad or len(recs) < 2:
        print(f"coverage host records: FAIL ({bad} of {len(recs)} differ{', need two or more' if len(recs) < 2 else ''})")
        return 1
    print(f"coverage host records: OK ({len(recs)} records, {len(base['programs'])} programs identical)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--write", type=Path)
    g.add_argument("--compare", type=Path, nargs="+")
    a = ap.parse_args()
    if a.compare:
        return compare(a.compare)
    from run_plan import ensure_built

    ensure_built()
    with tempfile.TemporaryDirectory(prefix="covhost-") as td:
        progs = record(Path(td))
    host = {"machine": platform.machine(), "python": platform.python_version(), "system": platform.system()}
    a.write.parent.mkdir(parents=True, exist_ok=True)
    a.write.write_text(json.dumps({"host": host, "programs": progs}, indent=2, sort_keys=True) + "\n")
    print(f"coverage host record: wrote {a.write} ({len(progs)} programs, {host})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
