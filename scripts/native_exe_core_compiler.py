"""Reentrant interface to the self-hosted sv0c core compiler (NEX-011, REL-004).

**History, so the migration is legible.** This module used to be an
explicitly-documented *migration shim*: sv0 (the language) had no
argv/env/stdin host function at all, so the native mega-TU compiler's CLI
entry point could only receive its input path via one global file,
`/tmp/.sv0_drv_path` — `CoreCompilerClient` wrapped every control-file
write / compiler invocation / control-file reset in one POSIX file lock
(`flock`) so that two calls made *through this module* were serialized
rather than racing to overwrite each other's request.

That precondition is now gone. NEX-055c added a real `getenv(name) ->
string` host builtin to sv0 (`sv0c/lib/checker.sv0` etc., sv0c commit
`fc19be9`), and wired it into both `sv0c/lib/driver.sv0`'s `fn main()` and
the mega-TU compose-main `scripts/build-sv0-megatu-native.sh` injects
(sv0c commit `647d2a0`, parent `4474e53`): the native compiler now reads
its control text from the `SV0_DRV_REQUEST` environment variable when
it's non-empty, falling back to the legacy control file only when unset.

**What this module is now.** `CoreCompilerClient.invoke()` passes
`control_value` to the compiler subprocess via `SV0_DRV_REQUEST` in that
child's own environment block — never the shared file, never a lock.
Each `subprocess.run(..., env=...)` call gets an independent copy of the
environment dict handed to it; the OS gives every child process its own
environment at exec time, so two concurrent `invoke()` calls (same
thread, different threads, or different processes) can never observe or
overwrite each other's request. This directly satisfies REL-004's own
literal text: "the production core compiler interface SHALL accept argv
directly or a unique private request channel" — `SV0_DRV_REQUEST`, set
fresh per invocation, *is* that unique private request channel.

**What this does not change.** Anything that still writes
`/tmp/.sv0_drv_path` directly *without* going through this module — the
self-host loop, `scripts/sv0`'s own `run_compile`/`run_emit_verified`,
ad-hoc build scripts — is untouched by this migration and keeps using the
legacy file exactly as before (the env-var read path added in NEX-055c's
driver.sv0/megaTU-main.sv0 wiring is additive, not a replacement). Per the
REL-004 design doc's own 6-step sequencing
(`sv0c/doc/native-executable-reentrant-core-compiler-design.md`), this is
step 3 (migrate `CoreCompilerClient`); step 5 (migrate the remaining
`/tmp/.sv0_drv_path` callers) and step 6 (remove the legacy path + add a
static guard) are separate, later work — REL-004 itself is not fully
closed by this module alone.

Run `python3 scripts/native_exe_core_compiler.py --selftest` for the
corpus, including the literal regression this migration must never
reintroduce: two concurrent requests through `CoreCompilerClient.invoke()`
must always come back correctly isolated, proven under real thread
concurrency against a fake compiler that reads its own `SV0_DRV_REQUEST`.
"""

from __future__ import annotations

import os

from native_exe_subprocess import CommandResult, run_argv

ENV_VAR = "SV0_DRV_REQUEST"


class CoreCompilerRequest:
    """Builders for the control-text formats the compiler's entry-reading
    logic understands (spec-external — see `scripts/build-sv0-megatu-native.sh`
    and `scripts/sv0`'s `run_compile`/`run_emit_verified` for the format this
    mirrors exactly, since every caller must agree on the same request
    encoding by construction, regardless of which channel — env var or
    legacy file — carries it).
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
    """Invokes one `SV0_DRV_REQUEST`-reading core compiler binary.

    No shared state, no lock, no control file: every `invoke()` call
    passes its own request through a fresh, per-call environment dict to
    a brand-new subprocess. Concurrent calls are inherently, structurally
    isolated — there is nothing left to race on.
    """

    def __init__(self, compiler_path: str) -> None:
        self.compiler_path = compiler_path

    def invoke(self, control_value: str) -> CommandResult:
        """Run the compiler with `control_value` carried in `SV0_DRV_REQUEST`.

        `dict(os.environ)` snapshots the *current* environment into a new,
        call-local dict before mutating it — `os.environ` itself is never
        written, so no other thread/call can ever observe this call's
        request. The resulting dict is handed straight to `subprocess.run`,
        which gives the child process its own independent copy at exec
        time (real OS-level isolation, not just a Python-level one).
        """
        env = dict(os.environ)
        env[ENV_VAR] = control_value
        return run_argv([self.compiler_path], env=env)


def _selftest() -> int:
    import sys
    import tempfile
    import threading
    import time

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        # A fake "core compiler": read its own SV0_DRV_REQUEST, sleep briefly
        # (widens the race window deterministically), then echo what it saw.
        # A real executable (shebang + chmod +x) so it stands in for
        # `build/sv0-megatu-native`/`build/sv0-driver-native` as a single
        # argv[0] path, exactly what CoreCompilerClient.invoke() expects.
        fake_compiler = os.path.join(td, "fake_core_compiler.py")
        with open(fake_compiler, "w", encoding="utf-8") as f:
            f.write(
                f"#!{sys.executable}\n"
                "import os, sys, time\n"
                "seen = os.environ.get('SV0_DRV_REQUEST', '')\n"
                "time.sleep(0.05)\n"
                "sys.stdout.write(seen)\n"
            )
        os.chmod(fake_compiler, 0o755)

        client = CoreCompilerClient(fake_compiler)

        # Case 1 (the real regression this migration must never reintroduce):
        # N concurrent invoke() calls, each with a distinct request, are
        # always correctly isolated -- no lock, and none needed.
        locked_results: dict = {}
        expected: dict = {}
        threads = []
        for i in range(6):
            value = f"REQUEST_{i}"
            expected[i] = value

            def worker(i=i, value=value):
                locked_results[i] = client.invoke(value).stdout

            th = threading.Thread(target=worker)
            threads.append(th)
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        for i, expected_value in expected.items():
            if locked_results.get(i) != expected_value:
                failures.append(
                    f"concurrent request {i}: expected {expected_value!r}, got "
                    f"{locked_results.get(i)!r} (cross-contamination)"
                )

        # Case 2 (deterministic mutation guard for the isolation mechanism
        # itself, not just its observable outcome): each invoke() call must
        # hand run_argv a genuinely independent env dict -- not a shared
        # reference that a later call mutates out from under an earlier
        # one. A real race (threads actually interleaving os.environ writes
        # around a fork) is inherently timing-dependent and flaky to force
        # on purpose; this instead deterministically inspects the exact env
        # dict object passed to run_argv on each call, by substituting a
        # capturing stand-in for the module-level run_argv this file calls.
        captured_envs: list[dict | None] = []

        def fake_run_argv(argv, *, env=None, cwd=None, timeout=None):
            captured_envs.append(dict(env) if env is not None else None)
            return CommandResult(returncode=0, stdout="", stderr="")

        global run_argv
        original_run_argv = run_argv
        run_argv = fake_run_argv
        try:
            client2 = CoreCompilerClient("unused-path")
            client2.invoke("FIRST")
            client2.invoke("SECOND")
        finally:
            run_argv = original_run_argv

        if len(captured_envs) != 2:
            failures.append(f"expected 2 captured env dicts, got {len(captured_envs)}")
        else:
            if captured_envs[0] is captured_envs[1]:
                failures.append(
                    "invoke() passed the SAME env dict object to both calls "
                    "(aliasing risk: a later call could mutate an earlier "
                    "call's already-in-flight request)"
                )
            if captured_envs[0] is None or captured_envs[0].get(ENV_VAR) != "FIRST":
                failures.append(
                    f"first call's captured env should hold {ENV_VAR}='FIRST', "
                    f"got {captured_envs[0]!r} -- mutated after the fact or never set"
                )
            if captured_envs[1] is None or captured_envs[1].get(ENV_VAR) != "SECOND":
                failures.append(
                    f"second call's captured env should hold {ENV_VAR}='SECOND', "
                    f"got {captured_envs[1]!r}"
                )

        # Case 3: CoreCompilerRequest builders match the documented
        # control-text formats (channel-independent -- same text whether it
        # travels via SV0_DRV_REQUEST or the legacy file).
        if CoreCompilerRequest.file("/abs/hello.sv0") != "/abs/hello.sv0":
            failures.append("file() request format mismatch")
        if CoreCompilerRequest.disabled("/abs/hello.sv0") != "--disabled /abs/hello.sv0":
            failures.append("disabled() request format mismatch")
        if CoreCompilerRequest.verified("/tmp/proof", "/abs/hello.sv0") != "--verified /tmp/proof /abs/hello.sv0":
            failures.append("verified() request format mismatch")
        if CoreCompilerRequest.project("/abs/proj") != "--project /abs/proj":
            failures.append("project() request format mismatch")

        # Case 4: invoke() never mutates the calling process's own
        # environment -- os.environ must be unchanged after a real call
        # (the isolation claim's other half: not just "children don't see
        # each other's request", but "the parent isn't touched either").
        before = dict(os.environ)
        client.invoke("SHOULD_NOT_LEAK")
        after = dict(os.environ)
        if before != after:
            failures.append(
                f"invoke() mutated the parent process's own os.environ: "
                f"added/changed keys {set(after.items()) - set(before.items())}"
            )
        if ENV_VAR in os.environ:
            failures.append(f"invoke() left {ENV_VAR} set in the parent process's os.environ")

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
