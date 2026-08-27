"""Unique, private scratch-directory lifecycle for the native-executable driver (NEX-008).

Implements ART-009…010 (`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`
§12.3, §19.3, §22.5): every build invocation gets its own scratch directory —
unpredictable leaf name, owner-only permissions, and cleanup that can only
ever remove the exact directory this instance created. It never derives a
path to delete from a glob, a prefix scan, or anything other than the value
it returned from its own `mkdtemp` call (SEC-005: "cleanup shall never
recursively delete outside exact owned scratch").

`ScratchDir` is a context manager so ordinary driver code gets cleanup for
free; `cleanup()` is also safe to call directly and is idempotent, and
refuses to delete a path that doesn't carry this module's own prefix even if
`.path` were ever set to something unexpected (defense in depth, not the
primary safety mechanism — the primary mechanism is that we only ever
`rmtree` the exact path `mkdtemp` handed back).

Run `python3 scripts/native_exe_scratch.py --selftest` for the corpus,
including NEX-008's literal red test: a neighbor scratch dir's sentinel file
survives cleanup of an unrelated scratch dir.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile

SCRATCH_PREFIX = "sv0c-native-"


class ScratchError(Exception):
    """Raised when asked to clean up a path that doesn't look like an owned scratch dir."""


class ScratchDir:
    """One private, unique scratch directory for a single build invocation."""

    def __init__(self, base_dir: str | None = None) -> None:
        self._base_dir = base_dir if base_dir is not None else tempfile.gettempdir()
        self.path: str | None = None

    def __enter__(self) -> "ScratchDir":
        self.path = tempfile.mkdtemp(prefix=SCRATCH_PREFIX, dir=self._base_dir)
        # mkdtemp already creates with 0700 on POSIX; assert it rather than trust it silently (ART-009/SEC-004).
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        if mode & 0o077:
            os.chmod(self.path, 0o700)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Remove exactly this instance's scratch directory. Idempotent."""
        if self.path is None:
            return
        path = self.path
        basename = os.path.basename(path)
        if not basename.startswith(SCRATCH_PREFIX):
            raise ScratchError(
                f"refusing to delete a path that doesn't carry the owned-scratch prefix: {path}"
            )
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        self.path = None


def _selftest() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as base:
        # Case 1: created directory exists with owner-only permissions.
        with ScratchDir(base_dir=base) as sd:
            if sd.path is None or not os.path.isdir(sd.path):
                failures.append("scratch dir was not created")
            else:
                mode = stat.S_IMODE(os.stat(sd.path).st_mode)
                if mode & 0o077:
                    failures.append(f"scratch dir is not owner-only: {oct(mode)}")
                if not os.path.basename(sd.path).startswith(SCRATCH_PREFIX):
                    failures.append(f"scratch dir missing prefix: {sd.path}")
            path_after_enter = sd.path
        if os.path.exists(path_after_enter):
            failures.append("scratch dir survived context-manager exit")

        # Case 2: two instances get distinct, unpredictable paths.
        a = ScratchDir(base_dir=base)
        b = ScratchDir(base_dir=base)
        with a, b:
            if a.path == b.path:
                failures.append("two scratch dirs collided on the same path")

        # Case 3 (NEX-008's red test): cleaning up one scratch dir never
        # touches a neighbor's contents, including a sentinel file.
        neighbor = ScratchDir(base_dir=base)
        with neighbor:
            sentinel = os.path.join(neighbor.path, "SHOULD_NOT_BE_TOUCHED")
            with open(sentinel, "w", encoding="utf-8") as f:
                f.write("neighbor data\n")

            victim = ScratchDir(base_dir=base)
            with victim:
                pass  # cleaned up by victim's own __exit__ here

            if not os.path.isfile(sentinel):
                failures.append("neighbor sentinel did not survive an unrelated scratch dir's cleanup")

        # Case 4: cleanup() is idempotent.
        sd = ScratchDir(base_dir=base)
        with sd:
            sd_path = sd.path
        try:
            sd.cleanup()
        except Exception as exc:  # noqa: BLE001 - selftest wants to see any failure
            failures.append(f"cleanup() was not idempotent: {exc!r}")
        if os.path.exists(sd_path):
            failures.append("path should already be gone after first cleanup")

        # Case 5: refuses to delete a path lacking the owned prefix, even if
        # something set .path to it directly (defense in depth).
        rogue = ScratchDir(base_dir=base)
        rogue_target = os.path.join(base, "not-ours")
        os.makedirs(rogue_target)
        rogue.path = rogue_target
        try:
            rogue.cleanup()
            failures.append("expected ScratchError deleting a non-prefixed path, none raised")
        except ScratchError:
            pass
        if not os.path.isdir(rogue_target):
            failures.append("rogue target should not have been deleted")

    if failures:
        for f in failures:
            print(f"native_exe_scratch selftest FAIL: {f}")
        return 1

    print("native_exe_scratch: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_scratch: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
