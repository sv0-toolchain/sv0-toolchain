"""Host C compiler capability probe (NEX-022).

Implements TOOL-005
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §16.3): before
its first use, the driver probes a selected compiler to confirm it can
actually run, capture its family/version text, and — the part a bare
`--version` check misses — that it can compile, link, *and run* a minimal
hosted C program on this host. A compiler that answers `--version` but can't
actually produce a working binary (missing SDK headers, wrong architecture,
a broken toolchain install) is exactly the case a version check alone would
miss.

Run `python3 scripts/native_exe_cc_probe.py --selftest` for the corpus.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass

from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_subprocess import SubprocessError, run_argv

_PROBE_C_SOURCE = "int main(void) { return 0; }\n"


@dataclass
class CompilerInfo:
    path: str
    family: str  # "clang" | "gcc" | "unknown"
    version_text: str


def _classify_family(version_text: str) -> str:
    lower = version_text.lower()
    if "clang" in lower:
        return "clang"
    if "gcc" in lower or "free software foundation" in lower:
        return "gcc"
    return "unknown"


def probe_compiler(cc_path: str) -> CompilerInfo:
    """Confirm `cc_path` runs, capture its identity, and confirm it can
    compile + link + run a minimal hosted C program. Raises
    BuildError(TOOL_DISCOVERY) on any failure along the way.
    """
    try:
        version_result = run_argv([cc_path, "--version"])
    except SubprocessError as exc:
        raise BuildError(DiagnosticPhase.TOOL_DISCOVERY, f"failed to run {cc_path} --version: {exc}") from exc
    if version_result.returncode != 0:
        raise BuildError(
            DiagnosticPhase.TOOL_DISCOVERY,
            f"{cc_path} --version exited {version_result.returncode}",
        )
    combined = (version_result.stdout or version_result.stderr or "").strip()
    version_text = combined.splitlines()[0] if combined else ""
    # Classify from the FULL --version output, not just the first line kept
    # for display: Debian/Ubuntu's gcc packaging renames the binary and its
    # own first line to "cc (Ubuntu 11.4.0-...) 11.4.0" -- no "gcc" and no
    # "Free Software Foundation" substring at all until line 2's copyright
    # notice, which the single-line version_text above deliberately doesn't
    # keep. Confirmed on a real Ubuntu 22.04 CI run (this project's own
    # suite had never once reached this far in CI before KC-001/002/005
    # were fixed, so this packaging quirk was never seen until now).
    family = _classify_family(combined)

    with tempfile.TemporaryDirectory() as td:
        c_path = os.path.join(td, "probe.c")
        out_path = os.path.join(td, "probe.out")
        with open(c_path, "w", encoding="utf-8") as f:
            f.write(_PROBE_C_SOURCE)

        try:
            compile_result = run_argv([cc_path, c_path, "-o", out_path])
        except SubprocessError as exc:
            raise BuildError(DiagnosticPhase.TOOL_DISCOVERY, f"probe compile/link failed: {exc}") from exc
        if compile_result.returncode != 0:
            raise BuildError(
                DiagnosticPhase.TOOL_DISCOVERY,
                f"probe compile/link failed (exit {compile_result.returncode}): {compile_result.stderr}",
            )

        try:
            run_result = run_argv([out_path])
        except (SubprocessError, OSError) as exc:
            # A compiler that "succeeds" but produces something unrunnable
            # (wrong architecture, not actually an executable) fails here.
            raise BuildError(DiagnosticPhase.TOOL_DISCOVERY, f"probe executable failed to run: {exc}") from exc
        if run_result.returncode != 0:
            raise BuildError(
                DiagnosticPhase.TOOL_DISCOVERY,
                f"probe executable exited {run_result.returncode}, expected 0",
            )

    return CompilerInfo(path=cc_path, family=family, version_text=version_text)


def probe_compiler_cached(cc_path: str, cache: dict[str, CompilerInfo] | None = None) -> CompilerInfo:
    """Like `probe_compiler`, but reuses a prior result for the same resolved
    tool identity instead of re-invoking `--version`/the compile-probe every
    time (NEX-044, TOOL-006's "record compiler identity" + PERF-007's "no
    more than one probe per unique tool identity per invocation" spirit).

    `cache` is caller-owned and in-process only -- a fresh dict per driver
    invocation is the intended lifetime; a persistent cross-invocation
    on-disk cache is explicitly deferred to R1 (PERF-007's fuller form).
    Keyed by `os.path.realpath(cc_path)` so two different argv spellings of
    the same tool (a relative path vs. its absolute form, or a symlink vs.
    its target) still share one cached probe.
    """
    if cache is None:
        cache = {}
    key = os.path.realpath(cc_path)
    if key in cache:
        return cache[key]
    info = probe_compiler(cc_path)
    cache[key] = info
    return info


def _selftest() -> int:
    import shutil
    import stat
    import sys

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_cc = os.path.join(this_dir, "native_exe_fake_cc.py")

    # Case 1: a real host `cc` passes the full probe end-to-end.
    real_cc = shutil.which("cc")
    if real_cc is None:
        failures.append("no real `cc` on PATH to probe (unexpected for this dev environment)")
    else:
        try:
            info = probe_compiler(real_cc)
            if not info.version_text:
                failures.append("real cc: expected non-empty version_text")
            if info.family == "unknown":
                failures.append(f"real cc: expected clang/gcc, got unknown ({info.version_text!r})")
        except BuildError as exc:
            failures.append(f"real cc: unexpected BuildError: {exc}")

    with tempfile.TemporaryDirectory() as td:
        # Case 2: a tool that fails --version is rejected before ever compiling.
        bad_version = os.path.join(td, "bad-version-cc")
        with open(bad_version, "w", encoding="utf-8") as f:
            f.write("#!/bin/sh\nexit 1\n")
        os.chmod(bad_version, os.stat(bad_version).st_mode | stat.S_IXUSR)
        try:
            probe_compiler(bad_version)
            failures.append("bad --version: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.TOOL_DISCOVERY:
                failures.append(f"bad --version: expected TOOL_DISCOVERY, got {exc.phase}")

        # Case 3: --version works but compile/link fails (fake_cc "fail" mode).
        env_backup = dict(os.environ)
        os.environ["SV0_FAKE_CC_MODE"] = "fail"
        try:
            probe_compiler(fake_cc)
            failures.append("compile failure: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.TOOL_DISCOVERY:
                failures.append(f"compile failure: expected TOOL_DISCOVERY, got {exc.phase}")
            if "probe compile/link failed" not in exc.message:
                failures.append(f"compile failure: unexpected message: {exc.message!r}")
        finally:
            os.environ.clear()
            os.environ.update(env_backup)

        # Case 4: a missing executable is a clean error, not a crash.
        try:
            probe_compiler(os.path.join(td, "does-not-exist"))
            failures.append("missing tool: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.TOOL_DISCOVERY:
                failures.append(f"missing tool: expected TOOL_DISCOVERY, got {exc.phase}")

        # Case 5 (NEX-044): probe_compiler_cached invokes the real subprocess
        # probe exactly once for repeated calls against the same tool
        # identity, proven via a wrapper around the REAL host `cc` that
        # counts its own invocations (a counter file it appends to on every
        # call) -- the wrapper has to delegate to a real compiler, not
        # `native_exe_fake_cc.py`'s "valid" mode, since `probe_compiler`
        # actually *runs* the produced binary and a fake placeholder file
        # isn't a real executable on this host.
        if real_cc is None:
            failures.append("case5: no real `cc` on PATH to wrap for the caching test")
            counting_wrapper = None
        else:
            counter_path = os.path.join(td, "probe_calls.txt")
            counting_wrapper = os.path.join(td, "counting_cc.sh")
            with open(counting_wrapper, "w", encoding="utf-8") as f:
                f.write(f'#!/bin/sh\necho x >> "{counter_path}"\nexec "{real_cc}" "$@"\n')
            os.chmod(
                counting_wrapper, os.stat(counting_wrapper).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
            )

        if counting_wrapper is not None:
            cache: dict = {}
            info1 = probe_compiler_cached(counting_wrapper, cache)
            info2 = probe_compiler_cached(counting_wrapper, cache)
            calls_after_two = sum(1 for _ in open(counter_path)) if os.path.exists(counter_path) else 0
            # Each real probe invokes the tool twice (--version, then compile) --
            # so two CACHED calls should still show only ONE probe's worth of
            # underlying invocations, not two.
            if calls_after_two != 2:
                failures.append(
                    f"case5: expected exactly 2 underlying invocations (one cached probe), got {calls_after_two}"
                )
            if info1 is not info2:
                failures.append("case5: expected the identical cached CompilerInfo object on the second call")

            # A THIRD, uncached call (fresh cache dict) must re-probe -- proves
            # the cache is doing real work, not just always returning early.
            info3 = probe_compiler_cached(counting_wrapper, {})
            calls_after_three = sum(1 for _ in open(counter_path))
            if calls_after_three != 4:
                failures.append(
                    f"case5: expected 4 underlying invocations after a fresh-cache re-probe, got {calls_after_three}"
                )
            if info3 == info1 and info3 is info1:
                failures.append("case5: fresh-cache probe unexpectedly reused the old cache entry")

    if failures:
        for f in failures:
            print(f"native_exe_cc_probe selftest FAIL: {f}")
        return 1

    print("native_exe_cc_probe: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_cc_probe: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
