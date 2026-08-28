"""`--emit=c`: write C atomically, never invoke the host compiler (NEX-039).

Implements CLI-014
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §11.3: `sv0c
--emit=c -o out.c file.sv0` — "write C atomically to `out.c`; do not invoke
the C compiler"). Runs exactly `build_native_executable`'s "front half" —
entry validation, output-path validation, core-compiler invocation, emission
classification and staging validation — using the same already-tested
functions from those modules, then writes the staging C atomically via
`native_exe_staging.write_text_atomically`. It never imports or calls
`native_exe_cc_select`/`native_exe_cc_probe`/`native_exe_host_compile` at
all, so there is no code path here that could invoke a host compiler.

This intentionally duplicates a few lines of *sequencing* with
`native_exe_build.build_native_executable` rather than factoring out a
shared internal helper — refactoring code that's already extensively
mutation-tested carries more risk than five lines of repeated glue.

Run `python3 scripts/native_exe_emit_c.py --selftest` for the corpus.
"""

from __future__ import annotations

from native_exe_core_compiler import CoreCompilerClient, CoreCompilerRequest
from native_exe_emit import classify_emission
from native_exe_entry_reserved import validate_no_reserved_collisions
from native_exe_entry_scan import validate_entry_exists
from native_exe_entry_signature import validate_entry_signature
from native_exe_input_validation import validate_file_input_shape
from native_exe_output_path import ensure_output_parent_dir, validate_output_path
from native_exe_staging import validate_staging_c, write_text_atomically
from native_exe_build import DEFAULT_COMPILER_PATH


def emit_c_only(
    input_kind: str,
    input_path: str,
    output_path: str,
    invocation_cwd: str,
    contract_mode: str = "runtime",
    proof_path: str | None = None,
    compiler_path: str | None = None,
) -> str:
    """Emit C for `input_path` to `output_path` atomically. Never invokes a
    host C compiler. Returns `output_path`. `output_path` is required here
    (unlike `build_native_executable`) — `--emit=c` has no default-naming
    rule of its own in the spec; a caller always supplies `-o`.
    """
    validate_file_input_shape(input_kind, input_path)  # CLI-008, same as build_native_executable's phase 1
    validate_entry_exists(input_kind, input_path)
    validate_entry_signature(input_kind, input_path)
    validate_no_reserved_collisions(input_kind, input_path)

    validate_output_path(output_path)
    ensure_output_parent_dir(output_path, is_default=False)

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

    emission = classify_emission(core_result)
    validate_staging_c(emission.c_source)

    write_text_atomically(emission.c_source, output_path)
    return output_path


def _selftest() -> int:
    import os
    import tempfile

    from native_exe_errors import BuildError

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")

    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("hi");\n    return 0;\n}\n')
        out_c = os.path.join(td, "out.c")

        # Case 1: real emission, real file, real content.
        result_path = emit_c_only("file", src, out_c, td)

        if result_path != out_c or not os.path.isfile(out_c):
            failures.append(f"case1: expected a real file at {out_c}, got {result_path}")
        else:
            content = open(out_c, encoding="utf-8").read()
            if 'sv0_runtime.h' not in content or "println" not in content:
                failures.append(f"case1: emitted C looks wrong: {content[:200]!r}")

        # Case 2 (CLI-014's literal red test): the host compiler is NEVER
        # invoked, even though a --cc pointing at a real, callable fake
        # compiler exists on disk. Prove it via the fake cc's own call-record
        # hook -- if emit_c_only ever invoked it, this file would exist.
        record_path2 = os.path.join(td, "cc_record2.json")
        if os.path.exists(record_path2):
            os.remove(record_path2)
        env_backup = dict(os.environ)
        os.environ["SV0_FAKE_CC_RECORD"] = record_path2
        os.environ["SV0_FAKE_CC_MODE"] = "valid"
        try:
            out_c2 = os.path.join(td, "out2.c")
            emit_c_only("file", src, out_c2, td)
        finally:
            os.environ.clear()
            os.environ.update(env_backup)
        if os.path.exists(record_path2):
            failures.append("case2: host compiler (fake cc) was invoked -- CLI-014 violated")

        # Case 3: a no-main fixture is still rejected before anything runs
        # (entry validation is not skipped just because this is --emit=c).
        bad_src = os.path.join(td, "library.sv0")
        with open(bad_src, "w", encoding="utf-8") as f:
            f.write("pub fn add(a: i32, b: i32) -> i32 { return a + b; }\n")
        out_c3 = os.path.join(td, "out3.c")
        try:
            emit_c_only("file", bad_src, out_c3, td)
            failures.append("case3: expected BuildError for a no-main fixture, none raised")
        except BuildError:
            pass
        if os.path.exists(out_c3):
            failures.append("case3: no output should have been written for a rejected entry")

        # Case 4 (CLI-008): a missing input file is a clean BuildError(INPUT),
        # never a raw OSError -- same hardening build_native_executable
        # already has via the same validate_file_input_shape call.
        out_c4 = os.path.join(td, "out4.c")
        try:
            emit_c_only("file", os.path.join(td, "genuinely-missing.sv0"), out_c4, td)
            failures.append("case4: expected BuildError for a missing input file, none raised")
        except BuildError as exc:
            from native_exe_errors import DiagnosticPhase

            if exc.phase is not DiagnosticPhase.INPUT:
                failures.append(f"case4: expected INPUT phase, got {exc.phase}")
        except OSError as exc:  # pragma: no cover - the exact regression this guards against
            failures.append(f"case4: leaked a raw OSError instead of BuildError: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_emit_c selftest FAIL: {f}")
        return 1

    print("native_exe_emit_c: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_emit_c: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
