"""Temporary-output validation and atomic publication (NEX-007).

Implements spec §12.5's `VALIDATED -> PUBLISHED` step and the ART-002…004
guarantees from `~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`:

  - ART-002: the host compiler targets a temporary output, never the final
    leaf directly (enforced by callers passing distinct `tmp_path`/
    `final_path`; this module never writes to the final path except via the
    one atomic rename at the end).
  - ART-003: final publication occurs only after temporary-output validation
    — `publish_atomically` always calls `validate_temp_output` first and
    never touches `final_path` if validation raises.
  - ART-004: a failed rebuild preserves the prior output byte-for-byte. This
    falls out of the design rather than needing special-case code: nothing
    in this module ever opens, truncates, or removes `final_path` except the
    single `os.replace` call reached only after successful validation.

A missing, non-regular, empty, or non-executable temporary output is
classified `host-link` (spec §18.1: the host compiler/linker produced no
usable artifact — TOOL-010, AC-012). A failure in the atomic rename itself,
which by construction only happens *after* validation has already confirmed
a good artifact exists, is classified `publish` (exit 8) per the spec's own
phase definition: "temporary artifact valid but final atomic publication
fails."

Run `python3 scripts/native_exe_publish.py --selftest` for the corpus,
including the ART-004 preservation check driven through
`native_exe_fake_cc.py`'s real failure modes.
"""

from __future__ import annotations

import os
import stat

from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_output_lock import OutputLock


def validate_temp_output(path: str) -> None:
    """Raise BuildError(HOST_LINK) unless `path` is a nonempty, executable regular file."""
    if not os.path.lexists(path):
        raise BuildError(DiagnosticPhase.HOST_LINK, f"host compiler produced no output at {path}")
    if os.path.islink(path):
        raise BuildError(DiagnosticPhase.HOST_LINK, f"host compiler output is a symlink, not a regular file: {path}")
    if os.path.isdir(path):
        raise BuildError(DiagnosticPhase.HOST_LINK, f"host compiler produced a directory instead of a file: {path}")
    if not os.path.isfile(path):
        raise BuildError(DiagnosticPhase.HOST_LINK, f"host compiler output is not a regular file: {path}")
    if os.path.getsize(path) == 0:
        raise BuildError(DiagnosticPhase.HOST_LINK, f"host compiler produced an empty output: {path}")
    st = os.stat(path)
    if not (st.st_mode & stat.S_IXUSR):
        raise BuildError(DiagnosticPhase.HOST_LINK, f"host compiler output is not executable: {path}")


def publish_atomically(tmp_path: str, final_path: str) -> None:
    """Validate `tmp_path`, then atomically publish it to `final_path`.

    Never touches `final_path` unless validation of `tmp_path` succeeds
    (ART-003). If `final_path` already exists, its bytes and mode are
    unchanged unless this call fully succeeds (ART-004) — `os.replace` is
    atomic on POSIX when both paths share a filesystem, so the artifact at
    `final_path` is always fully one build's output, never bytes mixed
    from two, with or without the lock below.

    NEX-052b wraps the validate+rename step in an `OutputLock` keyed on
    the exact normalized `final_path` (§22.1: same-output builds serialize
    only at publication, not the whole build) — this only ever affects
    *coordination* between same-output builds (each takes its turn rather
    than racing pointlessly), not the correctness `os.replace` already
    provides on its own.
    """
    with OutputLock(final_path):
        validate_temp_output(tmp_path)
        try:
            os.replace(tmp_path, final_path)
        except OSError as exc:
            raise BuildError(DiagnosticPhase.PUBLISH, f"failed to publish {final_path}: {exc}") from exc


def _selftest() -> int:
    import os as _os
    import shutil
    import subprocess
    import sys
    import tempfile

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")

    def run_fake_cc(mode: str, tmp_out: str) -> None:
        env = dict(os.environ)
        env["SV0_FAKE_CC_MODE"] = mode
        subprocess.run(
            [sys.executable, fake_cc, "program.c", "-o", tmp_out],
            env=env,
            capture_output=True,
            check=False,
        )

    # Case 1: happy path actually publishes and replaces prior content.
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "program.tmp-exe")
        final = os.path.join(td, "program")
        with open(final, "wb") as f:
            f.write(b"OLD\n")
        _os.chmod(final, 0o755)
        run_fake_cc("valid", tmp_out)
        publish_atomically(tmp_out, final)
        if open(final, "rb").read() == b"OLD\n":
            failures.append("happy path: final output was not replaced")
        if _os.path.exists(tmp_out):
            failures.append("happy path: temp output should be consumed by rename")

    # Case 2: ART-004 preservation — every real fake-cc failure mode leaves a
    # pre-existing final output byte-for-byte and mode unchanged.
    for mode in ("zero-no-output", "empty-output", "dir-at-output"):
        with tempfile.TemporaryDirectory() as td:
            tmp_out = os.path.join(td, "program.tmp-exe")
            final = os.path.join(td, "program")
            with open(final, "wb") as f:
                f.write(b"KNOWN_GOOD\n")
            _os.chmod(final, 0o755)
            before_bytes = open(final, "rb").read()
            before_mode = _os.stat(final).st_mode
            run_fake_cc(mode, tmp_out)
            try:
                publish_atomically(tmp_out, final)
                failures.append(f"{mode}: expected BuildError, publish succeeded")
            except BuildError as exc:
                if exc.phase is not DiagnosticPhase.HOST_LINK:
                    failures.append(f"{mode}: expected HOST_LINK phase, got {exc.phase}")
                if exc.exit_code != 6:
                    failures.append(f"{mode}: expected exit 6, got {exc.exit_code}")
            after_bytes = open(final, "rb").read()
            after_mode = _os.stat(final).st_mode
            if after_bytes != before_bytes:
                failures.append(f"{mode}: final output bytes changed after failed publish")
            if after_mode != before_mode:
                failures.append(f"{mode}: final output mode changed after failed publish")
            # dir-at-output leaves a directory at tmp_out; clean it for TemporaryDirectory teardown.
            if _os.path.isdir(tmp_out):
                shutil.rmtree(tmp_out)

    # Case 3: a validated temp output that fails the *rename itself* is classified `publish`, not `host-link`.
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "program.tmp-exe")
        final = os.path.join(td, "program")  # final is a non-empty directory: os.replace(file, dir) raises
        _os.makedirs(final)
        open(os.path.join(final, "keepme"), "w").close()
        run_fake_cc("valid", tmp_out)
        try:
            publish_atomically(tmp_out, final)
            failures.append("rename-failure case: expected BuildError, publish succeeded")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.PUBLISH:
                failures.append(f"rename-failure case: expected PUBLISH phase, got {exc.phase}")
            if exc.exit_code != 8:
                failures.append(f"rename-failure case: expected exit 8, got {exc.exit_code}")
        if not _os.path.isdir(final):
            failures.append("rename-failure case: prior directory output was disturbed")

    # Case 4: validate_temp_output alone rejects a missing path.
    with tempfile.TemporaryDirectory() as td:
        try:
            validate_temp_output(os.path.join(td, "nope"))
            failures.append("missing path: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.HOST_LINK:
                failures.append(f"missing path: expected HOST_LINK, got {exc.phase}")

    if failures:
        for f in failures:
            print(f"native_exe_publish selftest FAIL: {f}")
        return 1

    print("native_exe_publish: selftest OK (4 case groups)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_publish: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
