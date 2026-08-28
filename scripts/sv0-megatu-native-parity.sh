#!/usr/bin/env bash
# P2 / Phase B3 (l0-closure-roadmap.md): build the NATIVE full-compose compiler
# (scripts/build-sv0-megatu-native.sh) and prove BEHAVIORAL parity over the
# self-host-sv0-loop corpus using that binary — with NO SML heap at runtime.
#
# For each seed: emit C twice via the native compiler (cmp the two = determinism),
# cc-compile, and run (exit 0). This is the native analog of sv0-megatu-corpus-parity.sh
# (which uses the SML-built corpus binary): it validates that the RECIPE produces a
# working self-hosting compiler. The bar is behavioral, not byte-identical vs SML
# (measured ~109% emit divergence — see the roadmap Phase B / the byte-identical spike).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
SV0C="$ROOT/sv0c"
RT="$SV0C/runtime"
LIST="$SV0C/lib/self-host-sv0-loop.list"
WRAP="$ROOT/build/sv0-megatu-compiler-native"

# 1. Build the native full-compose compiler (SML->C->cc once; runs with no SML heap).
echo "sv0-megatu-native-parity: building the native full-compose compiler..." >&2
"$ROOT/scripts/build-sv0-megatu-native.sh"
[ -x "$WRAP" ] || { echo "sv0-megatu-native-parity: FAIL — $WRAP not built" >&2; exit 1; }

# $WRAP (build/sv0-megatu-compiler-native) is invoked below via its own argv[1]
# contract; its internal use of /tmp/.sv0_drv_path (not yet migrated to
# SV0_DRV_REQUEST -- see the REL-004 closure plan) is entirely the wrapper's own
# concern, including resetting the file in its own EXIT trap. Nothing here needs
# to touch that file itself (NEX-055c/REL-004: the two redundant resets that used
# to duplicate the wrapper's own cleanup were removed as dead code).
NAT_C="$(mktemp /tmp/sv0_nat_XXXXXX.c)"
NAT_C2="$(mktemp /tmp/sv0_nat2_XXXXXX.c)"
NAT_BIN="$(mktemp /tmp/sv0_natbin_XXXXXX)"
trap 'rm -f "$NAT_C" "$NAT_C2" "$NAT_BIN"' EXIT

pass=0 fail=0 total=0
fails=""
while IFS= read -r f; do
  case "$f" in ''|\#*) continue;; esac
  total=$((total + 1))
  seed="$SV0C/$f"
  [ -f "$seed" ] || { fails+="MISSING $f"$'\n'; fail=$((fail+1)); continue; }
  # Emit twice (determinism).
  "$WRAP" "$seed" > "$NAT_C"  2>/dev/null || { fails+="EMIT $f"$'\n'; fail=$((fail+1)); continue; }
  "$WRAP" "$seed" > "$NAT_C2" 2>/dev/null || { fails+="EMIT2 $f"$'\n'; fail=$((fail+1)); continue; }
  [ -s "$NAT_C" ] || { fails+="EMPTY $f"$'\n'; fail=$((fail+1)); continue; }
  cmp -s "$NAT_C" "$NAT_C2" || { fails+="NONDET $f"$'\n'; fail=$((fail+1)); continue; }
  # cc + run (exit 0).
  if ! python3 "$ROOT/scripts/native_exe_canonical_compile.py" "$NAT_C" "$NAT_BIN" 2>/dev/null; then
    fails+="CC $f"$'\n'; fail=$((fail+1)); continue
  fi
  set +e; "$NAT_BIN" >/dev/null 2>&1; rex=$?; set -e
  if [ "$rex" -eq 0 ]; then pass=$((pass + 1)); else fails+="RUN(exit$rex) $f"$'\n'; fail=$((fail+1)); fi
done < "$LIST"

echo "sv0-megatu-native-parity: PASS=$pass FAIL=$fail (total=$total)"
if [ "$fail" -ne 0 ]; then
  echo "--- failures ---" >&2
  printf '%s' "$fails" >&2
  echo "sv0-megatu-native-parity: FAIL — the native full-compose compiler did not cover the corpus behaviorally" >&2
  exit 1
fi
echo "sv0-megatu-native-parity: OK ($pass/$total emit+cc+run via the native binary, no SML at runtime)"
