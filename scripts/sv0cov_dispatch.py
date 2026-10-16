#!/usr/bin/env python3
"""``./scripts/sv0 coverage <subcommand>``: fixed launcher, preflight, dispatch (CV-241).

sv0cov SPEC 20.1.1, 20.6.2, 20.6.3. ``scripts/sv0`` has already checked that
the subcommand is one of the seven; it runs this file with the ``PATH`` it
inherited at process entry in ``SV0_COVERAGE_ENTRY_PATH`` (the driver may put
a newer Python first on its own ``PATH``; the launcher resolves its runtime
from the caller's, SPEC 20.6.4).

1. The launcher is exactly ``<physical-root>/sv0cov/scripts/sv0cov``: no
   component a symlink, the last a regular executable file. Nothing else is
   ever searched for.
2. ``doctor`` skips the preflight and gets ``--toolchain-root <physical-root>``
   in front of the caller's arguments; a caller's own ``--toolchain-root`` is
   an invocation error (exit 2).
3. Every other subcommand first passes the silent compatibility preflight:
   the root policy (read with sv0cov's own reader), the staged gitlink, the
   pinned commit's launcher mode and diagnostic registry, and one
   ``version --json`` from the launcher, compared by the nine rules of SPEC
   20.6.2. Any failure is ``COV5002`` on stderr, exit 7, and nothing else
   runs.
4. The launcher then replaces this process with the caller's argv after the
   subcommand untouched, the caller's working directory, standard streams
   and ``PATH``, so its exit status (or signal) is the driver's.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # physical: every symlink on the way resolved
sys.path.insert(0, str(Path(__file__).resolve().parent))

ENTRY_PATH = "SV0_COVERAGE_ENTRY_PATH"
SUBCOMMANDS = ("check", "clean", "doctor", "merge", "report", "run", "version")
LAUNCHER = ("sv0cov", "scripts", "sv0cov")
PREFLIGHT_SECONDS = 30
EXIT_USAGE = 2
EXIT_INCOMPATIBLE = 7
HOSTS = {"Darwin": "macos", "Linux": "linux"}
MACHINES = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}


class Incompatible(Exception):
    """Preflight or launcher failure: COV5002, exit 7."""


def escape(text: str) -> str:
    return "".join(f"\\x{ord(c):02x}" if ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F else c for c in text)


def report(detail: str) -> int:
    sys.stderr.write(f"COV5002 error: Release or submodule compatibility failed\n  detail: {escape(detail)}\n")
    return EXIT_INCOMPATIBLE


def launcher(root: Path) -> Path:
    """The fixed launcher (SPEC 20.6.3), or Incompatible."""
    path = root
    for i, part in enumerate(LAUNCHER):
        path = path / part
        try:
            st = os.lstat(path)
        except OSError:
            raise Incompatible(f"the fixed launcher {'/'.join(LAUNCHER)} is missing") from None
        if stat.S_ISLNK(st.st_mode):
            raise Incompatible(f"{'/'.join(LAUNCHER[: i + 1])} is a symlink")
        last = i == len(LAUNCHER) - 1
        if not last and not stat.S_ISDIR(st.st_mode):
            raise Incompatible(f"{'/'.join(LAUNCHER[: i + 1])} is not a directory")
    if not stat.S_ISREG(st.st_mode):
        raise Incompatible(f"the fixed launcher {'/'.join(LAUNCHER)} is not a regular file")
    if not os.access(path, os.X_OK):
        raise Incompatible(f"the fixed launcher {'/'.join(LAUNCHER)} is not executable")
    return path


def observed_host() -> tuple[str, str]:
    """The effective OS and process architecture, observed here, not taken from sv0cov."""
    u = os.uname()
    system, machine = HOSTS.get(u.sysname), MACHINES.get(u.machine.lower())
    if system is None or machine is None or sys.maxsize <= 2**32:
        raise Incompatible(f"unsupported host {u.sysname} {u.machine}")
    return system, machine


def capability_manifest(exe: Path, env: dict) -> bytes:
    from sv0cov.formats.version_manifest import MAX_BYTES

    try:
        r = subprocess.run([str(exe), "version", "--json"], stdin=subprocess.DEVNULL, capture_output=True, env=env,
                           cwd=ROOT, timeout=PREFLIGHT_SECONDS, check=False)
    except subprocess.TimeoutExpired:
        raise Incompatible(f"sv0cov version --json did not finish in {PREFLIGHT_SECONDS} s") from None
    except OSError as exc:
        raise Incompatible(f"the fixed launcher cannot be started: {exc.strerror}") from None
    if r.returncode != 0:
        why = [line.strip() for line in r.stderr.decode("utf-8", "replace").splitlines() if line.strip()]
        raise Incompatible(f"sv0cov version --json exited {r.returncode}" + (f": {' / '.join(why[:4])}" if why else ""))
    if r.stderr:
        raise Incompatible("sv0cov version --json wrote to stderr")
    if len(r.stdout) > MAX_BYTES:
        raise Incompatible(f"sv0cov version --json wrote more than {MAX_BYTES} bytes")
    return r.stdout


def preflight(root: Path, exe: Path, env: dict) -> None:
    """The nine rules of SPEC 20.6.2, in order."""
    import verify_sv0cov_compatibility as guard
    from sv0cov.formats import compatibility
    from sv0cov.formats.compatibility import PolicyError, validate_policy
    from sv0cov.formats.version_manifest import ManifestError, validate_manifest

    # 1. the policy itself
    try:
        policy = validate_policy(guard.policy_file_bytes(root))
    except guard.GuardError as exc:
        raise Incompatible(str(exc)) from None
    except PolicyError as exc:
        raise Incompatible(f"{guard.POLICY}: {exc}") from None
    # 2. the gitlink, and what the pinned commit holds
    try:
        revision = guard.gitlink(root)
        pinned = guard.pinned(root, revision)
    except guard.GuardError as exc:
        raise Incompatible(str(exc)) from None
    if policy["submodule_path"] != guard.SUBMODULE or policy["expected_revision"] != revision:
        raise Incompatible(f"expected_revision {policy['expected_revision']} != the {guard.SUBMODULE} gitlink {revision}")
    if pinned["launcher_mode"] != "100755":
        raise Incompatible(f"the pinned commit tracks {guard.LAUNCHER} at mode {pinned['launcher_mode']}, not 100755")
    # 3. one canonical, self-consistent capability manifest
    try:
        manifest = validate_manifest(capability_manifest(exe, env))
    except ManifestError as exc:
        raise Incompatible(f"sv0cov version --json: {exc}") from None
    # 3 to 9: sv0cov's own comparison (SPEC 20.6.1: sv0cov owns the semantics), against
    # the host observed here and the registry the pinned commit carries
    system, machine = observed_host()
    try:
        compatibility.evaluate(policy, manifest, {"architecture": machine, "operating_system": system}, pinned["registry"])
    except compatibility.Incompatible as exc:
        raise Incompatible(str(exc)) from None


def dispatch(argv: list[str]) -> int:
    sub, args = argv[0], argv[1:]
    if sub not in SUBCOMMANDS:  # scripts/sv0 checks this first; never reached from there
        sys.stderr.write(f"sv0 coverage: unknown subcommand {escape(sub)!r}\n")
        return EXIT_USAGE
    if sub == "doctor" and any(a == "--toolchain-root" or a.startswith("--toolchain-root=") for a in args):
        sys.stderr.write("sv0 coverage doctor: --toolchain-root is set by the root driver and cannot be given\n")
        return EXIT_USAGE
    env = dict(os.environ)
    entry = env.pop(ENTRY_PATH, None)
    if entry is None:
        return report(f"{ENTRY_PATH} is not set; run through ./scripts/sv0 coverage")
    env["PATH"] = entry
    try:
        exe = launcher(ROOT)
        if sub == "doctor":
            args = ["--toolchain-root", str(ROOT), *args]
        else:
            sys.path.insert(0, str(ROOT / "sv0cov" / "src"))
            try:
                preflight(ROOT, exe, env)
            except ImportError as exc:
                raise Incompatible(f"the pinned sv0cov readers cannot be loaded: {exc}") from None
    except Incompatible as exc:
        return report(str(exc))
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        os.execve(exe, [str(exe), sub, *args], env)
    except OSError as exc:
        return report(f"the fixed launcher cannot be started: {exc.strerror}")
    return 0  # not reached


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stderr.write("usage: sv0cov_dispatch.py <subcommand> [args...]\n")
        sys.exit(EXIT_USAGE)
    sys.exit(dispatch(sys.argv[1:]))
