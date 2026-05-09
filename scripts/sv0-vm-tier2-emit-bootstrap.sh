#!/usr/bin/env bash
# Bootstrap surrogate for M3-S-045 SV0_VM_BYTECODE_EMITTER: emits build/vm/<stem>.sv0b via the
# SML heap compiler (--target=vm), matching tier-1 reference output. Use until a native compiler
# built from sv0 sources implements the same VM emit contract.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
rel="${1:?usage: sv0-vm-tier2-emit-bootstrap.sh <path-relative-to-sv0c>}"
if [[ "$rel" == *'"'* ]]; then
  echo "sv0-vm-tier2-emit-bootstrap.sh: path must not contain double-quote" >&2
  exit 1
fi
[[ -f "$SV0C/$rel" ]] || {
  echo "sv0-vm-tier2-emit-bootstrap.sh: not found: $SV0C/$rel" >&2
  exit 1
}
if ! (cd "$SV0C" && make heap >/dev/null 2>&1); then
  echo "sv0-vm-tier2-emit-bootstrap.sh: sv0c make heap failed" >&2
  exit 1
fi
log="$(mktemp)"
set +e
(cd "$SV0C" && echo "CM.make \"sources.cm\"; OS.Process.exit(Main.main ((), [\"--target=vm\", \"$rel\"]));" | sml >"$log" 2>&1)
ec=$?
set -e
if [[ "$ec" -ne 0 ]]; then
  tail -40 "$log" >&2
  rm -f "$log"
  exit "$ec"
fi
rm -f "$log"
stem=$(basename "$rel" .sv0)
[[ -f "$SV0C/build/vm/${stem}.sv0b" ]] || {
  echo "sv0-vm-tier2-emit-bootstrap.sh: expected $SV0C/build/vm/${stem}.sv0b" >&2
  exit 1
}
