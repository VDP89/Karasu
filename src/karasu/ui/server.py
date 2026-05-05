"""Karasu UI HTTP server.

Stdlib-only ThreadingHTTPServer. Reads ``.karasu/events.jsonl``
on each request and exposes:

  GET /                static index.html (the UI shell)
  GET /design-system   UI-2 token documentation page
  GET /api/events      paginated event projection
  GET /api/health      server + crow state summary
  GET /api/meta        version + configured bus path (UI-3)
  GET /assets/...      static assets (fonts, sprites, css)

The projection in ``_project_event`` mirrors the bus schema as
of UI-1: the additive fields landed during chunks 4a/4b/4c +
the chain-cap implementation are surfaced so downstream UI
chunks (timeline, detail panel, Live Map) can render the full
audit picture without extra round-trips.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata as importlib_metadata
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

    Captures the module global ``EVENT_LOG`` into a local at
    function entry so a concurrent ``configure(...)`` cannot
    flip the path between the ``exists`` and ``read_text`` calls
    on this read. Today there is no caller that hot-reconfigures
    mid-request, but the local pin is cheap defence against a
    future one.
    """
    event_log = EVENT_LOG
    if not event_log.exists():
        return []
    lines = event_log.read_text(encoding="utf-8").splitlines()[-limit:]
    out: list[dict[str, Any]] = []
    for line in lines:
        try:
            out.append(_project_event(json.loads(line)))
        except Exception:
            continue
    return out


# --- UI-6: Live Map flight routing -------------------------------
#
# The Live Map paints five fixed nodes (user / karasu / claude /
# codex / github) and flies the crow between them whenever the bus
# advances. _flight_route is the read-only projection that tells
# the surface which (source, target) pair the latest event walks.
#
# Binding decisions pinned by the operator before UI-6 implementation:
#
#   1. Project the LATEST meaningful event. NO memory of prior
#      flights. NO invented recovery / delivery flights.
#   2. agent_response (completed OR failed) walks Agent → Karasu.
#      The response coming back is the meaningful motion regardless
#      of outcome; failed dispatches still routed to the agent.
#   3. controller_resubmit walks User → Karasu (operator intent
#      semantically, even though the controller mechanically emits).
#   4. file_change with an in-flight dispatch (router has assigned
#      an agent and status is pending / dispatched) walks
#      Karasu → Claude/Codex — the outbound leg the timeline
#      cannot read on its own.
#   5. github_webhook walks GitHub → Karasu.
#   6. human_decision walks User → Karasu.
#   7. Unknown / unmapped event types return None — the crow stays
#      parked at the most recent target node (the visual layer's
#      job, not the projection's).
#
# The flight is paired with crow_state on /api/health: state is
# colour, flight is position. Both are projections of the same
# event tail; neither holds memory.

# Node identifiers used on the wire and in tests. The CSS / SVG
# layer keys node positions off these strings, so any rename here
# is a coordinated UI change.
NODE_USER = "user"
NODE_KARASU = "karasu"
NODE_CLAUDE = "claude"
NODE_CODEX = "codex"
NODE_GITHUB = "github"

# Map dispatch.agent strings (as they appear on the bus) to Live
# Map node ids. Unknown agents fall through to None and the
# projection returns no flight rather than inventing a target —
# the operator should see a parked crow, not a wrong route.
_AGENT_TO_NODE: dict[str, str] = {
    "claude_code": NODE_CLAUDE,
    "claude": NODE_CLAUDE,
    "codex": NODE_CODEX,
}


def _flight_route(
    events: list[dict[str, Any]],
) -> tuple[str, str] | None:
    """Derive the Live Map flight pair from the event tail.

    Returns ``(source_node, target_node)`` for the LATEST event when
    the event has a deterministic node mapping, or ``None`` when
    the bus is silent OR the latest event is unmapped (the surface
    parks the crow).

    Precedence — only the latest event is consulted; older events
    are NOT searched. This is deliberately stricter than
    ``_crow_state``'s reverse walk: a flight is the visual proxy
    for the most recent motion on the bus, and resurrecting an
    older event's pair would contradict the operator's "no
    invented recovery flight" pin.

    Tests in tests/test_ui_server.py pin every branch.
    """
    if not events:
        return None
    ev = events[-1]
    ev_type = ev.get("type")

    if ev_type == "file_change":
        # Operator scar → controller resubmit. Mechanically emitted
        # by the controller, semantically User intent — show as
        # User → Karasu so the map explains "a human correction
        # entered the system" rather than "Karasu talked to itself".
        if ev.get("controller_resubmit"):
            return (NODE_USER, NODE_KARASU)
        # GitHub webhook ingress. The projection surfaces both the
        # github_event field (set when the webhook receiver handled
        # the payload) and source="github_webhook"; either is enough.
        if ev.get("github_event") or ev.get("source") == "github_webhook":
            return (NODE_GITHUB, NODE_KARASU)
        # Outbound leg: the router has picked an agent and the
        # dispatch is in flight. Show Karasu → agent so the map
        # narrates the request leaving the watchtower. Once the
        # corresponding agent_response lands, the next call to
        # _flight_route will return the inbound leg.
        agent = ev.get("agent")
        dispatch_status = ev.get("status")
        if agent and dispatch_status in ("pending", "dispatched"):
            target = _AGENT_TO_NODE.get(agent)
            if target is not None:
                return (NODE_KARASU, target)
        # Plain filesystem / git-hook activity. The change came
        # from the user editing the working tree.
        return (NODE_USER, NODE_KARASU)

    if ev_type == "agent_response":
        # Inbound leg from whichever agent ran. completed AND
        # failed both route Agent → Karasu — the response landed,
        # the outcome is the colour (handled by _crow_state),
        # not the path.
        agent = ev.get("agent")
        if agent is None:
            return None
        source_node = _AGENT_TO_NODE.get(agent)
        if source_node is None:
            return None
        return (source_node, NODE_KARASU)

    if ev_type == "human_decision":
        return (NODE_USER, NODE_KARASU)

    if ev_type == "git_event":
        # Local git activity (commit, push, hook). Counts as User
        # for routing purposes — the operator drove it.
        return (NODE_USER, NODE_KARASU)

    return None


def _crow_state(events: list[dict[str, Any]]) -> str:
    """Derive the crow's display state from the event tail.

    Precedence — the loop walks events in reverse-chronological
    order and returns at the first match:

      error      most-recent event with status="failed".
      waiting    most-recent event with requires_human=True.
                 (If the SAME event triggers both, error wins
                 because it is checked first per iteration.)
      processing the LATEST event is a file_change. Checked
                 only after the error/waiting scan finishes
                 without a match.
      idle       otherwise — including the case where the
                 latest event is a completed agent_response
                 that closed an older file_change.

    Earlier implementations set ``state = "processing"`` on any
    file_change in the loop and continued — that resolved a
    completed-agent_response tail with an older file_change to
    "processing", contradicting the documented "latest event is
    a file_change" rule and miscolouring the idle PNG. Caught
    by Codex on PR #74 re-audit; fix re-checks the LATEST event
    explicitly after the error/waiting scan.
    """
    if not events:
        return "idle"
    for ev in reversed(events):
        if ev.get("status") == "failed":
            return "error"
        if ev.get("requires_human") is True:
            return "waiting"
    if events[-1].get("type") == "file_change":
        return "processing"
    return "idle"


def _package_version() -> str:
    """Return the installed ``karasu`` package version, or
    ``"unknown"`` if the package is not installed (running from
    a source checkout without ``pip install -e .``). The UI
    footer prefers a graceful "v—" over a 500."""
    try:
        return importlib_metadata.version("karasu")
    except importlib_metadata.PackageNotFoundError:
        return "unknown"


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
        extra_headers: tuple[tuple[str, str], ...] = (),
    ) -> None:
        """Write a response. ``extra_headers`` carries optional
        headers added before ``end_headers``; UI-8 uses it to set
        ``Service-Worker-Allowed: /`` on the SW response so the
        worker registered from /assets/sw.js can scope to root.
        """
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in extra_headers:
            self.send_header(name, value)
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
            flight = _flight_route(events)
            self._send_json(
                {
                    "status": "ok",
                    "events": len(events),
                    "crow": _crow_state(events),
                    # UI-6 — Live Map projection. ``null`` when the
                    # bus is silent or the latest event has no
                    # mapped pair (parked crow); otherwise
                    # ``{"source": <node>, "target": <node>}``.
                    "flight": (
                        {"source": flight[0], "target": flight[1]}
                        if flight is not None
                        else None
                    ),
                }
            )
            return

        # UI-3 — surface enough metadata for the application
        # shell to render its own version line and bus-path
        # badge without hard-coding either. Read-only and
        # additive; no other endpoint changes shape.
        if path == "/api/meta":
            self._send_json(
                {
                    "version": _package_version(),
                    "bus_path": str(EVENT_LOG),
                }
            )
            return

        if path in ("/", "/index.html"):
            html = (STATIC_DIR / "index.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return

        # UI-8 — offline shell served by the service worker as a
        # navigation fallback when the network is unreachable. The
        # route is also reachable directly so the auditor can open
        # the page during the screenshot pass without faking a
        # network failure.
        if path == "/offline.html":
            html = (STATIC_DIR / "offline.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return

        # /design-system is an unlinked tool / debug page (UI-0
        # §6, leaned in next-session.md). It documents every
        # token from the design system in live code so a token
        # change is verifiable by rendering this page. Stays
        # accessible in production builds; not advertised from
        # the operator surface.
        if path == "/design-system":
            html = (STATIC_DIR / "design-system.html").read_bytes()
            self._send(200, html, "text/html; charset=utf-8")
            return

        # Static assets land in /assets/* and resolve under
        # STATIC_DIR. The /assets/ namespace exposes static
        # subdirs (css/, fonts/, sprites/...) at the URL level
        # while keeping the on-disk layout flat under static/.
        # Path-traversal guard: target must resolve under
        # STATIC_DIR.
        if path.startswith("/assets/"):
            target = (STATIC_DIR / path[len("/assets/"):]).resolve()
            try:
                target.relative_to(STATIC_DIR.resolve())
            except ValueError:
                self._send(403, b"forbidden", "text/plain")
                return
            if target.is_file():
                # UI-8 — the service worker file MUST carry
                # ``Service-Worker-Allowed: /`` so the SW
                # registered from /assets/sw.js can scope to
                # root. Without the header, the browser rejects
                # the registration with a SecurityError because
                # an SW's default scope is the directory it lives
                # in (/assets/), and we need it to intercept
                # navigation requests for the entire site.
                extra: tuple[tuple[str, str], ...] = ()
                if path == "/assets/sw.js":
                    extra = (("Service-Worker-Allowed", "/"),)
                self._send(
                    200,
                    target.read_bytes(),
                    _content_type_for(target),
                    extra_headers=extra,
                )
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
