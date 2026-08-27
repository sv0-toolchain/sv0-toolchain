"""Central dev-profile argv builder (NEX-023).

Implements TOOL-004/RT-006
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` Appendix B):
one canonical function builds the R0 development-profile host-compiler
argv, so every caller (tests, and eventually the real driver) constructs the
identical command line — no duplicated recipes (GOV-008, product principle
10: "one implementation of host linking").

`-std=gnu99`, not `-std=c99` (OD-005): `sv0c/runtime/sv0_runtime.h` already
uses GCC/Clang statement-expression extensions (confirmed during the NEX-016
investigation), so `-std=c99` would already be a false conformance claim.

Run `python3 scripts/native_exe_argv_builder.py --selftest` for the corpus.
"""

from __future__ import annotations

from native_exe_runtime import RuntimeLocation


def build_dev_profile_argv(
    cc_path: str,
    runtime: RuntimeLocation,
    program_c_path: str,
    output_path: str,
) -> list[str]:
    """The canonical R0 dev-profile argv (Appendix B), in exact logical order:
    dialect, optimization, debug info, trusted include dir, program C,
    runtime C, output.
    """
    return [
        cc_path,
        "-std=gnu99",
        "-O0",
        "-g",
        f"-I{runtime.dir}",
        program_c_path,
        runtime.source,
        "-o",
        output_path,
    ]


def _selftest() -> int:
    failures: list[str] = []

    runtime = RuntimeLocation(
        dir="/abs/runtime",
        header="/abs/runtime/sv0_runtime.h",
        source="/abs/runtime/sv0_runtime.c",
    )

    argv = build_dev_profile_argv("/usr/bin/cc", runtime, "/scratch/program.c", "/scratch/program.tmp-exe")

    expected = [
        "/usr/bin/cc",
        "-std=gnu99",
        "-O0",
        "-g",
        "-I/abs/runtime",
        "/scratch/program.c",
        "/abs/runtime/sv0_runtime.c",
        "-o",
        "/scratch/program.tmp-exe",
    ]
    if argv != expected:
        failures.append(f"argv mismatch:\n  got:      {argv}\n  expected: {expected}")

    # The trusted include dir must precede the program/runtime C files (TOOL-007's
    # ordering half — the sanitized-env half is NEX-024).
    if argv.index("-I/abs/runtime") > argv.index("/scratch/program.c"):
        failures.append("trusted -I must precede the program C file in argv order")

    # -std=gnu99, never -std=c99 (OD-005).
    if "-std=c99" in argv:
        failures.append("argv must never claim strict -std=c99 (OD-005)")

    if failures:
        for f in failures:
            print(f"native_exe_argv_builder selftest FAIL: {f}")
        return 1

    print("native_exe_argv_builder: selftest OK (3 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_argv_builder: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
