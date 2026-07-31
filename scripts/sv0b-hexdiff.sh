#!/usr/bin/env bash
# P4 / Phase D0 (l0-closure-roadmap.md): byte-diff instrumentation for .sv0b files.
# Compares two SV0B bytecode files and reports the FIRST divergence as an
# offset + field guess (which SV0B section the byte falls in), so byte-exact
# convergence of a native VM emitter vs the SML golden reads as "string-pool @ N"
# / "code @ M" rather than raw byte deltas.
#
# SV0B layout (sv0doc/bytecode/format.md; bytecode.sv0 encode_*):
#   [0..3]   magic "SV0B" (0x53 0x56 0x30 0x42)
#   [4]      version (u8)
#   [5]      reserved/pad
#   [6..9]   str_section_len (u32 LE)        <- encode_u32_le after encode_header
#   [10..]   string section (str_section_len bytes)
#   then     function table + code sections
# The exact post-string layout is emitter-defined; this tool orients by magic +
# version + str_section_len and otherwise reports raw offset + hex context.
set -euo pipefail

usage() { echo "usage: sv0b-hexdiff.sh <a.sv0b> <b.sv0b>   (a = reference/golden, b = candidate)" >&2; exit 2; }
[ "$#" -eq 2 ] || usage
A="$1"; B="$2"
[ -f "$A" ] || { echo "sv0b-hexdiff: not found: $A" >&2; exit 2; }
[ -f "$B" ] || { echo "sv0b-hexdiff: not found: $B" >&2; exit 2; }

sa=$(wc -c < "$A" | tr -d ' '); sb=$(wc -c < "$B" | tr -d ' ')
echo "A (ref)  = $A  ($sa bytes)"
echo "B (cand) = $B  ($sb bytes)"

# Orient by the header of the reference.
hdr=$(xxd -p -l 10 "$A" 2>/dev/null)
magic=${hdr:0:8}
if [ "$magic" = "53563042" ]; then
  ver=$((16#${hdr:8:2}))
  # str_section_len: bytes [6..9] little-endian
  b6=${hdr:12:2}; b7=${hdr:14:2}; b8=${hdr:16:2}; b9=${hdr:18:2}
  strlen=$(( 16#$b6 + 16#$b7*256 + 16#$b8*65536 + 16#$b9*16777216 ))
  str_start=10; str_end=$(( str_start + strlen ))
  echo "header: magic=SV0B version=$ver str_section_len=$strlen (string bytes [$str_start..$str_end))"
else
  echo "header: A is not an SV0B file (magic=$magic); reporting raw offsets only"
  str_start=-1; str_end=-1
fi

section_of() {  # $1 = offset -> section label
  local off="$1"
  if [ "$str_start" -lt 0 ]; then echo "raw"; return; fi
  if [ "$off" -lt 4 ]; then echo "magic"; elif [ "$off" -lt 6 ]; then echo "version/pad";
  elif [ "$off" -lt 10 ]; then echo "str_section_len(u32)";
  elif [ "$off" -lt "$str_end" ]; then echo "string-section@$(( off - str_start ))";
  else echo "function-table/code@$(( off - str_end ))"; fi
}

if cmp -s "$A" "$B"; then
  echo "RESULT: byte-identical ✓"
  exit 0
fi

# First differing byte (cmp is 1-indexed).
first=$(cmp "$A" "$B" 2>/dev/null | sed -E 's/.* differ: byte ([0-9]+),.*/\1/' | head -1)
if [ -z "$first" ]; then
  # length-only difference (one is a prefix of the other)
  echo "RESULT: differ — one file is a prefix of the other (lengths $sa vs $sb)"
  exit 1
fi
off=$(( first - 1 ))
echo "RESULT: differ — first at byte $off (0x$(printf '%x' "$off")) in $(section_of "$off")"
total_diff=$(cmp -l "$A" "$B" 2>/dev/null | wc -l | tr -d ' ')
echo "total differing bytes: $total_diff"
echo "--- context (16 bytes around 0x$(printf '%x' "$off")) ---"
ctx_start=$(( off > 8 ? off - 8 : 0 ))
echo "A: $(xxd -s "$ctx_start" -l 16 "$A")"
echo "B: $(xxd -s "$ctx_start" -l 16 "$B")"
exit 1
