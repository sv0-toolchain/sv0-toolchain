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
   the compiler identity. `instrument --emit=c` writes the instrumented C
   (CV-113) and its map; `instrument` links the sv0cov runtime, and the
   executable publishes one raw profile under a valid SV0COV_* transport
   (CV-115) and runs unchanged without one; the VM driver writes bytecode
   with COVER_HIT instructions, the map (CV-117), and the <stem>.sv0covbind.json
   companion bound to the bytecode's length and SHA-256 (CV-118).
3. Unknown/case-variant modes, `--coverage-map` without a mode, and a map
   path that collides with the artifact are usage errors (exit 2) that never
   invoke the compiler.
4. The build record states the mode (`{"mode": "off", "map_path": null,
   "formats": null}`), and for `map`/`instrument` the coverage format
   versions the build wrote.
5. CV-208 (COV-INS-004): instrumented and uninstrumented artifacts never
   collide. Rebuilding the same output path in another mode leaves no stale
   companion: an off build removes the earlier map (native, `--emit=c`) and
   the map and binding (VM); a map build removes the earlier binding; a
   build with `--coverage-map` elsewhere removes the earlier default map;
   a file at that name that is not an sv0cov map is left alone. The rebuilt
   off artifacts equal a fresh off build and run without coverage. The
   format versions in the cache key and build record are the ones the
   artifacts carry (map, point identity, binding, VM profile, raw profile,
   generated-C protocol). A coverage build is not emit-cacheable, and the
   run cache never stores or replays instrumented C (their selftests run in
   `sv0 test-guards`).
"""

from __future__ import annotations

import hashlib
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
RUN_ID = "0123456789abcdef0123456789abcdef"

sys.path.insert(0, str(ROOT / "scripts"))
from native_exe_coverage import FORMAT_VERSIONS  # noqa: E402


def run(args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([SV0, *args], capture_output=True, text=True, env=env, cwd=ROOT, timeout=600)


def collisions(d: Path, errors: list[str]) -> None:
    d.mkdir()
    exe, exe_map = d / "prog", d / "prog.sv0covmap.json"
    cfile, c_map = d / "emit" / "prog.c", d / "emit" / "prog.sv0covmap.json"
    sv0b, vm_map, vm_bind = d / "vm" / "prog.sv0b", d / "vm" / "prog.sv0covmap.json", d / "vm" / "prog.sv0covbind.json"
    fresh = d / "fresh"
    for sub in (cfile.parent, sv0b.parent, fresh, d / "profiles", d / "elsewhere"):
        sub.mkdir()
    transport = {k: v for k, v in os.environ.items() if not k.startswith("SV0COV")}
    transport.update(SV0COV_PROFILE_DIR=str(d / "profiles"), SV0COV_RUN_ID=RUN_ID, SV0COV_REQUIRED="1")

    def ok(label: str, p: subprocess.CompletedProcess) -> bool:
        if p.returncode:
            errors.append(f"collision/{label}: rc={p.returncode} {p.stderr.strip()[-300:]}")
        return p.returncode == 0

    # Native executable: instrument, then off at the same -o.
    if ok("native instrument", run(["native-compile", "--coverage=instrument", "-o", str(exe), str(CASE)])):
        m = json.loads(exe_map.read_bytes())
        if (m["version"], m["point_identity_version"]) != (FORMAT_VERSIONS["map"], FORMAT_VERSIONS["point_identity"]):
            errors.append("collision: the map's versions differ from FORMAT_VERSIONS")
        r = subprocess.run([str(exe)], capture_output=True, env=transport)
        profiles = list((d / "profiles").iterdir())
        if len(profiles) != 1 or profiles[0].read_bytes()[8:12] != b"\x01\x00\x00\x00":
            errors.append(f"collision: the instrumented run did not publish one raw profile 1.0 (exit {r.returncode})")
        for f in profiles:
            f.unlink()
    if ok("native off after instrument", run(["native-compile", "-o", str(exe), str(CASE)])):
        if exe_map.exists():
            errors.append("collision: an off build left the earlier coverage map beside the executable")
        r = subprocess.run([str(exe)], capture_output=True, env=transport)
        if any((d / "profiles").iterdir()) or b"sv0cov" in r.stderr:
            errors.append("collision: the off executable still behaves as instrumented")
    # A build with --coverage-map elsewhere removes the earlier default map.
    if ok("native map", run(["native-compile", "--coverage=map", "-o", str(exe), str(CASE)])) and not exe_map.exists():
        errors.append("collision: map mode did not write the default map")
    other = d / "elsewhere" / "m.json"
    if ok("native map elsewhere", run(["native-compile", "--coverage=map", "--coverage-map", str(other), "-o", str(exe), str(CASE)])):
        if exe_map.exists() or not other.exists():
            errors.append("collision: the default map survived a build that wrote its map elsewhere")
    # A file at the default name that is not an sv0cov map is not touched.
    exe_map.write_text("my notes\n")
    if ok("native off beside a foreign file", run(["native-compile", "-o", str(exe), str(CASE)])):
        if not exe_map.exists() or exe_map.read_text() != "my notes\n":
            errors.append("collision: an off build removed a file that is not a coverage map")
    exe_map.unlink(missing_ok=True)

    # --emit=c: instrument, then off.
    if ok("emit-c instrument", run(["native-compile", "--emit=c", "--coverage=instrument", "-o", str(cfile), str(CASE)])):
        text = cfile.read_text()
        if f"generated-C protocol {FORMAT_VERSIONS['generated_c_protocol']} " not in text or \
                f"= {{\n  {FORMAT_VERSIONS['generated_c_protocol']}u, " not in text or not c_map.exists():
            errors.append("collision: the instrumented C does not carry protocol major FORMAT_VERSIONS states")
    if ok("emit-c off after instrument", run(["native-compile", "--emit=c", "-o", str(cfile), str(CASE)])):
        ok("emit-c fresh off", run(["native-compile", "--emit=c", "-o", str(fresh / "prog.c"), str(CASE)]))
        if c_map.exists() or "__sv0cov" in cfile.read_text() or cfile.read_bytes() != (fresh / "prog.c").read_bytes():
            errors.append("collision: off C after instrumented C is not a clean off build")

    # VM: instrument, then map, then off.
    if ok("vm instrument", run(["vm-native-compile", "--coverage=instrument", str(CASE), str(sv0b)])):
        b = json.loads(vm_bind.read_bytes())
        got = (b["version"], b["profile"], b["raw_profile_version"])
        if got != (FORMAT_VERSIONS["vm_binding"], FORMAT_VERSIONS["vm_profile"], FORMAT_VERSIONS["raw_profile"]):
            errors.append(f"collision: the binding's versions {got} differ from FORMAT_VERSIONS")
    instrumented = sv0b.read_bytes() if sv0b.exists() else b""
    if ok("vm map after instrument", run(["vm-native-compile", "--coverage=map", str(CASE), str(sv0b)])):
        if vm_bind.exists() or not vm_map.exists():
            errors.append("collision: a VM map build left the earlier binding (or wrote no map)")
    ok("vm instrument again", run(["vm-native-compile", "--coverage=instrument", str(CASE), str(sv0b)]))
    if ok("vm off after instrument", run(["vm-native-compile", str(CASE), str(sv0b)])):
        ok("vm fresh off", run(["vm-native-compile", str(CASE), str(fresh / "prog.sv0b")]))
        if vm_map.exists() or vm_bind.exists():
            errors.append("collision: a VM off build left the earlier map or binding")
        if sv0b.read_bytes() != (fresh / "prog.sv0b").read_bytes() or sv0b.read_bytes() == instrumented:
            errors.append("collision: the off bytecode after an instrumented build is not a clean off build")
        r = run(["vm-run", str(sv0b)], transport)
        out = r.stdout + r.stderr
        if "COV2" in out or "COV1" in out or "vm_exit:42" not in out or any((d / "profiles").iterdir()):
            errors.append(f"collision: the off bytecode does not run as an uninstrumented program: {out[-200:]}")

    # The emit cache declines coverage builds.
    env = dict(os.environ, SV0_COVERAGE_REQUEST="map\n/m.json", SV0_RUN_CACHE_ENVKEY="k")
    k = subprocess.run([sys.executable, str(ROOT / "scripts" / "emit_cache_key.py"), "key", "--root", str(ROOT), str(CASE)],
                       capture_output=True, text=True, env=env)
    if k.returncode != 3 or k.stdout.strip():
        errors.append(f"collision: a coverage build got an emit cache key (rc={k.returncode})")


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
        ic = t / "instrument.c"
        p = run(["native-compile", "--emit=c", "--coverage=instrument", "-o", str(ic), str(CASE)])
        ijson = t / "instrument.sv0covmap.json"
        if p.returncode or not ic.is_file() or not ijson.is_file() \
                or "__sv0cov_start(__sv0cov_modules, 1u);" not in ic.read_text() \
                or json.loads(ijson.read_bytes())["map_id"] not in ic.read_text():
            errors.append(f"native instrument --emit=c: rc={p.returncode} C/map missing or unregistered: {p.stderr}")
        exe = t / "instrument-exe"
        p = run(["native-compile", "--coverage=instrument", "-o", str(exe), str(CASE)])
        emap = t / "instrument-exe.sv0covmap.json"
        if p.returncode or not exe.is_file() or not emap.is_file():
            errors.append(f"native instrument: rc={p.returncode} exe={exe.is_file()} map={emap.is_file()}: {p.stderr}")
        else:
            prof = t / "profiles"
            prof.mkdir()
            base = {k: v for k, v in os.environ.items() if not k.startswith("SV0COV")}
            r = subprocess.run([str(exe)], capture_output=True, timeout=60, env=dict(
                base, SV0COV_PROFILE_DIR=str(prof), SV0COV_RUN_ID=RUN_ID, SV0COV_REQUIRED="1"))
            got = [x.name for x in prof.iterdir()]
            if r.returncode != 42 or r.stderr or len(got) != 1 or not got[0].startswith(RUN_ID + "-") \
                    or not got[0].endswith(".sv0profraw"):
                errors.append(f"native instrument run: rc={r.returncode} profiles={got} stderr={r.stderr!r}")
            # Outside sv0cov (no transport, not required): the program runs as
            # usual, says why nothing was collected, and publishes nothing.
            r = subprocess.run([str(exe)], capture_output=True, timeout=60, env=base)
            if r.returncode != 42 or b"error[COV2001]" not in r.stderr or len(list(prof.iterdir())) != 1:
                errors.append(f"native instrument run without transport: rc={r.returncode} stderr={r.stderr!r}")
        bc = t / "instrument-vm.sv0b"
        vmap = t / "instrument-vm.json"
        q = run(["vm-native-compile", "--coverage=instrument", "--coverage-map", str(vmap), str(CASE), str(bc)])
        if q.returncode or not bc.is_file() or bytes([119]) not in bc.read_bytes() or not vmap.is_file() \
                or len(outs) == 3 and bc.read_bytes() == outs["none"][1]:
            errors.append(f"vm instrument: rc={q.returncode} no COVER_HIT bytecode or map: {q.stderr}")
        else:
            # CV-118: the companion binding sits beside the .sv0b and binds
            # its exact bytes to the map.
            vbind = t / "instrument-vm.sv0covbind.json"
            try:
                b = json.loads(vbind.read_bytes())
                code = bc.read_bytes()
                ok = (b["bytecode_length"] == len(code)
                      and b["bytecode_sha256"] == hashlib.sha256(code).hexdigest()
                      and b["map_id"] == json.loads(vmap.read_bytes())["map_id"]
                      and b["profile"] == "sv0vm-v1-coverage")
            except (OSError, ValueError, KeyError):
                ok = False
            if not ok:
                errors.append("vm instrument: the .sv0covbind.json companion is missing or does not bind the bytecode")

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
            if p.returncode != 2 or needle not in p.stderr or "coverage hits" in p.stderr:
                errors.append(f"{' '.join(args[:3])}: rc={p.returncode} stderr={p.stderr!r}")

        # 4. build metadata records the mode.
        rec = t / "r.json"
        p = run(["native-compile", "--build-record=" + str(rec), "-o", str(t / "rec-exe"), str(CASE)])
        if p.returncode:
            errors.append(f"build record build failed: {p.stderr}")
        elif json.loads(rec.read_text()).get("coverage") != {"mode": "off", "map_path": None, "formats": None}:
            errors.append(f"build record coverage field: {json.loads(rec.read_text()).get('coverage')!r}")
        for mode in ("map", "instrument"):
            rec = t / f"r-{mode}.json"
            exe = t / f"rec-{mode}"
            p = run(["native-compile", f"--coverage={mode}", "--build-record=" + str(rec), "-o", str(exe), str(CASE)])
            got = json.loads(rec.read_text()).get("coverage") if p.returncode == 0 else None
            want = {"mode": mode, "map_path": str(exe) + ".sv0covmap.json", "formats": FORMAT_VERSIONS}
            if got != want:
                errors.append(f"{mode} build record coverage field: {got!r} (want {want!r}) {p.stderr}")

        # 5. CV-208: no collisions between modes at one output path.
        collisions(t / "collide", errors)

    if errors:
        print("verify_coverage_modes: FAIL", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("verify_coverage_modes: OK (off byte-identical on native + VM; map writes the map with "
          f"unchanged C/.sv0b; instrument --emit=c registers + writes the map, native instrument publishes a profile, VM instrument emits COVER_HIT + its binding; {len(usage)} usage errors; build record states the mode and format versions; "
          "CV-208: rebuilding one output path in another mode leaves no stale map or binding on native, --emit=c and VM, "
          "format versions match the artifacts, coverage builds are not emit-cacheable)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
