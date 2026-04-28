#!/usr/bin/env python3
"""Local HTTP server: sv0-track digest + milestones (stdlib only).

Binds to 127.0.0.1 by default. Static UI under
``scripts/progress_dashboard/static/``.

Usage::

    ./scripts/sv0 progress-dashboard
    python3 scripts/progress_dashboard_server.py --root . --port 8765 --refresh-seconds 120
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import task_rmd_tracking  # noqa: E402


def _build_digest(root: Path) -> list[dict[str, object]]:
    task_dir = root / "task"
    rows: list[dict[str, object]] = []
    if not task_dir.is_dir():
        return rows
    for path in sorted(task_dir.glob("*.Rmd")):
        result = task_rmd_tracking.parse_task_rmd_file(path)
        rows.append(task_rmd_tracking.result_to_jsonable(result))
    return rows


def _load_milestones(root: Path) -> dict[str, object]:
    p = root / "task" / "milestone-orientation.json"
    if not p.is_file():
        return {
            "milestones": [],
            "error": "missing task/milestone-orientation.json",
        }
    return json.loads(p.read_text(encoding="utf-8"))


class _JsonBodyCache:
    """Thread-safe JSON body cache with monotonic TTL (rebuild at most every ``ttl`` s)."""

    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = max(1.0, float(ttl_seconds))
        self._lock = threading.Lock()
        self._built_at: float = 0.0
        self._body: bytes = b""

    def get_bytes(self, build: Callable[[], object]) -> bytes:
        with self._lock:
            now = time.monotonic()
            if self._body and (now - self._built_at) < self._ttl:
                return self._body
            payload = build()
            raw = json.dumps(payload, indent=2).encode("utf-8")
            self._body = raw
            self._built_at = time.monotonic()
            return self._body


def make_handler(root: Path, refresh_seconds: float) -> type[BaseHTTPRequestHandler]:
    static_root = _SCRIPT_DIR / "progress_dashboard" / "static"
    digest_cache = _JsonBodyCache(refresh_seconds)
    milestones_cache = _JsonBodyCache(refresh_seconds)

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: object) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

        def _send(
            self,
            code: int,
            body: bytes,
            content_type: str,
            *,
            cache_control: str = "no-store",
        ) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path or "/"
            if path == "/":
                index = static_root / "index.html"
                if not index.is_file():
                    self._send(
                        500,
                        b"missing static index",
                        "text/plain; charset=utf-8",
                    )
                    return
                self._send(
                    200,
                    index.read_bytes(),
                    "text/html; charset=utf-8",
                )
                return
            if path.startswith("/static/"):
                rel = unquote(path[len("/static/") :])
                if ".." in rel or rel.startswith("/"):
                    self._send(400, b"bad path", "text/plain; charset=utf-8")
                    return
                target = (static_root / rel).resolve()
                try:
                    target.relative_to(static_root.resolve())
                except ValueError:
                    self._send(403, b"forbidden", "text/plain; charset=utf-8")
                    return
                if not target.is_file():
                    self._send(404, b"not found", "text/plain; charset=utf-8")
                    return
                ctype = "application/octet-stream"
                if target.suffix == ".js":
                    ctype = "text/javascript; charset=utf-8"
                elif target.suffix == ".css":
                    ctype = "text/css; charset=utf-8"
                self._send(200, target.read_bytes(), ctype)
                return
            if path == "/api/config":
                poll_ms = int(max(15_000, min(refresh_seconds * 1000.0, 600_000)))
                cfg: dict[str, object] = {
                    "refresh_seconds": refresh_seconds,
                    "suggested_client_poll_ms": poll_ms,
                    "toolchain_root": str(root),
                }
                raw = json.dumps(cfg).encode("utf-8")
                # Do not let browsers cache JSON: digest/milestones already use an in-process
                # TTL cache; HTTP caching caused stale "Needs fix N files" after task fixes or
                # container restarts until max-age expired.
                self._send(
                    200,
                    raw,
                    "application/json; charset=utf-8",
                    cache_control="no-store",
                )
                return
            if path == "/api/digest":
                raw = digest_cache.get_bytes(lambda: _build_digest(root))
                self._send(
                    200,
                    raw,
                    "application/json; charset=utf-8",
                    cache_control="no-store",
                )
                return
            if path == "/api/milestones":
                raw = milestones_cache.get_bytes(lambda: _load_milestones(root))
                self._send(
                    200,
                    raw,
                    "application/json; charset=utf-8",
                    cache_control="no-store",
                )
                return
            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Toolchain root (default: parent of scripts/)",
    )
    ap.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind address (default: 127.0.0.1)",
    )
    ap.add_argument(
        "--port",
        type=int,
        default=8765,
        help="TCP port (default: 8765)",
    )
    ap.add_argument(
        "--refresh-seconds",
        type=float,
        default=120.0,
        help=(
            "Minimum seconds between re-scanning task/*.Rmd and milestone JSON "
            "for API responses (default: 120)"
        ),
    )
    args = ap.parse_args(argv)
    root = args.root.resolve()
    handler = make_handler(root, args.refresh_seconds)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        f"progress dashboard: http://{args.host}:{args.port}/",
        f"(root={root}, api_refresh≥{args.refresh_seconds}s)",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nprogress dashboard: stopped", file=sys.stderr)
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
