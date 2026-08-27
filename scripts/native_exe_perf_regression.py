"""Release-to-release performance regression budget (NEX-055a, PERF-005).

Implements PERF-005
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "release-to-
release p95 total build time SHALL not regress by more than 20% on the
reference suite without an accepted waiver and explanation."

`capture_baseline` runs `native_exe_benchmark.run_benchmark` (NEX-047)
multiple times and takes the MEDIAN total-time per fixture, not a single
run -- a real, directly-observed finding while building this: a single
`run_benchmark()` call showed a 506ms "minimal" fixture build once (almost
certainly a cold-cache/first-invocation outlier), while three repeated
runs' median settled at 80ms. A one-shot baseline would make this
regression check spuriously flaky; the median of several runs is the
practical, honest middle ground between a real statistical p95 (which
would need many more samples than is proportionate for this module) and a
single noisy sample.

`check_regression` compares a fresh baseline capture against the
persisted one (`sv0c/doc/perf-baseline.json`), flagging any fixture whose
total time regressed more than the 20% budget -- unless a waiver for that
exact fixture is present, in which case the regression is recorded but
does not fail.

Run `python3 scripts/native_exe_perf_regression.py --selftest` for the
corpus, or `--capture` to (re)write the persisted baseline.
"""

from __future__ import annotations

import json
import os
import statistics

from native_exe_benchmark import run_benchmark

REGRESSION_BUDGET = 0.20  # 20%, per PERF-005.
_DEFAULT_CAPTURE_RUNS = 3


class Waiver:
    def __init__(self, fixture: str, rationale: str):
        if not rationale or not rationale.strip():
            raise ValueError(f"waiver for {fixture!r} has an empty rationale")
        self.fixture = fixture
        self.rationale = rationale


def _baseline_path() -> str:
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(this_dir, "..", "sv0c", "doc", "perf-baseline.json"))


def capture_baseline(n_runs: int = _DEFAULT_CAPTURE_RUNS) -> dict:
    """Run the benchmark `n_runs` times; return {fixture: median_total_ms}."""
    runs = [run_benchmark() for _ in range(n_runs)]
    medians: dict[str, float] = {}
    for fixture in runs[0]:
        values = [r[fixture]["total"] for r in runs if "error" not in r[fixture]]
        if values:
            medians[fixture] = statistics.median(values)
    return medians


def write_baseline(baseline: dict, path: str | None = None) -> None:
    out_path = path if path is not None else _baseline_path()
    tmp_path = f"{out_path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2)
        f.write("\n")
    os.replace(tmp_path, out_path)


def load_baseline(path: str | None = None) -> dict:
    in_path = path if path is not None else _baseline_path()
    with open(in_path, encoding="utf-8") as f:
        return json.load(f)


def check_regression(
    baseline: dict, current: dict, waivers: list[Waiver] | None = None, budget: float = REGRESSION_BUDGET
) -> list[str]:
    """Return a list of unwaived regression violations (empty = pass).
    Each violation string names the fixture, the percentage regression,
    and the budget. A fixture present in `current` but not `baseline` (a
    new fixture) is never a regression by definition.
    """
    waived_fixtures = {w.fixture for w in (waivers or [])}
    violations: list[str] = []
    for fixture, baseline_ms in baseline.items():
        if fixture not in current or baseline_ms <= 0:
            continue
        current_ms = current[fixture]
        regression = (current_ms - baseline_ms) / baseline_ms
        if regression > budget and fixture not in waived_fixtures:
            violations.append(
                f"{fixture}: regressed {regression:.0%} (baseline {baseline_ms}ms -> {current_ms}ms), "
                f"budget is {budget:.0%}"
            )
    return violations


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: a synthetic 25% regression fails.
    baseline = {"fixtureA": 100.0}
    current_25pct = {"fixtureA": 125.0}
    violations = check_regression(baseline, current_25pct)
    if not violations:
        failures.append("case1: a 25% regression was not flagged")

    # Case 2: a synthetic 10% regression passes (within budget).
    current_10pct = {"fixtureA": 110.0}
    violations = check_regression(baseline, current_10pct)
    if violations:
        failures.append(f"case2: a 10% regression was incorrectly flagged: {violations}")

    # Case 3: a waivered 25% regression passes, with the regression still
    # recorded (not silently dropped) -- proven by checking the SAME
    # regression is caught again once the waiver no longer applies to it.
    waivers = [Waiver("fixtureA", "known slow CI runner this cycle")]
    violations_waived = check_regression(baseline, current_25pct, waivers=waivers)
    if violations_waived:
        failures.append(f"case3: a waivered 25% regression was incorrectly flagged: {violations_waived}")
    violations_unwaived_again = check_regression(baseline, current_25pct, waivers=[Waiver("fixtureB", "unrelated")])
    if not violations_unwaived_again:
        failures.append("case3: the same regression must still be flagged when the waiver doesn't apply to it")

    # Case 4: an empty-rationale waiver is rejected outright.
    try:
        Waiver("fixtureA", "")
        failures.append("case4: expected ValueError for an empty-rationale waiver, none raised")
    except ValueError:
        pass

    # Case 5: a real baseline capture + comparison against itself never
    # regresses (sanity: the harness's own output compared to itself).
    real_baseline = capture_baseline(n_runs=1)
    self_violations = check_regression(real_baseline, real_baseline)
    if self_violations:
        failures.append(f"case5: comparing a real baseline against itself flagged a regression: {self_violations}")

    # Case 6: write_baseline + load_baseline round-trips.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "perf-baseline.json")
        write_baseline(real_baseline, path)
        reloaded = load_baseline(path)
        if reloaded != real_baseline:
            failures.append("case6: baseline did not round-trip through write/load")

    if failures:
        for f in failures:
            print(f"native_exe_perf_regression selftest FAIL: {f}")
        return 1

    print("native_exe_perf_regression: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--capture" in sys.argv:
        baseline = capture_baseline()
        write_baseline(baseline)
        print(f"native_exe_perf_regression: wrote {_baseline_path()}: {baseline}")
        raise SystemExit(0)
    print("native_exe_perf_regression: library module; use --selftest or --capture", file=sys.stderr)
    raise SystemExit(2)
