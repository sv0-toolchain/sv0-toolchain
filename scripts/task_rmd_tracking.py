#!/usr/bin/env python3
"""Parse optional ``<!-- sv0-track: ... -->`` anchors and markdown checklists in task/*.Rmd bodies.

Human-edited prose stays authoritative. Anchors are *optional* machine-stable hooks for dashboards,
graph sync, and future tooling. This module is intentionally conservative: malformed anchors are
errors; unknown JSON keys produce warnings (strict mode can promote them to errors).

See ``.cursor/rules/10-rmd-agent-documents.mdc`` for authoring rules.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

# Stable ids: dotted paths, META- style tags, semver-ish tokens — no raw whitespace.
RE_TRACK_ID = re.compile(r"^[-a-zA-Z0-9_.:]+$")

ALLOWED_JSON_KEYS = frozenset(
    {
        "id",
        "title",
        "kind",
        "milestone",
        "refs",
        "ingest",
        "role",
        "done",
    }
)

# GFM task list item, optional inline trailing ``<!-- sv0-track: {...} -->``.
RE_TASK_LINE = re.compile(
    r"^(?P<prefix>(?P<indent>[ \t]*)(?P<bullet>[-*+]|\d+\.)\s+\[(?P<box>[ xX])\]\s+)(?P<mid>.*?)$"
)

# Single-line HTML comment only (``<!-- sv0-track: ... -->`` must not span lines).
RE_TRACK_LINE = re.compile(r"^\s*<!--\s*sv0-track:(?P<body>.*?)\s*-->\s*$")


@dataclass
class TrackAnchor:
    """One ``sv0-track`` directive after front matter."""

    line: int
    form: Literal["standalone", "begin", "end"]
    payload: dict[str, Any]


@dataclass
class ChecklistItem:
    """A GFM ``- [ ]`` / ``* [x]`` line with resolved track ids."""

    line: int
    done: bool
    text: str
    track_ids: list[str]
    source: Literal["region", "prev_line", "inline"]


@dataclass
class ParseResult:
    """Structured extraction for one ``.Rmd`` file."""

    path: str
    anchors: list[TrackAnchor] = field(default_factory=list)
    checklist_items: list[ChecklistItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def split_front_matter(text: str) -> tuple[str | None, str, int]:
    """Return (front_matter_block_without_delimiters, body, body_start_line_1_indexed).

    If no closing ``---``, body is full text and fm is None.
    """
    if not text.startswith("---\n"):
        return None, text, 1
    end = text.find("\n---\n", 4)
    if end == -1:
        return None, text, 1
    fm = text[4:end]
    body = text[end + 5 :]
    fm_lines = fm.count("\n") + 2
    return fm, body, fm_lines + 1


def _parse_json_object(
    raw: str, *, path: str, line: int, ctx: str
) -> dict[str, Any] | None:
    raw = raw.strip()
    if not raw:
        return None
    if "-->" in raw:
        return None  # caller surfaces error
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return obj


def _json_error_detail(raw: str, path: str, line: int, ctx: str) -> str:
    raw = raw.strip()
    if "-->" in raw:
        return f"{path}:{line}: {ctx}: JSON must not contain the literal sequence `-->` (HTML comment terminator)"
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        return f"{path}:{line}: {ctx}: invalid JSON ({e.msg})"
    if not isinstance(obj, dict):
        return f"{path}:{line}: {ctx}: JSON must be an object {{...}}"
    # json.loads produced an object — callers only append this string when parse failed
    return f"{path}:{line}: {ctx}: internal error (expected JSON failure detail)"


def _validate_payload_keys(
    obj: dict[str, Any], *, path: str, line: int, result: ParseResult
) -> None:
    unknown = sorted(set(obj.keys()) - ALLOWED_JSON_KEYS)
    for k in unknown:
        result.warnings.append(
            f"{path}:{line}: unknown JSON key {k!r} (ignored for validation)"
        )


def _validate_semantic_fields(
    obj: dict[str, Any], *, path: str, line: int, result: ParseResult
) -> None:
    """Validate well-known keys beyond JSON typing (errors for inconsistent task files)."""
    ing = obj.get("ingest")
    if ing is not None and ing not in ("gfm", "numbered", "both"):
        result.errors.append(
            f"{path}:{line}: ingest must be one of 'gfm', 'numbered', 'both' (got {ing!r})"
        )
    done = obj.get("done")
    if done is not None and not isinstance(done, bool):
        result.errors.append(f"{path}:{line}: done must be a JSON boolean when present")
    refs = obj.get("refs")
    if refs is not None:
        if not isinstance(refs, list) or not all(isinstance(x, str) for x in refs):
            result.errors.append(
                f"{path}:{line}: refs must be a JSON array of strings when present"
            )
        else:
            for j, r in enumerate(refs):
                if "\n" in r or "\r" in r:
                    result.errors.append(
                        f"{path}:{line}: refs[{j}] must be single-line strings"
                    )


def _require_id(obj: dict[str, Any], *, path: str, line: int, ctx: str) -> str | None:
    i = obj.get("id")
    if i is None:
        return None
    if not isinstance(i, str) or not i:
        return None
    if not RE_TRACK_ID.match(i):
        return None
    return i


def parse_track_comment_line(
    line: str, *, path: str, line_no: int, result: ParseResult
) -> TrackAnchor | None:
    """Parse a single line that is exactly one ``<!-- sv0-track: ... -->`` comment."""
    m = RE_TRACK_LINE.match(line)
    if not m:
        return None
    body = m.group("body").strip()

    def fail(msg: str) -> None:
        result.errors.append(f"{path}:{line_no}: {msg}")

    if body.startswith("begin"):
        rest = body[5:].strip()
        if not rest.startswith("{"):
            fail("sv0-track:begin must be followed by a JSON object")
            return None
        detail = _json_error_detail(rest, path, line_no, "begin")
        obj = _parse_json_object(rest, path=path, line=line_no, ctx="begin")
        if obj is None:
            result.errors.append(detail)
            return None
        _validate_payload_keys(obj, path=path, line=line_no, result=result)
        _validate_semantic_fields(obj, path=path, line=line_no, result=result)
        tid = _require_id(obj, path=path, line=line_no, ctx="begin")
        if tid is None:
            fail(
                'sv0-track:begin JSON must include a non-empty string "id" matching '
                + repr(RE_TRACK_ID.pattern)
            )
            return None
        anchor = TrackAnchor(line=line_no, form="begin", payload=obj)
        result.anchors.append(anchor)
        return anchor

    if body.startswith("end"):
        rest = body[3:].strip()
        if not rest:
            obj = {}
        elif not rest.startswith("{"):
            fail("sv0-track:end may only be followed by optional JSON object")
            return None
        else:
            detail = _json_error_detail(rest, path, line_no, "end")
            obj = _parse_json_object(rest, path=path, line=line_no, ctx="end")
            if obj is None:
                result.errors.append(detail)
                return None
            _validate_payload_keys(obj, path=path, line=line_no, result=result)
            _validate_semantic_fields(obj, path=path, line=line_no, result=result)
        anchor = TrackAnchor(line=line_no, form="end", payload=obj)
        result.anchors.append(anchor)
        return anchor

    # standalone
    if not body.startswith("{"):
        fail("sv0-track must use `begin JSON`, `end JSON`, or a standalone JSON object")
        return None
    detail = _json_error_detail(body, path, line_no, "standalone")
    obj = _parse_json_object(body, path=path, line=line_no, ctx="standalone")
    if obj is None:
        result.errors.append(detail)
        return None
    _validate_payload_keys(obj, path=path, line=line_no, result=result)
    _validate_semantic_fields(obj, path=path, line=line_no, result=result)
    tid = _require_id(obj, path=path, line=line_no, ctx="standalone")
    if tid is None:
        fail(
            'sv0-track standalone JSON must include a non-empty string "id" matching '
            + repr(RE_TRACK_ID.pattern)
        )
        return None
    anchor = TrackAnchor(line=line_no, form="standalone", payload=obj)
    result.anchors.append(anchor)
    return anchor


def _split_inline_track_suffix(
    line: str,
) -> tuple[str, dict[str, Any] | None, str | None]:
    """Return (line_without_inline_track, inline_json_or_none, error_or_none)."""
    token = "<!-- sv0-track:"
    if token not in line:
        return line, None, None
    idx = line.rfind(token)
    prefix = line[:idx]
    suffix = line[idx:]
    if not suffix.strip().endswith("-->"):
        return (
            line,
            None,
            "inline sv0-track comment must end with `-->` on the same line",
        )
    inner = suffix[len(token) :]
    inner = inner[: inner.rfind("-->")].strip()
    if "\n" in inner:
        return line, None, "inline sv0-track comment must be single-line"
    detail = _json_error_detail(inner, "<inline>", 0, "inline")
    try:
        obj = json.loads(inner)
    except json.JSONDecodeError:
        return line, None, detail
    if not isinstance(obj, dict):
        return line, None, "inline sv0-track JSON must be an object"
    return prefix.rstrip(), obj, None


def _ingest_numbered_for_region(open_payload: dict[str, Any]) -> bool:
    ing = open_payload.get("ingest")
    if ing == "numbered":
        return True
    if ing == "both":
        return True
    if ing in (None, "gfm"):
        return False
    return False


def _line_is_numbered_step(line: str) -> bool:
    return bool(re.match(r"^[ \t]*\d+\.\s+\S", line))


def parse_task_rmd_body(
    body: str, *, path: str, body_start_line: int = 1
) -> ParseResult:
    """Parse ``body`` (markdown after YAML front matter)."""
    result = ParseResult(path=path)
    lines = body.splitlines()
    region_stack: list[dict[str, Any]] = []
    standalone_ids: set[str] = set()
    prev_nonempty_was_standalone_track: TrackAnchor | None = None

    def line_no(i: int) -> int:
        return body_start_line + i

    for i, raw_line in enumerate(lines):
        ln = line_no(i)
        if "\n" in raw_line:
            result.warnings.append(f"{path}:{ln}: unexpected embedded newline")

        track_anchor = parse_track_comment_line(
            raw_line, path=path, line_no=ln, result=result
        )
        if track_anchor is not None:
            if track_anchor.form == "standalone":
                tid = str(track_anchor.payload["id"])
                is_dup = tid in standalone_ids
                if is_dup:
                    result.errors.append(
                        f"{path}:{ln}: duplicate standalone sv0-track id {tid!r} "
                        "(ids must be unique per file for standalone anchors)"
                    )
                else:
                    standalone_ids.add(tid)
                prev_nonempty_was_standalone_track = None if is_dup else track_anchor
            elif track_anchor.form == "begin":
                bid = str(track_anchor.payload["id"])
                if any(str(x.get("id")) == bid for x in region_stack):
                    result.errors.append(
                        f"{path}:{ln}: sv0-track:begin id {bid!r} is already open "
                        "(duplicate open region ids are not allowed)"
                    )
                else:
                    region_stack.append(track_anchor.payload)
                prev_nonempty_was_standalone_track = None
            elif track_anchor.form == "end":
                end_id = track_anchor.payload.get("id")
                if not region_stack:
                    result.errors.append(
                        f"{path}:{ln}: sv0-track:end without matching begin"
                    )
                else:
                    if end_id is not None:
                        if not isinstance(end_id, str) or not RE_TRACK_ID.match(end_id):
                            result.errors.append(
                                f"{path}:{ln}: sv0-track:end id must be a non-empty id string"
                            )
                        else:
                            innermost = region_stack[-1]
                            if str(innermost.get("id")) != end_id:
                                result.errors.append(
                                    f"{path}:{ln}: sv0-track:end id {end_id!r} does not match "
                                    f"innermost open region {innermost.get('id')!r}"
                                )
                            else:
                                region_stack.pop()
                    else:
                        region_stack.pop()
                prev_nonempty_was_standalone_track = None
            continue

        # Non-track line: maybe GFM checklist or numbered ingest.
        stripped = raw_line.strip()
        if stripped == "":
            continue

        # GFM task item
        m = RE_TASK_LINE.match(raw_line)
        if m:
            box = m.group("box")
            done = box.lower() == "x"
            mid = m.group("mid")
            text_base, inline_obj, inline_err = _split_inline_track_suffix(mid)
            if inline_err:
                result.errors.append(f"{path}:{ln}: {inline_err}")
                continue
            text = text_base.strip()
            track_ids: list[str] = []
            source: Literal["region", "prev_line", "inline"]

            if inline_obj is not None:
                _validate_payload_keys(inline_obj, path=path, line=ln, result=result)
                _validate_semantic_fields(inline_obj, path=path, line=ln, result=result)
                tid = _require_id(inline_obj, path=path, line=ln, ctx="inline")
                if tid is None:
                    result.errors.append(
                        f"{path}:{ln}: inline sv0-track JSON must include a valid string id"
                    )
                else:
                    track_ids.append(tid)
                source = "inline"
            elif region_stack:
                top = region_stack[-1]
                track_ids.append(str(top["id"]))
                source = "region"
            elif prev_nonempty_was_standalone_track is not None:
                track_ids.append(str(prev_nonempty_was_standalone_track.payload["id"]))
                source = "prev_line"
            else:
                source = "region"  # unused; no ids

            if not track_ids:
                # Orphan checkbox: allowed (optional anchors). Do not emit item for digest noise
                # unless we want to list untracked boxes — skip ingestion for untracked checkboxes.
                prev_nonempty_was_standalone_track = None
                continue

            result.checklist_items.append(
                ChecklistItem(
                    line=ln,
                    done=done,
                    text=text,
                    track_ids=list(track_ids),
                    source=source,
                )
            )
            prev_nonempty_was_standalone_track = None
            continue

        # Numbered steps inside region when ingest allows
        if (
            region_stack
            and _ingest_numbered_for_region(region_stack[-1])
            and _line_is_numbered_step(raw_line)
        ):
            top = region_stack[-1]
            tid = str(top["id"])
            result.checklist_items.append(
                ChecklistItem(
                    line=ln,
                    done=False,
                    text=stripped,
                    track_ids=[tid],
                    source="region",
                )
            )
            prev_nonempty_was_standalone_track = None
            continue

        prev_nonempty_was_standalone_track = None

    if region_stack:
        for open_pl in reversed(region_stack):
            rid = open_pl.get("id", "?")
            result.errors.append(
                f"{path}: unclosed sv0-track:begin region id {rid!r} (missing sv0-track:end)"
            )

    return result


def parse_task_rmd_file(path: Path) -> ParseResult:
    """Parse a full ``task/*.Rmd`` file including front matter skip."""
    text = path.read_text(encoding="utf-8")
    _fm, body, body_start = split_front_matter(text)
    return parse_task_rmd_body(body, path=str(path), body_start_line=body_start)


def parse_task_rmd_text(
    text: str, *, path: str = "<memory>", body_start_line: int = 1
) -> ParseResult:
    """Parse text; if it has YAML front matter, skip it."""
    _fm, body, bsl = split_front_matter(text)
    start = bsl if _fm is not None else body_start_line
    return parse_task_rmd_body(body, path=path, body_start_line=start)


def result_to_jsonable(result: ParseResult) -> dict[str, Any]:
    """Serialize for ``--digest`` / dashboard ingestion."""
    return {
        "path": result.path,
        "anchors": [
            {"line": a.line, "form": a.form, "payload": a.payload}
            for a in result.anchors
        ],
        "checklist_items": [
            {
                "line": c.line,
                "done": c.done,
                "text": c.text,
                "track_ids": c.track_ids,
                "source": c.source,
            }
            for c in result.checklist_items
        ],
        "errors": result.errors,
        "warnings": result.warnings,
    }


def run_selftests() -> list[str]:
    """Return error strings; empty means all synthetic parses passed."""

    def check(
        text: str, want_errors: int = 0, want_items: int | None = None
    ) -> list[str]:
        r = parse_task_rmd_text(text, path="<selftest>")
        bad: list[str] = []
        if want_errors is not None and len(r.errors) != want_errors:
            bad.append(
                f"expected {want_errors} errors, got {len(r.errors)}: {r.errors}"
            )
        if want_items is not None and len(r.checklist_items) != want_items:
            bad.append(
                f"expected {want_items} checklist items, got {len(r.checklist_items)}"
            )
        return bad

    errs: list[str] = []

    # Valid begin/end + checkbox in region
    t1 = """---
x: y
---

<!-- sv0-track:begin {"id":"r.a","ingest":"gfm"} -->
- [ ] one
- [x] two
<!-- sv0-track:end -->
"""
    errs.extend(check(t1, want_errors=0, want_items=2))

    # Unclosed begin
    t2 = """---
x: y
---

<!-- sv0-track:begin {"id":"r.b"} -->
- [ ] x
"""
    errs.extend(check(t2, want_errors=1))

    # end without begin
    t3 = """---
x: y
---

<!-- sv0-track:end -->
"""
    errs.extend(check(t3, want_errors=1))

    # Duplicate standalone id
    t4 = """---
x: y
---

<!-- sv0-track: {"id":"dup.a"} -->
<!-- sv0-track: {"id":"dup.a"} -->
"""
    errs.extend(check(t4, want_errors=1))

    # Malformed JSON
    t5 = """---
x: y
---

<!-- sv0-track: {nojson -->
"""
    errs.extend(check(t5, want_errors=1))

    # `-->` inside JSON string triggers safety error (literal `-->` in title)
    t6b = """---
x: y
---

<!-- sv0-track: {"id":"bad","title":"x-->y"} -->
"""
    errs.extend(check(t6b, want_errors=1))

    # Prev-line binding
    t7 = """---
x: y
---

<!-- sv0-track: {"id":"prev.bind"} -->
- [ ] bound item
"""
    errs.extend(check(t7, want_errors=0, want_items=1))
    r7 = parse_task_rmd_text(t7, path="<selftest>")
    if r7.checklist_items and r7.checklist_items[0].track_ids != ["prev.bind"]:
        errs.append("prev-line binding mismatch")

    # Blank line between standalone anchor and checklist still binds (prev_line)
    t7b = """---
x: y
---

<!-- sv0-track: {"id":"prev.blank"} -->

- [ ] after blank
"""
    r7b = parse_task_rmd_text(t7b, path="<selftest>")
    if len(r7b.checklist_items) != 1 or r7b.checklist_items[0].track_ids != [
        "prev.blank"
    ]:
        errs.append(f"blank-line prev bind failed: {r7b.checklist_items!r}")

    # Inline binding
    t8 = """---
x: y
---

- [ ] inline <!-- sv0-track: {"id":"inl.one"} -->
"""
    errs.extend(check(t8, want_errors=0, want_items=1))

    # Nested regions
    t9 = """---
x: y
---

<!-- sv0-track:begin {"id":"outer"} -->
- [ ] a
<!-- sv0-track:begin {"id":"inner"} -->
- [ ] b
<!-- sv0-track:end -->
- [ ] c
<!-- sv0-track:end -->
"""
    errs.extend(check(t9, want_errors=0, want_items=3))
    r9 = parse_task_rmd_text(t9, path="<selftest>")
    ids9 = [tuple(c.track_ids) for c in r9.checklist_items]
    if ids9 != [("outer",), ("inner",), ("outer",)]:
        errs.append(f"nested region binding mismatch: {ids9}")

    # Numbered ingest
    t10 = """---
x: y
---

<!-- sv0-track:begin {"id":"num.a","ingest":"numbered"} -->
1. First step
2. Second step
<!-- sv0-track:end -->
"""
    errs.extend(check(t10, want_errors=0, want_items=2))

    # end id mismatch
    t11 = """---
x: y
---

<!-- sv0-track:begin {"id":"a1"} -->
<!-- sv0-track:end {"id":"wrong"} -->
"""
    errs.extend(check(t11, want_errors=2))

    # Unknown key warning (no error)
    t12 = """---
x: y
---

<!-- sv0-track: {"id":"ok.warn","future_key":1} -->
"""
    r12 = parse_task_rmd_text(t12, path="<selftest>")
    if not r12.warnings:
        errs.append("expected warning for unknown JSON key")

    # sv0-track:end JSON is validated (unknown keys warn) — regression guard
    t13 = """---
x: y
---

<!-- sv0-track:begin {"id":"e13.open"} -->
<!-- sv0-track:end {"id":"e13.open","extra_end_key": true} -->
"""
    r13 = parse_task_rmd_text(t13, path="<selftest>")
    if r13.errors:
        errs.append(f"unexpected errors for end optional JSON: {r13.errors}")
    if not any("unknown JSON key" in w for w in r13.warnings):
        errs.append("expected unknown JSON key warning on sv0-track:end payload")

    return errs
