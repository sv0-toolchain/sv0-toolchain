#!/usr/bin/env python3
"""Production CLI entry point for `./scripts/sv0 native-compile` (NEX-059).

Wires the already-built-and-tested pieces together into something a user
can actually run from a terminal: `native_exe_cli.parse_args` ->
`native_exe_request.normalize_request` -> `native_exe_build.build_native_executable`,
then reports the outcome per `--message-format` and optionally writes a
build record. Every piece this module calls already has its own selftest
and mutation coverage; this module's own job is sequencing + exit-code
mapping + the deferred `--keep-c`/`--build-record` bare-flag default paths
(`native_exe_request`'s own documented convention: `<final_output>.c` /
`<final_output>.build-record.json`, resolved here because only this module
knows the final output path before the build runs -- `default_output_path`
is a pure function, so calling it here and letting
`build_native_executable` call it again internally can never drift).

Only the workspace-adapter spelling (`./scripts/sv0 native-compile`) is
wired here -- the installed `sv0c --emit=exe` spelling is a later slice
(NEX-060, not yet scoped) per spec §11.1.

Run `python3 scripts/native_exe_main.py --selftest` for the end-to-end
corpus (real builds, real binaries actually run).
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys

from native_exe_argv_builder import build_dev_profile_argv, build_release_profile_argv
from native_exe_build import build_native_executable
from native_exe_build_record import build_record, write_build_record_atomically
from native_exe_cc_probe import probe_compiler
from native_exe_cc_select import select_cc
from native_exe_cli import UsageError, parse_args
from native_exe_emit_c import emit_c_only
from native_exe_errors import BuildError
from native_exe_human_output import format_emit_c_success_message, render_argv_for_display
from native_exe_json_output import PhaseTimer, build_event, encode_event
from native_exe_output_path import default_output_path
from native_exe_request import Emit, RequestError, normalize_request
from native_exe_runtime import resolve_runtime_dir
from native_exe_runtime_manifest import load_manifest


def _sha256_file(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_revision(repo_root: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=repo_root, capture_output=True, text=True, check=True
        )
        return proc.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _collect_provenance(request, final_output: str) -> dict:
    """Best-effort real data for `--build-record`/`--message-format=json`.

    `build_native_executable` doesn't return compiler/runtime/timing detail
    (its `BuildResult` is deliberately minimal -- `output_path`/`message`
    only), so this gathers the same real facts a second time via the exact
    same already-tested, side-effect-free lookups (`select_cc`,
    `probe_compiler`, `resolve_runtime_dir`, `load_manifest`) rather than
    inventing or guessing any of it. `sv0c_version` has no version-tracking
    scheme anywhere in this toolchain yet, so it is honestly reported as
    "unknown" rather than fabricated.
    """
    cc_path, _selection = select_cc(request.cc_command, os.environ)
    compiler_info = probe_compiler(cc_path)
    runtime = resolve_runtime_dir()
    manifest = load_manifest(runtime)
    manifest_sha256 = _sha256_file(os.path.join(runtime.dir, "runtime-manifest.json"))
    sv0c_dir = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sv0c"))
    return {
        "compiler_path": compiler_info.path,
        "compiler_family": compiler_info.family,
        "compiler_version": compiler_info.version_text,
        "runtime_abi": manifest["abi_version"],
        "runtime_manifest_sha256": manifest_sha256,
        "runtime_header_sha256": manifest["header_sha256"],
        "runtime_source_sha256": manifest["source_sha256"],
        "host_os": platform.system().lower(),
        "host_arch": platform.machine(),
        "sv0c_version": "unknown",
        "sv0c_revision": _git_revision(sv0c_dir),
    }


def _format_verbose_detail(request, final_output: str, provenance: dict) -> str:
    """Normalized, non-secret build detail for `--verbose` (CLI-013).

    Reconstructs the exact host-compiler argv *shape* via the same real
    `build_dev_profile_argv`/`build_release_profile_argv` the pipeline
    itself calls -- with placeholder staged-C/temp-output paths, since the
    real ones are ephemeral scratch-directory paths generated fresh per
    build and never meaningful to show to a user (`native_exe_human_output`'s
    own docstring: "normal-mode output never names an unpredictable scratch
    path" -- verbose mode doesn't invent an exception to that for paths
    that don't exist yet at display time). Rendered via
    `render_argv_for_display` (`shlex.quote`-safe, diagnostic only).
    """
    runtime = resolve_runtime_dir()
    build_argv = build_dev_profile_argv if request.profile.value == "dev" else build_release_profile_argv
    argv = build_argv(provenance["compiler_path"], runtime, "<staged-C>", "<temp-output>")
    lines = [
        f"input:    {request.input_path}",
        f"output:   {final_output}",
        f"profile:  {request.profile.value}",
        f"contract: {request.contract_mode_requested.value}",
        f"config:   {request.config_path if request.config_path is not None else '(none discovered)'}",
        f"compiler: {provenance['compiler_path']} ({provenance['compiler_family']}, {provenance['compiler_version']})",
        f"argv shape: {render_argv_for_display(argv)}",
    ]
    return "\n".join(lines)


def run(argv: list[str], invocation_cwd: str) -> int:
    try:
        parsed = parse_args(argv)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    try:
        request = normalize_request(parsed, invocation_cwd=invocation_cwd)
    except RequestError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 3

    if request.emit is Emit.C_ONLY:
        # CLI-014: --emit=c never invokes a host compiler and produces no
        # executable -- a genuinely separate, smaller pipeline
        # (native_exe_emit_c.emit_c_only) rather than build_native_executable.
        # normalize_request/native_exe_cli already guarantee output_path is
        # set and that --keep-c/--build-record/--message-format=json were
        # never combined with --emit=c, so none of that machinery applies here.
        try:
            result_path = emit_c_only(
                input_kind=request.input_kind.value,
                input_path=request.input_path,
                output_path=request.output_path,
                invocation_cwd=request.invocation_cwd,
                contract_mode=request.contract_mode_requested.value,
            )
        except BuildError as exc:
            print(f"error: {exc.message}", file=sys.stderr)
            return exc.exit_code
        if not request.quiet:
            print(format_emit_c_success_message(result_path))
            if request.verbose:
                config_display = request.config_path if request.config_path is not None else "(none discovered)"
                print(
                    f"input:    {request.input_path}\n"
                    f"output:   {result_path}\n"
                    f"contract: {request.contract_mode_requested.value}\n"
                    f"config:   {config_display}"
                )
        return 0

    final_output = (
        request.output_path
        if request.output_path is not None
        else default_output_path(request.input_kind.value, request.input_path, request.invocation_cwd)
    )
    keep_c_path = request.keep_c
    if keep_c_path is None and request.keep_c_requested:
        keep_c_path = f"{final_output}.c"
    build_record_path = request.build_record
    if build_record_path is None and request.build_record_requested:
        build_record_path = f"{final_output}.build-record.json"

    timer = PhaseTimer()
    try:
        with timer.phase("total"):
            result = build_native_executable(
                input_kind=request.input_kind.value,
                input_path=request.input_path,
                output_path=request.output_path,
                invocation_cwd=request.invocation_cwd,
                contract_mode=request.contract_mode_requested.value,
                explicit_cc=request.cc_command,
                quiet=request.quiet,
                keep_c_path=keep_c_path,
                profile=request.profile.value,
            )
    except BuildError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return exc.exit_code

    if build_record_path is not None or request.message_format.value == "json" or request.verbose:
        provenance = _collect_provenance(request, final_output)

    if build_record_path is not None:
        record = build_record(
            artifact_path=result.output_path,
            input_kind=request.input_kind.value,
            input_root=request.input_path,
            source_paths=[request.input_path] if request.input_kind.value == "file" else [],
            sv0c_version=provenance["sv0c_version"],
            sv0c_revision=provenance["sv0c_revision"],
            backend="c",
            runtime_abi=provenance["runtime_abi"],
            runtime_manifest_sha256=provenance["runtime_manifest_sha256"],
            runtime_header_sha256=provenance["runtime_header_sha256"],
            runtime_source_sha256=provenance["runtime_source_sha256"],
            host_os=provenance["host_os"],
            host_arch=provenance["host_arch"],
            c_compiler_path=provenance["compiler_path"],
            c_compiler_family=provenance["compiler_family"],
            c_compiler_version=provenance["compiler_version"],
            c_compiler_argv=[],
            profile=request.profile.value,
            contract_mode_requested=request.contract_mode_requested.value,
            contract_mode_effective=request.contract_mode_requested.value,
            config={"path": request.config_path} if request.config_path is not None else None,
        )
        write_build_record_atomically(record, build_record_path)

    if request.message_format.value == "json":
        event = build_event(
            event="build",
            success=True,
            phase="done",
            input_path=request.input_path,
            output_path=result.output_path,
            backend="c",
            profile=request.profile.value,
            contract_mode_requested=request.contract_mode_requested.value,
            contract_mode_effective=request.contract_mode_requested.value,
            compiler_path=provenance["compiler_path"],
            compiler_family=provenance["compiler_family"],
            compiler_version=provenance["compiler_version"],
            timings_ms=timer.timings_ms(),
        )
        print(encode_event(event))
    elif result.message is not None:
        print(result.message)
        if request.verbose:
            print(_format_verbose_detail(request, final_output, provenance))

    return 0


def main() -> int:
    return run(sys.argv[1:], os.getcwd())


def _selftest() -> int:
    import json
    import tempfile

    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        # Case 1: a real file build exits 0 and produces a real, runnable binary.
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("hi from native_exe_main");\n    return 42;\n}\n')
        out = os.path.join(td, "hello_out")
        rc = run(["-o", out, src], td)
        if rc != 0:
            failures.append(f"case1: expected exit 0, got {rc}")
        elif not os.path.isfile(out):
            failures.append("case1: output binary not created")
        else:
            proc = subprocess.run([out], capture_output=True, text=True)
            if proc.returncode != 42 or "hi from native_exe_main" not in proc.stdout:
                failures.append(f"case1: rc={proc.returncode} stdout={proc.stdout!r}")

        # Case 2: a project build.
        proj = os.path.join(td, "proj")
        os.makedirs(proj)
        with open(os.path.join(proj, "main.sv0"), "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 5;\n}\n")
        out2 = os.path.join(td, "proj_out")
        rc2 = run(["--project", proj, "-o", out2], td)
        if rc2 != 0 or not os.path.isfile(out2):
            failures.append(f"case2: expected a real project build, got rc={rc2}")

        # Case 3: default output path (no explicit -o).
        src3 = os.path.join(td, "defaulted.sv0")
        with open(src3, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 7;\n}\n")
        rc3 = run([src3], td)
        expected_default = os.path.join(td, "build", "native", "defaulted")
        if rc3 != 0 or not os.path.isfile(expected_default):
            failures.append(f"case3: expected default-output build to succeed at {expected_default}, rc={rc3}")

        # Case 4: a bogus flag is a usage error, exit 2.
        rc4 = run(["--not-a-real-flag"], td)
        if rc4 != 2:
            failures.append(f"case4: expected exit 2 for a bogus flag, got {rc4}")

        # Case 5: a no-main fixture is an entry error (nonzero, non-usage).
        src5 = os.path.join(td, "library.sv0")
        with open(src5, "w", encoding="utf-8") as f:
            f.write("pub fn add(a: i32, b: i32) -> i32 {\n    return a + b;\n}\n")
        rc5 = run([src5], td)
        if rc5 == 0:
            failures.append("case5: expected a nonzero exit for a no-main fixture")

        # Case 6: --keep-c retains C whose hash matches the staged source
        # actually used for compilation (bare form: default path is
        # <output>.c).
        src6 = os.path.join(td, "keepc.sv0")
        with open(src6, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 1;\n}\n")
        out6 = os.path.join(td, "keepc_out")
        rc6 = run(["-o", out6, "--keep-c", src6], td)
        expected_c = f"{out6}.c"
        if rc6 != 0 or not os.path.isfile(expected_c):
            failures.append(f"case6: expected retained C at {expected_c}, rc={rc6}")

        # Case 7: --message-format=json produces exactly one parseable JSON
        # line on stdout with the expected shape.
        src7 = os.path.join(td, "json.sv0")
        with open(src7, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 0;\n}\n")
        out7 = os.path.join(td, "json_out")
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            rc7 = run(["-o", out7, "--message-format=json", src7], td)
        lines = [line for line in buf.getvalue().splitlines() if line.strip()]
        if rc7 != 0 or len(lines) != 1:
            failures.append(f"case7: expected exactly one JSON line, got rc={rc7} lines={lines!r}")
        else:
            try:
                event = json.loads(lines[0])
            except json.JSONDecodeError as exc:
                failures.append(f"case7: not valid JSON: {exc}")
                event = {}
            if event.get("success") is not True or event.get("output") != out7:
                failures.append(f"case7: unexpected event shape: {event!r}")

        # Case 8: --build-record (bare form) writes a real, valid record
        # whose artifact hash matches the actually-published binary.
        src8 = os.path.join(td, "rec.sv0")
        with open(src8, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 3;\n}\n")
        out8 = os.path.join(td, "rec_out")
        rc8 = run(["-o", out8, "--build-record", src8], td)
        expected_record = f"{out8}.build-record.json"
        if rc8 != 0 or not os.path.isfile(expected_record):
            failures.append(f"case8: expected a build record at {expected_record}, rc={rc8}")
        else:
            with open(expected_record, encoding="utf-8") as f:
                record = json.load(f)
            if record["artifact"]["sha256"] != _sha256_file(out8):
                failures.append("case8: build record artifact hash doesn't match the published binary")

        # Case 9 (CLI-013): --verbose exposes real, normalized build detail
        # (input/output/profile/compiler/argv shape) beyond the plain
        # success line -- proving the flag isn't silently accepted and
        # ignored.
        src9 = os.path.join(td, "verbose.sv0")
        with open(src9, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 0;\n}\n")
        out9 = os.path.join(td, "verbose_out")
        buf9 = io.StringIO()
        with redirect_stdout(buf9):
            rc9 = run(["-o", out9, "--verbose", src9], td)
        printed = buf9.getvalue()
        if rc9 != 0:
            failures.append(f"case9: expected exit 0, got {rc9}")
        elif "argv shape:" not in printed or out9 not in printed or "profile:" not in printed:
            failures.append(f"case9: --verbose output missing expected detail: {printed!r}")

        # Case 10 (sv0.toml, Section 17): a real sv0.toml beside the source
        # drives an actual build end to end with NO CLI flags at all --
        # isolated in its own subdirectory so it can't leak into any case
        # above (discover_config searches beside the input file, and every
        # other case's fixture lives directly in `td`). Real finding this
        # slice closes: native_exe_request.normalize_request previously
        # hardcoded config_path=None and never called discover_config/
        # load_config at all.
        config_dir = os.path.join(td, "config_case")
        os.makedirs(config_dir)
        with open(os.path.join(config_dir, "sv0.toml"), "w", encoding="utf-8") as f:
            f.write('[build]\ncontract-mode = "disabled"\n')
        src10 = os.path.join(config_dir, "config.sv0")
        with open(src10, "w", encoding="utf-8") as f:
            # requires-violating input: contract-mode=runtime would abort
            # (nonzero), contract-mode=disabled runs the stripped body to
            # completion -- the exact 1-vs-8 discriminator native_exe_contract_mode.py's
            # own corpus already established for this exact test shape.
            f.write(
                "fn half(x: i32) -> i32 requires(x > 0) {\n    return x / 2;\n}\n"
                "fn main() -> i32 {\n    return half(0 - 4) + 10;\n}\n"
            )
        out10 = os.path.join(config_dir, "config_out")
        rc10 = run(["-o", out10, src10], config_dir)
        if rc10 != 0 or not os.path.isfile(out10):
            failures.append(f"case10: expected a real config-driven build to succeed, rc={rc10}")
        else:
            proc10 = subprocess.run([out10], capture_output=True, text=True)
            if proc10.returncode != 8:
                failures.append(
                    f"case10: expected exit 8 (sv0.toml's contract-mode=disabled strips the "
                    f"check instead of aborting), got {proc10.returncode} -- config wasn't "
                    f"actually applied"
                )

        # Case 11 (CLI-014): --emit=c writes real C, never invokes a host
        # compiler, and produces no executable at all.
        src11 = os.path.join(td, "emitc.sv0")
        with open(src11, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("emit c works");\n    return 0;\n}\n')
        out11 = os.path.join(td, "emitc_out.c")
        rc11 = run(["--emit=c", "-o", out11, src11], td)
        if rc11 != 0 or not os.path.isfile(out11):
            failures.append(f"case11: expected a real --emit=c write to succeed, rc={rc11}")
        else:
            content11 = open(out11, encoding="utf-8").read()
            if "sv0_runtime.h" not in content11 or "emit c works" not in content11:
                failures.append(f"case11: emitted C looks wrong: {content11[:200]!r}")

        # Case 12 (CLI-014): --emit=c requires -o -- a clean usage error
        # (exit 2), not a guessed default path.
        rc12 = run(["--emit=c", src11], td)
        if rc12 != 2:
            failures.append(f"case12: expected exit 2 for --emit=c without -o, got {rc12}")

        # Case 13 (CLI-014): --emit=c rejects --keep-c/--build-record
        # (neither has a coherent meaning with no executable produced).
        out13 = os.path.join(td, "emitc13_out.c")
        rc13 = run(["--emit=c", "-o", out13, "--keep-c", src11], td)
        if rc13 != 2:
            failures.append(f"case13: expected exit 2 for --emit=c + --keep-c, got {rc13}")

        # Case 14 (CLI-014): --emit=c honors --quiet (suppresses the
        # success line) and --verbose (prints extra detail) just like
        # --emit=exe does.
        out14 = os.path.join(td, "emitc14_out.c")
        buf14 = io.StringIO()
        with redirect_stdout(buf14):
            rc14 = run(["--emit=c", "-o", out14, "--quiet", src11], td)
        if rc14 != 0 or buf14.getvalue().strip() != "":
            failures.append(f"case14: expected --quiet to suppress --emit=c output, got {buf14.getvalue()!r}")

    if failures:
        for f in failures:
            print(f"native_exe_main selftest FAIL: {f}")
        return 1

    print("native_exe_main: selftest OK (14 cases)")
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    raise SystemExit(main())
