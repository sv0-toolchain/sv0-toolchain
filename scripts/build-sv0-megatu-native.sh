#!/usr/bin/env bash
# P2 / Phase B (l0-closure-roadmap.md): native FULL-COMPOSE self-host compiler.
#
# Unlike build-sv0-self-host-compiler.sh's per-file native binary (from the single
# self-contained lib/driver.sv0), this composes the WHOLE multi-module compiler — all
# 18 lib/*.sv0 pipeline modules assembled into one mega-TU (the (A) model per
# native-compose-tradeoffs.md) plus the megaTU-main.sv0 compose main — into a native
# `cc` binary that honors the SV0_SELF_HOST_COMPILER contract (argv[1] = .sv0 path,
# C to stdout).
#
# Bar is BEHAVIORAL parity (emit + cc + run), NOT byte-identical vs SML: the composed
# emit diverges from SML's C by design (measured ~109% line churn on real modules), so
# self-host-sv0-loop (emit+cc+run + self-determinism) is the acceptance surface, not the
# vs-SML byte diff. See sv0c/doc/archive/native-compose-tradeoffs.md.
#
# Build is one-time bootstrap (SML compiles the mega-TU sv0 -> C, then cc); the RESULT
# runs with no SML heap. Produces:
#   build/sv0-megatu-native            — the native composed compiler (reads /tmp/.sv0_drv_path, C to stdout)
#   build/sv0-megatu-compiler-native   — wrapper adapting argv[1] -> /tmp/.sv0_drv_path -> the binary
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

MAIN_SRC="$SV0C/lib/megaTU-main.sv0"
CLI_MAIN="$BUILD/megaTU-native-main.sv0"
TU="$BUILD/megaTU-native.sv0"
EMIT_C="$BUILD/megaTU-native.c"
NATIVE="$BUILD/sv0-megatu-native"
WRAP="$BUILD/sv0-megatu-compiler-native"

# ── 1. Derive a CLI compose main from the committed megaTU-main.sv0 ──────────
#    - source: read the path from /tmp/.sv0_drv_path (strip trailing newline), read_file it
#    - output: write the emitted C to /dev/stdout (the SV0_SELF_HOST_COMPILER contract)
python3 - "$MAIN_SRC" "$CLI_MAIN" <<'PY'
import re, sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text()

# Replace the hardcoded smoke source with a CLI read of /tmp/.sv0_drv_path.
# The control file holds EITHER a single .sv0 path (file mode) OR "--project <dir>"
# (project mode -> collision-free source-concat of every .sv0 under <dir> via
# link_project_concat_sources_from_dir; PC-3b.5). One control file => no stale
# cross-contamination with the single-file corpus/self-host harnesses.
cli_read = (
    'let _drv_p: string = read_file("/tmp/.sv0_drv_path");\n'
    '    let _drv_n: i32 = string_len(_drv_p);\n'
    '    let _drv_c: string = if _drv_n > 0 {\n'
    '        if string_char_at(_drv_p, _drv_n - 1) == 10 {\n'
    '            string_substr(_drv_p, 0, _drv_n - 1)\n'
    '        } else { _drv_p }\n'
    '    } else { _drv_p };\n'
    '    let _drv_cn: i32 = string_len(_drv_c);\n'
    '    let _is_proj: bool = if _drv_cn >= 10 {\n'
    '        string_eq(string_substr(_drv_c, 0, 10), "--project ")\n'
    '    } else { false };\n'
    '    let source: string = if _is_proj {\n'
    '        link_project_concat_sources_from_dir(string_substr(_drv_c, 10, _drv_cn - 10))\n'
    '    } else {\n'
    '        expand_from_file(_drv_c)\n'
    '    };'
)
src, n = re.subn(r'let source: string = "[^"]*";', cli_read, src, count=1)
assert n == 1, "compose main shape changed: could not find hardcoded `let source`"

# Emit the composed C to stdout, just before the empty-C phase-5 gate.
needle = "    if string_len(c) == 0 { return 5; }"
assert needle in src, "compose main shape changed: missing empty-C gate"
src = src.replace(needle, '    write_file("/dev/stdout", c);\n' + needle, 1)

pathlib.Path(sys.argv[2]).write_text(src)
print("build-sv0-megatu-native: derived CLI compose main", file=sys.stderr)
PY

# ── 2. Assemble the 18 real modules + CLI compose main into one mega-TU ──────
python3 "$ROOT/scripts/assemble-sv0-megaTU.py" --root "$ROOT" --main "$CLI_MAIN" --out "$TU" >/dev/null
echo "build-sv0-megatu-native: assembled mega-TU -> $TU" >&2

# ── 3. One-time bootstrap: SML compiles the mega-TU sv0 -> C ─────────────────
if ! make -C "$SV0C" heap >/dev/null 2>&1; then
  echo "build-sv0-megatu-native: error: sv0c make heap failed" >&2
  exit 1
fi
if ! sml "@SMLload=$SV0C/build/sv0c" "$TU" > "$EMIT_C" 2>/dev/null; then
  echo "build-sv0-megatu-native: error: SML emit of the mega-TU failed" >&2
  exit 1
fi

# ── 4. cc the emitted C into the native composed compiler ────────────────────
_CC="${CC:-cc}"
if ! "$_CC" -std=c99 -O0 -I"$SV0C/runtime" -o "$NATIVE" "$EMIT_C" "$SV0C/runtime/sv0_runtime.c" 2>/dev/null; then
  echo "build-sv0-megatu-native: error: cc of the emitted mega-TU C failed" >&2
  exit 1
fi
echo "build-sv0-megatu-native: wrote $NATIVE (native composed compiler)" >&2

# ── 5. Wrapper: args -> /tmp/.sv0_drv_path -> native binary (C to stdout) ──────
#    `wrapper <file.sv0>`        -> file mode
#    `wrapper --project <dir>`   -> project mode (source-concat every .sv0 under dir)
cat >"$WRAP" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTL="/tmp/.sv0_drv_path"
printf '%s\n' "${*:?missing argument: <file.sv0> | --project <dir>}" > "$CTL"
trap 'printf "" > "$CTL"' EXIT
"$_HERE/sv0-megatu-native"
EOS
chmod +x "$WRAP"
echo "build-sv0-megatu-native: wrote $WRAP (native full-compose wrapper)" >&2

# ── 6. Init the control file empty (test-mode default) ───────────────────────
printf "" > /tmp/.sv0_drv_path
echo "build-sv0-megatu-native: done — point SV0_SELF_HOST_COMPILER at $WRAP for the native full-compose loop" >&2
