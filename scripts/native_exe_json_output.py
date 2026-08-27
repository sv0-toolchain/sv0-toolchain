"""`--message-format=json` event encoder + phase timing (NEX-041).

Implements CLI-016/ERR-009…011
(`~/Documents/project-specs/sv0c-runtime-executable/SPEC.md` §18.6/§18.7):
R0.1's JSON message mode emits newline-delimited JSON objects to stdout
matching an exact schema (schema_version, event, success, phase, input,
output, backend, profile, contract_mode_requested/effective, compiler
info, timings_ms) and reports at least frontend/emission, host
compile/link, publication, and total wall time via a monotonic clock.

`PhaseTimer` is a tiny wrapper around `time.monotonic()` for named phases;
`build_event`/`encode_event` produce and serialize one event dict. Neither
function invokes the real pipeline -- callers (a future `--message-format`
wiring point, and this module's own selftest) supply already-computed
values.

Run `python3 scripts/native_exe_json_output.py --selftest` for the corpus.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

SCHEMA_VERSION = 1


class PhaseTimer:
    """Accumulates named-phase durations (ms) via `time.monotonic()`.

    Usage: `with timer.phase("frontend"): ...`. `timings_ms()` returns a
    dict of every recorded phase plus `"total"` (sum of all phases, not a
    separately-timed wall clock -- summing keeps `total` exactly consistent
    with its parts by construction, per §18.7's "at least ... total" wording).
    """

    def __init__(self) -> None:
        self._durations_ms: dict[str, float] = {}

    def phase(self, name: str) -> "_PhaseContext":
        return _PhaseContext(self, name)

    def _record(self, name: str, duration_ms: float) -> None:
        # Nonnegative by construction (monotonic clock, end - start), but
        # clamp defensively so a hostile/backdated clock can never produce
        # a negative reported duration.
        self._durations_ms[name] = max(0.0, duration_ms)

    def timings_ms(self) -> dict[str, int]:
        rounded = {k: round(v) for k, v in self._durations_ms.items()}
        rounded["total"] = sum(rounded.values())
        return rounded


@dataclass
class _PhaseContext:
    timer: PhaseTimer
    name: str
    _start: float = field(default=0.0, init=False)

    def __enter__(self) -> "_PhaseContext":
        self._start = time.monotonic()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        elapsed_ms = (time.monotonic() - self._start) * 1000.0
        self.timer._record(self.name, elapsed_ms)


_REQUIRED_KEYS = {
    "schema_version",
    "event",
    "success",
    "phase",
    "input",
    "output",
    "backend",
    "profile",
    "contract_mode_requested",
    "contract_mode_effective",
    "compiler",
    "timings_ms",
}


def build_event(
    *,
    event: str,
    success: bool,
    phase: str,
    input_path: str,
    output_path: str | None,
    backend: str,
    profile: str,
    contract_mode_requested: str,
    contract_mode_effective: str,
    compiler_path: str,
    compiler_family: str,
    compiler_version: str,
    timings_ms: dict[str, int],
) -> dict:
    """Build one §18.6-shaped event dict. Pure data assembly -- no I/O."""
    return {
        "schema_version": SCHEMA_VERSION,
        "event": event,
        "success": success,
        "phase": phase,
        "input": input_path,
        "output": output_path,
        "backend": backend,
        "profile": profile,
        "contract_mode_requested": contract_mode_requested,
        "contract_mode_effective": contract_mode_effective,
        "compiler": {
            "path": compiler_path,
            "family": compiler_family,
            "version": compiler_version,
        },
        "timings_ms": timings_ms,
    }


def encode_event(event: dict) -> str:
    """Serialize one event dict as a single JSON line (no trailing newline)."""
    return json.dumps(event, ensure_ascii=True)


def _selftest() -> int:
    failures: list[str] = []

    # Case 1: PhaseTimer around real work never reports a negative duration,
    # and total equals the sum of its parts.
    timer = PhaseTimer()
    with timer.phase("frontend"):
        time.sleep(0.001)
    with timer.phase("host_compile_link"):
        time.sleep(0.001)
    timings = timer.timings_ms()
    if any(v < 0 for v in timings.values()):
        failures.append(f"PhaseTimer produced a negative duration: {timings}")
    if timings["total"] != timings["frontend"] + timings["host_compile_link"]:
        failures.append(f"total did not equal the sum of recorded phases: {timings}")
    if "frontend" not in timings or "host_compile_link" not in timings:
        failures.append(f"expected phases missing: {timings}")

    # Case 2: a zero-duration phase (no sleep) still reports 0, not negative
    # or missing -- proves the clamp/rounding path handles the empty case.
    timer2 = PhaseTimer()
    with timer2.phase("publish"):
        pass
    timings2 = timer2.timings_ms()
    if timings2.get("publish", -1) < 0:
        failures.append(f"zero-duration phase reported negative: {timings2}")

    # Case 3: build_event/encode_event round-trip through json.loads and match
    # the exact §18.6 schema (required-key/type check).
    event = build_event(
        event="build-finished",
        success=True,
        phase="publish",
        input_path="/work/hello.sv0",
        output_path="/work/build/native/hello",
        backend="c",
        profile="dev",
        contract_mode_requested="verified",
        contract_mode_effective="runtime",
        compiler_path="/usr/bin/cc",
        compiler_family="clang",
        compiler_version="Apple clang version 15.0.0",
        timings_ms=timings,
    )
    line = encode_event(event)
    if "\n" in line:
        failures.append("encode_event output contained an embedded newline")
    decoded = json.loads(line)
    missing = _REQUIRED_KEYS - decoded.keys()
    if missing:
        failures.append(f"decoded event missing required keys: {missing}")
    if decoded.get("schema_version") != SCHEMA_VERSION:
        failures.append(f"schema_version mismatch: {decoded.get('schema_version')}")
    if not isinstance(decoded.get("success"), bool):
        failures.append(f"success is not a bool: {decoded.get('success')!r}")
    if not isinstance(decoded.get("compiler"), dict) or "path" not in decoded["compiler"]:
        failures.append(f"compiler sub-object malformed: {decoded.get('compiler')!r}")
    if not isinstance(decoded.get("timings_ms"), dict) or "total" not in decoded["timings_ms"]:
        failures.append(f"timings_ms sub-object malformed: {decoded.get('timings_ms')!r}")

    # Case 4: a failed build's event still carries a well-formed, decodable
    # shape (success=False is a valid, expected value, not an error case).
    fail_event = build_event(
        event="build-finished",
        success=False,
        phase="host_compile",
        input_path="/work/bad.sv0",
        output_path=None,
        backend="c",
        profile="dev",
        contract_mode_requested="runtime",
        contract_mode_effective="runtime",
        compiler_path="/usr/bin/cc",
        compiler_family="gcc",
        compiler_version="gcc 13.2.0",
        timings_ms={"frontend": 5, "host_compile_link": 0, "total": 5},
    )
    fail_line = encode_event(fail_event)
    fail_decoded = json.loads(fail_line)
    if fail_decoded.get("success") is not False:
        failures.append(f"expected success=False, got {fail_decoded.get('success')!r}")
    if fail_decoded.get("output") is not None:
        failures.append(f"expected output=None for a failed build, got {fail_decoded.get('output')!r}")

    if failures:
        for f in failures:
            print(f"native_exe_json_output selftest FAIL: {f}")
        return 1

    print("native_exe_json_output: selftest OK (4 cases)")
    return 0


if __name__ == "__main__":
    import sys

    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("native_exe_json_output: library module; use --selftest", file=sys.stderr)
    raise SystemExit(2)
