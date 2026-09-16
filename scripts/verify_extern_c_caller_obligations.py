#!/usr/bin/env python3
"""Fail if an `#[extern_c] fn ...;` declaration has no `///` doc comment directly above it (FFI-011).

Every `#[extern_c]` declaration crosses a real, unverified C ABI boundary --
task/sv0c-ffi-raw-pointer-abi.Rmd's own Epic C requires "every `extern` fn
must document what safety invariant the *caller* must uphold", mirroring
`sv0-strings`' own DOC-005 requirement and its `strings_unsafe_abi` module
doc ("every function documents its full caller obligations").

This is a standalone script, not a `checker.sv0` diagnostic, for a structural
reason: sv0's lexer discards ALL comments -- `///` included -- before the
parser ever sees a token (lexer.sv0's `skip_line_comment`/
`skip_block_comment`), so a doc comment's presence is invisible to the
compiler proper. Catching this requires scanning raw source text outside
compilation, the same approach `sv0-strings/tools/check_doc_fences.py`
already takes for its own doc-fence discipline (there: Markdown code
fences; here: `.sv0` source lines) -- hence "lint" in FFI-011's own name.

Detection is deliberately narrow, presence-only (no prose-content check):
a `#[extern_c]` (or the reserved-for-later `#[extern_c(...)]`) attribute
only counts as a real declaration when it starts its own line (only
leading whitespace before it) -- the only shape the parser itself accepts
-- so this never misfires on the attribute's own name appearing inside a
string literal or a `/* ... */` explanatory comment, both common in sv0c's
own compiler source and test fixtures, which talk ABOUT the attribute
without declaring one.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EXTERN_C_LINE = re.compile(r"^\s*#\[extern_c\b")
DOC_LINE = re.compile(r"^\s*///")

SKIP_DIR_NAMES = {".git", "build"}


def iter_sv0_files(root: Path) -> list[Path]:
    """Return sorted ``*.sv0`` files under *root*, skipping VCS/build dirs."""
    out: list[Path] = []
    for p in sorted(root.rglob("*.sv0")):
        if any(part in SKIP_DIR_NAMES for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return out


def find_undocumented(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line, text) for each `#[extern_c]` with no `///` line
    immediately above it (blank lines in between are skipped over)."""
    hits: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not EXTERN_C_LINE.match(line):
            continue
        j = i - 1
        while j >= 0 and lines[j].strip() == "":
            j -= 1
        if j < 0 or not DOC_LINE.match(lines[j]):
            hits.append((i + 1, line.strip()))
    return hits


def run_selftest() -> int:
    documented = [
        "/// Caller obligation: x must be non-negative.",
        "#[extern_c]",
        "fn f(x: i32) -> i32;",
    ]
    assert find_undocumented(documented) == [], "documented decl flagged"

    undocumented = [
        "/* explains the test, not a caller obligation */",
        "#[extern_c]",
        "fn f(x: i32) -> i32;",
    ]
    hits = find_undocumented(undocumented)
    assert hits == [(2, "#[extern_c]")], f"undocumented decl not flagged: {hits}"

    blank_between = [
        "/// Caller obligation: x must be non-negative.",
        "",
        "#[extern_c]",
        "fn f(x: i32) -> i32;",
    ]
    assert find_undocumented(blank_between) == [], "blank-line-tolerant doc flagged"

    string_literal = [
        '    let source: string = "#[extern_c] fn f() -> i32;";',
    ]
    assert find_undocumented(string_literal) == [], "string literal false-positived"

    prose_comment = [
        "/* the `#[extern_c]` attribute marks an external declaration */",
    ]
    assert find_undocumented(prose_comment) == [], "prose comment false-positived"

    two_in_one_file = [
        "/// Caller obligation: a.",
        "#[extern_c]",
        "fn a() -> i32;",
        "#[extern_c]",
        "fn b() -> i32;",
    ]
    hits = find_undocumented(two_in_one_file)
    assert hits == [(4, "#[extern_c]")], f"second undocumented decl not flagged: {hits}"

    print("verify_extern_c_caller_obligations: selftest OK (6 case(s))")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", type=Path, help="sv0-toolchain repo root")
    ap.add_argument("--selftest", action="store_true", help="run built-in detector unit tests, no --root needed")
    args = ap.parse_args()

    if args.selftest:
        return run_selftest()

    if args.root is None:
        ap.error("--root is required unless --selftest is given")
    root: Path = args.root.resolve()
    paths = iter_sv0_files(root)
    all_hits: list[tuple[Path, int, str]] = []
    for path in paths:
        lines = path.read_text(encoding="utf-8").splitlines()
        for lineno, text in find_undocumented(lines):
            all_hits.append((path.relative_to(root), lineno, text))

    if all_hits:
        print(
            "verify_extern_c_caller_obligations: `#[extern_c]` declaration(s) with no "
            "`///` caller-obligation doc comment immediately above (FFI-011, "
            "task/sv0c-ffi-raw-pointer-abi.Rmd, Epic C):",
            file=sys.stderr,
        )
        for rel, lineno, text in all_hits:
            print(f"  {rel}:{lineno}: {text}", file=sys.stderr)
        return 1
    print(f"verify_extern_c_caller_obligations: OK (scanned {len(paths)} .sv0 file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
