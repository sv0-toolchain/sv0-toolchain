"""Normalized build request type for the sv0c native runtime executable driver (NEX-003).

Implements the `NativeBuildRequest` shape from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` Appendix A, and
`normalize_request` to build one from a `native_exe_cli.ParsedArgs` (spec
§11.4: normalization happens before any source/compiler execution, so tests
can compare normalized requests independent of how they were spelled).

Path resolution here is limited to CLI-007's rule (a relative path resolves
against the invocation working directory) — it does not yet validate
existence, permissions, symlinks, or apply the Section 12.1 default output
naming; that is NEX-026. `--profile=release` is rejected here per CLI-010
(blocked until its R1 gate opens) even though full profile-gate wiring is a
later slice, because accepting it silently would violate AE-009/product
principle 1 the moment this type starts getting used by real driver code.

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
    (CLI-014…016) carried in the type now so later slices don't need to widen
    it, per spec §11.2's own release-additive option grammar.
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
    keep_c: str | None
    message_format: MessageFormat
    build_record: str | None
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
    if parsed.profile == Profile.RELEASE.value:
        raise RequestError(
            "--profile=release is rejected until its R1 gate is enabled (CLI-010)"
        )
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
        keep_c=None,
        message_format=MessageFormat.HUMAN,
        build_record=None,
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

    # Case 6: --profile=release is rejected at normalization time (CLI-010), not silently accepted.
    try:
        normalize_request(ParsedArgs(input_kind="file", input_path="hello.sv0", profile="release"), invocation_cwd=cwd)
        failures.append("expected RequestError for --profile=release, got none")
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

    if failures:
        for f in failures:
            print(f"native_exe_request selftest FAIL: {f}")
        return 1

    print("native_exe_request: selftest OK (7 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_request: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
