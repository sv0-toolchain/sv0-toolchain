#!/usr/bin/env bash
# Native sv0 driver ↔ SML behavioral parity over sv0c/lib/self-host-sv0-loop.list.
#
# The self-host-sv0-loop third leg diffs emitted C *textually*, which two different
# compilers can never match: the native driver inlines expression trees
# (`return ((1+2)+3)`) while the SML heap lowers to IR temporaries
# (`_sv0t0 = (1+2); ...`). The principled parity bar for "native vs SML" is
# BEHAVIORAL: for each seed, emit C with both compilers, cc+run both, and require
# identical stdout and exit status. This script is the durable proof for the
# milestone-3 "self-compile (native semantic third leg)" evidence row.
#
# Usage: ./scripts/sv0-native-behavioral-parity.sh
# Env:   CC (default cc), SV0_DRIVER_NATIVE (default build/sv0-driver-native).
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SV0C="$ROOT/sv0c"
RT="$SV0C/runtime"
LIST="$SV0C/lib/self-host-sv0-loop.list"
CC="${CC:-cc}"
NATIVE="${SV0_DRIVER_NATIVE:-$ROOT/build/sv0-driver-native}"

command -v sml >/dev/null 2>&1 || { echo "native-parity: sml not found" >&2; exit 1; }
command -v "$CC" >/dev/null 2>&1 || { echo "native-parity: C compiler '$CC' not found" >&2; exit 1; }
[[ -f "$LIST" ]] || { echo "native-parity: missing $LIST" >&2; exit 1; }
if [[ ! -x "$NATIVE" ]]; then
  echo "native-parity: missing native driver $NATIVE" >&2
  echo "  build it with: bash scripts/build-sv0-self-host-compiler.sh" >&2
  exit 1
fi
[[ -f "$SV0C/build/sv0c" || -L "$SV0C/build/sv0c" ]] || { echo "native-parity: missing SML heap $SV0C/build/sv0c (run: make -C sv0c heap)" >&2; exit 1; }

tmp="$(mktemp -d)"
cleanup() { rm -rf "$tmp"; }
trap cleanup EXIT

# NEX-055c/REL-004: SV0_DRV_REQUEST (a per-invocation env var driver.sv0's own
# fn main() has preferred over the legacy /tmp/.sv0_drv_path control file since
# step 2) replaces the old write+run+reset dance -- no shared file, no reset.
emit_native() { # <abs> <out>
  SV0_DRV_REQUEST="$1" "$NATIVE" > "$2" 2>/dev/null
}

total=0 pass=0
fails=()
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ -z "${line//[[:space:]]/}" ]] && continue
  rel="${line//[[:space:]]/}"
  abs="$SV0C/$rel"
  [[ -f "$abs" ]] || { echo "native-parity: missing source $abs" >&2; exit 1; }
  total=$((total + 1))
  stem="$(basename "$rel" .sv0)"

  if ! sml "@SMLload=$SV0C/build/sv0c" "$abs" > "$tmp/$stem.sml.c" 2>/dev/null; then
    fails+=("$rel: SML emit failed"); continue
  fi
  if ! emit_native "$abs" "$tmp/$stem.nat.c"; then
    fails+=("$rel: native emit failed (panic/nonzero)"); continue
  fi
  if ! "$CC" -std=c99 -O0 -I "$RT" "$tmp/$stem.sml.c" "$RT/sv0_runtime.c" -o "$tmp/$stem.sml" 2>/dev/null; then
    fails+=("$rel: SML C did not compile"); continue
  fi
  if ! "$CC" -std=c99 -O0 -I "$RT" "$tmp/$stem.nat.c" "$RT/sv0_runtime.c" -o "$tmp/$stem.nat" 2>/dev/null; then
    fails+=("$rel: native C did not compile"); continue
  fi
  "$tmp/$stem.sml" > "$tmp/$stem.sml.out" 2>&1; so=$?
  "$tmp/$stem.nat" > "$tmp/$stem.nat.out" 2>&1; no=$?
  if [[ "$so" -eq "$no" ]] && diff -q "$tmp/$stem.sml.out" "$tmp/$stem.nat.out" >/dev/null; then
    pass=$((pass + 1))
  else
    fails+=("$rel: behavior differs (exit sml=$so nat=$no)")
  fi
done < "$LIST"

if ((${#fails[@]} > 0)); then
  echo "native-parity: FAIL — $pass/$total behavioral parity" >&2
  printf '  - %s\n' "${fails[@]}" >&2
  exit 1
fi
echo "native-parity: OK — $total/$total native driver ↔ SML behavioral parity (emit+cc+run, identical stdout+exit)"
