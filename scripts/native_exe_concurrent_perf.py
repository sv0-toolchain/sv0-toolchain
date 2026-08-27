"""Concurrent-build performance certification (NEX-055b, PERF-006).

Implements PERF-006
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "concurrent
distinct-output builds SHALL achieve parallel host compilation; no global
control-file serialization." Times N sequential builds against N
concurrent builds (reusing `native_exe_parallel_builds.py`'s
fingerprint-per-thread shape, NEX-035) and asserts the concurrent wall
time is meaningfully less than N times the per-build time -- real
parallelism, not merely "didn't crash."

**Honest, measured finding, not assumed**: `native_exe_core_compiler.py`'s
`CoreCompilerClient` (NEX-011) still serializes the core-compiler
sub-step behind a global `flock` on `/tmp/.sv0_drv_path` -- the exact
REL-004 gap this band's plan flags as needing a genuinely new sv0c-side
reentrant entry point (tracked separately, NEX-055c). This module
measures whether that serialization is actually a *bottleneck* for overall
wall time on real fixtures, given the host compile/link step (never
serialized) dominates total build time in practice, or whether it
measurably limits the achievable speedup -- and reports the real number
either way rather than assuming PERF-006 is met.

Run `python3 scripts/native_exe_concurrent_perf.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

from native_exe_build import build_native_executable

# A generous minimum speedup bar -- NOT "N times faster" (the core-compiler
# flock genuinely prevents that), but enough to prove concurrent builds are
# not simply queueing one-at-a-time behind a single global lock for their
# ENTIRE duration (which would show ~1.0x, not meaningfully more than 1x).
_MIN_ACCEPTABLE_SPEEDUP = 1.3


def _build_one(td: str, fingerprint: int) -> str:
    src = os.path.join(td, f"prog_{fingerprint}.sv0")
    with open(src, "w", encoding="utf-8") as f:
        f.write(f"fn main() -> i32 {{\n    return {fingerprint};\n}}\n")
    out = os.path.join(td, f"prog_{fingerprint}_out")
    build_native_executable("file", src, out, td, probe=False)
    return out


def _time_sequential(td: str, n: int) -> float:
    start = time.monotonic()
    for i in range(n):
        _build_one(os.path.join(td, f"seq_{i}"), 100 + i)
    return time.monotonic() - start


def _time_concurrent(td: str, n: int) -> float:
    threads_done: list[Exception | None] = [None] * n

    def worker(i: int) -> None:
        try:
            _build_one(os.path.join(td, f"conc_{i}"), 200 + i)
        except Exception as exc:  # noqa: BLE001
            threads_done[i] = exc

    start = time.monotonic()
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    errors = [e for e in threads_done if e is not None]
    if errors:
        raise RuntimeError(f"{len(errors)} concurrent build(s) raised: {errors}")
    return elapsed


def measure_speedup(n: int) -> dict:
    """Build `n` programs sequentially, then `n` more concurrently (fresh
    ones -- not reusing the sequential run's outputs, to keep filesystem
    cache effects symmetric). Returns timing + the measured speedup ratio.
    """
    with tempfile.TemporaryDirectory() as td:
        for sub in [f"seq_{i}" for i in range(n)] + [f"conc_{i}" for i in range(n)]:
            os.makedirs(os.path.join(td, sub), exist_ok=True)
        sequential_s = _time_sequential(td, n)
        concurrent_s = _time_concurrent(td, n)

    speedup = sequential_s / concurrent_s if concurrent_s > 0 else float("inf")
    return {
        "n": n,
        "sequential_s": sequential_s,
        "concurrent_s": concurrent_s,
        "speedup": speedup,
    }


def _selftest() -> int:
    failures: list[str] = []
    results = []

    for n in (2, 4):
        result = measure_speedup(n)
        results.append(result)
        print(
            f"native_exe_concurrent_perf: n={n} sequential={result['sequential_s']:.2f}s "
            f"concurrent={result['concurrent_s']:.2f}s speedup={result['speedup']:.2f}x"
        )
        if result["speedup"] < _MIN_ACCEPTABLE_SPEEDUP:
            failures.append(
                f"n={n}: measured speedup {result['speedup']:.2f}x is below the "
                f"{_MIN_ACCEPTABLE_SPEEDUP}x bar -- concurrent builds may be serializing "
                f"more than expected (see native_exe_core_compiler.py's flock, tracked as NEX-055c)"
            )

    if failures:
        for f in failures:
            print(f"native_exe_concurrent_perf selftest FAIL: {f}")
        return 1

    print(f"native_exe_concurrent_perf: selftest OK ({len(results)} n-value(s) measured)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_concurrent_perf: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
