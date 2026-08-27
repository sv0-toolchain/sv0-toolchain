"""Migration-shim interface to the self-hosted sv0c core compiler (NEX-011).

**What this is not.** The stable, reentrant core-compiler request ABI that
AE-008/REL-004 (`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`)
ultimately require does not exist yet, and this module does not create it.
sv0 (the language) has no argv/CLI-args host function today — `sv0_runtime.h`/
`.c` expose no such symbol, and the native mega-TU compiler's own CLI entry
point (`build/megaTU-native-main.sv0`, synthesized by
`scripts/build-sv0-megatu-native.sh`) reads its input path from a single
global file, `/tmp/.sv0_drv_path`, because that is literally the only channel
a self-hosted sv0 program has for receiving external input today (besides
reading files at fixed, known paths). Building the real fix means adding a
new host function across the resolver/checker/C-lowering/runtime (and
`sv0doc`, which owns language capabilities) — a compiler feature, not a
driver-layer change, and deliberately out of scope for this slice.

**What this is.** Spec §22.2's explicitly sanctioned interim: "If F0
temporarily serializes legacy core invocations behind a lock, the lock is a
migration mechanism, not R0 completion." `CoreCompilerClient` wraps every
control-file write / compiler invocation / control-file reset in one POSIX
file lock, so two calls made *through this module* are serialized rather than
racing to overwrite each other's request (the concrete bug class REL-004
names: "concurrent invocations can overwrite one another's requested source
path").

**What this does not protect against.** Anything that touches
`/tmp/.sv0_drv_path` *without* going through this module — other
`scripts/sv0` subcommands, the self-host loop, ad-hoc build scripts — is not
part of this lock's protocol and can still race against it. This is exactly
why `[[feedback_drv_path_reset]]` and the project's own build-script comments
warn never to run a build-native script concurrently with a pre-push
`sv0 test`. This module narrows the unsafe window; it does not close it.

Run `python3 scripts/native_exe_core_compiler.py --selftest` for the corpus,
including NEX-011's literal red test: two concurrent requests cross-contaminate
without the lock, and are correctly isolated with it.
"""

from __future__ import annotations

import fcntl
import os

from native_exe_subprocess import CommandResult, run_argv

DEFAULT_CONTROL_FILE = "/tmp/.sv0_drv_path"
DEFAULT_LOCK_FILE = "/tmp/.sv0_drv_path.lock"


class CoreCompilerRequest:
    """Builders for the legacy control-file's documented request formats
    (spec-external — see `scripts/build-sv0-megatu-native.sh` and
    `scripts/sv0`'s `run_compile`/`run_emit_verified` for the format this
    mirrors exactly, since the driver and the workspace script must agree on
    the same request encoding by construction).
    """

    @staticmethod
    def file(abs_path: str) -> str:
        return abs_path

    @staticmethod
    def disabled(abs_path: str) -> str:
        return f"--disabled {abs_path}"

    @staticmethod
    def verified(proof_path: str, abs_path: str) -> str:
        return f"--verified {proof_path} {abs_path}"

    @staticmethod
    def project(dir_path: str) -> str:
        return f"--project {dir_path}"


class CoreCompilerClient:
    """Serializes access to one legacy control-file-driven core compiler binary."""

    def __init__(
        self,
        compiler_path: str,
        control_file: str = DEFAULT_CONTROL_FILE,
        lock_file: str = DEFAULT_LOCK_FILE,
    ) -> None:
        self.compiler_path = compiler_path
        self.control_file = control_file
        self.lock_file = lock_file

    def invoke(self, control_value: str) -> CommandResult:
        """Write `control_value`, run the compiler, always reset to empty —
        all under one exclusive lock scoped to `self.lock_file`.
        """
        lock_fd = os.open(self.lock_file, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            try:
                self._write_control(control_value)
                return run_argv([self.compiler_path])
            finally:
                # Always reset, even on failure — matches [[feedback_drv_path_reset]]
                # and prevents a stale request leaking to the next caller.
                self._write_control("")
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _write_control(self, value: str) -> None:
        with open(self.control_file, "w", encoding="utf-8") as f:
            f.write(value)
            if value and not value.endswith("\n"):
                f.write("\n")


def _selftest() -> int:
    import os as _os
    import sys
    import tempfile
    import threading
    import time

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        control_file = _os.path.join(td, "drv_path")
        lock_file = _os.path.join(td, "drv_path.lock")

        # A fake "core compiler": read the control file, sleep briefly (widens
        # the race window deterministically), then echo the content it saw.
        # A real executable (shebang + chmod +x) so it stands in for
        # `build/sv0-megatu-compiler-native` as a single argv[0] path, exactly
        # what CoreCompilerClient.invoke() expects.
        fake_compiler = _os.path.join(td, "fake_core_compiler.py")
        with open(fake_compiler, "w", encoding="utf-8") as f:
            f.write(
                f"#!{sys.executable}\n"
                "import sys, time\n"
                f"with open({control_file!r}) as cf:\n"
                "    seen = cf.read()\n"
                "time.sleep(0.05)\n"
                "sys.stdout.write(seen)\n"
            )
        _os.chmod(fake_compiler, 0o755)
        compiler_argv0 = [fake_compiler]

        def unlocked_worker(value: str, results: dict, key: str) -> None:
            with open(control_file, "w", encoding="utf-8") as f:
                f.write(value)
            r = run_argv(compiler_argv0)
            results[key] = r.stdout

        # Case 1 (red, "before"): without the lock, two concurrent requests can
        # cross-contaminate — the second writer can clobber the first reader's
        # input before the fake compiler gets to read it.
        results: dict = {}
        t1 = threading.Thread(target=unlocked_worker, args=("REQUEST_A\n", results, "a"))
        t2 = threading.Thread(target=unlocked_worker, args=("REQUEST_B\n", results, "b"))
        t1.start()
        time.sleep(0.01)  # ensure t1 has written before t2 starts writing
        t2.start()
        t1.join()
        t2.join()
        if results.get("a") == "REQUEST_A\n" and results.get("b") == "REQUEST_B\n":
            failures.append(
                "expected the unlocked path to demonstrate cross-contamination at least "
                f"once in this run, but both requests came back clean: {results}"
            )

        # Case 2 (green, "after"): through CoreCompilerClient.invoke() — the
        # real production code path, not a test-only reimplementation — N
        # concurrent requests are always correctly isolated.
        client = CoreCompilerClient(fake_compiler, control_file=control_file, lock_file=lock_file)

        locked_results: dict = {}
        lock_threads = []
        expected = {}
        for i in range(6):
            value = f"REQUEST_{i}\n"
            expected[i] = value

            def worker(i=i, value=value):
                locked_results[i] = client.invoke(value).stdout

            th = threading.Thread(target=worker)
            lock_threads.append(th)
        for th in lock_threads:
            th.start()
        for th in lock_threads:
            th.join()

        for i, expected_value in expected.items():
            if locked_results.get(i) != expected_value:
                failures.append(
                    f"locked request {i}: expected {expected_value!r}, got {locked_results.get(i)!r} "
                    "(cross-contamination under the lock)"
                )

        # Case 3: CoreCompilerRequest builders match the documented control-file formats.
        if CoreCompilerRequest.file("/abs/hello.sv0") != "/abs/hello.sv0":
            failures.append("file() request format mismatch")
        if CoreCompilerRequest.disabled("/abs/hello.sv0") != "--disabled /abs/hello.sv0":
            failures.append("disabled() request format mismatch")
        if CoreCompilerRequest.verified("/tmp/proof", "/abs/hello.sv0") != "--verified /tmp/proof /abs/hello.sv0":
            failures.append("verified() request format mismatch")
        if CoreCompilerRequest.project("/abs/proj") != "--project /abs/proj":
            failures.append("project() request format mismatch")

        # Case 4: CoreCompilerClient itself always resets the control file to empty.
        client.invoke("FINAL_CHECK\n")
        with open(control_file, encoding="utf-8") as f:
            leftover = f.read()
        if leftover != "":
            failures.append(f"control file not reset to empty after invoke(): {leftover!r}")

    if failures:
        for f in failures:
            print(f"native_exe_core_compiler selftest FAIL: {f}")
        return 1

    print("native_exe_core_compiler: selftest OK (4 case groups)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_core_compiler: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
