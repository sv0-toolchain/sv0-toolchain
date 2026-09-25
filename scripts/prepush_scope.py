#!/usr/bin/env python3
"""Decide how much of the pre-push suite a push needs, from the paths it changes.

Reads NUL-separated changed paths on stdin (`git diff --name-only -z`, gitlinks
appear as their submodule path) and prints one line:

  full                  run the whole suite (`./scripts/sv0 test`)
  light [group ...]     run `./scripts/sv0 test-light [group ...]` (guards +
                        doctests, plus the stages the named groups feed)
  skip                  nothing to run (sv0c repo, docs-only)

Conservative by construction: a path is only treated as cheap if it matches an
explicit rule below; ANYTHING unrecognized makes the answer `full`. So adding a
new kind of file can only cost time, never silently skip coverage.

Usage: prepush_scope.py --repo parent|sv0c < paths      |      --selftest
"""
from __future__ import annotations

import sys

DOC_SUFFIXES = (".md", ".Rmd")
DOC_NAMES = {"LICENSE", "LICENSE-MIT", "LICENSE-APACHE", "CHANGELOG", ".gitignore",
             ".mcp.json", "CITATION.cff"}
DOC_PREFIXES = (".claude/", "docs/", ".github/")

# Parent repo: gitlinks whose contents no compiler/VM stage consumes -> the
# guards (submodule pin / scan checks) are the only thing that reads them.
GUARD_ONLY_GITLINKS = {"sv0cov", "sv0-mcp", "sv0doc"}
# Gitlinks feeding specific stages (see run_test_light).
GROUP_GITLINKS = {"sv0-mathlib": "mathlib", "sv0-strings": "strings"}


def _is_doc(path: str) -> bool:
    if path.endswith(DOC_SUFFIXES) or path in DOC_NAMES:
        return True
    if path.startswith(DOC_PREFIXES):
        return True
    # task tracking data (guards validate it) -- but not task scripts.
    return path.startswith("task/") and path.endswith(".json")


def classify_parent(paths: list[str]) -> str:
    groups: set[str] = set()
    for p in paths:
        if p in GROUP_GITLINKS:
            groups.add(GROUP_GITLINKS[p])
        elif p in GUARD_ONLY_GITLINKS or _is_doc(p):
            continue
        else:
            return "full"
    return "light" + "".join(f" {g}" for g in sorted(groups))


def classify_sv0c(paths: list[str]) -> str:
    for p in paths:
        if not (_is_doc(p) or p.startswith("doc/") or p == "PROGRESS.md"):
            return "full"
    return "skip"


def classify(repo: str, paths: list[str]) -> str:
    paths = [p for p in paths if p]
    if not paths:
        return "skip"
    return classify_parent(paths) if repo == "parent" else classify_sv0c(paths)


def _selftest() -> int:
    cases = [
        ("parent", [], "skip"),
        ("parent", ["task/foo.Rmd", "README.md"], "light"),
        ("parent", ["sv0cov", "sv0-mcp", "sv0doc"], "light"),
        ("parent", ["sv0-mathlib"], "light mathlib"),
        ("parent", ["sv0-strings", "sv0-mathlib", "CHANGELOG.md"], "light mathlib strings"),
        ("parent", [".github/workflows/ci.yml"], "light"),
        ("parent", ["sv0c"], "full"),
        ("parent", ["sv0vm"], "full"),
        ("parent", ["scripts/sv0"], "full"),
        ("parent", ["lib/shell/common.sh"], "full"),
        ("parent", ["Makefile"], "full"),
        ("parent", ["README.md", "scripts/x.py"], "full"),
        ("parent", ["something/unknown.bin"], "full"),
        ("parent", ["task/sv0c-milestone-1/02-integration-test.sh"], "full"),
        ("parent", ["task/milestone-orientation.json"], "light"),
        ("sv0c", ["doc/foo.md", "PROGRESS.md"], "skip"),
        ("sv0c", ["doc/foo.md", "sml-legacy/main.sml"], "full"),
        ("sv0c", ["lib/lexer.sv0"], "full"),
        ("sv0c", ["Makefile"], "full"),
    ]
    bad = 0
    for repo, paths, want in cases:
        got = classify(repo, paths)
        if got != want:
            bad += 1
            print(f"prepush_scope selftest FAIL: {repo} {paths} -> {got!r}, want {want!r}",
                  file=sys.stderr)
    if bad:
        return 1
    print(f"prepush_scope: selftest OK ({len(cases)} cases)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    repo = "parent"
    if "--repo" in argv:
        repo = argv[argv.index("--repo") + 1]
    if repo not in ("parent", "sv0c"):
        print(f"prepush_scope: unknown --repo {repo!r}", file=sys.stderr)
        return 2
    paths = sys.stdin.buffer.read().decode("utf-8", "surrogateescape").split("\0")
    print(classify(repo, paths))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
