"""Same-output publication lock/token protocol (NEX-052a).

Implements ART-013/REL-002/§22.5
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "any lock
file SHALL be adjacent to or deterministically associated with the exact
normalized output, use an ownership/token protocol, and have stale-lock
recovery. A lock SHALL not be based only on the input basename."

Note on what this actually adds: `native_exe_publish.publish_atomically`'s
`os.replace` is already an atomic POSIX rename, so a same-output race can
never produce a torn or byte-mixed artifact at the destination path even
with zero locking — whichever build's `os.replace` call lands last simply
wins outright (§22.1's explicitly-allowed "equivalent last-successful-
publication rule"). What this lock protocol adds on top is coordination:
an ownership/token identity for "who is currently publishing to this
output," and stale-lock recovery so a crashed builder's lock doesn't wedge
every future build targeting that same path forever.

The lock path is derived from a hash of the exact normalized ABSOLUTE
output path (never just its basename, per §22.5's explicit prohibition),
placed in a fixed lock directory next to the output's own parent so two
different output paths that happen to share a basename never collide.

Run `python3 scripts/native_exe_output_lock.py --selftest` for the corpus.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import uuid

_STALE_THRESHOLD_SECONDS = 300  # 5 minutes; a build this slow is itself a red flag.


def lock_path_for(output_path: str) -> str:
    """Derive the lock file path from the exact normalized ABSOLUTE output
    path (never just its basename, per §22.5). Placed beside the output's
    own parent directory as a dotfile, so it's deterministically
    associated with this one output path.
    """
    abs_output = os.path.abspath(output_path)
    digest = hashlib.sha256(abs_output.encode("utf-8")).hexdigest()[:16]
    parent = os.path.dirname(abs_output)
    basename = os.path.basename(abs_output)
    return os.path.join(parent, f".{basename}.{digest}.sv0-native-lock")


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # Exists, owned by someone else -- still alive as far as we're concerned.
        return True
    return True


class OutputLock:
    """A single ownership/token lock for one normalized output path.

    Usage: `with OutputLock(output_path) as token: ...` -- acquires on
    enter (reclaiming a stale lock first if one is found), releases on
    exit. Raises `TimeoutError` if a live lock is held by another owner
    and doesn't clear within `timeout` seconds.
    """

    def __init__(self, output_path: str, timeout: float = 30.0, poll_interval: float = 0.05):
        self.output_path = output_path
        self.lock_path = lock_path_for(output_path)
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.token = uuid.uuid4().hex

    def _read_owner(self) -> dict | None:
        try:
            with open(self.lock_path, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _is_stale(self, owner: dict) -> bool:
        if time.time() - owner.get("acquired_at", 0) > _STALE_THRESHOLD_SECONDS:
            return True
        pid = owner.get("pid")
        if pid is not None and not _pid_is_alive(pid):
            return True
        return False

    def acquire(self) -> str:
        deadline = time.time() + self.timeout
        while True:
            owner = self._read_owner()
            if owner is not None and not self._is_stale(owner):
                if time.time() >= deadline:
                    raise TimeoutError(
                        f"output lock for {self.output_path!r} held by pid={owner.get('pid')} "
                        f"token={owner.get('token')!r}, did not clear within {self.timeout}s"
                    )
                time.sleep(self.poll_interval)
                continue

            if owner is not None:
                # A known-stale lock: remove it first (best effort -- if a
                # concurrent reclaimer races us here, the O_EXCL create
                # below is the actual exclusivity guarantee, not this).
                try:
                    os.remove(self.lock_path)
                except FileNotFoundError:
                    pass

            # The real mutual-exclusion primitive: O_CREAT|O_EXCL fails
            # with FileExistsError if ANY other process/thread already
            # created this path first, unlike a rename-based scheme (POSIX
            # rename silently overwrites an existing destination, so it
            # cannot by itself prevent two racers from both "succeeding").
            payload = json.dumps({"token": self.token, "pid": os.getpid(), "acquired_at": time.time()})
            try:
                fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                # Someone else won the race (or a live lock reappeared);
                # loop and re-evaluate from the top.
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
            return self.token

    def release(self) -> None:
        owner = self._read_owner()
        if owner is not None and owner.get("token") == self.token:
            try:
                os.remove(self.lock_path)
            except FileNotFoundError:
                pass

    def __enter__(self) -> str:
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()


def _selftest() -> int:
    import tempfile
    import threading

    failures: list[str] = []

    # Case 1: lock path is derived from the full path, not just the basename
    # (two different dirs, same basename, must get different lock paths).
    p1 = lock_path_for("/a/dir/one/program")
    p2 = lock_path_for("/a/dir/two/program")
    if p1 == p2:
        failures.append("lock_path_for collided for two different output paths sharing a basename")

    # Case 2: acquire/release round-trips cleanly; the lock file is gone after release.
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program")
        lock = OutputLock(out)
        with lock as token:
            if not os.path.isfile(lock.lock_path):
                failures.append("case2: lock file was not created on acquire")
            if not token:
                failures.append("case2: acquire returned an empty token")
        if os.path.exists(lock.lock_path):
            failures.append("case2: lock file was not removed on release")

    # Case 3: a live lock (a real, alive PID -- this test process itself)
    # blocks a second acquirer until timeout.
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program")
        holder = OutputLock(out)
        holder.acquire()
        try:
            contender = OutputLock(out, timeout=0.2, poll_interval=0.02)
            try:
                contender.acquire()
                failures.append("case3: a second acquirer succeeded against a live lock")
            except TimeoutError:
                pass
        finally:
            holder.release()

    # Case 4: a STALE lock (dead PID) is reclaimed, not honored forever.
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program")
        lock_path = lock_path_for(out)
        # A PID essentially guaranteed not to exist.
        dead_payload = json.dumps({"token": "dead-token", "pid": 999999, "acquired_at": time.time()})
        with open(lock_path, "w", encoding="utf-8") as f:
            f.write(dead_payload)
        reclaimer = OutputLock(out, timeout=2.0)
        token = reclaimer.acquire()
        if token == "dead-token":
            failures.append("case4: reclaimer did not actually claim a new token")
        reclaimer.release()

    # Case 5: two threads racing for the SAME output only ever have one
    # holder at a time -- proven with a shared counter that must never
    # exceed 1 while "held".
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program")
        concurrent_holders = [0]
        max_concurrent = [0]
        race_lock = threading.Lock()

        def worker():
            with OutputLock(out, timeout=5.0, poll_interval=0.01):
                with race_lock:
                    concurrent_holders[0] += 1
                    max_concurrent[0] = max(max_concurrent[0], concurrent_holders[0])
                time.sleep(0.05)
                with race_lock:
                    concurrent_holders[0] -= 1

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if max_concurrent[0] != 1:
            failures.append(f"case5: observed {max_concurrent[0]} concurrent holders, expected exactly 1")

    if failures:
        for f in failures:
            print(f"native_exe_output_lock selftest FAIL: {f}")
        return 1

    print("native_exe_output_lock: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_output_lock: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
