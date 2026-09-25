#!/usr/bin/env python3
"""Verify the exact ``sv0cov`` submodule declaration and pin (CV-002).

sv0cov SPEC §8.2 / COV-PKG-015 / COV-GOV-005: the root ``.gitmodules`` entry
for sv0cov has exact name ``sv0cov``, exact path ``sv0cov``, exact URL
``git@github.com:sv0-toolchain/sv0cov.git``, and no other key (no ``branch``,
``update``, ``ignore``, ``shallow``, alias, or case variant). The commit is
selected only by a mode-160000 gitlink, and a present checkout must sit at that
commit. A missing or differently checked-out submodule fails visibly.

The gitlink is read from the index (``git ls-files -s``) so the guard can run
before ``git commit`` when the pointer is staged. When the workspace is not a
git work tree, only the ``.gitmodules`` text checks run.

``--selftest`` exercises the ``.gitmodules`` checks against in-memory fixtures.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

NAME = "sv0cov"
PATH = "sv0cov"
URL = "git@github.com:sv0-toolchain/sv0cov.git"

RE_SECTION = re.compile(r'^\s*\[\s*submodule\s+"([^"]*)"\s*\]\s*$')
RE_ANY_SECTION = re.compile(r"^\s*\[")
RE_KEY = re.compile(r"^\s*([A-Za-z][A-Za-z0-9-]*)\s*=\s*(.*?)\s*$")


def parse_gitmodules(text: str) -> list[tuple[str, list[tuple[str, str]]]]:
    """Return ``[(section_name, [(key, value), ...]), ...]`` in file order.

    Non-submodule sections are returned with name ``"<other>"`` so an entry
    hidden under an unexpected header is still inspected.
    """
    sections: list[tuple[str, list[tuple[str, str]]]] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", ";")):
            continue
        m = RE_SECTION.match(line)
        if m:
            sections.append((m.group(1), []))
            continue
        if RE_ANY_SECTION.match(line):
            sections.append(("<other>", []))
            continue
        k = RE_KEY.match(line)
        if k and sections:
            sections[-1][1].append((k.group(1), k.group(2)))
        elif k:
            sections.append(("<preamble>", [(k.group(1), k.group(2))]))
    return sections


def check_gitmodules(text: str) -> list[str]:
    errors: list[str] = []
    sections = parse_gitmodules(text)
    exact = [s for s in sections if s[0] == NAME]
    if len(exact) != 1:
        errors.append(f'expected exactly one [submodule "{NAME}"] section, found {len(exact)}')
    else:
        keys = exact[0][1]
        names = [k.lower() for k, _ in keys]
        if sorted(names) != ["path", "url"] or len(names) != 2:
            errors.append(f'[submodule "{NAME}"] must have exactly keys path, url; got {[k for k, _ in keys]}')
        for k, v in keys:
            if k == "path" and v != PATH:
                errors.append(f"path must be exactly {PATH!r}, got {v!r}")
            if k == "url" and v != URL:
                errors.append(f"url must be exactly {URL!r}, got {v!r}")
            if k not in ("path", "url"):
                errors.append(f"forbidden key {k!r} in sv0cov entry")
    # No other section may alias the sv0cov path, name, or repository.
    for name, keys in sections:
        if name == NAME:
            continue
        if name.lower() == NAME:
            errors.append(f"case-variant submodule name {name!r}")
        for k, v in keys:
            if k.lower() == "path" and v.strip("/").lower() == PATH:
                errors.append(f"section {name!r} also claims path {v!r}")
            if k.lower() == "url" and "sv0cov" in v.lower():
                errors.append(f"section {name!r} has an sv0cov URL alias {v!r}")
    return errors


def git(root: Path, *args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


def check_gitlink(root: Path) -> list[str]:
    if git(root, "rev-parse", "--is-inside-work-tree") is None:
        print("verify_sv0cov_submodule: not a git work tree; skipping gitlink checks")
        return []
    errors: list[str] = []
    staged = (git(root, "ls-files", "-s", "--", PATH) or "").strip()
    m = re.fullmatch(r"(\d{6}) ([0-9a-f]{40}) \d\t" + re.escape(PATH), staged)
    if not m:
        return [f"no index entry for {PATH!r} (got {staged!r})"]
    mode, sha = m.groups()
    if mode != "160000":
        errors.append(f"{PATH} must be a mode-160000 gitlink, got mode {mode}")
        return errors
    sub = root / PATH
    if not (sub / ".git").exists():
        errors.append(f"submodule {PATH} is not initialized (run: git submodule update --init {PATH})")
        return errors
    head = (git(sub, "rev-parse", "HEAD") or "").strip()
    if head != sha:
        errors.append(f"submodule {PATH} HEAD {head or '?'} != pinned gitlink {sha}")
    return errors


def selftest() -> int:
    good = f'[submodule "{NAME}"]\n\tpath = {PATH}\n\turl = {URL}\n'
    cases = {
        "exact": (good, True),
        "extra-branch": (good + "\tbranch = main\n", False),
        "https-url": (good.replace(URL, "https://github.com/sv0-toolchain/sv0cov.git"), False),
        "case-name": (good.replace(f'"{NAME}"', '"Sv0cov"'), False),
        "wrong-path": (good.replace(f"path = {PATH}", "path = tools/sv0cov"), False),
        "missing": ('[submodule "sv0c"]\n\tpath = sv0c\n\turl = git@github.com:sv0-toolchain/sv0c.git\n', False),
        "alias-section": (good + '[submodule "cov"]\n\tpath = cov\n\turl = git@github.com:sv0-toolchain/sv0cov.git\n', False),
        "duplicate": (good + good, False),
        "with-neighbors": ('[submodule "sv0c"]\n\tpath = sv0c\n\turl = git@github.com:sv0-toolchain/sv0c.git\n' + good, True),
    }
    failed = 0
    for name, (text, ok) in cases.items():
        got = not check_gitmodules(text)
        if got != ok:
            failed += 1
            print(f"selftest FAIL {name}: expected ok={ok}, got errors={check_gitmodules(text)}")
    if failed:
        return 1
    print(f"verify_sv0cov_submodule selftest: {len(cases)} cases OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path("."))
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    root = args.root.resolve()
    gm = root / ".gitmodules"
    if not gm.is_file():
        print("verify_sv0cov_submodule: .gitmodules missing", file=sys.stderr)
        return 1
    errors = check_gitmodules(gm.read_text(encoding="utf-8")) + check_gitlink(root)
    for e in errors:
        print(f"verify_sv0cov_submodule: {e}", file=sys.stderr)
    if errors:
        return 1
    print("verify_sv0cov_submodule: exact .gitmodules entry + pinned gitlink OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
