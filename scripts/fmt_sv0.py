#!/usr/bin/env python3
"""Normalize .sv0 source text.

Two passes, nothing else is reflowed or re-indented:

1. attribute layout (sv0doc attributes/coverage.md section 5, sv0cov CV-303):
   every attribute `#[...]` goes on its own line directly before the item or
   statement it attaches to, at that construct's indentation. Comments between
   an attribute and its construct stay (on the attribute's line when they
   trailed it), blank lines between them go, and attribute text is kept
   byte for byte, so the token stream and every attachment are unchanged.
   An attribute whose construct shares a line with earlier code (for example
   `{ #[coverage(off, reason = "r")] return 1; }`) has no indentation to take;
   that is an error and the file is left as it is. An attribute run that the
   end of the file follows is left as it is. A file whose leading comments
   include the line `// fmt_sv0: keep-layout` skips this pass (fixtures that
   test non-canonical layouts on purpose).
2. whitespace: strip trailing whitespace per line, trim trailing blank lines,
   ensure a final newline.

Use --check to exit 1 if any file would change; a layout error also exits 1."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path


class FormatError(Exception):
    def __init__(self, line: int, col: int, message: str) -> None:
        super().__init__(f"{line}:{col}: {message}")
        self.line = line
        self.col = col
        self.message = message


@dataclass
class Piece:
    kind: str  # "attr", "comment" or "code"
    start: int
    end: int


def _skip_quoted(text: str, p: int, quote: str) -> int:
    """`p` is just past the opening quote; returns the index past the closing one."""
    n = len(text)
    while p < n:
        c = text[p]
        if c == "\\":
            p += 2
            continue
        if c == quote:
            return p + 1
        if quote == "'" and c == "\n":
            return p
        p += 1
    return n


def scan(text: str) -> list[Piece]:
    """Split source into attributes, comments and code tokens (whitespace dropped).

    Strings and character literals are one code token each, so `#[` or `//`
    inside them is never mistaken for an attribute or a comment."""
    pieces: list[Piece] = []
    n = len(text)
    p = 0
    while p < n:
        c = text[p]
        if c in " \t\r\n":
            p += 1
            continue
        if text.startswith("//", p):
            e = text.find("\n", p)
            e = n if e < 0 else e
            pieces.append(Piece("comment", p, e))
            p = e
            continue
        if text.startswith("/*", p):
            e = text.find("*/", p + 2)
            e = n if e < 0 else e + 2
            pieces.append(Piece("comment", p, e))
            p = e
            continue
        if c == '"' or c == "'":
            e = _skip_quoted(text, p + 1, c)
            pieces.append(Piece("code", p, e))
            p = e
            continue
        if c == "#":
            q = p + 1
            while q < n and text[q] in " \t\r\n":
                q += 1
            if q < n and text[q] == "[":
                depth = 0
                while q < n:
                    d = text[q]
                    if d == '"' or d == "'":
                        q = _skip_quoted(text, q + 1, d)
                        continue
                    if d == "[":
                        depth += 1
                    elif d == "]":
                        depth -= 1
                        if depth == 0:
                            q += 1
                            break
                    q += 1
                pieces.append(Piece("attr", p, q))
                p = q
                continue
        if c.isalnum() or c == "_":
            e = p + 1
            while e < n and (text[e].isalnum() or text[e] == "_"):
                e += 1
            pieces.append(Piece("code", p, e))
            p = e
            continue
        pieces.append(Piece("code", p, p + 1))
        p += 1
    return pieces


def _line_start(text: str, pos: int) -> int:
    return text.rfind("\n", 0, pos) + 1


def _line_col(text: str, pos: int) -> tuple[int, int]:
    return text.count("\n", 0, pos) + 1, pos - _line_start(text, pos) + 1


KEEP_LAYOUT = "// fmt_sv0: keep-layout"


def keeps_layout(text: str, pieces: list[Piece]) -> bool:
    """A file whose leading comments include the line `// fmt_sv0: keep-layout`
    keeps its attribute layout (fixtures that test non-canonical layouts)."""
    for piece in pieces:
        if piece.kind != "comment":
            return False
        if text[piece.start : piece.end].rstrip() == KEEP_LAYOUT:
            return True
    return False


def layout_attributes(text: str, honor_keep_layout: bool = True) -> str:
    pieces = scan(text)
    if honor_keep_layout and keeps_layout(text, pieces):
        return text
    edits: list[tuple[int, int, str]] = []
    i = 0
    while i < len(pieces):
        if pieces[i].kind != "attr":
            i += 1
            continue
        j = i
        while j < len(pieces) and pieces[j].kind in ("attr", "comment"):
            j += 1
        if j == len(pieces):
            break
        first = pieces[i]
        construct = pieces[j]
        first_line = _line_start(text, first.start)
        before = text[first_line : first.start]
        code_before = before.strip() != ""
        construct_line = _line_start(text, construct.start)
        if construct_line <= first.start and code_before:
            line, col = _line_col(text, first.start)
            raise FormatError(
                line,
                col,
                "the attributed construct shares a line with earlier code; "
                "put the attribute and its construct on lines of their own",
            )
        lead = text[construct_line : construct.start]
        indent = lead[: len(lead) - len(lead.lstrip(" \t"))]
        if code_before:
            region = first_line + len(before.rstrip())
            out = "\n"
        else:
            region = first_line
            out = ""
        prev_end = -1
        for k in range(i, j):
            piece = pieces[k]
            body = text[piece.start : piece.end]
            if piece.kind == "comment" and prev_end >= 0 and "\n" not in text[prev_end : piece.start]:
                out = out[:-1] + " " + body + "\n"
            else:
                out += indent + body + "\n"
            prev_end = piece.end
        out += indent
        edits.append((region, construct.start, out))
        i = j
    for start, end, repl in reversed(edits):
        text = text[:start] + repl + text[end:]
    return text


def format_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def format_sv0(text: str, honor_keep_layout: bool = True) -> str:
    return format_whitespace(layout_attributes(text, honor_keep_layout))


def main() -> int:
    p = argparse.ArgumentParser(description="Format .sv0 files (attribute layout and whitespace normalization).")
    p.add_argument("--check", action="store_true", help="Do not write; exit 1 if a file would change.")
    p.add_argument("paths", nargs="*", type=Path, help=".sv0 files or directories (default: none)")
    args = p.parse_args()
    paths: list[Path] = list(args.paths)
    if not paths:
        print("fmt_sv0: no paths given", file=sys.stderr)
        return 2

    files: list[Path] = []
    for raw in paths:
        path = raw.resolve()
        if path.is_dir():
            files.extend(sorted(path.rglob("*.sv0")))
        elif path.suffix == ".sv0":
            files.append(path)
    if not files:
        return 0

    changed = False
    failed = False
    for f in files:
        try:
            old = f.read_text(encoding="utf-8")
        except OSError as e:
            print(f"fmt_sv0: read {f}: {e}", file=sys.stderr)
            return 1
        try:
            new = format_sv0(old)
        except FormatError as e:
            print(f"fmt_sv0: {f}:{e}", file=sys.stderr)
            failed = True
            continue
        if old == new:
            continue
        changed = True
        if args.check:
            print(f"would reformat: {f}", file=sys.stderr)
            continue
        try:
            f.write_text(new, encoding="utf-8")
        except OSError as e:
            print(f"fmt_sv0: write {f}: {e}", file=sys.stderr)
            return 1
    if failed or (args.check and changed):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
