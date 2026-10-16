#!/usr/bin/env python3
"""``./scripts/sv0 coverage doctor`` against this checkout, end to end (CV-242).

sv0cov SPEC 20.7 / AC-117: the toolchain doctor passes offline from a clean
checkout. This runs the real root namespace twice with ``--json`` and
requires:

- exit 0 and a valid ``sv0cov.doctor`` aggregate in toolchain mode with
  every probe passing except ``D016``, which is ``not_applicable`` before
  R1 (SPEC 15.6);
- the same bytes both times, although each run collects fresh raw profiles
  with new profile IDs (planning-hub D-12);
- no path of this machine in the result.

The smoke probes build and run the bundled fixture through this checkout's
own ``scripts/sv0`` (generated C and VM-v1), so the native compiler and
SML/NJ must be available, as for ``./scripts/sv0 test``. D010 needs the
``sv0cov`` submodule at its gitlink with no change; with a dirty submodule
(sv0cov work in progress) the check reports that and fails.

The launcher resolves its Python from ``PATH`` (SPEC 20.6.4): the first
``python3.14`` or ``python3.13`` that is a real interpreter, never a shim.
This script builds that ``PATH`` from the first such interpreter it finds.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sv0cov" / "src"))

from sv0cov.formats.canonical_json import decode_canonical  # noqa: E402
from sv0cov.formats.doctor import validate  # noqa: E402


def interpreter_dir() -> str | None:
    """The first PATH directory holding a real ``python3.14`` (else ``python3.13``), not a script."""
    for name in ("python3.14", "python3.13"):
        for entry in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(entry) / name
            try:
                with open(candidate, "rb") as f:
                    if f.read(2) != b"#!" and os.access(candidate, os.X_OK):
                        return entry
            except OSError:
                continue
    return None


def main() -> int:
    where = interpreter_dir()
    if where is None:
        print("verify_sv0cov_toolchain_doctor: no real python3.14 or python3.13 on PATH (sv0cov needs one)", file=sys.stderr)
        return 1
    env = {**os.environ, "PATH": os.pathsep.join([where, "/usr/bin", "/bin"])}
    runs = []
    for _ in range(2):
        r = subprocess.run([str(ROOT / "scripts" / "sv0"), "coverage", "doctor", "--json"], cwd=ROOT, env=env,
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=600)
        runs.append(r)
        if r.returncode != 0:
            print(f"verify_sv0cov_toolchain_doctor: exit {r.returncode}\n{r.stderr.decode('utf-8', 'replace')}", file=sys.stderr)
            if r.stdout:
                bad = [(p["id"], p["status"], p["diagnostic_code"]) for p in decode_canonical(r.stdout)["probes"]
                       if p["status"] not in ("pass", "not_applicable")]
                print(f"verify_sv0cov_toolchain_doctor: {bad}", file=sys.stderr)
            return 1
    obj = validate(runs[0].stdout)
    errors = []
    statuses = {p["id"]: p["status"] for p in obj["probes"]}
    want = {f"D{n:03d}": "pass" for n in range(1, 19)} | {"D016": "not_applicable"}
    if obj["mode"] != "toolchain" or statuses != want:
        errors.append(f"mode {obj['mode']}, probes {statuses}")
    if runs[1].stdout != runs[0].stdout:
        errors.append("two runs gave different bytes")
    for path in {str(ROOT), str(Path.home()), "/tmp/", "/private/"}:
        if path.encode() in runs[0].stdout:
            errors.append(f"the result contains the path {path}")
    for e in errors:
        print(f"verify_sv0cov_toolchain_doctor: {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"verify_sv0cov_toolchain_doctor: 17 probes pass, D016 not applicable, stable bytes ({obj['doctor_sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
