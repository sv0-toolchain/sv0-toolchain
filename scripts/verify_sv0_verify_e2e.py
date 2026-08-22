#!/usr/bin/env python3
"""M4-S-020/021: end-to-end `./scripts/sv0 verify <file>` acceptance.

Drives the full P0 verification path on a real .sv0 file: the native verify
binary tokenizes + parses the source, extracts each contract clause into the
CExpr IR, generates the SMT-LIB2 obligation for every `ensures`, and the shell
driver runs each query through z3, reporting per-contract status in the
sv0doc/contracts/semantics.md §3.2 shape:

    <file>:<line>  <clause>  [verified|runtime]  -- <reason>

Asserts, for sv0c/test/verify/basic.sv0:
  - ensures(result >= 1)   → [verified] (x>0 ⟹ result>=1, return x)
  - ensures(result >= 100) → [runtime]  (not provable — sound residual)
  - ensures(result > 0)    → [verified] (a>0 ∧ b>0 ⟹ result>0, return a+b)
  - every requires(...)     → [runtime]  (input precondition, assumed locally)
  - summary line: "2 verified, 5 runtime"

Skips cleanly (exit 0) when `z3` is not on PATH — without a solver every ensures
degrades to [runtime], so the [verified] assertions can't hold. CI installs z3, so
this runs there. Building the native verify binary is a one-time SML→C→cc
bootstrap driven by `./scripts/sv0 verify` itself.
"""
from __future__ import annotations
import argparse, json, re, shutil, subprocess, sys
from pathlib import Path

FIXTURE = "sv0c/test/verify/basic.sv0"
EXPECT_ENSURES = {
    "ensures(result >= 1)": "verified",
    "ensures(result >= 100)": "runtime",
    "ensures(result > 0)": "verified",
}
EXPECT_SUMMARY = (2, 5)  # (verified, runtime)

LINE_RE = re.compile(r"^\S+:\d+\s+(.*?)\s+\[(verified|runtime)\]\s+--\s+(.*)$")
SUMMARY_RE = re.compile(r"—\s*(\d+)\s*verified,\s*(\d+)\s*runtime")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent)
    args = ap.parse_args(argv)
    root: Path = args.root.resolve()

    fixture = root / FIXTURE
    if not fixture.is_file():
        print(f"verify_sv0_verify_e2e: missing fixture {fixture}", file=sys.stderr)
        return 1

    if shutil.which("z3") is None:
        print("verify_sv0_verify_e2e: SKIP (z3 not on PATH)", file=sys.stderr)
        return 0

    proc = subprocess.run(
        ["bash", str(root / "scripts" / "sv0"), "verify", str(fixture)],
        capture_output=True, text=True, timeout=600,
    )
    out = proc.stdout + proc.stderr
    if proc.returncode != 0:
        print(f"verify_sv0_verify_e2e: `sv0 verify` exit {proc.returncode}\n{out[-1500:]}",
              file=sys.stderr)
        return 1

    rows: list[tuple[str, str]] = []       # (clause, status)
    summary: tuple[int, int] | None = None
    for ln in out.splitlines():
        m = LINE_RE.match(ln)
        if m:
            rows.append((m.group(1).strip(), m.group(2)))
        ms = SUMMARY_RE.search(ln)
        if ms:
            summary = (int(ms.group(1)), int(ms.group(2)))

    by_clause = dict(rows)
    failures = 0
    for clause, want in EXPECT_ENSURES.items():
        if by_clause.get(clause) != want:
            print(f"verify_sv0_verify_e2e: {clause!r} got [{by_clause.get(clause)}], want [{want}]",
                  file=sys.stderr)
            failures += 1
    # every requires clause must be [runtime] (input precondition)
    for clause, status in rows:
        if clause.startswith("requires(") and status != "runtime":
            print(f"verify_sv0_verify_e2e: {clause!r} got [{status}], want [runtime]",
                  file=sys.stderr)
            failures += 1
    if summary != EXPECT_SUMMARY:
        print(f"verify_sv0_verify_e2e: summary got {summary}, want {EXPECT_SUMMARY}",
              file=sys.stderr)
        failures += 1

    # M4-S-022: --json output must parse and agree with the text report.
    jproc = subprocess.run(
        ["bash", str(root / "scripts" / "sv0"), "verify", "--json", str(fixture)],
        capture_output=True, text=True, timeout=600,
    )
    if jproc.returncode != 0:
        print(f"verify_sv0_verify_e2e: `sv0 verify --json` exit {jproc.returncode}\n"
              f"{(jproc.stdout + jproc.stderr)[-1500:]}", file=sys.stderr)
        failures += 1
    else:
        try:
            doc = json.loads(jproc.stdout.strip().splitlines()[-1])
        except Exception as e:  # noqa: BLE001
            print(f"verify_sv0_verify_e2e: --json not valid JSON: {e}\n{jproc.stdout[-800:]}",
                  file=sys.stderr)
            doc = None
            failures += 1
        if doc is not None:
            jby = {c["clause"]: c["status"] for c in doc.get("contracts", [])}
            for clause, want in EXPECT_ENSURES.items():
                if jby.get(clause) != want:
                    print(f"verify_sv0_verify_e2e: --json {clause!r} got [{jby.get(clause)}], want [{want}]",
                          file=sys.stderr)
                    failures += 1
            jsum = (doc.get("summary", {}).get("verified"), doc.get("summary", {}).get("runtime"))
            if jsum != EXPECT_SUMMARY:
                print(f"verify_sv0_verify_e2e: --json summary got {jsum}, want {EXPECT_SUMMARY}",
                      file=sys.stderr)
                failures += 1

    if failures:
        print(f"verify_sv0_verify_e2e: {failures} failure(s)\n--- output ---\n{out}",
              file=sys.stderr)
        return 1
    print("verify_sv0_verify_e2e: OK (§3.2 report + --json; 2 ensures proven, 1 sound residual, "
          "requires as preconditions)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
