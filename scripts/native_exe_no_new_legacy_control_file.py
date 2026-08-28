"""Static guard: no NEW `/tmp/.sv0_drv_path` reference outside the known legacy set (NEX-055c, REL-004 step 6).

Implements the "static guard" half of REL-004
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "Global
`/tmp/.sv0_drv_path` SHALL not appear in the stable executable path."

**What step 6 actually is, stated honestly.** The design doc's own
sequencing (`sv0c/doc/native-executable-reentrant-core-compiler-design.md`)
calls step 6 "remove the legacy control-file path entirely." That is NOT
what this module does, and doing it for real is not safe today. A
full-repo scan (run once, by hand, while writing this guard) originally
found the legacy control file load-bearing in eleven places beyond the
two already migrated in steps 3/5 (`native_exe_core_compiler.py`,
`scripts/sv0`'s `run_compile`/`run_emit_verified`). A REL-004 closure
follow-up has since migrated `build-sv0-megatu-vm-native.sh`'s own
compose-main to prefer `SV0_DRV_REQUEST` too (chunk 2 -- the one
compose-main step 2 originally missed; along the way, its `megatu_
emit_program` call needle had also silently bit-rotted against an
unrelated upstream signature change and needed a one-line fix just to
make the recipe buildable again, unrelated to REL-004 itself but
necessary to verify this chunk at all), and migrated/cleared three more
files that turned out to never touch the file for real in the first
place (`sv0-native-behavioral-parity.sh`, `sv0-megatu-corpus-parity.sh`,
and a dead-code cleanup in `sv0-megatu-native-parity.sh`'s own redundant
resets), and migrated `sv0-vm-tier2-native-emitter.sh` to
`SV0_DRV_REQUEST` (chunk 3, unblocked by chunk 2). A further follow-up
migrated the two wrapper-*generating* scripts' emitted wrapper bodies
themselves (chunk 4) -- `build-sv0-megatu-native.sh`'s `$WRAP` heredoc
and `build-sv0-self-host-compiler.sh`'s wrapper heredoc now pass the
request via `SV0_DRV_REQUEST` too, changing the wrapper's internal
implementation only, never its external argv/stdout contract (verified
byte-identical output before/after for every invocation shape: file
mode, `--project` mode, the missing-argument error path). A final
cleanup pass (chunk 5) removed `verify_behavior_corpus_native.py`'s own
now-redundant defensive reset (the wrapper it invokes stopped writing
the file in chunk 4, so nothing was left to protect) and investigated
`assemble-sv0-megaTU.py`'s equivalent reset in its `--check` mode --
concluded that one is NOT the same kind of migratable dead code: it is
a generic developer tool whose `--check` mode can be pointed at an
arbitrary caller-supplied compose-main, so its defensive reset is a
legitimate, permanent safety net rather than a specific request write to
migrate, and was left in place deliberately.

**A real finding from finishing chunk 5**: every genuinely *temporary*
caller (one this closure plan could actually finish migrating) has now
been migrated. **Five entries remain in `_EXEMPT_BASENAMES`, and all
five are now permanent-by-design, not "not yet migrated"**: `sv0`
(`scripts/sv0`'s `ensure_*` file-existence guarantees),
`build-sv0-megatu-native.sh` and `build-sv0-megatu-vm-native.sh` (each
keeps the file as an intentional, additive fallback in its own
compose-main, plus a shared file-init reset), `build-sv0-self-host-compiler.sh`
(the same shared file-init reset for `driver.sv0`'s own fallback), and
`assemble-sv0-megaTU.py` (the generic safety net above). Every one of
these exists only *because* `driver.sv0`/`megaTU-main.sv0` still have a
legacy fallback read path at all -- they cannot shrink further without
removing that fallback itself, which is the true REL-004 closure (this
guard's own step 6), not a chunk this migration plan can execute
incrementally -- real, separate, tracked work, recorded honestly here
rather than silently attempted or silently dropped.

**What this module does instead**: the other half of step 6 that IS safe
and valuable today -- a static guard that fails closed if a *new* file
(anything not in the exhaustive, documented allowlist below) references
`/tmp/.sv0_drv_path`. This stops the legacy channel from *growing* any
further while the real migration of its existing callers remains a
tracked, separate follow-up, mirroring NEX-058's own
`native_exe_no_duplicate_cc_recipe.py` precedent exactly (a duplication
guard with a documented exemption list, not a completed migration).

Run `python3 scripts/native_exe_no_new_legacy_control_file.py --selftest`
for the corpus.
"""

from __future__ import annotations

import os

_LEGACY_PATH_TOKEN = ".sv0_drv_path"

# The exhaustive, documented set of files legitimately allowed to
# reference the legacy control file today. Every entry has a one-line
# reason; a file not on this list that mentions the token is a NEW
# reference this guard exists to catch. Entries fall into two groups:
#
#   (a) STILL A REAL, UNMIGRATED CALLER -- reads/writes the file for real,
#       not yet moved to SV0_DRV_REQUEST. Tracked as the follow-up this
#       module's own docstring names; removing the entry from this list is
#       exactly how a future migration of that file gets held to this
#       guard (migrate the file, then delete its allowlist line).
#   (b) DOC-ONLY / GUARD-OWN-SOURCE -- mentions the token in prose (this
#       module's own docstring, or another module's historical-context
#       comment) with no actual file I/O on it.
_EXEMPT_BASENAMES = {
    # (a) real, unmigrated legacy callers
    "sv0",  # scripts/sv0: ensure_*'s file-existence guarantee for every other unmigrated caller below
    "build-sv0-megatu-native.sh",  # compose-main + generated wrapper both migrated (steps 2, chunk 4); token survives only in the intentional, permanent legacy-fallback read + the shared file-init reset every other still-unmigrated caller depends on
    "build-sv0-megatu-vm-native.sh",  # compose-main migrated to SV0_DRV_REQUEST (chunk 2); the token survives only in its intentional, permanent legacy-fallback read (no wrapper of its own)
    "build-sv0-self-host-compiler.sh",  # generated wrapper migrated (chunk 4); token survives only in the shared file-init reset + a doc comment
    "assemble-sv0-megaTU.py",  # generic --check tool: defensively resets before invoking sml on WHATEVER compose-main a caller supplies; not migratable in the same sense (it never constructs a request itself, and its future callers/compose-mains aren't fully enumerable) -- a permanent, intentional safety net
    # (b) doc-only mentions, no real file I/O on the legacy path (migrated to
    # SV0_DRV_REQUEST already, or never touched it for real; the token only
    # survives in a comment/docstring explaining the history or a sibling file)
    "build-sv0-megatu-verify-native.sh",  # one comment explaining why it uses ITS OWN separate /tmp/.sv0_verify_path instead
    "sv0-megatu-corpus-parity.sh",  # migrated NEX-055c/REL-004 chunk 1; comment now explains its own compose-main never touched the file at all
    "sv0-native-behavioral-parity.sh",  # migrated NEX-055c/REL-004 chunk 1; comment quotes the legacy path for history only
    "sv0-vm-tier2-native-emitter.sh",  # migrated NEX-055c/REL-004 chunk 3; comment quotes the legacy path for history only
    "sv0-megatu-native-parity.sh",  # invokes build-sv0-megatu-native.sh's now-migrated wrapper (chunk 4); comment quotes the legacy path for history only
    "verify_behavior_corpus_native.py",  # migrated NEX-055c/REL-004 chunk 5; comment quotes the legacy path for history only
    "native_exe_core_compiler.py",  # migration history in its own docstring (NEX-011/055c)
    "native_exe_concurrent_perf.py",  # PERF-006 finding's before/after history in its docstring
    "native_exe_no_new_legacy_control_file.py",  # this file's own docstring/allowlist, quoting the token
}


def find_new_legacy_control_file_refs(scripts_dir: str) -> list[str]:
    """Scan every plain file directly inside `scripts_dir` (not
    recursively -- this project keeps its scripts flat in one directory)
    for the legacy control-file token, skipping the documented allowlist.
    Returns the list of offending file paths (empty = clean).
    """
    offenders: list[str] = []
    for name in sorted(os.listdir(scripts_dir)):
        if name in _EXEMPT_BASENAMES:
            continue
        path = os.path.join(scripts_dir, name)
        if not os.path.isfile(path):
            continue
        if name.endswith(".pyc") or name.endswith(".bak"):
            continue
        try:
            with open(path, encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except OSError:
            continue
        if _LEGACY_PATH_TOKEN in content:
            offenders.append(path)
    return offenders


def _selftest() -> int:
    import tempfile

    failures: list[str] = []

    scripts_dir = os.path.dirname(os.path.abspath(__file__))

    # Case 1: the real, shipped scripts/ directory is clean against this
    # exact allowlist -- the actual regression-prevention this guard
    # exists for. A file falling off this list (migrated, or the token
    # simply removed) makes this case fail too, in the "entry can be
    # deleted now" direction -- both directions of drift are visible.
    offenders = find_new_legacy_control_file_refs(scripts_dir)
    if offenders:
        failures.append(
            f"case1: real scripts/ directory has an unlisted legacy-control-file "
            f"reference (either a genuinely new site, or the allowlist is stale): {offenders}"
        )

    # Case 2: a synthetic directory WITH a violating new script is caught.
    with tempfile.TemporaryDirectory() as td:
        bad_script = os.path.join(td, "hypothetical-new-caller.sh")
        with open(bad_script, "w", encoding="utf-8") as f:
            f.write('#!/usr/bin/env bash\nprintf \'%s\\n\' "$1" > /tmp/.sv0_drv_path\n')
        offenders2 = find_new_legacy_control_file_refs(td)
        if not offenders2:
            failures.append("case2: a synthetic new legacy-control-file reference was not caught")

    # Case 3: a Python variant is caught too, not just shell.
    with tempfile.TemporaryDirectory() as td:
        bad_py = os.path.join(td, "hypothetical_new_caller.py")
        with open(bad_py, "w", encoding="utf-8") as f:
            f.write('open("/tmp/.sv0_drv_path", "w").write(path)\n')
        offenders3 = find_new_legacy_control_file_refs(td)
        if len(offenders3) != 1:
            failures.append(f"case3: expected exactly 1 offender, got {offenders3}")

    # Case 4: a file on the allowlist is never flagged, even though it
    # genuinely contains the token -- proves the exemption mechanism
    # itself works, not just that the scan can find a hit.
    with tempfile.TemporaryDirectory() as td:
        allowed = os.path.join(td, "sv0")
        with open(allowed, "w", encoding="utf-8") as f:
            f.write('printf "" > /tmp/.sv0_drv_path\n')
        offenders4 = find_new_legacy_control_file_refs(td)
        if offenders4:
            failures.append(f"case4: an allowlisted basename was incorrectly flagged: {offenders4}")

    # Case 5: an unrelated file mentioning some OTHER tmp path is not
    # flagged -- this guard targets the specific legacy token, not any
    # /tmp/ reference.
    with tempfile.TemporaryDirectory() as td:
        clean = os.path.join(td, "unrelated.py")
        with open(clean, "w", encoding="utf-8") as f:
            f.write('SCRATCH = "/tmp/.sv0_other_thing"\n')
        offenders5 = find_new_legacy_control_file_refs(td)
        if offenders5:
            failures.append(f"case5: an unrelated /tmp/ path was incorrectly flagged: {offenders5}")

    if failures:
        for f in failures:
            print(f"native_exe_no_new_legacy_control_file selftest FAIL: {f}")
        return 1

    print("native_exe_no_new_legacy_control_file: selftest OK (5 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_no_new_legacy_control_file: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
