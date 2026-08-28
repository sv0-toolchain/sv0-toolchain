#!/usr/bin/env python3
"""Behavioral PASS corpus: compile each program with the native mega-TU compiler,
cc it, run it, and assert the process exit code matches the manifest.

Manifest: sv0c/test/behavior/manifest.txt, one row per line:  rel | expected_exit
Run by `./scripts/sv0 test`. Complements the diagnostics (reject) corpus.
"""
from __future__ import annotations
import argparse, os, subprocess, sys, tempfile
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()
    sv0c = root / "sv0c"
    rt = sv0c / "runtime"
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
    n = 0
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
        case = sv0c / rel
        if not case.is_file():
            print(f"verify_behavior_corpus_native: missing case {case}", file=sys.stderr)
            return 1
        with tempfile.TemporaryDirectory() as td:
            cpath = os.path.join(td, "out.c")
            binp = os.path.join(td, "out.bin")
            emit = subprocess.run([str(wrapper), str(case)], capture_output=True, text=True, timeout=120)
            if emit.returncode != 0:
                print(f"verify_behavior_corpus_native: emit failed for {rel}", file=sys.stderr)
                print((emit.stderr or "")[-1500:], file=sys.stderr)
                return 1
            Path(cpath).write_text(emit.stdout)
            cc = subprocess.run(
                ["cc", "-std=c99", "-O0", "-w", "-I", str(rt), cpath, str(rt / "sv0_runtime.c"), "-o", binp],
                capture_output=True, text=True,
            )
            if cc.returncode != 0:
                print(f"verify_behavior_corpus_native: cc failed for {rel}", file=sys.stderr)
                print((cc.stderr or "")[-1500:], file=sys.stderr)
                return 1
            got = subprocess.run([binp], capture_output=True).returncode
            if got != want:
                print(f"verify_behavior_corpus_native: {rel} exited {got}, expected {want}", file=sys.stderr)
                return 1
        n += 1
    print(f"verify_behavior_corpus_native: OK ({n} program(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
