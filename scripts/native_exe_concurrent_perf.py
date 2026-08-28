"""Concurrent-build performance certification (NEX-055b, PERF-006).

Implements PERF-006
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "concurrent
distinct-output builds SHALL achieve parallel host compilation; no global
control-file serialization." Times N sequential builds against N
concurrent builds (reusing `native_exe_parallel_builds.py`'s
fingerprint-per-thread shape, NEX-035) and asserts the concurrent wall
time is meaningfully less than N times the per-build time -- real
parallelism, not merely "didn't crash."

**History, so the finding stays honest as it changes.** When this module
was first written, `native_exe_core_compiler.py`'s `CoreCompilerClient`
(NEX-011) still serialized the core-compiler sub-step behind a global
`flock` on `/tmp/.sv0_drv_path`. The measured finding at the time was that
this did NOT bottleneck overall wall time in practice, since the host
compile/link step (never serialized) dominates total build time for real
fixtures -- PERF-006's speedup bar was met even before the lock was gone.

**NEX-055c (REL-004) has since removed that lock entirely**
(`native_exe_core_compiler.py`'s `CoreCompilerClient.invoke()` now passes
the request via a per-call `SV0_DRV_REQUEST` env var, structurally
impossible to race on -- no shared file, no lock, no serialization of any
kind). PERF-006's literal text ("no global control-file serialization")
is now fully, structurally met, not merely "not a practical bottleneck."
This module still measures and reports the real number rather than
assuming it, since a future regression in the core-compiler path could
reintroduce serialization without this test catching it any other way.

Run `python3 scripts/native_exe_concurrent_perf.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import tempfile
import threading
import time

from native_exe_build import build_native_executable

# A generous minimum speedup bar -- kept modest even though the
# core-compiler lock is gone (NEX-055c), since this is a real-fixture
# wall-clock measurement (host-compiler/link time, disk, scheduler noise
# all vary by machine) and the bar only needs to catch a REGRESSION back
# to one-at-a-time queueing (which would show ~1.0x, not meaningfully
# more than 1x), not certify a specific multiplier.
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
