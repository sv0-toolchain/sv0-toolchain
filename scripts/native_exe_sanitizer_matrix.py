"""Sanitizer matrix: 048b's fixtures under ASan/UBSan, -O0 and -O2 (NEX-050b).

Implements TEST-007
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §26.7):
"sanitizer jobs SHALL include ... optimized (`-O2`) and unoptimized
builds." Runs every fixture from `sv0c/doc/native-executable-sanitizer-fixtures.md`
(NEX-048b) through `native_exe_sanitizer_build.build_sanitized_executable`
at both optimization levels (an extra `-O2` in `extra_cc_args` overrides
the dev profile's fixed `-O0` -- both GCC and Clang honor the
last-specified `-O` flag; confirmed directly, not assumed).

Intentional process-lifetime allocations are classified via
`sv0c/runtime/lsan-suppressions.txt` (NEX-050b) -- observed directly that
LeakSanitizer doesn't run at all on macOS (Apple's ASan runtime has no
leak-detection support), so this module's own local run can only confirm
"no crash, no UBSan finding on the clean fixtures, and the known-UB
fixture is still caught" — the suppression file's actual load-bearing
effect is on NEX-050c's Linux CI job, not provable from this machine.

Run `python3 scripts/native_exe_sanitizer_matrix.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from native_exe_build import build_native_executable
from native_exe_sanitizer_build import SANITIZE_FLAGS, sanitizer_env

_SAFE_FIXTURES = [("box_deref_chain_stress.sv0", 210), ("vec_growth_stress.sv0", 188)]
_UB_FIXTURES = [
    "ub_arith_neg_i32_min.sv0",
    "ub_arith_div_i32_min_by_neg1.sv0",
    "ub_arith_mod_i32_min_by_neg1.sv0",
]
_OPT_LEVELS = ["-O0", "-O2"]


def _fixture_path(name: str) -> str:
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(this_dir, "..", "sv0c", "test", "behavior", "cases", name))


def _selftest() -> int:
    failures: list[str] = []

    for name, expected_exit in _SAFE_FIXTURES:
        path = _fixture_path(name)
        if not os.path.isfile(path):
            failures.append(f"missing safe fixture: {path}")
            continue
        for opt in _OPT_LEVELS:
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "out")
                result = build_native_executable(
                    "file", path, out, td, probe=False, extra_cc_args=[*SANITIZE_FLAGS, opt]
                )
                proc = subprocess.run([result.output_path], capture_output=True, text=True, env=sanitizer_env())
                if proc.returncode != expected_exit:
                    failures.append(
                        f"{name} at {opt}: rc={proc.returncode}, expected {expected_exit}, "
                        f"stderr={proc.stderr!r}"
                    )
                if proc.stderr.strip():
                    failures.append(f"{name} at {opt}: unexpected sanitizer output on a clean fixture: {proc.stderr!r}")

    for name in _UB_FIXTURES:
        path = _fixture_path(name)
        if not os.path.isfile(path):
            failures.append(f"missing UB fixture: {path}")
            continue
        for opt in _OPT_LEVELS:
            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "out")
                result = build_native_executable(
                    "file", path, out, td, probe=False, extra_cc_args=[*SANITIZE_FLAGS, opt]
                )
                proc = subprocess.run([result.output_path], capture_output=True, text=True, env=sanitizer_env())
                stderr_lower = proc.stderr.lower()
                if "runtime error" not in stderr_lower:
                    failures.append(f"{name} at {opt}: UBSan did not report a runtime error: {proc.stderr!r}")

    if failures:
        for f in failures:
            print(f"native_exe_sanitizer_matrix selftest FAIL: {f}")
        return 1

    print(
        f"native_exe_sanitizer_matrix: selftest OK "
        f"({len(_SAFE_FIXTURES)} safe + {len(_UB_FIXTURES)} UB fixture(s), "
        f"{len(_OPT_LEVELS)} optimization level(s) each)"
    )
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_sanitizer_matrix: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
