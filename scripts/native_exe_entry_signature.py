"""Validate `fn main`'s parameters and return type (NEX-015).

Implements ENTRY-002/ENTRY-003
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §14.1): R0
executable builds accept only a zero-parameter `main` returning `i32` or
unit (explicit `-> ()` or implicit — no `->` at all). Every other shape
(parameters, `bool`, a non-`i32` integer width, a struct/enum/reference/
string return) must be rejected before the host compiler ever runs.

Like `native_exe_entry_scan.py` (NEX-013/014), this is a source-level
pre-filter, not the compiler's own type checker — it reuses that module's
comment/string masking and `fn main(` matcher, then hand-parses the
balanced-paren parameter list and the return-type text up to the opening
`{`, entirely as raw text. It answers only "does this signature's *shape*
match one of the two accepted forms", not full type-correctness (a genuinely
malformed type expression is still the checker's problem, same division of
labor as NEX-013/014).

Run `python3 scripts/native_exe_entry_signature.py --selftest` for the
return/signature matrix (NEX-015's red test): one fixture per rejected shape,
plus every accepted shape.
"""

from __future__ import annotations

from dataclasses import dataclass

from native_exe_entry_scan import MAIN_DECL_RE, discover_sv0_files, mask_comments_and_strings
from native_exe_errors import BuildError, DiagnosticPhase

# Spec §14.1: only these three source spellings are accepted through R1.
_ACCEPTED_RETURN_TYPES = {"", "()", "i32"}


@dataclass
class MainSignature:
    params: str  # raw text between the parens, whitespace-trimmed; "" means zero params
    return_type: str  # "" means no `->` at all (implicit unit); else the raw text after `->`


def extract_main_signatures(source: str) -> list[MainSignature]:
    """Return one MainSignature per top-level `fn main(...)` found in `source`."""
    masked = mask_comments_and_strings(source)
    n = len(masked)
    sigs: list[MainSignature] = []

    for m in MAIN_DECL_RE.finditer(masked):
        i = m.end()  # just past the opening "("
        depth = 1
        params_start = i
        while i < n and depth > 0:
            if masked[i] == "(":
                depth += 1
            elif masked[i] == ")":
                depth -= 1
            i += 1
        params = masked[params_start : i - 1].strip()

        j = i
        while j < n and masked[j] in " \t\r\n":
            j += 1
        return_type = ""
        if masked[j : j + 2] == "->":
            j += 2
            type_start = j
            while j < n and masked[j] != "{":
                j += 1
            return_type = masked[type_start:j].strip()

        sigs.append(MainSignature(params=params, return_type=return_type))

    return sigs


def validate_entry_signature(input_kind: str, input_path: str) -> None:
    """Raise BuildError(ENTRY) for the first `fn main` signature found that
    takes parameters (ENTRY-002) or returns anything but `i32`/unit
    (ENTRY-003), across the given file or project tree.
    """
    paths = [input_path] if input_kind == "file" else discover_sv0_files(input_path)

    for path in paths:
        with open(path, encoding="utf-8") as f:
            source = f.read()
        for sig in extract_main_signatures(source):
            if sig.params:
                raise BuildError(
                    DiagnosticPhase.ENTRY,
                    f"{path}: `fn main` must take zero parameters, found `({sig.params})` (ENTRY-002)",
                )
            if sig.return_type not in _ACCEPTED_RETURN_TYPES:
                raise BuildError(
                    DiagnosticPhase.ENTRY,
                    f"{path}: `fn main` must return `i32` or unit, found `-> {sig.return_type}` (ENTRY-003)",
                )


def _selftest() -> int:
    import os
    import tempfile

    failures: list[str] = []

    accepted = [
        ("explicit i32", "fn main() -> i32 {\n    return 0;\n}\n"),
        ("explicit unit", "fn main() -> () {\n    println(\"hi\");\n}\n"),
        ("implicit unit", "fn main() {\n    println(\"hi\");\n}\n"),
    ]
    rejected = [
        ("params", "fn main(argc: i32) -> i32 {\n    return 0;\n}\n", "ENTRY-002"),
        ("bool return", "fn main() -> bool {\n    return true;\n}\n", "ENTRY-003"),
        ("wrong int width", "fn main() -> i64 {\n    return 0;\n}\n", "ENTRY-003"),
        ("struct return", "fn main() -> Outcome {\n    return Outcome::Ok(0);\n}\n", "ENTRY-003"),
        ("enum-shaped return", "fn main() -> Status {\n    return Status::Ready;\n}\n", "ENTRY-003"),
        ("reference return", "fn main() -> &i32 {\n    return 0;\n}\n", "ENTRY-003"),
        ("string return", "fn main() -> string {\n    return \"done\";\n}\n", "ENTRY-003"),
    ]

    with tempfile.TemporaryDirectory() as td:
        for name, source in accepted:
            p = os.path.join(td, f"{name.replace(' ', '_')}.sv0")
            with open(p, "w", encoding="utf-8") as f:
                f.write(source)
            try:
                validate_entry_signature("file", p)
            except BuildError as exc:
                failures.append(f"accepted[{name}]: unexpected BuildError: {exc}")

        for name, source, expected_code in rejected:
            p = os.path.join(td, f"{name.replace(' ', '_')}.sv0")
            with open(p, "w", encoding="utf-8") as f:
                f.write(source)
            try:
                validate_entry_signature("file", p)
                failures.append(f"rejected[{name}]: expected BuildError, none raised")
            except BuildError as exc:
                if exc.phase is not DiagnosticPhase.ENTRY:
                    failures.append(f"rejected[{name}]: expected ENTRY phase, got {exc.phase}")
                if expected_code not in exc.message:
                    failures.append(f"rejected[{name}]: expected {expected_code} in message, got {exc.message!r}")

        # Project mode: a bad signature in a nested file is still caught.
        proj = os.path.join(td, "proj")
        os.makedirs(proj)
        with open(os.path.join(proj, "main.sv0"), "w", encoding="utf-8") as f:
            f.write("fn main() -> bool {\n    return true;\n}\n")
        try:
            validate_entry_signature("project", proj)
            failures.append("project mode: expected BuildError, none raised")
        except BuildError as exc:
            if "ENTRY-003" not in exc.message:
                failures.append(f"project mode: expected ENTRY-003, got {exc.message!r}")

    total = len(accepted) + len(rejected) + 1
    if failures:
        for f in failures:
            print(f"native_exe_entry_signature selftest FAIL: {f}")
        return 1

    print(f"native_exe_entry_signature: selftest OK ({total} cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_entry_signature: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
