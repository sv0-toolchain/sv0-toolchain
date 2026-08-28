"""Supported host C compiler family/version matrix (TOOL-013).

Implements TOOL-013
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "Supported
compiler families/versions SHALL be pinned in release evidence." Red test:
"Matrix manifest validation."

This is a *declared support claim* -- the set of compiler families/version
floors this release states it supports -- distinct from
`native_exe_cc_probe.probe_compiler`'s real, per-build capability check
(TOOL-005: does THIS compiler actually compile+link+run a minimal hosted
program). A compiler can pass the real probe and still be outside the
declared support matrix (e.g. an ancient GCC that happens to still work);
this module records the claim, it does not gate builds -- `probe_compiler`
already does the actual gating, and stays the sole gate (this module adds
declared intent on top, it does not replace or duplicate that check).

The version floors below are grounded in what this project has actually
exercised, not invented: Ubuntu 22.04 (this project's pinned CI image,
`.github/workflows/ci.yml`) ships GCC 11 and Clang 14 by default/via
`clang-14`; this dev machine's Apple Clang tracks Apple's own version
numbering (not upstream LLVM majors), which is why the Clang floor is
expressed loosely enough to include both, and Apple Clang is accepted as
a supported "clang"-family compiler regardless of its exact version
string -- `native_exe_cc_probe.probe_compiler`'s real compile+link+run
check is what actually decides fitness for an Apple Clang build, this
matrix only declares that the *family* is supported.

Run `python3 scripts/native_exe_supported_compilers.py --selftest` for
the corpus.
"""

from __future__ import annotations

SUPPORTED_COMPILER_MATRIX = [
    {
        "family": "gcc",
        "minimum_version": "11",
        "note": "Ubuntu 22.04's default `gcc` package (this project's pinned CI image).",
    },
    {
        "family": "clang",
        "minimum_version": "14",
        "note": (
            "Ubuntu 22.04's `clang-14` package (native-exe-clang CI leg) and Apple Clang "
            "(macOS developer builds, verified throughout this project's own development) -- "
            "Apple Clang's version string does not track upstream LLVM majors 1:1, so this "
            "floor is a declared-support statement, not a parsed numeric gate; "
            "native_exe_cc_probe.probe_compiler's real compile+link+run check is what "
            "actually decides fitness for any specific Apple Clang build."
        ),
    },
]


def validate_supported_compiler_matrix(matrix: list[dict]) -> None:
    """Raise `ValueError` if `matrix` is malformed: every entry needs a
    non-empty `family`, `minimum_version`, and `note`; no family may repeat.
    """
    seen_families: set[str] = set()
    for entry in matrix:
        for key in ("family", "minimum_version", "note"):
            if not entry.get(key):
                raise ValueError(f"supported-compiler matrix entry missing/empty {key!r}: {entry!r}")
        family = entry["family"]
        if family in seen_families:
            raise ValueError(f"supported-compiler matrix has a duplicate family: {family!r}")
        seen_families.add(family)


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: the real, shipped matrix is well-formed.
    try:
        validate_supported_compiler_matrix(SUPPORTED_COMPILER_MATRIX)
    except ValueError as exc:
        failures.append(f"case1: the real matrix failed validation: {exc}")

    # Case 2: the real matrix actually covers gcc and clang (the two
    # families this project's own CI matrix and cc_probe classify).
    families = {entry["family"] for entry in SUPPORTED_COMPILER_MATRIX}
    if families != {"gcc", "clang"}:
        failures.append(f"case2: expected exactly {{'gcc', 'clang'}}, got {families}")

    # Case 3: a missing field is rejected.
    try:
        validate_supported_compiler_matrix([{"family": "gcc", "minimum_version": "11"}])
        failures.append("case3: expected ValueError for a missing note, none raised")
    except ValueError:
        pass

    # Case 4: an empty-string field is rejected (not just a missing key).
    try:
        validate_supported_compiler_matrix([{"family": "gcc", "minimum_version": "", "note": "x"}])
        failures.append("case4: expected ValueError for an empty minimum_version, none raised")
    except ValueError:
        pass

    # Case 5: a duplicate family is rejected.
    try:
        validate_supported_compiler_matrix(
            [
                {"family": "gcc", "minimum_version": "11", "note": "x"},
                {"family": "gcc", "minimum_version": "12", "note": "y"},
            ]
        )
        failures.append("case5: expected ValueError for a duplicate family, none raised")
    except ValueError:
        pass

    if failures:
        for f in failures:
            print(f"native_exe_supported_compilers selftest FAIL: {f}")
        return 1

    print("native_exe_supported_compilers: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_supported_compilers: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
