"""Same-output concurrent-build stress test (NEX-052b, AC-021).

Implements ART-013/REL-002
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §22.1): N
concurrent builds of DIFFERENT programs (each with its own distinguishing
fingerprint exit code, same technique as `native_exe_parallel_builds.py`,
NEX-035, adapted to the same-output case instead of distinct outputs) all
targeting the SAME final output path. After every thread finishes, the
published binary's observed exit code must be EXACTLY one of the N
fingerprints -- never a crash, never a value outside that set (which would
indicate a torn/mixed artifact) -- proving `native_exe_publish.publish_atomically`'s
`OutputLock`-wrapped `os.replace` (NEX-052a/b) never publishes a mixed
result even when every thread races for the identical destination path.

Run `python3 scripts/native_exe_same_output_stress.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import threading

from native_exe_build import build_native_executable

N_CONCURRENT = 6


def _selftest() -> int:
    failures: list[str] = []
    lock = threading.Lock()

    with tempfile.TemporaryDirectory() as td:
        shared_output = os.path.join(td, "shared_program")
        fingerprints = list(range(10, 10 + N_CONCURRENT))  # 10, 11, ..., distinguishable from 0/1/errors
        errors: dict[int, str] = {}
        succeeded: list[int] = []

        def build_one(fp: int) -> None:
            src = os.path.join(td, f"prog_{fp}.sv0")
            with open(src, "w", encoding="utf-8") as f:
                f.write(f"fn main() -> i32 {{\n    return {fp};\n}}\n")
            try:
                # Every thread targets shared_output -- the literal race
                # this test exists to stress.
                build_native_executable("file", src, shared_output, td, probe=False)
                with lock:
                    succeeded.append(fp)
            except Exception as exc:  # noqa: BLE001 - a build losing a coordination race is not itself a failure
                with lock:
                    errors[fp] = str(exc)

        threads = [threading.Thread(target=build_one, args=(fp,)) for fp in fingerprints]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        if not succeeded:
            failures.append(f"no build succeeded at all; errors: {errors}")

        if not os.path.isfile(shared_output):
            failures.append("no artifact was ever published to the shared output path")
        else:
            proc = subprocess.run([shared_output], capture_output=True)
            if proc.returncode not in fingerprints:
                failures.append(
                    f"published artifact's exit code {proc.returncode} is not one of the "
                    f"expected fingerprints {fingerprints} -- indicates a torn/mixed artifact"
                )
            elif proc.returncode not in succeeded:
                failures.append(
                    f"published artifact's exit code {proc.returncode} does not match any "
                    f"build this test itself observed as having succeeded ({succeeded}) -- "
                    "the published binary doesn't correspond to a real completed build"
                )

    if failures:
        for f in failures:
            print(f"native_exe_same_output_stress selftest FAIL: {f}")
        return 1

    print(f"native_exe_same_output_stress: selftest OK ({N_CONCURRENT} concurrent same-output builds)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_same_output_stress: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
