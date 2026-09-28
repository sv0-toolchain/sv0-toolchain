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
  (target = the artifact's stem, identity = ``sv0c+<sv0c revision>``).
  ``off`` sets nothing, so an off build invokes the compiler exactly as
  before (byte-identical output).

The compiler plans coverage for a non-off request. ``map`` writes the
canonical ``.sv0covmap.json`` (CV-110) and builds the uninstrumented
artifact; ``instrument`` places and checks the hits (CV-112) and emits
instrumented C with its map (CV-113). Linking an instrumented executable is
refused until the native coverage runtime (CV-114) lands, and the VM
refuses ``instrument`` until COVER_HIT emission (CV-117), rather than
building an unmarked, uninstrumented artifact.

    python3 scripts/native_exe_coverage.py --selftest
    python3 scripts/native_exe_coverage.py resolve --mode M [--map P] --artifact A
        (prints the SV0_COVERAGE_REQUEST value, empty for off; exit 2 on a
        usage error -- used by `sv0 vm-native-compile`)
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

ENV_VAR = "SV0_COVERAGE_REQUEST"
MODES = ("off", "map", "instrument")
MAP_SUFFIX = ".sv0covmap.json"
_ARTIFACT_SUFFIXES = (".sv0b", ".c")


class CoverageUsageError(Exception):
    """An invalid mode/map combination (usage error, exit class 2)."""


@dataclass(frozen=True)
class CoverageRequest:
    mode: str  # "off" | "map" | "instrument"
    map_path: str | None  # absolute; None exactly when mode is "off"
    target: str = ""  # the map's target name: the artifact's stem
    identity: str = ""  # the map's compiler identity: sv0c+<sv0c revision>


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
    return CoverageRequest(mode, resolved, target_name(artifact), compiler_identity())


def request_value(req: CoverageRequest) -> str | None:
    """The SV0_COVERAGE_REQUEST value, or None for off (variable unset)."""
    if req.mode == "off":
        return None
    return f"{req.mode}\n{req.map_path}\n{req.target}\n{req.identity}"


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


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if len(sys.argv) > 1 and sys.argv[1] == "resolve":
        raise SystemExit(_resolve_cli(sys.argv[2:]))
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
