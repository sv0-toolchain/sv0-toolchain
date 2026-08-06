#!/usr/bin/env bash
# SV0_VM_BYTECODE_EMITTER adapter for the native mega-TU VM emitter (P4/D2).
#
# The tier-2 byte-parity leg (scripts/sv0 run_vm_parity_tier2_emit_compare) invokes
# the emitter as `<emitter> <rel>` and expects it to write sv0c/build/vm/<stem>.sv0b,
# then cmp's that against test/vm-parity/golden/sml/<stem>.sv0b. The native emitter
# (build/sv0-megatu-vm-native) instead reads the source path from /tmp/.sv0_drv_path
# and writes the .sv0b to stdout, so this wrapper bridges the two: build the native
# emitter on demand, then run it for one manifest path into build/vm/<stem>.sv0b.
#
# The native emitter is byte-identical to the SML --target=vm golden for every
# tier-2 program (all 18 mega-TU compiler modules as of P4/D2), so a mismatch
# here is a real regression in the sv0 VM emitter or its lowering.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
NATIVE="$ROOT/build/sv0-megatu-vm-native"

rel="${1:?usage: sv0-vm-tier2-native-emitter.sh <path-relative-to-sv0c>}"
if [[ ! -f "$SV0C/$rel" ]]; then
  echo "sv0-vm-tier2-native-emitter.sh: not found: $SV0C/$rel" >&2
  exit 1
fi

# Build (or rebuild) the native emitter once; subsequent manifest paths reuse it.
if [[ ! -x "$NATIVE" ]]; then
  bash "$ROOT/scripts/build-sv0-megatu-vm-native.sh" >&2
fi
if [[ ! -x "$NATIVE" ]]; then
  echo "sv0-vm-tier2-native-emitter.sh: native emitter missing after build: $NATIVE" >&2
  exit 1
fi

stem="$(basename "$rel" .sv0)"
mkdir -p "$SV0C/build/vm"
# The native emitter reads the source path from /tmp/.sv0_drv_path (CLI-mode).
printf '%s' "$SV0C/$rel" > /tmp/.sv0_drv_path
"$NATIVE" > "$SV0C/build/vm/${stem}.sv0b"
