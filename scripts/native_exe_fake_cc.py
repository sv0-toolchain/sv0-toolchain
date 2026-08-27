#!/usr/bin/env python3
"""Fake host C compiler/linker executable for native-executable driver tests (NEX-005).

Stands in for the real host `cc`/`clang`/`gcc` in TOOL/ART-class driver tests
(spec §26.3) so those tests never need a real toolchain to exercise
temp-output validation (ART-002…003), host-failure diagnostics (TOOL-009…010),
and capability probing (TOOL-005) — matching `native_exe_fake_emitter.py`'s
role for the core-compiler side of the pipeline (NEX-004).

As with the fake emitter, **build/link mode is never selected through argv**
(`SV0_FAKE_CC_MODE` env var instead) — argv here is exactly what a real driver
would pass a real compiler (Appendix B: `-std=gnu99 -O0 -g -I<runtime>
program.c sv0_runtime.c -o <tmp-exe>`), so this fake stays indistinguishable
from a real subprocess call to the code under test. The one exception is
`--version`, handled the same way real compilers handle it (a real driver
probe literally passes that flag) — recognized in argv regardless of
`SV0_FAKE_CC_MODE`.

Modes (spec §26.3):
  valid            find `-o <path>`, write a nonempty placeholder executable
                    there with the exec bit set, record argv/env, exit 0.
  fail             exit nonzero with stdout then stderr written in a fixed,
                    checkable order; no output file is created.
  zero-no-output   exit 0 but never create the `-o` file (TOOL-010: a
                    zero-exit compiler with no output is still a failure).
  empty-output     create the `-o` file but as an empty (0-byte) file, exit 0.
  dir-at-output    create a directory at the `-o` path instead of a file,
                    exit 0.
  hang             sleep until killed (cancellation tests, NEX-034).
  write-then-fail  write a nonempty output file, then exit nonzero (simulates
                    a linker crash after a partial write — proves the driver
                    validates before publishing rather than trusting exit 0).

Optional environment variables:
  SV0_FAKE_CC_RECORD    if set, write a JSON record of {argv, env, mode} here.
  SV0_FAKE_CC_VERSION    text `--version` responds with (default provided).

Run `python3 scripts/native_exe_fake_cc.py --selftest` to exercise every mode
as a real subprocess and check its observable behavior.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import time

_DEFAULT_VERSION = "fake-cc version 1.0.0 (test double, clang-compatible)"

_KNOWN_MODES = {
    "valid",
    "fail",
    "zero-no-output",
    "empty-output",
    "dir-at-output",
    "hang",
    "write-then-fail",
}


def _find_output_path(argv: list[str]) -> str | None:
    for i, arg in enumerate(argv):
        if arg == "-o" and i + 1 < len(argv):
            return argv[i + 1]
    return None


def _record(argv: list[str], mode: str) -> None:
    record_path = os.environ.get("SV0_FAKE_CC_RECORD")
    if not record_path:
        return
    payload = {
        "argv": argv,
        "mode": mode,
        "env": {
            k: v
            for k, v in os.environ.items()
            if k.startswith("SV0_FAKE_CC_") or k in ("PATH",)
        },
    }
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def _write_placeholder_executable(path: str) -> None:
    with open(path, "wb") as f:
        f.write(b"FAKE_EXECUTABLE\n")
    mode = os.stat(path).st_mode
    os.chmod(path, mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def run(argv: list[str], mode: str) -> int:
    _record(argv, mode)
    output_path = _find_output_path(argv)

    if mode == "valid":
        if output_path:
            _write_placeholder_executable(output_path)
        return 0

    if mode == "fail":
        sys.stdout.write("fake-cc: compiling...\n")
        sys.stderr.write("fake-cc: error: simulated compile failure, line 1\n")
        sys.stderr.write("fake-cc: error: simulated compile failure, line 2\n")
        return 1

    if mode == "zero-no-output":
        return 0

    if mode == "empty-output":
        if output_path:
            open(output_path, "wb").close()
        return 0

    if mode == "dir-at-output":
        if output_path:
            os.makedirs(output_path, exist_ok=True)
        return 0

    if mode == "hang":
        while True:
            time.sleep(3600)

    if mode == "write-then-fail":
        if output_path:
            _write_placeholder_executable(output_path)
        sys.stderr.write("fake-cc: error: simulated linker crash after partial write\n")
        return 1

    sys.stderr.write(f"native_exe_fake_cc: unknown mode {mode!r}\n")
    return 2


def _selftest() -> int:
    import subprocess
    import tempfile

    failures: list[str] = []
    this_file = os.path.abspath(__file__)

    def invoke(mode: str, argv_extra: list[str], extra_env: dict | None = None):
        env = dict(os.environ)
        env["SV0_FAKE_CC_MODE"] = mode
        if extra_env:
            env.update(extra_env)
        argv = [sys.executable, this_file] + argv_extra
        return subprocess.run(argv, capture_output=True, text=True, env=env)

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")

        r = invoke("valid", ["-std=gnu99", "-O0", "program.c", "-o", out])
        if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
            failures.append(f"valid: rc={r.returncode} exists={os.path.exists(out)}")
        elif not (os.stat(out).st_mode & stat.S_IXUSR):
            failures.append("valid: output is not executable")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")
        r = invoke("fail", ["program.c", "-o", out])
        if r.returncode == 0 or os.path.exists(out):
            failures.append(f"fail: rc={r.returncode} exists={os.path.exists(out)}")
        if "line 1" not in r.stderr or "line 2" not in r.stderr:
            failures.append(f"fail: stderr ordering lost: {r.stderr!r}")
        if r.stderr.index("line 1") > r.stderr.index("line 2"):
            failures.append("fail: stderr lines out of order")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")
        r = invoke("zero-no-output", ["program.c", "-o", out])
        if r.returncode != 0 or os.path.exists(out):
            failures.append(f"zero-no-output: rc={r.returncode} exists={os.path.exists(out)}")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")
        r = invoke("empty-output", ["program.c", "-o", out])
        if r.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) != 0:
            failures.append(f"empty-output: rc={r.returncode} size={os.path.getsize(out) if os.path.exists(out) else -1}")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")
        r = invoke("dir-at-output", ["program.c", "-o", out])
        if r.returncode != 0 or not os.path.isdir(out):
            failures.append(f"dir-at-output: rc={r.returncode} isdir={os.path.isdir(out)}")

    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")
        r = invoke("write-then-fail", ["program.c", "-o", out])
        if r.returncode == 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
            failures.append(f"write-then-fail: rc={r.returncode} exists={os.path.exists(out)}")

    r = invoke("bogus-mode", ["program.c", "-o", "/dev/null"])
    if r.returncode != 2:
        failures.append(f"unknown mode: expected exit 2, got {r.returncode}")

    # --version probe (TOOL-005) works independent of SV0_FAKE_CC_MODE.
    r = invoke("fail", ["--version"], extra_env={"SV0_FAKE_CC_VERSION": "fake-cc 9.9.9"})
    if r.returncode != 0 or "fake-cc 9.9.9" not in r.stdout:
        failures.append(f"--version: rc={r.returncode} stdout={r.stdout!r}")

    # argv recording, and metacharacter-laden arguments pass through as literal strings
    # (never shell-interpreted — this is a plain argv, no shell involved).
    with tempfile.TemporaryDirectory() as td:
        out = os.path.join(td, "program.tmp-exe")
        hostile = "a name; $(touch SHOULD_NOT_EXIST)"
        record_path = os.path.join(td, "record.json")
        r = invoke("valid", [hostile, "-o", out], extra_env={"SV0_FAKE_CC_RECORD": record_path})
        sentinel = os.path.join(os.path.dirname(this_file), "SHOULD_NOT_EXIST")
        if os.path.exists(sentinel):
            failures.append("hostile argv was shell-interpreted (sentinel created)")
            os.remove(sentinel)
        data = json.loads(open(record_path, encoding="utf-8").read())
        if hostile not in data.get("argv", []):
            failures.append(f"hostile argv not recorded literally: {data.get('argv')}")

    if failures:
        for f in failures:
            print(f"native_exe_fake_cc selftest FAIL: {f}")
        return 1

    print("native_exe_fake_cc: selftest OK (9 cases)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    if "--version" in argv:
        sys.stdout.write(os.environ.get("SV0_FAKE_CC_VERSION", _DEFAULT_VERSION) + "\n")
        return 0
    mode = os.environ.get("SV0_FAKE_CC_MODE", "valid")
    if mode not in _KNOWN_MODES:
        sys.stderr.write(f"native_exe_fake_cc: unknown SV0_FAKE_CC_MODE={mode!r}\n")
        return 2
    return run(argv, mode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
