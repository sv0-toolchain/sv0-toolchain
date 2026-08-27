"""Reject source/project with zero or duplicate `main` before any host-compiler
invocation (NEX-013, NEX-014).

Implements ENTRY-001/ENTRY-004 and PIPE-002
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §14.2): native
executable construction requires exactly one top-level `main`, and a missing
one must be a *source* diagnostic that prevents the host compiler from ever
running — not a fabricated no-op executable. Spec §4.4 documents that the
current C backend actually does the wrong thing here: given no user `main`,
it emits `int main(void) { return 0; }` anyway, indistinguishable in the
*generated C* from a legitimate trivial `fn main() -> i32 { return 0; }`.
That makes detection from emitted C output structurally unsound — the two
cases produce byte-identical C. This module instead scans the **source**,
where the distinction is real: either the user wrote `fn main` somewhere or
they didn't.

This is a conservative *pre-filter*, not project composition or a substitute
for the compiler's own semantic entry validation (spec §13.3: "The driver
SHALL NOT independently concatenate sources, infer module names, select an
entry file, or reimplement resolver behavior"). It answers exactly one
narrow, source-truth question — how many top-level `fn main` declarations
exist in the given file or project tree — using a comment/string-aware scan
(adapted from this repo's own `check_sv0_block_comment_nesting.py`
tokenizer) so text inside a `//` line comment, a `/* */` block comment, or a
string literal is never mistaken for a real declaration. Zero is ENTRY-004
(missing), more than one is ENTRY-001 (duplicate — whether within one file
or spread across several project files). It does not (and cannot, without
the checker) validate parameters or return type (NEX-015) — that stays a
compiler-validated slice.

Run `python3 scripts/native_exe_entry_scan.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import re

from native_exe_errors import BuildError, DiagnosticPhase

MAIN_DECL_RE = re.compile(r"\bfn\s+main\s*\(")


def mask_comments_and_strings(source: str) -> str:
    """Replace comment/string-literal bytes with spaces, preserving offsets
    and newlines, so a plain regex scan never matches inside either.
    """
    n = len(source)
    out = list(source)
    i = 0
    depth = 0
    while i < n:
        if depth > 0:
            if i + 1 < n and source[i] == "/" and source[i + 1] == "*":
                depth += 1
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if i + 1 < n and source[i] == "*" and source[i + 1] == "/":
                depth -= 1
                out[i] = out[i + 1] = " "
                i += 2
                continue
            if source[i] != "\n":
                out[i] = " "
            i += 1
            continue

        if i + 1 < n and source[i] == "/" and source[i + 1] == "/":
            while i < n and source[i] != "\n":
                out[i] = " "
                i += 1
            continue

        if i + 1 < n and source[i] == "/" and source[i + 1] == "*":
            depth = 1
            out[i] = out[i + 1] = " "
            i += 2
            continue

        if source[i] == '"':
            out[i] = " "
            i += 1
            while i < n:
                if source[i] == "\\" and i + 1 < n:
                    out[i] = out[i + 1] = " "
                    i += 2
                    continue
                if source[i] == '"':
                    out[i] = " "
                    i += 1
                    break
                if source[i] != "\n":
                    out[i] = " "
                i += 1
            continue

        i += 1

    return "".join(out)


def has_main_declaration(source: str) -> bool:
    return MAIN_DECL_RE.search(mask_comments_and_strings(source)) is not None


def count_main_declarations(source: str) -> int:
    return len(MAIN_DECL_RE.findall(mask_comments_and_strings(source)))


def discover_sv0_files(project_dir: str) -> list[str]:
    """Recursively find `.sv0` files, skipping hidden path components.

    A pre-filter convenience only — real project file discovery/ordering
    remains the compiler's job (PIPE-007, spec §13.3); this exists solely to
    give `validate_entry_exists` something to scan for project mode.
    """
    found: list[str] = []
    for root, dirs, files in os.walk(project_dir):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            if name.endswith(".sv0") and not name.startswith("."):
                found.append(os.path.join(root, name))
    return sorted(found)


def validate_entry_exists(input_kind: str, input_path: str) -> None:
    """Raise BuildError(ENTRY) unless exactly one `.sv0` file at `input_path`
    (a single file for `input_kind == "file"`, or a project tree for
    `input_kind == "project"`) declares a top-level `fn main` — zero is
    ENTRY-004 (missing), more than one (whether within one file or spread
    across several project files) is ENTRY-001 (duplicate).
    """
    if input_kind == "file":
        with open(input_path, encoding="utf-8") as f:
            source = f.read()
        count = count_main_declarations(source)
        if count == 1:
            return
        if count == 0:
            raise BuildError(
                DiagnosticPhase.ENTRY,
                f"{input_path}: no top-level `fn main` found; native executable "
                "construction requires exactly one (ENTRY-004)",
            )
        raise BuildError(
            DiagnosticPhase.ENTRY,
            f"{input_path}: found {count} top-level `fn main` declarations; native "
            "executable construction requires exactly one (ENTRY-001)",
        )

    files_with_main: list[str] = []
    for path in discover_sv0_files(input_path):
        with open(path, encoding="utf-8") as f:
            source = f.read()
        for _ in range(count_main_declarations(source)):
            files_with_main.append(path)

    if len(files_with_main) == 1:
        return
    if len(files_with_main) == 0:
        raise BuildError(
            DiagnosticPhase.ENTRY,
            f"{input_path}: no top-level `fn main` found in any .sv0 file under the "
            "project; native executable construction requires exactly one (ENTRY-004)",
        )
    raise BuildError(
        DiagnosticPhase.ENTRY,
        f"{input_path}: found {len(files_with_main)} top-level `fn main` declarations "
        f"across the project ({', '.join(files_with_main)}); native executable "
        "construction requires exactly one (ENTRY-001)",
    )


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    def write(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    with tempfile.TemporaryDirectory() as td:
        # Case 1: a real fn main passes.
        p = os.path.join(td, "hello.sv0")
        write(p, "fn main() -> i32 {\n    return 0;\n}\n")
        try:
            validate_entry_exists("file", p)
        except BuildError as exc:
            failures.append(f"case1 (real main): unexpected BuildError: {exc}")

        # Case 2 (ENTRY-004): a library file with no main is rejected.
        p = os.path.join(td, "lib.sv0")
        write(p, "pub fn add(a: i32, b: i32) -> i32 {\n    return a + b;\n}\n")
        try:
            validate_entry_exists("file", p)
            failures.append("case2 (no main): expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY or exc.exit_code != 4:
                failures.append(f"case2: expected ENTRY/exit4, got {exc.phase}/{exc.exit_code}")

        # Case 3: `main` mentioned only inside a `//` comment does not count.
        p = os.path.join(td, "commented.sv0")
        write(p, "// TODO: add fn main() someday\npub fn add(a: i32, b: i32) -> i32 { return a + b; }\n")
        try:
            validate_entry_exists("file", p)
            failures.append("case3 (main in // comment): expected BuildError, none raised")
        except BuildError:
            pass

        # Case 4: `main` mentioned only inside a block comment does not count.
        p = os.path.join(td, "block_commented.sv0")
        write(p, "/* fn main() -> i32 { return 0; } */\npub fn add(a: i32, b: i32) -> i32 { return a + b; }\n")
        try:
            validate_entry_exists("file", p)
            failures.append("case4 (main in /* */ comment): expected BuildError, none raised")
        except BuildError:
            pass

        # Case 5: `main` mentioned only inside a string literal does not count.
        p = os.path.join(td, "stringed.sv0")
        write(p, 'pub fn describe() -> string {\n    return "fn main() -> i32 { return 0; }";\n}\n')
        try:
            validate_entry_exists("file", p)
            failures.append("case5 (main in string literal): expected BuildError, none raised")
        except BuildError:
            pass

        # Case 6: project mode finds main in a nested file.
        proj = os.path.join(td, "calculator")
        write(os.path.join(proj, "math", "math.sv0"), "pub fn add(a: i32, b: i32) -> i32 { return a + b; }\n")
        write(os.path.join(proj, "main.sv0"), "module app;\nuse math::add;\nfn main() -> i32 { return add(40, 2); }\n")
        try:
            validate_entry_exists("project", proj)
        except BuildError as exc:
            failures.append(f"case6 (project with main): unexpected BuildError: {exc}")

        # Case 7: project mode with no main anywhere is rejected.
        proj2 = os.path.join(td, "library_project")
        write(os.path.join(proj2, "a.sv0"), "pub fn a() -> i32 { return 1; }\n")
        write(os.path.join(proj2, "sub", "b.sv0"), "pub fn b() -> i32 { return 2; }\n")
        try:
            validate_entry_exists("project", proj2)
            failures.append("case7 (project with no main): expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY:
                failures.append(f"case7: expected ENTRY phase, got {exc.phase}")

        # Case 8: a main hiding only under a hidden directory does not count
        # (hidden path components are skipped, matching project-discovery policy).
        proj3 = os.path.join(td, "hidden_main_project")
        write(os.path.join(proj3, "a.sv0"), "pub fn a() -> i32 { return 1; }\n")
        write(os.path.join(proj3, ".git", "fake.sv0"), "fn main() -> i32 { return 0; }\n")
        try:
            validate_entry_exists("project", proj3)
            failures.append("case8 (main only under hidden dir): expected BuildError, none raised")
        except BuildError:
            pass

        # Case 9 (ENTRY-001, NEX-014): two `fn main` in one file is a duplicate, not success.
        p = os.path.join(td, "two_mains.sv0")
        write(p, "fn main() -> i32 { return 0; }\nfn main() -> i32 { return 1; }\n")
        try:
            validate_entry_exists("file", p)
            failures.append("case9 (two main in one file): expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY:
                failures.append(f"case9: expected ENTRY phase, got {exc.phase}")
            if "2 top-level" not in exc.message:
                failures.append(f"case9: expected count in message, got {exc.message!r}")

        # Case 10 (ENTRY-001, NEX-014): two different project files each declaring
        # `fn main` is also a duplicate, even though no single file has two.
        proj4 = os.path.join(td, "duplicate_entry_project")
        write(os.path.join(proj4, "a.sv0"), "fn main() -> i32 { return 0; }\n")
        write(os.path.join(proj4, "b.sv0"), "fn main() -> i32 { return 1; }\n")
        try:
            validate_entry_exists("project", proj4)
            failures.append("case10 (two files each with main): expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY:
                failures.append(f"case10: expected ENTRY phase, got {exc.phase}")
            if "2 top-level" not in exc.message:
                failures.append(f"case10: expected count in message, got {exc.message!r}")

    if failures:
        for f in failures:
            print(f"native_exe_entry_scan selftest FAIL: {f}")
        return 1

    print("native_exe_entry_scan: selftest OK (10 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_entry_scan: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
