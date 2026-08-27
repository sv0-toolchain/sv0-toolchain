"""Assemble the native executable build pipeline (NEX-028).

Implements TEST-004
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §13.1's phase
order): `build_native_executable` is the first real wiring-together of
every module built so far — entry validation, runtime resolution, compiler
selection/probing, core-compiler invocation, emission classification,
staging, host compile, output publication, and human output. It contains
**no new logic of its own** beyond sequencing; every step delegates to an
already-mutation-tested module. This is the "one implementation of host
linking" product principle 10 calls for — later slices in this band (and
the eventual `sv0c --emit=exe` command surface) call this function rather
than re-deriving their own mini-pipeline.

`input_path` and `output_path` (when given) must already be absolute paths
— resolving a relative path against the invocation cwd is `native_exe_request`'s
job (NEX-003), not this function's.

`verified` contract mode takes a pre-computed `proof_path` (the
Z3-obligation-results file `CoreCompilerRequest.verified` expects) rather
than running Z3 itself — that orchestration is NEX-031's job, kept out of
this assembly to keep it pure composition.

Run `python3 scripts/native_exe_build.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from native_exe_argv_builder import build_dev_profile_argv, build_release_profile_argv
from native_exe_cc_probe import probe_compiler
from native_exe_cc_select import select_cc
from native_exe_core_compiler import CoreCompilerClient, CoreCompilerRequest
from native_exe_emit import classify_emission
from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_entry_reserved import validate_no_reserved_collisions
from native_exe_entry_scan import validate_entry_exists
from native_exe_entry_signature import validate_entry_signature
from native_exe_env import sanitized_child_env
from native_exe_host_compile import run_host_compile
from native_exe_human_output import format_success_message
from native_exe_output_path import default_output_path, ensure_output_parent_dir, validate_output_path
from native_exe_publish import publish_atomically
from native_exe_runtime import resolve_runtime_dir
from native_exe_runtime_manifest import verify_manifest
from native_exe_scratch import ScratchDir
from native_exe_staging import validate_staging_c, write_text_atomically

DEFAULT_COMPILER_PATH = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "build", "sv0-megatu-native")
)


@dataclass
class BuildResult:
    output_path: str
    message: str | None


def build_native_executable(
    input_kind: str,
    input_path: str,
    output_path: str | None,
    invocation_cwd: str,
    contract_mode: str = "runtime",
    proof_path: str | None = None,
    explicit_cc: str | None = None,
    compiler_path: str | None = None,
    quiet: bool = False,
    probe: bool = True,
    runtime_override=None,
    scratch_base_dir: str | None = None,
    keep_c_path: str | None = None,
    extra_cc_args: list[str] | None = None,
    profile: str = "dev",
) -> BuildResult:
    """Run the full R0 build pipeline for one file or project input.

    Raises `BuildError` (from whichever step fails) on any failure, per
    spec §13.1 — no step past a failure ever runs. `runtime_override`
    (a `RuntimeLocation`) exists purely for tests that need to force a
    RUNTIME-phase failure end to end (NEX-032) — production callers never
    pass it, letting `resolve_runtime_dir()` run normally. `scratch_base_dir`
    is a similar test-only seam (NEX-033) forcing this build's scratch dir
    to share a parent with a test's own neighbor directory, to make
    scratch-cleanup-scoping tests genuinely adjacency-sensitive. `keep_c_path`
    (NEX-040, `--keep-c`) retains the exact staging C there — written
    unconditionally right after `validate_staging_c` succeeds, so it survives
    whether the *later* host-compile/link step succeeds or fails (CLI-015,
    ART-012). `extra_cc_args` (NEX-050a) threads straight through to
    `build_dev_profile_argv`'s own seam of the same name -- production
    callers never pass it; `native_exe_sanitizer_build.py` is the one real
    caller, adding `-fsanitize=...` without duplicating this whole pipeline.
    `profile` (NEX-051c, `--profile=release`) selects
    `build_release_profile_argv` instead of `build_dev_profile_argv` --
    `"dev"` (the default) is byte-identical to this parameter not existing;
    any other value is a `BuildError(USAGE)` rather than a silent fallback,
    since §11.4 forbids silently falling back to a lower-precedence/default
    value for an invalid explicit setting.
    """
    # 0. Profile validation (NEX-051c) -- a pure usage-level check with no
    # dependency on the input at all, so it's rejected before ANY real work
    # runs (matching entry validation's own "usage errors first" precedent,
    # NEX-028 case5) rather than deep in the pipeline after the core
    # compiler has already run.
    if profile == "dev":
        build_argv = build_dev_profile_argv
    elif profile == "release":
        build_argv = build_release_profile_argv
    else:
        raise BuildError(DiagnosticPhase.USAGE, f"unknown profile {profile!r} (want 'dev' or 'release')")

    # 1. Entry validation (NEX-013/014/015/017) -- before anything else runs.
    validate_entry_exists(input_kind, input_path)
    validate_entry_signature(input_kind, input_path)
    validate_no_reserved_collisions(input_kind, input_path)

    # 2. Resolve + validate the output path (NEX-026).
    is_default_output = output_path is None
    final_output = output_path if output_path is not None else default_output_path(
        input_kind, input_path, invocation_cwd
    )
    validate_output_path(final_output)
    ensure_output_parent_dir(final_output, is_default=is_default_output)

    # 3. Runtime resolution + ABI manifest verification (NEX-019/020).
    runtime = runtime_override if runtime_override is not None else resolve_runtime_dir()
    verify_manifest(runtime)

    # 4. Host C compiler selection + capability probe (NEX-021/022).
    cc_path, _cc_selection = select_cc(explicit_cc, os.environ)
    if probe:
        probe_compiler(cc_path)

    # 5. Core-compiler invocation (NEX-011).
    resolved_compiler_path = compiler_path if compiler_path is not None else DEFAULT_COMPILER_PATH
    if input_kind == "project":
        control_value = CoreCompilerRequest.project(input_path)
    elif contract_mode == "disabled":
        control_value = CoreCompilerRequest.disabled(input_path)
    elif contract_mode == "verified":
        control_value = CoreCompilerRequest.verified(proof_path or "", input_path)
    else:
        control_value = CoreCompilerRequest.file(input_path)

    client = CoreCompilerClient(resolved_compiler_path)
    core_result = client.invoke(control_value)

    # 6. Emission protocol classification + staging validation (NEX-012/018).
    emission = classify_emission(core_result)
    validate_staging_c(emission.c_source)

    # 6b. Retain the staging C (NEX-040) -- unconditionally, before host
    # compile runs, so it survives a later host-compile/link failure too.
    if keep_c_path is not None:
        write_text_atomically(emission.c_source, keep_c_path)

    # 7. Scratch dir, argv, sanitized env, host compile (NEX-008/023/024/025).
    with ScratchDir(base_dir=scratch_base_dir) as scratch:
        program_c_path = os.path.join(scratch.path, "program.c")
        with open(program_c_path, "w", encoding="utf-8") as f:
            f.write(emission.c_source)
        tmp_output_path = os.path.join(scratch.path, "program.tmp-exe")

        argv = build_argv(cc_path, runtime, program_c_path, tmp_output_path, extra_cc_args=extra_cc_args)
        env = sanitized_child_env(os.environ)
        run_host_compile(argv, env, tmp_output_path)

        # 8. Atomic publication (NEX-007).
        publish_atomically(tmp_output_path, final_output)

    # 9. Human success output (NEX-027).
    message = None if quiet else format_success_message(final_output, "c", profile, contract_mode)
    return BuildResult(output_path=final_output, message=message)


def _selftest() -> int:
    import subprocess
    import tempfile

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        # Case 1: i32-returning main with println (AC-001/002).
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("hi from build_native_executable");\n    return 42;\n}\n')
        out = os.path.join(td, "hello_out")
        result = build_native_executable("file", src, out, td)
        if result.output_path != out or result.message is None:
            failures.append(f"case1: unexpected result: {result}")
        elif not os.path.isfile(out):
            failures.append("case1: output not created")
        else:
            proc = subprocess.run([out], capture_output=True, text=True)
            if proc.returncode != 42 or "hi from build_native_executable" not in proc.stdout:
                failures.append(f"case1: rc={proc.returncode} stdout={proc.stdout!r}")

        # Case 2: unit-returning main (AC-003).
        src2 = os.path.join(td, "unit.sv0")
        with open(src2, "w", encoding="utf-8") as f:
            f.write('fn main() -> () {\n    println("unit done");\n}\n')
        out2 = os.path.join(td, "unit_out")
        build_native_executable("file", src2, out2, td)
        proc2 = subprocess.run([out2], capture_output=True, text=True)
        if proc2.returncode != 0 or "unit done" not in proc2.stdout:
            failures.append(f"case2: rc={proc2.returncode} stdout={proc2.stdout!r}")

        # Case 3: default output path (no explicit -o) lands at build/native/<stem>.
        src3 = os.path.join(td, "defaulted.sv0")
        with open(src3, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 7;\n}\n")
        result3 = build_native_executable("file", src3, None, td, probe=False)
        expected_default = os.path.join(td, "build", "native", "defaulted")
        if result3.output_path != expected_default or not os.path.isfile(expected_default):
            failures.append(f"case3: expected default output at {expected_default}, got {result3}")

        # Case 4: quiet suppresses the success message.
        src4 = os.path.join(td, "quiet.sv0")
        with open(src4, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 0;\n}\n")
        out4 = os.path.join(td, "quiet_out")
        result4 = build_native_executable("file", src4, out4, td, quiet=True, probe=False)
        if result4.message is not None:
            failures.append(f"case4: expected no message under quiet, got {result4.message!r}")

        # Case 5 (the phase-ordering guarantee, §13.1): a no-main fixture is
        # rejected by entry validation *before* the core compiler ever runs --
        # confirmed here by checking no output was ever created, not just that
        # an exception was raised.
        src5 = os.path.join(td, "library.sv0")
        with open(src5, "w", encoding="utf-8") as f:
            f.write("pub fn add(a: i32, b: i32) -> i32 {\n    return a + b;\n}\n")
        out5 = os.path.join(td, "library_out")

        try:
            build_native_executable("file", src5, out5, td, probe=False)
            failures.append("case5: expected BuildError for a no-main fixture, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.ENTRY:
                failures.append(f"case5: expected ENTRY phase, got {exc.phase}")
        if os.path.exists(out5):
            failures.append("case5: no output should have been created for a rejected entry")

        # Case 6 (NEX-051c): profile="release" actually builds and runs
        # correctly (proves the release argv path is really wired, not
        # just defined), and its human message reports "profile=release".
        src6 = os.path.join(td, "release.sv0")
        with open(src6, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("release profile works");\n    return 6;\n}\n')
        out6 = os.path.join(td, "release_out")
        result6 = build_native_executable("file", src6, out6, td, probe=False, profile="release")
        if result6.message is None or "profile=release" not in result6.message:
            failures.append(f"case6: expected a profile=release message, got {result6.message!r}")
        elif not os.path.isfile(out6):
            failures.append("case6: release-profile build produced no output")
        else:
            proc6 = subprocess.run([out6], capture_output=True, text=True)
            if proc6.returncode != 6 or "release profile works" not in proc6.stdout:
                failures.append(f"case6: release binary misbehaved: rc={proc6.returncode} stdout={proc6.stdout!r}")

        # Case 7: an unknown profile value is a BuildError(USAGE), never a
        # silent fallback to dev (§11.4) -- and (the phase-ordering
        # guarantee, matching case5's precedent) rejected before ANY real
        # work runs, proven here with a NONEXISTENT input path: if profile
        # validation ran after entry validation, this would raise an INPUT/
        # ENTRY error instead, not USAGE.
        try:
            build_native_executable(
                "file", os.path.join(td, "does-not-exist.sv0"), out6, td, probe=False, profile="bogus"
            )
            failures.append("case7: expected BuildError for an unknown profile, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.USAGE:
                failures.append(
                    f"case7: expected USAGE phase (profile validated before entry checks), got {exc.phase}"
                )

    if failures:
        for f in failures:
            print(f"native_exe_build selftest FAIL: {f}")
        return 1

    print("native_exe_build: selftest OK (7 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_build: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
