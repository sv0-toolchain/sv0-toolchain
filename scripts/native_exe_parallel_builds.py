"""Parallel distinct-output builds share no mutable state (NEX-035).

Implements REL-001
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`, AC-020):
reuses `native_exe_build.build_native_executable` under real `threading` —
≥4 concurrent builds to distinct inputs/outputs, each with a unique
fingerprint (a literal, distinguishing exit code) written into its own
program. Exercises `native_exe_core_compiler`'s lock (NEX-011 — serializes
only the core-compiler sub-step, not the whole pipeline) and
`native_exe_scratch`'s per-invocation uniqueness (NEX-008) under genuine
concurrency, not just at the unit level.

Run `python3 scripts/native_exe_parallel_builds.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading

from native_exe_build import build_native_executable

N_PARALLEL = 6


def _selftest() -> int:
    failures: list[str] = []
    lock = threading.Lock()

    with tempfile.TemporaryDirectory() as td:
        results: dict[int, int] = {}
        errors: dict[int, str] = {}

        def build_one(i: int) -> None:
            src = os.path.join(td, f"prog_{i}.sv0")
            with open(src, "w", encoding="utf-8") as f:
                # Each program's fingerprint is its own distinguishing exit code.
                f.write(f"fn main() -> i32 {{\n    return {i};\n}}\n")
            out = os.path.join(td, f"prog_{i}_out")
            try:
                build_native_executable("file", src, out, td, probe=False)
                proc = subprocess.run([out], capture_output=True)
                with lock:
                    results[i] = proc.returncode
            except Exception as exc:  # noqa: BLE001 - report any failure, don't hide it
                with lock:
                    errors[i] = str(exc)

        threads = [threading.Thread(target=build_one, args=(i,)) for i in range(N_PARALLEL)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if errors:
            failures.append(f"{len(errors)} build(s) raised: {errors}")

        for i in range(N_PARALLEL):
            if results.get(i) != i:
                failures.append(f"program {i}: expected exit {i}, got {results.get(i)} -- possible cross-contamination")

    if failures:
        for f in failures:
            print(f"native_exe_parallel_builds selftest FAIL: {f}")
        return 1

    print(f"native_exe_parallel_builds: selftest OK ({N_PARALLEL} concurrent builds, all correctly isolated)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_parallel_builds: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
