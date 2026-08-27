"""Full-corpus generated-C/runtime warning report (NEX-049b).

Implements TEST-008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §26.6): runs
every fixture in `sv0c/test/behavior/manifest.txt` through the accepted
warning flags (`native_exe_warning_policy.ACCEPTED_WARNING_FLAGS`),
compiles the emitted C, and classifies every warning actually observed
into one of three buckets: "suppressed" (a confirmed-harmless entry in
`SUPPRESSED_WARNINGS`, with its rationale), "tracked" (a real, known gap
in `TRACKED_GAPS`, deliberately left visible rather than suppressed), or
"unclassified" — an unclassified warning is §26.6's literal enforcement
point and is a hard failure here, never silently ignored. No shell flag
strings anywhere: the host compiler is always invoked with an explicit
argv list.

Compiles with `-c` (compile-only, no link) since warnings are a per-TU
compile-time concern; this deliberately does not touch
`native_exe_argv_builder.build_dev_profile_argv` (the R0 dev-profile argv
stays exactly Appendix B's shape) — this report is a separate, additive
check, not a change to how dev-profile builds actually compile.

Run `python3 scripts/native_exe_warning_report.py --selftest` for the
corpus, or `--run` to print a real report.
"""

from __future__ import annotations

import os
import re
import tempfile

from native_exe_cc_select import select_cc
from native_exe_emit_c import emit_c_only
from native_exe_runtime import resolve_runtime_dir
from native_exe_subprocess import run_argv
from native_exe_warning_policy import ACCEPTED_WARNING_FLAGS, SUPPRESSED_WARNINGS, TRACKED_GAPS

_WARNING_FLAG_RE = re.compile(r"\[-W([a-zA-Z0-9-]+)\]")


def _repo_root() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _manifest_rows(root: str) -> list[str]:
    manifest_path = os.path.join(root, "sv0c", "test", "behavior", "manifest.txt")
    rows: list[str] = []
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            rows.append(line.split("|")[0])
    return rows


def _bare_name(flag: str) -> str:
    return flag.removeprefix("-Wno-").removeprefix("-W")


def _classify_warning_lines(stderr: str) -> tuple[list[str], list[str], list[str]]:
    """Split every `warning:` line in `stderr` into (suppressed, tracked,
    unclassified). A `tracked` line is a known, real gap that is
    deliberately left visible (not suppressed) but also not a failure --
    see `native_exe_warning_policy.TRACKED_GAPS`'s own docstring for why.
    """
    suppressed_names = {_bare_name(s.flag) for s in SUPPRESSED_WARNINGS}
    tracked_names = {_bare_name(t.flag) for t in TRACKED_GAPS}
    suppressed: list[str] = []
    tracked: list[str] = []
    unclassified: list[str] = []
    for line in stderr.splitlines():
        if "warning:" not in line:
            continue
        match = _WARNING_FLAG_RE.search(line)
        name = match.group(1) if match else None
        if name in suppressed_names:
            suppressed.append(line)
        elif name in tracked_names:
            tracked.append(line)
        else:
            unclassified.append(line)
    return suppressed, tracked, unclassified


def build_warning_report(root: str | None = None) -> dict:
    """Compile every behavior-corpus fixture's emitted C under the accepted
    warning flags; return
    {fixture: {"suppressed": [...], "tracked": [...], "unclassified": [...]}}.
    """
    if root is None:
        root = _repo_root()

    sv0c_dir = os.path.join(root, "sv0c")
    runtime = resolve_runtime_dir()
    cc_path, _ = select_cc(None, os.environ)

    report: dict[str, dict] = {}

    for rel_path in _manifest_rows(root):
        abs_path = os.path.join(sv0c_dir, rel_path)
        if not os.path.isfile(abs_path):
            report[rel_path] = {"error": f"fixture missing: {abs_path}"}
            continue

        with tempfile.TemporaryDirectory() as td:
            c_path = os.path.join(td, "program.c")
            try:
                emit_c_only("file", abs_path, c_path, td)
            except Exception as exc:  # noqa: BLE001 - one broken fixture must not abort the report
                report[rel_path] = {"error": f"emit failed: {exc}"}
                continue

            obj_path = os.path.join(td, "program.o")
            argv = [
                cc_path,
                "-std=gnu99",
                "-O0",
                "-g",
                f"-I{runtime.dir}",
                *ACCEPTED_WARNING_FLAGS,
                "-c",
                c_path,
                "-o",
                obj_path,
            ]
            result = run_argv(argv)
            suppressed, tracked, unclassified = _classify_warning_lines(result.stderr or "")
            report[rel_path] = {"suppressed": suppressed, "tracked": tracked, "unclassified": unclassified}

    return report


def _selftest() -> int:
    failures: list[str] = []

    report = build_warning_report()

    if not report:
        failures.append("report is empty -- no fixtures were processed")

    total_unclassified = 0
    total_tracked = 0
    total_suppressed = 0
    for fixture, result in report.items():
        if "error" in result:
            failures.append(f"fixture {fixture!r} failed to emit/compile: {result['error']}")
            continue
        total_unclassified += len(result["unclassified"])
        total_tracked += len(result["tracked"])
        total_suppressed += len(result["suppressed"])
        for line in result["unclassified"]:
            failures.append(f"fixture {fixture!r}: unclassified warning: {line}")

    # The tracked-gap and suppressed buckets should each have caught at
    # least one real observed warning -- otherwise those classification
    # branches are dead code that happens to never fire, not a genuinely
    # exercised part of this report.
    if total_tracked == 0:
        failures.append("no warning matched a TRACKED_GAPS entry -- classification branch never exercised")
    if total_suppressed == 0:
        failures.append("no warning matched a SUPPRESSED_WARNINGS entry -- classification branch never exercised")

    if failures:
        for f in failures:
            print(f"native_exe_warning_report selftest FAIL: {f}")
        return 1

    print(
        f"native_exe_warning_report: selftest OK ({len(report)} fixture(s), "
        f"{total_suppressed} suppressed, {total_tracked} tracked, 0 unclassified)"
    )
    return 0


def _print_report() -> int:
    import json

    report = build_warning_report()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--run" in sys.argv:
        raise SystemExit(_print_report())
    print("native_exe_warning_report: library module; use --selftest or --run", file=sys.stderr)
    raise SystemExit(2)
