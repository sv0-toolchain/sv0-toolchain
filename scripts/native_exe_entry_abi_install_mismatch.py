"""Installed-layout entry-ABI mismatch fails closed (NEX-054b, ENTRY-010).

Implements ENTRY-010's install-mismatch half
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): an
installed runtime bundle (copied outside a source checkout, reusing
`native_exe_installed_layout._copy_installed_layout`, NEX-046) whose
`entry-abi-manifest.json` declares an `entry_abi_version` this compiled
driver doesn't support fails the build closed, with a clear diagnostic --
mirroring `native_exe_runtime_manifest.verify_manifest`'s existing
ABI-mismatch behavior for the runtime bundle itself
(`native_exe_entry_abi.verify_entry_abi_compat`, wired into
`build_native_executable`'s pipeline for NEX-054b).

Run `python3 scripts/native_exe_entry_abi_install_mismatch.py --selftest`
for the corpus.
"""

from __future__ import annotations

import json
import os
import tempfile

from native_exe_build import DEFAULT_COMPILER_PATH, build_native_executable
from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_installed_layout import _copy_installed_layout
from native_exe_runtime import RuntimeLocation


def _selftest() -> int:
    failures: list[str] = []

    if not os.path.isfile(DEFAULT_COMPILER_PATH):
        print(f"native_exe_entry_abi_install_mismatch selftest SKIP: {DEFAULT_COMPILER_PATH} not built")
        return 0

    with tempfile.TemporaryDirectory(prefix="entry abi mismatch ") as td:
        installed_runtime_dir, installed_compiler_path = _copy_installed_layout(td)

        # Corrupt the COPIED entry-abi-manifest.json's version -- never
        # touches the real sv0c/runtime/ source.
        manifest_path = os.path.join(installed_runtime_dir, "entry-abi-manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
        data["entry_abi_version"] = 999
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        runtime_location = RuntimeLocation(
            dir=installed_runtime_dir,
            header=os.path.join(installed_runtime_dir, "sv0_runtime.h"),
            source=os.path.join(installed_runtime_dir, "sv0_runtime.c"),
        )

        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write("fn main() -> i32 {\n    return 0;\n}\n")
        out = os.path.join(td, "hello_out")

        try:
            build_native_executable(
                "file",
                src,
                out,
                td,
                probe=False,
                runtime_override=runtime_location,
                compiler_path=installed_compiler_path,
            )
            failures.append("expected BuildError for an unsupported installed entry_abi_version, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.RUNTIME:
                failures.append(f"expected RUNTIME phase, got {exc.phase}")
            if "999" not in exc.message:
                failures.append(f"error didn't clearly name the unsupported version: {exc.message!r}")

        if os.path.exists(out):
            failures.append("no output should have been created for a rejected entry-ABI mismatch")

    if failures:
        for f in failures:
            print(f"native_exe_entry_abi_install_mismatch selftest FAIL: {f}")
        return 1

    print("native_exe_entry_abi_install_mismatch: selftest OK (1 case)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_entry_abi_install_mismatch: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
