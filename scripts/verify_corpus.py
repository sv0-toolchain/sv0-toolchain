#!/usr/bin/env python3
"""M4-S-040: verification corpus gate.

Runs `./scripts/sv0 verify --json` over every `.sv0` under
`sv0c/test/verify/corpus/` and checks each contract's reported status against the
expected status annotated inline on the same source line:

    ensures(result >= 1)      //@ verified
    requires(x > 0)           //@ runtime

The `//@ <status>` annotation lives on the contract clause's line (it is a `//`
line comment, invisible to the compiler) and moves with the clause, so the corpus
is robust to reordering. Every contract must have an annotation and every
annotation must correspond to a contract (both directions checked), so a new
contract or a status regression fails the gate.

Statuses: `verified` (z3 proved the obligation `unsat`) or `runtime` (anything
else — precondition, counterexample, unknown, or outside the supported fragment;
always sound: only a solid unsat is `verified`).

Skips cleanly (exit 0) when `z3` is not on PATH — without a solver every ensures
degrades to `runtime`, so `verified` expectations can't hold. CI installs z3.
"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

CORPUS_REL = "sv0c/test/verify/corpus"
ANNOT_RE = re.compile(r"//@\s*(verified|runtime)\b")


def annotations(path: Path) -> dict[int, str]:
    """Map 1-based line number -> expected status for each `//@` annotation."""
    out: dict[int, str] = {}
    for i, line in enumerate(path.read_text().splitlines(), start=1):
        m = ANNOT_RE.search(line)
        if m:
            out[i] = m.group(1)
    return out


def check_file(root: Path, path: Path) -> tuple[int, int]:
    """Return (checked, failures) for one corpus file."""
    expected = annotations(path)
    proc = subprocess.run(
        ["bash", str(root / "scripts" / "sv0"), "verify", "--json", str(path)],
        capture_output=True, text=True, timeout=600,
    )
    rel = path.relative_to(root)
    if proc.returncode != 0:
        print(f"verify_corpus: {rel}: `sv0 verify` exit {proc.returncode}\n"
              f"{(proc.stdout + proc.stderr)[-1000:]}", file=sys.stderr)
        return (0, 1)
    try:
        doc = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as e:  # noqa: BLE001
        print(f"verify_corpus: {rel}: bad JSON: {e}\n{proc.stdout[-800:]}", file=sys.stderr)
        return (0, 1)

    contracts = doc.get("contracts", [])
    if not contracts:
        print(f"verify_corpus: {rel}: no contracts emitted", file=sys.stderr)
        return (0, 1)

    checked = 0
    failures = 0
    seen_lines: set[int] = set()
    for c in contracts:
        ln = c["line"]
        seen_lines.add(ln)
        want = expected.get(ln)
        if want is None:
            print(f"verify_corpus: {rel}:{ln}: {c['clause']} [{c['status']}] "
                  f"has no `//@` annotation", file=sys.stderr)
            failures += 1
            continue
        checked += 1
        if c["status"] != want:
            print(f"verify_corpus: {rel}:{ln}: {c['clause']} got [{c['status']}], "
                  f"want [{want}]", file=sys.stderr)
            failures += 1
    # every annotation must correspond to a contract
    for ln in sorted(set(expected) - seen_lines):
        print(f"verify_corpus: {rel}:{ln}: `//@ {expected[ln]}` annotation has no contract",
              file=sys.stderr)
        failures += 1
    return (checked, failures)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()

    corpus = root / CORPUS_REL
    files = sorted(corpus.glob("*.sv0")) if corpus.is_dir() else []
    if not files:
        print(f"verify_corpus: no corpus files under {CORPUS_REL}; skipped", file=sys.stderr)
        return 0

    if shutil.which("z3") is None:
        print("verify_corpus: SKIP (z3 not on PATH)", file=sys.stderr)
        return 0

    total_checked = 0
    total_failures = 0
    for f in files:
        checked, failures = check_file(root, f)
        total_checked += checked
        total_failures += failures

    if total_failures:
        print(f"verify_corpus: {total_failures} failure(s) across {len(files)} file(s)",
              file=sys.stderr)
        return 1
    print(f"verify_corpus: OK ({total_checked} contract(s) match expected status "
          f"across {len(files)} file(s))", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
