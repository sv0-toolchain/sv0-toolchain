#!/usr/bin/env bash
# Regenerate sv0c/test/vm-parity/golden/sml/*.sv0b from the SML bootstrap (--target=vm).
# Run from sv0-toolchain root; requires SML/NJ. Commit updated binaries in sv0c with any compiler change.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
MANIFEST="$SV0C/test/vm-parity/manifest.txt"
OUT="$SV0C/test/vm-parity/golden/sml"

if ! command -v sml >/dev/null 2>&1; then
  echo "capture_vm_parity_goldens: sml not in PATH" >&2
  exit 1
fi
if [[ ! -f "$MANIFEST" ]]; then
  echo "capture_vm_parity_goldens: missing $MANIFEST" >&2
  exit 1
fi

mkdir -p "$SV0C/build/vm" "$OUT"
n=0
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -z "${line//[[:space:]]/}" ]] && continue
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  rel="${line//[[:space:]]/}"
  stem=$(basename "$rel" .sv0)
  src="$SV0C/$rel"
  if [[ ! -f "$src" ]]; then
    echo "capture_vm_parity_goldens: missing source $src" >&2
    exit 1
  fi
  log="$(mktemp)"
  if ! (cd "$SV0C" && echo "CM.make \"sources.cm\"; Main.main ((), [\"--target=vm\", \"$rel\"]);" | sml >"$log" 2>&1); then
    tail -40 "$log"
    rm -f "$log"
    exit 1
  fi
  if grep -q 'Error:' "$log"; then
    tail -40 "$log"
    rm -f "$log"
    exit 1
  fi
  rm -f "$log"
  built="$SV0C/build/vm/${stem}.sv0b"
  if [[ ! -f "$built" ]]; then
    echo "capture_vm_parity_goldens: expected $built after compile ($rel)" >&2
    exit 1
  fi
  cp -f "$built" "$OUT/${stem}.sv0b"
  n=$((n + 1))
  echo "captured $stem.sv0b"
done <"$MANIFEST"

echo "capture_vm_parity_goldens: wrote $n file(s) under $OUT"
