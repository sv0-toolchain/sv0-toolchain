#!/usr/bin/env bash
# M3-S-047: materialize a canonical path suitable for SV0_SELF_HOST_COMPILER (bootstrap delegate).
# Writes build/sv0-self-host-compiler — a wrapper around scripts/sv0-self-host-emit-c.sh (SML heap).
# Semantic closure with a binary compiled from sv0 sources replaces this wrapper when ready.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/build/sv0-self-host-compiler"
mkdir -p "$(dirname "$OUT")"
cat >"$OUT" <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$_HERE/.." && pwd)"
exec "$ROOT/scripts/sv0-self-host-emit-c.sh" "$@"
EOS
chmod +x "$OUT"
echo "build-sv0-self-host-compiler: wrote $OUT (bootstrap delegate — see sv0c/doc/native-self-host-compiler-recipe.md)" >&2
