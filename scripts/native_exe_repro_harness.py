"""Pinned double-build reproducibility harness (NEX-053a, REPRO-004).

Implements §21.2/§21.3
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): builds the
same fixture twice with a pinned compiler/runtime/flags/environment
(everything `build_native_executable` already controls) and compares the
two published artifacts.

**Real, directly-observed finding, not assumed**: on this dev machine
(macOS/arm64, Apple's `ld64` linker), two builds of the IDENTICAL source
are never byte-identical, even with debug info disabled (`-g0`) and even
though the emitted C itself IS byte-identical between runs (confirmed
directly via `emit_c_only`, matching PIPE-012's determinism claim). The
actual cause, confirmed via `dwarfdump --uuid`: every Mach-O executable
gets a fresh, random `LC_UUID` load command from the linker on every
link, with no documented `ld64` flag to suppress it. This is *exactly*
the platform-specific nondeterminism §21.3 anticipates ("after
normalizing or suppressing nondeterministic timestamps, UUIDs, build
IDs... if a platform prevents byte identity, the build record SHALL
distinguish semantic reproducibility from byte reproducibility").

`check_reproducibility` therefore classifies its result as one of:
  - `"byte-identical"` -- the two artifacts hash-match exactly;
  - `"semantic-only"` -- the artifacts differ, but only in a region this
    module can attribute to a known, documented nondeterminism source
    (currently: the Mach-O `LC_UUID` load command on Darwin) -- confirmed
    by stripping/ignoring that source and re-comparing, not assumed;
  - `"divergent"` -- the artifacts differ for an UNKNOWN reason (a real
    reproducibility failure, not the known UUID source) -- this is the
    failure case a real regression would land in.

Run `python3 scripts/native_exe_repro_harness.py --selftest` for the
corpus.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import tempfile

from native_exe_build import build_native_executable


def _sha256_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def _macho_uuid(path: str) -> str | None:
    """The Mach-O LC_UUID for `path`, or None if `dwarfdump` isn't
    available or the platform isn't Darwin -- never raises.
    """
    if platform.system() != "Darwin":
        return None
    try:
        proc = subprocess.run(["dwarfdump", "--uuid", path], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    line = proc.stdout.strip()
    # Format: "UUID: <uuid> (arch) <path>"
    if line.startswith("UUID:"):
        return line.split()[1]
    return None


def build_twice_and_compare(source_content: str, extra_cc_args: list[str] | None = None) -> dict:
    """Build `source_content` twice, each in its own fresh scratch
    directory, and classify the comparison. Returns a dict with `status`
    ("byte-identical" | "semantic-only" | "divergent"), the two hashes,
    and (for Darwin) the two observed UUIDs.
    """
    hashes = []
    paths = []
    with tempfile.TemporaryDirectory() as td_a, tempfile.TemporaryDirectory() as td_b:
        for td in (td_a, td_b):
            src = os.path.join(td, "repro.sv0")
            with open(src, "w", encoding="utf-8") as f:
                f.write(source_content)
            out = os.path.join(td, "out")
            build_native_executable("file", src, out, td, probe=False, extra_cc_args=extra_cc_args)
            hashes.append(_sha256_file(out))
            paths.append(out)

        if hashes[0] == hashes[1]:
            return {"status": "byte-identical", "hashes": hashes}

        uuids = [_macho_uuid(p) for p in paths]
        if all(u is not None for u in uuids) and uuids[0] != uuids[1]:
            # The known source is present and actually differs -- confirm
            # every actually-differing byte is explained by it (directly,
            # not assumed): either inside the 16-byte LC_UUID load command
            # itself, or inside the trailing ad-hoc code-signature blob,
            # which macOS's linker computes OVER the whole file (including
            # the UUID bytes) and is therefore a DERIVED effect of the same
            # single root cause, not an independent second source.
            if _divergence_fully_explained_by_uuid(paths[0], paths[1], uuids[0], uuids[1]):
                return {"status": "semantic-only", "hashes": hashes, "uuids": uuids, "reason": "LC_UUID"}

        return {"status": "divergent", "hashes": hashes}


# Generous but bounded: real ad-hoc code-signature superblobs for a small
# executable like these fixtures are a few hundred bytes; this window is
# checked, not assumed -- any difference outside BOTH this window and the
# UUID's own 16 bytes fails the classification below.
_TRAILING_SIGNATURE_WINDOW = 1024


def _divergence_fully_explained_by_uuid(path_a: str, path_b: str, uuid_a: str, uuid_b: str) -> bool:
    data_a = open(path_a, "rb").read()
    data_b = open(path_b, "rb").read()
    if len(data_a) != len(data_b):
        return False

    try:
        raw_a = bytes.fromhex(uuid_a.replace("-", ""))
    except ValueError:
        return False
    uuid_offset = data_a.find(raw_a)
    if uuid_offset == -1:
        return False
    uuid_range = range(uuid_offset, uuid_offset + 16)
    trailing_start = len(data_a) - _TRAILING_SIGNATURE_WINDOW

    for i, (byte_a, byte_b) in enumerate(zip(data_a, data_b)):
        if byte_a == byte_b:
            continue
        if i in uuid_range:
            continue
        if i >= trailing_start:
            continue
        # A differing byte outside both allowed regions -- a real,
        # unexplained divergence.
        return False
    return True


def _selftest() -> int:
    failures: list[str] = []

    src = 'fn main() -> i32 {\n    println("repro check");\n    return 42;\n}\n'
    # -g0: isolates the LC_UUID source in isolation. WITH debug info (the
    # default dev/release profile), Darwin's `-g` ALSO embeds the absolute
    # scratch path into debug strings -- a SECOND, independent
    # nondeterminism source stacked on top of LC_UUID, confirmed directly
    # (the unmasked-UUID comparison alone does not explain a with-debug-info
    # divergence). That second source needs its own fix (prefix-mapping
    # scratch paths, e.g. `-ffile-prefix-map`) which is out of this
    # harness's scope -- documented as a known gap in the checklist rather
    # than silently worked around here.
    result = build_twice_and_compare(src, extra_cc_args=["-g0"])

    if platform.system() == "Darwin":
        # The documented, directly-observed platform behavior: Darwin
        # is semantic-only due to LC_UUID, never byte-identical, and
        # never an unattributed "divergent" (which would mean a REAL,
        # unexplained reproducibility regression).
        if result["status"] == "divergent":
            failures.append(f"unattributed divergence on Darwin: {result}")
        elif result["status"] == "byte-identical":
            failures.append(
                "unexpectedly byte-identical on Darwin -- either the LC_UUID "
                "behavior changed, or this result is suspicious and needs re-checking"
            )
        elif result["status"] != "semantic-only":
            failures.append(f"unexpected status on Darwin: {result['status']}")
    else:
        # On non-Darwin platforms this module has no documented
        # explanation for a divergence -- require true byte-identity
        # (a real regression should fail loudly here, not be
        # silently written off as "semantic-only").
        if result["status"] != "byte-identical":
            failures.append(f"expected byte-identical on non-Darwin, got: {result}")

    # A genuinely different source MUST NOT be classified as reproducible
    # against a different source (sanity check on the harness itself --
    # this isn't comparing two arbitrary artifacts, it's the SAME source
    # built twice).
    src2 = 'fn main() -> i32 {\n    println("different");\n    return 7;\n}\n'
    with tempfile.TemporaryDirectory() as td:
        srcfile = os.path.join(td, "a.sv0")
        with open(srcfile, "w", encoding="utf-8") as f:
            f.write(src)
        out_a = os.path.join(td, "out_a")
        build_native_executable("file", srcfile, out_a, td, probe=False)

        srcfile2 = os.path.join(td, "b.sv0")
        with open(srcfile2, "w", encoding="utf-8") as f:
            f.write(src2)
        out_b = os.path.join(td, "out_b")
        build_native_executable("file", srcfile2, out_b, td, probe=False)

        if _sha256_file(out_a) == _sha256_file(out_b):
            failures.append("sanity check failed: two DIFFERENT sources hashed identically")

        # Direct unit test of the classifier itself: two artifacts built
        # from genuinely DIFFERENT source content have real content
        # divergence far outside any UUID/signature window -- the
        # classifier must say so (False), not wave it through as
        # "explained by the known UUID source" just because a UUID also
        # happens to differ between them.
        if platform.system() == "Darwin":
            uuid_a = _macho_uuid(out_a)
            uuid_b = _macho_uuid(out_b)
            if uuid_a and uuid_b and uuid_a != uuid_b:
                if _divergence_fully_explained_by_uuid(out_a, out_b, uuid_a, uuid_b):
                    failures.append(
                        "classifier incorrectly explained a real content divergence "
                        "(two different programs) as UUID-only"
                    )

    if failures:
        for f in failures:
            print(f"native_exe_repro_harness selftest FAIL: {f}")
        return 1

    print(f"native_exe_repro_harness: selftest OK (status={result['status']!r})")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_repro_harness: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
