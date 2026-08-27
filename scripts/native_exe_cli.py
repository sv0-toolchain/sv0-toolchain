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

This module has no ``if __name__ == "__main__"`` production entry point yet —
it is wired into ``./scripts/sv0 native-compile`` in a later slice once there
is something downstream to run. Run ``python3 scripts/native_exe_cli.py
--selftest`` to exercise the table-driven parser corpus.
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
    profile: str = "dev"
    contract_mode: str = "runtime"
    cc: str | None = None
    verbose: bool = False
    quiet: bool = False
    emit_seen: bool = False  # true if an explicit --emit=exe token was given
    trailing: list[str] = field(default_factory=list)  # tokens after `--`


# Options that take exactly one value and may appear at most once (CLI-003:
# "repeated scalar options are usage errors unless the option explicitly
# documents repetition" — none of these document repetition).
_SCALAR_VALUE_OPTIONS = {"-o", "--project", "--cc"}
_SCALAR_EQUALS_OPTIONS = {"--profile", "--contract-mode", "--emit"}


def parse_args(argv: list[str]) -> ParsedArgs:
    """Parse one native-compile invocation's argv into a ParsedArgs.

    Raises UsageError (CLI-003-class) on any unknown, conflicting, repeated
    scalar, or incomplete option (CLI-002, CLI-003, CLI-005). `--` terminates
    option parsing (CLI-006); everything after it is a positional/opaque token,
    never re-interpreted as an option.
    """
    seen_scalars: set[str] = set()
    output_path: str | None = None
    profile = "dev"
    contract_mode = "runtime"
    cc: str | None = None
    verbose = False
    quiet = False
    emit_seen = False
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
                    if value != "exe":
                        raise UsageError(
                            f"--emit={value} conflicts with this native-executable driver "
                            "(only --emit=exe is accepted here)"
                        )
                    emit_seen = True
                matched_equals = True
                break
        if matched_equals:
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
        {"emit_seen": True},
    ),
    (
        "-- terminates option parsing (hostile leading-hyphen path)",
        ["--", "-weird-name.sv0"],
        {"input_kind": "file", "input_path": "-weird-name.sv0"},
    ),
    ("no operand at all", [], UsageError),
    ("unknown option", ["--bogus", "hello.sv0"], UsageError),
    ("conflicting emit value", ["--emit=c", "hello.sv0"], UsageError),
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
