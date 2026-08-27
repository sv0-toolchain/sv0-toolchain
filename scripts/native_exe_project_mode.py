"""Project-mode executable build via compiler-owned composition (NEX-030).

Implements CLI-009/PIPE-007
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §13.3, AC-006):
`build_native_executable("project", ...)` already handles this — it passes
`--project <dir>` straight through `CoreCompilerRequest.project` to the core
compiler's own recursive project composition (module/`use` resolution,
deterministic file ordering, duplicate-definition diagnostics), exactly as
`scripts/sv0`'s own `run_compile` does today. The driver never concatenates
sources, infers module names, or selects an entry file itself (§13.3) — this
slice proves that composition against a real, already-existing multi-file
fixture, `sv0c/test/integration/modules/` (`main.sv0` importing
`lib::bump` from `lib/lib.sv0`), rather than inventing a new one.

Run `python3 scripts/native_exe_project_mode.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from native_exe_build import build_native_executable


def _selftest() -> int:
    failures: list[str] = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_dir = os.path.join(root, "sv0c", "test", "integration", "modules")

    if not os.path.isdir(project_dir):
        failures.append(f"fixture project missing: {project_dir}")
    else:
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "modules_out")
            result = build_native_executable("project", project_dir, out, td, probe=False)
            if result.output_path != out or not os.path.isfile(out):
                failures.append(f"unexpected build result: {result}")
            else:
                proc = subprocess.run([out], capture_output=True)
                # main.sv0 returns lib::bump(41) == 42 (AC-006).
                if proc.returncode != 42:
                    failures.append(f"expected exit 42 (bump(41)), got {proc.returncode}")

    if failures:
        for f in failures:
            print(f"native_exe_project_mode selftest FAIL: {f}")
        return 1

    print("native_exe_project_mode: selftest OK (1 case)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_project_mode: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
