#!/usr/bin/env python3
"""Extract ```sv0 doctest ...``` blocks from Markdown and run them via sv0c --target=vm + sv0vm.

Fence line format (all attributes optional):
  ```sv0 doctest name=foo expect_exit=0
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path


FENCE_START = re.compile(
    r"^```sv0\s+doctest(?:\s+(.+))?\s*$",
    re.IGNORECASE,
)


def parse_attrs(s: str | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not s or not s.strip():
        return out
    for part in s.split():
        if "=" in part:
            k, _, v = part.partition("=")
            out[k.strip()] = v.strip()
    return out


def sml_string_lit(path: str) -> str:
    esc = path.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{esc}"'


def extract_blocks(md: str) -> list[tuple[str, str, dict[str, str]]]:
    """Return list of (name, body, attrs)."""
    lines = md.splitlines(keepends=True)
    i = 0
    blocks: list[tuple[str, str, dict[str, str]]] = []
    while i < len(lines):
        m = FENCE_START.match(lines[i].rstrip("\n"))
        if not m:
            i += 1
            continue
        attrs = parse_attrs(m.group(1))
        i += 1
        body_lines: list[str] = []
        while i < len(lines):
            if lines[i].startswith("```"):
                break
            body_lines.append(lines[i])
            i += 1
        if i < len(lines) and lines[i].startswith("```"):
            i += 1
        name = attrs.get("name", f"block_{len(blocks)}")
        body = "".join(body_lines)
        blocks.append((name, body, attrs))
    return blocks


def run_one(
    sv0c_root: Path,
    sv0vm_root: Path,
    name: str,
    body: str,
    expect_exit: int,
) -> tuple[bool, str]:
    with tempfile.TemporaryDirectory(prefix="sv0_doctest_") as tmp:
        tdir = Path(tmp)
        src = tdir / "snippet.sv0"
        src.write_text(body, encoding="utf-8")
        log = tdir / "compile.log"
        sml_cmd = (
            f'CM.make "sources.cm"; Main.main ((), ["--target=vm", '
            f"{sml_string_lit(str(src))}]);"
        )
        cmd_compile = (
            f"cd {shlex.quote(str(sv0c_root))} && echo {shlex.quote(sml_cmd)} | sml"
        )
        r = subprocess.run(
            cmd_compile,
            shell=True,
            capture_output=True,
            text=True,
        )
        log.write_text(r.stdout + r.stderr, encoding="utf-8")
        if r.returncode != 0 or "Error:" in r.stdout + r.stderr:
            return False, f"{name}: compile failed (see {log})"
        sv0b = sv0c_root / "build" / "vm" / "snippet.sv0b"
        if not sv0b.is_file():
            return False, f"{name}: missing {sv0b}"
        env = {**os.environ, "SV0B": str(sv0b.resolve())}
        r2 = subprocess.run(
            f"cd {shlex.quote(str(sv0vm_root))} && sml < scripts/run_sv0b.sml",
            shell=True,
            capture_output=True,
            text=True,
            env=env,
        )
        out = r2.stdout + r2.stderr
        m = re.search(r"^vm_exit:(-?\d+)\s*$", out, re.MULTILINE)
        if not m:
            return False, f"{name}: no vm_exit in output"
        got = int(m.group(1))
        if got != expect_exit:
            return False, f"{name}: exit {got}, expected {expect_exit}"
        return True, name


def main() -> int:
    ap = argparse.ArgumentParser(description="Run sv0 doctests from Markdown.")
    ap.add_argument("--root", type=Path, required=True, help="sv0-toolchain root")
    ap.add_argument("markdown", nargs="+", type=Path, help="Markdown files to scan")
    args = ap.parse_args()
    root: Path = args.root.resolve()
    sv0c = root / "sv0c"
    sv0vm = root / "sv0vm"
    if not sv0c.is_dir() or not sv0vm.is_dir():
        print("sv0_doctest: need sv0c/ and sv0vm/ under root", file=sys.stderr)
        return 1

    failures: list[str] = []
    total = 0
    for md_path in args.markdown:
        text = md_path.read_text(encoding="utf-8")
        for name, body, attrs in extract_blocks(text):
            total += 1
            exp = int(attrs.get("expect_exit", "0"))
            ok, msg = run_one(sv0c, sv0vm, f"{md_path.name}:{name}", body.strip() + "\n", exp)
            if ok:
                print(f"  OK  {msg}")
            else:
                print(f"  FAIL {msg}", file=sys.stderr)
                failures.append(msg)

    print(f"doctests: {total - len(failures)}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
