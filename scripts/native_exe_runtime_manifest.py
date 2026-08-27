#!/usr/bin/env python3
"""Runtime ABI manifest + hash verification (NEX-020).

Implements RT-004…005
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §15.1/§15.2,
OD-004: schema/ABI version 1, exact SHA-256 file hashes): before the host
compiler runs, the driver verifies the runtime manifest is readable,
schema-compatible, and that the declared header/source hashes match the
actual files. A mismatch is a toolchain-integrity failure — fail closed, no
search for a "seemingly compatible" runtime elsewhere (§15.2).

The manifest, `sv0c/runtime/runtime-manifest.json`, is sv0c-owned data (the
spec's own ownership table: "runtime ABI versioning: sv0c") but is plain
JSON metadata, not compiler logic. Regenerate it with
`python3 scripts/native_exe_runtime_manifest.py --write` after an
intentional edit to `sv0_runtime.h`/`sv0_runtime.c` — `test-guards` running
`verify_manifest` against the live files is what makes an *unintentional*
runtime edit fail loudly instead of silently drifting from its manifest.

Run `python3 scripts/native_exe_runtime_manifest.py --selftest` for the
verification corpus (separate from `--write`, which is a real, invoked-by-
hand maintenance action, not something a selftest should trigger).
"""

from __future__ import annotations

import hashlib
import json
import os

from native_exe_errors import BuildError, DiagnosticPhase
from native_exe_runtime import RuntimeLocation, resolve_runtime_dir

SCHEMA_VERSION = 1
ABI_VERSION = 1
MANIFEST_FILENAME = "runtime-manifest.json"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_path_for(runtime: RuntimeLocation) -> str:
    return os.path.join(runtime.dir, MANIFEST_FILENAME)


def load_manifest(runtime: RuntimeLocation) -> dict:
    path = manifest_path_for(runtime)
    if not os.path.isfile(path):
        raise BuildError(DiagnosticPhase.RUNTIME, f"runtime manifest not found: {path}")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildError(DiagnosticPhase.RUNTIME, f"runtime manifest unreadable: {path} ({exc})") from exc

    for key in ("schema_version", "abi_version", "header_sha256", "source_sha256"):
        if key not in data:
            raise BuildError(DiagnosticPhase.RUNTIME, f"runtime manifest missing required key {key!r}: {path}")
    return data


def verify_manifest(runtime: RuntimeLocation) -> None:
    """Raise BuildError(RUNTIME) unless the manifest is schema-compatible and
    its declared hashes match the actual header/source files.
    """
    data = load_manifest(runtime)

    if data["schema_version"] != SCHEMA_VERSION:
        raise BuildError(
            DiagnosticPhase.RUNTIME,
            f"runtime manifest schema_version {data['schema_version']!r} is not "
            f"supported (expected {SCHEMA_VERSION})",
        )
    if data["abi_version"] != ABI_VERSION:
        raise BuildError(
            DiagnosticPhase.RUNTIME,
            f"runtime manifest abi_version {data['abi_version']!r} is not "
            f"supported by this compiler (expected {ABI_VERSION})",
        )

    actual_header = _sha256_file(runtime.header)
    actual_source = _sha256_file(runtime.source)
    if data["header_sha256"] != actual_header:
        raise BuildError(
            DiagnosticPhase.RUNTIME,
            f"runtime header hash mismatch: manifest declares {data['header_sha256']}, "
            f"actual is {actual_header} ({runtime.header})",
        )
    if data["source_sha256"] != actual_source:
        raise BuildError(
            DiagnosticPhase.RUNTIME,
            f"runtime source hash mismatch: manifest declares {data['source_sha256']}, "
            f"actual is {actual_source} ({runtime.source})",
        )


def write_manifest(runtime: RuntimeLocation) -> str:
    """Regenerate the manifest from the live runtime files. Returns the path written."""
    data = {
        "schema_version": SCHEMA_VERSION,
        "abi_version": ABI_VERSION,
        "header_sha256": _sha256_file(runtime.header),
        "source_sha256": _sha256_file(runtime.source),
    }
    path = manifest_path_for(runtime)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    return path


def _selftest() -> int:
    import shutil
    import tempfile

    failures: list[str] = []

    # Case 1: the real, checked-in manifest verifies clean against the real files.
    real_runtime = resolve_runtime_dir()
    try:
        verify_manifest(real_runtime)
    except BuildError as exc:
        failures.append(f"real manifest failed to verify: {exc}")

    # Case 2: a corrupted copy of the header (one byte flipped) fails verification
    # against the real manifest's declared hash.
    with tempfile.TemporaryDirectory() as td:
        fake_dir = os.path.join(td, "runtime")
        os.makedirs(fake_dir)
        shutil.copy(real_runtime.header, os.path.join(fake_dir, "sv0_runtime.h"))
        shutil.copy(real_runtime.source, os.path.join(fake_dir, "sv0_runtime.c"))
        shutil.copy(manifest_path_for(real_runtime), os.path.join(fake_dir, MANIFEST_FILENAME))

        # Flip one byte in the copied header.
        header_copy = os.path.join(fake_dir, "sv0_runtime.h")
        with open(header_copy, "r+b") as f:
            content = bytearray(f.read())
            content[0] = content[0] ^ 0xFF
            f.seek(0)
            f.write(content)

        fake_runtime = RuntimeLocation(
            dir=fake_dir,
            header=header_copy,
            source=os.path.join(fake_dir, "sv0_runtime.c"),
        )
        try:
            verify_manifest(fake_runtime)
            failures.append("corrupted header: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.RUNTIME:
                failures.append(f"corrupted header: expected RUNTIME phase, got {exc.phase}")
            if "header hash mismatch" not in exc.message:
                failures.append(f"corrupted header: unexpected message: {exc.message!r}")

    # Case 3: a missing manifest file is a clean RUNTIME failure, not a crash.
    with tempfile.TemporaryDirectory() as td:
        fake_dir = os.path.join(td, "runtime")
        os.makedirs(fake_dir)
        shutil.copy(real_runtime.header, os.path.join(fake_dir, "sv0_runtime.h"))
        shutil.copy(real_runtime.source, os.path.join(fake_dir, "sv0_runtime.c"))
        fake_runtime = RuntimeLocation(
            dir=fake_dir,
            header=os.path.join(fake_dir, "sv0_runtime.h"),
            source=os.path.join(fake_dir, "sv0_runtime.c"),
        )
        try:
            verify_manifest(fake_runtime)
            failures.append("missing manifest: expected BuildError, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.RUNTIME:
                failures.append(f"missing manifest: expected RUNTIME phase, got {exc.phase}")

    # Case 4: write_manifest regenerates a manifest that then verifies clean.
    with tempfile.TemporaryDirectory() as td:
        fake_dir = os.path.join(td, "runtime")
        os.makedirs(fake_dir)
        shutil.copy(real_runtime.header, os.path.join(fake_dir, "sv0_runtime.h"))
        shutil.copy(real_runtime.source, os.path.join(fake_dir, "sv0_runtime.c"))
        fake_runtime = RuntimeLocation(
            dir=fake_dir,
            header=os.path.join(fake_dir, "sv0_runtime.h"),
            source=os.path.join(fake_dir, "sv0_runtime.c"),
        )
        write_manifest(fake_runtime)
        try:
            verify_manifest(fake_runtime)
        except BuildError as exc:
            failures.append(f"freshly written manifest failed to verify: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_runtime_manifest selftest FAIL: {f}")
        return 1

    print("native_exe_runtime_manifest: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--write" in sys.argv:
        written = write_manifest(resolve_runtime_dir())
        print(f"native_exe_runtime_manifest: wrote {written}")
        raise SystemExit(0)
    print("native_exe_runtime_manifest: library module; use --selftest or --write", file=sys.stderr)
    raise SystemExit(2)
