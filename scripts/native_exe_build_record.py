"""Atomic build-record JSON with content/output hashes (NEX-042).

Implements REPRO-002…003
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` Appendix C):
a durable JSON record of exactly what a build produced and from what,
matching Appendix C's shape byte-for-byte in key structure -- artifact
identity (kind/path/sha256/size), input source hashes, `sv0c`/runtime/host/
compiler identity, profile, both contract modes, and a `hermetic` flag.

`build_record` computes the two hash-bearing pieces itself (the published
artifact's sha256/size via `hashlib.sha256` over its actual bytes, and each
input source file's sha256) from real paths -- it does not trust a caller
to supply those, since the whole point of a build record is that its
digests are independently verifiable against the files on disk. Everything
else (sv0c version/revision, runtime hashes, host, compiler identity,
profile, contract modes) is caller-supplied data this module has no way to
derive itself.

`write_build_record_atomically` reuses `native_exe_staging.write_text_atomically`
(NEX-039) with `json.dumps` -- no new atomic-write logic.

Run `python3 scripts/native_exe_build_record.py --selftest` for the corpus.
"""

from __future__ import annotations

import hashlib
import json
import os

from native_exe_staging import write_text_atomically

SCHEMA_VERSION = 1


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_record(
    *,
    artifact_path: str,
    input_kind: str,
    input_root: str,
    source_paths: list[str],
    sv0c_version: str,
    sv0c_revision: str,
    backend: str,
    runtime_abi: int,
    runtime_manifest_sha256: str,
    runtime_header_sha256: str,
    runtime_source_sha256: str,
    host_os: str,
    host_arch: str,
    c_compiler_path: str,
    c_compiler_family: str,
    c_compiler_version: str,
    c_compiler_argv: list[str],
    profile: str,
    contract_mode_requested: str,
    contract_mode_effective: str,
    hermetic: bool = False,
    config: dict | None = None,
) -> dict:
    """Build one Appendix-C-shaped record dict from a real published artifact."""
    artifact_bytes_sha256 = _sha256_file(artifact_path)
    artifact_size = os.path.getsize(artifact_path)

    sources = [{"path": p, "sha256": _sha256_file(p)} for p in source_paths]

    return {
        "schema_version": SCHEMA_VERSION,
        "artifact": {
            "kind": "native-executable",
            "path": artifact_path,
            "sha256": artifact_bytes_sha256,
            "size": artifact_size,
        },
        "input": {
            "kind": input_kind,
            "root": input_root,
            "sources": sources,
        },
        "sv0c": {
            "version": sv0c_version,
            "revision": sv0c_revision,
            "backend": backend,
            "runtime_abi": runtime_abi,
        },
        "runtime": {
            "manifest_sha256": runtime_manifest_sha256,
            "header_sha256": runtime_header_sha256,
            "source_sha256": runtime_source_sha256,
        },
        "host": {
            "os": host_os,
            "arch": host_arch,
        },
        "c_compiler": {
            "path": c_compiler_path,
            "family": c_compiler_family,
            "version": c_compiler_version,
            "argv": c_compiler_argv,
        },
        "profile": profile,
        "contract_mode_requested": contract_mode_requested,
        "contract_mode_effective": contract_mode_effective,
        "hermetic": hermetic,
        "config": config,
    }


def write_build_record_atomically(record: dict, output_path: str) -> None:
    write_text_atomically(json.dumps(record, indent=2, ensure_ascii=True) + "\n", output_path)


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    from native_exe_build import build_native_executable

    with tempfile.TemporaryDirectory() as td:
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("hi");\n    return 5;\n}\n')
        out = os.path.join(td, "hello_out")

        result = build_native_executable("file", src, out, td, probe=False)

        record = build_record(
            artifact_path=result.output_path,
            input_kind="file",
            input_root=src,
            source_paths=[src],
            sv0c_version="0.0.0-dev",
            sv0c_revision="unknown",
            backend="c",
            runtime_abi=1,
            runtime_manifest_sha256="deadbeef",
            runtime_header_sha256="deadbeef",
            runtime_source_sha256="deadbeef",
            host_os="darwin",
            host_arch="arm64",
            c_compiler_path="/usr/bin/cc",
            c_compiler_family="clang",
            c_compiler_version="Apple clang version 15.0.0",
            c_compiler_argv=["-std=gnu99", "-O0", "-g", src, "-o", out],
            profile="dev",
            contract_mode_requested="runtime",
            contract_mode_effective="runtime",
        )

        # Case 1: the record's artifact sha256 equals a direct hash of the
        # actually-published bytes (the load-bearing property of REPRO-002/003).
        direct_hash = _sha256_file(result.output_path)
        if record["artifact"]["sha256"] != direct_hash:
            failures.append(
                f"artifact sha256 mismatch: record={record['artifact']['sha256']} direct={direct_hash}"
            )
        if record["artifact"]["size"] != os.path.getsize(result.output_path):
            failures.append("artifact size mismatch")

        # Case 2: the recorded source hash matches a direct hash of the source file.
        if record["input"]["sources"][0]["sha256"] != _sha256_file(src):
            failures.append("source sha256 mismatch")

        # Case 3: atomic write round-trips through json.loads with the same content.
        record_path = os.path.join(td, "build-record.json")
        write_build_record_atomically(record, record_path)
        if not os.path.isfile(record_path):
            failures.append("build record file was not written")
        else:
            reloaded = json.loads(open(record_path, encoding="utf-8").read())
            if reloaded != record:
                failures.append("reloaded build record did not match the in-memory record")

        # Case 4: a mutated artifact (corrupted after publish) must NOT match a
        # stale record's hash -- proves the hash is a real content digest, not
        # a placeholder always agreeing with itself.
        with open(result.output_path, "ab") as f:
            f.write(b"CORRUPTED")
        corrupted_hash = _sha256_file(result.output_path)
        if corrupted_hash == record["artifact"]["sha256"]:
            failures.append("corrupting the artifact did not change its hash (test itself is broken)")

    if failures:
        for f in failures:
            print(f"native_exe_build_record selftest FAIL: {f}")
        return 1

    print("native_exe_build_record: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_build_record: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
