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

The launcher resolves its Python from ``PATH`` (SPEC 20.6.4) and refuses a
shim, so this script runs it with the caller's ``PATH`` reordered: the first
real interpreter's directory first, shim directories left out.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sv0cov" / "src"))

from sv0cov.formats.canonical_json import decode_canonical  # noqa: E402
from sv0cov.formats.doctor import validate  # noqa: E402


NAMES = ("python3.14", "python3.13")


def real(candidate: Path) -> bool | None:
    """True for an executable interpreter, False for a script (a shim), None when absent."""
    try:
        with open(candidate, "rb") as f:
            return f.read(2) != b"#!" and os.access(candidate, os.X_OK)
    except OSError:
        return None


def launcher_path() -> str | None:
    """The caller's PATH with the first real ``python3.14`` (else ``python3.13``) directory first and
    every directory holding a shim of either name left out, so the launcher's own search (3.14 before
    3.13, the first one found is authoritative) lands on a real interpreter. Everything else the smoke
    probes need from PATH (SML/NJ for vm-run, the C compiler) stays."""
    entries = [e for e in os.environ.get("PATH", "").split(os.pathsep) if e]
    found = next((e for name in NAMES for e in entries if real(Path(e) / name)), None)
    if found is None:
        return None
    kept = [e for e in entries if e != found and not any(real(Path(e) / name) is False for name in NAMES)]
    return os.pathsep.join([found, *kept])


def main() -> int:
    path = launcher_path()
    if path is None:
        print("verify_sv0cov_toolchain_doctor: no real python3.14 or python3.13 on PATH (sv0cov needs one)", file=sys.stderr)
        return 1
    env = {**os.environ, "PATH": path}
    # Build the fixture once on both backends first: a cold compiler build is not the doctor's to time,
    # and the doctor keeps no child output, so a failure here is the place to see why.
    fixture = ROOT / "sv0cov" / "resources" / "doctor" / "doctor-r1-smoke.sv0"
    with tempfile.TemporaryDirectory() as tmp:
        for args in (["native-compile", "--coverage=instrument", "-o", f"{tmp}/native", str(fixture)],
                     ["vm-native-compile", "--coverage=instrument", str(fixture), f"{tmp}/vm.sv0b"]):
            r = subprocess.run([str(ROOT / "scripts" / "sv0"), *args], cwd=tmp, stdin=subprocess.DEVNULL, capture_output=True, timeout=900)
            if r.returncode != 0:
                print(f"verify_sv0cov_toolchain_doctor: sv0 {args[0]} of the smoke fixture failed (exit {r.returncode}):\n"
                      f"{r.stdout.decode('utf-8', 'replace')}{r.stderr.decode('utf-8', 'replace')}", file=sys.stderr)
                return 1
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
