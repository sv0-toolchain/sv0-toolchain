"""Installed runtime bundle manifest + licenses verification (NEX-045).

Implements RT-009
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §15.1): the
runtime bundle a driver ships and reads at build time must carry, alongside
`sv0_runtime.h`/`.c`, an ABI version marker (`abi-version.txt`, matching
`native_exe_runtime_manifest.ABI_VERSION`), the hash manifest
(`runtime-manifest.json`, NEX-020), and license text for the bundle's own
dual Apache-2.0/MIT terms (`licenses/LICENSE-APACHE`, `licenses/LICENSE-MIT`)
-- so an installed (non-source-checkout) copy of the runtime is
self-describing and doesn't need the surrounding `sv0c` repo to prove its
identity or licensing.

`verify_bundle_contents` checks presence and (for `abi-version.txt`)
content, failing closed rather than silently treating a missing member as
optional.

Run `python3 scripts/native_exe_runtime_bundle.py --selftest` for the corpus.
"""

from __future__ import annotations

import os

from native_exe_runtime_manifest import ABI_VERSION

_REQUIRED_MEMBERS = [
    "sv0_runtime.h",
    "sv0_runtime.c",
    "abi-version.txt",
    "runtime-manifest.json",
    os.path.join("licenses", "LICENSE-APACHE"),
    os.path.join("licenses", "LICENSE-MIT"),
]


class RuntimeBundleError(Exception):
    """Raised when an installed runtime bundle is missing a required member
    or carries an inconsistent ABI version marker."""


def verify_bundle_contents(runtime_dir: str) -> None:
    """Confirm `runtime_dir` has the full §15.1 bundle shape.

    Raises `RuntimeBundleError` naming the first missing member, or an
    `abi-version.txt` whose content doesn't match
    `native_exe_runtime_manifest.ABI_VERSION`.
    """
    for member in _REQUIRED_MEMBERS:
        member_path = os.path.join(runtime_dir, member)
        if not os.path.isfile(member_path):
            raise RuntimeBundleError(f"{runtime_dir}: missing required runtime bundle member {member!r}")

    abi_path = os.path.join(runtime_dir, "abi-version.txt")
    abi_text = open(abi_path, encoding="utf-8").read().strip()
    try:
        abi_value = int(abi_text)
    except ValueError as exc:
        raise RuntimeBundleError(f"{abi_path}: not an integer ABI version: {abi_text!r}") from exc
    if abi_value != ABI_VERSION:
        raise RuntimeBundleError(
            f"{abi_path}: ABI version {abi_value} does not match expected {ABI_VERSION}"
        )


def _selftest() -> int:
    import shutil
    import tempfile

    failures: list[str] = []
    this_dir = os.path.dirname(os.path.abspath(__file__))
    real_runtime_dir = os.path.normpath(os.path.join(this_dir, "..", "sv0c", "runtime"))

    # Case 1: the real, in-repo runtime bundle verifies clean.
    try:
        verify_bundle_contents(real_runtime_dir)
    except RuntimeBundleError as exc:
        failures.append(f"case1: real runtime bundle failed verification: {exc}")

    # Case 2..N: a temp copy missing exactly one required member fails closed,
    # one member at a time -- proves every member is actually load-bearing,
    # not just the first one checked.
    for missing_member in _REQUIRED_MEMBERS:
        with tempfile.TemporaryDirectory() as td:
            bundle_dir = os.path.join(td, "runtime")
            shutil.copytree(real_runtime_dir, bundle_dir)
            victim_path = os.path.join(bundle_dir, missing_member)
            os.remove(victim_path)
            try:
                verify_bundle_contents(bundle_dir)
                failures.append(f"missing {missing_member!r}: expected RuntimeBundleError, none raised")
            except RuntimeBundleError as exc:
                if missing_member not in str(exc):
                    failures.append(f"missing {missing_member!r}: error didn't name the missing member: {exc}")

    # Case: a wrong ABI version is rejected even though every file is present.
    with tempfile.TemporaryDirectory() as td:
        bundle_dir = os.path.join(td, "runtime")
        shutil.copytree(real_runtime_dir, bundle_dir)
        with open(os.path.join(bundle_dir, "abi-version.txt"), "w", encoding="utf-8") as f:
            f.write("999\n")
        try:
            verify_bundle_contents(bundle_dir)
            failures.append("wrong ABI version: expected RuntimeBundleError, none raised")
        except RuntimeBundleError as exc:
            if "999" not in str(exc):
                failures.append(f"wrong ABI version: error didn't name the mismatch: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_runtime_bundle selftest FAIL: {f}")
        return 1

    print(f"native_exe_runtime_bundle: selftest OK ({2 + len(_REQUIRED_MEMBERS)} cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_runtime_bundle: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
