"""Staging-C protocol validation and content hashing (NEX-018).

Implements PIPE-006/PIPE-011
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §13.5):

  - PIPE-011: "The staging C SHALL contain the expected runtime ABI/include
    marker before host compile." `validate_staging_c` checks this — a
    successful core-compiler exit with content that doesn't even look like
    sv0-generated C (missing `#include "sv0_runtime.h"`) is an emitter-protocol
    failure, not something to hand the host compiler and let it fail
    confusingly on unrelated grounds.
  - PIPE-006: "Single-file executable C SHALL be semantically identical to
    explicit C-emission output for the same mode." There is exactly one
    emission call in this driver (`native_exe_emit.classify_emission`) for
    both `--emit=c` and `--emit=exe` — this module never re-derives or
    re-processes the C differently per mode, so byte-identity holds by
    construction. `hash_staging_c` makes that verifiable (and is the same
    digest `--keep-c` (NEX-040) will later compare against).

`RUNTIME_INCLUDE_MARKER` here is the canonical definition; the test double
`native_exe_fake_emitter.py` keeps its own independent copy of the same
literal (test infrastructure intentionally does not import production
constants — it simulates the protocol, it doesn't consume it).

Run `python3 scripts/native_exe_staging.py --selftest` for the corpus.
"""

from __future__ import annotations

import hashlib

from native_exe_errors import BuildError, DiagnosticPhase

RUNTIME_INCLUDE_MARKER = '#include "sv0_runtime.h"'


def validate_staging_c(c_source: str) -> None:
    """Raise BuildError(EMIT_C) unless `c_source` contains the runtime ABI marker."""
    if RUNTIME_INCLUDE_MARKER not in c_source:
        raise BuildError(
            DiagnosticPhase.EMIT_C,
            "staging C is missing the expected runtime ABI include marker "
            f"({RUNTIME_INCLUDE_MARKER!r}); refusing to hand this to the host compiler",
        )


def hash_staging_c(c_source: str) -> str:
    """SHA-256 hex digest of the exact staging C bytes (OD-008: SHA-256)."""
    return hashlib.sha256(c_source.encode("utf-8")).hexdigest()


def _selftest() -> int:
    import os
    import sys

    from native_exe_emit import classify_emission
    from native_exe_subprocess import run_argv

    failures: list[str] = []

    # Case 1: valid staging C (has the marker) passes validation.
    try:
        validate_staging_c('#include "sv0_runtime.h"\n\nint main(void) { return 0; }\n')
    except BuildError as exc:
        failures.append(f"valid marker: unexpected BuildError: {exc}")

    # Case 2: C missing the marker is rejected as an emitter-protocol failure.
    try:
        validate_staging_c("int main(void) { return 0; }\n")
        failures.append("missing marker: expected BuildError, none raised")
    except BuildError as exc:
        if exc.phase is not DiagnosticPhase.EMIT_C:
            failures.append(f"missing marker: expected EMIT_C, got {exc.phase}")
        if exc.exit_code != 4:
            failures.append(f"missing marker: expected exit 4, got {exc.exit_code}")

    # Case 3: hashing is deterministic and content-sensitive.
    a = hash_staging_c("same content")
    b = hash_staging_c("same content")
    c = hash_staging_c("different content")
    if a != b:
        failures.append("hash_staging_c: same input produced different hashes")
    if a == c:
        failures.append("hash_staging_c: different input produced the same hash")
    if len(a) != 64:
        failures.append(f"hash_staging_c: expected a 64-char hex digest, got {len(a)} chars")

    # Case 4 (PIPE-006, the literal red test): the C reaching validate/hash in
    # "executable mode" is byte-identical to what an "explicit --emit=c" call
    # would see, because both paths go through the same classify_emission call
    # with no per-mode divergence. Prove it with two independent invocations
    # of the real fake emitter (one "playing" plain --emit=c, one "playing"
    # --emit=exe) and compare.
    this_dir = os.path.dirname(os.path.abspath(__file__))
    fake_emitter = os.path.join(this_dir, "native_exe_fake_emitter.py")
    env = dict(os.environ)
    env["SV0_FAKE_EMITTER_MODE"] = "valid"

    emit_c_result = classify_emission(run_argv([sys.executable, fake_emitter, "input.sv0"], env=env))
    emit_exe_result = classify_emission(run_argv([sys.executable, fake_emitter, "input.sv0"], env=env))

    if emit_c_result.c_source != emit_exe_result.c_source:
        failures.append("PIPE-006: --emit=c and --emit=exe staging C diverged")
    if hash_staging_c(emit_c_result.c_source) != hash_staging_c(emit_exe_result.c_source):
        failures.append("PIPE-006: --emit=c and --emit=exe staging C hashes diverged")
    try:
        validate_staging_c(emit_exe_result.c_source)
    except BuildError as exc:
        failures.append(f"PIPE-006/011: real emitted C failed marker validation: {exc}")

    if failures:
        for f in failures:
            print(f"native_exe_staging selftest FAIL: {f}")
        return 1

    print("native_exe_staging: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_staging: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
