#!/usr/bin/env bash
# M3-S-047 / P2: materialize canonical SV0_SELF_HOST_COMPILER paths.
#
# Produces two artifacts:
#   build/sv0-self-host-compiler         — SML-heap wrapper (bootstrap delegate, CI default)
#   build/sv0-driver-native              — native binary compiled from lib/driver.sv0 via SML→C→cc
#   build/sv0-self-host-compiler-native  — wrapper around sv0-driver-native (for manual native testing)
#
# The native binary reads its input path from /tmp/.sv0_drv_path (written by the wrapper
# before each invocation; empty = test mode). This script initialises that file as empty
# so that test-mode invocations of the native binary work without the wrapper.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

# ── 1. SML-heap bootstrap delegate (CI default) ─────────────────────────────
OUT="$BUILD/sv0-self-host-compiler"
cat >"$OUT" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_HERE/.." && pwd)"
exec "$ROOT/scripts/sv0-self-host-emit-c.sh" "$@"
EOS
chmod +x "$OUT"
echo "build-sv0-self-host-compiler: wrote $OUT (bootstrap delegate)" >&2

# ── 2. Native binary from lib/driver.sv0 (P2) ───────────────────────────────
NATIVE="$BUILD/sv0-driver-native"
EMIT_TMP="$(mktemp /tmp/sv0_driver_emit_XXXXXX.c)"
trap 'rm -f "$EMIT_TMP"' EXIT

echo "build-sv0-self-host-compiler: building native binary from lib/driver.sv0..." >&2

# 2a. Ensure SML heap exists
if ! make -C "$SV0C" heap >/dev/null 2>&1; then
  echo "build-sv0-self-host-compiler: warning: sv0c make heap failed; skipping native binary" >&2
else
  # 2b. Emit C from driver.sv0 via SML bootstrap
  if ! (cd "$SV0C" && sml "@SMLload=build/sv0c" lib/driver.sv0 >"$EMIT_TMP" 2>/dev/null); then
    echo "build-sv0-self-host-compiler: warning: SML emit of driver.sv0 failed; skipping native binary" >&2
  else
    # 2c. Compile emitted C with cc
    _CC="${CC:-cc}"
    if "$_CC" -std=c99 -O0 -I"$SV0C/runtime" -o "$NATIVE" "$EMIT_TMP" "$SV0C/runtime/sv0_runtime.c" 2>/dev/null; then
      echo "build-sv0-self-host-compiler: wrote $NATIVE (native driver)" >&2

      # 2d. Wrapper that adapts argv[1] → /tmp/.sv0_drv_path → native binary
      NATIVE_WRAP="$BUILD/sv0-self-host-compiler-native"
      cat >"$NATIVE_WRAP" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTL="/tmp/.sv0_drv_path"
printf '%s\n' "${1:?missing argument: path to .sv0 file}" > "$CTL"
trap 'printf "" > "$CTL"' EXIT
"$_HERE/sv0-driver-native"
EOS
      chmod +x "$NATIVE_WRAP"
      echo "build-sv0-self-host-compiler: wrote $NATIVE_WRAP (native wrapper)" >&2
    else
      echo "build-sv0-self-host-compiler: warning: cc compile of driver.sv0 emitted C failed; skipping native binary" >&2
    fi
  fi
fi

# ── 3. Initialise control file empty so native binary runs in test mode ──────
printf "" > /tmp/.sv0_drv_path

echo "build-sv0-self-host-compiler: done (see sv0c/doc/native-self-host-compiler-recipe.md)" >&2
