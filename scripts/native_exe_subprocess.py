"""Direct argv-only subprocess abstraction for the native-executable driver (NEX-009).

Implements TOOL-003 ("host compiler SHALL be invoked directly with an argv
array") and SEC-001 ("no child process SHALL be launched through a shell") from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`. `run_argv` is the
**only** sanctioned way later driver slices (core-compiler invocation,
host-compiler invocation) spawn a child process — it structurally cannot
invoke a shell: `shell` is not a parameter at all, `subprocess.run` is always
called with `shell=False`, and passing a bare string instead of a list of
tokens is a `TypeError`, not a convenience that silently degrades into a
shell command.

This is deliberately a thin wrapper, not a process-management framework —
timeouts and environment sanitization are separate slices (NEX-024) that
build on top of this rather than duplicate it (spec principle 10: "one
implementation of host linking"). `run_argv_cancellable` (NEX-034) is the one
exception, added directly here rather than as a new module, since
cancellation is fundamentally a property of how a child process gets
launched (as its own process-group leader) — implementing SEC-009/REL-003
("cancellation SHALL terminate child process groups... and produce no
success event"): the child is always launched via `start_new_session=True`
(a process-group leader, portable across macOS/Linux) so a cancellation can
terminate the *whole group*, not just the immediate child, and `Cancelled` is
a distinct exception from a normal `CommandResult` — there is no code path
that could mistake a cancelled run for a successful one.

Run `python3 scripts/native_exe_subprocess.py --selftest` for the corpus,
including NEX-009's literal red test: a shell-metacharacter sentinel embedded
in a single argv element never gets created as a side effect.
"""

from __future__ import annotations

import os
import signal
import subprocess
from dataclasses import dataclass


class SubprocessError(Exception):
    """Raised for a usage error or unrecoverable process-launch failure."""


class Cancelled(SubprocessError):
    """Raised when a cancellable run was terminated before the child exited
    naturally — never returned as a CommandResult, so a cancelled run can
    never be mistaken for a successful (or even a failed-but-completed) one.
    """


@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


def run_argv(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    timeout: float | None = None,
) -> CommandResult:
    """Run `argv` directly — never through a shell. `argv` must be a non-empty
    list of strings; a bare string is rejected outright rather than silently
    becoming a shell command line.
    """
    if isinstance(argv, str):
        raise TypeError(
            "run_argv requires a list of argv tokens, never a shell command string "
            f"(got a str: {argv!r})"
        )
    if not argv or not all(isinstance(tok, str) for tok in argv):
        raise TypeError(f"argv must be a non-empty list[str], got {argv!r}")

    try:
        proc = subprocess.run(
            list(argv),
            shell=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise SubprocessError(f"executable not found: {argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise SubprocessError(f"timed out after {timeout}s: {argv}") from exc

    return CommandResult(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def _terminate_process_group(proc: subprocess.Popen, grace_period: float) -> None:
    """SIGTERM the whole process group, escalating to SIGKILL after
    `grace_period` seconds if it hasn't exited (SEC-009).
    """
    try:
        pgid = os.getpgid(proc.pid)
    except ProcessLookupError:
        return
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=grace_period)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()


def run_argv_cancellable(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    cancel_event=None,
    poll_interval: float = 0.05,
    grace_period: float = 2.0,
) -> CommandResult:
    """Like `run_argv`, but launches the child as its own process-group
    leader and can be cancelled mid-flight: if `cancel_event` (a
    `threading.Event`) becomes set, or this call itself receives a
    `KeyboardInterrupt`, before the child exits naturally, the *entire
    process group* is terminated and `Cancelled` is raised — never a
    `CommandResult` (REL-003: "signals/cancellation SHALL produce no
    success event").
    """
    if isinstance(argv, str):
        raise TypeError(
            "run_argv_cancellable requires a list of argv tokens, never a shell command string "
            f"(got a str: {argv!r})"
        )
    if not argv or not all(isinstance(tok, str) for tok in argv):
        raise TypeError(f"argv must be a non-empty list[str], got {argv!r}")

    try:
        proc = subprocess.Popen(
            list(argv),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=cwd,
            start_new_session=True,  # process-group leader; portable macOS/Linux
        )
    except FileNotFoundError as exc:
        raise SubprocessError(f"executable not found: {argv[0]}") from exc

    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                _terminate_process_group(proc, grace_period)
                raise Cancelled(f"cancelled before exit: {argv}")
            try:
                stdout, stderr = proc.communicate(timeout=poll_interval)
                return CommandResult(returncode=proc.returncode, stdout=stdout, stderr=stderr)
            except subprocess.TimeoutExpired:
                continue
    except KeyboardInterrupt:
        _terminate_process_group(proc, grace_period)
        raise Cancelled(f"cancelled by KeyboardInterrupt: {argv}") from None


def _selftest() -> int:
    import os
    import sys
    import tempfile

    failures: list[str] = []

    # Case 1: a bare string is rejected, never silently treated as a shell command.
    try:
        run_argv("echo hello")  # type: ignore[arg-type]
        failures.append("expected TypeError for a bare string argv, got none")
    except TypeError:
        pass

    # Case 2: empty argv is rejected.
    try:
        run_argv([])
        failures.append("expected TypeError for empty argv, got none")
    except TypeError:
        pass

    # Case 3: a normal argv round-trips correctly (sanity check on the happy path).
    r = run_argv([sys.executable, "-c", "import sys; print(sys.argv[1]); sys.exit(0)", "hello"])
    if r.returncode != 0 or r.stdout.strip() != "hello":
        failures.append(f"happy path: rc={r.returncode} stdout={r.stdout!r}")

    # Case 4 (NEX-009's literal red test): a shell-metacharacter payload passed
    # as ONE argv element never gets interpreted — the sentinel is never created,
    # and the receiving process sees the string byte-for-byte, unsplit.
    with tempfile.TemporaryDirectory() as td:
        sentinel = os.path.join(td, "SHOULD_NOT_EXIST")
        hostile = f"; $(touch {sentinel}) && `touch {sentinel}` | touch {sentinel} > {sentinel}"
        r = run_argv([sys.executable, "-c", "import sys; print(sys.argv[1])", hostile])
        if os.path.exists(sentinel):
            failures.append("shell-metacharacter argv element was interpreted (sentinel created)")
        if r.stdout.strip() != hostile:
            failures.append(f"hostile argv element was not passed through literally: {r.stdout!r}")

    # Case 5: a missing executable raises SubprocessError, not a bare OSError leak.
    try:
        run_argv(["/definitely/not/a/real/executable/path"])
        failures.append("expected SubprocessError for a missing executable, got none")
    except SubprocessError:
        pass

    # Case 6: stdout and stderr never mix into one stream.
    r = run_argv([sys.executable, "-c", "import sys; print('OUT'); print('ERR', file=sys.stderr)"])
    if "ERR" in r.stdout or "OUT" in r.stderr:
        failures.append(f"stdout/stderr channels leaked into each other: stdout={r.stdout!r} stderr={r.stderr!r}")

    # Case 7 (NEX-034, SEC-009/REL-003): a cancelled run against a real
    # hanging compiler (native_exe_fake_cc.py's own `hang` mode) raises
    # Cancelled promptly, never a CommandResult.
    import threading
    import time

    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")
    env = dict(os.environ)
    env["SV0_FAKE_CC_MODE"] = "hang"

    cancel_event = threading.Event()

    def cancel_soon() -> None:
        time.sleep(0.3)
        cancel_event.set()

    canceller = threading.Thread(target=cancel_soon)
    started_at = time.monotonic()
    canceller.start()
    try:
        run_argv_cancellable([fake_cc, "program.c", "-o", "out"], env=env, cancel_event=cancel_event)
        failures.append("case7: expected Cancelled, run completed normally")
    except Cancelled:
        elapsed = time.monotonic() - started_at
        if elapsed > 5.0:
            failures.append(f"case7: cancellation took too long ({elapsed:.1f}s) -- polling loop may be broken")
    finally:
        canceller.join()

    # Case 8: cancellation kills the WHOLE process group, not just the
    # immediate child -- a wrapper shell spawns a background grandchild sleep,
    # and both must be gone after cancellation.
    with tempfile.TemporaryDirectory() as td:
        marker = os.path.join(td, "still_running")
        wrapper = os.path.join(td, "spawn_and_hang.sh")
        with open(wrapper, "w", encoding="utf-8") as f:
            f.write(
                "#!/bin/sh\n"
                # touch immediately, THEN loop -- guarantees the marker exists
                # before cancellation can possibly fire, regardless of scheduling.
                f"(touch {marker}; while true; do sleep 0.1; touch {marker}; done) &\n"
                "CHILD=$!\n"
                "wait $CHILD\n"
            )
        os.chmod(wrapper, os.stat(wrapper).st_mode | 0o111)

        cancel_event2 = threading.Event()

        def cancel_soon2() -> None:
            time.sleep(0.5)
            cancel_event2.set()

        canceller2 = threading.Thread(target=cancel_soon2)
        canceller2.start()
        try:
            run_argv_cancellable([wrapper], cancel_event=cancel_event2)
            failures.append("case8: expected Cancelled, run completed normally")
        except Cancelled:
            pass
        finally:
            canceller2.join()

        # Confirm the marker actually got created before checking anything
        # about it -- a silently-skipped check here would vacuously pass.
        if not os.path.isfile(marker):
            failures.append("case8: marker was never created -- test setup is broken, not a real pass")
        else:
            mtime_after_cancel = os.path.getmtime(marker)
            time.sleep(0.5)
            if os.path.getmtime(marker) != mtime_after_cancel:
                failures.append("case8: background grandchild process is still running after cancellation")

    # Case 9: a normal (never-cancelled) run still completes and returns a
    # real CommandResult -- cancellation support doesn't break the happy path.
    r9 = run_argv_cancellable([sys.executable, "-c", "print('still works')"])
    if r9.returncode != 0 or "still works" not in r9.stdout:
        failures.append(f"case9: uncancelled run misbehaved: rc={r9.returncode} stdout={r9.stdout!r}")

    if failures:
        for f in failures:
            print(f"native_exe_subprocess selftest FAIL: {f}")
        return 1

    print("native_exe_subprocess: selftest OK (9 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_subprocess: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
