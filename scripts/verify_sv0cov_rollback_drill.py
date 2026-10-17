#!/usr/bin/env python3
"""Rollback dry run for the sv0cov pin (CV-244; sv0cov SPEC 20.6.3, R0-G8).

A rollback is a reviewed root change to a previously qualified gitlink and
its matching compatibility policy; there is no runtime switch. This drill
performs that change in a throwaway copy of this checkout and then rolls
forward again, publishing nothing and touching nothing here:

1. The previous qualified pin is the ``sv0cov`` gitlink of the most recent
   root commit that changed ``compatibility/sv0cov.json`` while pinning
   another commit than today's; its policy bytes are the qualified policy.
2. A shared clone of this repository (HEAD) gets a shared clone of the
   ``sv0cov`` checkout, detached at that commit, and the gitlink is staged.
3. ``verify_sv0cov_compatibility.py --write`` (the copy's own) reseals the
   policy, which must be byte-identical to the qualified one; the guard then
   passes with ``--require-clean``; ``./scripts/sv0 coverage version --json``
   passes the preflight and reports the rolled-back commit.
4. The same steps to the current pin reproduce HEAD's committed policy byte
   for byte and report the current commit.
5. This checkout's index, HEAD and policy are unchanged.

Like the toolchain doctor guard, the launcher needs a real ``python3.14`` or
``python3.13`` on ``PATH``; shim directories are left out of the child's
``PATH``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "sv0cov" / "src"))

from verify_sv0cov_toolchain_doctor import launcher_path  # noqa: E402

from sv0cov.formats.version_manifest import validate_manifest  # noqa: E402

POLICY = "compatibility/sv0cov.json"


class DrillFailure(Exception):
    pass


def env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("GIT_")} | {"GIT_CONFIG_NOSYSTEM": "1"}


def git(cwd: Path, *args: str, binary: bool = False) -> str | bytes:
    r = subprocess.run(["git", "-c", "advice.detachedHead=false", *args], cwd=cwd, env=env(), capture_output=True, check=False)
    if r.returncode:
        raise DrillFailure(f"git {' '.join(args)} in {cwd.name}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout if binary else r.stdout.decode("utf-8").strip()


def previous_pin(current: str) -> tuple[str, str, bytes]:
    """(root commit, its sv0cov gitlink, its policy bytes) of the last qualified pin before ``current``."""
    for commit in git(ROOT, "log", "--format=%H", "--", POLICY).split():
        pin = git(ROOT, "rev-parse", f"{commit}:sv0cov")
        if pin != current:
            return commit, pin, git(ROOT, "show", f"{commit}:{POLICY}", binary=True)
    raise DrillFailure("no earlier qualified pin: the policy has only ever named the current sv0cov commit")


def run(cwd: Path, *argv: str, path: str | None = None) -> subprocess.CompletedProcess:
    e = env() if path is None else {**env(), "PATH": path}
    return subprocess.run(list(argv), cwd=cwd, env=e, stdin=subprocess.DEVNULL, capture_output=True, timeout=600, check=False)


def pin(copy: Path, revision: str, qualified: bytes, path: str) -> None:
    """Move the copy's pin to ``revision`` the reviewed way and check everything that follows.
    The reviewed change restores the qualified policy's required sets (the root's own choice,
    which ``--write`` keeps) and reseals it for the gitlink."""
    sub = copy / "sv0cov"
    git(sub, "checkout", "-q", "--detach", revision)
    git(copy, "update-index", "--cacheinfo", f"160000,{revision},sv0cov")
    (copy / POLICY).write_bytes(qualified)
    guard = [sys.executable, str(copy / "scripts" / "verify_sv0cov_compatibility.py"), "--root", str(copy)]
    r = run(copy, *guard, "--write")
    if r.returncode:
        raise DrillFailure(f"resealing for {revision[:12]} failed: {r.stderr.decode('utf-8', 'replace').strip()}")
    if (copy / POLICY).read_bytes() != qualified:
        raise DrillFailure(f"the resealed policy for {revision[:12]} is not the qualified policy byte for byte")
    git(copy, "add", POLICY)
    r = run(copy, *guard, "--require-clean")
    if r.returncode:
        raise DrillFailure(f"the compatibility guard refuses {revision[:12]}: {r.stderr.decode('utf-8', 'replace').strip()}")
    r = run(copy, str(copy / "scripts" / "sv0"), "coverage", "version", "--json", path=path)
    if r.returncode:
        raise DrillFailure(f"sv0 coverage version at {revision[:12]} exited {r.returncode}: {r.stderr.decode('utf-8', 'replace').strip()}")
    manifest = validate_manifest(r.stdout)
    if manifest["implementation"]["revision"] != revision:
        raise DrillFailure(f"sv0 coverage version reports {manifest['implementation']['revision']}, not {revision}")


def main() -> int:
    path = launcher_path()
    if path is None:
        print("verify_sv0cov_rollback_drill: no real python3.14 or python3.13 on PATH (sv0cov needs one)", file=sys.stderr)
        return 1
    before = (git(ROOT, "rev-parse", "HEAD"), git(ROOT, "ls-files", "-s", "--", "sv0cov", POLICY), (ROOT / POLICY).read_bytes())
    current = git(ROOT, "rev-parse", "HEAD:sv0cov")
    try:
        root_commit, previous, qualified = previous_pin(current)
        with tempfile.TemporaryDirectory(prefix="sv0cov-rollback-") as tmp:
            copy = Path(tmp) / "root"
            git(Path(tmp), "clone", "-q", "--shared", "--no-checkout", str(ROOT), str(copy))
            git(copy, "checkout", "-q", "--detach", before[0])
            git(Path(tmp), "clone", "-q", "--shared", "--no-checkout", str(ROOT / "sv0cov"), str(copy / "sv0cov"))
            pin(copy, previous, qualified, path)  # roll back
            pin(copy, current, git(ROOT, "show", f"HEAD:{POLICY}", binary=True), path)  # and forward again
        after = (git(ROOT, "rev-parse", "HEAD"), git(ROOT, "ls-files", "-s", "--", "sv0cov", POLICY), (ROOT / POLICY).read_bytes())
        if after != before:
            raise DrillFailure("the drill changed this checkout")
    except DrillFailure as exc:
        print(f"verify_sv0cov_rollback_drill: {exc}", file=sys.stderr)
        return 1
    print(f"verify_sv0cov_rollback_drill: rolled sv0cov back to {previous[:12]} (qualified by {root_commit[:12]}) and forward to "
          f"{current[:12]}; both policies reproduced byte for byte, guard and preflight passed; nothing here changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
