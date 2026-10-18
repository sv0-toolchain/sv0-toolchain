#!/usr/bin/env python3
"""Tests for scripts/fmt_sv0.py (sv0cov CV-303: the formatter keeps attributes).

--selftest (no build needed; in ./scripts/sv0 test-guards):
  * layout cases: each input formats to the expected text, formatting it again
    changes nothing, and only whitespace changed;
  * shared-line errors name the attribute's line:col and leave the file alone;
  * the fixtures sv0c/test/attributes/{placement,layouts}.sv0 format to their
    goldens (*.fmt; --write regenerates them);
  * the trees `./scripts/sv0 fmt` formats (sv0c/, sv0vm/) are already formatted;
  * the CLI: --check, a write, an error file left unchanged.

--reparse (needs the native compiler and VM emitter; in ./scripts/sv0 test):
  each fixture and its formatted form give the same attribute table on both
  binaries (offsets compared as the count of non-whitespace characters before
  them, so attachment and arguments must match exactly), byte-identical C and
  bytecode, and programs that exit 0 natively and on the VM."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fmt_sv0  # noqa: E402
from fmt_sv0 import FormatError, format_sv0  # noqa: E402

ATTRS = ROOT / "sv0c" / "test" / "attributes"
FIXTURES = ("placement", "layouts")
A = '#[coverage(off, reason = "r")]'
B = '#[coverage(branch_off, reason = "b")]'

# (label, input, expected output)
CASES = [
    ("no attributes", "fn main() -> i32 {\n    return 0;\n}\n", None),
    ("canonical already", f"{A}\nfn f() -> i32 {{ return 1; }}\n", None),
    ("item on the same line", f"{A} fn f() -> i32 {{ return 1; }}\n", f"{A}\nfn f() -> i32 {{ return 1; }}\n"),
    ("two on a line", f"{A} {B}\nfn f() {{}}\n", f"{A}\n{B}\nfn f() {{}}\n"),
    ("statement on the same line", f"fn f() {{\n    {A} let a: i32 = 1; let b: i32 = 2;\n}}\n",
     f"fn f() {{\n    {A}\n    let a: i32 = 1; let b: i32 = 2;\n}}\n"),
    ("takes the construct's indentation", f"fn f() {{\n        {A}\n  {B}\n    if true {{}};\n}}\n",
     f"fn f() {{\n    {A}\n    {B}\n    if true {{}};\n}}\n"),
    ("tabs", f"fn f() {{\n\t{A} return;\n}}\n", f"fn f() {{\n\t{A}\n\treturn;\n}}\n"),
    ("blank lines dropped", f"{A}\n\n\nfn f() {{}}\n", f"{A}\nfn f() {{}}\n"),
    ("trailing line comment kept", f"{A} // why\n\nfn f() {{}}\n", f"{A} // why\nfn f() {{}}\n"),
    ("trailing block comment kept", f"{A} /* why */ fn f() {{}}\n", f"{A} /* why */\nfn f() {{}}\n"),
    ("comments between keep their order", f"{A}\n  // one\n/* two */\n/// doc\nfn f() {{}}\n",
     f"{A}\n// one\n/* two */\n/// doc\nfn f() {{}}\n"),
    ("code before, construct below", f"fn f() {{ {A}\n    return;\n}}\n", f"fn f() {{\n    {A}\n    return;\n}}\n"),
    ("comment before on the line", f"/* c */ {A}\nfn f() {{}}\n", f"/* c */\n{A}\nfn f() {{}}\n"),
    ("argument text kept byte for byte", "#[ coverage ( off ,reason=\"x\" ) ]   fn f() {}\n",
     "#[ coverage ( off ,reason=\"x\" ) ]\nfn f() {}\n"),
    ("space between # and [", f"# [inline] {A} fn f() {{}}\n", f"# [inline]\n{A}\nfn f() {{}}\n"),
    ("brackets and strings inside", '#[a(b = "]", c(d))] #[e = "x]y"] fn f() {}\n',
     '#[a(b = "]", c(d))]\n#[e = "x]y"]\nfn f() {}\n'),
    ("other attributes too", "#[extern_c] fn abs(x: i32) -> i32;\n", "#[extern_c]\nfn abs(x: i32) -> i32;\n"),
    ("in a string", 'fn f() {\n    let s: string = "a; #[x] b";\n}\n', None),
    ("in comments", f"// {A} fn\n/* {A} let */\nfn f() {{}}\n", None),
    ("in a nested block comment", f"/* a /* b */ {A} fn */\nfn f() {{}}\n", None),
    ("char literals", "fn f() {\n    let c: char = '#'; let d: char = '['; let e: char = '\\'';\n}\n", None),
    ("run at the end of the file", f"fn f() {{}}\n{A}  {B}\n", f"fn f() {{}}\n{A}  {B}\n"),
    ("unterminated attribute", "fn f() {}\n#[coverage(off\n", None),
    ("keep-layout pragma", f"// fmt_sv0: keep-layout\n{A} fn f() {{}}\n", None),
    ("pragma after code is ignored", f"fn g() {{}}\n// fmt_sv0: keep-layout\n{A} fn f() {{}}\n",
     f"fn g() {{}}\n// fmt_sv0: keep-layout\n{A}\nfn f() {{}}\n"),
    ("whitespace pass still applies", f"{A}   \nfn f() {{}}   \n\n\n", f"{A}\nfn f() {{}}\n"),
    ("CRLF", f"{A} fn f() {{}}\r\n", f"{A}\nfn f() {{}}\n"),
    ("no final newline", "fn f() {}", "fn f() {}\n"),
]

# (label, input, line, col)
ERRORS = [
    ("one-line block", f"fn f() -> i32 {{ {A} return 1; }}\n", 1, 17),
    ("expression operand", f"fn f() {{\n    let a: i32 = 1 + {A} 2;\n}}\n", 2, 22),
    ("after a statement", f"fn f() {{\n    let a: i32 = 1; {A} return;\n}}\n", 2, 21),
    ("after a block comment", f"fn f() {{\n    /* c */ {A} return;\n}}\n", 2, 13),
]


def nonws(text: str) -> str:
    return "".join(text.split())


def selftest(write: bool) -> list[str]:
    errors: list[str] = []
    for label, src, want in CASES:
        want = src if want is None else want
        try:
            got = format_sv0(src)
        except FormatError as e:
            errors.append(f"{label}: unexpected error {e}")
            continue
        if got != want:
            errors.append(f"{label}: got {got!r}, want {want!r}")
        if format_sv0(got) != got:
            errors.append(f"{label}: formatting is not idempotent")
        if nonws(got) != nonws(src):
            errors.append(f"{label}: something other than whitespace changed")
    for label, src, line, col in ERRORS:
        try:
            got = format_sv0(src)
            errors.append(f"{label}: formatted without an error: {got!r}")
        except FormatError as e:
            if (e.line, e.col) != (line, col) or "shares a line with earlier code" not in e.message:
                errors.append(f"{label}: error {e}, want {line}:{col}")
    for name in FIXTURES:
        src = (ATTRS / f"{name}.sv0").read_text()
        if fmt_sv0.format_sv0(src) != fmt_sv0.format_whitespace(src):
            errors.append(f"{name}.sv0: the keep-layout pragma is not honored")
        got = format_sv0(src, honor_keep_layout=False)
        golden = ATTRS / f"{name}.fmt"
        if write:
            golden.write_text(got)
        if not golden.is_file() or golden.read_text() != got:
            errors.append(f"{name}.fmt: the formatted fixture differs from the golden (--write regenerates it)")
        if got == src:
            errors.append(f"{name}.sv0: the fixture is already canonical, so it tests nothing")
        if format_sv0(got, honor_keep_layout=False) != got or nonws(got) != nonws(src):
            errors.append(f"{name}.fmt: not idempotent, or more than whitespace changed")
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "fmt_sv0.py"), "--check", str(ROOT / "sv0c"), str(ROOT / "sv0vm")],
                       capture_output=True, text=True)
    if p.returncode != 0:
        errors.append(f"sv0c/ and sv0vm/ are not formatted (./scripts/sv0 fmt): {p.stderr.strip()[:500]}")
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        bad, ugly, clean = t / "bad.sv0", t / "ugly.sv0", t / "clean.sv0"
        bad.write_text(ERRORS[0][1])
        ugly.write_text(CASES[2][1])
        clean.write_text(CASES[2][2])
        cli = [sys.executable, str(ROOT / "scripts" / "fmt_sv0.py")]
        if subprocess.run([*cli, "--check", str(clean)], capture_output=True).returncode != 0:
            errors.append("cli: --check fails a formatted file")
        if subprocess.run([*cli, "--check", str(ugly)], capture_output=True).returncode != 1 or ugly.read_text() != CASES[2][1]:
            errors.append("cli: --check does not fail (or writes) an unformatted file")
        p = subprocess.run([*cli, str(ugly), str(bad)], capture_output=True, text=True)
        if p.returncode != 1 or f"{bad}:1:17:" not in p.stderr or bad.read_text() != ERRORS[0][1]:
            errors.append(f"cli: a layout error does not exit 1 with its position and leave the file: {p.stderr!r}")
        if ugly.read_text() != CASES[2][2]:
            errors.append("cli: a file beside one with a layout error was not formatted")
    return errors


def table(dump: str, text: str) -> list[list[str]]:
    """attr-dump records with byte offsets replaced by non-whitespace ordinals."""
    rows = []
    for line in dump.splitlines():
        f = line.split("\t")
        cols = {"attr": (6, 7, 8), "arg": (4, 5)}.get(f[0], ())
        for c in cols:
            off = int(f[c])
            f[c] = "-" if off < 0 else str(len(nonws(text[:off])))
        rows.append(f)
    return rows


def reparse() -> list[str]:
    sys.path.insert(0, str(ATTRS))
    sys.dont_write_bytecode = True
    from run_attributes import NATIVE, SV0, VM_EMIT, ensure_built, run

    ensure_built()
    errors: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        for name in FIXTURES:
            orig = ATTRS / f"{name}.sv0"
            fmt = t / f"{name}.sv0"
            fmt.write_text(format_sv0(orig.read_text(), honor_keep_layout=False))
            tables = []
            for binary in (NATIVE, VM_EMIT):
                for src in (orig, fmt):
                    p = run(binary, src, "attr-dump\n/unused")
                    if p.returncode:
                        errors.append(f"{name}: attr-dump on {binary.name} exits {p.returncode}")
                    tables.append(table(p.stdout.decode(), src.read_text()))
            if not tables[0] or any(x != tables[0] for x in tables[1:]):
                errors.append(f"{name}: an attribute's attachment or arguments changed when formatting (or the binaries disagree)")
            c = [run(NATIVE, src) for src in (orig, fmt)]
            if c[0].returncode or not c[0].stdout or c[0].stdout != c[1].stdout:
                errors.append(f"{name}: the generated C changed when formatting")
            bytecode = []
            for src in (orig, fmt):
                out = t / f"{src.stem}-{len(bytecode)}.sv0b"
                subprocess.run([str(SV0), "vm-native-compile", str(src), str(out)], capture_output=True, timeout=300)
                bytecode.append(out.read_bytes() if out.is_file() else b"")
                r = subprocess.run([str(SV0), "vm-run", str(out)], capture_output=True, text=True, timeout=300)
                if "vm_exit:0" not in r.stdout + r.stderr:
                    errors.append(f"{name} ({'formatted' if src == fmt else 'original'}): the VM run does not exit 0")
                exe = t / f"{name}-exe-{len(bytecode)}"
                subprocess.run([str(SV0), "native-compile", "-o", str(exe), str(src)], capture_output=True, timeout=300)
                if not exe.exists() or subprocess.run([str(exe)], timeout=60).returncode != 0:
                    errors.append(f"{name} ({'formatted' if src == fmt else 'original'}): the native program does not exit 0")
            if not bytecode[0] or bytecode[0] != bytecode[1]:
                errors.append(f"{name}: the bytecode changed when formatting")
    return errors


def main() -> int:
    if "--reparse" in sys.argv:
        errors, what = reparse(), "format/reparse (attr-dump on both binaries, C, bytecode)"
    else:
        errors, what = selftest("--write" in sys.argv), f"{len(CASES)} layout cases, {len(ERRORS)} errors, fixtures, trees, CLI"
    for e in errors:
        print(f"verify_fmt_sv0: {e}", file=sys.stderr)
    if errors:
        return 1
    print(f"verify_fmt_sv0: OK ({what})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
