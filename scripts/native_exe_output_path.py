"""Default/explicit output paths + permission/symlink rules (NEX-026).

Implements ART-001,005…011
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §12.1/§12.2):
`default_output_path` derives `<cwd>/build/native/<stem>` when `-o` is
absent (`.exe` suffixing is deferred — no supported Windows target yet).
`validate_output_path` applies the pre-flight rules to the *final* path
before a build even starts (an existing directory or symlink leaf is
rejected, ART-008/SEC-003 — reusing the same `os.path.lexists`/
`os.path.islink` checks `native_exe_publish.validate_temp_output` already
proved for the *temp* path, applied here in the opposite direction:
pre-flight on the destination rather than post-flight on the source).
`ensure_output_parent_dir` creates the default `build/native` directory
when needed but never invents missing parents for an *explicit* `-o`
(ART-007) — that stays a hard error.

Run `python3 scripts/native_exe_output_path.py --selftest` for the corpus.
"""

from __future__ import annotations

import os

from native_exe_errors import BuildError, DiagnosticPhase


def stem_for(input_kind: str, input_path: str) -> str:
    """The bare output stem (no directory, no extension) for `input_path` --
    public (not `_stem_for`) because `native_exe_request.py` also needs it
    to compute a config-`output-dir`-relative default path (§17.4), not
    just this module's own `<cwd>/build/native/<stem>` default.
    """
    if input_kind == "project":
        # Strip trailing separators before deriving the basename (§12.1).
        return os.path.basename(input_path.rstrip(os.sep))
    base = os.path.basename(input_path)
    if base.endswith(".sv0"):
        base = base[: -len(".sv0")]
    return base


def default_output_path(input_kind: str, input_path: str, invocation_cwd: str) -> str:
    """`<cwd>/build/native/<stem>` per spec §12.1."""
    stem = stem_for(input_kind, input_path)
    return os.path.join(invocation_cwd, "build", "native", stem)


def validate_output_path(path: str) -> None:
    """Raise BuildError(PUBLISH) for an output path that's unsafe to publish
    to: empty, `-`, an existing directory leaf, or (by default) an existing
    symlink leaf.
    """
    if not path:
        raise BuildError(DiagnosticPhase.PUBLISH, "output path must not be empty")
    if path == "-":
        raise BuildError(DiagnosticPhase.PUBLISH, "executables cannot be streamed to stdout (-o -)")
    if os.path.islink(path):
        raise BuildError(DiagnosticPhase.PUBLISH, f"output path is an existing symlink, refusing to publish over it: {path}")
    if os.path.isdir(path):
        raise BuildError(DiagnosticPhase.PUBLISH, f"output path is an existing directory: {path}")


def ensure_output_parent_dir(path: str, *, is_default: bool) -> None:
    """Create the parent directory only for the *default* output path
    (`build/native/`, §12.1). An explicit `-o` with missing parents is a
    hard error (ART-007) — never silently mkdir'd.
    """
    parent = os.path.dirname(path)
    if not parent or os.path.isdir(parent):
        return
    if is_default:
        os.makedirs(parent, exist_ok=True)
        return
    raise BuildError(
        DiagnosticPhase.PUBLISH,
        f"parent directory does not exist for explicit output path: {parent} "
        "(missing parents are not created for an explicit -o)",
    )


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    # Case 1: default naming table (spec §12.1).
    if default_output_path("file", "/work/demo.sv0", "/work") != os.path.join("/work", "build", "native", "demo"):
        failures.append("file default naming mismatch")
    if default_output_path("project", "/work/app", "/work") != os.path.join("/work", "build", "native", "app"):
        failures.append("project default naming mismatch")
    if default_output_path("project", "/work/app/", "/work") != os.path.join("/work", "build", "native", "app"):
        failures.append("project default naming with trailing slash mismatch")

    with tempfile.TemporaryDirectory() as td:
        # Case 2: an existing directory leaf is rejected.
        dir_leaf = os.path.join(td, "a_directory")
        os.makedirs(dir_leaf)
        try:
            validate_output_path(dir_leaf)
            failures.append("directory leaf: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.PUBLISH:
                failures.append(f"directory leaf: expected PUBLISH phase, got {exc.phase}")

        # Case 3: an existing symlink leaf is rejected by default (SEC-003).
        target = os.path.join(td, "protected_target")
        with open(target, "w", encoding="utf-8") as f:
            f.write("do not touch\n")
        symlink_leaf = os.path.join(td, "symlink_leaf")
        os.symlink(target, symlink_leaf)
        try:
            validate_output_path(symlink_leaf)
            failures.append("symlink leaf: expected BuildError, none raised")
        except BuildError:
            pass
        if open(target, encoding="utf-8").read() != "do not touch\n":
            failures.append("symlink leaf: the symlink target was modified")

        # Case 4: empty path and "-" are both rejected.
        for bad in ("", "-"):
            try:
                validate_output_path(bad)
                failures.append(f"{bad!r}: expected BuildError, none raised")
            except BuildError:
                pass

        # Case 5: a nonexistent, ordinary leaf passes validation cleanly.
        try:
            validate_output_path(os.path.join(td, "does_not_exist_yet"))
        except BuildError as exc:
            failures.append(f"ordinary nonexistent leaf: unexpected BuildError: {exc}")

        # Case 6: default output dir is created; explicit missing parent is a hard error.
        default_path = os.path.join(td, "build", "native", "hello")
        ensure_output_parent_dir(default_path, is_default=True)
        if not os.path.isdir(os.path.dirname(default_path)):
            failures.append("default output parent was not created")

        explicit_path = os.path.join(td, "no_such_dir", "hello")
        try:
            ensure_output_parent_dir(explicit_path, is_default=False)
            failures.append("explicit missing parent: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.PUBLISH:
                failures.append(f"explicit missing parent: expected PUBLISH phase, got {exc.phase}")
        if os.path.isdir(os.path.join(td, "no_such_dir")):
            failures.append("explicit missing parent: directory should not have been created")

    if failures:
        for f in failures:
            print(f"native_exe_output_path selftest FAIL: {f}")
        return 1

    print("native_exe_output_path: selftest OK (6 case groups)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_output_path: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
