"""Reject source that collides with the entry-adapter's reserved symbols (NEX-017).

Implements ENTRY-008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §14.5): "Internal
entry symbols SHALL not collide with user source names... Source-name
mangling SHALL prevent a user function from colliding with them."

NEX-016 (`sv0c/lib/megaTU-main.sv0`) introduced two new C symbols the
compiler itself synthesizes: `sv0_user_main` (the wrapped entry body) and
`sv0_runtime_init` (`sv0c/runtime/sv0_runtime.h`). Verified directly: a
source file declaring its own top-level `fn sv0_user_main(...)` alongside a
real `main` compiles to two conflicting `static int sv0_user_main(void)`
definitions, and `cc` fails with "redefinition of 'sv0_user_main'"; a user
`fn sv0_runtime_init(...)` similarly fails with "conflicting types" against
the runtime header. That's a real safety net (the host compiler refuses to
link), but it surfaces as a raw `host-compile` (exit 6) C-level error, not
the early, source-level ENTRY diagnostic (exit 4) ENTRY-008 calls for.

Rather than teaching the compiler to *mangle* (rename) a colliding user
function — which would also require rewriting every call site that
references it, real compiler surgery — this rejects the collision at the
Python driver layer, before the host compiler (or even the core compiler)
ever runs, mirroring `native_exe_entry_scan.py`'s `fn main` detection
exactly: a comment/string-aware source scan, file or project mode. The host
compiler's existing redefinition/conflicting-types errors remain as a
defense-in-depth backstop for anyone invoking the core compiler directly,
bypassing this driver.

Scope is deliberately narrow: exactly the two concrete symbols NEX-016
introduced, not the whole `sv0_`-prefixed runtime API surface (~20 other
symbols like `sv0_println`/`sv0_vec_new` share that prefix too — a
pre-existing, differently-scoped risk this slice does not take on), and only
top-level `fn <name>(` declarations (struct/enum names live in a different C
namespace and aren't what ENTRY-008 addresses).

Run `python3 scripts/native_exe_entry_reserved.py --selftest` for the corpus.
"""

from __future__ import annotations

import re

from native_exe_entry_scan import discover_sv0_files, mask_comments_and_strings
from native_exe_errors import BuildError, DiagnosticPhase

# The exact two C symbols NEX-016's entry adapter introduced (spec §14.3/§14.5).
RESERVED_ENTRY_SYMBOLS = ("sv0_user_main", "sv0_runtime_init")

_RESERVED_DECL_RE = re.compile(
    r"\bfn\s+(" + "|".join(re.escape(n) for n in RESERVED_ENTRY_SYMBOLS) + r")\s*\("
)


def find_reserved_collisions(source: str) -> list[str]:
    """Return every reserved symbol name declared as a top-level `fn` in `source`."""
    masked = mask_comments_and_strings(source)
    return [m.group(1) for m in _RESERVED_DECL_RE.finditer(masked)]


def validate_no_reserved_collisions(input_kind: str, input_path: str) -> None:
    """Raise BuildError(ENTRY) if any file at `input_path` declares a top-level
    `fn` named `sv0_user_main` or `sv0_runtime_init` (ENTRY-008).
    """
    paths = [input_path] if input_kind == "file" else discover_sv0_files(input_path)

    for path in paths:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        collisions = find_reserved_collisions(source)
        if collisions:
            raise BuildError(
                DiagnosticPhase.ENTRY,
                f"{path}: user source declares `fn {collisions[0]}`, which collides "
                "with a symbol reserved for the native executable entry adapter "
                "(ENTRY-008); rename the function",
            )


def _selftest() -> int:
    import os
    import tempfile

    failures: list[str] = []

    def write(path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    with tempfile.TemporaryDirectory() as td:
        # Case 1: a user `sv0_user_main` alongside a real `main` is rejected.
        p = os.path.join(td, "collide_user_main.sv0")
        write(p, "fn sv0_user_main() -> i32 {\n    return 7;\n}\n\nfn main() -> i32 {\n    return 0;\n}\n")
        try:
            validate_no_reserved_collisions("file", p)
            failures.append("case1 (sv0_user_main collision): expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY or exc.exit_code != 4:
                failures.append(f"case1: expected ENTRY/exit4, got {exc.phase}/{exc.exit_code}")
            if "sv0_user_main" not in exc.message:
                failures.append(f"case1: message doesn't name the symbol: {exc.message!r}")

        # Case 2: a user `sv0_runtime_init` is rejected.
        p = os.path.join(td, "collide_runtime_init.sv0")
        write(p, "fn sv0_runtime_init() -> i32 {\n    return 7;\n}\n\nfn main() -> i32 {\n    return 0;\n}\n")
        try:
            validate_no_reserved_collisions("file", p)
            failures.append("case2 (sv0_runtime_init collision): expected BuildError, none raised")
        except BuildError as exc:
            if "sv0_runtime_init" not in exc.message:
                failures.append(f"case2: message doesn't name the symbol: {exc.message!r}")

        # Case 3: project mode catches a collision in a nested file.
        proj = os.path.join(td, "proj")
        write(os.path.join(proj, "main.sv0"), "module app;\nfn main() -> i32 {\n    return 0;\n}\n")
        write(os.path.join(proj, "helpers", "bad.sv0"), "pub fn sv0_user_main() -> i32 {\n    return 1;\n}\n")
        try:
            validate_no_reserved_collisions("project", proj)
            failures.append("case3 (project-mode collision): expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY:
                failures.append(f"case3: expected ENTRY phase, got {exc.phase}")

        # Case 4: the reserved names mentioned only in a comment or string
        # literal do not count (reusing native_exe_entry_scan's masking guarantee).
        p = os.path.join(td, "mentioned_only.sv0")
        write(
            p,
            "// TODO: consider a fn sv0_user_main() helper someday\n"
            'pub fn describe() -> string {\n    return "fn sv0_runtime_init() {}";\n}\n'
            "fn main() -> i32 {\n    return 0;\n}\n",
        )
        try:
            validate_no_reserved_collisions("file", p)
        except BuildError as exc:
            failures.append(f"case4 (mentioned in comment/string only): unexpected BuildError: {exc}")

        # Case 5: an ordinary program with neither reserved name passes cleanly.
        p = os.path.join(td, "clean.sv0")
        write(p, "pub fn add(a: i32, b: i32) -> i32 {\n    return a + b;\n}\n\nfn main() -> i32 {\n    return add(40, 2);\n}\n")
        try:
            validate_no_reserved_collisions("file", p)
        except BuildError as exc:
            failures.append(f"case5 (clean program): unexpected BuildError: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_entry_reserved selftest FAIL: {f}")
        return 1

    print("native_exe_entry_reserved: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_entry_reserved: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
