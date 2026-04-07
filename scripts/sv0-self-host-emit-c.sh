#!/usr/bin/env bash
# Bootstrap implementation of the SV0_SELF_HOST_COMPILER contract used by
# ./scripts/sv0 self-host-sv0-loop: given one absolute path to a .sv0 file,
# print C to stdout (same behavior as `sml @SMLload=build/sv0c <path>` from sv0c/).
# When a native compiler built from sv0 sources exists, point SV0_SELF_HOST_COMPILER
# at that binary (or a wrapper) instead to close the semantic sv0→sv0 loop.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
file="${1:?usage: sv0-self-host-emit-c.sh /absolute/path/to/file.sv0}"
[[ -f "$file" ]] || {
  echo "sv0-self-host-emit-c.sh: not found: $file" >&2
  exit 1
}
(cd "$SV0C" && sml "@SMLload=build/sv0c" "$file")
