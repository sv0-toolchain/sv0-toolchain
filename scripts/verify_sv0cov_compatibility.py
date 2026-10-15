#!/usr/bin/env python3
"""Verify ``compatibility/sv0cov.json`` against the pinned sv0cov gitlink (CV-240).

sv0cov SPEC 20.6.1 / COV-PKG-009 / COV-PKG-014 / R0-G1: the root commits the
exact canonical ``sv0cov.compatibility`` 1.0 policy in the same commit as the
``sv0cov`` gitlink it names. A root commit whose policy and gitlink disagree
fails before sv0cov runs. sv0cov owns the vocabulary and the reader; this
guard reads the policy with sv0cov's own ``validate_policy`` and then checks
what only the root can see:

- the policy is a tracked mode-100644 regular file at the exact path (no
  symlink anywhere on the way), at most 64 KiB, and the working-tree bytes
  equal the staged bytes;
- ``expected_revision`` equals the staged ``sv0cov`` gitlink;
- ``expected_tool.version`` equals ``[project].version`` of ``pyproject.toml``
  in that commit;
- the one allowed diagnostic registry is the revision and digest of
  ``registries/diagnostics-v1.json`` in that commit;
- that commit tracks ``scripts/sv0cov`` at mode 100755 (SPEC 20.6.3);
- with ``--require-clean`` (CI, release evidence), the submodule checkout is
  at that commit with no tracked or untracked change.

Everything is read from the index and from the pinned commit's objects, so the
guard runs before ``git commit`` and does not trust the submodule's working
tree. The guard does not run sv0cov; comparing the policy with the launcher's
``version --json`` is the namespace preflight (CV-241).

``--write`` reseals the policy for the staged gitlink: it takes the revision,
product version, and registry identity from the pinned commit and keeps every
required set of the existing policy (or, for a new policy, the pre-R1 values:
the ``version`` command, all four hosts, every artifact family at ``1.0``).
``--selftest`` runs the checks against throwaway repositories.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sv0cov" / "src"))

from sv0cov.diagnostics import RegistryError, validate_registry  # noqa: E402
from sv0cov.formats.compatibility import MAX_BYTES, PolicyError, seal, validate_policy  # noqa: E402
from sv0cov.model import inventory as inv  # noqa: E402

POLICY = "compatibility/sv0cov.json"
SUBMODULE = "sv0cov"
LAUNCHER = "scripts/sv0cov"
REGISTRY = "registries/diagnostics-v1.json"


class GuardError(Exception):
    pass


def submodule_env() -> dict:
    """The environment without the repository variables a Git hook sets: under
    ``pre-commit``, ``GIT_DIR`` and ``GIT_INDEX_FILE`` name the root, and a Git
    command in the submodule would read the root instead."""
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_") or k.startswith(("GIT_CONFIG", "GIT_SSH"))}


def git(cwd: Path, *args: str, binary: bool = False, env: dict | None = None) -> bytes | str | None:
    try:
        r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False, env=env)
    except OSError:
        return None
    if r.returncode != 0:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8", "replace")


def staged_entry(root: Path, path: str) -> tuple[str, str] | None:
    """``(mode, object id)`` of ``path`` in the index, or None."""
    out = (git(root, "ls-files", "-s", "--", path) or "").strip()
    if not out or "\n" in out:
        return None
    meta, name = out.split("\t", 1)
    mode, oid, _stage = meta.split(" ")
    return (mode, oid) if name == path else None


def gitlink(root: Path) -> str:
    entry = staged_entry(root, SUBMODULE)
    if entry is None or entry[0] != "160000":
        raise GuardError(f"no mode-160000 {SUBMODULE} gitlink in the index (got {entry})")
    return entry[1]


def pinned(root: Path, revision: str) -> dict:
    """What the root policy must name, read from the pinned commit's objects."""
    sub, env = root / SUBMODULE, submodule_env()
    if git(sub, "cat-file", "-e", f"{revision}^{{commit}}", env=env) is None:
        raise GuardError(f"pinned commit {revision} is not present in {SUBMODULE} (run: git submodule update --init {SUBMODULE})")
    pyproject = git(sub, "show", f"{revision}:pyproject.toml", env=env)
    registry = git(sub, "show", f"{revision}:{REGISTRY}", binary=True, env=env)
    launcher = (git(sub, "ls-tree", revision, "--", LAUNCHER, env=env) or "").split()
    if pyproject is None or registry is None:
        raise GuardError(f"pinned commit {revision} lacks pyproject.toml or {REGISTRY}")
    try:
        version = tomllib.loads(pyproject)["project"]["version"]
        reg = validate_registry(registry)
    except (tomllib.TOMLDecodeError, KeyError, RegistryError) as exc:
        raise GuardError(f"pinned commit {revision}: {exc}") from None
    return {"version": version, "registry": {"revision": reg.revision, "sha256": reg.sha256},
            "launcher_mode": launcher[0] if launcher else None}


def policy_file_bytes(root: Path) -> bytes:
    """The working-tree policy bytes: exact path, no symlink on the way, a regular file, bounded before it is read."""
    path = root
    for part in POLICY.split("/"):
        path = path / part
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            raise GuardError(f"{POLICY} is missing") from None
        if stat.S_ISLNK(st.st_mode):
            raise GuardError(f"{path.relative_to(root)} is a symlink")
    if not stat.S_ISREG(st.st_mode):
        raise GuardError(f"{POLICY} is not a regular file")
    if st.st_size > MAX_BYTES:
        raise GuardError(f"{POLICY} exceeds {MAX_BYTES} bytes")
    with open(path, "rb") as f:
        data = f.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise GuardError(f"{POLICY} exceeds {MAX_BYTES} bytes")
    return data


def read_policy_bytes(root: Path) -> bytes:
    """The working-tree policy, which must also equal the staged bytes."""
    data = policy_file_bytes(root)
    entry = staged_entry(root, POLICY)
    if entry is None:
        raise GuardError(f"{POLICY} is not tracked (git add {POLICY})")
    if entry[0] != "100644":
        raise GuardError(f"{POLICY} must be tracked at mode 100644, got {entry[0]}")
    if git(root, "cat-file", "blob", entry[1], binary=True) != data:
        raise GuardError(f"{POLICY} differs from the staged copy (git add {POLICY})")
    return data


def check(root: Path, *, require_clean: bool = False) -> dict:
    data = read_policy_bytes(root)
    try:
        policy = validate_policy(data)
    except PolicyError as exc:
        raise GuardError(f"{POLICY}: {exc}") from None
    revision = gitlink(root)
    errors = []
    if policy["expected_revision"] != revision:
        errors.append(f"expected_revision {policy['expected_revision']} != staged {SUBMODULE} gitlink {revision} "
                      f"(a gitlink change and its policy go in one commit; reseal with --write)")
    facts = pinned(root, revision)
    if policy["expected_tool"]["version"] != facts["version"]:
        errors.append(f"expected_tool.version {policy['expected_tool']['version']} != {facts['version']} in the pinned pyproject.toml")
    if policy["allowed_diagnostic_registries"] != [facts["registry"]]:
        errors.append(f"allowed_diagnostic_registries {policy['allowed_diagnostic_registries']} != the pinned registry {facts['registry']}")
    if facts["launcher_mode"] != "100755":
        errors.append(f"the pinned commit must track {LAUNCHER} at mode 100755, got {facts['launcher_mode']}")
    if require_clean:
        sub, env = root / SUBMODULE, submodule_env()
        head = (git(sub, "rev-parse", "HEAD", env=env) or "").strip()
        if head != revision:
            errors.append(f"{SUBMODULE} HEAD {head or '?'} != pinned {revision}")
        dirty = git(sub, "status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=none", env=env)
        if dirty is None or dirty.strip():
            errors.append(f"{SUBMODULE} checkout is not clean")
    if errors:
        raise GuardError("; ".join(errors))
    return policy


def default_requirements() -> dict:
    return {
        "expected_artifact_versions": {f: ["1.0"] for f in sorted(inv.ARTIFACT_FAMILIES)},
        "required_backends": [],
        "required_bytecode_profiles": [],
        "required_commands": ["version"],
        "required_features": [],
        "required_hosts": list(inv.HOSTS),
    }


def write(root: Path) -> bytes:
    """Reseal the policy for the staged gitlink, keeping its required sets."""
    revision = gitlink(root)
    facts = pinned(root, revision)
    path = root / POLICY
    keep = default_requirements()
    if path.is_file() and not path.is_symlink():
        try:
            old = validate_policy(path.read_bytes())
            keep = {k: old[k] for k in keep}
        except PolicyError:
            pass  # an unreadable policy is replaced by the defaults
    policy = {
        "allowed_diagnostic_registries": [facts["registry"]],
        "allowed_implementation_languages": ["python"],
        "default_implementation_language": "python",
        "expected_revision": revision,
        "expected_tool": {"name": "sv0cov", "version": facts["version"]},
        "schema": "sv0cov.compatibility",
        "submodule_path": SUBMODULE,
        "version": "1.0",
        "version_manifest_version": "1.0",
        **keep,
    }
    data = seal(policy)
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(data)
    return data


# ── selftest ─────────────────────────────────────────────────────────────────


def _run(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "protocol.file.allow=always", *args], cwd=cwd,
                          env=env, check=True, capture_output=True, text=True).stdout.strip()


class Fixture:
    """A root repository with an sv0cov submodule whose commits carry the pinned facts."""

    def __init__(self, base: Path) -> None:
        self.base = base
        self.upstream = base / "upstream"
        self.upstream.mkdir()
        _run(self.upstream, "init", "-q", "-b", "main")
        (self.upstream / "scripts").mkdir()
        (self.upstream / "registries").mkdir()
        (self.upstream / LAUNCHER).write_text("#!/bin/sh\n")
        (self.upstream / LAUNCHER).chmod(0o755)
        (self.upstream / REGISTRY).write_bytes((ROOT / SUBMODULE / REGISTRY).read_bytes())
        self.first = self.release("0.1.0")
        self.root = base / "root"
        self.root.mkdir()
        _run(self.root, "init", "-q", "-b", "main")
        _run(self.root, "submodule", "add", "-q", str(self.upstream), SUBMODULE)
        write(self.root)
        _run(self.root, "add", "-A")
        _run(self.root, "commit", "-q", "-m", "pin")

    def release(self, version: str) -> str:
        (self.upstream / "pyproject.toml").write_text(f'[project]\nname = "sv0cov"\nversion = "{version}"\n')
        _run(self.upstream, "add", "-A")
        _run(self.upstream, "commit", "-q", "-m", version)
        return _run(self.upstream, "rev-parse", "HEAD")

    def bump(self, version: str) -> str:
        sha = self.release(version)
        sub = self.root / SUBMODULE
        _run(sub, "fetch", "-q", str(self.upstream))
        _run(sub, "checkout", "-q", sha)
        _run(self.root, "add", SUBMODULE)
        return sha


def _case(template: Path, label: str, mutate, ok: bool, *, require_clean: bool = False) -> str | None:
    with tempfile.TemporaryDirectory() as tmp:
        shutil.copytree(template, Path(tmp) / "t", symlinks=True)
        fx = Fixture.__new__(Fixture)
        fx.base, fx.upstream, fx.root = Path(tmp) / "t", Path(tmp) / "t" / "upstream", Path(tmp) / "t" / "root"
        mutate(fx)
        try:
            check(fx.root, require_clean=require_clean)
            got = None
        except GuardError as exc:
            got = str(exc)
    if (got is None) != ok:
        return f"{label}: expected {'pass' if ok else 'failure'}, got {got or 'pass'}"
    return None


def _edit(fx: Fixture, **changes) -> None:
    obj = validate_policy((fx.root / POLICY).read_bytes())
    obj.update(changes)
    (fx.root / POLICY).write_bytes(seal(obj))
    _run(fx.root, "add", POLICY)


def _symlink(fx: Fixture) -> None:
    real = fx.root / "elsewhere.json"
    (fx.root / POLICY).rename(real)
    (fx.root / POLICY).symlink_to("../elsewhere.json")
    _run(fx.root, "add", "-A")


def _bump_and_write(fx: Fixture) -> None:
    fx.bump("0.2.0")
    write(fx.root)
    _run(fx.root, "add", POLICY)


def _drop_exec(fx: Fixture) -> None:
    (fx.upstream / LAUNCHER).chmod(0o644)
    fx.bump("0.2.0")
    write(fx.root)
    _run(fx.root, "add", POLICY)


def _tamper_digest(fx: Fixture) -> None:
    path = fx.root / POLICY
    path.write_bytes(path.read_bytes().replace(b'"required_hosts":["linux-arm64",', b'"required_hosts":['))
    _run(fx.root, "add", POLICY)


CASES = [
    ("pinned and sealed", lambda fx: None, True),
    ("clean checkout", lambda fx: None, True, True),
    ("gitlink bumped without the policy", lambda fx: fx.bump("0.2.0"), False),
    ("gitlink bumped with --write", _bump_and_write, True),
    ("policy names another commit", lambda fx: _edit(fx, expected_revision="0" * 40), False),
    ("policy names another product version", lambda fx: _edit(fx, expected_tool={"name": "sv0cov", "version": "0.9.0"}), False),
    ("policy names another registry", lambda fx: _edit(fx, allowed_diagnostic_registries=[{"revision": 1, "sha256": "a" * 64}]), False),
    ("digest no longer matches", _tamper_digest, False),
    ("noncanonical bytes", lambda fx: ((fx.root / POLICY).write_bytes((fx.root / POLICY).read_bytes() + b"\n"), _run(fx.root, "add", POLICY)), False),
    ("unstaged edit", lambda fx: (fx.root / POLICY).write_bytes((fx.root / POLICY).read_bytes().replace(b"0.1.0", b"0.1.1")), False),
    ("untracked policy", lambda fx: _run(fx.root, "rm", "-q", "--cached", POLICY), False),
    ("symlinked policy", _symlink, False),
    ("missing policy", lambda fx: (fx.root / POLICY).unlink(), False),
    ("launcher not executable in the pinned commit", _drop_exec, False),
    ("dirty submodule (tolerated locally)", lambda fx: (fx.root / SUBMODULE / "scratch").write_text("x"), True),
    ("dirty submodule (release evidence)", lambda fx: (fx.root / SUBMODULE / "scratch").write_text("x"), False, True),
    ("submodule HEAD elsewhere (release evidence)", lambda fx: _run(fx.root / SUBMODULE, "commit", "-q", "--allow-empty", "-m", "x"), False, True),
]


def selftest() -> int:
    for k in [k for k in os.environ if k.startswith("GIT_")]:  # run from a hook: the fixtures are other repositories
        del os.environ[k]
    with tempfile.TemporaryDirectory() as tmp:
        Fixture(Path(tmp))  # built once, copied for each case
        failures = [msg for c in CASES if (msg := _case(Path(tmp), *c[:3], require_clean=c[3] if len(c) > 3 else False))]
    for msg in failures:
        print(f"selftest FAIL {msg}")
    if failures:
        return 1
    print(f"verify_sv0cov_compatibility selftest: {len(CASES)} cases OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--write", action="store_true", help="reseal the policy for the staged gitlink")
    ap.add_argument("--require-clean", action="store_true", help="also require a clean submodule checkout at the pinned commit")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    root = args.root.resolve()
    try:
        if args.write:
            data = write(root)
            print(f"verify_sv0cov_compatibility: wrote {POLICY} ({hashlib.sha256(data).hexdigest()[:12]}); stage it with the gitlink")
            return 0
        policy = check(root, require_clean=args.require_clean)
    except GuardError as exc:
        print(f"verify_sv0cov_compatibility: {exc}", file=sys.stderr)
        return 1
    print(f"verify_sv0cov_compatibility: {POLICY} pins {SUBMODULE} {policy['expected_revision'][:12]} "
          f"({policy['expected_tool']['version']}, registry revision {policy['allowed_diagnostic_registries'][0]['revision']}) OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
