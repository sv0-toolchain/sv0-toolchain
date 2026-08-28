"""Normalized build request type for the sv0c native runtime executable driver (NEX-003).

Implements the `NativeBuildRequest` shape from
`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` Appendix A, and
`normalize_request` to build one from a `native_exe_cli.ParsedArgs` (spec
§11.4: normalization happens before any source/compiler execution, so tests
can compare normalized requests independent of how they were spelled).

Path resolution here is limited to CLI-007's rule (a relative path resolves
against the invocation working directory) — it does not yet validate
existence, permissions, symlinks; that is NEX-026 (and, for the CLI's own
default-output resolution when neither `-o` nor a config `output-dir` apply,
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

`sv0.toml` (Section 17, `native_exe_config.py`, NEX-043) is wired in for
real here, closing a gap flagged by the post-R1 traceability audit: the
config module existed and was tested in isolation, but nothing ever called
`discover_config`/`load_config` from a real build. §17.3's discovery rule
(beside the file, or `<project>/sv0.toml`) runs once `input_path` is
resolved to an absolute path; §11.4's four-tier precedence (CLI > config >
env > default) is `native_exe_config.resolve_precedence`, applied per
setting via `_tier` (mapping this module's own "not given" sentinel, `None`,
onto `resolve_precedence`'s `_UNSET`, since a config/CLI value is never
legitimately `None` itself for any of these six keys). A malformed
`sv0.toml` (`ConfigError`) becomes a `RequestError` here, exactly like an
unrecognized `--profile`/`--contract-mode` value already does -- both are
normalization-time, non-build-specific failures with the same exit class.

Deliberately NOT done here, and not claimed: the `SV0_CC` environment-variable
tier `native_exe_cc_select.py`'s own docstring names as a distinct, still
unimplemented R0.1 tier (`--cc` -> `sv0.toml` -> `SV0_CC` -> `CC` -> `PATH`)
-- this module wires the `sv0.toml` tier only, since that's what was asked;
`SV0_CC` remains a separate, smaller, still-open gap.

Run `python3 scripts/native_exe_request.py --selftest` for the normalization
corpus.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum

from native_exe_cli import ParsedArgs
from native_exe_config import _UNSET, ConfigError, discover_config, load_config, resolve_precedence
from native_exe_output_path import stem_for


class InputKind(Enum):
    FILE = "file"
    PROJECT = "project"


class Backend(Enum):
    C = "c"


class Emit(Enum):
    EXECUTABLE = "executable"
    C_ONLY = "c"  # CLI-014: --emit=c, write C atomically, never invoke the host compiler


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
    at normalization time -- UNLESS a config `output-dir` applies, in which
    case `output_path` IS resolved here (§17.4: `-o` wins over `output-dir`,
    but `output-dir` still needs to win over the hardcoded `build/native`
    default, which only `normalize_request` can decide, since
    `build_native_executable` has no config awareness). `native_exe_main.py`
    resolves the still-deferred (`None`) case before calling
    `build_native_executable`. `config_path` records the discovered
    `sv0.toml` path (or `None` if none was found) -- exposed per §17.3
    ("the selected configuration path appears in verbose output and build
    records").
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


def _tier(value):
    """Map this module's own "not given" sentinel (`None`) onto
    `resolve_precedence`'s `_UNSET` -- none of the six `sv0.toml` keys, nor
    any CLI flag wired here, ever legitimately means a real `None` value
    itself, so `None` always means "this tier didn't supply anything."
    """
    return _UNSET if value is None else value


def normalize_request(parsed: ParsedArgs, invocation_cwd: str | None = None) -> NativeBuildRequest:
    cwd = invocation_cwd if invocation_cwd is not None else os.getcwd()

    input_kind = InputKind.PROJECT if parsed.input_kind == "project" else InputKind.FILE
    input_path = _resolve(parsed.input_path, cwd)

    # §17.3 discovery: beside the file, or <project>/sv0.toml -- both
    # collapse to "does sv0.toml exist directly in this one directory."
    config_dir = input_path if input_kind is InputKind.PROJECT else os.path.dirname(input_path)
    config_path = discover_config(config_dir)
    config_build: dict = {}
    if config_path is not None:
        try:
            config_build = load_config(config_path)
        except ConfigError as exc:
            raise RequestError(f"{config_path}: {exc}") from exc

    profile_value = resolve_precedence(
        cli=_tier(parsed.profile), config=_tier(config_build.get("profile")), default="dev"
    )
    if profile_value not in _PROFILE_VALUES:
        raise RequestError(f"unknown profile: {profile_value!r}")

    contract_mode_value = resolve_precedence(
        cli=_tier(parsed.contract_mode), config=_tier(config_build.get("contract-mode")), default="runtime"
    )
    if contract_mode_value not in _CONTRACT_VALUES:
        raise RequestError(f"unknown contract mode: {contract_mode_value!r}")

    # §17.4: c-compiler relative paths resolve against the CONFIG FILE's own
    # directory, never cwd -- applied to the config value before it ever
    # competes in the precedence tier, so a winning CLI value (which has its
    # own, unrelated resolution rules inside native_exe_cc_select) is never
    # touched by this config-specific resolution.
    config_cc_raw = config_build.get("c-compiler")
    config_cc = (
        _resolve(config_cc_raw, os.path.dirname(config_path)) if config_cc_raw is not None else None
    )
    cc_command = resolve_precedence(cli=_tier(parsed.cc), config=_tier(config_cc), default=None)
    if cc_command is not None and parsed.cc is not None:
        cc_selection = CcSelection.EXPLICIT
    elif cc_command is not None:
        cc_selection = CcSelection.CONFIG
    else:
        cc_selection = CcSelection.PATH_DEFAULT

    # §17.4: -o always wins (already-resolved-against-cwd, per CLI-007);
    # otherwise a config output-dir (resolved against the CONFIG FILE's
    # directory) replaces the hardcoded build/native default entirely --
    # only normalize_request can decide this, since build_native_executable
    # has no config awareness of its own.
    if parsed.output_path is not None:
        output_path = _resolve(parsed.output_path, cwd)
    elif "output-dir" in config_build:
        output_dir = _resolve(config_build["output-dir"], os.path.dirname(config_path))
        output_path = os.path.join(output_dir, stem_for(input_kind.value, input_path))
    else:
        output_path = None

    # keep-c/build-record: sv0.toml's form is a plain boolean (no path), so
    # a config True is equivalent to the bare CLI flag -- the actual default
    # PATH stays deferred to native_exe_main.py either way (NEX-059's own
    # documented convention), never guessed here.
    keep_c_requested = resolve_precedence(
        cli=_tier(True if parsed.keep_c_seen else None),
        config=_tier(config_build.get("keep-c")),
        default=False,
    )
    keep_c_resolved = _resolve(parsed.keep_c_path, cwd) if parsed.keep_c_path is not None else None

    build_record_requested = resolve_precedence(
        cli=_tier(True if parsed.build_record_seen else None),
        config=_tier(config_build.get("build-record")),
        default=False,
    )
    build_record_resolved = (
        _resolve(parsed.build_record_path, cwd) if parsed.build_record_path is not None else None
    )

    return NativeBuildRequest(
        input_kind=input_kind,
        input_path=input_path,
        output_path=output_path,
        backend=Backend.C,
        emit=Emit.C_ONLY if parsed.emit_value == "c" else Emit.EXECUTABLE,
        profile=Profile(profile_value),
        contract_mode_requested=ContractMode(contract_mode_value),
        cc_selection=cc_selection,
        cc_command=cc_command,
        keep_c_requested=keep_c_requested,
        keep_c=keep_c_resolved,
        message_format=MessageFormat(parsed.message_format),
        build_record_requested=build_record_requested,
        build_record=build_record_resolved,
        quiet=parsed.quiet,
        verbose=parsed.verbose,
        invocation_cwd=cwd,
        config_path=config_path,
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

    # Case 12b (CLI-014): default emit_value ("exe") normalizes to
    # Emit.EXECUTABLE; an explicit --emit=c normalizes to Emit.C_ONLY.
    req = normalize_request(ParsedArgs(input_kind="file", input_path="hello.sv0"), invocation_cwd=cwd)
    if req.emit is not Emit.EXECUTABLE:
        failures.append(f"case12b: expected default Emit.EXECUTABLE, got {req.emit}")
    req = normalize_request(
        ParsedArgs(input_kind="file", input_path="hello.sv0", emit_value="c", output_path="out.c"),
        invocation_cwd=cwd,
    )
    if req.emit is not Emit.C_ONLY:
        failures.append(f"case12b: expected Emit.C_ONLY for --emit=c, got {req.emit}")

    # Case 13: no sv0.toml present at all -- config_path is None, and
    # nothing about the previous 12 cases' behavior changes (a real "no
    # config" run behaves exactly like before this wiring existed).
    req = normalize_request(ParsedArgs(input_kind="file", input_path="hello.sv0"), invocation_cwd=cwd)
    if req.config_path is not None:
        failures.append(f"case13: expected no config discovered, got {req.config_path!r}")

    # The remaining cases need a REAL sv0.toml on disk (discover_config
    # does real os.path.isfile checks), so they run against a real temp
    # directory rather than the synthetic "/work" cwd above.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        cfg_path = os.path.join(td, "sv0.toml")
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(
                '[build]\nprofile = "release"\ncontract-mode = "disabled"\n'
                'c-compiler = "tools/my-cc"\noutput-dir = "dist"\n'
                "keep-c = true\nbuild-record = true\n"
            )
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 { return 0; }\n")

        # Case 14: config supplies profile/contract-mode when the CLI
        # doesn't (§11.4: config beats the hardcoded default).
        req = normalize_request(ParsedArgs(input_kind="file", input_path=src), invocation_cwd=td)
        if req.profile is not Profile.RELEASE:
            failures.append(f"case14: expected config profile=release, got {req.profile}")
        if req.contract_mode_requested is not ContractMode.DISABLED:
            failures.append(f"case14: expected config contract-mode=disabled, got {req.contract_mode_requested}")
        if req.config_path != cfg_path:
            failures.append(f"case14: expected config_path={cfg_path!r}, got {req.config_path!r}")

        # Case 15: an explicit CLI --profile still wins over config (§11.4:
        # CLI is the top tier).
        req = normalize_request(ParsedArgs(input_kind="file", input_path=src, profile="dev"), invocation_cwd=td)
        if req.profile is not Profile.DEV:
            failures.append(f"case15: expected CLI profile=dev to win over config, got {req.profile}")

        # Case 16: config's c-compiler resolves relative to the CONFIG
        # FILE's directory (§17.4), not cwd -- invoked from a DIFFERENT
        # cwd (a subdirectory) than the config file's own directory, so a
        # cwd-relative resolution and a config-dir-relative one would
        # genuinely disagree if the wiring used the wrong base.
        invocation_subdir = os.path.join(td, "elsewhere")
        os.makedirs(invocation_subdir)
        req = normalize_request(ParsedArgs(input_kind="file", input_path=src), invocation_cwd=invocation_subdir)
        if req.cc_command != os.path.join(td, "tools/my-cc"):
            failures.append(f"case16: expected config c-compiler resolved against config dir, got {req.cc_command!r}")
        if req.cc_selection is not CcSelection.CONFIG:
            failures.append(f"case16: expected CcSelection.CONFIG, got {req.cc_selection}")

        # Case 17: an explicit CLI --cc still wins over config's c-compiler.
        req = normalize_request(
            ParsedArgs(input_kind="file", input_path=src, cc="/usr/bin/clang"), invocation_cwd=td
        )
        if req.cc_command != "/usr/bin/clang" or req.cc_selection is not CcSelection.EXPLICIT:
            failures.append(f"case17: expected CLI --cc to win, got {req.cc_command!r}, {req.cc_selection}")

        # Case 18: config's output-dir (resolved against the config file's
        # directory, not cwd -- same cwd-vs-config-dir divergence as case 16)
        # replaces the hardcoded build/native default when -o is absent.
        req = normalize_request(ParsedArgs(input_kind="file", input_path=src), invocation_cwd=invocation_subdir)
        expected_output = os.path.join(td, "dist", "hello")
        if req.output_path != expected_output:
            failures.append(f"case18: expected output-dir-derived path {expected_output!r}, got {req.output_path!r}")

        # Case 19: an explicit -o still wins over config's output-dir.
        req = normalize_request(
            ParsedArgs(input_kind="file", input_path=src, output_path="explicit_out"), invocation_cwd=td
        )
        if req.output_path != os.path.join(td, "explicit_out"):
            failures.append(f"case19: expected -o to win over output-dir, got {req.output_path!r}")

        # Case 20: config's keep-c/build-record (plain booleans) set the
        # *_requested flags even with no CLI flag at all; the actual default
        # path still stays deferred (native_exe_main.py's job), never guessed.
        req = normalize_request(ParsedArgs(input_kind="file", input_path=src), invocation_cwd=td)
        if not req.keep_c_requested or req.keep_c is not None:
            failures.append(f"case20: expected config keep-c to request without a path, got {req.keep_c_requested}, {req.keep_c!r}")
        if not req.build_record_requested or req.build_record is not None:
            failures.append(f"case20: expected config build-record to request without a path, got {req.build_record_requested}, {req.build_record!r}")

        # Case 21: a malformed sv0.toml raises RequestError (never a raw
        # ConfigError leaking past this module's own exception vocabulary).
        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write('[build]\nbogus-key = "oops"\n')
        try:
            normalize_request(ParsedArgs(input_kind="file", input_path=src), invocation_cwd=td)
            failures.append("case21: expected RequestError for a malformed sv0.toml, none raised")
        except RequestError:
            pass

    if failures:
        for f in failures:
            print(f"native_exe_request selftest FAIL: {f}")
        return 1

    print("native_exe_request: selftest OK (21 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_request: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
