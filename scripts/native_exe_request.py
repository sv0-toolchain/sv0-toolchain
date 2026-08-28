"""Normalized build request type for the sv0c native runtime executable driver (NEX-003).

Implements the `NativeBuildRequest` shape from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` Appendix A, and
`normalize_request` to build one from a `native_exe_cli.ParsedArgs` (spec
§11.4: normalization happens before any source/compiler execution, so tests
can compare normalized requests independent of how they were spelled).

Path resolution here is limited to CLI-007's rule (a relative path resolves
against the invocation working directory) — it does not yet validate
existence, permissions, symlinks, or apply the Section 12.1 default output
naming; that is NEX-026 (and, for the CLI's own default-output resolution,
`native_exe_output_path.default_output_path`, called by
`build_native_executable` itself when `output_path` is left `None`).

`--profile=release` was rejected here through NEX-058 (CLI-010: "blocked
until its release gate is enabled") — written back when the release
profile didn't exist. NEX-051 has since actually built and gated it
(048's UB audit -> 050's sanitizer clearance -> 051b's full-corpus parity
gate all passed before 051c wired `profile` into
`build_native_executable`), so this module now forwards `release` through
instead of rejecting it (NEX-059) — rejecting it today would make the CLI
contradict its own, already-gated engine.

Run `python3 scripts/native_exe_request.py --selftest` for the normalization
corpus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from native_exe_cli import ParsedArgs


class InputKind(Enum):
    FILE = "file"
    PROJECT = "project"


class Backend(Enum):
    C = "c"


class Emit(Enum):
    EXECUTABLE = "executable"


class Profile(Enum):
    DEV = "dev"
    RELEASE = "release"


class ContractMode(Enum):
    RUNTIME = "runtime"
    VERIFIED = "verified"
    DISABLED = "disabled"


class CcSelection(Enum):
    EXPLICIT = "explicit"
    CONFIG = "config"
    SV0_CC_ENV = "sv0_cc_env"
    CC_ENV = "cc_env"
    PATH_DEFAULT = "path_default"


class MessageFormat(Enum):
    HUMAN = "human"
    JSON = "json"


class RequestError(Exception):
    """Raised when a ParsedArgs cannot be normalized into a valid NativeBuildRequest."""


@dataclass
class NativeBuildRequest:
    """Spec Appendix A, normalized. `output_path` is None until NEX-026 adds
    Section 12.1 default naming; an explicit `-o` is the only way to set it
    for now. `keep_c`/`build_record`/`message_format` are R0.1 fields
    (CLI-014…016), wired for real in NEX-059: `keep_c`/`build_record` hold
    the resolved explicit path when `-o`-style `=<path>` was given; when
    the flag was given BARE (no `=<path>`), the corresponding `_requested`
    flag is `True` but the path stays `None` here -- the default path
    (`<final_output>.c`, this module's own documented convention, since
    the spec gives no worked example for the bare form) can only be
    computed once the final output path is known, which for a default
    (`-o`-less) build happens inside `build_native_executable` itself, not
    at normalization time. `native_exe_main.py` resolves that deferred
    default before calling `build_native_executable`.
    """

    input_kind: InputKind
    input_path: str
    output_path: str | None
    backend: Backend
    emit: Emit
    profile: Profile
    contract_mode_requested: ContractMode
    cc_selection: CcSelection
    cc_command: str | None
    keep_c_requested: bool
    keep_c: str | None  # resolved explicit path if given; None if not requested OR bare (default deferred)
    message_format: MessageFormat
    build_record_requested: bool
    build_record: str | None  # resolved explicit path if given; None if not requested OR bare (default deferred)
    quiet: bool
    verbose: bool
    invocation_cwd: str
    config_path: str | None


_PROFILE_VALUES = {p.value for p in Profile}
_CONTRACT_VALUES = {c.value for c in ContractMode}


def _resolve(path: str, cwd: str) -> str:
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(cwd, path))


def normalize_request(parsed: ParsedArgs, invocation_cwd: str | None = None) -> NativeBuildRequest:
    cwd = invocation_cwd if invocation_cwd is not None else os.getcwd()

    if parsed.profile not in _PROFILE_VALUES:
        raise RequestError(f"unknown profile: {parsed.profile!r}")
    if parsed.contract_mode not in _CONTRACT_VALUES:
        raise RequestError(f"unknown contract mode: {parsed.contract_mode!r}")

    input_kind = InputKind.PROJECT if parsed.input_kind == "project" else InputKind.FILE
    input_path = _resolve(parsed.input_path, cwd)
    output_path = _resolve(parsed.output_path, cwd) if parsed.output_path is not None else None

    if parsed.cc is not None:
        cc_selection = CcSelection.EXPLICIT
        cc_command = parsed.cc
    else:
        cc_selection = CcSelection.PATH_DEFAULT
        cc_command = None

    keep_c_resolved = _resolve(parsed.keep_c_path, cwd) if parsed.keep_c_path is not None else None
    build_record_resolved = (
        _resolve(parsed.build_record_path, cwd) if parsed.build_record_path is not None else None
    )

    return NativeBuildRequest(
        input_kind=input_kind,
        input_path=input_path,
        output_path=output_path,
        backend=Backend.C,
        emit=Emit.EXECUTABLE,
        profile=Profile(parsed.profile),
        contract_mode_requested=ContractMode(parsed.contract_mode),
        cc_selection=cc_selection,
        cc_command=cc_command,
        keep_c_requested=parsed.keep_c_seen,
        keep_c=keep_c_resolved,
        message_format=MessageFormat(parsed.message_format),
        build_record_requested=parsed.build_record_seen,
        build_record=build_record_resolved,
        quiet=parsed.quiet,
        verbose=parsed.verbose,
        invocation_cwd=cwd,
        config_path=None,
    )


def _selftest() -> int:
    failures: list[str] = []
    cwd = "/work"

    # Case 1: minimal file request normalizes relative paths against invocation cwd (CLI-007).
    req = normalize_request(ParsedArgs(input_kind="file", input_path="hello.sv0"), invocation_cwd=cwd)
    if req.input_path != "/work/hello.sv0":
        failures.append(f"expected /work/hello.sv0, got {req.input_path}")
    if req.output_path is not None:
        failures.append(f"expected no default output_path yet (NEX-026), got {req.output_path}")
    if req.backend is not Backend.C or req.emit is not Emit.EXECUTABLE:
        failures.append("backend/emit must always be C/EXECUTABLE through R1")
    if req.cc_selection is not CcSelection.PATH_DEFAULT:
        failures.append(f"expected PATH_DEFAULT cc_selection, got {req.cc_selection}")

    # Case 2: an absolute input path is passed through unchanged.
    req = normalize_request(ParsedArgs(input_kind="file", input_path="/abs/hello.sv0"), invocation_cwd=cwd)
    if req.input_path != "/abs/hello.sv0":
        failures.append(f"expected absolute path passthrough, got {req.input_path}")

    # Case 3: explicit -o resolves relative to invocation cwd, not the source directory.
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="src/hello.sv0", output_path="dist/hello"),
        invocation_cwd=cwd,
    )
    if req.output_path != "/work/dist/hello":
        failures.append(f"expected /work/dist/hello, got {req.output_path}")

    # Case 4: project mode maps input_kind and carries the directory as input_path.
    req = normalize_request(ParsedArgs(input_kind="project", input_path="calculator"), invocation_cwd=cwd)
    if req.input_kind is not InputKind.PROJECT or req.input_path != "/work/calculator":
        failures.append(f"project normalization wrong: {req.input_kind}, {req.input_path}")

    # Case 5: explicit --cc records EXPLICIT selection (TOOL-001 precedence, top of the chain).
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="hello.sv0", cc="/usr/bin/clang"),
        invocation_cwd=cwd,
    )
    if req.cc_selection is not CcSelection.EXPLICIT or req.cc_command != "/usr/bin/clang":
        failures.append(f"expected EXPLICIT/clang, got {req.cc_selection}, {req.cc_command}")

    # Case 6 (NEX-059): --profile=release is now ACCEPTED and forwarded as
    # Profile.RELEASE -- the R1 gate (NEX-048/050/051) is real now, so
    # this module must no longer contradict its own, already-gated engine.
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="hello.sv0", profile="release"), invocation_cwd=cwd
    )
    if req.profile is not Profile.RELEASE:
        failures.append(f"expected Profile.RELEASE to be forwarded, got {req.profile}")

    # Case 6b: an unrecognized profile value is still rejected (only "dev"
    # and "release" are ever valid -- this isn't a blanket pass-through).
    try:
        normalize_request(
            ParsedArgs(input_kind="file", input_path="hello.sv0", profile="turbo"), invocation_cwd=cwd
        )
        failures.append("expected RequestError for an unrecognized profile, got none")
    except RequestError:
        pass

    # Case 7: an unknown contract mode is rejected rather than silently passed through.
    try:
        normalize_request(
            ParsedArgs(input_kind="file", input_path="hello.sv0", contract_mode="bogus"),
            invocation_cwd=cwd,
        )
        failures.append("expected RequestError for unknown contract mode, got none")
    except RequestError:
        pass

    # Case 8 (NEX-059): --keep-c=<path> resolves relative to invocation cwd,
    # same rule as -o; keep_c_requested is True.
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="hello.sv0", keep_c_seen=True, keep_c_path="out/hello.c"),
        invocation_cwd=cwd,
    )
    if not req.keep_c_requested or req.keep_c != "/work/out/hello.c":
        failures.append(f"case8: expected keep_c_requested + /work/out/hello.c, got {req.keep_c_requested}, {req.keep_c}")

    # Case 9: bare --keep-c (no path) records keep_c_requested=True but
    # keep_c=None -- the default is deferred to native_exe_main.py, which
    # knows the final output path; this module must not guess it.
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="hello.sv0", keep_c_seen=True, keep_c_path=None),
        invocation_cwd=cwd,
    )
    if not req.keep_c_requested or req.keep_c is not None:
        failures.append(f"case9: bare --keep-c should defer its path, got requested={req.keep_c_requested} path={req.keep_c!r}")

    # Case 10: keep_c_requested defaults to False when --keep-c was never given.
    req = normalize_request(ParsedArgs(input_kind="file", input_path="hello.sv0"), invocation_cwd=cwd)
    if req.keep_c_requested or req.keep_c is not None:
        failures.append(f"case10: expected no keep-c request by default, got requested={req.keep_c_requested} path={req.keep_c!r}")

    # Case 11: --message-format=json is forwarded as MessageFormat.JSON.
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="hello.sv0", message_format="json"), invocation_cwd=cwd
    )
    if req.message_format is not MessageFormat.JSON:
        failures.append(f"case11: expected MessageFormat.JSON, got {req.message_format}")

    # Case 12: --build-record mirrors --keep-c's bare/explicit-path handling.
    req = normalize_request(
        ParsedArgs(
            input_kind="file", input_path="hello.sv0", build_record_seen=True, build_record_path="r.json"
        ),
        invocation_cwd=cwd,
    )
    if not req.build_record_requested or req.build_record != "/work/r.json":
        failures.append(f"case12: expected build_record_requested + /work/r.json, got {req.build_record_requested}, {req.build_record}")

    if failures:
        for f in failures:
            print(f"native_exe_request selftest FAIL: {f}")
        return 1

    print("native_exe_request: selftest OK (13 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_request: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
