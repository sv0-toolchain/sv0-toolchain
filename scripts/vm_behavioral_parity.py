#!/usr/bin/env python3
"""VMF-018: cross-backend behavioral parity for the f64 / i64 surface.

For each fixture (a `.sv0` file or a `--project <dir>`), run it through BOTH
native backends and compare:

  * C backend   : build/sv0-megatu-native  -> emitted C -> cc -> execute
  * VM backend  : build/sv0-megatu-vm-native -> .sv0b -> sv0vm

Integer / i64 / modular results must be bit-identical (COMPAT-001); this harness
compares the process exit code and stdout, which is how sv0-mathlib's own
self-test programs report (0 = pass, nonzero = first failing case). Float
fixtures whose check is *not* exit-code-based would need a ULP compare
(COMPAT-002); none exist yet -- the sv0-mathlib self-tests all reduce to an
exit code, and that already exercises the f64 arithmetic / comparison paths.

Both emitters read the source path (or `--project <dir>`) from SV0_DRV_REQUEST.
The manifest is `sv0c/test/vm-parity/behavioral-manifest.txt`: one entry per
line, either a path relative to the repo root or `--project <dir>` (dir also
repo-root-relative). Blank lines and `#` comments are ignored.
"""
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from native_exe_canonical_compile import compile_and_publish  # noqa: E402
from native_exe_errors import BuildError  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SV0C = os.path.join(ROOT, "sv0c")
SV0VM = os.path.join(ROOT, "sv0vm")
C_EMIT = os.path.join(ROOT, "build", "sv0-megatu-native")
VM_EMIT = os.path.join(ROOT, "build", "sv0-megatu-vm-native")
MANIFEST = os.path.join(SV0C, "test", "vm-parity", "behavioral-manifest.txt")


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def build_emitters():
    for name, script in (
        (C_EMIT, "build-sv0-megatu-native.sh"),
        (VM_EMIT, "build-sv0-megatu-vm-native.sh"),
    ):
        if not os.access(name, os.X_OK):
            r = sh(["bash", os.path.join(ROOT, "scripts", script)])
            if not os.access(name, os.X_OK):
                sys.exit(f"vm_behavioral_parity: failed to build {name}\n{r.stderr}")


def run_c(request, workdir):
    c_path = os.path.join(workdir, "out.c")
    with open(c_path, "w") as f:
        r = subprocess.run([C_EMIT], stdout=f, stderr=subprocess.PIPE,
                           text=True, env={**os.environ, "SV0_DRV_REQUEST": request})
    if r.returncode != 0 or os.path.getsize(c_path) == 0:
        return ("EMIT_FAIL", r.stderr.strip())
    bin_path = os.path.join(workdir, "out_c")
    try:
        compile_and_publish(c_path, bin_path)
    except BuildError as exc:
        return ("CC_FAIL", str(exc)[-300:])
    ex = sh([bin_path])
    return (ex.returncode, ex.stdout)


def run_vm(request, workdir):
    b_path = os.path.join(workdir, "out.sv0b")
    with open(b_path, "wb") as f:
        r = subprocess.run([VM_EMIT], stdout=f, stderr=subprocess.PIPE,
                           env={**os.environ, "SV0_DRV_REQUEST": request})
    if r.returncode != 0 or os.path.getsize(b_path) == 0:
        return ("EMIT_FAIL", r.stderr.decode(errors="replace").strip())
    run = subprocess.run(["sml"], stdin=open(os.path.join(SV0VM, "scripts", "run_sv0b.sml")),
                         capture_output=True, text=True, cwd=SV0VM,
                         env={**os.environ, "SV0B": b_path})
    out = run.stdout + run.stderr
    m = re.search(r"vm_exit:(-?\d+)", out)
    if not m:
        return ("NO_EXIT", out.strip()[-400:])
    return (int(m.group(1)) & 0xFF, "")


def resolve(entry):
    if entry.startswith("--project "):
        d = os.path.join(ROOT, entry[len("--project "):].strip())
        return f"--project {os.path.abspath(d)}", entry
    p = os.path.join(ROOT, entry)
    return os.path.abspath(p), entry


def main():
    entries = []
    if not os.path.exists(MANIFEST):
        sys.exit(f"vm_behavioral_parity: missing {MANIFEST}")
    for line in open(MANIFEST):
        line = line.split("#", 1)[0].strip()
        if line:
            entries.append(line)
    if not entries:
        print("vm_behavioral_parity: manifest empty; nothing to check")
        return 0
    build_emitters()
    fails = 0
    skipped = 0
    for entry in entries:
        request, label = resolve(entry)
        # An optional `--project <dir>` entry (e.g. the sibling sv0-mathlib
        # checkout) is skipped when the dir is absent -- present in
        # sv0-mathlib's own CI, absent in sv0-toolchain's.
        if request.startswith("--project "):
            d = request[len("--project "):]
            if not os.path.isdir(d):
                print(f"  SKIP  {label:50s} (dir absent: {d})")
                skipped += 1
                continue
        with tempfile.TemporaryDirectory() as wd:
            c = run_c(request, wd)
            v = run_vm(request, wd)
        # Compare exit codes (all current fixtures report pass/fail via exit
        # code). C stdout is checked to be empty -- a fixture that prints would
        # need the ULP/stdout compare path, not yet built.
        ok = (c[0] == v[0]) and isinstance(c[0], int) and not c[1].strip()
        if ok:
            print(f"  OK    {label:50s} exit={c[0]}")
        else:
            fails += 1
            print(f"  FAIL  {label}")
            print(f"        C : exit={c[0]!r}  {c[1][:200]!r}")
            print(f"        VM: exit={v[0]!r}  {v[1][:200]!r}")
    n = len(entries)
    tail = f" ({skipped} skipped)" if skipped else ""
    if fails:
        print(f"vm_behavioral_parity: {fails}/{n} FAILED{tail}")
        return 1
    print(f"vm_behavioral_parity: {n - skipped}/{n} cross-backend parity OK{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
