#!/usr/bin/env bash
# Run the native-compose (A) mega-TU compiler over the self-host-sv0-loop corpus
# and report native-vs-SML behavioral parity.
#
# Unlike `assemble-megatu --check` (which compiles+runs the mega-TU on ONE fixed
# smoke program), this builds a mega-TU whose compose main reads a source file
# (/tmp/megatu_in.sv0) and writes the emitted C (/tmp/megatu_out.c). The binary is
# built ONCE, then run over every corpus file; each emitted C is cc-compiled and
# run, and the exit code checked against the corpus contract (every seed exits 0).
#
# Outcome categories per file:
#   PASS       emit + cc + run -> exit 0            (behavioral parity)
#   PHASEFAIL  the composed compiler cleanly rejected it (compose main returned a
#              phase code 2/3/4/5: parse/resolve/check/emit)
#   PANIC      the composed compiler crashed (a signal, or sv0_panic's exit(1) —
#              the compose main's own "no tokens" return-1 gate is unreachable for
#              real seeds, so any exit 1 here is a panic)
#   CCFAIL     emitted C did not compile — a feature that resolves/checks but whose
#              lowering/emit is not complete yet (known incompleteness, not wrong)
#   RUNFAIL    ran but exited non-zero              (wrong output — a real defect)
#
# This is a PROGRESS MONITOR, not a CI gate (the real gate is `./scripts/sv0 test`,
# which keeps self-host-sv0-loop at 98/98 via the SML pipeline). The composed
# compiler is bottom-up work in progress: fixing an early phase (e.g. resolve) lets
# more modules reach later phases, so PHASEFAIL falls while CCFAIL/PANIC/RUNFAIL on
# the newly-reached, still-unsupported modules temporarily rise. That is expected —
# those modules never passed. The metric that matters is PASS, and it must not go
# backwards: the script fails only if PASS drops below MIN_PASS (the recorded high-
# water mark, bumped as tasks land). PANIC/RUNFAIL are printed as triage signals to
# investigate and drive to zero, not hard failures. Usage:
#   scripts/sv0-megatu-corpus-parity.sh            # summary
#   scripts/sv0-megatu-corpus-parity.sh --verbose  # also list every non-PASS file
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERBOSE=0
[ "${1:-}" = "--verbose" ] && VERBOSE=1

SV0C="sv0c/build/sv0c"
RT="sv0c/runtime"
LIST="sv0c/lib/self-host-sv0-loop.list"
IN="/tmp/megatu_in.sv0"
OUT="/tmp/megatu_out.c"
CORPUS_MAIN="build/megaTU-corpus-main.sv0"
CORPUS_TU="build/megaTU-corpus.sv0"
CORPUS_C="build/megaTU-corpus.c"
CORPUS_BIN="build/megaTU-corpus-bin"

[ -f "$SV0C" ] || { echo "error: $SV0C not built (run scripts to build the SML sv0c first)" >&2; exit 2; }
mkdir -p build

# 1. Derive the corpus-runner main from the committed compose main: read the source
#    from $IN and write the emitted C to $OUT (keeping every megatu_* helper).
python3 - "$IN" "$OUT" "$CORPUS_MAIN" <<'PY'
import re, sys, pathlib
inp, outp, dst = sys.argv[1], sys.argv[2], sys.argv[3]
src = pathlib.Path("sv0c/lib/megaTU-main.sv0").read_text()
src = re.sub(r'let source: string = "[^"]*";',
             f'let source: string = read_file("{inp}");', src, count=1)
needle = "    if string_len(c) == 0 { return 5; }"
assert needle in src, "compose main shape changed; update this harness"
src = src.replace(needle, f'    write_file("{outp}", c);\n' + needle, 1)
pathlib.Path(dst).write_text(src)
PY

# 2. Assemble + SML->C->cc the corpus binary once.
python3 scripts/assemble-sv0-megaTU.py --root "$ROOT" --main "$CORPUS_MAIN" --out "$CORPUS_TU" >/dev/null
sml "@SMLload=$SV0C" "$CORPUS_TU" > "$CORPUS_C" 2>/dev/null
cc -std=c99 -O0 -w -I "$RT" "$CORPUS_C" "$RT/sv0_runtime.c" -o "$CORPUS_BIN"

# 3. Run every corpus seed through it.
pass=0 phasefail=0 panic=0 ccfail=0 runfail=0 total=0
fails=""
while IFS= read -r f; do
  case "$f" in ''|\#*) continue;; esac
  total=$((total + 1))
  seed="sv0c/$f"
  [ -f "$seed" ] || { fails+="MISSING $f"$'\n'; continue; }
  cp "$seed" "$IN"; rm -f "$OUT"
  set +e
  "$CORPUS_BIN" >/dev/null 2>&1; mex=$?
  set -e
  if [ ! -s "$OUT" ]; then
    # No emitted C: a clean phase rejection (compose main returned 2/3/4/5) vs a
    # crash (signal, or sv0_panic's exit 1 — the return-1 gate is unreachable here).
    case "$mex" in
      2|3|4|5) phasefail=$((phasefail + 1)); fails+="PHASEFAIL(exit$mex) $f"$'\n';;
      *)       panic=$((panic + 1));         fails+="PANIC(exit$mex) $f"$'\n';;
    esac
    continue
  fi
  if ! cc -std=c99 -O0 -w -I "$RT" "$OUT" "$RT/sv0_runtime.c" -o /tmp/megatu_run 2>/dev/null; then
    ccfail=$((ccfail + 1)); fails+="CCFAIL $f"$'\n'; continue
  fi
  set +e
  /tmp/megatu_run >/dev/null 2>&1; rex=$?
  set -e
  if [ "$rex" -eq 0 ]; then pass=$((pass + 1)); else runfail=$((runfail + 1)); fails+="RUNFAIL(exit$rex) $f"$'\n'; fi
done < "$LIST"

echo "megatu-corpus-parity: PASS=$pass PHASEFAIL=$phasefail PANIC=$panic CCFAIL=$ccfail RUNFAIL=$runfail (total=$total)"
if [ "$VERBOSE" = 1 ] && [ -n "$fails" ]; then
  echo "--- non-PASS ---"
  printf '%s' "$fails"
fi

# PASS must not regress below the recorded high-water mark. PANIC/RUNFAIL are
# triage signals on still-unsupported modules, not gate failures (see header).
MIN_PASS=84
if [ "$panic" -ne 0 ] || [ "$runfail" -ne 0 ]; then
  echo "megatu-corpus-parity: note — $panic panic(s), $runfail wrong-output on unsupported modules (triage, not fatal)"
fi
if [ "$pass" -lt "$MIN_PASS" ]; then
  echo "megatu-corpus-parity: FAIL — PASS $pass regressed below high-water mark $MIN_PASS" >&2
  exit 1
fi
echo "megatu-corpus-parity: OK ($pass/$total PASS; floor $MIN_PASS; $phasefail rejected, $ccfail emit-incomplete)"
