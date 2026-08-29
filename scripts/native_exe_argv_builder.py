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
    extra_cc_args: list[str] | None = None,
) -> list[str]:
    """The canonical R0 dev-profile argv (Appendix B), in exact logical order:
    dialect, optimization, debug info, [extra_cc_args], trusted include dir,
    program C, runtime C, output.

    `extra_cc_args` (NEX-050a) is an argv-native seam for callers that need
    one or more additional compiler flags -- e.g. `-fsanitize=address,undefined`
    for `native_exe_sanitizer_build.py` -- inserted as-is, one argv element
    each, right after the R0 dialect/optimization/debug flags and before the
    trusted include dir. Never a parsed flag string (§16.6); production
    callers never pass this (it stays `None`, producing byte-identical argv
    to before this parameter existed).
    """
    return [
        cc_path,
        "-std=gnu99",
        "-O0",
        "-g",
        *(extra_cc_args or []),
        f"-I{runtime.dir}",
        program_c_path,
        runtime.source,
        "-o",
        output_path,
    ]


def build_release_profile_argv(
    cc_path: str,
    runtime: RuntimeLocation,
    program_c_path: str,
    output_path: str,
    extra_cc_args: list[str] | None = None,
) -> list[str]:
    """The R1 release-profile argv (NEX-051a, §16.5): `-O2` -- explicitly
    NOT `-O3`, link-time optimization, `-ffast-math`, or `NDEBUG`-based
    contract removal, per §16.5's exact prohibition list.

    History: this argv used to also include `-fno-strict-aliasing`, the
    audit's (`native-executable-ub-audit.md`, NEX-048a) concluded
    mitigation for two real strict-aliasing violations (Sites 1/2: the
    box-pool pointer-cast deref, and the `lowering.sv0`/`codegen.sv0`
    `Value` cross-reinterpretation) that `-O2`'s type-based alias analysis
    was entitled to exploit. KC-004 cleanup pass (post-R1): both sites have
    since been fixed for real at the representation level
    (`sv0__box_deref_raw` now reads via `memcpy` into a same-typed local
    instead of a pointer-cast deref -- see `sv0_runtime.h`; Site 2 shared
    the identical macro, so the one fix covers both, confirmed by
    recompiling the full enum/struct/combo fixture set through the mega-TU
    compiler binary itself at `-O2` with no aliasing mitigation, output
    unchanged). No known live strict-aliasing violation remains, so the
    flag was removed rather than kept as unnecessary belt-and-suspenders --
    a future site should be fixed for real (as these were) or the flag
    re-added with a fresh, honest audit entry, not silently re-added on
    reflex.

    Otherwise identical in shape to `build_dev_profile_argv`: same dialect,
    same trusted-include-before-program-C ordering, same `extra_cc_args`
    seam.
    """
    return [
        cc_path,
        "-std=gnu99",
        "-O2",
        "-g",
        *(extra_cc_args or []),
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

    # extra_cc_args (NEX-050a): omitted -> byte-identical to the no-seam call;
    # supplied -> inserted after -g, before the trusted -I, each as its own
    # argv element (never joined into one string).
    argv_no_extra = build_dev_profile_argv(
        "/usr/bin/cc", runtime, "/scratch/program.c", "/scratch/program.tmp-exe"
    )
    argv_default_extra = build_dev_profile_argv(
        "/usr/bin/cc", runtime, "/scratch/program.c", "/scratch/program.tmp-exe", extra_cc_args=None
    )
    if argv_no_extra != argv_default_extra:
        failures.append("omitting extra_cc_args must be byte-identical to extra_cc_args=None")

    argv_sanitized = build_dev_profile_argv(
        "/usr/bin/cc",
        runtime,
        "/scratch/program.c",
        "/scratch/program.tmp-exe",
        extra_cc_args=["-fsanitize=address,undefined"],
    )
    if "-fsanitize=address,undefined" not in argv_sanitized:
        failures.append("extra_cc_args entry did not appear in the argv at all")
    elif argv_sanitized.index("-fsanitize=address,undefined") <= argv_sanitized.index("-g"):
        failures.append("extra_cc_args must come after -g")
    elif argv_sanitized.index("-fsanitize=address,undefined") >= argv_sanitized.index("-I/abs/runtime"):
        failures.append("extra_cc_args must come before the trusted -I")

    # Case 5 (NEX-051a): the release-profile argv has -O2, and explicitly
    # none of §16.5's prohibited flags (-O3, LTO, -ffast-math, NDEBUG-based
    # contract removal). KC-004 cleanup pass: -fno-strict-aliasing is gone
    # too -- both audit sites it mitigated are now fixed for real (see the
    # function's own docstring) -- so its ABSENCE is the thing asserted now,
    # not its presence.
    release_argv = build_release_profile_argv(
        "/usr/bin/cc", runtime, "/scratch/program.c", "/scratch/program.tmp-exe"
    )
    if "-O2" not in release_argv:
        failures.append("release argv missing -O2")
    if "-fno-strict-aliasing" in release_argv:
        failures.append(
            "release argv still has -fno-strict-aliasing -- KC-004 fixed both audit "
            "sites for real; re-adding this flag needs a fresh audit entry, not a revert"
        )
    prohibited = ["-O3", "-flto", "-ffast-math", "-DNDEBUG"]
    found_prohibited = [f for f in prohibited if f in release_argv]
    if found_prohibited:
        failures.append(f"release argv contains a §16.5-prohibited flag: {found_prohibited}")
    if "-std=c99" in release_argv:
        failures.append("release argv must never claim strict -std=c99 either (OD-005)")

    # Release argv also honors extra_cc_args, same as dev profile.
    release_argv_extra = build_release_profile_argv(
        "/usr/bin/cc",
        runtime,
        "/scratch/program.c",
        "/scratch/program.tmp-exe",
        extra_cc_args=["-fsanitize=address,undefined"],
    )
    if "-fsanitize=address,undefined" not in release_argv_extra:
        failures.append("release argv did not honor extra_cc_args")

    if failures:
        for f in failures:
            print(f"native_exe_argv_builder selftest FAIL: {f}")
        return 1

    print("native_exe_argv_builder: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_argv_builder: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
