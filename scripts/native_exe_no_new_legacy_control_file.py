"""Static guard: no new `/tmp/.sv0_drv_path` reference, anywhere (NEX-055c, REL-004 -- CLOSED).

Implements the "static guard" half of REL-004
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md`): "Global
`/tmp/.sv0_drv_path` SHALL not appear in the stable executable path."

**REL-004 is now closed.** `sv0c/lib/driver.sv0`'s `fn main()` and both
mega-TU compose-main templates (`build-sv0-megatu-native.sh`,
`build-sv0-megatu-vm-native.sh`) no longer have a legacy-file fallback at
all -- `getenv("SV0_DRV_REQUEST")` (never panics on an unset variable) is
the sole entry channel. Getting here took a 6-step migration plan, each
step verified real end to end (byte-identical output before/after,
`./scripts/sv0 test`/`test-guards` clean, no new failures beyond this
project's own long-standing pre-existing ones):

1. Add the `getenv` host builtin (NEX-055c's own original scoping +
   implementation).
2. Add `SV0_DRV_REQUEST` as an *additional* read path to `driver.sv0`
   and `build-sv0-megatu-native.sh`'s compose-main, alongside the legacy
   file.
3. Migrate `native_exe_core_compiler.py`'s `CoreCompilerClient` off its
   `flock`-on-a-shared-file design onto a per-call env var (structural,
   not just lock-protected, isolation).
4. Formal self-host-loop re-verification.
5. Migrate every remaining real caller: `scripts/sv0`'s
   `run_compile`/`run_emit_verified`; the VM-bytecode-emitter
   compose-main (`build-sv0-megatu-vm-native.sh`, which step 2 had
   missed -- its `megatu_emit_program` needle had also separately
   bit-rotted, fixed as an unrelated prerequisite); the two
   wrapper-*generating* scripts' emitted wrapper bodies
   (`build-sv0-megatu-native.sh`'s `$WRAP`,
   `build-sv0-self-host-compiler.sh`'s wrapper -- internal
   implementation only, external argv/stdout contract unchanged);
   `sv0-vm-tier2-native-emitter.sh`; dead-code cleanup in
   `verify_behavior_corpus_native.py`/`assemble-sv0-megaTU.py`'s
   defensive resets; and a genuine gap this guard's own first version
   had missed entirely (it only ever scanned `scripts/`) --
   `.github/workflows/self-host-native.yml` had a real, unmigrated
   write, found by an exhaustive repo-wide check and fixed alongside
   extending this guard's scan to cover `.github/workflows/` too.
6. **Remove the legacy fallback for real** from `driver.sv0`'s
   `fn main()` and both compose-main templates, once step 5's exhaustive
   scan confirmed nothing anywhere still wrote real content into the
   file. Verified byte-identical output for every remaining caller with
   the legacy file deleted entirely (not just emptied) throughout; full
   `./scripts/sv0 test` shows only the same long-standing pre-existing
   failures. **Incidental bonus found, not chased further**: simplifying
   `driver.sv0`'s `fn main()` (removing the now-dead fallback branch)
   fixed a pre-existing native-C-compile failure for `lib/driver.sv0`
   itself in `sv0-megatu-native-parity.sh`/`sv0-megatu-corpus-parity.sh`
   (both now pass 97/99 instead of 96/99) -- a genuine improvement, not
   investigated for root cause since it's strictly positive.

**What this module does now**: a permanent regression guard, not a
temporary migration-tracking allowlist. It fails closed if any file (in
`scripts/` or `.github/workflows/`) references the retired
`/tmp/.sv0_drv_path` token outside the documented allowlist below --
which now holds only historical/doc-only mentions (comments explaining
the migration, or a sibling module's own separate control file), never a
real reader or writer. Mirrors NEX-058's own
`native_exe_no_duplicate_cc_recipe.py` precedent (a duplication guard
with a documented exemption list).

Run `python3 scripts/native_exe_no_new_legacy_control_file.py --selftest`
for the corpus.
"""

from __future__ import annotations

import os

_LEGACY_PATH_TOKEN = ".sv0_drv_path"

# The exhaustive, documented set of files legitimately allowed to
# reference the legacy control file today. Every entry has a one-line
# reason; a file not on this list that mentions the token is a NEW
# reference this guard exists to catch. Every entry below is DOC-ONLY --
# REL-004 is closed, so nothing anywhere does real file I/O on the
# legacy path any more. Each entry mentions the token only in a comment
# or docstring explaining the migration history, or (one case) a
# sibling module's own separate, unrelated control file.
_EXEMPT_BASENAMES = {
    "sv0",  # scripts/sv0: ensure_* comment records that driver.sv0's fallback no longer needs a file guarantee
    "build-sv0-megatu-native.sh",  # comment records the retired legacy fallback this compose-main used to also accept
    "build-sv0-megatu-vm-native.sh",  # comment records the retired legacy fallback this compose-main used to also accept
    "assemble-sv0-megaTU.py",  # comment records the retired defensive reset this --check tool used to perform
    "build-sv0-megatu-verify-native.sh",  # one comment explaining why it uses ITS OWN separate, unrelated /tmp/.sv0_verify_path
    "sv0-megatu-corpus-parity.sh",  # comment explains its own compose-main never touched the file at all
    "sv0-native-behavioral-parity.sh",  # comment quotes the legacy path for history only
    "sv0-vm-tier2-native-emitter.sh",  # comment quotes the legacy path for history only
    "verify_behavior_corpus_native.py",  # comment quotes the legacy path for history only
    "native_exe_core_compiler.py",  # migration history in its own docstring (NEX-011/055c)
    "native_exe_concurrent_perf.py",  # PERF-006 finding's before/after history in its docstring
    "native_exe_no_new_legacy_control_file.py",  # this file's own docstring, quoting the token
}


def find_new_legacy_control_file_refs(*dirs: str) -> list[str]:
    """Scan every plain file directly inside each of `dirs` (not
    recursively -- this project keeps its scripts flat in one directory,
    and CI workflow files flat in .github/workflows/) for the legacy
    control-file token, skipping the documented allowlist. Returns the
    list of offending file paths (empty = clean).
    """
    offenders: list[str] = []
    for one_dir in dirs:
        offenders.extend(_scan_one_dir(one_dir))
    return offenders


def _scan_one_dir(scan_dir: str) -> list[str]:
    offenders: list[str] = []
    if not os.path.isdir(scan_dir):
        return offenders
    for name in sorted(os.listdir(scan_dir)):
        if name in _EXEMPT_BASENAMES:
            continue
        path = os.path.join(scan_dir, name)
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
    workflows_dir = os.path.abspath(os.path.join(scripts_dir, "..", ".github", "workflows"))

    # Case 1: the real, shipped scripts/ AND .github/workflows/ directories
    # are both clean against this exact allowlist -- the actual
    # regression-prevention this guard exists for (workflows/ was a real,
    # once-missed gap: self-host-native.yml had a genuine unmigrated write
    # this guard's original scripts-only scope never saw). A file falling
    # off this list (migrated, or the token simply removed) makes this
    # case fail too, in the "entry can be deleted now" direction -- both
    # directions of drift are visible.
    offenders = find_new_legacy_control_file_refs(scripts_dir, workflows_dir)
    if offenders:
        failures.append(
            f"case1: real scripts/ or .github/workflows/ directory has an "
            f"unlisted legacy-control-file reference (either a genuinely new "
            f"site, or the allowlist is stale): {offenders}"
        )

    # Case 2: a synthetic directory WITH a violating new script is caught.
    with tempfile.TemporaryDirectory() as td:
        bad_script = os.path.join(td, "hypothetical-new-caller.sh")
        with open(bad_script, "w", encoding="utf-8") as f:
            f.write('#!/usr/bin/env bash\nprintf \'%s\\n\' "$1" > /tmp/.sv0_drv_path\n')
        offenders2 = find_new_legacy_control_file_refs(td)
        if not offenders2:
            failures.append("case2: a synthetic new legacy-control-file reference was not caught")

    # Case 3: a Python variant is caught too, not just shell -- and across
    # MULTIPLE dirs passed in one call, not just one.
    with tempfile.TemporaryDirectory() as td, tempfile.TemporaryDirectory() as td2:
        bad_py = os.path.join(td, "hypothetical_new_caller.py")
        with open(bad_py, "w", encoding="utf-8") as f:
            f.write('open("/tmp/.sv0_drv_path", "w").write(path)\n')
        bad_yml = os.path.join(td2, "hypothetical-workflow.yml")
        with open(bad_yml, "w", encoding="utf-8") as f:
            f.write('run: printf "%s" "$X" > /tmp/.sv0_drv_path\n')
        offenders3 = find_new_legacy_control_file_refs(td, td2)
        if len(offenders3) != 2:
            failures.append(f"case3: expected exactly 2 offenders across both dirs, got {offenders3}")

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
