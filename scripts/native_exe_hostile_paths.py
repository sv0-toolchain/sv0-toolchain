"""Hostile paths through the full pipeline (NEX-036).

Implements PORT-004/SEC-001
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`, AC-015):
`native_exe_cli.py` (NEX-002/010) and `native_exe_subprocess.py` (NEX-009)
already prove hostile paths never get shell-interpreted at the argv-parsing
and subprocess-wrapper layers. This drives the same class of hostile names
(spaces, Unicode, a leading hyphen, shell metacharacters) through the real,
assembled `build_native_executable` end to end — a source path AND an
output path, together — confirming either a clean success or a clean path
error, never a shell-interpreted side effect, at every layer in between
(core-compiler invocation, host-compiler invocation, publication).

Run `python3 scripts/native_exe_hostile_paths.py --selftest` for the
corpus.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from native_exe_build import build_native_executable

_HOSTILE_STEMS = [
    "has spaces",
    "unicode_héllo_λ",
    "-leading-hyphen",
    "semi;colon",
    "dollar$paren(sub)",
    "backtick`quote",
]


def _selftest() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as td:
        # The sentinel name is bare (no embedded path separators) -- it must
        # remain exactly one filename *component*, living directly in `td`,
        # for the "did a shell run `touch SENTINEL_NAME`" check to be
        # meaningful. Embedding a full path with slashes here would make
        # os.path.dirname() of the hostile output resolve to a nonexistent
        # directory, which native_exe_output_path correctly rejects before
        # ever reaching a subprocess call — a real bug in an earlier version
        # of this test: it silently never exercised the property it claimed
        # to, because every build failed early on that unrelated ground.
        sentinel_name = "SHOULD_NOT_EXIST"
        sentinel_path = os.path.join(td, sentinel_name)

        for stem in _HOSTILE_STEMS:
            src = os.path.join(td, f"{stem}.sv0")
            out = os.path.join(td, f"{stem}_out; touch {sentinel_name}")
            with open(src, "w", encoding="utf-8") as f:
                f.write("fn main() -> i32 {\n    return 17;\n}\n")

            try:
                result = build_native_executable("file", src, out, td, probe=False)
                if not os.path.isfile(result.output_path):
                    failures.append(f"{stem!r}: build reported success but output is missing")
                else:
                    proc = subprocess.run([result.output_path], capture_output=True)
                    if proc.returncode != 17:
                        failures.append(f"{stem!r}: expected exit 17, got {proc.returncode}")
            except Exception as exc:  # noqa: BLE001 - a clean path error is acceptable; a crash is not
                # Any exception must be one of our own typed errors, not a raw
                # crash from a hostile path breaking some internal assumption.
                from native_exe_errors import BuildError

                if not isinstance(exc, BuildError):
                    failures.append(f"{stem!r}: raised a non-BuildError exception: {exc!r}")

            if os.path.exists(sentinel_path):
                failures.append(f"{stem!r}: shell metacharacters in the output path were interpreted")
                os.remove(sentinel_path)

    if failures:
        for f in failures:
            print(f"native_exe_hostile_paths selftest FAIL: {f}")
        return 1

    print(f"native_exe_hostile_paths: selftest OK ({len(_HOSTILE_STEMS)} hostile path shapes)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_hostile_paths: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
