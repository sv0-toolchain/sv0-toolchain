"""Runtime-feature native coverage beyond the behavior corpus (NEX-029).

Implements RT-007…008
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): println,
string, and Vec are already exercised extensively by
`native_exe_behavior_corpus.py`'s full 112-row sweep over
`sv0c/test/behavior/manifest.txt` (NEX-028) — that sweep *is* this
requirement's evidence for those three features, not reproduced here. This
module covers what that sweep doesn't:

  - **Box** (RT-007): `sv0c/test/integration/box_expr/box_expr.sv0` is a
    real, already-existing fixture (`Box<Expr>`/`box_new`/`box_deref`,
    proven on the VM path today) — built here through
    `native_exe_build.build_native_executable` to confirm it links (no
    unresolved `sv0_box_*` symbols) and exits 0 on the native path too.
  - **Filesystem host I/O** (RT-007): no fixture exercising
    `read_file`/`write_file`/`read_dir` exists anywhere in this repo yet.
    Deliberately not invented here — RT-007 applies "where supported," and
    nothing in the current corpus requires it. Documented, not silently
    skipped: `FILESYSTEM_IO_COVERAGE` records this explicitly so a future
    fixture has an obvious place to plug in.
  - **stdout/stderr channel separation for a real compiled program**
    (RT-008): a `requires`-violation fixture confirms `println` output
    lands on stdout and the runtime's own `sv0 contract violation: ...`
    diagnostic (from `sv0_requires` in `sv0c/runtime/sv0_runtime.h`, which
    `fprintf`s to stderr) lands on stderr — verified directly against the
    real compiled binary's separate stdout/stderr streams, not just at the
    subprocess-wrapper unit level (already covered by NEX-012/025).

Run `python3 scripts/native_exe_runtime_feature_smoke.py --selftest` for
the corpus.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

from native_exe_build import build_native_executable

FILESYSTEM_IO_COVERAGE = (
    "no fixture in this repo exercises read_file/write_file/read_dir yet; "
    "RT-007 applies 'where supported' and nothing in the current corpus "
    "requires it -- add a fixture here when one exists, don't fabricate one"
)


def _selftest() -> int:
    failures: list[str] = []
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    box_expr = os.path.join(root, "sv0c", "test", "integration", "box_expr", "box_expr.sv0")

    with tempfile.TemporaryDirectory() as td:
        # Case 1 (RT-007): Box links and runs correctly through the native driver.
        if not os.path.isfile(box_expr):
            failures.append(f"fixture missing: {box_expr}")
        else:
            out = os.path.join(td, "box_expr_out")
            build_native_executable("file", box_expr, out, td, probe=False)
            proc = subprocess.run([out], capture_output=True)
            if proc.returncode != 0:
                failures.append(f"box_expr: expected exit 0, got {proc.returncode}")

        # Case 2 (RT-008): println (stdout) and a runtime contract violation
        # (stderr) stay on separate channels for a real compiled program.
        src = os.path.join(td, "contract_channels.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write(
                "fn f(x: i32) -> i32 requires(x > 0) { return x + 100; }\n"
                'fn main() -> i32 {\n    println("before violation");\n    return f(0 - 5);\n}\n'
            )
        out2 = os.path.join(td, "contract_channels_out")
        build_native_executable("file", src, out2, td, probe=False)
        proc2 = subprocess.run([out2], capture_output=True, text=True)
        if proc2.returncode != 1:
            failures.append(f"channel separation: expected exit 1, got {proc2.returncode}")
        if "before violation" not in proc2.stdout:
            failures.append(f"channel separation: println missing from stdout: {proc2.stdout!r}")
        if "sv0 contract violation" not in proc2.stderr:
            failures.append(f"channel separation: contract diagnostic missing from stderr: {proc2.stderr!r}")
        if "before violation" in proc2.stderr or "sv0 contract violation" in proc2.stdout:
            failures.append("channel separation: output leaked across streams")

    if failures:
        for f in failures:
            print(f"native_exe_runtime_feature_smoke selftest FAIL: {f}")
        return 1

    print("native_exe_runtime_feature_smoke: selftest OK (2 case groups)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_runtime_feature_smoke: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
