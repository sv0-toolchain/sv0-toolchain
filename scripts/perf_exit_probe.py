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
directory under --work (the campaign uses $RUNNER_TEMP). Prints one JSON
document: host facts, then median and p95 in microseconds per mode.
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
"""

RUN_ID = "0123456789abcdef0123456789abcdef"


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


def bench(argv: list[str], env: dict, prof: Path, runs: int, warmup: int) -> dict:
    xs = []
    for i in range(warmup + runs):
        t = time.perf_counter_ns()
        subprocess.run(argv, env=env, stdout=subprocess.DEVNULL, check=True)
        dt = time.perf_counter_ns() - t
        published = list(prof.iterdir())
        if argv[-1] == "ok" and len(published) != 1:
            sys.exit(f"perf_exit_probe: expected one profile, found {len(published)}")
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
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
