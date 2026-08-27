"""Contract-mode executable matrix: runtime/verified/disabled (NEX-031).

Implements PIPE-008…009
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): all three
contract modes reuse `native_exe_build.build_native_executable`'s
`contract_mode` parameter unchanged — this slice's own job is `verified`
mode's proof-file computation, which was deliberately left out of
`build_native_executable` (NEX-028) to keep that function pure composition.

`compute_proof_lines` mirrors `scripts/sv0`'s own `run_emit_verified` pass 1
exactly (same compiled verify binary, same `sv0-z3.sh` driver) rather than
reimplementing VC generation or SMT-LIB2 handling: it runs
`build/sv0-megatu-verify` to get `ensures` verification-condition records,
discharges each through `scripts/sv0-z3.sh`, and keeps the source line of
every `unsat` (proven) result. If `z3` isn't found, it returns an empty
proof file — nothing is proven, nothing is stripped, so a missing solver
can never silently become a false "verified" claim (PIPE-009).

Run `python3 scripts/native_exe_contract_mode.py --selftest` for the
corpus, using the real, installed Z3 (4.16.0 in this dev environment) for
the proven leg and a `PATH`-hiding override for the degradation leg.
"""

from __future__ import annotations

import os
import shutil
import tempfile

from native_exe_subprocess import run_argv

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_VERIFY_BINARY = os.path.join(_REPO_ROOT, "build", "sv0-megatu-verify")
DEFAULT_Z3_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "sv0-z3.sh")


def compute_proof_lines(
    abs_path: str,
    verify_binary: str | None = None,
    z3_script: str | None = None,
    path_override: str | None = None,
) -> str:
    """Return a path to a temp file listing the source line of every PROVEN
    `ensures` obligation in `abs_path`. Empty (not missing) if `z3` isn't
    found on the searched PATH -- sound degradation, PIPE-009.
    """
    proof_fd, proof_path = tempfile.mkstemp(suffix=".proof")
    os.close(proof_fd)

    search_path = path_override if path_override is not None else os.environ.get("PATH")
    if shutil.which("z3", path=search_path) is None:
        open(proof_path, "w", encoding="utf-8").close()
        return proof_path

    verify_bin = verify_binary or DEFAULT_VERIFY_BINARY
    z3 = z3_script or DEFAULT_Z3_SCRIPT

    result = run_argv([verify_bin, abs_path])
    proven_lines: list[str] = []

    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 5 or parts[0] != "VC" or parts[2] != "ensures":
            continue
        src_line, query = parts[1], parts[4]
        query_fd, query_path = tempfile.mkstemp(suffix=".smt2")
        try:
            with os.fdopen(query_fd, "w") as qf:
                qf.write(query + "\n")
            z3_result = run_argv(["bash", z3, query_path])
            verdict_lines = z3_result.stdout.strip().splitlines()
            verdict = verdict_lines[0] if verdict_lines else ""
            if verdict == "unsat":
                proven_lines.append(src_line)
        finally:
            os.remove(query_path)

    with open(proof_path, "w", encoding="utf-8") as f:
        for src_line in proven_lines:
            f.write(src_line + "\n")
    return proof_path


def _selftest() -> int:
    import subprocess

    from native_exe_build import build_native_executable

    failures: list[str] = []
    sv0c = os.path.join(_REPO_ROOT, "sv0c")

    with tempfile.TemporaryDirectory() as td:
        # Case 1 (runtime mode): requires satisfied, runs to completion.
        runtime_src = os.path.join(sv0c, "test", "behavior", "cases", "contract_ok.sv0")
        out1 = os.path.join(td, "runtime_out")
        build_native_executable("file", runtime_src, out1, td, contract_mode="runtime", probe=False)
        rc1 = subprocess.run([out1], capture_output=True).returncode
        if rc1 != 6:
            failures.append(f"runtime mode: expected exit 6 (half(12)), got {rc1}")

        # Case 2 (disabled mode): a requires violation that WOULD abort in
        # runtime mode instead runs the stripped body to completion.
        disabled_src = os.path.join(td, "disabled_case.sv0")
        with open(disabled_src, "w", encoding="utf-8") as f:
            f.write("fn half(x: i32) -> i32 requires(x > 0) { return x / 2; }\nfn main() -> i32 { return half(0 - 4) + 10; }\n")
        out2a = os.path.join(td, "runtime_violation_out")
        build_native_executable("file", disabled_src, out2a, td, contract_mode="runtime", probe=False)
        rc2a = subprocess.run([out2a], capture_output=True).returncode
        if rc2a != 1:
            failures.append(f"runtime mode (violation): expected exit 1 (contract abort), got {rc2a}")

        out2b = os.path.join(td, "disabled_out")
        build_native_executable("file", disabled_src, out2b, td, contract_mode="disabled", probe=False)
        rc2b = subprocess.run([out2b], capture_output=True).returncode
        # half(-4) + 10 == -2 + 10 == 8, with the check stripped instead of aborting.
        if rc2b != 8:
            failures.append(f"disabled mode: expected exit 8 (check stripped), got {rc2b}")

        # Case 3 (verified mode, real Z3): a proven `ensures` is stripped;
        # the program still runs correctly (the underlying computation is
        # unaffected -- only the now-redundant runtime check is gone).
        verified_src = os.path.join(sv0c, "test", "behavior", "cases", "contract_ensures_ok.sv0")
        proof_path = compute_proof_lines(verified_src)
        try:
            with open(proof_path, encoding="utf-8") as f:
                proof_content = f.read()
            if shutil.which("z3") is not None and proof_content.strip() == "":
                failures.append("verified mode: expected at least one proven ensures with real z3, proof file is empty")
            out3 = os.path.join(td, "verified_out")
            build_native_executable(
                "file", verified_src, out3, td, contract_mode="verified", proof_path=proof_path, probe=False
            )
            rc3 = subprocess.run([out3], capture_output=True).returncode
            if rc3 != 8:
                failures.append(f"verified mode: expected exit 8 (dbl(4)), got {rc3}")
        finally:
            os.remove(proof_path)

        # Case 4 (PIPE-009, sound degradation): hiding z3 from the searched
        # PATH must produce an empty proof (nothing proven), never a false
        # "verified" claim -- and the build must still succeed, with every
        # check retained (identical behavior to runtime mode).
        empty_bin_dir = os.path.join(td, "empty_path")
        os.makedirs(empty_bin_dir, exist_ok=True)
        degraded_proof = compute_proof_lines(verified_src, path_override=empty_bin_dir)
        try:
            with open(degraded_proof, encoding="utf-8") as f:
                if f.read().strip() != "":
                    failures.append("degradation: expected an empty proof file when z3 is hidden from PATH")
            out4 = os.path.join(td, "degraded_out")
            build_native_executable(
                "file", verified_src, out4, td, contract_mode="verified", proof_path=degraded_proof, probe=False
            )
            rc4 = subprocess.run([out4], capture_output=True).returncode
            if rc4 != 8:
                failures.append(f"degradation: expected exit 8 (dbl(4), check retained either way), got {rc4}")
        finally:
            os.remove(degraded_proof)

    if failures:
        for f in failures:
            print(f"native_exe_contract_mode selftest FAIL: {f}")
        return 1

    print("native_exe_contract_mode: selftest OK (4 case groups)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_contract_mode: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
