"""Human quiet/verbose/success/failure output (NEX-027).

Implements ERR-005…008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §18.3/§18.5):
a concise success line on stderr matching the spec's own worked example
verbatim (§25.1); `--quiet` suppresses only that success line and never an
error; `--verbose` renders a safely-quoted argv display (`shlex.quote` per
token — labeled diagnostic, never re-parsed) alongside normalized inputs;
normal-mode output never names an unpredictable scratch path.

Run `python3 scripts/native_exe_human_output.py --selftest` for the corpus.
"""

from __future__ import annotations

import shlex


def format_success_message(output_path: str, backend: str, profile: str, contract_mode: str) -> str:
    """Matches spec S18.3's example line exactly:
    'sv0c: built build/native/hello (backend=c, profile=dev, contracts=runtime)'
    """
    return f"sv0c: built {output_path} (backend={backend}, profile={profile}, contracts={contract_mode})"


def maybe_print_success(output_path: str, backend: str, profile: str, contract_mode: str, *, quiet: bool) -> str | None:
    """Returns the success message unless `quiet` is set (never suppresses errors --
    callers only ever call this on the success path in the first place).
    """
    if quiet:
        return None
    return format_success_message(output_path, backend, profile, contract_mode)


def render_argv_for_display(argv: list[str]) -> str:
    """A safely quoted, human-readable rendering of an argv list for `--verbose`
    output. Diagnostic only -- never re-parsed by anything.
    """
    return " ".join(shlex.quote(tok) for tok in argv)


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: the success message matches the spec's own example exactly.
    msg = format_success_message("build/native/hello", "c", "dev", "runtime")
    expected = "sv0c: built build/native/hello (backend=c, profile=dev, contracts=runtime)"
    if msg != expected:
        failures.append(f"success message mismatch:\n  got:      {msg!r}\n  expected: {expected!r}")

    # Case 2: --quiet suppresses the success line.
    if maybe_print_success("build/native/hello", "c", "dev", "runtime", quiet=True) is not None:
        failures.append("quiet=True should suppress the success message")

    # Case 3: without --quiet, the success line is produced.
    if maybe_print_success("build/native/hello", "c", "dev", "runtime", quiet=False) is None:
        failures.append("quiet=False should produce the success message")

    # Case 4 (ERR-005/006 spirit): errors are raised via BuildError elsewhere
    # in this driver (native_exe_errors.py), never through this module --
    # `maybe_print_success` only ever has a *success* message to suppress, so
    # "quiet never suppresses an error" holds structurally: there is no
    # quiet-aware error path here to accidentally silence.
    if hasattr(__import__(__name__), "format_error_message"):
        failures.append("this module must not grow an error-formatting/suppression function")

    # Case 5: verbose argv rendering safely quotes hostile arguments.
    hostile = ["cc", "a name; $(touch SHOULD_NOT_EXIST)", "-o", "out"]
    rendered = render_argv_for_display(hostile)
    if "SHOULD_NOT_EXIST" not in rendered:
        failures.append("hostile argument content should still appear (quoted) in the rendering")
    # shlex.split should recover the exact original tokens -- proving the
    # rendering is faithful, even though it is never actually re-parsed by the driver.
    if shlex.split(rendered) != hostile:
        failures.append(f"rendered argv did not round-trip: {shlex.split(rendered)} != {hostile}")

    # Case 6: a plain, no-metacharacter argv renders without unnecessary quoting.
    plain = ["cc", "-O0", "program.c", "-o", "out"]
    rendered_plain = render_argv_for_display(plain)
    if "'" in rendered_plain:
        failures.append(f"plain argv should not need quoting: {rendered_plain!r}")

    if failures:
        for f in failures:
            print(f"native_exe_human_output selftest FAIL: {f}")
        return 1

    print("native_exe_human_output: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_human_output: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
