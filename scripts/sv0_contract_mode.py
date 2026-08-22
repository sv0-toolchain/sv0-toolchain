#!/usr/bin/env python3
"""M4-S-025: read `[build] contract-mode` from an sv0.toml file.

Prints the value (runtime | verified | disabled) on stdout, or nothing if the
file is absent or the key is unset. Deliberately tiny — a full TOML parser is not
warranted for one key. Recognizes the `contract-mode` (or `contract_mode`) key
inside the `[build]` table. The shell driver applies precedence: an explicit
`--contract-mode=` flag overrides this file value, which overrides the default
`runtime`.
"""
from __future__ import annotations
import re, sys
from pathlib import Path

KEY_RE = re.compile(r'^\s*contract[-_]mode\s*=\s*"?([A-Za-z]+)"?\s*(?:#.*)?$')
SECTION_RE = re.compile(r'^\s*\[([^\]]+)\]\s*(?:#.*)?$')


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: sv0_contract_mode.py <sv0.toml>", file=sys.stderr)
        return 2
    p = Path(argv[1])
    if not p.is_file():
        return 0
    section = ""
    for line in p.read_text().splitlines():
        ms = SECTION_RE.match(line)
        if ms:
            section = ms.group(1).strip()
            continue
        if section == "build":
            mk = KEY_RE.match(line)
            if mk:
                print(mk.group(1).strip())
                return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
