#!/usr/bin/env python3
"""Coverage-mode plumbing shared by the native and VM drivers (sv0cov CV-106).

sv0cov SPEC 13.3: the compiler interface takes `--coverage=off|map|instrument`
and `--coverage-map <path>`; the mode is explicit in build metadata and cache
keys. This module holds the rules both drivers apply:

- ``default_map_path``: with no ``--coverage-map``, the map sits beside the
  artifact: its ``.sv0b``/``.c`` suffix (if any) is replaced by
  ``.sv0covmap.json`` (``dist/hello`` -> ``dist/hello.sv0covmap.json``,
  ``out/prog.sv0b`` -> ``out/prog.sv0covmap.json``).
- ``resolve``: validates the mode and map path and returns the request.
- ``request_value``/``child_env``: the core compiler receives a non-off mode
  in its own environment variable, ``SV0_COVERAGE_REQUEST``, as
  ``<mode>\\n<absolute map path>\\n<target name>\\n<compiler identity>``
  (target = the artifact's stem, identity = ``sv0c+<sv0c revision>``), plus
  ``\\n<binding path>`` for a VM ``instrument`` build: the companion
  ``<stem>.sv0covbind.json`` beside the ``.sv0b`` (CV-118).
  ``off`` sets nothing, so an off build invokes the compiler exactly as
  before (byte-identical output).

The compiler plans coverage for a non-off request. ``map`` writes the
canonical ``.sv0covmap.json`` (CV-110) and builds the uninstrumented
artifact; ``instrument`` places and checks the hits (CV-112) and emits
instrumented C with its map (CV-113); the native driver links it with the
sv0cov runtime (``sv0cov/runtime/c/sv0cov_rt.c``, CV-114/CV-115), which
publishes one raw profile per run into ``SV0COV_PROFILE_DIR``. On the VM,
``instrument`` writes bytecode with COVER_HIT instructions (CV-117) and its
companion ``<stem>.sv0covbind.json`` (CV-118); a VM runs it only with that
binding (sv0vm support: CV-119, CV-120). Neither backend ever
builds an unmarked, uninstrumented artifact for ``instrument``.

- ``FORMAT_VERSIONS``/``cache_key_part`` (CV-208, COV-INS-004): the
  coverage mode and the versions of every coverage format a build writes
  take part in cache keys, so instrumented, map-mode, and uninstrumented
  artifacts can never share a cache entry, nor can builds made for
  different format versions. Off contributes nothing (existing keys keep
  their value).
- ``stale_outputs``/``remove_stale_outputs`` (CV-208): a build removes the
  coverage companions an earlier build left beside the same artifact when
  this build does not write them: the default map and VM binding after an
  off build, the binding after a map build, the default map when
  ``--coverage-map`` names another file. Otherwise an uninstrumented
  artifact would sit next to a map that describes a different build. Only
  files that really are sv0cov maps or bindings are removed.

- ``coverage_runtime_source``/``compile_coverage_runtime``: locate the
  runtime in the toolchain checkout and compile it (C11) to an object in the
  build's scratch directory.

    python3 scripts/native_exe_coverage.py --selftest
    python3 scripts/native_exe_coverage.py resolve --mode M [--map P] --artifact A
        (prints the SV0_COVERAGE_REQUEST value, empty for off; exit 2 on a
        usage error -- used by `sv0 vm-native-compile`)
    python3 scripts/native_exe_coverage.py clean-stale --mode M [--map P] --artifact A
        (removes stale companions after a successful build; prints each
        removed path)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

ENV_VAR = "SV0_COVERAGE_REQUEST"
MODES = ("off", "map", "instrument")
MAP_SUFFIX = ".sv0covmap.json"
BINDING_SUFFIX = ".sv0covbind.json"
_ARTIFACT_SUFFIXES = (".sv0b", ".c")
# Every coverage format a non-off build writes or binds to (sv0cov SPEC
# 16.3, 16.4, 14.1, 15; sv0doc bytecode/coverage.md). A change to any of
# them changes what a build produces, so they are part of cache keys and of
# the build record.
FORMAT_VERSIONS = {
    "generated_c_protocol": "1",
    "map": "1.0",
    "point_identity": "1.0",
    "raw_profile": "1.0",
    "vm_binding": "1.0",
    "vm_profile": "sv0vm-v1-coverage",
}
_STALE_MARKERS = {MAP_SUFFIX: b'"schema":"sv0cov.map"', BINDING_SUFFIX: b'"schema":"sv0cov.vm-binding"'}


class CoverageUsageError(Exception):
    """An invalid mode/map combination (usage error, exit class 2)."""


@dataclass(frozen=True)
class CoverageRequest:
    mode: str  # "off" | "map" | "instrument"
    map_path: str | None  # absolute; None exactly when mode is "off"
    target: str = ""  # the map's target name: the artifact's stem
    identity: str = ""  # the map's compiler identity: sv0c+<sv0c revision>
    binding_path: str | None = None  # VM instrument only: the .sv0covbind.json companion


def target_name(artifact_path: str) -> str:
    """The artifact's file name without a .sv0b/.c suffix."""
    name = os.path.basename(artifact_path)
    for suffix in _ARTIFACT_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def compiler_identity(toolchain_root: str | None = None) -> str:
    """sv0c+<git revision of sv0c>, or sv0c+unknown outside a checkout."""
    import subprocess

    root = toolchain_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        rev = subprocess.run(["git", "-C", os.path.join(root, "sv0c"), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        rev = ""
    return f"sv0c+{rev or 'unknown'}"


def default_map_path(artifact_path: str) -> str:
    base = artifact_path
    for suffix in _ARTIFACT_SUFFIXES:
        if base.endswith(suffix) and len(base) > len(suffix):
            base = base[: -len(suffix)]
            break
    return base + MAP_SUFFIX


def resolve(mode: str, map_path: str | None, artifact_path: str, cwd: str,
            other_outputs: tuple[str, ...] = ()) -> CoverageRequest:
    """Validate and resolve one build's coverage request.

    `artifact_path` is the final artifact (executable, emitted C, or
    `.sv0b`); `other_outputs` are further files the build writes (retained
    C, build record) that the map must not overwrite either.
    """
    if mode not in MODES:
        raise CoverageUsageError(f"--coverage={mode} is invalid (want 'off', 'map' or 'instrument')")
    if mode == "off":
        if map_path is not None:
            raise CoverageUsageError("--coverage-map requires --coverage=map or --coverage=instrument")
        return CoverageRequest("off", None)
    if map_path is not None and map_path in ("", "-"):
        raise CoverageUsageError("--coverage-map requires a non-empty file path")

    def absolute(p: str) -> str:
        return os.path.normpath(p if os.path.isabs(p) else os.path.join(cwd, p))

    artifact = absolute(artifact_path)
    resolved = absolute(map_path) if map_path is not None else default_map_path(artifact)
    if "\n" in resolved or "\r" in resolved:
        raise CoverageUsageError("--coverage-map path must not contain a line break")
    for other in (artifact, *(absolute(o) for o in other_outputs)):
        if os.path.realpath(resolved) == os.path.realpath(other):
            raise CoverageUsageError(f"--coverage-map {resolved} is also a build output; choose a different path")
    if os.path.isdir(resolved):
        raise CoverageUsageError(f"--coverage-map {resolved} is a directory")
    binding = None
    if mode == "instrument" and artifact.endswith(".sv0b") and len(artifact) > len(".sv0b"):
        # sv0cov CV-118 (sv0doc bytecode/coverage.md 4): VM instrument bytecode
        # needs its companion binding, <stem>.sv0covbind.json beside it.
        binding = artifact[: -len(".sv0b")] + BINDING_SUFFIX
        for other in (artifact, resolved, *(absolute(o) for o in other_outputs)):
            if os.path.realpath(binding) == os.path.realpath(other):
                raise CoverageUsageError(f"the coverage binding {binding} would overwrite another build output; "
                                         "choose a different --coverage-map or output path")
        if os.path.isdir(binding):
            raise CoverageUsageError(f"the coverage binding path {binding} is a directory")
    return CoverageRequest(mode, resolved, target_name(artifact), compiler_identity(), binding)


def formats_key() -> str:
    """The format versions as one canonical string (sorted `name=version`)."""
    return ";".join(f"{k}={FORMAT_VERSIONS[k]}" for k in sorted(FORMAT_VERSIONS))


def cache_key_part(request: str | None) -> bytes:
    """What a coverage request adds to a build cache key (COV-INS-004).

    `request` is the SV0_COVERAGE_REQUEST value (None or empty for off).
    Off adds nothing; any other request adds its mode, the rest of the
    request (map path, target, identity: they shape the artifact and its
    map), and the format versions.
    """
    if not request:
        return b""
    return b"coverage\0" + request.encode("utf-8", "surrogateescape") + b"\0" + formats_key().encode() + b"\n"


def stale_outputs(req: CoverageRequest, artifact_path: str, cwd: str) -> list[str]:
    """Coverage companions beside `artifact_path` that this build does not write."""
    artifact = os.path.normpath(artifact_path if os.path.isabs(artifact_path) else os.path.join(cwd, artifact_path))
    default_map = default_map_path(artifact)
    out = []
    if req.map_path is None or os.path.realpath(req.map_path) != os.path.realpath(default_map):
        out.append(default_map)
    if artifact.endswith(".sv0b") and len(artifact) > len(".sv0b") and req.binding_path is None:
        out.append(artifact[: -len(".sv0b")] + BINDING_SUFFIX)
    return out


def remove_stale_outputs(req: CoverageRequest, artifact_path: str, cwd: str) -> list[str]:
    """Remove `stale_outputs` that are regular sv0cov map/binding files;
    return the removed paths. Anything else at those names is left alone."""
    removed = []
    for path in stale_outputs(req, artifact_path, cwd):
        marker = next(m for suffix, m in _STALE_MARKERS.items() if path.endswith(suffix))
        try:
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            with open(path, "rb") as f:
                if marker not in f.read():
                    continue
            os.unlink(path)
        except OSError:
            continue
        removed.append(path)
    return removed


RUNTIME_RELPATH = os.path.join("sv0cov", "runtime", "c", "sv0cov_rt.c")


def coverage_runtime_source(toolchain_root: str | None = None) -> str:
    """The sv0cov native runtime source, or BuildError(RUNTIME) if absent."""
    from native_exe_errors import BuildError, DiagnosticPhase

    root = toolchain_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, RUNTIME_RELPATH)
    if not os.path.isfile(path):
        raise BuildError(DiagnosticPhase.RUNTIME,
                         f"--coverage=instrument needs the sv0cov native runtime, but {path} is missing "
                         "(is the sv0cov submodule checked out?)")
    return path


def compile_coverage_runtime(cc_path: str, source: str, scratch_dir: str, env: dict[str, str]) -> str:
    """Compile the runtime to <scratch>/sv0cov_rt.o and return that path."""
    from native_exe_errors import BuildError, DiagnosticPhase
    from native_exe_subprocess import SubprocessError, run_argv

    obj = os.path.join(scratch_dir, "sv0cov_rt.o")
    argv = [cc_path, "-std=c11", "-O2", "-c", source, "-o", obj]
    try:
        result = run_argv(argv, env=dict(env))
    except SubprocessError as exc:
        raise BuildError(DiagnosticPhase.HOST_COMPILE, f"failed to compile the coverage runtime: {exc}") from exc
    if result.returncode != 0 or not os.path.isfile(obj):
        raise BuildError(DiagnosticPhase.HOST_COMPILE,
                         f"compiling the coverage runtime failed: {result.stderr or result.returncode}")
    return obj


def request_value(req: CoverageRequest) -> str | None:
    """The SV0_COVERAGE_REQUEST value, or None for off (variable unset)."""
    if req.mode == "off":
        return None
    value = f"{req.mode}\n{req.map_path}\n{req.target}\n{req.identity}"
    if req.binding_path is not None:
        value += f"\n{req.binding_path}"
    return value


def child_env(base: dict[str, str], req: CoverageRequest) -> dict[str, str]:
    """A copy of `base` carrying `req`; a stray inherited value is dropped for off."""
    env = dict(base)
    env.pop(ENV_VAR, None)
    value = request_value(req)
    if value is not None:
        env[ENV_VAR] = value
    return env


def _selftest() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        if not cond:
            failures.append(name)

    check("default exe", default_map_path("/o/dist/hello") == "/o/dist/hello.sv0covmap.json")
    check("default sv0b", default_map_path("/o/prog.sv0b") == "/o/prog.sv0covmap.json")
    check("default c", default_map_path("/o/prog.c") == "/o/prog.sv0covmap.json")
    check("default bare suffix kept", default_map_path(".sv0b") == ".sv0b.sv0covmap.json")
    check("default only one suffix", default_map_path("/o/a.c.sv0b") == "/o/a.c.sv0covmap.json")

    off = resolve("off", None, "dist/hello", "/w")
    check("off request", off == CoverageRequest("off", None) and request_value(off) is None)
    m = resolve("map", None, "dist/hello", "/w")
    check("map default path", m.map_path == "/w/dist/hello.sv0covmap.json")
    ident = compiler_identity()
    check("identity", ident.startswith("sv0c+") and len(ident) > 5)
    check("map request value", request_value(m) == f"map\n/w/dist/hello.sv0covmap.json\nhello\n{ident}")
    check("target of sv0b", target_name("/o/prog.sv0b") == "prog" and target_name("/o/a.c") == "a")
    i = resolve("instrument", "cov/m.json", "dist/hello", "/w")
    check("instrument explicit map", i.map_path == "/w/cov/m.json")

    env = child_env({"PATH": "/bin", ENV_VAR: "instrument\n/stale"}, off)
    check("off drops inherited value", ENV_VAR not in env and env["PATH"] == "/bin")
    check("instrument sets value", child_env({}, i)[ENV_VAR] == f"instrument\n/w/cov/m.json\nhello\n{ident}")

    def rejects(name: str, needle: str, *args, **kw) -> None:
        try:
            resolve(*args, **kw)
            failures.append(f"{name}: accepted")
        except CoverageUsageError as exc:
            if needle not in str(exc):
                failures.append(f"{name}: message {exc}")

    rejects("unknown mode", "want 'off'", "branch", None, "a", "/w")
    rejects("map with off", "requires --coverage=map", "off", "m.json", "a", "/w")
    rejects("empty map", "non-empty", "map", "", "a", "/w")
    rejects("stdout map", "non-empty", "map", "-", "a", "/w")
    rejects("map is the artifact", "also a build output", "map", "dist/hello", "dist/hello", "/w")
    rejects("map is the kept C", "also a build output", "map", "k.c", "a", "/w", other_outputs=("k.c",))
    rejects("line break", "line break", "map", "a\nb", "a", "/w")
    rejects("directory", "is a directory", "map", "/", "a", "/w")

    vi = resolve("instrument", None, "out/prog.sv0b", "/w")
    check("vm binding path", vi.binding_path == "/w/out/prog.sv0covbind.json"
          and request_value(vi) == f"instrument\n/w/out/prog.sv0covmap.json\nprog\n{ident}\n/w/out/prog.sv0covbind.json")
    check("no binding for map mode", resolve("map", None, "out/prog.sv0b", "/w").binding_path is None)
    check("no binding for native", resolve("instrument", None, "dist/hello", "/w").binding_path is None)
    rejects("map is the binding", "would overwrite", "instrument", "out/prog.sv0covbind.json", "out/prog.sv0b", "/w")

    # CV-208: cache-key participation.
    check("off adds nothing to a key", cache_key_part(None) == b"" and cache_key_part("") == b"")
    km, ki = cache_key_part(request_value(m)), cache_key_part(request_value(i))
    check("mode is in the key", km != ki and km.startswith(b"coverage\0map\n") and ki.startswith(b"coverage\0instrument\n"))
    check("format versions are in the key", formats_key().encode() in km
          and formats_key() == "generated_c_protocol=1;map=1.0;point_identity=1.0;raw_profile=1.0;"
                               "vm_binding=1.0;vm_profile=sv0vm-v1-coverage")
    saved = FORMAT_VERSIONS["map"]
    FORMAT_VERSIONS["map"] = "1.1"
    check("a format version change changes the key", cache_key_part(request_value(m)) != km)
    FORMAT_VERSIONS["map"] = saved

    # CV-208: stale companions.
    check("off: map and binding are stale", stale_outputs(off, "out/prog.sv0b", "/w")
          == ["/w/out/prog.sv0covmap.json", "/w/out/prog.sv0covbind.json"])
    check("off native: only the map", stale_outputs(off, "dist/hello", "/w") == ["/w/dist/hello.sv0covmap.json"])
    check("map mode: the binding is stale", stale_outputs(resolve("map", None, "out/prog.sv0b", "/w"), "out/prog.sv0b", "/w")
          == ["/w/out/prog.sv0covbind.json"])
    check("vm instrument: nothing stale", stale_outputs(vi, "out/prog.sv0b", "/w") == [])
    check("explicit map: the default map is stale", stale_outputs(i, "dist/hello", "/w") == ["/w/dist/hello.sv0covmap.json"])
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        def put(name: str, data: bytes) -> str:
            path = os.path.join(td, name)
            with open(path, "wb") as f:
                f.write(data)
            return path
        art = put("prog.sv0b", b"bytecode")
        smap = put("prog.sv0covmap.json", b'{"schema":"sv0cov.map","version":"1.0"}\n')
        sbind = put("prog.sv0covbind.json", b'{"schema":"sv0cov.vm-binding"}\n')
        check("removes a stale map and binding", sorted(remove_stale_outputs(off, art, td)) == sorted([smap, sbind])
              and not os.path.exists(smap) and not os.path.exists(sbind) and os.path.exists(art))
        check("nothing to remove is fine", remove_stale_outputs(off, art, td) == [])
        other = put("prog.sv0covmap.json", b"my notes, not a map\n")
        check("a file that is not a map is kept", remove_stale_outputs(off, art, td) == [] and os.path.exists(other))
        os.unlink(other)
        target = put("elsewhere.json", b'{"schema":"sv0cov.map"}\n')
        os.symlink(target, os.path.join(td, "prog.sv0covmap.json"))
        check("a symlink is kept", remove_stale_outputs(off, art, td) == [] and os.path.exists(target))
        os.unlink(os.path.join(td, "prog.sv0covmap.json"))
        kept = put("prog.sv0covmap.json", b'{"schema":"sv0cov.map"}\n')
        inst = resolve("instrument", None, art, td)
        check("an instrument build keeps its own outputs", remove_stale_outputs(inst, art, td) == [] and os.path.exists(kept))

    check("runtime source", coverage_runtime_source().endswith(RUNTIME_RELPATH))
    try:
        coverage_runtime_source("/nonexistent-toolchain")
        failures.append("missing runtime: accepted")
    except Exception as exc:  # BuildError(RUNTIME)
        if "sv0cov native runtime" not in str(exc) and "sv0cov native runtime" not in getattr(exc, "message", ""):
            failures.append(f"missing runtime: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_coverage selftest FAIL: {f}", file=sys.stderr)
        return 1
    print("native_exe_coverage: selftest OK")
    return 0


def _resolve_cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="native_exe_coverage.py resolve")
    ap.add_argument("--mode", required=True)
    ap.add_argument("--map")
    ap.add_argument("--artifact", required=True)
    args = ap.parse_args(argv)
    try:
        req = resolve(args.mode, args.map, args.artifact, os.getcwd())
    except CoverageUsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    sys.stdout.write(request_value(req) or "")
    return 0


def _clean_stale_cli(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="native_exe_coverage.py clean-stale")
    ap.add_argument("--mode", required=True)
    ap.add_argument("--map")
    ap.add_argument("--artifact", required=True)
    args = ap.parse_args(argv)
    try:
        req = resolve(args.mode, args.map, args.artifact, os.getcwd())
    except CoverageUsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for path in remove_stale_outputs(req, args.artifact, os.getcwd()):
        print(path)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        raise SystemExit(_resolve_cli(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "clean-stale":
        raise SystemExit(_clean_stale_cli(sys.argv[2:]))
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
