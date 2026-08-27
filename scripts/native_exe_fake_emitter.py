#!/usr/bin/env python3
"""Fake core-compiler executable for native-executable driver tests (NEX-004).

Stands in for the real self-hosted `sv0c` core compiler in PIPE/SEC-class
driver tests (spec §26.2) so those tests never need a real compiler build to
exercise the C-stdout / diagnostic-stderr / exit-code protocol (PIPE-003…005)
or prove argv-safety (SEC-001, TOOL-003). Invoked exactly like the real core
compiler would be — argv is whatever the driver passes (e.g. a source path) —
so **mode selection never goes through argv**; it goes through the
`SV0_FAKE_EMITTER_MODE` environment variable, keeping this indistinguishable
from a real subprocess call from the driver's point of view.

Modes (spec §26.2):
  valid      emit a plausible C translation unit (with the runtime include
             marker) to stdout, exit 0.
  empty      emit nothing, exit 0 (PIPE-004: zero exit + empty C == emitter-
             protocol failure).
  partial    emit truncated C, then exit nonzero.
  warn       emit valid C on stdout AND a warning on stderr, exit 0 (PIPE-005:
             stdout/stderr must stay separate channels even when both are used).
  diag       emit nothing on stdout, a diagnostic on stderr, exit nonzero
             (PIPE-003: a frontend/semantic failure).
  hang       sleep until killed (for future cancellation tests, NEX-034).
  sentinel   attempt to create a side-effect sentinel file, then behave like
             `valid` — proves a driver path never blindly trusts/re-invokes.

Optional environment variables:
  SV0_FAKE_EMITTER_RECORD    if set, write a JSON record of {argv, env, mode}
                             to this path (NEX-004's red test: "driver test
                             records emitter argv").
  SV0_FAKE_EMITTER_SENTINEL  path the `sentinel` mode touches.

Run `python3 scripts/native_exe_fake_emitter.py --selftest` to exercise every
mode as a real subprocess and check its observable behavior.
"""

from __future__ import annotations

import json
import os
import sys
import time

RUNTIME_INCLUDE_MARKER = '#include "sv0_runtime.h"'

_VALID_C = (
    RUNTIME_INCLUDE_MARKER
    + "\n\nstatic int32_t sv0_user_main(void) {\n    return 0;\n}\n\n"
    "int main(int argc, char **argv) {\n"
    "  sv0_runtime_init(argc, argv);\n"
    "  return (int)sv0_user_main();\n"
    "}\n"
)

_PARTIAL_C = RUNTIME_INCLUDE_MARKER + "\n\nstatic int32_t sv0_user_m"  # truncated mid-token

_KNOWN_MODES = {"valid", "empty", "partial", "warn", "diag", "hang", "sentinel"}


def _record(mode: str) -> None:
    record_path = os.environ.get("SV0_FAKE_EMITTER_RECORD")
    if not record_path:
        return
    payload = {
        "argv": sys.argv[1:],
        "mode": mode,
        "env": {
            k: v
            for k, v in os.environ.items()
            if k.startswith("SV0_FAKE_EMITTER_") or k in ("PATH",)
        },
    }
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def run(mode: str) -> int:
    _record(mode)

    if mode == "valid":
        sys.stdout.write(_VALID_C)
        return 0

    if mode == "empty":
        return 0

    if mode == "partial":
        sys.stdout.write(_PARTIAL_C)
        return 1

    if mode == "warn":
        sys.stdout.write(_VALID_C)
        sys.stderr.write("warning: fake-emitter simulated diagnostic\n")
        return 0

    if mode == "diag":
        sys.stderr.write("error[E9999]: fake-emitter simulated frontend failure\n")
        return 1

    if mode == "hang":
        while True:
            time.sleep(3600)

    if mode == "sentinel":
        sentinel_path = os.environ.get("SV0_FAKE_EMITTER_SENTINEL")
        if sentinel_path:
            with open(sentinel_path, "w", encoding="utf-8") as f:
                f.write("fake-emitter side effect\n")
        sys.stdout.write(_VALID_C)
        return 0

    sys.stderr.write(f"native_exe_fake_emitter: unknown mode {mode!r}\n")
    return 2


def _selftest() -> int:
    import subprocess
    import tempfile

    failures: list[str] = []
    this_file = os.path.abspath(__file__)

    def invoke(mode: str, extra_env: dict | None = None, argv_extra: list[str] | None = None):
        env = dict(os.environ)
        env["SV0_FAKE_EMITTER_MODE"] = mode
        if extra_env:
            env.update(extra_env)
        argv = [sys.executable, this_file] + (argv_extra or ["some/fake/input.sv0"])
        return subprocess.run(argv, capture_output=True, text=True, env=env)

    r = invoke("valid")
    if r.returncode != 0 or RUNTIME_INCLUDE_MARKER not in r.stdout or r.stderr:
        failures.append(f"valid: rc={r.returncode} stdout_ok={RUNTIME_INCLUDE_MARKER in r.stdout} stderr={r.stderr!r}")

    r = invoke("empty")
    if r.returncode != 0 or r.stdout != "" or r.stderr != "":
        failures.append(f"empty: rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")

    r = invoke("partial")
    if r.returncode == 0 or r.stdout == "" or RUNTIME_INCLUDE_MARKER not in r.stdout:
        failures.append(f"partial: rc={r.returncode} stdout={r.stdout!r}")

    r = invoke("warn")
    if r.returncode != 0 or RUNTIME_INCLUDE_MARKER not in r.stdout or not r.stderr:
        failures.append(f"warn: rc={r.returncode} stdout_ok={RUNTIME_INCLUDE_MARKER in r.stdout} stderr={r.stderr!r}")

    r = invoke("diag")
    if r.returncode == 0 or r.stdout != "" or not r.stderr:
        failures.append(f"diag: rc={r.returncode} stdout={r.stdout!r} stderr={r.stderr!r}")

    r = invoke("bogus-mode")
    if r.returncode != 2:
        failures.append(f"unknown mode: expected exit 2, got {r.returncode}")

    # argv recording: NEX-004's actual red test.
    with tempfile.TemporaryDirectory() as td:
        record_path = os.path.join(td, "record.json")
        r = invoke("valid", extra_env={"SV0_FAKE_EMITTER_RECORD": record_path}, argv_extra=["/abs/hello.sv0"])
        if r.returncode != 0:
            failures.append(f"record run failed: rc={r.returncode} stderr={r.stderr!r}")
        elif not os.path.isfile(record_path):
            failures.append("expected a record file to be written, found none")
        else:
            data = json.loads(open(record_path, encoding="utf-8").read())
            if data.get("argv") != ["/abs/hello.sv0"]:
                failures.append(f"expected recorded argv ['/abs/hello.sv0'], got {data.get('argv')}")
            if data.get("mode") != "valid":
                failures.append(f"expected recorded mode 'valid', got {data.get('mode')}")

    # sentinel: only the sentinel mode ever touches the sentinel path.
    with tempfile.TemporaryDirectory() as td:
        sentinel_path = os.path.join(td, "SHOULD_NOT_EXIST")
        invoke("valid", extra_env={"SV0_FAKE_EMITTER_SENTINEL": sentinel_path})
        if os.path.exists(sentinel_path):
            failures.append("valid mode must never touch the sentinel path")
        invoke("sentinel", extra_env={"SV0_FAKE_EMITTER_SENTINEL": sentinel_path})
        if not os.path.exists(sentinel_path):
            failures.append("sentinel mode must touch the sentinel path")

    if failures:
        for f in failures:
            print(f"native_exe_fake_emitter selftest FAIL: {f}")
        return 1

    print("native_exe_fake_emitter: selftest OK (8 cases)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    mode = os.environ.get("SV0_FAKE_EMITTER_MODE", "valid")
    if mode not in _KNOWN_MODES:
        sys.stderr.write(f"native_exe_fake_emitter: unknown SV0_FAKE_EMITTER_MODE={mode!r}\n")
        return 2
    return run(mode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
