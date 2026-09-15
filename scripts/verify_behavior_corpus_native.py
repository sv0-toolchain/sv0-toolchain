#!/usr/bin/env python3
"""Behavioral PASS corpus: compile each program with the native mega-TU compiler,
cc it, run it, and assert the process exit code matches the manifest.

Manifest: sv0c/test/behavior/manifest.txt, one row per line:  rel | expected_exit
Run by `./scripts/sv0 test`. Complements the diagnostics (reject) corpus.

Rows are independent (each gets its own temp dir, own emit/compile/run), so
they run across a small thread pool instead of one at a time -- each row's
real work (the native-emitter subprocess, `cc`, running the binary) already
releases the GIL, so threads parallelize the wait just like separate
processes would, without the extra interpreter-startup cost of one.
"""
from __future__ import annotations
import argparse, os, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from native_exe_canonical_compile import compile_and_publish
from native_exe_errors import BuildError


def _job_count() -> int:
    env = os.environ.get("SV0_JOBS")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            pass
    return os.cpu_count() or 4


def _run_one(sv0c: Path, wrapper: Path, rel: str, want: int) -> str | None:
    """Returns None on success, else an error message."""
    case = sv0c / rel
    if not case.is_file():
        return f"missing case {case}"
    with tempfile.TemporaryDirectory() as td:
        cpath = os.path.join(td, "out.c")
        binp = os.path.join(td, "out.bin")
        emit = subprocess.run([str(wrapper), str(case)], capture_output=True, text=True, timeout=120)
        if emit.returncode != 0:
            return f"emit failed for {rel}\n{(emit.stderr or '')[-1500:]}"
        Path(cpath).write_text(emit.stdout)
        try:
            compile_and_publish(cpath, binp)
        except BuildError as exc:
            return f"cc failed for {rel}\n{str(exc)[-1500:]}"
        got = subprocess.run([binp], capture_output=True).returncode
        if got != want:
            return f"{rel} exited {got}, expected {want}"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    sv0c = root / "sv0c"
    manifest = sv0c / "test" / "behavior" / "manifest.txt"
    if not manifest.is_file():
        print(f"verify_behavior_corpus_native: missing {manifest}", file=sys.stderr)
        return 1
    wrapper = root / "build" / "sv0-megatu-compiler-native"
    if not wrapper.is_file():
        subprocess.run(["bash", str(root / "scripts" / "build-sv0-megatu-native.sh")],
                       capture_output=True, text=True, check=False)
    if not wrapper.is_file():
        print("verify_behavior_corpus_native: native compiler build failed", file=sys.stderr)
        return 1
    # NEX-055c/REL-004 closure chunk 5: `wrapper` (migrated in chunk 4) now
    # passes argv[1] through via SV0_DRV_REQUEST internally, not the legacy
    # /tmp/.sv0_drv_path control file -- there is nothing to keep present here.
    rows: list[tuple[str, int]] = []
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            print(f"verify_behavior_corpus_native: bad line: {raw!r}", file=sys.stderr)
            return 1
        # Format: rel | exit [ | leg ]   leg in {both (default), native}.
        # The native C leg runs every row regardless of the leg tag.
        parts = [s.strip() for s in line.split("|")]
        rel, want_s = parts[0], parts[1]
        try:
            want = int(want_s)
        except ValueError:
            print(f"verify_behavior_corpus_native: bad exit {want_s!r} for {rel}", file=sys.stderr)
            return 1
        rows.append((rel, want))

    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=_job_count()) as pool:
        futures = {pool.submit(_run_one, sv0c, wrapper, rel, want): rel for rel, want in rows}
        for fut in futures:
            err = fut.result()
            if err is not None:
                failures.append(err)

    if failures:
        for err in failures:
            print(f"verify_behavior_corpus_native: {err}", file=sys.stderr)
        print(f"verify_behavior_corpus_native: {len(failures)} failure(s)", file=sys.stderr)
        return 1
    print(f"verify_behavior_corpus_native: OK ({len(rows)} program(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
