"""Karasu UI HTTP server.

Stdlib-only ThreadingHTTPServer. Reads ``.karasu/events.jsonl``
on each request and exposes:

  GET  /                          static index.html (the UI shell)
  GET  /design-system             UI-2 token documentation page
  GET  /api/events                paginated event projection
  GET  /api/health                server + crow state summary
  GET  /api/meta                  version + configured bus path (UI-3)
  GET  /api/agents                configured adapters + trust levels (UI-11a)
  GET  /api/scars                 active scars list (UI-10)
  POST /api/scars/{id}/revoke     append revoke + emit bus event (UI-10)
  GET  /assets/...                static assets (fonts, sprites, css)

The projection in ``_project_event`` mirrors the bus schema as
of UI-1: the additive fields landed during chunks 4a/4b/4c +
the chain-cap implementation are surfaced so downstream UI
chunks (timeline, detail panel, Live Map) can render the full
audit picture without extra round-trips.

UI-10 introduces the surface's first write path. The POST
endpoint is local-only (the operator IS the human running the
process — no auth in this brief; UI-12+ deployed surfaces earn
their own auth design). Every successful revoke appends a
``human_decision`` event to the bus with
``data.action="scar_revoke"`` so the timeline annotates the
revocation by the next ``/api/events`` tick.
"""

from __future__ import annotations

import gzip
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

# UI-9 follow-up — content types worth compressing on the wire.
# woff2 fonts and PNG icons are already compressed; gzip-ing
# them again is CPU for no payload win. Restrict to text-shaped
# resources only.
_GZIP_CONTENT_TYPES = (
    "text/html",
    "text/css",
    "application/javascript",
    "application/json",
    "image/svg+xml",
)
# Minimum response size before we bother gzipping. Below this,
# the gzip framing overhead can equal or exceed the savings.
_GZIP_MIN_BYTES = 1024

# Static asset cache TTL. 24 h is conservative for a tool
# that ships under active development without fingerprinted
# asset URLs (a fingerprinting build step would let us safely
# use 1 year per Lighthouse's recommendation; UI-0 §4 forbids
# the build step). One day strikes the balance between
# Lighthouse's ``uses-long-cache-ttl`` audit threshold and the
# need for newly-deployed CSS / SVG to land within a working
# day. The SW pre-cache list in sw.js + the CACHE_NAME
# version-bump rule are the durable invalidation mechanism;
# this header just lets the browser reuse static assets across
# page navigations within a single session without a round-trip.
_STATIC_CACHE_MAX_AGE = 86400

# Default bus path. Mutable so ``configure(event_log=...)`` can
# point the UI server at a non-default ``karasu.yaml`` bus
# location (UI-9 deferred follow-up). Tests and ``cmd_ui``
# override this; the default keeps the dogfood path working
# for an operator running ``karasu ui`` from a fresh checkout
# without a config file.
EVENT_LOG = Path(".karasu/events.jsonl")
STATIC_DIR = Path(__file__).parent / "static"

# Default scar rules path. Same configure-or-default contract as
# ``EVENT_LOG``: ``cmd_ui`` overrides via ``configure(...)`` so
# ``karasu ui`` honours ``scars.rules_path`` from ``karasu.yaml``;
# tests override directly. The default mirrors
# ``karasu.__main__.DEFAULT_SCARS`` so a fresh checkout works.
SCARS_PATH = Path(".karasu/scars/")

# UI-11a — config path for read-only agent/trust projection.
# ``cmd_ui`` wires this from the same ``--config`` argument that
# ``cmd_watch`` uses. Tests override it via ``configure(...)``.
CONFIG_PATH = Path("karasu.yaml")

# UI-10 — bound on the POST body for /api/scars/{id}/revoke.
# Modal textarea caps the operator's reason on the client; the
# server is the second line of defence. 4 KiB matches the
# pattern UI-7 used for the cap on review-comment bodies.
_REVOKE_BODY_MAX_BYTES = 4096

# UI-10 — scar id character set (brief §10.1). Mirrored on the
# wire and in the URL pattern so an id outside the regex is a
# server-side bug, not a UI input concern.
_SCAR_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_REVOKE_PATH_RE = re.compile(r"^/api/scars/([A-Za-z0-9._:-]+)/revoke$")

# Sentinels returned by ``UIHandler._read_revoke_reason`` so the
# caller can map distinct error shapes to distinct HTTP statuses
# without raising. ``object()`` per sentinel so identity checks
# are unambiguous.
_MALFORMED_BODY = object()
_BODY_TOO_LARGE = object()
_BODY_NOT_OBJECT = object()

# Default page size for /api/events. Operator can override via
# ?limit=N (capped at MAX_EVENT_LIMIT to bound memory in the
# face of an enormous bus).
DEFAULT_EVENT_LIMIT = 100
MAX_EVENT_LIMIT = 1000

_SUPPORTED_TRUST_LEVELS = frozenset({0, 1, 2})
_AGENT_DEFAULTS: dict[str, dict[str, Any]] = {
    "claude_code": {
        "trust_level": 1,
        "handles": ("code_change", "bug_fix", "implementation"),
    },
    "codex": {
        "trust_level": 0,
        "handles": ("code_review", "audit"),
    },
}


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
        # data — human_decision subtype (UI-10+ write-path events)
        "action": data.get("action"),
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


def _list_active_scars() -> list[dict[str, Any]]:
    """Project the active (non-revoked) scars for ``GET /api/scars``.

    Brief §10.5: only the fields ScarEngine exposes naturally
    ship in the projection — ``id``, ``correction_text``,
    ``created_at``. ``status`` / ``revoked_at`` /
    ``applied_count`` / ``last_applied_at`` would require new
    plumbing in ScarEngine and are explicitly deferred (the UI
    annotates revoked scars from request context + the emitted
    ``human_decision`` event instead, per pin §11.6.4).

    ``correction_text`` is a deterministic JSON serialisation of
    the correction dict — sorted keys + ``ensure_ascii=False`` —
    so the operator surface can quote the rule the original
    ``/scar`` command produced. Stable text is what the modal
    quote contract assumes.
    """
    from karasu.scars import ScarEngine

    engine = ScarEngine(SCARS_PATH)
    out: list[dict[str, Any]] = []
    for scar in engine.all():
        out.append(
            {
                "id": scar.id,
                "correction_text": json.dumps(
                    scar.correction, ensure_ascii=False, sort_keys=True
                ),
                "created_at": scar.created,
            }
        )
    return out


def _list_agents() -> list[dict[str, Any]]:
    """Project configured adapters for ``GET /api/agents``.

    UI-11a is read-only: it reads ``karasu.yaml`` directly and
    never reaches into running adapter instances. This keeps
    ``karasu ui`` useful when ``karasu watch`` is not running and
    preserves the separate-process contract pinned in the UI-11
    brief. Unknown adapter names are skipped because the current
    runtime can only construct the adapters in ``_AGENT_DEFAULTS``.
    """
    from karasu.__main__ import _load_config, _normalize_handles

    config = _load_config(CONFIG_PATH)
    agents_cfg = config.get("agents", {}) or {}
    if not isinstance(agents_cfg, dict):
        return []

    out: list[dict[str, Any]] = []
    for name, defaults in _AGENT_DEFAULTS.items():
        raw = agents_cfg.get(name)
        if raw is None or raw is False:
            continue
        if not isinstance(raw, dict):
            continue
        # Mirrors ``_adapters``: codex without a repo is not an
        # active adapter, even if the config section exists.
        if name == "codex" and not raw.get("repo"):
            continue

        trust_level = int(raw.get("trust_level", defaults["trust_level"]))
        raw_handles = raw.get("handles")
        handles = (
            defaults["handles"]
            if raw_handles is None
            else _normalize_handles(name, raw_handles)
        )
        record: dict[str, Any] = {
            "name": name,
            "trust_level": trust_level,
            "handles": list(handles),
        }
        if trust_level not in _SUPPORTED_TRUST_LEVELS:
            record["unsupported"] = True
        out.append(record)
    return out


def _emit_human_decision(action: str, data: dict[str, Any]) -> None:
    """Append a ``human_decision`` event to the configured bus.

    UI-10 is the first write path on the UI surface; the helper
    is intentionally tiny so the audit trail is obvious. Lazy
    import keeps the read-only paths free of the import cost.
    """
    from karasu.eventbus.jsonl_bus import Event, JsonlEventBus

    payload: dict[str, Any] = {"action": action}
    payload.update(data)
    bus = JsonlEventBus(EVENT_LOG)
    bus.append(Event(type="human_decision", source="ui", data=payload))


class UIHandler(BaseHTTPRequestHandler):
    """HTTP handler.

    GET routes are read-only sinks over the bus (and over the
    ScarEngine for ``/api/scars``). The POST route added in
    UI-10 (``/api/scars/{id}/revoke``) is the operator surface's
    first write path — local-only, single-scar, network-only
    (the SW handler from UI-8 already pins ``/api/*`` to
    network-only), 204 on success."""

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

        UI-9 follow-up — compress text-shaped responses with gzip
        when the client advertises support and the body is larger
        than ``_GZIP_MIN_BYTES``. The compression is purely a
        Lighthouse Performance lift; it does NOT change the
        response semantics or wire shape (the JSON / HTML / CSS
        body is identical after the client decompresses).

        ``Content-Encoding: gzip`` is added BEFORE
        ``end_headers``; ``Content-Length`` is recomputed from
        the compressed bytes. Non-text responses (PNG icons,
        woff2 fonts) skip the path because they're already
        compressed at the format level.
        """
        accept_encoding = self.headers.get("Accept-Encoding", "")
        gzip_ok = (
            "gzip" in accept_encoding
            and any(content_type.startswith(t) for t in _GZIP_CONTENT_TYPES)
            and len(body) >= _GZIP_MIN_BYTES
        )
        if gzip_ok:
            body = gzip.compress(body, compresslevel=6, mtime=0)

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if gzip_ok:
            self.send_header("Content-Encoding", "gzip")
            # Tell shared caches the cached entity varies by the
            # request's Accept-Encoding so a client that did NOT
            # ask for gzip never sees a cached compressed body.
            self.send_header("Vary", "Accept-Encoding")
        for name, value in extra_headers:
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload: Any) -> None:
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

        # UI-11a — read-only trust display source. Reads the
        # configured adapters from karasu.yaml directly; does not
        # require ``karasu watch`` and does not mutate adapter state.
        if path == "/api/agents":
            self._send_json(_list_agents())
            return

        # UI-10 — active scars list. Companion read endpoint to
        # the POST revoke pathway: the drawer fetches this to
        # render the scar's stored correction text inside the
        # confirmation modal.
        if path == "/api/scars":
            self._send_json({"scars": _list_active_scars()})
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
                #
                # UI-9 follow-up — Cache-Control on every static
                # asset response. The SW pre-cache list in sw.js
                # handles the durable offline shell; this header
                # lets the browser reuse static assets across
                # page navigations without a round-trip.
                # Lighthouse 2026-05-04 baseline flagged
                # ``uses-long-cache-ttl`` as the largest single
                # Performance audit miss. ``public`` lets shared
                # caches store the response; the SW + the
                # CACHE_NAME version-bump rule in sw.js are the
                # invalidation mechanism on real deploys. The
                # service worker file itself is excluded from
                # long caching because the SW spec already gives
                # it a 24 h max-age cap regardless of header,
                # and we want bumped CACHE_NAME values to land
                # quickly during development.
                extra: list[tuple[str, str]] = []
                if path == "/assets/sw.js":
                    extra.append(("Service-Worker-Allowed", "/"))
                    extra.append(
                        ("Cache-Control", "no-cache")
                    )
                else:
                    extra.append(
                        (
                            "Cache-Control",
                            f"public, max-age={_STATIC_CACHE_MAX_AGE}",
                        )
                    )
                self._send(
                    200,
                    target.read_bytes(),
                    _content_type_for(target),
                    extra_headers=tuple(extra),
                )
                return

        self._send(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler API
        """Write paths.

        UI-10 ships the only POST route: scar revoke. Returns
        204 with no body on success, per brief §3-E. Single-scar
        only — batch revokes are a UI-12+ concern.
        """
        path, _, _ = self.path.partition("?")
        m = _REVOKE_PATH_RE.match(path)
        if m is None:
            # Method-not-allowed for paths the GET handler knows
            # about (so a stray POST to /api/health gets a 405,
            # not a 404 that hides the typo); 404 for everything
            # else.
            if path in (
                "/",
                "/index.html",
                "/offline.html",
                "/design-system",
                "/api/events",
                "/api/health",
                "/api/meta",
                "/api/agents",
                "/api/scars",
            ):
                self._send(405, b"method not allowed", "text/plain")
                return
            self._send(404, b"not found", "text/plain")
            return

        scar_id = m.group(1)
        # The path regex already accepted only [A-Za-z0-9._:-]+;
        # double-check via the canonical id regex to fail loud if
        # the two ever diverge.
        if not _SCAR_ID_RE.match(scar_id):
            self._send(400, b"invalid scar id", "text/plain")
            return

        reason = self._read_revoke_reason()
        if reason is _MALFORMED_BODY:
            self._send(422, b"malformed json", "text/plain")
            return
        if reason is _BODY_TOO_LARGE:
            self._send(413, b"payload too large", "text/plain")
            return
        if reason is _BODY_NOT_OBJECT:
            self._send(422, b"json body must be an object", "text/plain")
            return

        from karasu.scars import ScarEngine

        engine = ScarEngine(SCARS_PATH)
        if not engine.revoke(scar_id, reason=reason):
            # Scar id unknown OR already revoked. Same shape so
            # the UI does not need to distinguish — the operator
            # already saw the scar disappear from the active
            # list.
            self._send(404, b"scar not found or already revoked", "text/plain")
            return

        event_data: dict[str, Any] = {"scar_id": scar_id}
        if reason:
            event_data["reason"] = reason
        _emit_human_decision("scar_revoke", event_data)

        # 204 No Content — brief §3-E: the endpoint is
        # intentionally empty so the UI re-fetches /api/scars
        # and reads the human_decision event from /api/events
        # to annotate the post-revoke state. Pin §11.6.3 (POST
        # returns 204) is verified by the HTTP shape lock.
        self._send(204, b"", "application/octet-stream")

    def _read_revoke_reason(self) -> "str | None | object":
        """Read + validate the optional ``{reason}`` body.

        Returns:
          * ``str`` (trimmed, non-empty) — the operator's reason.
          * ``None`` — body absent OR ``reason`` field missing /
            empty after trim. Brief §10.2: empty reason MUST
            NOT block the revoke.
          * One of the ``_MALFORMED_BODY`` /
            ``_BODY_TOO_LARGE`` / ``_BODY_NOT_OBJECT`` sentinels
            — caller maps to the matching HTTP status.
        """
        try:
            declared = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            declared = 0
        if declared > _REVOKE_BODY_MAX_BYTES:
            return _BODY_TOO_LARGE
        if declared == 0:
            return None
        body = self.rfile.read(declared)
        if not body:
            return None
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _MALFORMED_BODY
        if not isinstance(payload, dict):
            return _BODY_NOT_OBJECT
        raw_reason = payload.get("reason")
        if not isinstance(raw_reason, str):
            return None
        trimmed = raw_reason.strip()
        return trimmed or None

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


def configure(
    event_log: Path,
    scars_path: Path | None = None,
    config_path: Path | None = None,
) -> None:
    """Override the paths the UI server reads from / writes to.

    Called by ``cmd_ui`` (so ``karasu ui`` honours
    ``event_bus.path`` and ``scars.rules_path`` in
    ``karasu.yaml``) and by tests. Pure mutation of the module
    globals; subsequent requests see the new values on the next
    read because ``_read_events`` and ``_list_active_scars``
    resolve the globals at call time.

    UI-10 added the optional ``scars_path`` parameter. UI-11a
    added ``config_path`` so ``GET /api/agents`` reads the same
    ``karasu.yaml`` path the CLI was given. Omitting either leaves
    the pre-existing default.
    """
    global EVENT_LOG, SCARS_PATH, CONFIG_PATH
    EVENT_LOG = event_log
    if scars_path is not None:
        SCARS_PATH = scars_path
    if config_path is not None:
        CONFIG_PATH = config_path


def run_ui_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    event_log: Path | None = None,
    scars_path: Path | None = None,
    config_path: Path | None = None,
) -> None:
    """Start the UI HTTP server. Blocks until interrupted.

    ``event_log`` overrides the default ``.karasu/events.jsonl``
    bus path; ``scars_path`` overrides the default
    ``.karasu/scars/`` rules directory (UI-10); ``config_path``
    points the UI-11a agent/trust projection at the same
    ``karasu.yaml`` the CLI loaded. Callers that omit kwargs keep
    the pre-existing defaults.
    """
    if event_log is not None or scars_path is not None or config_path is not None:
        configure(
            event_log=event_log if event_log is not None else EVENT_LOG,
            scars_path=scars_path,
            config_path=config_path,
        )
    server = ThreadingHTTPServer((host, port), UIHandler)
    print(f"karasu ui → http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
