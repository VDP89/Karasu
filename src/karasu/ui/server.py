"""Karasu UI HTTP server.

Stdlib-only ThreadingHTTPServer. Reads ``.karasu/events.jsonl``
on each request and exposes:

  GET /              static index.html (the UI shell)
  GET /api/events    paginated event projection
  GET /api/health    server + crow state summary
  GET /assets/...    static assets (fonts, sprites — UI-2+)

The projection in ``_project_event`` mirrors the bus schema as
of UI-1: the additive fields landed during chunks 4a/4b/4c +
the chain-cap implementation are surfaced so downstream UI
chunks (timeline, detail panel, Live Map) can render the full
audit picture without extra round-trips.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

# Default bus path. Mutable so ``configure(event_log=...)`` can
# point the UI server at a non-default ``karasu.yaml`` bus
# location (UI-9 deferred follow-up). Tests and ``cmd_ui``
# override this; the default keeps the dogfood path working
# for an operator running ``karasu ui`` from a fresh checkout
# without a config file.
EVENT_LOG = Path(".karasu/events.jsonl")
STATIC_DIR = Path(__file__).parent / "static"

# Default page size for /api/events. Operator can override via
# ?limit=N (capped at MAX_EVENT_LIMIT to bound memory in the
# face of an enormous bus).
DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 1000


def _project_event(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw bus event into the UI's view model.

    The UI never consumes the full bus event verbatim; it picks
    the fields that drive the visible surfaces. Adding a field
    here is the contract change for "the UI now sees X". This
    file is the canonical projection.
    """
    data = raw.get("data") or {}
    dispatch = raw.get("dispatch") or {}
    response = raw.get("response") or {}
    return {
        "id": raw.get("id"),
        "timestamp": raw.get("timestamp"),
        "type": raw.get("type"),
        "source": raw.get("source"),
        # data — common
        "path": data.get("path"),
        "classification": data.get("classification"),
        "priority": data.get("priority"),
        # data — controller resubmits (chain cap, issue #47)
        "controller_resubmit": data.get("controller_resubmit"),
        "resubmit_origin": data.get("resubmit_origin"),
        "controller_chain_depth": data.get("controller_chain_depth"),
        # data — github webhook metadata (chunks 4a + 4c)
        "github_event": data.get("github_event"),
        "github_action": data.get("github_action"),
        "github_pr": data.get("github_pr"),
        "github_repo": data.get("github_repo"),
        "github_author": data.get("github_author"),
        # data — agent_response correlation (Phase 1B / F3)
        "correlates": data.get("correlates"),
        # dispatch
        "agent": dispatch.get("agent"),
        "status": dispatch.get("status"),
        "trust_level": dispatch.get("trust_level"),
        # response
        "requires_human": response.get("requires_human"),
    }


def _read_events(limit: int = DEFAULT_EVENT_LIMIT) -> list[dict[str, Any]]:
    """Tail the bus log and project the last ``limit`` events.

    Lines that fail to parse are skipped silently — the bus is
    append-only JSONL; partial / corrupt lines from a crash mid-
    write are real, and the UI must keep rendering whatever is
    valid.
    """
    if not EVENT_LOG.exists():
        return []
    lines = EVENT_LOG.read_text(encoding="utf-8").splitlines()[-limit:]
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            out.append(_project_event(json.loads(line)))
        except Exception:
            continue
    return out


def _crow_state(events: list[dict[str, Any]]) -> str:
    """Derive the crow's display state from the event tail.

    Precedence (most-recent wins):
      error      any event with status="failed" OR success=False.
      waiting    any event with requires_human=True.
      processing the latest event is a file_change.
      idle       otherwise.
    """
    state = "idle"
    for ev in reversed(events):
        if ev.get("status") == "failed":
            return "error"
        if ev.get("requires_human") is True:
            return "waiting"
        if ev.get("type") == "file_change":
            state = "processing"
    return state


def _parse_limit(query: str) -> int:
    """Parse ``?limit=N`` from a raw query string. Out-of-range
    values clamp; non-integer / missing falls back to the default.

    Uses urllib.parse.parse_qs so percent-encoded values, repeated
    keys, and other URL-grammar edge cases parse correctly.
    """
    if not query:
        return DEFAULT_EVENT_LIMIT
    raw = parse_qs(query, keep_blank_values=False).get("limit")
    if not raw:
        return DEFAULT_EVENT_LIMIT
    try:
        value = int(raw[0])
    except (ValueError, TypeError):
        return DEFAULT_EVENT_LIMIT
    return max(1, min(value, MAX_EVENT_LIMIT))


class UIHandler(BaseHTTPRequestHandler):
    """HTTP handler. Read-only; no POST routes today (write paths
    arrive in UI-10+ and MUST go through ScarEngine /
    human_decision events, never through direct bus mutation)."""

    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self._send(200, body, "application/json")

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        path, _, query = self.path.partition("?")

        if path == "/api/events":
            events = _read_events(_parse_limit(query))
            self._send_json({"events": events})
            return

        if path == "/api/health":
            events = _read_events()
            self._send_json(
                {
                    "status": "ok",
                    "events": len(events),
                    "crow": _crow_state(events),
                }
            )
            return

        if path in ("/", "/index.html"):
            html = (STATIC_DIR / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return

        # Static assets land in /assets/* — UI-2 introduces fonts
        # and sprite SVGs. Path-traversal guard: must resolve
        # under STATIC_DIR.
        if path.startswith("/assets/"):
            target = (STATIC_DIR / path[len("/assets/"):]).resolve()
            try:
                target.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._send(403, b"forbidden", "text/plain")
                return
            if target.is_file():
                self._send(200, target.read_bytes(), _content_type_for(target))
                return

        self._send(404, b"not found", "text/plain")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        # The default handler logs to stderr in apache combined
        # format which competes with karasu's own logging. Quiet
        # by default; operators run `karasu tail` for the bus.
        return


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".svg": "image/svg+xml",
        ".woff2": "font/woff2",
        ".png": "image/png",
        ".json": "application/json",
    }.get(suffix, "application/octet-stream")


def configure(event_log: Path) -> None:
    """Override the bus path read by ``/api/events`` and
    ``/api/health``.

    Called by ``cmd_ui`` (so ``karasu ui`` honours
    ``event_bus.path`` in ``karasu.yaml``) and by tests. Pure
    mutation of the module global; subsequent requests see the
    new value on the next read because ``_read_events`` reads
    ``EVENT_LOG`` at call time.
    """
    global EVENT_LOG
    EVENT_LOG = event_log


def run_ui_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    event_log: Path | None = None,
) -> None:
    """Start the UI HTTP server. Blocks until interrupted.

    ``event_log`` overrides the default ``.karasu/events.jsonl``
    bus path. ``cmd_ui`` passes the resolved value from
    ``karasu.yaml``; callers that omit the kwarg get the
    pre-existing default.
    """
    if event_log is not None:
        configure(event_log)
    server = ThreadingHTTPServer((host, port), UIHandler)
    print(f"karasu ui → http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
