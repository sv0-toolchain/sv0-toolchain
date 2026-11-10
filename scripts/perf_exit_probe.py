#!/usr/bin/env python3
# SPDX-License-Identifier: MIT OR Apache-2.0
# SPDX-FileCopyrightText: 2026 Sasank Vishnubhatla
"""Exit-cost probe for the sv0cov native runtime (CV-428).

The first recorded campaign put a fixed ~0.8 ms per run on every Linux
execute fixture. This measures what the runtime's exit-time publication
costs on the host, and how much of it is the two fsync calls (the profile
file, then its directory; SPEC 20.2.3 and 16.4).

One driver binary (sv0cov/runtime/c/tests/rt_driver.c, scenario "ok") is
built with fsync routed through a shim; SV0PROBE_FSYNC picks what the shim
does, so every mode runs the same bytes:

  none       the real fsync on both calls (what ships)
  skip-all   both calls are no-ops
  skip-file  the first call (the profile file) is a no-op
  skip-dir   the second call (the directory) is a no-op
  fdatasync  both calls use fdatasync
  fullfsync  both calls use fcntl F_FULLFSYNC (macOS only)

An empty C program gives the host's bare process cost. Profiles go to a
directory under --work (the campaign uses $RUNNER_TEMP).

The "program" section times the real startup-empty fixture, from the C
sv0c edd99af emits for it without and with --coverage=instrument, built
with native-compile's own argv builders (dev profile): off; on (both
fsyncs real); on with both fsyncs skipped (Linux only); and on with an
invalid transport in optional mode, so the runtime stops at transport
validation and publishes nothing (the binary's load cost). On Linux,
"phases" is an LD_PRELOAD trace of the libc calls the runtime makes,
median microseconds per phase.

Prints one JSON document: host facts, then median and p95 in
microseconds per mode.
"""

import argparse
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

SHIM = r"""
#include <fcntl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#ifdef SV0PROBE_WRAP /* linked with -Wl,--wrap=fsync: the real one is __real_fsync */
int __real_fsync(int fd);
#define fsync __real_fsync
#endif
static int calls;
int sv0probe_fsync(int fd) {
  const char *m = getenv("SV0PROBE_FSYNC");
  int n = calls++;
  if (!m || !strcmp(m, "none")) return fsync(fd);
  if (!strcmp(m, "skip-all")) return 0;
  if (!strcmp(m, "skip-file")) return n == 0 ? 0 : fsync(fd);
  if (!strcmp(m, "skip-dir")) return n == 1 ? 0 : fsync(fd);
#ifdef __linux__
  if (!strcmp(m, "fdatasync")) return fdatasync(fd);
#endif
#ifdef F_FULLFSYNC
  if (!strcmp(m, "fullfsync")) return fcntl(fd, F_FULLFSYNC);
#endif
  abort();
}
#ifdef SV0PROBE_WRAP
int __wrap_fsync(int fd) { return sv0probe_fsync(fd); }
#endif
"""

RUN_ID = "0123456789abcdef0123456789abcdef"

# startup-empty as sv0c edd99af emits it (native-compile --keep-c).
OFF_C = r"""#include "sv0_runtime.h"


static int sv0_user_main(void) {
  return 0;
}

int main(int argc, char **argv) {
  sv0_runtime_init(argc, argv);
  return (int)sv0_user_main();
}

"""

ON_C = r"""#include "sv0_runtime.h"

/* sv0cov coverage instrumentation, generated-C protocol 1 (sv0cov CV-113, CV-206).
   One module descriptor per map fragment; hits count module-local counters.
   The coverage runtime validates the whole set before user entry. */
struct __sv0cov_fragment {
  const char *fragment_id;
  uint32_t slice_base;
  uint32_t slice_length;
};
struct __sv0cov_module {
  uint32_t protocol_major;
  const char *map_id;
  uint32_t program_counter_count;
  const char *target;
  const char *compiler_identity;
  uint32_t slice_base;
  uint32_t slice_length;
  uint32_t fragment_count;
  const struct __sv0cov_fragment *fragments;
};
void __sv0cov_start(const struct __sv0cov_module *const *modules, uint32_t module_count);
void __sv0cov_hit(const struct __sv0cov_module *module, uint32_t local_index);
static const struct __sv0cov_fragment __sv0cov_fragment_0[1] = {{"4a3048049a16b756063fe67c56445f6662a613da8f4ee0f4a4547351099f5b4e", 0u, 1u}};
static const struct __sv0cov_module __sv0cov_module_0 = {
  1u, "a9f4932146c70f747640acf293c63e96e89224359952e89785ca63adac84595a", 1u, "on.exe", "sv0c+edd99af2a85b1c1a16805b9a956ecc0c423df6ac", 0u, 1u, 1u, __sv0cov_fragment_0
};
static const struct __sv0cov_module *const __sv0cov_modules[1] = {&__sv0cov_module_0};


static int sv0_user_main(void) {
  __sv0cov_hit(&__sv0cov_module_0, 0u);
  return 0;
}

int main(int argc, char **argv) {
  sv0_runtime_init(argc, argv);
  __sv0cov_start(__sv0cov_modules, 1u);
  return (int)sv0_user_main();
}

"""

TRACE = r"""
#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <sys/types.h>
#include <time.h>
static struct { const char *n; long ns; } ev[64];
static int ne;
static struct timespec t0;
static void mark(const char *n) {
  struct timespec t;
  clock_gettime(CLOCK_MONOTONIC, &t);
  if (ne < 64) { ev[ne].n = n; ev[ne].ns = (t.tv_sec - t0.tv_sec) * 1000000000L + (t.tv_nsec - t0.tv_nsec); ne++; }
}
__attribute__((constructor)) static void ctor(void) { clock_gettime(CLOCK_MONOTONIC, &t0); }
__attribute__((destructor)) static void dtor(void) {
  mark("dtor");
  for (int i = 0; i < ne; i++) fprintf(stderr, "%s %ld\n", ev[i].n, ev[i].ns);
}
#define WRAP(ret, name, params, args) ret name params { \
  static ret (*f) params; if (!f) f = dlsym(RTLD_NEXT, #name); \
  mark(#name "<"); ret r = f args; mark(#name ">"); return r; }
WRAP(int, getentropy, (void *b, size_t n), (b, n))
WRAP(int, mkstemp, (char *t), (t))
WRAP(int, fsync, (int fd), (fd))
WRAP(int, close, (int fd), (fd))
WRAP(int, renameat2, (int a, const char *o, int b, const char *n, unsigned fl), (a, o, b, n, fl))
WRAP(ssize_t, write, (int fd, const void *b, size_t n), (fd, b, n))
int open(const char *p, int fl, ...) {
  static int (*f)(const char *, int, ...);
  if (!f) f = dlsym(RTLD_NEXT, "open");
  mode_t m = 0;
  if (fl & O_CREAT) { va_list ap; va_start(ap, fl); m = va_arg(ap, int); va_end(ap); }
  mark("open<"); int r = f(p, fl, m); mark("open>"); return r;
}
"""

# Phase name: (start event, its occurrence), (end event, its occurrence).
PHASES = {
    "load+init to runtime start": (None, ("getentropy<", 0)),
    "runtime start to flush": (("getentropy<", 0), ("mkstemp<", 0)),
    "mkstemp": (("mkstemp<", 0), ("mkstemp>", 0)),
    "write": (("mkstemp>", 0), ("fsync<", 0)),
    "fsync file": (("fsync<", 0), ("fsync>", 0)),
    "close+rename": (("fsync>", 0), ("renameat2>", 0)),
    "open dir": (("renameat2>", 0), ("open>", 0)),
    "fsync dir": (("open>", 0), ("fsync>", 1)),
    "close to exit": (("fsync>", 1), ("dtor", 0)),
}


def build(root: Path, work: Path) -> tuple[Path, Path]:
    rt = root / "sv0cov/runtime/c"
    (work / "shim.c").write_text(SHIM)
    (work / "empty.c").write_text("int main(void) { return 0; }\n")
    driver, empty = work / "driver", work / "empty"
    subprocess.run(["cc", "-O2", "-o", str(empty), str(work / "empty.c")], check=True)
    # The macro renames only the runtime's two fsync calls (and the libc
    # declaration they see); the shim itself is compiled without it.
    subprocess.run(["cc", "-O2", "-std=c11", "-DSV0COV_RT_TESTING", "-Dfsync=sv0probe_fsync", "-pthread",
                    "-c", "-o", str(work / "rt.o"), str(rt / "sv0cov_rt.c")], check=True)
    subprocess.run(["cc", "-O2", "-std=c11", "-DSV0COV_RT_TESTING", "-pthread", "-o", str(driver), str(rt / "tests/rt_driver.c"),
                    str(work / "rt.o"), str(work / "shim.c")], check=True)
    return driver, empty


def build_program(root: Path, work: Path) -> tuple[Path, Path]:
    """startup-empty off and on, through native-compile's own argv builders.

    On Linux the on binary links with -Wl,--wrap=fsync so the runtime's fsync
    calls reach the shim (which calls __real_fsync); macOS ld has no --wrap,
    so there the on binary keeps the real fsync and SV0PROBE_FSYNC is unused.
    """
    from native_exe_argv_builder import build_dev_profile_argv
    from native_exe_coverage import compile_coverage_runtime
    from native_exe_runtime import resolve_runtime_dir

    runtime = resolve_runtime_dir(str(root))
    (work / "off.c").write_text(OFF_C)
    (work / "on.c").write_text(ON_C)
    off, on = work / "prog-off", work / "prog-on"
    subprocess.run(build_dev_profile_argv("cc", runtime, str(work / "off.c"), str(off)), check=True)
    obj = compile_coverage_runtime("cc", str(root / "sv0cov/runtime/c/sv0cov_rt.c"), str(work), dict(os.environ))
    link = [obj]
    if sys.platform == "linux":
        link = ["-DSV0PROBE_WRAP", "-Wl,--wrap=fsync", obj, str(work / "shim.c")]
    subprocess.run(build_dev_profile_argv("cc", runtime, str(work / "on.c"), str(on), extra_cc_args=link), check=True)
    return off, on


def phases(on: Path, env: dict, work: Path, prof: Path, runs: int) -> dict:
    """Median microseconds per publication phase (Linux LD_PRELOAD trace)."""
    (work / "trace.c").write_text(TRACE)
    so = work / "trace.so"
    subprocess.run(["cc", "-O2", "-shared", "-fPIC", "-o", str(so), str(work / "trace.c"), "-ldl"], check=True)
    acc: dict[str, list[int]] = {k: [] for k in PHASES}
    for _ in range(runs):
        r = subprocess.run([str(on)], env=dict(env, LD_PRELOAD=str(so)), stderr=subprocess.PIPE, text=True, check=True)
        for f in prof.iterdir():
            f.unlink()
        seen: dict[str, list[int]] = {}
        for line in r.stderr.split("\n"):
            if line.strip():
                name, ns = line.split()
                seen.setdefault(name, []).append(int(ns))
        for k, (a, b) in PHASES.items():
            acc[k].append(seen[b[0]][b[1]] - (seen[a[0]][a[1]] if a else 0))
    return {k: round(statistics.median(v) / 1e3, 1) for k, v in acc.items()}


def bench(argv: list[str], env: dict, prof: Path, runs: int, warmup: int, profiles: int | None = None) -> dict:
    xs = []
    for i in range(warmup + runs):
        t = time.perf_counter_ns()
        subprocess.run(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        dt = time.perf_counter_ns() - t
        published = list(prof.iterdir())
        want = profiles if profiles is not None else (1 if argv[-1] == "ok" else 0)
        if len(published) != want:
            sys.exit(f"perf_exit_probe: {argv[0]}: expected {want} profile(s), found {len(published)}")
        for f in published:
            f.unlink()
        if i >= warmup:
            xs.append(dt)
    xs.sort()
    return {"median_us": round(statistics.median(xs) / 1e3, 1), "p95_us": round(xs[int(len(xs) * 0.95)] / 1e3, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--toolchain", type=Path, default=Path("."))
    ap.add_argument("--work", type=Path, required=True)
    ap.add_argument("--runs", type=int, default=500)
    ap.add_argument("--warmup", type=int, default=20)
    a = ap.parse_args()
    shutil.rmtree(a.work, ignore_errors=True)
    prof = a.work / "prof"
    prof.mkdir(parents=True)
    driver, empty = build(a.toolchain.resolve(), a.work)
    base = {k: v for k, v in os.environ.items() if not k.startswith("SV0COV_")}
    base.update(SV0COV_PROFILE_DIR=str(prof.resolve()), SV0COV_RUN_ID=RUN_ID, SV0COV_REQUIRED="1")
    modes = ["none", "skip-all", "skip-file", "skip-dir"]
    modes.append("fdatasync" if sys.platform == "linux" else "fullfsync")
    out = {"host": {"system": platform.system(), "machine": platform.machine(), "cpus": os.cpu_count(),
                    "runner": os.environ.get("SV0COV_RUNNER_LABEL", "local")},
           "empty": bench([str(empty)], base, prof, a.runs, a.warmup)}
    # Interleave the modes round by round so drift on a shared runner hits them alike.
    rounds, per = 5, a.runs // 5
    acc: dict[str, list[dict]] = {m: [] for m in modes}
    for _ in range(rounds):
        for m in modes:
            acc[m].append(bench([str(driver), "ok"], dict(base, SV0PROBE_FSYNC=m), prof, per, a.warmup // rounds))
    out["driver"] = {m: {"median_us": statistics.median(r["median_us"] for r in acc[m]),
                         "p95_us": statistics.median(r["p95_us"] for r in acc[m])} for m in modes}
    off, on = build_program(a.toolchain.resolve(), a.work)
    optional = dict(base, SV0COV_PROFILE_DIR=str(a.work / "missing"), SV0COV_REQUIRED="0")
    progs = {"off": ([str(off)], base, 0), "on": ([str(on)], dict(base, SV0PROBE_FSYNC="none"), 1),
             "on-no-collection": ([str(on)], optional, 0)}
    if sys.platform == "linux":
        progs["on-skip-fsync"] = ([str(on)], dict(base, SV0PROBE_FSYNC="skip-all"), 1)
    pacc: dict[str, list[dict]] = {m: [] for m in progs}
    for _ in range(rounds):
        for m, (argv, env, n) in progs.items():
            pacc[m].append(bench(argv, env, prof, per, a.warmup // rounds, profiles=n))
    out["program"] = {m: {"median_us": statistics.median(r["median_us"] for r in pacc[m]),
                          "p95_us": statistics.median(r["p95_us"] for r in pacc[m])} for m in progs}
    if sys.platform == "linux":
        out["phases"] = phases(on, dict(base, SV0PROBE_FSYNC="none"), a.work, prof, 200)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
