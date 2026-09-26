#!/usr/bin/env python3
"""End-to-end check of the --coverage plumbing (sv0cov CV-106, SPEC 13.3).

Through the real `sv0 native-compile` and `sv0 vm-native-compile` drivers:

1. `--coverage=off` is byte-identical to giving no flag: the emitted C (and
   the pinned golden) and the `.sv0b`, even with a stray
   SV0_COVERAGE_REQUEST in the environment.
2. `map` and `instrument` reach the compiler, which plans coverage and then
   refuses them until map emission (CV-110) and hit placement (CV-112)
   land: nonzero exit, the diagnostic, and no artifact or map file left
   behind.
3. Unknown/case-variant modes, `--coverage-map` without a mode, and a map
   path that collides with the artifact are usage errors (exit 2) that never
   invoke the compiler.
4. The build record states the mode (`{"mode": "off", "map_path": null}`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SV0 = str(ROOT / "scripts" / "sv0")
CASE = ROOT / "sv0c" / "test" / "behavior" / "cases" / "struct_field.sv0"
GOLDEN_C = ROOT / "sv0c" / "test" / "behavior" / "golden-c" / "struct_field.c"
PENDING = "is not available yet: coverage map emission"


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([SV0, *args], capture_output=True, text=True, env=env, cwd=ROOT, timeout=600)


def main() -> int:
    errors: list[str] = []
    stray = dict(os.environ, SV0_COVERAGE_REQUEST="instrument\n/nonexistent/stray.json")
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)

        # 1. off is byte-identical (native emitted C, VM bytecode).
        outs = {}
        for name, flags, env in (("none", [], None), ("off", ["--coverage=off"], None), ("stray", [], stray)):
            c = t / f"{name}.c"
            p = run(["native-compile", "--emit=c", *flags, "-o", str(c), str(CASE)], env)
            b = t / f"{name}.sv0b"
            q = run(["vm-native-compile", *flags, str(CASE), str(b)], env)
            if p.returncode or q.returncode:
                errors.append(f"off/{name}: native rc={p.returncode} vm rc={q.returncode}: {p.stderr}{q.stderr}")
                continue
            outs[name] = (c.read_bytes(), b.read_bytes())
        if len(outs) == 3:
            if not (outs["none"] == outs["off"] == outs["stray"]):
                errors.append("--coverage=off (or a stray SV0_COVERAGE_REQUEST) changed the emitted C or .sv0b")
            if outs["none"][0] != GOLDEN_C.read_bytes():
                errors.append(f"emitted C differs from {GOLDEN_C.relative_to(ROOT)}")

        # 2. map / instrument are refused by the compiler, leaving nothing behind.
        for mode in ("map", "instrument"):
            exe = t / f"{mode}-exe"
            p = run(["native-compile", f"--coverage={mode}", "-o", str(exe), str(CASE)])
            if p.returncode == 0 or PENDING not in p.stderr or f"--coverage={mode}" not in p.stderr:
                errors.append(f"native {mode}: rc={p.returncode} stderr={p.stderr!r}")
            left = [x.name for x in t.iterdir() if x.name.startswith(f"{mode}-exe")]
            if left:
                errors.append(f"native {mode}: left {left}")
            bc = t / f"{mode}.sv0b"
            q = run(["vm-native-compile", f"--coverage={mode}", "--coverage-map", str(t / f"{mode}.json"), str(CASE), str(bc)])
            if q.returncode != 9 or PENDING not in q.stderr:
                errors.append(f"vm {mode}: rc={q.returncode} stderr={q.stderr!r}")
            left = [x.name for x in t.iterdir() if x.name.startswith(f"{mode}.")]
            if left:
                errors.append(f"vm {mode}: left {left}")

        # 3. usage errors never reach the compiler.
        usage = [
            (["native-compile", "--coverage=branch", str(CASE)], "want 'off', 'map' or 'instrument'"),
            (["native-compile", "--coverage=Map", str(CASE)], "want 'off', 'map' or 'instrument'"),
            (["native-compile", "--coverage-map", "m.json", str(CASE)], "requires --coverage=map"),
            (["native-compile", "--coverage=map", "--coverage-map", str(t / "x"), "-o", str(t / "x"), str(CASE)],
             "also a build output"),
            (["vm-native-compile", "--coverage=branch", str(CASE), str(t / "u.sv0b")], "want 'off', 'map' or 'instrument'"),
            (["vm-native-compile", "--coverage-map", "m.json", str(CASE), str(t / "u.sv0b")], "requires --coverage=map"),
            (["vm-native-compile", "--coverage=map", "--coverage=off", str(CASE), str(t / "u.sv0b")], "repeated option"),
        ]
        for args, needle in usage:
            p = run(args)
            if p.returncode != 2 or needle not in p.stderr or PENDING in p.stderr:
                errors.append(f"{' '.join(args[:3])}: rc={p.returncode} stderr={p.stderr!r}")

        # 4. build metadata records the mode.
        rec = t / "r.json"
        p = run(["native-compile", "--build-record=" + str(rec), "-o", str(t / "rec-exe"), str(CASE)])
        if p.returncode:
            errors.append(f"build record build failed: {p.stderr}")
        elif json.loads(rec.read_text()).get("coverage") != {"mode": "off", "map_path": None}:
            errors.append(f"build record coverage field: {json.loads(rec.read_text()).get('coverage')!r}")

    if errors:
        print("verify_coverage_modes: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_coverage_modes: OK (off byte-identical on native + VM; map/instrument refused "
          f"pending map emission; {len(usage)} usage errors; build record states the mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
