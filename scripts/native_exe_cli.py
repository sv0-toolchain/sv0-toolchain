"""CLI argv parsing for the sv0c native runtime executable driver (NEX-002, NEX-010).

Implements spec CLI-001…006 (`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`
§11.2, §11.5) for the workspace adapter grammar, plus GOV-002/GOV-003 bytecode
isolation (NEX-010): `--target=vm` and `.sv0b` input are rejected here, at
parse time, before any code path exists that could invoke a host compiler or
`sv0vm` — the earliest point bytecode isolation can be enforced.

    ./scripts/sv0 native-compile [OPTIONS] <file.sv0>
    ./scripts/sv0 native-compile [OPTIONS] --project <directory>

Per §11.1 the workspace spelling "SHALL construct the same normalized build
request" as the eventual installed `sv0c --emit=exe` spelling — this module is
that shared parser (OD-001: Python, isolated from the bash entry point so it is
independently testable). It only parses and validates argv; path resolution,
the full ``NativeBuildRequest`` shape, and phase sequencing are later slices
(NEX-003 onward).

Also carries the R0.1 provenance flags (CLI-014…016: ``--keep-c[=<path>]``,
``--message-format=human|json``, ``--build-record[=<path>]``) even though
this module has no production entry point of its own — that is
``scripts/native_exe_main.py`` (NEX-059), which imports this parser
directly. Run ``python3 scripts/native_exe_cli.py --selftest`` to exercise
the table-driven parser corpus.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class UsageError(Exception):
    """Raised for any CLI-003-class parse failure (usage error, exit class 2)."""


@dataclass
class ParsedArgs:
    """Raw parsed CLI state for one invocation, before path/config resolution."""

    input_kind: str  # "file" | "project"
    input_path: str  # positional file path, or the --project directory operand
    output_path: str | None = None  # -o value, if given
    profile: str | None = None  # None means "not given on the CLI" -- sv0.toml/default apply (§11.4/§17)
    contract_mode: str | None = None  # None means "not given on the CLI" -- sv0.toml/default apply
    cc: str | None = None
    verbose: bool = False
    quiet: bool = False
    emit_seen: bool = False  # true if an explicit --emit=<value> token was given
    emit_value: str = "exe"  # "exe" | "c" -- defaults to "exe" when --emit is never given
    keep_c_seen: bool = False  # true if --keep-c (bare or =value) was given
    keep_c_path: str | None = None  # explicit path from --keep-c=<path>, else None
    message_format: str = "human"  # --message-format=human|json
    build_record_seen: bool = False  # true if --build-record (bare or =value) was given
    build_record_path: str | None = None  # explicit path from --build-record=<path>, else None
    trailing: list[str] = field(default_factory=list)  # tokens after `--`


# Options that take exactly one value and may appear at most once (CLI-003:
# "repeated scalar options are usage errors unless the option explicitly
# documents repetition" — none of these document repetition).
_SCALAR_VALUE_OPTIONS = {"-o", "--project", "--cc"}
_SCALAR_EQUALS_OPTIONS = {"--profile", "--contract-mode", "--emit", "--message-format"}
# CLI-014/016: options valid either bare (a documented default applies) or
# with an explicit `=<path>` value -- distinct from _SCALAR_EQUALS_OPTIONS,
# which always REQUIRES a value.
_OPTIONAL_VALUE_OPTIONS = {"--keep-c", "--build-record"}


def parse_args(argv: list[str]) -> ParsedArgs:
    """Parse one native-compile invocation's argv into a ParsedArgs.

    Raises UsageError (CLI-003-class) on any unknown, conflicting, repeated
    scalar, or incomplete option (CLI-002, CLI-003, CLI-005). `--` terminates
    option parsing (CLI-006); everything after it is a positional/opaque token,
    never re-interpreted as an option.
    """
    seen_scalars: set[str] = set()
    output_path: str | None = None
    profile: str | None = None
    contract_mode: str | None = None
    cc: str | None = None
    verbose = False
    quiet = False
    emit_seen = False
    emit_value = "exe"
    keep_c_seen = False
    keep_c_path: str | None = None
    message_format = "human"
    build_record_seen = False
    build_record_path: str | None = None
    project_dir: str | None = None
    positional: list[str] = []
    trailing: list[str] = []

    i = 0
    n = len(argv)
    opts_done = False
    while i < n:
        arg = argv[i]

        if not opts_done and arg == "--":
            opts_done = True
            i += 1
            continue

        if opts_done:
            trailing.append(arg)
            i += 1
            continue

        if not opts_done and arg == "--target=vm":
            raise UsageError(
                "--target=vm cannot be combined with the native executable driver "
                "(bytecode isolation: GOV-002/GOV-003 — .sv0b/sv0vm never enter this path)"
            )

        if arg in _SCALAR_VALUE_OPTIONS:
            if arg in seen_scalars:
                raise UsageError(f"repeated option: {arg}")
            seen_scalars.add(arg)
            if i + 1 >= n:
                raise UsageError(f"option {arg} requires a value")
            value = argv[i + 1]
            if arg == "-o":
                if value == "":
                    raise UsageError("-o requires a non-empty path")
                if value == "-":
                    raise UsageError("-o - is invalid: executables cannot be streamed to stdout")
                output_path = value
            elif arg == "--project":
                project_dir = value
            elif arg == "--cc":
                cc = value
            i += 2
            continue

        matched_equals = False
        for opt in _SCALAR_EQUALS_OPTIONS:
            prefix = opt + "="
            if arg.startswith(prefix):
                if opt in seen_scalars:
                    raise UsageError(f"repeated option: {opt}")
                seen_scalars.add(opt)
                value = arg[len(prefix):]
                if not value:
                    raise UsageError(f"option {opt} requires a value")
                if opt == "--profile":
                    profile = value
                elif opt == "--contract-mode":
                    contract_mode = value
                elif opt == "--emit":
                    if value not in ("exe", "c"):
                        raise UsageError(
                            f"--emit={value} is invalid for this driver (want 'exe' or 'c')"
                        )
                    emit_seen = True
                    emit_value = value
                elif opt == "--message-format":
                    if value not in ("human", "json"):
                        raise UsageError(
                            f"--message-format={value} is invalid (want 'human' or 'json')"
                        )
                    message_format = value
                matched_equals = True
                break
        if matched_equals:
            i += 1
            continue

        matched_optional = False
        for opt in _OPTIONAL_VALUE_OPTIONS:
            prefix = opt + "="
            if arg == opt or arg.startswith(prefix):
                if opt in seen_scalars:
                    raise UsageError(f"repeated option: {opt}")
                seen_scalars.add(opt)
                value = arg[len(prefix):] if arg.startswith(prefix) else None
                if value == "":
                    raise UsageError(f"option {opt} requires a non-empty path when given a value")
                if opt == "--keep-c":
                    keep_c_seen = True
                    keep_c_path = value
                elif opt == "--build-record":
                    build_record_seen = True
                    build_record_path = value
                matched_optional = True
                break
        if matched_optional:
            i += 1
            continue

        if arg == "--verbose":
            verbose = True
            i += 1
            continue
        if arg == "--quiet":
            quiet = True
            i += 1
            continue

        if arg.startswith("-") and arg != "-":
            raise UsageError(f"unknown option: {arg}")

        positional.append(arg)
        i += 1

    if verbose and quiet:
        raise UsageError("--verbose and --quiet are mutually exclusive")

    if emit_value == "c":
        # CLI-014/native_exe_emit_c.emit_c_only's own documented contract:
        # "--emit=c has no default-naming rule of its own in the spec; a
        # caller always supplies -o" -- enforced here, at parse time, the
        # same place every other complete-argv-shape rule in this function
        # lives, rather than discovered later as a confusing runtime error.
        if output_path is None:
            raise UsageError("--emit=c requires an explicit -o path (no default naming)")
        # --keep-c/--build-record are executable-build artifacts (retained
        # staging C alongside a published binary; a build record describing
        # a published binary's checksums) -- neither has a coherent meaning
        # when no executable is ever produced, so reject rather than
        # silently ignore or produce a nonsensical/empty record.
        if keep_c_seen:
            raise UsageError("--keep-c has no effect with --emit=c (the emitted C IS the -o output already)")
        if build_record_seen:
            raise UsageError("--build-record requires --emit=exe (no executable artifact exists under --emit=c)")
        if message_format == "json":
            # native_exe_json_output.build_event's schema is executable-build
            # shaped (a "compiler" sub-object that only exists once a host
            # compiler actually runs) -- rather than fabricate placeholder
            # compiler identity for an event that never probes one, reject
            # the combination outright.
            raise UsageError("--message-format=json requires --emit=exe (no compiler identity to report under --emit=c)")

    if project_dir is not None:
        if positional or trailing:
            raise UsageError("--project takes no additional file operand")
        return ParsedArgs(
            input_kind="project",
            input_path=project_dir,
            output_path=output_path,
            profile=profile,
            contract_mode=contract_mode,
            cc=cc,
            verbose=verbose,
            quiet=quiet,
            emit_seen=emit_seen,
            emit_value=emit_value,
            keep_c_seen=keep_c_seen,
            keep_c_path=keep_c_path,
            message_format=message_format,
            build_record_seen=build_record_seen,
            build_record_path=build_record_path,
            trailing=trailing,
        )

    all_positional = positional + trailing
    if len(all_positional) == 0:
        raise UsageError("exactly one source file or one --project directory is required")
    if len(all_positional) > 1:
        raise UsageError("exactly one source file is required, got multiple operands")

    if all_positional[0].endswith(".sv0b"):
        raise UsageError(
            f"{all_positional[0]!r} is bytecode input: .sv0b cannot be converted to a "
            "native executable (bytecode isolation: GOV-002 — this path only accepts .sv0 "
            "source compiled fresh through the C backend)"
        )

    return ParsedArgs(
        input_kind="file",
        input_path=all_positional[0],
        output_path=output_path,
        profile=profile,
        contract_mode=contract_mode,
        cc=cc,
        verbose=verbose,
        quiet=quiet,
        emit_seen=emit_seen,
        emit_value=emit_value,
        keep_c_seen=keep_c_seen,
        keep_c_path=keep_c_path,
        message_format=message_format,
        build_record_seen=build_record_seen,
        build_record_path=build_record_path,
        trailing=[],
    )


# ── table-driven parser corpus (NEX-002 red test) ─────────────────────────

_CASES: list[tuple[str, list[str], dict | type]] = [
    ("minimal file", ["hello.sv0"], {"input_kind": "file", "input_path": "hello.sv0"}),
    (
        "explicit output",
        ["-o", "dist/hello", "hello.sv0"],
        {"input_kind": "file", "input_path": "hello.sv0", "output_path": "dist/hello"},
    ),
    (
        "project mode",
        ["--project", "calculator"],
        {"input_kind": "project", "input_path": "calculator"},
    ),
    (
        "contract mode + cc",
        ["--contract-mode=verified", "--cc", "/usr/bin/clang", "verified.sv0"],
        {"contract_mode": "verified", "cc": "/usr/bin/clang"},
    ),
    (
        "explicit --emit=exe is accepted",
        ["--emit=exe", "hello.sv0"],
        {"emit_seen": True, "emit_value": "exe"},
    ),
    (
        "--emit=c with -o is accepted (CLI-014)",
        ["--emit=c", "-o", "out.c", "hello.sv0"],
        {"emit_seen": True, "emit_value": "c", "output_path": "out.c"},
    ),
    (
        "--emit=c without -o is a usage error (no default naming)",
        ["--emit=c", "hello.sv0"],
        (UsageError, "requires an explicit -o"),
    ),
    (
        "--emit=c with --keep-c is a usage error",
        ["--emit=c", "-o", "out.c", "--keep-c", "hello.sv0"],
        (UsageError, "--keep-c has no effect"),
    ),
    (
        "--emit=c with --build-record is a usage error",
        ["--emit=c", "-o", "out.c", "--build-record", "hello.sv0"],
        (UsageError, "--build-record requires --emit=exe"),
    ),
    (
        "--emit=c with --message-format=json is a usage error",
        ["--emit=c", "-o", "out.c", "--message-format=json", "hello.sv0"],
        (UsageError, "--message-format=json requires --emit=exe"),
    ),
    (
        "-- terminates option parsing (hostile leading-hyphen path)",
        ["--", "-weird-name.sv0"],
        {"input_kind": "file", "input_path": "-weird-name.sv0"},
    ),
    ("no operand at all", [], UsageError),
    ("unknown option", ["--bogus", "hello.sv0"], UsageError),
    ("invalid emit value", ["--emit=bogus", "hello.sv0"], (UsageError, "want 'exe' or 'c'")),
    ("repeated scalar option", ["-o", "a", "-o", "b", "hello.sv0"], UsageError),
    ("incomplete option (missing value)", ["-o"], UsageError),
    ("-o - is invalid for executable output", ["-o", "-", "hello.sv0"], UsageError),
    ("two positional files", ["a.sv0", "b.sv0"], UsageError),
    ("--project plus a stray positional", ["--project", "dir", "extra.sv0"], UsageError),
    ("--verbose and --quiet together", ["--verbose", "--quiet", "hello.sv0"], UsageError),
    (
        "--target=vm rejected (GOV-002/003 bytecode isolation)",
        ["--target=vm", "hello.sv0"],
        (UsageError, "bytecode isolation"),
    ),
    (
        "--target=vm after --emit=exe rejected",
        ["--emit=exe", "--target=vm", "hello.sv0"],
        (UsageError, "bytecode isolation"),
    ),
    (
        ".sv0b input rejected (GOV-002 bytecode isolation)",
        ["program.sv0b"],
        (UsageError, "bytecode isolation"),
    ),
    (
        "--keep-c bare (CLI-014/015)",
        ["--keep-c", "hello.sv0"],
        {"keep_c_seen": True, "keep_c_path": None},
    ),
    (
        "--keep-c=<path> (CLI-014/015)",
        ["--keep-c=build/native/hello.c", "hello.sv0"],
        {"keep_c_seen": True, "keep_c_path": "build/native/hello.c"},
    ),
    (
        "repeated --keep-c is a usage error",
        ["--keep-c", "--keep-c=x.c", "hello.sv0"],
        UsageError,
    ),
    (
        "--keep-c= with an empty value is a usage error",
        ["--keep-c=", "hello.sv0"],
        UsageError,
    ),
    (
        "--message-format=json (CLI-016)",
        ["--message-format=json", "hello.sv0"],
        {"message_format": "json"},
    ),
    (
        "--message-format=human is the explicit default (CLI-016)",
        ["--message-format=human", "hello.sv0"],
        {"message_format": "human"},
    ),
    (
        "--message-format with an invalid value is a usage error",
        ["--message-format=xml", "hello.sv0"],
        UsageError,
    ),
    (
        "repeated --message-format is a usage error",
        ["--message-format=json", "--message-format=human", "hello.sv0"],
        UsageError,
    ),
    (
        "--build-record bare (CLI-016)",
        ["--build-record", "hello.sv0"],
        {"build_record_seen": True, "build_record_path": None},
    ),
    (
        "--build-record=<path> (CLI-016)",
        ["--build-record=build/native/hello.record.json", "hello.sv0"],
        {"build_record_seen": True, "build_record_path": "build/native/hello.record.json"},
    ),
    (
        "repeated --build-record is a usage error",
        ["--build-record", "--build-record=x.json", "hello.sv0"],
        UsageError,
    ),
    (
        "all three R0.1 flags together",
        ["--keep-c=k.c", "--message-format=json", "--build-record=r.json", "hello.sv0"],
        {"keep_c_path": "k.c", "message_format": "json", "build_record_path": "r.json"},
    ),
]


def _selftest() -> int:
    failures = []
    for name, argv, expected in _CASES:
        expects_error = expected is UsageError or (isinstance(expected, tuple) and expected[0] is UsageError)
        required_substring = expected[1] if isinstance(expected, tuple) else None

        try:
            result = parse_args(list(argv))
        except UsageError as exc:
            if not expects_error:
                failures.append(f"{name}: expected success, got UsageError({exc})")
            elif required_substring is not None and required_substring not in str(exc):
                failures.append(f"{name}: UsageError message {str(exc)!r} missing required substring {required_substring!r}")
            continue
        if expects_error:
            failures.append(f"{name}: expected UsageError, got {result}")
            continue
        for key, val in expected.items():
            actual = getattr(result, key)
            if actual != val:
                failures.append(f"{name}: field {key} = {actual!r}, expected {val!r}")

    if failures:
        for f in failures:
            print(f"native_exe_cli selftest FAIL: {f}")
        return 1

    print(f"native_exe_cli: selftest OK ({len(_CASES)} cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_cli: no production entry point yet (NEX-002 parser only); use --selftest", file=sys.stderr)
    raise SystemExit(2)
