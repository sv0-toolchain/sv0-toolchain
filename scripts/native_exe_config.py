"""`sv0.toml` `[build]` schema, discovery, and precedence (NEX-043).

Implements Section 17
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §17.2/§17.3/
§11.4): R0.1's `sv0.toml` extends the `[build]` table with exactly six
recognized keys (`contract-mode`, `profile`, `c-compiler`, `output-dir`,
`keep-c`, `build-record`). §17.2 requires a real TOML parser (or a bounded
one with a published schema) that "SHALL NOT silently ignore a malformed
recognized key" -- so `load_config` rejects both an unrecognized key and a
recognized key with the wrong type, rather than coercing or dropping it.

`discover_config` implements R0.1's simple discovery rule (§17.3): search
beside the file or project root only -- no parent-workspace walk, which the
spec itself defers to a "separately accepted" model.

`resolve_precedence` encodes §11.4's four-tier rule (CLI > config > env >
default) as one small generic helper, so every R0.1 setting that has a
config/env/default form uses identical precedence logic rather than each
call site re-deriving its own tie-breaking order.

Run `python3 scripts/native_exe_config.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import tomllib

_KNOWN_KEYS = {
    "contract-mode": str,
    "profile": str,
    "c-compiler": str,
    "output-dir": str,
    "keep-c": bool,
    "build-record": bool,
}


class ConfigError(Exception):
    """Raised for a malformed or unrecognized `sv0.toml` `[build]` entry."""


def discover_config(start_dir: str) -> str | None:
    """Return the path to `sv0.toml` beside `start_dir`, or None.

    R0.1's rule (§17.3): for a single file, search beside the file; for a
    project, read `<project>/sv0.toml` only. Both collapse to "does
    `sv0.toml` exist directly inside this one directory" -- no walk toward
    a filesystem root, which would cross a workspace boundary §17.3 forbids.
    """
    candidate = os.path.join(start_dir, "sv0.toml")
    return candidate if os.path.isfile(candidate) else None


def load_config(path: str) -> dict:
    """Parse and validate `sv0.toml`'s `[build]` table.

    Raises `ConfigError` for a missing `[build]` table, an unrecognized
    key, or a recognized key holding the wrong type -- never silently
    drops or coerces, per §17.2.
    """
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{path}: malformed TOML: {exc}") from exc

    build = data.get("build")
    if build is None:
        raise ConfigError(f"{path}: missing required [build] table")
    if not isinstance(build, dict):
        raise ConfigError(f"{path}: [build] must be a table")

    for key, value in build.items():
        if key not in _KNOWN_KEYS:
            raise ConfigError(f"{path}: unrecognized [build] key {key!r}")
        expected_type = _KNOWN_KEYS[key]
        if not isinstance(value, expected_type) or isinstance(value, bool) != (expected_type is bool):
            raise ConfigError(
                f"{path}: [build].{key} must be a {expected_type.__name__}, got {value!r}"
            )

    return build


_UNSET = object()


def resolve_precedence(cli=_UNSET, config=_UNSET, env=_UNSET, default=_UNSET):
    """Apply §11.4's precedence: CLI > config > env > default.

    Each tier is `_UNSET` (the sentinel default) when that source didn't
    supply a value at all -- distinct from an explicit falsy value like
    `False` or `""`, which must still win over a lower tier.
    """
    for tier in (cli, config, env, default):
        if tier is not _UNSET:
            return tier
    raise ConfigError("resolve_precedence: no tier supplied a value, including default")


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    # Case 1: a well-formed config parses to exactly its keys, correctly typed.
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "sv0.toml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(
                '[build]\ncontract-mode = "runtime"\nprofile = "dev"\n'
                'c-compiler = "/usr/bin/clang"\noutput-dir = "build/native"\n'
                "keep-c = false\nbuild-record = false\n"
            )
        found = discover_config(td)
        if found != cfg_path:
            failures.append(f"case1: discover_config found {found!r}, expected {cfg_path!r}")
        build = load_config(cfg_path)
        if build.get("contract-mode") != "runtime" or build.get("keep-c") is not False:
            failures.append(f"case1: unexpected parsed config: {build}")

    # Case 2: discovery returns None when no sv0.toml is present beside the dir.
    with tempfile.TemporaryDirectory() as td:
        if discover_config(td) is not None:
            failures.append("case2: expected no config discovered in an empty dir")

    # Case 3: an unrecognized key is rejected outright (not silently ignored).
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "sv0.toml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write('[build]\ncontract-mode = "runtime"\nbogus-key = "oops"\n')
        try:
            load_config(cfg_path)
            failures.append("case3: expected ConfigError for an unrecognized key, none raised")
        except ConfigError:
            pass

    # Case 4: a recognized key with the wrong type is rejected, not coerced.
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "sv0.toml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write('[build]\nkeep-c = "not-a-bool"\n')
        try:
            load_config(cfg_path)
            failures.append("case4: expected ConfigError for a malformed keep-c, none raised")
        except ConfigError:
            pass

    # Case 4b: a missing [build] table is rejected too.
    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "sv0.toml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write('[not_build]\nfoo = "bar"\n')
        try:
            load_config(cfg_path)
            failures.append("case4b: expected ConfigError for a missing [build] table, none raised")
        except ConfigError:
            pass

    # Case 5: the 4-tier precedence matrix (§11.4): CLI > config > env > default,
    # and an explicit falsy value at a higher tier still wins over a lower one.
    if resolve_precedence(cli="from-cli", config="from-config", env="from-env", default="from-default") != "from-cli":
        failures.append("case5: CLI did not win over config/env/default")
    if resolve_precedence(config="from-config", env="from-env", default="from-default") != "from-config":
        failures.append("case5: config did not win over env/default when CLI unset")
    if resolve_precedence(env="from-env", default="from-default") != "from-env":
        failures.append("case5: env did not win over default when CLI/config unset")
    if resolve_precedence(default="from-default") != "from-default":
        failures.append("case5: default did not apply when nothing else was set")
    if resolve_precedence(cli=False, config="from-config", default="from-default") is not False:
        failures.append("case5: an explicit falsy CLI value was overridden by a lower tier")

    if failures:
        for f in failures:
            print(f"native_exe_config selftest FAIL: {f}")
        return 1

    print("native_exe_config: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_config: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
