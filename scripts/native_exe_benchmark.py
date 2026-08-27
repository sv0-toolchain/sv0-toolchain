"""Phase-timing + reference benchmark harness (NEX-047).

Implements PERF-001…004
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §18.7): a
representative-fixture benchmark that wraps `build_native_executable` with
`PhaseTimer` (NEX-041) and reports per-fixture timings. This is the harness
existing and running -- establishing the schema and the fixture selection --
not a performance *regression* gate (that comparison is R1/PERF-005's job
once a baseline exists to compare against).

Fixture set:
  - a minimal single-file program (smallest possible frontend+emit+link work);
  - the median-size and largest files in `sv0c/test/behavior/manifest.txt`
    (by source byte size), as representative "typical" and "large" single
    files;
  - the `sv0c/test/integration/modules/` project fixture (multi-module,
    NEX-030's own fixture), as the one project-mode data point.

Run `python3 scripts/native_exe_benchmark.py --selftest` for the corpus, or
`python3 scripts/native_exe_benchmark.py --run` to print a real report.
"""

from __future__ import annotations

import os
import tempfile

from native_exe_build import build_native_executable
from native_exe_json_output import PhaseTimer

_MINIMAL_SOURCE = "fn main() -> i32 {\n    return 0;\n}\n"


def _repo_root() -> str:
    return os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def _behavior_manifest_rows(root: str) -> list[tuple[str, int]]:
    manifest_path = os.path.join(root, "sv0c", "test", "behavior", "manifest.txt")
    rows: list[tuple[str, int]] = []
    if not os.path.isfile(manifest_path):
        return rows
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            rel_path, exit_str = fields[0], fields[1]
            rows.append((rel_path, int(exit_str)))
    return rows


def _pick_median_and_largest(root: str) -> list[tuple[str, str]]:
    """Return [(label, absolute_path), ...] for the median-size and
    largest behavior-corpus fixtures, by source byte size.
    """
    rows = _behavior_manifest_rows(root)
    sv0c_dir = os.path.join(root, "sv0c")
    sized = []
    for rel_path, _exit in rows:
        abs_path = os.path.join(sv0c_dir, rel_path)
        if os.path.isfile(abs_path):
            sized.append((os.path.getsize(abs_path), abs_path))
    if not sized:
        return []
    sized.sort(key=lambda pair: pair[0])
    median_path = sized[len(sized) // 2][1]
    largest_path = sized[-1][1]
    return [("median", median_path), ("largest", largest_path)]


def run_benchmark(root: str | None = None) -> dict:
    """Build every fixture once, timed with `PhaseTimer`, returning a report
    dict of {fixture_name: timings_ms} (NEX-041's schema). Never raises for
    an individual fixture failure -- records `{"error": str(exc)}` for that
    fixture instead, so one broken fixture doesn't abort the whole report.
    """
    if root is None:
        root = _repo_root()

    report: dict[str, dict] = {}

    with tempfile.TemporaryDirectory() as td:
        # Fixture 1: minimal single file.
        minimal_src = os.path.join(td, "minimal.sv0")
        with open(minimal_src, "w", encoding="utf-8") as f:
            f.write(_MINIMAL_SOURCE)
        report["minimal"] = _time_one_build("file", minimal_src, os.path.join(td, "minimal_out"), td)

        # Fixtures 2/3: median-size and largest behavior-corpus files.
        for label, abs_path in _pick_median_and_largest(root):
            out = os.path.join(td, f"{label}_out")
            report[label] = _time_one_build("file", abs_path, out, td)

        # Fixture 4: the modules project (multi-module, project mode).
        project_dir = os.path.join(root, "sv0c", "test", "integration", "modules")
        if os.path.isdir(project_dir):
            out = os.path.join(td, "modules_out")
            report["project_modules"] = _time_one_build("project", project_dir, out, td)

    return report


def _time_one_build(input_kind: str, input_path: str, output_path: str, invocation_cwd: str) -> dict:
    timer = PhaseTimer()
    try:
        with timer.phase("build"):
            build_native_executable(input_kind, input_path, output_path, invocation_cwd, probe=False)
    except Exception as exc:  # noqa: BLE001 - one broken fixture must not abort the report
        return {"error": str(exc)}
    return timer.timings_ms()


def _selftest() -> int:
    failures: list[str] = []

    report = run_benchmark()

    expected_fixtures = {"minimal"}
    for fixture in expected_fixtures:
        if fixture not in report:
            failures.append(f"expected fixture {fixture!r} missing from report: {list(report.keys())}")

    for fixture, timings in report.items():
        if "error" in timings:
            failures.append(f"fixture {fixture!r} failed to build: {timings['error']}")
            continue
        if "total" not in timings:
            failures.append(f"fixture {fixture!r} timings missing 'total': {timings}")
        elif timings["total"] < 0:
            failures.append(f"fixture {fixture!r} reported a negative total: {timings}")
        for phase_name, value in timings.items():
            if value < 0:
                failures.append(f"fixture {fixture!r} phase {phase_name!r} reported negative: {value}")

    # The median/largest and project fixtures are present whenever their
    # source data exists on disk -- confirm at least one of them showed up,
    # since this repo's own checkout always has the behavior manifest.
    if "median" not in report and "largest" not in report:
        failures.append("neither 'median' nor 'largest' behavior-corpus fixtures appeared in the report")

    if failures:
        for f in failures:
            print(f"native_exe_benchmark selftest FAIL: {f}")
        return 1

    print(f"native_exe_benchmark: selftest OK ({len(report)} fixture(s) in report)")
    return 0


def _print_report() -> int:
    import json

    report = run_benchmark()
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--run" in sys.argv:
        raise SystemExit(_print_report())
    print("native_exe_benchmark: library module; use --selftest or --run", file=sys.stderr)
    raise SystemExit(2)
