#!/usr/bin/env python3
"""End-to-end check of the --coverage plumbing (sv0cov CV-106, SPEC 13.3).

Through the real `sv0 native-compile` and `sv0 vm-native-compile` drivers:

1. `--coverage=off` is byte-identical to giving no flag: the emitted C (and
   the pinned golden) and the `.sv0b`, even with a stray
   SV0_COVERAGE_REQUEST in the environment.
2. `map` builds the artifact and writes the canonical map beside it (or at
   `--coverage-map`) on both drivers; the emitted C and `.sv0b` are
   byte-identical to an `off` build (map mode adds no hit operations), and
   the map names the artifact's stem as its target and `sv0c+<revision>` as
   the compiler identity. `instrument` places and checks its hits (CV-112)
   and is then refused until emission (CV-113/CV-117) lands: nonzero exit,
   the diagnostic, nothing left behind.
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
PENDING = "is not available yet: coverage hits are placed and checked"


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

        # 2. map writes the map and an unchanged artifact; instrument is refused.
        mc = t / "map.c"
        p = run(["native-compile", "--emit=c", "--coverage=map", "--coverage-map", str(t / "c.map.json"), "-o", str(mc), str(CASE)])
        if p.returncode or not mc.is_file() or len(outs) == 3 and mc.read_bytes() != outs["none"][0]:
            errors.append(f"native map --emit=c: rc={p.returncode}, C differs from off or missing: {p.stderr}")
        mexe = t / "mapped"
        p = run(["native-compile", "--coverage=map", "-o", str(mexe), str(CASE)])
        mjson = t / "mapped.sv0covmap.json"
        if p.returncode or not mexe.is_file() or not mjson.is_file():
            errors.append(f"native map: rc={p.returncode} exe={mexe.is_file()} map={mjson.is_file()}: {p.stderr}")
        else:
            m = json.loads(mjson.read_bytes())
            if m.get("schema") != "sv0cov.map" or m["target"] != {"kind": "executable", "name": "mapped"} \
                    or not m["compiler"]["identity"].startswith("sv0c+") or not m["points"]:
                errors.append(f"native map: unexpected map header {m.get('schema')} {m.get('target')} {m.get('compiler')}")
            if subprocess.run([str(mexe)], timeout=60).returncode != 42:
                errors.append("native map: the executable does not exit 42 like the off build")
        vb = t / "vmapped.sv0b"
        q = run(["vm-native-compile", "--coverage=map", "--coverage-map", str(t / "v.json"), str(CASE), str(vb)])
        if q.returncode or not (t / "v.json").is_file() or len(outs) == 3 and vb.read_bytes() != outs["none"][1]:
            errors.append(f"vm map: rc={q.returncode}, map missing or .sv0b differs from off: {q.stderr}")
        elif (t / "v.json").read_bytes() != mjson.read_bytes().replace(b'"name":"mapped"', b'"name":"vmapped"') \
                .replace(json.loads(mjson.read_bytes())["map_id"].encode(), json.loads((t / "v.json").read_bytes())["map_id"].encode()):
            errors.append("vm map: differs from the native driver's map beyond the target name")
        for mode in ("instrument",):
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
    print("verify_coverage_modes: OK (off byte-identical on native + VM; map writes the map with "
          f"unchanged C/.sv0b; instrument refused; {len(usage)} usage errors; build record states the mode)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
