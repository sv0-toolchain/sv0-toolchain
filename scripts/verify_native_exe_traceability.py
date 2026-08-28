#!/usr/bin/env python3
"""Verify requirement traceability for the sv0c native runtime executable spec (NEX-001).

Every normative requirement in ``scripts/native_exe_requirements.json`` (transcribed
from ``~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`` §23/§24) must be
cited by at least one ``NEX-###`` slice row's requirement column in
``task/sv0c-runtime-executable-checklist.Rmd`` before that requirement's release
becomes active. This is the GOV-005/TEST-001 traceability rule made mechanical:
"every requirement in the active release SHALL map to at least one test or
approved manual evidence record" — here, a mapped slice stands in for evidence
until that slice lands with its own real tests.

The active release is F0 until the hub (``task/sv0c-runtime-executable.Rmd``)
records that a later release has opened; pass ``--active-release`` to check a
later gate explicitly. Requirements above the active release are reported but
do not fail the run.

``extract_cited_ids`` only counts a requirement id as cited when it appears in
one of two structurally-trusted locations: a ``### NEX-### — <ids>: <title>``
section header's id list, or a table row's own dedicated ``requirement(s)``
column (present on the checklist's F0/R0/R0.1 tables; the R1-band tables
instead rely on the section-header convention). It deliberately does NOT scan
a row's free-text "slice"/"status"/"red test" cells: a real, observed failure
mode (NEX-059/060, 2026-08-27) is that honest prose disclosing a requirement
as *explicitly not covered* mentions that requirement's id, which a naive
"cited anywhere in the file" scan then counted as a real citation --
silently hiding real gaps behind the guard's own green output. Restricting
extraction to these two trusted locations makes that impossible: a citation
now has to be a deliberate act (writing the id into a header or the
requirement(s) column), never an accidental byproduct of writing about it.

Run ``python3 scripts/verify_native_exe_traceability.py --selftest`` to exercise
the pass/fail behavior against a synthetic unmapped requirement without touching
the real checklist file.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

RELEASES_ORDERED = ["F0", "R0", "R0.1", "R1"]

# Matches a requirement id, optionally followed by an ellipsis-style range end
# such as ``GOV-001…005`` (the exact separator the checklist uses) or the
# plainer ``GOV-001-005``/``GOV-001..005`` spellings, for robustness.
_ID_RANGE_RE = re.compile(r"\b([A-Z]{2,6})-(\d{3})(?:(?:…|\.\.|-)(\d{3}))?\b")

# ``### NEX-059 — CLI-007/008/010…013/017: title`` / ``#### NEX-048 — TOOL-012: title``
# -- the id list sits between the em dash and the first colon.
_SECTION_HEADER_RE = re.compile(r"^#{2,6}\s+NEX-\S+\s+—\s+(.+?):")

_NON_REQUIREMENT_PREFIXES = {"NEX", "AC", "OD"}


def _release_rank(release: str) -> int:
    return RELEASES_ORDERED.index(release)


def load_catalog(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data["requirements"])


def _ids_in(text: str) -> set[str]:
    ids: set[str] = set()
    for m in _ID_RANGE_RE.finditer(text):
        prefix, start, end = m.groups()
        if prefix in _NON_REQUIREMENT_PREFIXES:
            continue  # slice/acceptance/open-decision ids, not spec requirement ids
        lo = int(start)
        hi = int(end) if end else lo
        if hi < lo or hi - lo > 200:
            continue  # not a plausible range; treat as a single id instead
        for n in range(lo, hi + 1):
            ids.add(f"{prefix}-{n:03d}")
    return ids


def _is_table_row(line: str) -> bool:
    s = line.strip()
    return len(s) > 1 and s.startswith("|") and s.endswith("|")


def _is_separator_row(line: str) -> bool:
    s = line.strip()
    if not _is_table_row(s):
        return False
    inner = s[1:-1]
    return bool(inner) and "-" in inner and all(c in "-:| \t" for c in inner)


def _split_row(line: str) -> list[str]:
    s = line.strip()
    inner = s[1:-1]
    return [c.strip() for c in inner.split("|")]


def extract_cited_ids(checklist_text: str) -> set[str]:
    """Return every requirement id genuinely cited in the checklist.

    Only two locations count: a ``### NEX-### — <ids>: <title>`` section
    header's id list, and a table row's own dedicated ``requirement(s)``
    column (when the enclosing table has one). A row's free-text "slice",
    "status", and "red test / acceptance" cells are never scanned -- see
    this module's own docstring for why that matters.
    """
    cited: set[str] = set()
    lines = checklist_text.splitlines()

    in_table = False
    req_col_idx: int | None = None
    i = 0
    while i < len(lines):
        line = lines[i]

        header_match = _SECTION_HEADER_RE.match(line.strip())
        if header_match:
            cited |= _ids_in(header_match.group(1))
            in_table = False
            req_col_idx = None
            i += 1
            continue

        if _is_table_row(line) and i + 1 < len(lines) and _is_separator_row(lines[i + 1]):
            header_cells = _split_row(line)
            req_col_idx = next(
                (idx for idx, cell in enumerate(header_cells) if cell.lower().startswith("requirement")),
                None,
            )
            in_table = True
            i += 2  # skip the header row and its separator row
            continue

        if in_table and _is_table_row(line):
            if req_col_idx is not None:
                cells = _split_row(line)
                if req_col_idx < len(cells):
                    cited |= _ids_in(cells[req_col_idx])
            i += 1
            continue

        if in_table:
            # A blank line or any non-row line ends the current table.
            in_table = False
            req_col_idx = None
        i += 1

    return cited


def check(
    catalog: dict[str, str], cited: set[str], active_release: str
) -> tuple[list[str], list[str]]:
    """Return (blocking_missing, informational_missing)."""
    active_rank = _release_rank(active_release)
    blocking: list[str] = []
    informational: list[str] = []
    for req_id, release in sorted(catalog.items()):
        if req_id in cited:
            continue
        if _release_rank(release) <= active_rank:
            blocking.append(req_id)
        else:
            informational.append(req_id)
    return blocking, informational


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Toolchain root (default: parent of scripts/)",
    )
    ap.add_argument(
        "--active-release",
        default="F0",
        choices=RELEASES_ORDERED,
        help="Highest release whose requirements must be cited (default: F0)",
    )
    ap.add_argument("--selftest", action="store_true", help="Run the built-in accept/reject cases")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    root: Path = args.root.resolve()
    catalog_path = root / "scripts" / "native_exe_requirements.json"
    checklist_path = root / "task" / "sv0c-runtime-executable-checklist.Rmd"

    if not catalog_path.is_file():
        print(f"verify_native_exe_traceability: missing {catalog_path}", file=sys.stderr)
        return 1
    if not checklist_path.is_file():
        print(f"verify_native_exe_traceability: missing {checklist_path}", file=sys.stderr)
        return 1

    catalog = load_catalog(catalog_path)
    cited = extract_cited_ids(checklist_path.read_text(encoding="utf-8"))
    blocking, informational = check(catalog, cited, args.active_release)

    if informational:
        print(
            f"verify_native_exe_traceability: {len(informational)} requirement(s) "
            f"above active release {args.active_release} not yet cited (informational): "
            + ", ".join(informational)
        )

    if blocking:
        print(
            f"verify_native_exe_traceability: {len(blocking)} active-release "
            f"({args.active_release}) requirement(s) not cited by any NEX-### slice:",
            file=sys.stderr,
        )
        for req_id in blocking:
            print(f"  {req_id} (release {catalog[req_id]})", file=sys.stderr)
        return 1

    print(
        f"verify_native_exe_traceability: OK ({len(catalog)} requirement(s), "
        f"active release {args.active_release}, 0 blocking gaps)"
    )
    return 0


def _selftest() -> int:
    catalog = {"GOV-001": "F0", "GOV-002": "F0", "RT-004": "R0"}

    # Case 1: everything active-release is cited -> no blocking gaps.
    cited_ok = {"GOV-001", "GOV-002"}
    blocking, informational = check(catalog, cited_ok, "F0")
    assert blocking == [], f"expected no blocking gaps, got {blocking}"
    assert informational == ["RT-004"], f"expected RT-004 informational, got {informational}"

    # Case 2: an active-release requirement is missing -> blocking gap (the red test).
    cited_gap = {"GOV-001"}
    blocking, informational = check(catalog, cited_gap, "F0")
    assert blocking == ["GOV-002"], f"expected GOV-002 to block, got {blocking}"

    # Case 3: raising the active release surfaces the R0 item too.
    blocking, informational = check(catalog, cited_gap, "R0")
    assert blocking == ["GOV-002", "RT-004"], f"expected both to block, got {blocking}"

    # Case 4: range expansion — "GOV-001…002" cites both ids from a real
    # requirement(s) column, inside a real header+separator+row table.
    text = (
        "| ID | slice | requirement(s) | status | red test / acceptance |\n"
        "|----|-------|-----------------|--------|------------------------|\n"
        "| NEX-001 | slice | GOV-001…002 | todo | acceptance |\n"
    )
    assert extract_cited_ids(text) == {"GOV-001", "GOV-002"}

    # Case 5: NEX-###, AC-###, and OD-### ids in the requirement(s) column are
    # never mistaken for spec requirement ids.
    text2 = (
        "| ID | slice | requirement(s) | status | red test / acceptance |\n"
        "|----|-------|-----------------|--------|------------------------|\n"
        "| NEX-013 | slice | ENTRY-001, ENTRY-004 | todo | AC-004, see OD-003 |\n"
    )
    assert extract_cited_ids(text2) == {"ENTRY-001", "ENTRY-004"}

    # Case 6 (the red test for the real bug this module's docstring
    # describes): a requirement id mentioned only in the "red test /
    # acceptance" prose column -- e.g. an honest disclosure that a
    # requirement is explicitly NOT covered -- must NOT be counted as
    # cited, even though the real requirement(s) column citation for a
    # DIFFERENT id on the same row is.
    text3 = (
        "| ID | slice | requirement(s) | status | red test / acceptance |\n"
        "|----|-------|-----------------|--------|------------------------|\n"
        "| NEX-002 | slice | GOV-003 | todo | note: ENTRY-001 and ENTRY-004 are explicitly NOT covered by this slice |\n"
    )
    assert extract_cited_ids(text3) == {"GOV-003"}, extract_cited_ids(text3)

    # Case 7: a 4-column table (no requirement(s) column at all -- the
    # R1-band convention) cites nothing from its rows; only the section
    # header's own id list counts. A disclosure sentence inside a row's
    # trailing cell must not leak a citation just because the table has no
    # dedicated column to protect against it.
    text4 = (
        "### NEX-048 — TOOL-012: some title\n\n"
        "| ID | slice | status | red test / acceptance |\n"
        "|----|-------|--------|------------------------|\n"
        "| NEX-048a | mentions TOOL-012 again, and notes PIPE-099 is NOT covered | done | evidence |\n"
    )
    assert extract_cited_ids(text4) == {"TOOL-012"}, extract_cited_ids(text4)

    print("verify_native_exe_traceability: selftest OK (7 cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
