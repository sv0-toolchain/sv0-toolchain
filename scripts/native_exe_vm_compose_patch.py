"""Resilient phase-6 patch for the VM-bytecode-emitter compose main (P4/D1b hardening).

`scripts/build-sv0-megatu-vm-native.sh` derives its own VM compose main
from the committed `sv0c/lib/megaTU-main.sv0` by textually replacing
phase 6 (the C-emit call + empty-C gate) with a VM-specific tail. The
substitution used to match `megatu_emit_program`'s own call *literally*,
argument list and all -- brittle by construction, and not hypothetically:
that argument list grew TWICE in real history
(`eit_nt`/`eit_base`/`eit_cnt`/`eit_cats`, then
`sit_nt`/`sit_base`/`sit_cnt`/`sit_field_name`/`sit_field_cat`, both
unrelated C-emit-only metadata additions), silently breaking the build
script's own assembly step each time with no test-time signal at all --
found only by someone happening to run the script by hand.

This module holds the substitution as a real, independently testable
function instead: it matches only the STABLE start anchor
(`assign_shadow_indices`'s own call, which begins phase 6) through the
STABLE end anchor (the `if string_len(c) == 0 { return 5; }` empty-C
gate that ends it), via a non-greedy multi-line regex. The VM tail never
calls `megatu_emit_program` at all (it calls `vm_codegen_emit_program`
instead), so the exact argument list phase 6 passes to the C-only emit
function is irrelevant to this substitution -- a future argument added
to that call no longer requires touching this patch at all, and the
`--selftest` below proves that directly by mutating a synthetic snippet
across several argument-list shapes, not just asserting today's shape
still matches.

Run `python3 scripts/native_exe_vm_compose_patch.py --selftest` for the
corpus.
"""

from __future__ import annotations

import re

PHASE6_RE = re.compile(
    r"    let sidx: Vec<i32> = assign_shadow_indices\(.*?"
    r"    if string_len\(c\) == 0 \{ return 5; \}",
    re.DOTALL,
)


class Phase6PatchError(Exception):
    """Raised when the compose main's phase-6 start/end anchors can't be found at all --
    a real, structural shape change (not just an argument-list length change),
    which this patch genuinely cannot handle and should not silently guess at.
    """


def find_phase6(src: str) -> str:
    """Return the exact phase-6 text (start anchor through end anchor,
    inclusive) found in `src`. Raises `Phase6PatchError` if the anchors
    aren't both present.
    """
    m = PHASE6_RE.search(src)
    if m is None:
        raise Phase6PatchError(
            "compose main phase-6 shape changed: could not find the "
            "assign_shadow_indices...string_len(c)==0 anchors at all"
        )
    return m.group(0)


def patch_phase6(src: str, replacement: str) -> str:
    """Replace phase 6 (whatever its current internal shape) with
    `replacement`. Raises `Phase6PatchError` if phase 6 can't be found.
    """
    phase6 = find_phase6(src)
    return src.replace(phase6, replacement, 1)


def _selftest() -> int:
    failures: list[str] = []

    # A synthetic snippet mimicking megaTU-main.sv0's real shape, with the
    # `megatu_emit_program` call's own argument list deliberately varied
    # across cases -- proving the patch tolerates a growing/shrinking arg
    # list (the real historical failure mode) rather than merely
    # re-confirming today's exact shape still matches.
    def make_snippet(emit_args: str) -> str:
        return (
            "fn main() -> i32 {\n"
            "    /* ... phases 1-5 ... */\n"
            "    let sidx: Vec<i32> = assign_shadow_indices(it, id3, id4, id5, fpn,\n"
            "                                               bet, bed1, bed2, bed3, bed4, pp,\n"
            "                                               source, starts, ends);\n"
            f"    let c: string = megatu_emit_program({emit_args});\n"
            "    if string_len(c) == 0 { return 5; }\n"
            "    write_file(\"/dev/stdout\", c);\n"
            "    return 0;\n"
            "}\n"
        )

    cases = [
        "td, out_blocks, source, starts, ends",
        "td, out_blocks, source, starts, ends, it, id1, id2, id3, id5, fpn, fpt, frt, ptt, ptd1, ptd2, pp, sidx",
        (
            "td, out_blocks, source, starts, ends, it, id1, id2, id3, id5, fpn, fpt, frt, ptt, ptd1, ptd2, pp, "
            "sidx, eit_nt, eit_base, eit_cnt, eit_cats"
        ),
        (
            "td, out_blocks, source, starts, ends, it, id1, id2, id3, id5, fpn, fpt, frt, ptt, ptd1, ptd2, pp, "
            "sidx, eit_nt, eit_base, eit_cnt, eit_cats, sit_nt, sit_base, sit_cnt, sit_field_name, sit_field_cat"
        ),
        # A 6th, hypothetical FUTURE arg-list growth this patch has never
        # seen before -- the actual point of this test: prove it still
        # works on a shape that doesn't exist in the repo yet.
        (
            "td, out_blocks, source, starts, ends, it, id1, id2, id3, id5, fpn, fpt, frt, ptt, ptd1, ptd2, pp, "
            "sidx, eit_nt, eit_base, eit_cnt, eit_cats, sit_nt, sit_base, sit_cnt, sit_field_name, sit_field_cat, "
            "some_brand_new_arg_from_a_future_change"
        ),
    ]

    vm_tail = "    /* VM TAIL */\n    write_bytes(\"/dev/stdout\", vout);"

    for i, emit_args in enumerate(cases):
        snippet = make_snippet(emit_args)
        try:
            patched = patch_phase6(snippet, vm_tail)
        except Phase6PatchError as exc:
            failures.append(f"case{i}: raised unexpectedly for a valid arg-list shape: {exc}")
            continue
        if "megatu_emit_program" in patched:
            failures.append(f"case{i}: patched source still mentions megatu_emit_program (phase 6 not fully replaced)")
        if vm_tail not in patched:
            failures.append(f"case{i}: VM tail not found in patched source")
        if "assign_shadow_indices" in patched:
            failures.append(f"case{i}: assign_shadow_indices call survived the patch (start anchor not consumed)")
        # Everything before/after phase 6 must survive untouched.
        if "fn main() -> i32 {" not in patched or "return 0;\n}\n" not in patched:
            failures.append(f"case{i}: surrounding main() body was damaged by the patch")

    # A genuinely different, unrelated structural change (not just a longer
    # arg list) -- the end anchor itself renamed -- must still raise, not
    # silently guess at a replacement. This is the one case this patch
    # deliberately does NOT tolerate, and should say so clearly.
    broken_snippet = make_snippet("td, out_blocks").replace(
        "if string_len(c) == 0 { return 5; }", "if string_len(c) == 0 { return 6; }"
    )
    try:
        patch_phase6(broken_snippet, vm_tail)
        failures.append("broken-anchor case: expected Phase6PatchError, none raised")
    except Phase6PatchError:
        pass

    if failures:
        for f in failures:
            print(f"native_exe_vm_compose_patch selftest FAIL: {f}")
        return 1

    print(f"native_exe_vm_compose_patch: selftest OK ({len(cases)} arg-list shapes + 1 broken-anchor case)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_vm_compose_patch: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
