#!/usr/bin/env bash
# P4 / Phase D1b (l0-closure-roadmap.md): native VM bytecode emitter.
#
# STATUS: builds + runs, but the emitted binary panics (vec index out of bounds)
# on any input pending the IR-ADT bridge. lowering's and vm_codegen's Expr/Value
# ADTs have DRIFTED (Instr tags match; Expr/Value tags are skewed and Value is
# structurally different — VBoolTrue/VBoolFalse vs VBool(bool), plus vm-only
# VFloat/IndexAccess), so vm_codegen.emit_instrs misreads lower's boxed sub-exprs.
# See l0-closure-roadmap.md § D1b for the two fix paths (converge the ADTs, or an
# additive re-tagging translator). This recipe is the infra; the bridge is next.
#
# Derives a VM compose main from lib/megaTU-main.sv0 (reusing its exact phases 1-5:
# tokenize->parse->resolve->check->lower, and its megatu_find_item_by_label /
# megatu_type_root_name_tok helpers) but replaces phase 6 (the C emit) with the VM
# tail: bridge lower's out_blocks (interleaved boxed quads) -> emit_program's 4
# parallel block vecs (labels + box_deref instrs + per-fn param name/cty vecs
# reconstructed from the parse arenas) -> vm_codegen.emit_program -> bytecode.
# encode_strings -> bytecode.encode_file -> write_bytes("/dev/stdout", ...).
#
# Assembles the 18 modules + this VM main into one mega-TU, SML->C->cc once (native,
# no SML at runtime). Produces build/sv0-megatu-vm-native (reads the source path from
# /tmp/.sv0_drv_path, writes the .sv0b to stdout).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SV0C="$ROOT/sv0c"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

MAIN_SRC="$SV0C/lib/megaTU-main.sv0"
VM_MAIN="$BUILD/megaTU-vm-main.sv0"
TU="$BUILD/megaTU-vm.sv0"
EMIT_C="$BUILD/megaTU-vm.c"
NATIVE="$BUILD/sv0-megatu-vm-native"

python3 - "$MAIN_SRC" "$VM_MAIN" <<'PY'
import re, sys, pathlib
src = pathlib.Path(sys.argv[1]).read_text()

# 1. CLI source read (path in /tmp/.sv0_drv_path).
cli_read = (
    'let _drv_p: string = read_file("/tmp/.sv0_drv_path");\n'
    '    let _drv_n: i32 = string_len(_drv_p);\n'
    '    let _drv_path: string = if _drv_n > 0 {\n'
    '        if string_char_at(_drv_p, _drv_n - 1) == 10 {\n'
    '            string_substr(_drv_p, 0, _drv_n - 1)\n'
    '        } else { _drv_p }\n'
    '    } else { _drv_p };\n'
    '    let source: string = read_file(_drv_path);'
)
src, n = re.subn(r'let source: string = "[^"]*";', cli_read, src, count=1)
assert n == 1, "compose main shape changed: `let source`"

# 2. Replace phase 6 (C emit call + gate) with the VM tail. Falls through to the
#    existing `return 0;` at end of main (no return here). `td` from lower is unused
#    in the VM path but kept (lower fills out_blocks).
needle = (
    '    let c: string = megatu_emit_program(td, out_blocks, source, starts, ends,\n'
    '                                        it, id1, id2, id3, id5, fpn,\n'
    '                                        fpt, frt, ptt, ptd1, ptd2, pp);\n'
    '    if string_len(c) == 0 { return 5; }'
)
assert needle in src, "compose main phase-6 shape changed"
vm_tail = r'''    /* VM tail (P4/D1b): bridge lower's out_blocks -> emit_program's 4 parallel
       block vecs, then vm_codegen.emit_program -> bytecode.encode_strings /
       encode_file -> write_bytes. Reuses megatu_find_item_by_label /
       megatu_type_root_name_tok (defined above for the C emit). */
    let vbl: Vec<i32> = vec_new();
    let vbpn: Vec<i32> = vec_new();
    let vbpc: Vec<i32> = vec_new();
    let vbi: Vec<i32> = vec_new();
    let vnb: i32 = vec_len(out_blocks) / 4;
    let mut vbx: i32 = 0;
    while vbx < vnb {
        let vlabel: i32 = vec_get(out_blocks, vbx * 4 + 0);
        vec_push(vbl, vlabel);
        let vins: Vec<i32> = box_deref(vec_get(out_blocks, vbx * 4 + 3));
        vec_push(vbi, vins);
        let vitem: i32 = megatu_find_item_by_label(it, id1, vlabel);
        let vpn: Vec<i32> = vec_new();
        let vpc: Vec<i32> = vec_new();
        if vitem >= 0 {
            let vpcount: i32 = vec_get(id3, vitem);
            let vbase: i32 = vec_get(id5, vitem);
            let mut vk: i32 = 0;
            while vk < vpcount {
                vec_push(vpn, vec_get(fpn, vbase + vk));
                vec_push(vpc, megatu_type_root_name_tok(
                    vec_get(fpt, vbase + vk), ptt, ptd1, ptd2, pp));
                vk = vk + 1;
            }
        }
        vec_push(vbpn, vpn);
        vec_push(vbpc, vpc);
        vbx = vbx + 1;
    }
    let vpool: Vec<i32> = vec_new();
    let vft: Vec<i32> = vec_new();
    let vfc: i32 = vm_codegen_emit_program(it, id1, ifc, ivm, vbl, vbpn, vbpc, vbi,
                                source, starts, ends, vpool, vft);
    if vfc < 0 { return 5; }
    let vstrbuf: Vec<i32> = vec_new();
    let vstrlen: i32 = encode_strings(vpool, source, starts, ends, vstrbuf);
    let vout: Vec<i32> = vec_new();
    let vtotal: i32 = encode_file(vstrbuf, vstrlen, vft, vout);
    write_bytes("/dev/stdout", vout);'''
src = src.replace(needle, vm_tail, 1)
pathlib.Path(sys.argv[2]).write_text(src)
print("build-sv0-megatu-vm-native: derived VM compose main", file=sys.stderr)
PY

python3 "$ROOT/scripts/assemble-sv0-megaTU.py" --root "$ROOT" --main "$VM_MAIN" --out "$TU" >/dev/null
echo "build-sv0-megatu-vm-native: assembled mega-TU -> $TU" >&2

if ! make -C "$SV0C" heap >/dev/null 2>&1; then
  echo "build-sv0-megatu-vm-native: error: sv0c make heap failed" >&2; exit 1
fi
if ! sml "@SMLload=$SV0C/build/sv0c" "$TU" > "$EMIT_C" 2>/dev/null; then
  echo "build-sv0-megatu-vm-native: error: SML emit of the VM mega-TU failed" >&2; exit 1
fi
_CC="${CC:-cc}"
if ! "$_CC" -std=c99 -O0 -I"$SV0C/runtime" -o "$NATIVE" "$EMIT_C" "$SV0C/runtime/sv0_runtime.c" 2>/dev/null; then
  echo "build-sv0-megatu-vm-native: error: cc of the emitted VM C failed" >&2; exit 1
fi
echo "build-sv0-megatu-vm-native: wrote $NATIVE (native VM bytecode emitter)" >&2
printf "" > /tmp/.sv0_drv_path
echo "build-sv0-megatu-vm-native: done — set /tmp/.sv0_drv_path then run $NATIVE (>.sv0b on stdout)" >&2
