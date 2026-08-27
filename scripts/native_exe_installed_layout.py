"""Installed-layout E2E outside a source checkout (NEX-046).

Implements AC-023
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): the driver
must work when it's *installed* -- runtime bundle and core compiler binary
copied somewhere with no `sv0c` source tree alongside them at all -- not
just when run from inside this repo's own checkout. This is the sharpest
test of "does the driver actually resolve paths relative to itself /
via explicit overrides, rather than accidentally depending on something
only a source checkout provides" (a stray relative path, an assumption
about a sibling directory, an implicit `cwd`-relative lookup).

Reuses `build_native_executable`'s existing `runtime_override` (NEX-032)
and `compiler_path` (NEX-033) test seams -- no new seams needed, since
those were built exactly to let a test point the pipeline at an arbitrary
runtime/compiler location.

Run `python3 scripts/native_exe_installed_layout.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile

from native_exe_build import DEFAULT_COMPILER_PATH, build_native_executable
from native_exe_runtime import RuntimeLocation
from native_exe_runtime_bundle import verify_bundle_contents
from native_exe_runtime_manifest import verify_manifest


def _copy_installed_layout(dest_dir: str) -> tuple[str, str]:
    """Copy the real runtime bundle + core compiler binary into `dest_dir`
    (which the caller has made to contain no `sv0c` source tree). Returns
    (runtime_dir, compiler_path) inside the copy.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))
    real_runtime_dir = os.path.normpath(os.path.join(this_dir, "..", "sv0c", "runtime"))

    installed_runtime_dir = os.path.join(dest_dir, "runtime")
    shutil.copytree(real_runtime_dir, installed_runtime_dir)

    installed_compiler_path = os.path.join(dest_dir, "sv0-megatu-native")
    shutil.copy2(DEFAULT_COMPILER_PATH, installed_compiler_path)
    os.chmod(installed_compiler_path, 0o755)

    return installed_runtime_dir, installed_compiler_path


def _selftest() -> int:
    failures: list[str] = []

    if not os.path.isfile(DEFAULT_COMPILER_PATH):
        print(f"native_exe_installed_layout selftest SKIP: {DEFAULT_COMPILER_PATH} not built")
        return 0

    # A fresh temp dir with a SPACE in its path, containing no sv0c source
    # tree alongside the copied layout at all (AC-023's literal point).
    with tempfile.TemporaryDirectory(prefix="installed layout ") as td:
        installed_runtime_dir, installed_compiler_path = _copy_installed_layout(td)

        # Case 1: the copied bundle verifies clean on its own (NEX-045).
        try:
            verify_bundle_contents(installed_runtime_dir)
        except Exception as exc:  # noqa: BLE001 - report any failure as a selftest failure
            failures.append(f"case1: copied bundle failed verify_bundle_contents: {exc}")

        # Case 2: the runtime manifest verifies against the copied bundle
        # (NEX-020), using the same RuntimeLocation shape resolve_runtime_dir
        # would produce, but pointed at the installed copy.
        runtime_location = RuntimeLocation(
            dir=installed_runtime_dir,
            header=os.path.join(installed_runtime_dir, "sv0_runtime.h"),
            source=os.path.join(installed_runtime_dir, "sv0_runtime.c"),
        )
        try:
            verify_manifest(runtime_location)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"case2: copied runtime failed verify_manifest: {exc}")

        # Case 3: a real build, driven entirely off the installed copy via
        # runtime_override + compiler_path -- no sv0c source tree is ever
        # touched or assumed to exist.
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("installed layout works");\n    return 9;\n}\n')
        out = os.path.join(td, "hello_out")

        try:
            result = build_native_executable(
                "file",
                src,
                out,
                td,
                probe=False,
                runtime_override=runtime_location,
                compiler_path=installed_compiler_path,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"case3: build from installed layout raised: {exc}")
            result = None

        if result is not None:
            if not os.path.isfile(result.output_path):
                failures.append("case3: installed-layout build produced no output file")
            else:
                proc = subprocess.run([result.output_path], capture_output=True, text=True)
                if proc.returncode != 9 or "installed layout works" not in proc.stdout:
                    failures.append(
                        f"case3: installed-layout binary misbehaved: rc={proc.returncode} stdout={proc.stdout!r}"
                    )

        # Case 4: confirm the whole test genuinely had no sv0c tree beside it --
        # a sanity check on the test's own setup, not the pipeline.
        if os.path.isdir(os.path.join(td, "sv0c")):
            failures.append("case4: test setup itself is broken -- an sv0c tree exists beside the installed copy")

    if failures:
        for f in failures:
            print(f"native_exe_installed_layout selftest FAIL: {f}")
        return 1

    print("native_exe_installed_layout: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_installed_layout: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
