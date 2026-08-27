"""No-blanket-`-w` acceptance check (NEX-049c).

Implements TEST-008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §26.6): "R0
removes blanket `-w` from the canonical driver... global warning
suppression is not an R1 completion strategy." NEX-049b's real
full-corpus run (`native_exe_warning_report.py`) already proves the
canonical driver's *behavior* is clean under `-Wall -Wextra` with zero
unclassified warnings across all 114 behavior-corpus fixtures. This
module adds the complementary *static* half of that acceptance check —
confirming the canonical argv builder's own source never contains a bare
`-w` token at all — so the "no blanket suppression" claim doesn't rest on
"the corpus happens to be clean today" alone.

This is the acceptance check NEX-058 (migrating the three legacy shell
scripts off their own `cc -std=c99 -O0 -w ...` recipes) can point back to,
rather than re-deriving its own warning-cleanliness evidence.

Run `python3 scripts/native_exe_no_blanket_suppression.py --selftest` for
the corpus.
"""

from __future__ import annotations

import os
import re

_BLANKET_W_RE = re.compile(r'(^|[\s,"\'])-w([\s,"\']|$)')

_CANONICAL_ARGV_MODULE = "native_exe_argv_builder.py"


class BlanketSuppressionError(Exception):
    """Raised when a bare `-w` token is found where it shouldn't be."""


def assert_no_blanket_suppression(source_text: str, label: str) -> None:
    """Raise `BlanketSuppressionError` if `source_text` contains a bare
    `-w` token (word-bounded, so it doesn't false-positive on `-Wall`,
    `-Wextra`, or any other `-W...` flag).
    """
    if _BLANKET_W_RE.search(source_text):
        raise BlanketSuppressionError(f"{label}: contains a blanket -w token")


def check_canonical_argv_builder(scripts_dir: str | None = None) -> None:
    """Check the real, shipped `native_exe_argv_builder.py` source."""
    if scripts_dir is None:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(scripts_dir, _CANONICAL_ARGV_MODULE)
    with open(path, encoding="utf-8") as f:
        source_text = f.read()
    assert_no_blanket_suppression(source_text, path)


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: the real, shipped canonical argv builder has no blanket -w.
    try:
        check_canonical_argv_builder()
    except BlanketSuppressionError as exc:
        failures.append(f"case1: canonical argv builder failed the check: {exc}")

    # Case 2: a bare -w IS caught when actually present.
    try:
        assert_no_blanket_suppression('argv = [cc_path, "-std=gnu99", "-w", "-O0"]', "synthetic")
        failures.append("case2: expected BlanketSuppressionError for a bare -w, none raised")
    except BlanketSuppressionError:
        pass

    # Case 3: -Wall/-Wextra/-Wno-foo do NOT false-positive (word-boundary check).
    try:
        assert_no_blanket_suppression('argv = [cc_path, "-Wall", "-Wextra", "-Wno-foo"]', "synthetic")
    except BlanketSuppressionError as exc:
        failures.append(f"case3: false positive on -Wall/-Wextra/-Wno-foo: {exc}")

    # Case 4: -w embedded at the start/end of the text (no surrounding
    # whitespace token boundaries provided by a list literal) is still caught.
    try:
        assert_no_blanket_suppression("-w", "synthetic-bare")
        failures.append("case4: expected BlanketSuppressionError for a bare -w with no other tokens")
    except BlanketSuppressionError:
        pass

    if failures:
        for f in failures:
            print(f"native_exe_no_blanket_suppression selftest FAIL: {f}")
        return 1

    print("native_exe_no_blanket_suppression: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_no_blanket_suppression: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
