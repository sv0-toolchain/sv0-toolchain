"""ASan/UBSan-instrumented dev-profile build wrapper (NEX-050a).

Implements TEST-007
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §26.7): wraps
the real `build_native_executable` (NEX-028) — never reimplements it — with
`-fsanitize=address,undefined` via `native_exe_argv_builder.build_dev_profile_argv`'s
`extra_cc_args` seam (NEX-050a), so a sanitizer build goes through exactly
the same pipeline (entry validation, staging, publication, ...) as an
ordinary dev build, just compiled with extra instrumentation flags.

Run `python3 scripts/native_exe_sanitizer_build.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import subprocess

from native_exe_build import BuildResult, build_native_executable

SANITIZE_FLAGS: list[str] = ["-fsanitize=address,undefined"]

# sv0c/runtime/lsan-suppressions.txt (NEX-050b), resolved relative to this
# file's own location the same way native_exe_runtime.py resolves the
# runtime bundle -- never a bare relative path, so this works regardless of
# invocation cwd.
LSAN_SUPPRESSIONS_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sv0c", "runtime", "lsan-suppressions.txt")
)


def sanitizer_env(base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Environment for RUNNING (not building) a sanitized binary: a copy of
    `base_env` (defaulting to `os.environ`) with `LSAN_OPTIONS` pointed at
    `lsan-suppressions.txt`.

    This file existed since NEX-050b but was never actually wired anywhere
    -- LeakSanitizer only consults `LSAN_OPTIONS=suppressions=<path>` when
    it's genuinely set in the child's environment; nothing set it, so the
    file was silently inert on every real Linux CI run until this was
    found (NEX-050c's own corpus job, native_exe_sanitizer_corpus.py) and
    fixed. Also sets `print_suppressions=0`: LSan's default behavior
    prints a "Suppressions used:" summary to stderr even when every leak
    was legitimately suppressed and the run is otherwise completely clean
    -- confirmed directly (a real Linux/Docker run), this alone would
    still fail every caller's "expect empty stderr" check despite nothing
    actually being wrong. Appends to any existing `LSAN_OPTIONS` a caller
    already set (colon-separated, LSan's own accepted format) rather than
    clobbering it.
    """
    env = dict(os.environ if base_env is None else base_env)
    existing = env.get("LSAN_OPTIONS", "")
    suppress_opts = f"suppressions={LSAN_SUPPRESSIONS_PATH}:print_suppressions=0"
    env["LSAN_OPTIONS"] = f"{existing}:{suppress_opts}" if existing else suppress_opts
    return env


def build_sanitized_executable(
    input_kind: str,
    input_path: str,
    output_path: str | None,
    invocation_cwd: str,
    **kwargs,
) -> BuildResult:
    """`build_native_executable`, always compiled with ASan+UBSan. Any
    keyword `build_native_executable` accepts (contract_mode, probe,
    quiet, ...) passes straight through; `extra_cc_args` is intentionally
    not overridable here -- a sanitizer build is exactly the dev build
    plus these flags, not a customizable variant.
    """
    kwargs.pop("extra_cc_args", None)
    return build_native_executable(
        input_kind, input_path, output_path, invocation_cwd, extra_cc_args=SANITIZE_FLAGS, **kwargs
    )


def _selftest() -> int:
    import tempfile

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    ub_fixture = os.path.abspath(
        os.path.join(this_dir, "..", "sv0c", "test", "behavior", "cases", "ub_arith_div_i32_min_by_neg1.sv0")
    )
    clean_fixture = os.path.abspath(
        os.path.join(this_dir, "..", "sv0c", "test", "behavior", "cases", "box_deref_chain_stress.sv0")
    )

    if not (os.path.isfile(ub_fixture) and os.path.isfile(clean_fixture)):
        print("native_exe_sanitizer_build selftest SKIP: NEX-048b fixtures not found")
        return 0

    with tempfile.TemporaryDirectory() as td:
        # Case 1: a real, deliberately-UB fixture is caught by UBSan at
        # runtime. On macOS/Clang, UBSan's DEFAULT mode is "print and
        # continue" (not fatal), so the process exits 0 and prints its own
        # "runtime error: ... cannot be represented in type 'int'" plus a
        # "UndefinedBehaviorSanitizer" summary line. On Linux/GCC (confirmed
        # via a real CI run -- this project's own suite had never once
        # reached this far in CI before KC-001/002/005 were fixed, so this
        # platform difference was never seen until now), integer division
        # overflow by -1 is a genuine hardware trap (SIGFPE) regardless of
        # UBSan: UBSan still prints its own "runtime error: ..." diagnostic
        # line FIRST, but the process is then killed by the trap before it
        # can print its own summary line -- ASan's signal handler intercepts
        # the SIGFPE instead and reports "AddressSanitizer: FPE ...". The
        # load-bearing signal either way is the "runtime error: ..."
        # diagnostic itself (proof UBSan's instrumentation genuinely fired
        # with the right reason), not which sanitizer's own name shows up
        # in whatever happens after that -- so accept either sanitizer's
        # brand name confirming the combined ASan+UBSan build's
        # instrumentation is real, not just the exact one that would print
        # last in the "print and continue" case.
        out_ub = os.path.join(td, "ub_out")
        result_ub = build_sanitized_executable("file", ub_fixture, out_ub, td, probe=False)
        proc_ub = subprocess.run([result_ub.output_path], capture_output=True, text=True, env=sanitizer_env())
        ub_stderr_lower = (proc_ub.stderr or "").lower()
        has_sanitizer_name = (
            "undefinedbehaviorsanitizer" in ub_stderr_lower or "addresssanitizer" in ub_stderr_lower
        )
        if "runtime error" not in ub_stderr_lower or not has_sanitizer_name:
            failures.append(
                f"UB fixture's sanitizer stderr didn't contain the expected UBSan diagnostic: {proc_ub.stderr!r}"
            )

        # Case 2: a genuinely clean fixture (048b's box-pool stress
        # program) still builds and runs correctly under the same
        # instrumentation, with its ordinary expected exit code (210).
        out_clean = os.path.join(td, "clean_out")
        result_clean = build_sanitized_executable("file", clean_fixture, out_clean, td, probe=False)
        proc_clean = subprocess.run([result_clean.output_path], capture_output=True, text=True, env=sanitizer_env())
        if proc_clean.returncode != 210:
            failures.append(
                f"clean fixture misbehaved under sanitizers: rc={proc_clean.returncode} stderr={proc_clean.stderr!r}"
            )

    if failures:
        for f in failures:
            print(f"native_exe_sanitizer_build selftest FAIL: {f}")
        return 1

    print("native_exe_sanitizer_build: selftest OK (2 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_sanitizer_build: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
