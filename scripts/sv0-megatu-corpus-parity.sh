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
#   PHASEFAIL  the composed compiler rejected it    (parse/resolve/check/emit)
#   PANIC      the composed compiler crashed
#   CCFAIL     emitted C did not compile
#   RUNFAIL    ran but exited non-zero              (wrong output — a real defect)
#
# The interesting invariant is PANIC = CCFAIL = RUNFAIL = 0: the composed compiler
# never crashes, never emits invalid C, and never emits behaviorally-wrong C — it
# only rejects programs whose features it does not yet support. Usage:
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
  if [ "$mex" -ge 128 ]; then panic=$((panic + 1)); fails+="PANIC(sig$((mex - 128))) $f"$'\n'; continue; fi
  if [ ! -s "$OUT" ]; then phasefail=$((phasefail + 1)); fails+="PHASEFAIL(exit$mex) $f"$'\n'; continue; fi
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

# A crash, invalid C, or wrong output is a real defect; a rejection is a known gap.
if [ "$panic" -ne 0 ] || [ "$ccfail" -ne 0 ] || [ "$runfail" -ne 0 ]; then
  echo "megatu-corpus-parity: FAIL (composed compiler crashed / emitted bad or wrong C)" >&2
  exit 1
fi
echo "megatu-corpus-parity: OK ($pass/$total behaviorally correct; the rest are clean rejections)"
