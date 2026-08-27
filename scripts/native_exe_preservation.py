"""Prior-output preservation across every failure phase (NEX-032).

Implements ART-004/REL-002
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`, AC-014): a
failed rebuild must leave a pre-existing output byte-for-byte and
mode-for-mode unchanged, for *every* phase a build can fail in — not just
the one case `native_exe_publish.py` already mutation-tests at the unit
level (a bad temp artifact). This drives the real, assembled
`native_exe_build.build_native_executable` end to end through each
already-injectable failure seam:

  - **ENTRY** — a no-`main` fixture.
  - **FRONTEND** — `compiler_path` pointed at `native_exe_fake_emitter.py`
    in `diag` mode (nonzero exit).
  - **EMIT_C** — the same fake emitter in `empty` mode (zero exit, no C).
  - **HOST_COMPILE** — `explicit_cc` pointed at `native_exe_fake_cc.py` in
    `fail` mode.
  - **HOST_LINK** — the same fake cc in `zero-no-output` mode.
  - **RUNTIME** — `runtime_override` pointing at a corrupted runtime copy
    (mirrors `native_exe_runtime_manifest.py`'s own corruption fixture).

PUBLISH-phase preservation (a *validated* temp artifact whose final rename
itself fails) is already covered by `native_exe_publish.py`'s own
mutation-tested corpus and isn't re-derived here.

Run `python3 scripts/native_exe_preservation.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile

from native_exe_build import build_native_executable
from native_exe_errors import BuildError
from native_exe_runtime import RuntimeLocation, resolve_runtime_dir

_KNOWN_GOOD_BYTES = b"KNOWN_GOOD_EXECUTABLE\n"


def _seed_known_good(path: str) -> None:
    with open(path, "wb") as f:
        f.write(_KNOWN_GOOD_BYTES)
    os.chmod(path, 0o755)


def _make_cc_wrapper(td: str, fake_cc: str, mode: str) -> str:
    """A tiny wrapper baking SV0_FAKE_CC_MODE into the executable itself --
    NEX-024's sanitized_child_env correctly strips SV0_FAKE_CC_MODE before
    the real host-compiler invocation (it isn't allowlisted, by design), so
    an env var set by the test process never reaches the actual subprocess.
    Baking it into the wrapper script sidesteps that (deliberate) barrier.
    """
    wrapper = os.path.join(td, f"fake_cc_{mode.replace('-', '_')}.sh")
    with open(wrapper, "w", encoding="utf-8") as f:
        f.write(f"#!/bin/sh\nexport SV0_FAKE_CC_MODE={mode}\nexec python3 {fake_cc} \"$@\"\n")
    os.chmod(wrapper, os.stat(wrapper).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return wrapper


def _assert_unchanged(path: str, before_bytes: bytes, before_mode: int, label: str, failures: list[str]) -> None:
    if not os.path.isfile(path):
        failures.append(f"{label}: prior output disappeared")
        return
    after_bytes = open(path, "rb").read()
    after_mode = os.stat(path).st_mode
    if after_bytes != before_bytes:
        failures.append(f"{label}: prior output bytes changed")
    if after_mode != before_mode:
        failures.append(f"{label}: prior output mode changed")


def _selftest() -> int:
    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_emitter = os.path.join(this_dir, "native_exe_fake_emitter.py")
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")
    real_runtime = resolve_runtime_dir()

    ok_src = 'fn main() -> i32 {\n    return 0;\n}\n'

    # (label, src_content, kwargs_builder(td) -> dict)
    scenarios = [
        ("ENTRY", "pub fn add(a: i32, b: i32) -> i32 { return a + b; }\n", lambda td: {}),
        (
            "FRONTEND",
            ok_src,
            lambda td: {"compiler_path": fake_emitter, "env": ("SV0_FAKE_EMITTER_MODE", "diag")},
        ),
        (
            "EMIT_C",
            ok_src,
            lambda td: {"compiler_path": fake_emitter, "env": ("SV0_FAKE_EMITTER_MODE", "empty")},
        ),
        ("HOST_COMPILE", ok_src, lambda td: {"explicit_cc": _make_cc_wrapper(td, fake_cc, "fail")}),
        ("HOST_LINK", ok_src, lambda td: {"explicit_cc": _make_cc_wrapper(td, fake_cc, "zero-no-output")}),
    ]

    for label, src_content, kwargs_builder in scenarios:
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "case.sv0")
            with open(src, "w", encoding="utf-8") as f:
                f.write(src_content)
            out = os.path.join(td, "prior_output")
            _seed_known_good(out)
            before_bytes = open(out, "rb").read()
            before_mode = os.stat(out).st_mode

            kwargs = kwargs_builder(td)
            env_mode = kwargs.pop("env", None)
            env_backup = dict(os.environ)
            if env_mode:
                os.environ[env_mode[0]] = env_mode[1]
            try:
                try:
                    build_native_executable("file", src, out, td, probe=False, **kwargs)
                    failures.append(f"{label}: expected BuildError, build succeeded")
                except BuildError:
                    pass
            finally:
                os.environ.clear()
                os.environ.update(env_backup)

            _assert_unchanged(out, before_bytes, before_mode, label, failures)

    # RUNTIME phase: a corrupted runtime copy fails at manifest verification,
    # before the core compiler ever runs.
    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "case.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write(ok_src)
        out = os.path.join(td, "prior_output")
        _seed_known_good(out)
        before_bytes = open(out, "rb").read()
        before_mode = os.stat(out).st_mode

        corrupt_dir = os.path.join(td, "corrupt_runtime")
        os.makedirs(corrupt_dir)
        shutil.copy(real_runtime.header, os.path.join(corrupt_dir, "sv0_runtime.h"))
        shutil.copy(real_runtime.source, os.path.join(corrupt_dir, "sv0_runtime.c"))
        header_copy = os.path.join(corrupt_dir, "sv0_runtime.h")
        with open(header_copy, "r+b") as f:
            content = bytearray(f.read())
            content[0] ^= 0xFF
            f.seek(0)
            f.write(content)
        # No manifest in corrupt_dir at all -- verify_manifest fails closed on
        # a missing manifest just as surely as on a hash mismatch (NEX-020).
        corrupt_runtime = RuntimeLocation(
            dir=corrupt_dir,
            header=header_copy,
            source=os.path.join(corrupt_dir, "sv0_runtime.c"),
        )
        try:
            build_native_executable("file", src, out, td, probe=False, runtime_override=corrupt_runtime)
            failures.append("RUNTIME: expected BuildError, build succeeded")
        except BuildError:
            pass
        _assert_unchanged(out, before_bytes, before_mode, "RUNTIME", failures)

    # Self-check: _assert_unchanged itself must actually discriminate a real
    # corruption, not just always pass -- every scenario above is defended by
    # multiple already-mutation-tested layers (NEX-006/007/012/019/020/025),
    # so mutating any single one of them tends to get caught upstream before
    # reaching this test's own comparison; this proves the comparison itself
    # is not a no-op.
    probe_failures: list[str] = []
    fake_before = b"before"
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "probe")
        with open(p, "wb") as f:
            f.write(b"after-corrupted")
        _assert_unchanged(p, fake_before, os.stat(p).st_mode, "self-check", probe_failures)
    if not probe_failures:
        failures.append("_assert_unchanged failed to detect a genuine byte-content mismatch")

    if failures:
        for f in failures:
            print(f"native_exe_preservation selftest FAIL: {f}")
        return 1

    print(f"native_exe_preservation: selftest OK ({len(scenarios) + 1} phases, comparison self-check included)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_preservation: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
