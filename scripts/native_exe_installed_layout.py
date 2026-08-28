"""Installed-layout E2E outside a source checkout (NEX-046), generalized
into a real, reusable installed-layout builder for the installed `sv0c`
command surface (NEX-060b).

Implements AC-023
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): the driver
must work when it's *installed* -- runtime bundle and core compiler binary
copied somewhere with no `sv0c` source tree alongside them at all -- not
just when run from inside this repo's own checkout. This is the sharpest
test of "does the driver actually resolve paths relative to itself /
via explicit overrides, rather than accidentally depending on something
only a source checkout provides" (a stray relative path, an assumption
about a sibling directory, an implicit `cwd`-relative lookup).

`_copy_installed_layout` (NEX-046) reuses `build_native_executable`'s
existing `runtime_override`/`compiler_path` test seams to prove the
*pipeline* is override-clean -- but it never proves the driver's own
*default* resolution (`native_exe_runtime.resolve_runtime_dir()`,
`native_exe_build.DEFAULT_COMPILER_PATH`) works standalone from a
relocated tree, since a test seam always overrides it. `build_install_layout`
(NEX-060b) closes that gap: it assembles a real, self-contained installed
tree -- `<root>/scripts/native_exe_*.py`, `<root>/sv0c/runtime/*`,
`<root>/build/sv0-megatu-native` -- preserving the exact relative shape
those two functions already assume, so a real `python3
<root>/scripts/native_exe_main.py` subprocess resolves everything
correctly with zero overrides, zero `sv0c` source tree, and zero
knowledge of this repo's own layout. This is the installed-layout
builder `sv0c/doc/native-executable-installed-command-design.md` (NEX-060a)
scoped: the same directory shape the `<install>/bin/sv0c` launcher
(NEX-060c) is built on top of.

Run `python3 scripts/native_exe_installed_layout.py --selftest` for the corpus.
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import tempfile

from native_exe_build import DEFAULT_COMPILER_PATH, build_native_executable
from native_exe_runtime import RuntimeLocation
from native_exe_runtime_bundle import verify_bundle_contents
from native_exe_runtime_manifest import verify_manifest

_SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.normpath(os.path.join(_SCRIPTS_DIR, ".."))


def compute_native_exe_module_closure(entry: str = "native_exe_main") -> set[str]:
    """Transitively walk `from native_exe_X import ...` / `import native_exe_X`
    statements starting at `entry`, returning every `native_exe_*` module
    name reachable from it (module names, no `.py`/directory).

    Computed by reading the actual source (`ast.parse`), not maintained as
    a hand-written list that could silently drift as the driver grows new
    imports -- a wrong/stale list here would produce an installed layout
    that's missing a module and fails at import time, which is exactly the
    class of bug this function exists to make impossible.
    """
    closure: set[str] = set()
    frontier = [entry]
    while frontier:
        name = frontier.pop()
        if name in closure:
            continue
        closure.add(name)
        path = os.path.join(_SCRIPTS_DIR, name + ".py")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("native_exe"):
                if node.module not in closure:
                    frontier.append(node.module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("native_exe") and alias.name not in closure:
                        frontier.append(alias.name)
    return closure


def build_install_layout(dest_root: str, entry: str = "native_exe_main") -> dict:
    """Assemble a real, self-contained installed tree at `dest_root`:
    `<dest_root>/scripts/native_exe_*.py` (the full import closure of
    `entry`), `<dest_root>/sv0c/runtime/*` (the runtime bundle, NEX-045),
    and `<dest_root>/build/sv0-megatu-native` (the core compiler binary) --
    the exact relative shape `native_exe_runtime.resolve_runtime_dir()`
    and `native_exe_build.DEFAULT_COMPILER_PATH` already assume by
    default, with no `runtime_override`/`compiler_path` overrides
    involved anywhere. Returns a dict of the paths written, for tests and
    for a future `<dest_root>/bin/sv0c` launcher (NEX-060c) to reference.
    """
    modules = compute_native_exe_module_closure(entry)

    dest_scripts = os.path.join(dest_root, "scripts")
    os.makedirs(dest_scripts, exist_ok=True)
    for name in modules:
        src = os.path.join(_SCRIPTS_DIR, name + ".py")
        shutil.copy2(src, os.path.join(dest_scripts, name + ".py"))

    dest_sv0c_runtime = os.path.join(dest_root, "sv0c", "runtime")
    real_runtime_dir = os.path.normpath(os.path.join(_ROOT_DIR, "sv0c", "runtime"))
    os.makedirs(os.path.dirname(dest_sv0c_runtime), exist_ok=True)
    shutil.copytree(real_runtime_dir, dest_sv0c_runtime)

    dest_build_dir = os.path.join(dest_root, "build")
    os.makedirs(dest_build_dir, exist_ok=True)
    dest_compiler_path = os.path.join(dest_build_dir, "sv0-megatu-native")
    shutil.copy2(DEFAULT_COMPILER_PATH, dest_compiler_path)
    os.chmod(dest_compiler_path, 0o755)

    return {
        "root": dest_root,
        "entry_script": os.path.join(dest_scripts, entry + ".py"),
        "runtime_dir": dest_sv0c_runtime,
        "compiler_path": dest_compiler_path,
        "modules": sorted(modules),
    }


def _copy_installed_layout(dest_dir: str) -> tuple[str, str]:
    """Copy the real runtime bundle + core compiler binary into `dest_dir`
    (which the caller has made to contain no `sv0c` source tree). Returns
    (runtime_dir, compiler_path) inside the copy.
    """
    this_dir = os.path.dirname(os.path.abspath(__file__))
    real_runtime_dir = os.path.normpath(os.path.join(this_dir, "..", "sv0c", "runtime"))

    installed_runtime_dir = os.path.join(dest_dir, "runtime")
    shutil.copytree(real_runtime_dir, installed_runtime_dir)

    installed_compiler_path = os.path.join(dest_dir, "sv0-megatu-native")
    shutil.copy2(DEFAULT_COMPILER_PATH, installed_compiler_path)
    os.chmod(installed_compiler_path, 0o755)

    return installed_runtime_dir, installed_compiler_path


def _selftest() -> int:
    failures: list[str] = []

    if not os.path.isfile(DEFAULT_COMPILER_PATH):
        print(f"native_exe_installed_layout selftest SKIP: {DEFAULT_COMPILER_PATH} not built")
        return 0

    # A fresh temp dir with a SPACE in its path, containing no sv0c source
    # tree alongside the copied layout at all (AC-023's literal point).
    with tempfile.TemporaryDirectory(prefix="installed layout ") as td:
        installed_runtime_dir, installed_compiler_path = _copy_installed_layout(td)

        # Case 1: the copied bundle verifies clean on its own (NEX-045).
        try:
            verify_bundle_contents(installed_runtime_dir)
        except Exception as exc:  # noqa: BLE001 - report any failure as a selftest failure
            failures.append(f"case1: copied bundle failed verify_bundle_contents: {exc}")

        # Case 2: the runtime manifest verifies against the copied bundle
        # (NEX-020), using the same RuntimeLocation shape resolve_runtime_dir
        # would produce, but pointed at the installed copy.
        runtime_location = RuntimeLocation(
            dir=installed_runtime_dir,
            header=os.path.join(installed_runtime_dir, "sv0_runtime.h"),
            source=os.path.join(installed_runtime_dir, "sv0_runtime.c"),
        )
        try:
            verify_manifest(runtime_location)
        except Exception as exc:  # noqa: BLE001
            failures.append(f"case2: copied runtime failed verify_manifest: {exc}")

        # Case 3: a real build, driven entirely off the installed copy via
        # runtime_override + compiler_path -- no sv0c source tree is ever
        # touched or assumed to exist.
        src = os.path.join(td, "hello.sv0")
        with open(src, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("installed layout works");\n    return 9;\n}\n')
        out = os.path.join(td, "hello_out")

        try:
            result = build_native_executable(
                "file",
                src,
                out,
                td,
                probe=False,
                runtime_override=runtime_location,
                compiler_path=installed_compiler_path,
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"case3: build from installed layout raised: {exc}")
            result = None

        if result is not None:
            if not os.path.isfile(result.output_path):
                failures.append("case3: installed-layout build produced no output file")
            else:
                proc = subprocess.run([result.output_path], capture_output=True, text=True)
                if proc.returncode != 9 or "installed layout works" not in proc.stdout:
                    failures.append(
                        f"case3: installed-layout binary misbehaved: rc={proc.returncode} stdout={proc.stdout!r}"
                    )

        # Case 4: confirm the whole test genuinely had no sv0c tree beside it --
        # a sanity check on the test's own setup, not the pipeline.
        if os.path.isdir(os.path.join(td, "sv0c")):
            failures.append("case4: test setup itself is broken -- an sv0c tree exists beside the installed copy")

    # Case 5 (NEX-060b): a real `build_install_layout` tree, at a SECOND
    # temp prefix also containing a space, exercised via a REAL subprocess
    # invocation of the installed native_exe_main.py with NO overrides
    # passed at all -- proving the driver's *default* resolve_runtime_dir()/
    # DEFAULT_COMPILER_PATH resolution genuinely works standalone from a
    # relocated tree, which case 1-4 above (via explicit overrides) never
    # actually exercised.
    with tempfile.TemporaryDirectory(prefix="sv0c install root ") as install_root:
        layout = build_install_layout(install_root)

        expected_module_count = len(compute_native_exe_module_closure())
        if len(layout["modules"]) != expected_module_count or expected_module_count == 0:
            failures.append(f"case5: unexpected module closure size {len(layout['modules'])}")
        for name in layout["modules"]:
            if not os.path.isfile(os.path.join(install_root, "scripts", name + ".py")):
                failures.append(f"case5: closure module {name} not actually copied into the install tree")

        src5 = os.path.join(install_root, "hello.sv0")
        with open(src5, "w", encoding="utf-8") as f:
            f.write('fn main() -> i32 {\n    println("installed sv0c layout works");\n    return 11;\n}\n')
        out5 = os.path.join(install_root, "hello_out")

        proc = subprocess.run(
            [sys.executable, layout["entry_script"], "-o", out5, src5],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0 or not os.path.isfile(out5):
            failures.append(
                f"case5: real installed-layout subprocess (no overrides) failed: "
                f"rc={proc.returncode} stderr={proc.stderr!r}"
            )
        else:
            run_proc = subprocess.run([out5], capture_output=True, text=True)
            if run_proc.returncode != 11 or "installed sv0c layout works" not in run_proc.stdout:
                failures.append(
                    f"case5: installed-layout binary misbehaved: "
                    f"rc={run_proc.returncode} stdout={run_proc.stdout!r}"
                )

        # Case 6: corrupt the COPY's native_exe_runtime.py (never the
        # source tree) so it always raises -- proving case 5's subprocess
        # genuinely imports and runs off the installed copy, not a
        # cached/real location. If the corruption were somehow not
        # reached, the subprocess would still succeed and this case
        # would (correctly) fail.
        corrupted_module_path = os.path.join(install_root, "scripts", "native_exe_runtime.py")
        original_source = open(corrupted_module_path, encoding="utf-8").read()
        corrupted_source = original_source + (
            "\ndef resolve_runtime_dir(root=None):\n"
            "    raise RuntimeError('native_exe_installed_layout case6 corruption marker')\n"
        )
        with open(corrupted_module_path, "w", encoding="utf-8") as f:
            f.write(corrupted_source)
        try:
            src6 = os.path.join(install_root, "hello2.sv0")
            with open(src6, "w", encoding="utf-8") as f:
                f.write("fn main() -> i32 {\n    return 0;\n}\n")
            out6 = os.path.join(install_root, "hello2_out")
            corrupted_proc = subprocess.run(
                [sys.executable, layout["entry_script"], "-o", out6, src6],
                capture_output=True,
                text=True,
            )
            if corrupted_proc.returncode == 0 or "case6 corruption marker" not in corrupted_proc.stderr:
                failures.append(
                    "case6: corrupting the installed copy's native_exe_runtime.py had no "
                    f"effect -- subprocess didn't genuinely run off the copy "
                    f"(rc={corrupted_proc.returncode}, stderr={corrupted_proc.stderr!r})"
                )
        finally:
            with open(corrupted_module_path, "w", encoding="utf-8") as f:
                f.write(original_source)

    if failures:
        for f in failures:
            print(f"native_exe_installed_layout selftest FAIL: {f}")
        return 1

    print("native_exe_installed_layout: selftest OK (6 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_installed_layout: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
