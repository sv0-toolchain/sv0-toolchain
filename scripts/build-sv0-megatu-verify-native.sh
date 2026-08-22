#!/usr/bin/env bash
# M4-S-020: native contract-VERIFY binary (driver-orchestrated verification).
#
# Sibling to build-sv0-megatu-native.sh, but instead of composing the full
# compile pipeline (resolve/check/lower/emit → C) it composes tokenize + parse +
# verify_all_fns → SMT-LIB2 obligation records. The whole 18-module pipeline plus
# lib/verify_vcgen.sv0 (the M4 verification module) is assembled into one mega-TU
# whose derived main:
#   - reads the .sv0 path from /tmp/.sv0_verify_path (its OWN control file — never
#     collides with the compiler's /tmp/.sv0_drv_path),
#   - tokenizes + parse_programs it,
#   - calls verify_all_fns over the parser arenas and writes the obligation
#     records (one `VC\t<fn>\t<line>\t<smt2|RESIDUAL>` per ensures) to stdout.
# `./scripts/sv0 verify <file>` then runs each query through scripts/sv0-z3.sh and
# reports per-contract [verified]/[runtime]. z3 is never spawned by this binary
# (host-process story M4-S-013: driver-orchestrated).
#
# Build is a one-time SML bootstrap (mega-TU sv0 → C → cc); the result runs with
# no SML heap. Produces:
#   build/sv0-megatu-verify-native      — the native verify binary (reads /tmp/.sv0_verify_path, records to stdout)
#   build/sv0-megatu-verify             — wrapper adapting argv[1] → /tmp/.sv0_verify_path → the binary
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

MAIN_SRC="$SV0C/lib/megaTU-main.sv0"
MODULES="$SV0C/lib/megaTU-modules.list"
VERIFY_MAIN="$BUILD/megaTU-verify-main.sv0"
MANIFEST="$BUILD/megaTU-verify-modules.list"
TU="$BUILD/megaTU-verify.sv0"
EMIT_C="$BUILD/megaTU-verify.c"
NATIVE="$BUILD/sv0-megatu-verify-native"
WRAP="$BUILD/sv0-megatu-verify"

# ── 1. Derive the verify compose main from megaTU-main.sv0 ───────────────────
#    - source: read the path from /tmp/.sv0_verify_path (strip trailing newline)
#    - after the parse gate, emit obligation records + return 0 (the rest of the
#      compile pipeline stays in the derived source but is unreachable).
python3 - "$MAIN_SRC" "$VERIFY_MAIN" <<'PY'
import re, sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text()

cli_read = (
    'let _vrf_p: string = read_file("/tmp/.sv0_verify_path");\n'
    '    let _vrf_n: i32 = string_len(_vrf_p);\n'
    '    let _vrf_c: string = if _vrf_n > 0 {\n'
    '        if string_char_at(_vrf_p, _vrf_n - 1) == 10 {\n'
    '            string_substr(_vrf_p, 0, _vrf_n - 1)\n'
    '        } else { _vrf_p }\n'
    '    } else { _vrf_p };\n'
    '    let source: string = expand_from_file(_vrf_c);'
)
src, n = re.subn(r'let source: string = "[^"]*";', cli_read, src, count=1)
assert n == 1, "compose main shape changed: could not find hardcoded `let source`"

# Emit the verify obligation records right after the parse gate, then return.
needle = "    if vec_len(it) < 1 { return 2; }"
assert needle in src, "compose main shape changed: missing parse gate"
inject = (
    needle + "\n"
    '    let _vc_out: string = verify_all_fns(it, id1, id2, id3, id4, id5, fpn, fcb, fcr,\n'
    '        bet, bed1, bed2, bed3, bed4, pp, tags, source, starts, ends);\n'
    '    write_file("/dev/stdout", _vc_out);\n'
    '    return 0;'
)
src = src.replace(needle, inject, 1)

pathlib.Path(sys.argv[2]).write_text(src)
print("build-sv0-megatu-verify-native: derived verify compose main", file=sys.stderr)
PY

# ── 2. Assemble the pipeline modules + verify_vcgen + the verify main ────────
#    (compiler's manifest, with lib/verify_vcgen.sv0 appended — the verification
#    module joins the mega-TU so verify_all_fns is available to the main.)
grep -vE '^\s*(#|$)' "$MODULES" > "$MANIFEST"
echo "lib/verify_vcgen.sv0" >> "$MANIFEST"
python3 "$ROOT/scripts/assemble-sv0-megaTU.py" --manifest "$MANIFEST" --main "$VERIFY_MAIN" --out "$TU" >/dev/null
echo "build-sv0-megatu-verify-native: assembled verify mega-TU -> $TU" >&2

# ── 3. One-time bootstrap: SML compiles the mega-TU sv0 -> C ─────────────────
if ! make -C "$SV0C" heap >/dev/null 2>&1; then
  echo "build-sv0-megatu-verify-native: error: sv0c make heap failed" >&2
  exit 1
fi
if ! sml "@SMLload=$SV0C/build/sv0c" "$TU" > "$EMIT_C" 2>/dev/null; then
  echo "build-sv0-megatu-verify-native: error: SML emit of the verify mega-TU failed" >&2
  exit 1
fi

# ── 4. cc the emitted C into the native verify binary ────────────────────────
_CC="${CC:-cc}"
if ! "$_CC" -std=c99 -O0 -I"$SV0C/runtime" -o "$NATIVE" "$EMIT_C" "$SV0C/runtime/sv0_runtime.c" 2>/dev/null; then
  echo "build-sv0-megatu-verify-native: error: cc of the emitted verify mega-TU C failed" >&2
  exit 1
fi
echo "build-sv0-megatu-verify-native: wrote $NATIVE (native verify binary)" >&2

# ── 5. Wrapper: arg -> /tmp/.sv0_verify_path -> native binary (records to stdout) ─
cat >"$WRAP" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTL="/tmp/.sv0_verify_path"
printf '%s\n' "${1:?missing argument: <file.sv0>}" > "$CTL"
trap 'printf "" > "$CTL"' EXIT
"$_HERE/sv0-megatu-verify-native"
EOS
chmod +x "$WRAP"
echo "build-sv0-megatu-verify-native: wrote $WRAP (verify wrapper)" >&2
echo "build-sv0-megatu-verify-native: done" >&2
