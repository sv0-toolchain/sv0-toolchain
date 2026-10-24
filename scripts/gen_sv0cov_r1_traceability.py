#!/usr/bin/env python3
"""Generate task/sv0cov-r1-traceability.md (sv0cov CV-417): every R1-phase
requirement and every acceptance criterion of the sv0cov SPEC, mapped to the
checklist slices that cite them, with hand overrides for the rest.

    python3 scripts/gen_sv0cov_r1_traceability.py [--spec PATH]

The SPEC lives outside this repository (default
~/Documents/project-specs/sv0cov/SPEC.md), so this is a maintainer tool, not
a guard. Rerun it whenever a slice's status or citations change; it fails
if any item is left unmapped.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "task" / "sv0cov-r1-traceability.md"


def collect(spec_lines: list[str]) -> dict:
    rows = {}
    for line in open(ROOT / "task" / "sv0cov-checklist.Rmd"):
        m = re.match(r"\| (CV-\d+[a-z]?) \|", line)
        if m:
            cells = [c.strip() for c in line.split("|")]
            status = cells[6] if len(cells) > 6 else ""
            rows[m.group(1)] = (status, line)
    def expand(text):
        out = set()
        for m in re.finditer(r"(COV-[A-Z]+|AC)-(\d{3})((?:\s*(?:\.\.|/)\s*\d{3})*)", text):
            pre, first, rest = m.group(1), int(m.group(2)), m.group(3)
            nums = [first]; prev = first
            for op, n in re.findall(r"(\.\.|/)\s*(\d{3})", rest):
                n = int(n)
                if op == "..": nums += list(range(prev + 1, n + 1))
                else: nums.append(n)
                prev = n
            out |= {f"{pre}-{n:03d}" for n in nums}
        # AC ranges like AC-045..049 handled above; also "AC-016" plain
        return out
    cites = {}
    for cv, (status, line) in rows.items():
        for ident in expand(line):
            cites.setdefault(ident, []).append((cv, status))
    reqs = [re.match(r"\| (COV-[A-Z]+-\d+) \| R1 \| (.*?) \|", l) for l in spec_lines if re.match(r"\| COV-[A-Z]+-\d+ \| R1 \|", l)]
    acs = [l[4:].strip() for l in spec_lines if l.startswith("### AC-")]
    res = {"req": [], "ac": []}
    for m in reqs:
        rid, text = m.group(1), m.group(2)
        res["req"].append({"id": rid, "text": text, "cites": cites.get(rid, [])})
    for a in acs:
        aid, title = a.split(":",1)
        res["ac"].append({"id": aid, "text": title.strip(), "cites": cites.get(aid, [])})
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=str(Path.home() / "Documents" / "project-specs" / "sv0cov" / "SPEC.md"))
    args = ap.parse_args()
    r = collect(Path(args.spec).read_text().splitlines())
    isdone = lambda st: st.lower().lstrip("*").startswith("done")
    M = {  # mismatches for the owner
     "M1": "COV-REP-017 says the report has twenty-two top-level members; it has 24 since CV-312 (`changes`) and CV-313 (`ratchet`).",
     "M2": "COV-SCP-009 names Python *and sv0* scope matchers; the sv0 implementation is post-R1 (CV-902). Through R1 only the Python matcher can exist.",
     "M3": "COV-MET-007 asks for proof provenance on proven-impossible outcomes; no schema has a provenance field (the `statically_unreachable` status is all a record carries). Amend, or add a field before the CV-412 freeze.",
     "M4": "AC-073 says only dedicated-host evidence can pass R1 performance; DEC-087 (§24.1) admits `managed-ci-recorded` campaigns with exception records, the path chosen in CV-315.",
     "M5": "AC-133 requires a distinct human approver; DEC-087 admits single-maintainer approval under compensating controls (COV-PKG-025).",
     "M6": "§20.1 lists seven commands and §20.1.1 exactly seven root subcommands; `sv0cov baseline` (CV-313) exists unadvertised (CV-421).",
     "M7": "§20.1 lets `check` take a native report; §16.5 says the indexed profile is the only `check` input. D-10 chose native reports in R1 (CV-416).",
     "M8": "§21.5 requires a reserved root-package spelling for sources without a package but does not give it; CV-402 uses `(root)` (owner decision).",
    }
    ROVR = {  # requirement overrides: (status, evidence, owner, note)
     "COV-GOV-008": ("partly met", "CV-009 (append-only registry), CV-417 (IDs kept at the R1 re-slice)", "CV-412", "format identifiers at the freeze"),
     "COV-REL-003": ("owned", "", "CV-415", "evidence manifest"),
     "COV-SCP-004": ("met", "CV-209, CV-417 (B12: dependency units no longer reach the project)", "", ""),
     "COV-REP-004": ("met", "CV-401 (functions, lines, branches), CV-403 (loss manifest)", "", ""),
     "COV-REP-010": ("met", "CV-401 (LCOV), CV-402 (Cobertura)", "", ""),
     "COV-FMT-037": ("partly met", "CV-403 (schema, goldens, negatives, mutation)", "CV-412", "cross-language reader parity"),
     "COV-REP-005": ("met", "CV-402 (pinned-DTD validation; docs/cobertura.md), CV-403 (loss manifest)", "", ""),
     "COV-REP-011": ("met", "CV-402 (vendored digest-pinned DTD, offline stdlib validator)", "", ""),
     "COV-REP-012": ("met", "CV-402 (writer never emits them; reader refuses them)", "", ""),
     "COV-MAP-010": ("met", "CV-229, CV-231", "", "COV1004 unless `--allow-source-mismatch`"),
     "COV-MET-007": ("mismatch", "CV-201, CV-203", "owner", "M3"),
     "COV-MET-013": ("met", "CV-228 (closed schemas: five metrics only)", "", "by construction"),
     "COV-INS-011": ("partly met", "CV-207, CV-171 (VM counts and saturation equal C)", "CV-407", ""),
     "COV-FMT-024": ("partly met", "CV-224, CV-228 (resolved tier in the report)", "CV-415", "release evidence"),
     "COV-EXC-018": ("met", "CV-304, CV-305", "", ""),
     "COV-CLI-005": ("met", "CV-009, CV-225", "", ""),
     "COV-POL-006": ("met", "CV-231", "", ""),
     "COV-POL-021": ("met", "CV-312", "", "`clean`; terminal/HTML say dirty is not reproducible from HEAD"),
     "COV-POL-024": ("met", "CV-229, CV-230, CV-309, CV-310", "", ""),
     "COV-PERF-025": ("conditional", "CV-315 plan", "CV-428", "only if a dedicated host appears"),
     "COV-PERF-026": ("conditional", "CV-315 plan", "CV-428", "only if a dedicated host appears"),
     "COV-RW-001": ("partly met", "CV-011 (language-neutral schemas)", "CV-412", "cross-reader parity at the freeze"),
     "COV-EXC-006": ("partly met", "CV-305 (C and VM v1)", "CV-407", "v2"),
     "COV-EXC-011": ("partly met", "CV-305 (C and VM v1)", "CV-407", "v2"),
     "COV-CLI-010": ("partly met", "CV-021, CV-316 (pre-R1 subsets)", "CV-415", "exact R1 inventories at 1.0.0"),
     "COV-CLI-012": ("partly met", "CV-241", "CV-421, CV-430", "M6"),
     "COV-REP-017": ("mismatch", "CV-228, CV-312, CV-313", "owner", "M1"),
     "COV-SCP-009": ("mismatch", "CV-030, CV-310 (Python matcher)", "owner", "M2"),
    }
    AOVR = {
     "AC-003": ("met", "CV-209, CV-417 (B12 fixed; `tests/test_default_scope.py`)", "", ""),
     "AC-004": ("met", "CV-113, CV-205 (maps name only sv0 sources)", "", "by construction"),
     "AC-005": ("met", "CV-229, CV-231", "", ""),
     "AC-008": ("met", "CV-202, CV-230", "", ""),
     "AC-009": ("met", "CV-109", "", ""),
     "AC-023": ("met", "CV-111", "", ""),
     "AC-026": ("met", "CV-119", "", ""),
     "AC-029": ("met", "CV-117, CV-119", "", ""),
     "AC-030": ("met", "CV-102", "", ""),
     "AC-033": ("post-R1", "", "CV-904", ""),
     "AC-039": ("met", "CV-113", "", ""),
     "AC-051": ("partly met", "CV-402 (determinism, timestamp 0, offline DTD, no DOCTYPE/PI/extension/host path)", "CV-419", "GitLab smoke"),
     "AC-053": ("met", "CV-401, CV-402 (core profiles only), CV-403 (extended profile names refused before reading, pointing to native JSON)", "", ""),
     "AC-055": ("met", "CV-211, CV-224", "", ""),
     "AC-059": ("met", "CV-024, CV-025", "", ""),
     "AC-060": ("met", "CV-024, CV-025, CV-115", "", ""),
     "AC-062": ("owned", "", "CV-410", ""),
     "AC-063": ("owned", "", "CV-428", ""),
     "AC-064": ("partly met", "CV-035 (frozen protocol)", "CV-410", ""),
     "AC-065": ("owned", "", "CV-410", ""),
     "AC-066": ("partly met", "CV-036", "CV-427", ""),
     "AC-067": ("owned", "", "CV-410, CV-427", ""),
     "AC-068": ("owned", "", "CV-427", ""),
     "AC-069": ("owned", "", "CV-427", ""),
     "AC-070": ("met", "CV-037", "", ""),
     "AC-071": ("met", "CV-037, CV-315", "", ""),
     "AC-072": ("conditional", "CV-315 plan", "CV-428", "only if a dedicated host appears"),
     "AC-073": ("mismatch", "", "owner", "M4"),
     "AC-074": ("partly met", "CV-001, CV-034", "CV-411", ""),
     "AC-075": ("partly met", "CV-001, CV-034", "CV-411", ""),
     "AC-076": ("owned", "", "CV-411", ""),
     "AC-077": ("owned", "", "CV-411", ""),
     "AC-078": ("partly met", "CV-243 (dry run)", "CV-413", ""),
     "AC-079": ("partly met", "CV-243", "CV-426", ""),
     "AC-080": ("partly met", "CV-005, CV-243", "CV-413", ""),
     "AC-081": ("owned", "", "CV-414", ""),
     "AC-082": ("owned", "", "CV-413", ""),
     "AC-083": ("owned", "", "CV-428", ""), "AC-084": ("owned", "", "CV-428", ""), "AC-085": ("owned", "", "CV-428", ""),
     "AC-086": ("owned", "", "CV-428", ""), "AC-088": ("owned", "", "CV-428", ""),
     "AC-087": ("partly met", "CV-111, CV-223", "CV-428", ""),
     "AC-099": ("met", "CV-310", "", ""),
     "AC-107": ("met", "CV-306, CV-310", "", ""),
     "AC-116": ("met", "CV-002", "", ""),
     "AC-119": ("met", "CV-240, CV-241", "", ""),
     "AC-126": ("met", "CV-005", "", ""), "AC-127": ("met", "CV-005", "", ""),
     "AC-128": ("partly met", "CV-004, CV-243", "CV-413", ""),
     "AC-129": ("partly met", "CV-004, CV-034", "CV-413", ""),
     "AC-130": ("partly met", "CV-034", "CV-413", ""),
     "AC-131": ("owned", "", "CV-411, CV-413", ""), "AC-132": ("owned", "", "CV-411, CV-413", ""),
     "AC-133": ("mismatch", "", "owner, CV-413", "M5"),
     "AC-134": ("owned", "", "CV-413", ""), "AC-135": ("owned", "", "CV-413, CV-415", ""),
    }
    def auto(item):
        d = sorted({c for c, s in item["cites"] if isdone(s)}); o = sorted({c for c, s in item["cites"] if not isdone(s)} - {"CV-417"})
        if d and o: return ("partly met", ", ".join(d), ", ".join(o), "")
        if d: return ("met", ", ".join(d), "", "")
        if o: return ("owned", "", ", ".join(o), "")
        return ("UNMAPPED", "", "", "")
    out = []
    counts = {}
    def table(items, ovr, head):
        out.append(f"| {head} | text | status | evidence | owner | note |\n|---|---|---|---|---|---|")
        for i in items:
            st, ev, ow, note = ovr.get(i["id"]) or auto(i)
            counts.setdefault(head, {}).setdefault(st, 0); counts[head][st] += 1
            text = i["text"].replace("|", "\\|")
            text = text if len(text) <= 110 else text[:107].rstrip() + "..."
            out.append(f"| {i['id']} | {text} | {st} | {ev} | {ow} | {note} |")
        out.append("")
    table(r["req"], ROVR, "requirement"); body_req = "\n".join(out); out.clear()
    table(r["ac"], AOVR, "criterion"); body_ac = "\n".join(out)
    summ = "\n".join(f"- **{ {"requirement": "requirements", "criterion": "acceptance criteria"}[k] }:** " + ", ".join(f"{n} {s}" for s, n in sorted(v.items())) for k, v in counts.items())
    mis = "\n".join(f"- **{k}.** {v}" for k, v in M.items())
    doc = f"""---
    title: "sv0cov R1 traceability (CV-417)"
    ---

    # sv0cov R1 traceability (CV-417, 2026-10-24)

    Every SPEC requirement whose phase is R1 (138) and every acceptance
    criterion (135), mapped to the evidence that already meets it (done
    checklist slices) and to the R1 slice that owns what remains. Generated from
    the SPEC (`project-specs/sv0cov/SPEC.md`) and `task/sv0cov-checklist.Rmd`
    citations, with the uncited items mapped by hand. Statuses:

    - **met**: done slices carry the evidence;
    - **partly met**: done slices meet part of it, the owner completes it;
    - **owned**: an open R1 slice owns all of it;
    - **conditional**: applies only on the dedicated-host path (CV-315 plan);
    - **post-R1**: owned by a post-R1 slice;
    - **mismatch**: the SPEC and the implementation or an accepted decision
      disagree; listed for an owner amendment (below).

    No item is unmapped. R1 still re-verifies every "met" item at the gate review
    (CV-415) against the final revision.

    ## Summary

    {summ}

    ## SPEC mismatches for owner amendment

    {mis}

    ## Requirements (phase R1)

    {body_req}
    ## Acceptance criteria

    {body_ac}"""
    # The template sits inside this function, so its own lines carry four spaces of indentation.
    doc = "\n".join(line[4:] if line.startswith("    ") else line for line in doc.split("\n"))
    OUT.write_text(doc)
    print(counts)
    if "UNMAPPED" in doc:
        sys.exit("unmapped items: map them in ROVR/AOVR or cite them in the checklist")
    return 0


if __name__ == "__main__":
    sys.exit(main())
