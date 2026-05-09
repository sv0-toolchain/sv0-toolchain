#!/usr/bin/env bash
# M3-S-052: default sv0c smoke — heap image + SV0_SELF_HOST_COMPILER emission (one bootstrap list file).
# Full CM.make of sml-legacy remains `make -C sv0c legacy-bootstrap-check`.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
cd "$SV0C"
make heap >/dev/null
if [[ ! -x "$ROOT/build/sv0-self-host-compiler" ]]; then
  bash "$ROOT/scripts/build-sv0-self-host-compiler.sh"
fi
export SV0_SELF_HOST_COMPILER="${SV0_SELF_HOST_COMPILER:-$ROOT/build/sv0-self-host-compiler}"
first=""
if [[ -f "$SV0C/lib/bootstrap-sources.list" ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    [[ -z "${line//[[:space:]]/}" ]] && continue
    first="${line//[[:space:]]/}"
    break
  done <"$SV0C/lib/bootstrap-sources.list"
fi
if [[ -z "$first" ]]; then
  first="lib/main.sv0"
fi
abs="$SV0C/$first"
if [[ "$abs" != /* ]]; then
  abs="$(cd "$(dirname "$abs")" && pwd)/$(basename "$abs")"
fi
if [[ ! -f "$abs" ]]; then
  echo "sv0-smoke-self-host-compiler: missing $abs" >&2
  exit 1
fi
tmp="$(mktemp)"
log="$(mktemp)"
cleanup() {
  rm -f "$tmp" "$log"
}
trap cleanup EXIT
set +e
"$SV0_SELF_HOST_COMPILER" "$abs" >"$tmp" 2>"$log"
ec=$?
set -e
if [[ "$ec" -ne 0 ]] || grep -q 'Error:' "$log"; then
  tail -40 "$log" >&2
  exit 1
fi
if ! grep -q '#include' "$tmp"; then
  echo "sv0-smoke-self-host-compiler: emitted C missing #include" >&2
  exit 1
fi
exit 0
