#!/usr/bin/env python3
"""Contract tests for the root ``./scripts/sv0 coverage`` namespace (CV-032).

sv0cov SPEC 20.1.1, 20.6.2, 20.6.3, AC-118. These are written ahead of the
implementation (CV-241) and are expected to FAIL until it lands; they are
deliberately not wired into ``./scripts/sv0 test-guards`` yet. CV-241 wires
them in and is done when they pass.

Each test builds a throwaway toolchain root: a copy of the real driver
(``DRIVER_FILES``), a Git repository whose ``sv0cov`` gitlink points at a
fake sv0cov checkout, and a sealed ``compatibility/sv0cov.json``. The fake
launcher at ``sv0cov/scripts/sv0cov`` answers ``version --json`` with a
manifest that satisfies the policy, and records every other invocation
(argv, working directory, PATH, stdin) before writing fixed bytes to
stdout/stderr and exiting with a controlled status or signal.

    python3 scripts/verify_sv0cov_root_namespace.py        # run the contract
"""

from __future__ import annotations

import os
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "sv0cov" / "src"))

from sv0cov.diagnostics import load_registry  # noqa: E402
from sv0cov.formats.compatibility import seal, validate_policy  # noqa: E402
from sv0cov.formats.version_manifest import Advertised, build, current_host, validate_manifest  # noqa: E402
from sv0cov.model import inventory as inv  # noqa: E402

# Files copied from this checkout into each fake root. CV-241 adds any helper
# the driver's coverage dispatch needs.
DRIVER_FILES = ("scripts/sv0", "lib/shell/common.sh")
SUBCOMMANDS = ("run", "merge", "report", "check", "clean", "version")
TOOL_VERSION = "1.0.0"
STDOUT = b"stdout-bytes\x00\xff\n"
STDERR = b"stderr-bytes\n"
TRICKY_ARGS = ["", "a b", "*", "$HOME", "x;y", "--", "--toolchain-root", "-", "é"]

GIT_ENV = {
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.invalid",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.invalid",
}

FAKE_LAUNCHER = r"""#!/bin/sh
S='@STATE@'
n=$(/bin/ls "$S/calls" | /usr/bin/wc -l | /usr/bin/tr -d ' ')
d="$S/calls/$(printf '%03d' "$n")"
/bin/mkdir "$d"
for a in "$@"; do printf '%s\000' "$a" >>"$d/argv"; done
: >>"$d/argv"
/bin/pwd -P >"$d/cwd"
printf '%s' "$PATH" >"$d/path"
if [ "$#" -eq 2 ] && [ "$1" = version ] && [ "$2" = --json ] && [ "$n" = 0 ]; then
    exec /bin/cat "$S/manifest.json"
fi
/bin/cat >"$d/stdin"
printf 'stdout-bytes\000\377\n'
printf 'stderr-bytes\n' >&2
mode=$(/bin/cat "$S/mode")
case $mode in
    signal) /bin/kill -TERM $$ ;;
    *) exit "$mode" ;;
esac
"""


def git(cwd: Path, *args: str) -> str:
    env = {**os.environ, **GIT_ENV}
    return subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


class FakeRoot:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "root"
        self.state = base / "state"
        (self.state / "calls").mkdir(parents=True)
        (self.state / "mode").write_text("0")
        for rel in DRIVER_FILES:
            dst = self.root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, dst)
        sub = self.root / "sv0cov"
        (sub / "scripts").mkdir(parents=True)
        launcher = sub / "scripts" / "sv0cov"
        launcher.write_text(FAKE_LAUNCHER.replace("@STATE@", str(self.state)))
        launcher.chmod(0o755)
        git(sub, "init", "-q")
        git(sub, "add", "scripts/sv0cov")
        git(sub, "commit", "-q", "-m", "fake sv0cov")
        self.revision = git(sub, "rev-parse", "HEAD")
        self.write_manifest(self.revision)
        (self.root / ".gitmodules").write_text('[submodule "sv0cov"]\n\tpath = sv0cov\n\turl = git@github.com:sv0-toolchain/sv0cov.git\n')
        self.write_policy(self.revision)
        git(self.root, "init", "-q")
        git(self.root, "-c", "advice.addEmbeddedRepo=false", "add", "-A")
        git(self.root, "commit", "-q", "-m", "fake root")

    def write_manifest(self, revision: str, **overrides: object) -> None:
        reg = load_registry()
        runtime = platform.python_version() if sys.version_info[:2] in ((3, 13), (3, 14)) else "3.14.0"
        advertised = Advertised(commands=inv.COMMANDS, backends=inv.BACKENDS, bytecode_profiles=inv.BYTECODE_PROFILES, features=inv.FEATURES)
        args = dict(tool_version=TOOL_VERSION, revision=revision, runtime_version=runtime, host=current_host(), registry_revision=reg.revision, registry_sha256=reg.sha256, advertised=advertised)
        args.update(overrides)
        (self.state / "manifest.json").write_bytes(build(**args))

    def write_policy(self, revision: str) -> None:
        reg = load_registry()
        policy = {
            "allowed_diagnostic_registries": [{"revision": reg.revision, "sha256": reg.sha256}],
            "allowed_implementation_languages": ["python"],
            "default_implementation_language": "python",
            "expected_artifact_versions": {f: ["1.0"] for f in sorted(inv.ARTIFACT_FAMILIES)},
            "expected_revision": revision,
            "expected_tool": {"name": "sv0cov", "version": TOOL_VERSION},
            "required_backends": list(inv.BACKENDS),
            "required_bytecode_profiles": list(inv.BYTECODE_PROFILES),
            "required_commands": list(inv.COMMANDS),
            "required_features": list(inv.FEATURES),
            "required_hosts": list(inv.HOSTS),
            "schema": "sv0cov.compatibility",
            "submodule_path": "sv0cov",
            "version": "1.0",
            "version_manifest_version": "1.0",
        }
        path = self.root / "compatibility" / "sv0cov.json"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(seal(policy))

    def calls(self) -> list[dict]:
        out = []
        for d in sorted((self.state / "calls").iterdir()):
            argv = (d / "argv").read_bytes().split(b"\0")[:-1]
            stdin = d / "stdin"
            out.append({
                "argv": [a.decode("utf-8") for a in argv],
                "cwd": (d / "cwd").read_text().strip(),
                "path": (d / "path").read_text(),
                "stdin": stdin.read_bytes() if stdin.exists() else None,
            })
        return out

    def requested(self) -> list[dict]:
        """Calls other than the compatibility preflight."""
        return [c for c in self.calls() if c["argv"] != ["version", "--json"] or c["stdin"] is not None]


class NamespaceContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(os.path.realpath(self._tmp.name))
        self.fake = FakeRoot(base)
        self.caller = base / "caller"
        self.caller.mkdir()
        self.path = os.pathsep.join([str(Path(sys.executable).parent), "/usr/bin", "/bin"])

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def sv0(self, *args: str, stdin: bytes = b"", driver: str | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
        driver = driver or str(self.fake.root / "scripts" / "sv0")
        env = {"PATH": self.path, "HOME": str(self.caller), "LC_ALL": "C"}
        return subprocess.run([driver, *args], input=stdin, env=env, cwd=cwd or self.caller, capture_output=True, timeout=120)

    def assert_passthrough(self, r: subprocess.CompletedProcess, status: int) -> None:
        self.assertEqual(r.stdout, STDOUT)
        self.assertEqual(r.stderr, STDERR)
        self.assertEqual(r.returncode, status)

    # --- the fixture itself (passes before CV-241) --------------------------

    def test_fixture_is_consistent(self) -> None:
        policy = validate_policy((self.fake.root / "compatibility" / "sv0cov.json").read_bytes())
        launcher = self.fake.root / "sv0cov" / "scripts" / "sv0cov"
        out = subprocess.run([str(launcher), "version", "--json"], capture_output=True, check=True).stdout
        manifest = validate_manifest(out)
        gitlink = git(self.fake.root, "ls-tree", "HEAD", "sv0cov").split()
        self.assertEqual(gitlink[:3], ["160000", "commit", policy["expected_revision"]])
        self.assertEqual(manifest["implementation"]["revision"], policy["expected_revision"])
        self.assertEqual(manifest["tool"], policy["expected_tool"])
        shutil.rmtree(self.fake.state / "calls")
        (self.fake.state / "calls").mkdir()

    # --- successful dispatch ------------------------------------------------

    def test_each_subcommand_preserves_argv_cwd_streams_and_exit(self) -> None:
        for i, sub in enumerate(SUBCOMMANDS):
            with self.subTest(sub=sub):
                shutil.rmtree(self.fake.state / "calls")
                (self.fake.state / "calls").mkdir()
                (self.fake.state / "mode").write_text(str(10 + i))
                r = self.sv0("coverage", sub, *TRICKY_ARGS, stdin=b"in\x00put")
                self.assert_passthrough(r, 10 + i)
                calls = self.fake.calls()
                self.assertEqual(calls[0]["argv"], ["version", "--json"], "preflight first")
                self.assertEqual(len(self.fake.requested()), 1)
                req = self.fake.requested()[0]
                self.assertEqual(req["argv"], [sub, *TRICKY_ARGS])
                self.assertEqual(req["cwd"], str(self.caller))
                self.assertEqual(req["stdin"], b"in\x00put", "preflight must not consume stdin")

    def test_exit_statuses_are_preserved(self) -> None:
        for status in (0, 1, 2, 7, 8, 42, 255):
            with self.subTest(status=status):
                (self.fake.state / "mode").write_text(str(status))
                self.assert_passthrough(self.sv0("coverage", "check", "x.json"), status)

    def test_signal_status_is_preserved(self) -> None:
        (self.fake.state / "mode").write_text("signal")
        r = self.sv0("coverage", "run", "--", "t")
        self.assertIn(r.returncode, (-signal.SIGTERM, 128 + signal.SIGTERM))

    def test_inherited_path_reaches_the_launcher_unchanged(self) -> None:
        self.sv0("coverage", "clean")
        requested = self.fake.requested()
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0]["path"], self.path)

    def test_driver_by_relative_path_from_another_directory(self) -> None:
        rel = os.path.relpath(self.fake.root / "scripts" / "sv0", self.caller)
        r = self.sv0("coverage", "merge", "raw", driver=rel)
        self.assert_passthrough(r, 0)
        self.assertEqual([c["cwd"] for c in self.fake.requested()], [str(self.caller)])

    # --- doctor -------------------------------------------------------------

    def test_doctor_gets_the_physical_root_and_no_preflight(self) -> None:
        (self.fake.state / "mode").write_text("5")
        r = self.sv0("coverage", "doctor", "--json")
        self.assert_passthrough(r, 5)
        calls = self.fake.calls()
        self.assertEqual([c["argv"] for c in calls], [["doctor", "--toolchain-root", str(self.fake.root), "--json"]])

    def test_doctor_runs_even_when_the_policy_is_broken(self) -> None:
        (self.fake.root / "compatibility" / "sv0cov.json").write_bytes(b"{}\n")
        (self.fake.state / "mode").write_text("1")
        self.assert_passthrough(self.sv0("coverage", "doctor"), 1)

    def test_doctor_rejects_caller_toolchain_root(self) -> None:
        for args in (["--toolchain-root", "/x"], ["--toolchain-root=/x"], ["--json", "--toolchain-root", str(self.fake.root)]):
            with self.subTest(args=args):
                r = self.sv0("coverage", "doctor", *args)
                self.assertEqual(r.returncode, 2)
                self.assertEqual(self.fake.calls(), [])

    # --- invocation errors (exit 2, nothing executed) -----------------------

    def test_invocation_errors(self) -> None:
        cases = [
            ["coverage"],
            ["coverage", "bogus"],
            ["coverage", "Run"],
            ["coverage", "RUN"],
            ["coverage", "--verbose", "run"],
            ["coverage", "--help"],
            ["coverage", "-h", "run"],
            ["coverage", ""],
            ["cov", "run"],
            ["sv0cov", "run"],
            ["coverage-run"],
            ["coverage-report"],
            ["Coverage", "run"],
        ]
        for args in cases:
            with self.subTest(args=args):
                r = self.sv0(*args)
                self.assertEqual(r.returncode, 2, r.stderr)
                self.assertEqual(r.stdout, b"")
                self.assertEqual(self.fake.calls(), [])

    # --- compatibility preflight (COV5002, exit 7) --------------------------

    def assert_preflight_failure(self, *args: str) -> None:
        r = self.sv0("coverage", *args)
        self.assertEqual(r.returncode, 7, r.stderr)
        self.assertIn(b"COV5002", r.stderr)
        self.assertEqual(r.stdout, b"")
        self.assertEqual(self.fake.requested(), [])

    def test_policy_failures(self) -> None:
        policy = self.fake.root / "compatibility" / "sv0cov.json"
        good = policy.read_bytes()
        bad = {
            "missing": None,
            "tampered": good.replace(b'"schema":"sv0cov.compatibility"', b'"schema":"sv0cov.compatibilitY"'),
            "not-canonical": good.replace(b"{", b"{ ", 1),
            "oversized": good[:-1] + b" " * 65536 + b"\n",
        }
        for name, data in bad.items():
            with self.subTest(policy=name):
                if data is None:
                    policy.unlink()
                else:
                    policy.write_bytes(data)
                self.assert_preflight_failure("report", "x")
                policy.write_bytes(good)

    def test_policy_symlink_is_rejected(self) -> None:
        policy = self.fake.root / "compatibility" / "sv0cov.json"
        moved = self.fake.base / "policy.json"
        policy.rename(moved)
        policy.symlink_to(moved)
        self.assert_preflight_failure("check", "x")

    def test_manifest_disagreements(self) -> None:
        other = "0" * 39 + "1"
        for name, kwargs in {
            "revision": {"revision": other},
            "tool-version": {"tool_version": "1.0.1"},
            "registry": {"registry_sha256": "0" * 64},
        }.items():
            with self.subTest(manifest=name):
                self.fake.write_manifest(kwargs.pop("revision", self.fake.revision), **kwargs)
                self.assert_preflight_failure("merge", "raw")
        self.fake.write_manifest(self.fake.revision)

    def test_contaminated_manifest_stdout(self) -> None:
        manifest = self.fake.state / "manifest.json"
        manifest.write_bytes(b"warning\n" + manifest.read_bytes())
        self.assert_preflight_failure("run", "--", "t")

    def test_gitlink_must_equal_expected_revision(self) -> None:
        self.fake.write_policy("0" * 39 + "1")
        self.assert_preflight_failure("version")

    def test_launcher_defects(self) -> None:
        launcher = self.fake.root / "sv0cov" / "scripts" / "sv0cov"
        body = launcher.read_bytes()
        aside = self.fake.base / "launcher"

        def missing() -> None:
            launcher.unlink()

        def not_executable() -> None:
            launcher.chmod(0o644)

        def symlink() -> None:
            aside.write_bytes(body)
            aside.chmod(0o755)
            launcher.unlink()
            launcher.symlink_to(aside)

        def directory() -> None:
            launcher.unlink()
            launcher.mkdir()

        for defect in (missing, not_executable, symlink, directory):
            with self.subTest(defect=defect.__name__):
                try:
                    defect()
                    self.assert_preflight_failure("clean")
                finally:
                    if launcher.is_dir() and not launcher.is_symlink():
                        launcher.rmdir()
                    elif launcher.exists() or launcher.is_symlink():
                        launcher.unlink()
                    launcher.write_bytes(body)
                    launcher.chmod(0o755)

    def test_no_fallback_launcher_is_searched(self) -> None:
        (self.fake.root / "sv0cov" / "scripts" / "sv0cov").unlink()
        decoy = self.fake.base / "bin"
        decoy.mkdir()
        (decoy / "sv0cov").write_text("#!/bin/sh\necho decoy\n")
        (decoy / "sv0cov").chmod(0o755)
        self.path = os.pathsep.join([str(decoy), self.path])
        r = self.sv0("coverage", "version")
        self.assertEqual(r.returncode, 7)
        self.assertNotIn(b"decoy", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
