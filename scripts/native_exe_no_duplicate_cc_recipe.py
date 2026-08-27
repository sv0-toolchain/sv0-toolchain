"""Static duplication guard: no manual `cc -std=` recipe outside the canonical driver (NEX-058, GOV-008).

Implements GOV-008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "the
canonical host-link implementation SHALL be shared by user commands and
integration tests." NEX-058 migrated the three legacy shell scripts that
used to hand-roll `cc -std=c99 -O0 -w ...` recipes
(`pc3b6-native-project-acceptance.sh`, `sv0-megatu-native-parity.sh`,
`sv0-megatu-corpus-parity.sh`) onto `native_exe_canonical_compile.py`.
This guard fails closed if any future script reintroduces a manual
`cc -std=`/`gcc -std=`/`clang -std=` invocation, catching a regression at
the source-scan level rather than trusting every future contributor to
remember not to.

See `_EXEMPT_BASENAMES` below for exactly which files this guard exempts
and why -- the canonical driver's own argv construction site, files whose
docstrings quote the pattern for documentation only, and (recorded
honestly) a handful of pre-existing manual recipes this guard's own first
run surfaced that were out of NEX-058's approved scope, flagged as a
separate follow-up rather than silently left unenforced.

Run `python3 scripts/native_exe_no_duplicate_cc_recipe.py --selftest` for
the corpus.
"""

from __future__ import annotations

import os
import re

_RECIPE_RE = re.compile(r"\b(?:cc|gcc|clang)[\s,\"']+-std=")

# Files legitimately allowed to contain the pattern: the canonical argv
# builder (constructs it as real argv), this guard's own source (which
# quotes the pattern in prose/regex form for documentation), and the
# canonical-compile CLI + no-blanket-`-w` modules (whose own docstrings
# quote the exact legacy pattern they replace/check for, for documentation).
_EXEMPT_BASENAMES = {
    "native_exe_argv_builder.py",
    "native_exe_no_duplicate_cc_recipe.py",
    "native_exe_canonical_compile.py",
    "native_exe_no_blanket_suppression.py",
    # Pre-existing, real manual `cc -std=` recipes this guard's own first
    # run surfaced -- NOT the three shell scripts NEX-058 was scoped to
    # migrate. Deliberately exempted rather than silently migrated here:
    # spec S26.5 explicitly sanctions "the manual recipe is a differential
    # oracle" during migration, and retiring THESE specific scripts was
    # never part of NEX-058's approved scope. Flagged as a real follow-up
    # (not fixed inline) -- see the spawned task from this same slice.
    "verify_behavior_corpus_native.py",
    "verify_contract_mode.py",
    "assemble-sv0-megaTU.py",
}


def find_duplicate_recipes(scripts_dir: str) -> list[str]:
    """Scan every `.py`/`.sh` file directly inside `scripts_dir` (not
    recursively -- this project keeps all its scripts flat in one
    directory) for a manual `cc -std=`/`gcc -std=`/`clang -std=` recipe.
    Returns the list of offending file paths (empty = clean).
    """
    offenders: list[str] = []
    for name in sorted(os.listdir(scripts_dir)):
        if name in _EXEMPT_BASENAMES:
            continue
        if not (name.endswith(".py") or name.endswith(".sh")):
            continue
        path = os.path.join(scripts_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        if _RECIPE_RE.search(content):
            offenders.append(path)
    return offenders


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    scripts_dir = os.path.dirname(os.path.abspath(__file__))

    # Case 1: the real, shipped scripts/ directory is clean (the actual
    # regression-prevention this guard exists for).
    offenders = find_duplicate_recipes(scripts_dir)
    if offenders:
        failures.append(f"case1: real scripts/ directory has manual cc recipes: {offenders}")

    # Case 2: a synthetic directory WITH a violating script is caught.
    with tempfile.TemporaryDirectory() as td:
        bad_script = os.path.join(td, "hypothetical-new-script.sh")
        with open(bad_script, "w", encoding="utf-8") as f:
            f.write('#!/usr/bin/env bash\ncc -std=c99 -O0 -w -I "$RT" "$c" -o "$bin"\n')
        offenders2 = find_duplicate_recipes(td)
        if not offenders2:
            failures.append("case2: a synthetic manual-cc-recipe script was not caught")

    # Case 3: gcc/clang variants are caught too, not just cc.
    with tempfile.TemporaryDirectory() as td:
        for tool in ("gcc", "clang"):
            script = os.path.join(td, f"uses-{tool}.py")
            with open(script, "w", encoding="utf-8") as f:
                f.write(f'subprocess.run(["{tool}", "-std=c99", "prog.c"])\n')
        offenders3 = find_duplicate_recipes(td)
        if len(offenders3) != 2:
            failures.append(f"case3: expected both gcc/clang variants caught, got {offenders3}")

    # Case 4: an ordinary script mentioning "-std=gnu99" WITHOUT a
    # preceding cc/gcc/clang token (e.g. quoting it in a comment about
    # something else) is NOT flagged -- this guard targets the specific
    # tool-plus-flag pattern, not the flag alone.
    with tempfile.TemporaryDirectory() as td:
        clean_script = os.path.join(td, "mentions-flag-only.py")
        with open(clean_script, "w", encoding="utf-8") as f:
            f.write('# the canonical dialect is "-std=gnu99", constructed elsewhere\n')
        offenders4 = find_duplicate_recipes(td)
        if offenders4:
            failures.append(f"case4: a bare flag mention (no cc/gcc/clang token) was incorrectly flagged: {offenders4}")

    if failures:
        for f in failures:
            print(f"native_exe_no_duplicate_cc_recipe selftest FAIL: {f}")
        return 1

    print("native_exe_no_duplicate_cc_recipe: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_no_duplicate_cc_recipe: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
