"""File-mode input shape validation (CLI-008).

Implements CLI-008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §11.3): "File
mode SHALL require a regular readable `.sv0` file." Red test: "Missing,
directory, FIFO, wrong-extension tests."

This is a distinct concern from `native_exe_entry_scan.py`'s job (ENTRY-001/
004: does the *content* declare exactly one `fn main`) -- that module's
`validate_entry_exists` calls `open(input_path, encoding="utf-8").read()`
directly, which raises a raw, undiagnosed `FileNotFoundError`/`IsADirectoryError`/
`PermissionError` instead of a clean `BuildError` when the path itself is
missing, a directory, a FIFO, unreadable, or not a `.sv0` file at all --
this module's `validate_file_input_shape` runs first, in `build_native_executable`'s
pipeline, to turn every one of those into a clean `BuildError(INPUT)` (exit
3, the input-class phase, distinct from `ENTRY`'s content-validation phase)
before any file content is ever read. Project mode is unaffected: its own
directory-discovery walk (`native_exe_entry_scan.discover_sv0_files`)
already only visits real `.sv0` files it finds by extension.

The `.sv0` extension check runs before any filesystem access at all
(a pure string check), matching the existing `.sv0b`-rejection precedent
in `native_exe_cli.py` (GOV-002/003: reject by suffix before any I/O) --
this is a *different* rejection (INPUT-phase, "wrong extension" in
general) from that CLI-parse-time, bytecode-isolation-specific one.

Run `python3 scripts/native_exe_input_validation.py --selftest` for the corpus.
"""

from __future__ import annotations

import os

from native_exe_errors import BuildError, DiagnosticPhase


def validate_file_input_shape(input_kind: str, input_path: str) -> None:
    """For `input_kind == "file"`, confirm `input_path` is a `.sv0`-suffixed,
    existing, regular, readable file -- raising `BuildError(INPUT)` on the
    first violation found, never a raw OS exception. A no-op for
    `input_kind == "project"` (a directory is the correct shape there).
    """
    if input_kind != "file":
        return

    if not input_path.endswith(".sv0"):
        raise BuildError(
            DiagnosticPhase.INPUT,
            f"{input_path}: file input must have a `.sv0` extension (CLI-008)",
        )
    if not os.path.exists(input_path):
        raise BuildError(DiagnosticPhase.INPUT, f"{input_path}: no such file (CLI-008)")
    if not os.path.isfile(input_path):
        raise BuildError(
            DiagnosticPhase.INPUT,
            f"{input_path}: not a regular file -- file mode requires a regular "
            "file, not a directory, FIFO, or other special file (CLI-008)",
        )
    if not os.access(input_path, os.R_OK):
        raise BuildError(DiagnosticPhase.INPUT, f"{input_path}: not readable (CLI-008)")


def _selftest() -> int:
    import stat
    import tempfile

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        # Case 1: a normal, real .sv0 file is accepted (no exception).
        good = os.path.join(td, "good.sv0")
        with open(good, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 { return 0; }\n")
        try:
            validate_file_input_shape("file", good)
        except BuildError as exc:
            failures.append(f"case1: a valid .sv0 file was rejected: {exc.message}")

        # Case 2: project mode is a no-op regardless of what input_path looks like.
        try:
            validate_file_input_shape("project", os.path.join(td, "does-not-exist"))
        except BuildError as exc:
            failures.append(f"case2: project mode must be a no-op, got: {exc.message}")

        # Case 3: a missing file -> clean BuildError(INPUT), never a raw
        # FileNotFoundError.
        missing = os.path.join(td, "missing.sv0")
        try:
            validate_file_input_shape("file", missing)
            failures.append("case3: expected BuildError for a missing file, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.INPUT:
                failures.append(f"case3: expected INPUT phase, got {exc.phase}")
        except OSError as exc:  # pragma: no cover - the exact regression this guards against
            failures.append(f"case3: leaked a raw OSError instead of BuildError: {exc}")

        # Case 4: a directory given as file-mode input -> clean BuildError(INPUT).
        a_dir = os.path.join(td, "a_directory.sv0")
        os.makedirs(a_dir)
        try:
            validate_file_input_shape("file", a_dir)
            failures.append("case4: expected BuildError for a directory, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.INPUT:
                failures.append(f"case4: expected INPUT phase, got {exc.phase}")
        except OSError as exc:  # pragma: no cover
            failures.append(f"case4: leaked a raw OSError instead of BuildError: {exc}")

        # Case 5: a FIFO given as file-mode input -> clean BuildError(INPUT).
        # (Skipped gracefully on a platform without os.mkfifo, e.g. some CI
        # sandboxes -- this is a real POSIX call, not something to fake.)
        fifo_path = os.path.join(td, "a_fifo.sv0")
        try:
            os.mkfifo(fifo_path)
        except (AttributeError, OSError):
            pass
        else:
            try:
                validate_file_input_shape("file", fifo_path)
                failures.append("case5: expected BuildError for a FIFO, none raised")
            except BuildError as exc:
                if exc.phase is not DiagnosticPhase.INPUT:
                    failures.append(f"case5: expected INPUT phase, got {exc.phase}")
            except OSError as exc:  # pragma: no cover
                failures.append(f"case5: leaked a raw OSError instead of BuildError: {exc}")

        # Case 6: a wrong-extension file (real, readable, regular) -> clean
        # BuildError(INPUT) -- checked purely by suffix, never by content.
        wrong_ext = os.path.join(td, "not_sv0.txt")
        with open(wrong_ext, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 { return 0; }\n")
        try:
            validate_file_input_shape("file", wrong_ext)
            failures.append("case6: expected BuildError for a wrong extension, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.INPUT:
                failures.append(f"case6: expected INPUT phase, got {exc.phase}")

        # Case 7: an unreadable file (permissions revoked) -> clean
        # BuildError(INPUT). Skipped gracefully if running as a user that
        # bypasses permission bits (e.g. root in some CI containers).
        unreadable = os.path.join(td, "unreadable.sv0")
        with open(unreadable, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 { return 0; }\n")
        os.chmod(unreadable, 0)
        try:
            if os.access(unreadable, os.R_OK):
                pass  # running as a user that ignores permission bits -- skip this case
            else:
                try:
                    validate_file_input_shape("file", unreadable)
                    failures.append("case7: expected BuildError for an unreadable file, none raised")
                except BuildError as exc:
                    if exc.phase is not DiagnosticPhase.INPUT:
                        failures.append(f"case7: expected INPUT phase, got {exc.phase}")
        finally:
            os.chmod(unreadable, stat.S_IRUSR | stat.S_IWUSR)  # restore so cleanup can remove it

    if failures:
        for f in failures:
            print(f"native_exe_input_validation selftest FAIL: {f}")
        return 1

    print("native_exe_input_validation: selftest OK (7 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_input_validation: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
