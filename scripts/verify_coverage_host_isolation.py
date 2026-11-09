#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# SPDX-FileCopyrightText: 2026 Sasank Vishnubhatla
"""Per-host runtime selection and site isolation, end to end (sv0cov CV-409;
SPEC 20.6.4, 25.2.1; COV-PORT-005..007, R1-G10).

On this host, with the interpreter running this script (the matrix cell's
CPython 3.13 or 3.14):

1. constructs.sv0 is built with coverage instrumented through the real
   driver and run, giving one map and one raw profile;
2. ``sv0cov/scripts/sv0cov merge`` of them runs with a controlled PATH
   holding only this interpreter (as ``python3.<minor>``), then with an
   empty virtual environment's bin directory, then with a poisoned one (a
   shadowing ``sv0cov`` package, ``sitecustomize``, ``usercustomize`` and a
   ``.pth`` hook in its site-packages, ``PYTHON*`` poisoning, and a shadowing
   package in the working directory). The three evidence outputs must be
   byte-identical, no hook may run, and ``version --json`` must report this
   interpreter's exact version each time;
3. with ``--unsupported PY`` (a CPython 3.12), the launcher must fail early
   with COV0016, exit 7 and nothing on stdout, both when ``python3.12`` is the
   only interpreter on PATH and when it sits under the ``python3.13`` name.

    python3 scripts/verify_coverage_host_isolation.py [--unsupported /path/to/python3.12]
"""

from __future__ import annotations

import argparse
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
from run_plan import ensure_built  # noqa: E402
from run_vm_profile import RUN_ID, sv0, transport  # noqa: E402

NAME = f"python3.{sys.version_info.minor}"
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def launch(path: str, args: list[str], cwd: Path, extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": path, "HOME": str(cwd), **(extra or {})}
    return subprocess.run([str(LAUNCHER), *args], env=env, cwd=cwd, capture_output=True, timeout=300)


def venv(at: Path) -> Path:
    subprocess.run([os.path.realpath(sys.executable), "-m", "venv", "--without-pip", str(at)], check=True, capture_output=True, timeout=300)
    return at / "bin"


def poison(bindir: Path, mark: Path) -> Path:
    site = Path(subprocess.run([str(bindir / "python"), "-c", "import sysconfig; print(sysconfig.get_paths()['purelib'])"],
                               check=True, capture_output=True, text=True).stdout.strip())
    (site / "sv0cov").mkdir()
    (site / "sv0cov" / "__init__.py").write_text("raise SystemExit('shadowed sv0cov')\n")
    for hook in ("sitecustomize", "usercustomize"):
        (site / f"{hook}.py").write_text(f"open({str(mark) + '.' + hook!r}, 'w').write('ran')\n")
    (site / "evil.pth").write_text(f"import os; open({str(mark) + '.pth'!r}, 'w').write('ran')\n")
    return site


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--unsupported", type=Path, help="a CPython 3.12 interpreter")
    a = ap.parse_args()
    ensure_built()
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="covhostiso-") as td:
        t = Path(os.path.realpath(td))
        work, prof = t / "work", t / "profiles"
        work.mkdir()
        prof.mkdir()
        exe = work / "constructs"
        p = sv0("native-compile", "--coverage=instrument", "-o", str(exe), str(PLAN / "constructs.sv0"))
        if p.returncode:
            raise SystemExit(f"build failed: {p.stderr.strip()}")
        subprocess.run([str(exe)], env=transport(prof), capture_output=True, timeout=60)
        exe.unlink()
        for f in prof.iterdir():
            (work / f.name).write_bytes(f.read_bytes())

        clean = t / "clean-bin"
        clean.mkdir()
        (clean / NAME).symlink_to(os.path.realpath(sys.executable))
        empty = venv(t / "empty")
        poisoned = venv(t / "poisoned")
        mark = t / "marker"
        poison(poisoned, mark)
        evil = work / "sv0cov"  # a shadowing package in the working directory
        evil.mkdir()
        (evil / "__init__.py").write_text("raise SystemExit('shadowed sv0cov (cwd)')\n")
        bad_env = {"PYTHONPATH": str(work), "PYTHONSTARTUP": str(evil / "__init__.py"), "PYTHONHOME": str(work), "PYTHONSAFEPATH": "0",
                   "PYTHONUSERBASE": str(t), "PYTHONNOUSERSITE": "0"}
        want = platform.python_version()
        outputs = {}
        merge = ["merge", "--expect-run", RUN_ID, "--output", "-", "."]
        for label, bindir, extra in (("clean", clean, None), ("empty-site", empty, None), ("poisoned-site", poisoned, bad_env)):
            path = f"{bindir}:{SYSTEM_PATH}"
            v = launch(path, ["version", "--json"], work, extra)
            got = json.loads(v.stdout)["implementation"]["runtime"]["version"] if v.returncode == 0 else None
            if got != want:
                errors.append(f"{label}: the launcher selected Python {got}, not this cell's {want} ({v.stderr.decode(errors='replace')[-300:]})")
            r = launch(path, merge, work, extra)
            if r.returncode:
                errors.append(f"{label}: merge exited {r.returncode}: {r.stderr.decode(errors='replace')[-400:]}")
            outputs[label] = r.stdout
        if len(set(outputs.values())) != 1:
            errors.append(f"the evidence differs across clean, empty-site and poisoned-site runs: { {k: len(v) for k, v in outputs.items()} }")
        ran = sorted(p.name for p in t.iterdir() if p.name.startswith("marker"))
        if ran:
            errors.append(f"site hooks ran inside sv0cov: {ran}")

        unsupported = "not run (no --unsupported)"
        if a.unsupported:
            ver = subprocess.run([str(a.unsupported), "-c", "import sys; print(sys.version_info[:2])"], capture_output=True, text=True).stdout.strip()
            if ver != "(3, 12)":
                raise SystemExit(f"--unsupported must be CPython 3.12, got {ver}")
            for label, name in (("only python3.12 on PATH", "python3.12"), ("3.12 under the python3.13 name", "python3.13")):
                d = t / f"unsupported-{name}"
                d.mkdir()
                (d / name).symlink_to(os.path.realpath(a.unsupported))
                r = launch(f"{d}:{SYSTEM_PATH}", ["version"], work)
                if r.returncode != 7 or r.stdout or b"COV0016" not in r.stderr:
                    errors.append(f"unsupported Python ({label}): exit {r.returncode}, stdout {r.stdout[:80]!r}, stderr {r.stderr[-200:]!r}")
            unsupported = "3.12 refused with COV0016 (absent and misnamed)"
    if errors:
        print("coverage host isolation: FAIL")
        for e in errors:
            print(f"  {e}")
        return 1
    print(f"coverage host isolation: OK (Python {want} selected in clean, empty-site and poisoned-site runs; evidence identical; "
          f"no site hook ran; unsupported: {unsupported})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
