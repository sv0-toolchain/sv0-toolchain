"""Stable entry ABI version + manifest (NEX-054a, ENTRY-010).

Implements ENTRY-010
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "the entry
ABI and reserved symbols SHALL be versioned and documented." This is a
genuinely new, parallel concept to `native_exe_runtime_manifest.ABI_VERSION`
(NEX-020), which versions only the runtime *bundle* (header/source hashes)
-- nothing in this codebase versioned the entry contract itself before
this slice: the reserved-symbol set
(`native_exe_entry_reserved.RESERVED_ENTRY_SYMBOLS`) and the two hosted
`int main(argc, argv)` adapter shapes `megaTU-main.sv0` emits (one for an
i32-returning user `main`, one for a unit-returning one).

The adapter shape strings below are copied byte-for-byte from
`sv0c/lib/megaTU-main.sv0`'s own emission code (not paraphrased) -- if
that emitter ever changes either shape, this module's hash check fails
until `ENTRY_ABI_VERSION` is deliberately bumped, per ENTRY-010's
versioning requirement.

Run `python3 scripts/native_exe_entry_abi.py --selftest` for the corpus,
or `--write-manifest` to (re)write `sv0c/runtime/entry-abi-manifest.json`
after a deliberate ABI change.
"""

from __future__ import annotations

import hashlib
import json
import os

from native_exe_entry_reserved import RESERVED_ENTRY_SYMBOLS
from native_exe_errors import BuildError, DiagnosticPhase

ENTRY_ABI_VERSION = 1

# Byte-for-byte copies of megaTU-main.sv0's own emitted adapter strings
# (lines ~684 and ~687 as of this writing) -- the actual, real ABI
# surface, not a paraphrase of it.
ADAPTER_SHAPE_I32_RETURN = (
    "int main(int argc, char **argv) {\n"
    "  sv0_runtime_init(argc, argv);\n"
    "  return (int)sv0_user_main();\n"
    "}\n\n"
)
ADAPTER_SHAPE_UNIT_RETURN = (
    "int main(int argc, char **argv) {\n"
    "  sv0_runtime_init(argc, argv);\n"
    "  sv0_user_main();\n"
    "  return 0;\n"
    "}\n\n"
)


def _manifest_path() -> str:
    this_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(this_dir, "..", "sv0c", "runtime", "entry-abi-manifest.json"))


def compute_entry_abi_hashes() -> dict:
    """The current, real ABI surface's hashes -- reserved-symbol set
    (order-independent: sorted before hashing) and both adapter shapes.
    """
    reserved_sorted = sorted(RESERVED_ENTRY_SYMBOLS)
    reserved_digest = hashlib.sha256(json.dumps(reserved_sorted).encode("utf-8")).hexdigest()
    i32_digest = hashlib.sha256(ADAPTER_SHAPE_I32_RETURN.encode("utf-8")).hexdigest()
    unit_digest = hashlib.sha256(ADAPTER_SHAPE_UNIT_RETURN.encode("utf-8")).hexdigest()
    return {
        "entry_abi_version": ENTRY_ABI_VERSION,
        "reserved_symbols_sha256": reserved_digest,
        "adapter_i32_return_sha256": i32_digest,
        "adapter_unit_return_sha256": unit_digest,
    }


class EntryAbiMismatchError(Exception):
    """Raised when the live entry ABI surface no longer matches the
    committed snapshot without a version bump."""


def verify_entry_abi_manifest(manifest_path: str | None = None) -> None:
    """Raise `EntryAbiMismatchError` if the live reserved-symbol set or
    either adapter shape has drifted from the committed snapshot at
    `entry-abi-manifest.json` without `ENTRY_ABI_VERSION` being bumped.
    """
    path = manifest_path if manifest_path is not None else _manifest_path()
    with open(path, encoding="utf-8") as f:
        snapshot = json.load(f)

    current = compute_entry_abi_hashes()
    if snapshot.get("entry_abi_version") != current["entry_abi_version"]:
        # A version bump is itself a deliberate, allowed ABI change -- the
        # snapshot simply hasn't been regenerated for the new version yet.
        # That's a separate, human-driven step (--write-manifest), not an
        # error this function raises.
        return
    for key in ("reserved_symbols_sha256", "adapter_i32_return_sha256", "adapter_unit_return_sha256"):
        if snapshot.get(key) != current[key]:
            raise EntryAbiMismatchError(
                f"{path}: {key} changed without an ENTRY_ABI_VERSION bump "
                f"(snapshot={snapshot.get(key)!r}, current={current[key]!r})"
            )


def verify_entry_abi_compat(runtime_dir: str) -> None:
    """The RUNTIME-facing half of ENTRY-010 (NEX-054b), distinct from
    `verify_entry_abi_manifest`'s repo-hygiene drift check: reads
    `<runtime_dir>/entry-abi-manifest.json` (part of the runtime bundle
    since NEX-054a) and raises `BuildError(RUNTIME)` if its declared
    `entry_abi_version` doesn't match this compiled driver's own
    `ENTRY_ABI_VERSION` -- mirroring
    `native_exe_runtime_manifest.verify_manifest`'s existing ABI-version
    compat check for the runtime bundle itself, applied to the entry
    contract instead.
    """
    manifest_path = os.path.join(runtime_dir, "entry-abi-manifest.json")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise BuildError(DiagnosticPhase.RUNTIME, f"missing entry ABI manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(DiagnosticPhase.RUNTIME, f"malformed entry ABI manifest {manifest_path}: {exc}") from exc

    declared = data.get("entry_abi_version")
    if declared != ENTRY_ABI_VERSION:
        raise BuildError(
            DiagnosticPhase.RUNTIME,
            f"{manifest_path}: entry_abi_version {declared!r} is not supported "
            f"by this compiler (expected {ENTRY_ABI_VERSION})",
        )


def write_manifest(manifest_path: str | None = None) -> None:
    path = manifest_path if manifest_path is not None else _manifest_path()
    content = json.dumps(compute_entry_abi_hashes(), indent=2) + "\n"
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, path)


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    # Case 1: the real, committed manifest matches the live ABI surface.
    try:
        verify_entry_abi_manifest()
    except (EntryAbiMismatchError, FileNotFoundError) as exc:
        failures.append(f"case1: real manifest failed verification: {exc}")

    # Case 2: a manifest with a stale hash (same version) is rejected.
    with tempfile.TemporaryDirectory() as td:
        stale_path = os.path.join(td, "entry-abi-manifest.json")
        current = compute_entry_abi_hashes()
        stale = dict(current)
        stale["reserved_symbols_sha256"] = "0" * 64
        with open(stale_path, "w", encoding="utf-8") as f:
            json.dump(stale, f)
        try:
            verify_entry_abi_manifest(stale_path)
            failures.append("case2: expected EntryAbiMismatchError for a stale hash, none raised")
        except EntryAbiMismatchError:
            pass

    # Case 3: a manifest for a DIFFERENT (older/newer) version is not
    # flagged as a mismatch -- a version bump is the allowed escape hatch.
    with tempfile.TemporaryDirectory() as td:
        old_version_path = os.path.join(td, "entry-abi-manifest.json")
        old = dict(compute_entry_abi_hashes())
        old["entry_abi_version"] = 999
        old["reserved_symbols_sha256"] = "irrelevant-for-a-different-version"
        with open(old_version_path, "w", encoding="utf-8") as f:
            json.dump(old, f)
        try:
            verify_entry_abi_manifest(old_version_path)
        except EntryAbiMismatchError as exc:
            failures.append(f"case3: a different entry_abi_version should not be flagged as a mismatch: {exc}")

    # Case 4: write_manifest + verify round-trips cleanly.
    with tempfile.TemporaryDirectory() as td:
        out_path = os.path.join(td, "entry-abi-manifest.json")
        write_manifest(out_path)
        try:
            verify_entry_abi_manifest(out_path)
        except EntryAbiMismatchError as exc:
            failures.append(f"case4: freshly-written manifest failed its own verification: {exc}")

    # Case 5 (NEX-054b): verify_entry_abi_compat -- the real, shipped
    # sv0c/runtime/ bundle's entry-abi-manifest.json is compatible with
    # this compiled driver's own ENTRY_ABI_VERSION.
    real_runtime_dir = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sv0c", "runtime")
    )
    try:
        verify_entry_abi_compat(real_runtime_dir)
    except BuildError as exc:
        failures.append(f"case5: real runtime bundle failed entry-ABI compat check: {exc}")

    # Case 6: an installed bundle declaring an unsupported entry_abi_version
    # fails closed with BuildError(RUNTIME), naming the mismatch clearly.
    with tempfile.TemporaryDirectory() as td:
        bad_manifest = os.path.join(td, "entry-abi-manifest.json")
        with open(bad_manifest, "w", encoding="utf-8") as f:
            json.dump({"entry_abi_version": 999}, f)
        try:
            verify_entry_abi_compat(td)
            failures.append("case6: expected BuildError for an unsupported entry_abi_version, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.RUNTIME:
                failures.append(f"case6: expected RUNTIME phase, got {exc.phase}")
            if "999" not in exc.message:
                failures.append(f"case6: error didn't name the unsupported version: {exc.message!r}")

    # Case 7: a missing entry-abi-manifest.json also fails closed, not a raw crash.
    with tempfile.TemporaryDirectory() as td:
        try:
            verify_entry_abi_compat(td)
            failures.append("case7: expected BuildError for a missing manifest, none raised")
        except BuildError as exc:
            if exc.phase is not DiagnosticPhase.RUNTIME:
                failures.append(f"case7: expected RUNTIME phase, got {exc.phase}")

    if failures:
        for f in failures:
            print(f"native_exe_entry_abi selftest FAIL: {f}")
        return 1

    print("native_exe_entry_abi: selftest OK (7 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    if "--write-manifest" in sys.argv:
        write_manifest()
        print(f"native_exe_entry_abi: wrote {_manifest_path()}")
        raise SystemExit(0)
    print("native_exe_entry_abi: library module; use --selftest or --write-manifest", file=sys.stderr)
    raise SystemExit(2)
