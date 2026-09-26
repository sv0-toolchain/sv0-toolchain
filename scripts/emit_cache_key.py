#!/usr/bin/env python3
"""Content-addressed cache key for one native-compiler emit (`.sv0` -> C).

The native mega-TU compiler's output for a single-file request is a pure function
of: the compiler itself, the source text (including everything it textually
`include`s), the request path, and the platform/cc that built it. This prints a
sha256 over exactly those, or exits 3 ("not cacheable") when the on-disk compiler
cannot be tied to its recorded inputs. Used by `sv0 self-host-sv0-loop`.

Compiler identity: the native binary is NOT byte-reproducible (the linker embeds
build-dir state), but it is the host C compiler's output for build/megaTU-native.c (which IS
deterministic) linked with the runtime -- so sha256(megaTU-native.c) plus the
environment key (cc identity + flags + runtime hash + platform, exported by the
caller as SV0_RUN_CACHE_ENVKEY) identifies it. If the binary is older than that C
file, the pair is out of sync and nothing is cached.

Include closure mirrors sml-legacy/include_expand.sml: top-level lines
`include "rel/path.sv0";`, relative to the including file's directory. The scan is
deliberately a SUPERSET (any line starting `include "` counts, missing files are
recorded) so it can only over-invalidate, never miss a dependency.

Usage:
  emit_cache_key.py key --root <toolchain root> <abs-source.sv0>
  emit_cache_key.py --selftest
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile

WS = " \t\n\v\f"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def include_closure(entry: str) -> list[str]:
    """Entry first, then transitively included files (DFS, deduped, cycle-safe)."""
    seen: list[str] = []

    def visit(p: str) -> None:
        p = os.path.realpath(p)
        if p in seen:
            return
        seen.append(p)
        try:
            text = open(p, "rb").read().decode("utf-8", "surrogateescape")
        except OSError:
            return
        for line in text.split("\n"):
            s = line.rstrip("\r").strip(WS)
            if not s.startswith('include "'):
                continue
            after = s[len('include "'):]
            q = after.find('"')
            if q < 0:
                continue
            visit(os.path.join(os.path.dirname(p), after[:q]))

    visit(entry)
    return seen


def cache_key(root: str, entry: str, envkey: str, coverage_request: str = "") -> str | None:
    tu_c = os.path.join(root, "build", "megaTU-native.c")
    binary = os.path.join(root, "build", "sv0-megatu-native")
    wrapper = os.path.join(root, "build", "sv0-megatu-compiler-native")
    if not (envkey and os.path.isfile(tu_c) and os.path.isfile(binary) and os.path.isfile(wrapper)):
        return None
    if os.path.getmtime(binary) < os.path.getmtime(tu_c):
        return None  # binary predates its recorded source: identity unknown
    h = hashlib.sha256()
    h.update(b"sv0-emit-cache-v1\n")
    h.update(envkey.encode() + b"\n")
    h.update(_sha(open(tu_c, "rb").read()).encode() + b"\n")
    h.update(_sha(open(wrapper, "rb").read()).encode() + b"\n")
    h.update(os.path.abspath(entry).encode("utf-8", "surrogateescape") + b"\n")
    # sv0cov CV-106 / COV-INS-004: a non-off coverage request changes the
    # emitted artifact; off (empty) keeps every existing key unchanged.
    if coverage_request:
        h.update(b"coverage\0" + coverage_request.encode("utf-8", "surrogateescape") + b"\n")
    for f in include_closure(entry):
        try:
            data = _sha(open(f, "rb").read())
        except OSError:
            data = "missing"
        h.update(f.encode("utf-8", "surrogateescape") + b"\0" + data.encode() + b"\n")
    return h.hexdigest()


def _selftest() -> int:
    bad = 0

    def check(name: str, cond: bool) -> None:
        nonlocal bad
        if not cond:
            bad += 1
            print(f"emit_cache_key selftest FAIL: {name}", file=sys.stderr)

    with tempfile.TemporaryDirectory() as td:
        td = os.path.realpath(td)
        os.makedirs(os.path.join(td, "src", "sub"))
        w = lambda rel, txt: open(os.path.join(td, rel), "w").write(txt)  # noqa: E731
        w("src/main.sv0", 'include "sub/a.sv0";\n  include "b.sv0" ;\nfn main() -> i32 { 0 }\n')
        w("src/sub/a.sv0", 'include "c.sv0";\nfn a() -> i32 { 1 }\n')
        w("src/sub/c.sv0", 'include "a.sv0";\nfn c() -> i32 { 2 }\n')  # cycle a <-> c
        w("src/b.sv0", 'include "missing.sv0";\nfn b() -> i32 { 3 }\n')
        rel = lambda ps: [os.path.relpath(p, td) for p in ps]  # noqa: E731
        got = rel(include_closure(os.path.join(td, "src", "main.sv0")))
        check("closure order/nesting/cycle/missing",
              got == ["src/main.sv0", "src/sub/a.sv0", "src/sub/c.sv0", "src/b.sv0", "src/missing.sv0"])

        os.makedirs(os.path.join(td, "build"))
        w("build/megaTU-native.c", "int compiler(void){return 1;}\n")
        w("build/sv0-megatu-compiler-native", "#!/bin/sh\n")
        w("build/sv0-megatu-native", "bin\n")
        now = os.path.getmtime(os.path.join(td, "build", "megaTU-native.c"))
        os.utime(os.path.join(td, "build", "sv0-megatu-native"), (now + 5, now + 5))
        entry = os.path.join(td, "src", "main.sv0")
        k = lambda e="ENV": cache_key(td, entry, e)  # noqa: E731
        base = k()
        check("key is produced", bool(base) and len(base) == 64)
        check("key is stable", k() == base)
        w("src/sub/c.sv0", 'include "a.sv0";\nfn c() -> i32 { 22 }\n')
        check("nested include change invalidates", k() != base)
        w("src/sub/c.sv0", 'include "a.sv0";\nfn c() -> i32 { 2 }\n')
        check("restoring the include restores the key", k() == base)
        w("src/main.sv0", 'include "sub/a.sv0";\n  include "b.sv0" ;\nfn main() -> i32 { 1 }\n')
        check("entry change invalidates", k() != base)
        w("src/main.sv0", 'include "sub/a.sv0";\n  include "b.sv0" ;\nfn main() -> i32 { 0 }\n')
        check("environment key change invalidates", k("OTHER") != base)
        check("empty coverage request keeps the key", cache_key(td, entry, "ENV", "") == base)
        cov_map = cache_key(td, entry, "ENV", "map\n/m.json")
        check("coverage request invalidates", cov_map not in (None, base))
        check("coverage mode is part of the key", cache_key(td, entry, "ENV", "instrument\n/m.json") != cov_map)
        check("empty environment key is not cacheable", k("") is None)
        w("build/megaTU-native.c", "int compiler(void){return 2;}\n")
        os.utime(os.path.join(td, "build", "sv0-megatu-native"), (now + 9, now + 9))
        check("compiler source change invalidates", k() != base)
        os.utime(os.path.join(td, "build", "sv0-megatu-native"), (now - 100, now - 100))
        check("binary older than its C is not cacheable", k() is None)

    if bad:
        return 1
    print("emit_cache_key: selftest OK (13 checks)")
    return 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return _selftest()
    if len(argv) >= 4 and argv[0] == "key" and argv[1] == "--root":
        key = cache_key(argv[2], argv[3], os.environ.get("SV0_RUN_CACHE_ENVKEY", ""),
                        os.environ.get("SV0_COVERAGE_REQUEST", ""))
        if key is None:
            return 3
        print(key)
        return 0
    print(__doc__, file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
