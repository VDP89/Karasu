"""Karasu UI HTTP server.

Stdlib-only ThreadingHTTPServer. Reads ``.karasu/events.jsonl``
on each request and exposes:

  GET  /                          static index.html (the UI shell)
  GET  /design-system             UI-2 token documentation page
  GET  /api/events                paginated event projection
  GET  /api/health                server + crow state summary
  GET  /api/meta                  version + configured bus path (UI-3)
  GET  /api/agents                configured adapters + trust levels (UI-11a)
  POST /api/agents/{name}/trust   persist trust intent + emit bus event (UI-11b)
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
import logging
import re
import yaml
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote

from karasu.ui._auth import (
    AuthCredentials,
    AuthCredentialsError,
    AuthSessionError,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    LoginRateLimit,
    SESSION_COOKIE_NAME,
    UNTRUSTED_FORWARDED,
    derive_client_ip,
    dummy_password_verify,
    is_anonymous_path,
    is_loopback_ip,
    issue_csrf_token,
    issue_session_token,
    load_credentials,
    origin_matches,
    parse_forwarded_chain,
    verify_csrf,
    verify_password,
    verify_session_token,
)

_auth_log = logging.getLogger("karasu.ui.auth")

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

# UI-12a — push subscription store path (UI-12 brief §3-F /
# §11.6 PRIVATE STORE). Default lives next to the bus log; the
# ``--push-store`` flag on ``karasu ui`` overrides per process.
# UI-12a is read-only against this path; UI-12b earns the
# subscribe / unsubscribe writers, UI-12c earns VAPID
# generation behind the ``cryptography`` exception (§11.6.13).
PUSH_STORE_PATH = Path("karasu-push.json")

# UI-13 — auth state. Set by ``configure_auth()``; the default
# is ``AUTH_NO_AUTH=True`` so UI tests that pre-date UI-13 (and
# the local --no-auth dev posture) keep working without
# threading credentials through every fixture. ``cmd_ui``
# enables auth by calling ``configure_auth(no_auth=False, ...)``
# at startup; the brief §3-B fail-closed contract refuses to
# bind the listener if creds are missing.
AUTH_NO_AUTH: bool = True
AUTH_DEPLOYED: bool = False
AUTH_TRUSTED_PROXIES: frozenset[str] = frozenset({"127.0.0.1", "::1"})
AUTH_EXPECTED_ORIGINS: tuple[str, ...] = ()
AUTH_CREDENTIALS_PATH: Path | None = None
_AUTH_CREDS_CACHE: AuthCredentials | None = None
_AUTH_RATE_LIMIT: LoginRateLimit | None = None

# Login JSON body cap. Real bodies are ~200 bytes (username +
# password); 4 KiB matches the existing per-POST cap parity from
# UI-10 / UI-11b / UI-12b.
_LOGIN_BODY_MAX_BYTES = 4096

# Sentinels for login body parsing — same shape as the UI-10
# revoke / UI-12b push sentinels so the handler maps cleanly to
# distinct HTTP statuses without raising.
_LOGIN_MALFORMED_JSON = object()
_LOGIN_BODY_NOT_OBJECT = object()
_LOGIN_BODY_TOO_LARGE = object()
_LOGIN_INVALID_FIELDS = object()

# UI-10 — bound on the POST body for /api/scars/{id}/revoke.
# Modal textarea caps the operator's reason on the client; the
# server is the second line of defence. 4 KiB matches the
# pattern UI-7 used for the cap on review-comment bodies.
_REVOKE_BODY_MAX_BYTES = 4096
_TRUST_BODY_MAX_BYTES = 4096

# UI-12b — body cap parity (brief §10.5): both POSTs share one
# 4 KiB cap. Real subscribe payloads are ~600 bytes; unsubscribe
# is ~200; the parity simplifies the test surface.
_PUSH_BODY_MAX_BYTES = 4096

# UI-10 — scar id character set (brief §10.1). Mirrored on the
# wire and in the URL pattern so an id outside the regex is a
# server-side bug, not a UI input concern.
_SCAR_ID_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_REVOKE_PATH_RE = re.compile(r"^/api/scars/([A-Za-z0-9._:-]+)/revoke$")
_TRUST_PATH_RE = re.compile(r"^/api/agents/([A-Za-z0-9._:-]+)/trust$")

# UI-12b — push opt-in surface. Two new POST routes, both
# 204-on-success, both inside /api/* (network-only by SW
# construction per pin §11.6.4).
_PUSH_SUBSCRIBE_PATH = "/api/push/subscribe"
_PUSH_UNSUBSCRIBE_PATH = "/api/push/unsubscribe"

# UI-12b §3-B — Web Push endpoints are always HTTPS URLs; a
# plain HTTP endpoint cannot be a real PushSubscription. The
# regex matches scheme://host/path with at least one path
# character so an empty path does not slip through.
_PUSH_HTTPS_ENDPOINT_RE = re.compile(r"^https://[^/]+/.+$")

# Sentinels returned by ``UIHandler._read_revoke_reason`` so the
# caller can map distinct error shapes to distinct HTTP statuses
# without raising. ``object()`` per sentinel so identity checks
# are unambiguous.
_MALFORMED_BODY = object()
_BODY_TOO_LARGE = object()
_BODY_NOT_OBJECT = object()
_INVALID_TRUST_LEVEL = object()

# UI-12b sentinels — the brief §3-B distinguishes the
# malformed-JSON branch (400) from the non-object-body branch
# (422), with distinct generic response bodies. Existing UI-10 /
# UI-11b reuse _MALFORMED_BODY for both at 422; UI-12b's
# response shape diverges to honour pin §11.6.5 (400 + 422 with
# generic bodies that never echo request fragments).
_PUSH_MALFORMED_JSON = object()
_PUSH_BODY_NOT_OBJECT = object()
_PUSH_BODY_TOO_LARGE = object()
_PUSH_INVALID_FIELDS = object()
_PUSH_VAPID_NOT_PROVISIONED = object()

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
    if not isinstance(config, dict):
        return []
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

        raw_trust = raw.get("trust_level", defaults["trust_level"])
        try:
            trust_level: Any = int(raw_trust)
        except (TypeError, ValueError):
            trust_level = raw_trust
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


def _configured_agent_record(name: str) -> dict[str, Any] | None:
    """Return one active /api/agents record by adapter name."""
    for record in _list_agents():
        if record.get("name") == name:
            return record
    return None


def _persist_agent_trust(name: str, trust_level: int) -> None:
    """Persist ``agents.<name>.trust_level`` in ``CONFIG_PATH``.

    UI-11b is intent-only with respect to live adapter instances:
    this helper never reaches into ``karasu watch``. It updates the
    configured value so the recorded intent becomes effective after
    the operator restarts the watcher.
    """
    from karasu.__main__ import _load_config

    config = _load_config(CONFIG_PATH)
    if not isinstance(config, dict):
        config = {}
    agents_cfg = config.setdefault("agents", {})
    if not isinstance(agents_cfg, dict):
        agents_cfg = {}
        config["agents"] = agents_cfg
    raw = agents_cfg.get(name)
    if not isinstance(raw, dict):
        raw = {}
        agents_cfg[name] = raw
    raw["trust_level"] = trust_level

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_name(f"{CONFIG_PATH.name}.tmp")
    tmp.write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    tmp.replace(CONFIG_PATH)


def _list_push_state() -> dict[str, Any]:
    """Project the push store at :data:`PUSH_STORE_PATH` for
    ``GET /api/push``.

    Reads the store file via :func:`push_store.read_push_store`
    and projects the result through
    :func:`push_store.project_push_state_payload`. Both helpers
    enforce the privacy contract (§11.6.5 + §11.6.16) — only
    the subscription count and the public VAPID key surface;
    raw endpoints and keys never leave the store.

    A missing store returns the empty-state payload so the
    surface works on a fresh checkout. A malformed store raises
    ``PushStoreError`` and surfaces as a 500 rather than
    silently coercing garbage; the operator's recourse is to
    delete the file and let UI-12b re-bootstrap.
    """
    from karasu.ui.push_store import (
        project_push_state_payload,
        read_push_store,
    )

    state = read_push_store(PUSH_STORE_PATH)
    return project_push_state_payload(state)


def _push_store_has_vapid() -> bool:
    """Lazy wrapper around :func:`push_store.has_vapid_keys`
    against the configured ``PUSH_STORE_PATH``.

    Lazy import keeps the read-only paths free of the import
    cost on every event tick (the bus pumps /api/events 3 s and
    only POST handlers reach this helper).
    """
    from karasu.ui.push_store import has_vapid_keys

    return has_vapid_keys(PUSH_STORE_PATH)


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
    ScarEngine for ``/api/scars``). The POST routes added in
    UI-10 / UI-11b are local-only, drawer-earned, network-only
    (the SW handler from UI-8 already pins ``/api/*`` to
    network-only), 204 on success.

    UI-13 wraps every request behind an auth perimeter: the
    anonymous whitelist (§3-D) bypasses session checks; every
    other path requires a valid session cookie + (for mutating
    methods) a valid CSRF double-submit token. The default
    posture is ``AUTH_NO_AUTH=True`` so tests that pre-date
    UI-13 keep passing; ``configure_auth(no_auth=False, ...)``
    flips into the deployed posture."""

    # Stash for the authenticated user resolved by
    # ``_authorize_request``; consulted by handlers that emit
    # human_decision events so the operator's username can
    # land on the bus alongside the action.
    _authenticated_user: str | None = None

    # ---- UI-13 auth helpers --------------------------------------

    def _parse_cookies(self) -> dict[str, str]:
        """Parse the ``Cookie`` request header into a dict.

        Multiple cookies with the same name → last wins (matches
        browser behaviour). Quoted values keep their quotes; the
        verifiers don't care about the framing."""
        raw = self.headers.get("Cookie", "")
        out: dict[str, str] = {}
        for piece in raw.split(";"):
            piece = piece.strip()
            if not piece or "=" not in piece:
                continue
            name, _, value = piece.partition("=")
            out[name.strip()] = value.strip()
        return out

    def _derive_client_ip(self) -> str | object:
        """Apply §3-G three-layer derivation against this
        request. Returns either an IP string,
        ``UNTRUSTED_FORWARDED`` sentinel, or ``None`` (all-
        trusted chain — caller fail-closes)."""
        peer_addr = self.client_address[0]
        chain = parse_forwarded_chain(
            forwarded_header=self.headers.get("Forwarded"),
            xff_header=self.headers.get("X-Forwarded-For"),
        )
        return derive_client_ip(
            peer_addr=peer_addr,
            forwarded_chain=chain,
            trusted_proxies=AUTH_TRUSTED_PROXIES,
        )

    def _ip_for_rate_limit(self) -> str:
        """Resolve a concrete IP key for the rate-limit slot.

        Codex P0 round 1 audit binding 2026-05-08: when
        derive_client_ip returns UNTRUSTED_FORWARDED or None,
        the slot key MUST NOT be a loopback IP — otherwise
        ``LoginRateLimit.check`` short-circuits via
        ``is_loopback_ip`` and the public-guessing bypass
        that round 3 P1 closed at the primitive level
        re-opens at the server layer.

        Resolution per §3-G post-derivation rules:
          * IP string from derive_client_ip → use verbatim.
          * UNTRUSTED_FORWARDED → synthetic key
            ``"!untrusted:<peer_addr>"``. Bucket is still
            per-peer (so a flood from one untrusted peer is
            bounded), but the prefix guarantees the string
            never matches ``is_loopback_ip``'s 127.0.0.0/8 +
            ::1 set, so the bypass cannot fire.
          * None (all-trusted chain — impossible for
            external traffic) → synthetic key
            ``"!unknown:<peer_addr>"``. Same fail-closed
            shape: fresh slot keyed by peer, never loopback.
        """
        peer_addr = self.client_address[0]
        derived = self._derive_client_ip()
        if isinstance(derived, str):
            return derived
        if derived is UNTRUSTED_FORWARDED:
            return f"!untrusted:{peer_addr}"
        return f"!unknown:{peer_addr}"

    def _session_payload(self) -> dict[str, Any] | None:
        """Verify the session cookie and return the payload, or
        None when no valid session is present. Returns None in
        no-auth posture; the caller decides what that means."""
        if AUTH_NO_AUTH or _AUTH_CREDS_CACHE is None:
            return None
        token = self._parse_cookies().get(SESSION_COOKIE_NAME)
        if not token:
            return None
        try:
            return verify_session_token(token, creds=_AUTH_CREDS_CACHE)
        except AuthSessionError:
            return None

    def _verify_csrf_for_request(self, payload: dict[str, Any]) -> bool:
        """Constant-time CSRF double-submit check using the
        verified session payload (§3-F)."""
        cookies = self._parse_cookies()
        return verify_csrf(
            cookie_value=cookies.get(CSRF_COOKIE_NAME),
            header_value=self.headers.get(CSRF_HEADER_NAME),
            creds=_AUTH_CREDS_CACHE,
            username=payload["user"],
            gen=payload["gen"],
        )

    def _authorize_request(self, method: str, path: str) -> bool:
        """Run the auth perimeter (§3-D). Returns True if the
        handler should proceed; False if a response was already
        written.

        no-auth posture → unconditionally True.
        Anonymous path  → True (handler may still apply route-
                           specific Origin checks, e.g. /auth/login
                           and GET /auth/logout in deployed posture).
        Auth-required path:
          GET without session  → 302 redirect to /
          POST without session → 401
          POST with session but bad CSRF → 403
          Otherwise           → True
        """
        if AUTH_NO_AUTH:
            return True
        if is_anonymous_path(method, path):
            return True
        payload = self._session_payload()
        if payload is None:
            if method == "GET":
                self._send(
                    302,
                    b"",
                    "text/plain",
                    extra_headers=(("Location", "/"),),
                )
            else:
                self._send(
                    401,
                    b'{"error":"unauthorized"}',
                    "application/json",
                )
            return False
        if method != "GET":
            if not self._verify_csrf_for_request(payload):
                self._send(
                    403,
                    b'{"error":"forbidden"}',
                    "application/json",
                )
                return False
        self._authenticated_user = payload["user"]
        return True

    # ---- end UI-13 auth helpers ----------------------------------

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

        if not self._authorize_request("GET", path):
            return

        # UI-13 — GET /auth/logout (anonymous + idempotent
        # recovery shape per §3-D logout split). Same-origin
        # Referer/Origin check enforced in deployed posture
        # (Codex round 2 P2 binding); cookies cleared on
        # success; cross-site forced-logout produces 403 + NO
        # cookie mutation.
        if path == "/auth/logout":
            self._handle_logout_get()
            return

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

        # UI-12a — push notification surface state. Read-only
        # projection of the push subscription store. The shape
        # is pinned by the HTTP shape lock in
        # tests/test_ui_server_http.py. Server-side ``state`` is
        # always ``"supported"``; the client reflects
        # browser-feature-detected ``"unsupported"`` /
        # ``"denied"`` per UI-12 brief §10.9 against this
        # baseline. Pin §11.6.5 + §11.6.16: raw endpoint URLs
        # and keys NEVER appear here — only the count and the
        # public VAPID key (when present). A malformed store
        # surfaces as 500 rather than silently coercing to an
        # empty count — the operator's recourse is to delete
        # the file and let UI-12b re-bootstrap.
        if path == "/api/push":
            from karasu.ui.push_store import PushStoreError

            try:
                payload = _list_push_state()
            except PushStoreError:
                self._send(
                    500,
                    b'{"error": "push store malformed"}',
                    "application/json",
                )
                return
            self._send_json(payload)
            return

        if path in ("/", "/index.html"):
            # UI-13 §3-D: GET / renders the login surface when
            # there is no session (and auth is enabled); the
            # PWA shell otherwise. /index.html stays an alias.
            if (
                AUTH_NO_AUTH
                or self._session_payload() is not None
            ):
                html = (STATIC_DIR / "index.html").read_bytes()
            else:
                html = (STATIC_DIR / "login.html").read_bytes()
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

        UI-10 ships scar revoke. UI-11b adds trust adjust.
        UI-12b adds push subscribe + unsubscribe. UI-13 adds
        POST /auth/login (anonymous, CSRF-cookie-exempt) +
        POST /auth/logout (auth+CSRF-required, JS-driven from
        the PWA shell). All five return 204 with no body on
        success and emit auditable ``human_decision`` events
        where applicable.
        """
        path, _, _ = self.path.partition("?")

        if not self._authorize_request("POST", path):
            return

        # UI-13 login + logout split (§3-D + §3-F).
        if path == "/auth/login":
            self._handle_login_post()
            return
        if path == "/auth/logout":
            self._handle_logout_post()
            return

        revoke = _REVOKE_PATH_RE.match(path)
        trust = _TRUST_PATH_RE.match(path)
        push_subscribe = path == _PUSH_SUBSCRIBE_PATH
        push_unsubscribe = path == _PUSH_UNSUBSCRIBE_PATH

        if (
            revoke is None
            and trust is None
            and not push_subscribe
            and not push_unsubscribe
        ):
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
                "/api/push",
            ):
                self._send(405, b"method not allowed", "text/plain")
                return
            if path == "/auth/logout":
                # GET /auth/logout exists; POST /auth/logout
                # is reached above when authorized. A POST that
                # reached here means authorization rejected it
                # (in no-auth posture there's nothing to log out
                # on the POST side either) — 405 is the honest
                # answer rather than 404.
                self._send(405, b"method not allowed", "text/plain")
                return
            self._send(404, b"not found", "text/plain")
            return

        if push_subscribe:
            self._handle_push_subscribe_post()
            return
        if push_unsubscribe:
            self._handle_push_unsubscribe_post()
            return

        if trust is not None:
            self._handle_trust_post(unquote(trust.group(1)))
            return

        scar_id = revoke.group(1)
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

    def _handle_trust_post(self, agent_name: str) -> None:
        """Handle ``POST /api/agents/{name}/trust``.

        UI-11b is drawer-earned and intent-only: the endpoint
        persists the configured trust value for the next watcher
        run, emits a bus event, and never mutates a live adapter
        instance.
        """
        record = _configured_agent_record(agent_name)
        if record is None:
            self._send(404, b"agent not found", "text/plain")
            return
        trust_before = record.get("trust_level")
        if record.get("unsupported") or trust_before not in _SUPPORTED_TRUST_LEVELS:
            self._send(422, b"unsupported current trust_level", "text/plain")
            return

        payload = self._read_trust_adjust_body()
        if payload is _MALFORMED_BODY:
            self._send(422, b"malformed json", "text/plain")
            return
        if payload is _BODY_TOO_LARGE:
            self._send(413, b"payload too large", "text/plain")
            return
        if payload is _BODY_NOT_OBJECT:
            self._send(422, b"json body must be an object", "text/plain")
            return
        if payload is _INVALID_TRUST_LEVEL:
            self._send(422, b"invalid trust_level", "text/plain")
            return

        assert isinstance(payload, dict)
        trust_after = payload["trust_after"]
        _persist_agent_trust(agent_name, trust_after)

        event_data: dict[str, Any] = {
            "agent": agent_name,
            "trust_before": trust_before,
            "trust_after": trust_after,
        }
        reason = payload.get("reason")
        if reason:
            event_data["reason"] = reason
        _emit_human_decision("trust_adjust", event_data)

        self._send(204, b"", "application/octet-stream")

    # --- UI-12b push handlers --------------------------------------

    def _handle_push_subscribe_post(self) -> None:
        """Handle ``POST /api/push/subscribe``.

        Brief §3-B happy path: 204, NO body, store updated +
        idempotent UPDATE for duplicate endpoints, fresh
        push_subscribe event emitted on the bus regardless
        (operator's intent is authoritative).

        Validation matrix per brief §3-B + pin §11.6.5:

          400 — body NOT valid JSON. Generic body
                 ``{"error": "invalid request"}``; never echoes
                 raw bytes or JSONDecodeError text.
          413 — body > 4 KiB.
          422 — body shape wrong (top-level non-object, missing
                 required field, invalid endpoint, invalid
                 categories enum / shape, duplicates).
          503 — VAPID public + private not provisioned in store.
                 Generic body; defensive only — the frontend
                 short-circuits BEFORE calling this endpoint
                 when /api/push.vapid_public_key is null
                 (pin §11.6.14).
          500 — push store malformed (read failed). Generic
                 body matching the GET /api/push 500 contract.
          204 — happy path + idempotent UPDATE.
        """
        from karasu.ui.push_store import (
            PushStoreError,
            append_subscription,
            compute_endpoint_hash,
        )

        # Defensive: if the store is malformed, both the read
        # (for VAPID check) and the writer would raise. Surface
        # one structured 500 rather than letting a bare
        # PushStoreError reach the wire.
        try:
            vapid_ok = _push_store_has_vapid()
        except PushStoreError:
            self._send(
                500,
                b'{"error": "push store malformed"}',
                "application/json",
            )
            return

        if not vapid_ok:
            self._send(
                503,
                b'{"error": "vapid keys not provisioned"}',
                "application/json",
            )
            return

        payload = self._read_push_subscribe_body()
        if payload is _PUSH_BODY_TOO_LARGE:
            self._send(413, b"payload too large", "text/plain")
            return
        if payload is _PUSH_MALFORMED_JSON:
            self._send(
                400,
                b'{"error": "invalid request"}',
                "application/json",
            )
            return
        if payload is _PUSH_BODY_NOT_OBJECT:
            self._send(
                422,
                b'{"error": "request body must be an object"}',
                "application/json",
            )
            return
        if payload is _PUSH_INVALID_FIELDS:
            self._send(
                422,
                b'{"error": "invalid subscription"}',
                "application/json",
            )
            return

        assert isinstance(payload, dict)
        subscription = payload["subscription"]
        categories = payload["categories"]
        endpoint = subscription["endpoint"]

        try:
            append_subscription(
                PUSH_STORE_PATH,
                subscription=subscription,
                categories=categories,
            )
        except PushStoreError:
            # The writer's "partial write recovery needed" path,
            # or any malformed-store path the read leg surfaces.
            # Surface as the same generic 500 the GET path uses.
            self._send(
                500,
                b'{"error": "push store malformed"}',
                "application/json",
            )
            return

        # Pin §11.6.6 + §11.6.16: ONLY the hash + categories
        # land on the bus. Raw endpoint never crosses the
        # human_decision boundary.
        _emit_human_decision(
            "push_subscribe",
            {
                "endpoint_hash": compute_endpoint_hash(endpoint),
                "categories": list(categories),
            },
        )

        self._send(204, b"", "application/octet-stream")

    def _handle_push_unsubscribe_post(self) -> None:
        """Handle ``POST /api/push/unsubscribe``.

        Brief §3-B unsubscribe contract: 204 on store mutation,
        404 when the endpoint is absent (pin §11.6.13 binding —
        the 404 path emits ZERO bus events; the audit is server
        silence on a non-mutation).

        Validation matrix:

          400 — body NOT valid JSON. Same generic shape as
                 subscribe.
          413 — body > 4 KiB.
          422 — non-object body, missing endpoint, or endpoint
                 fails the HTTPS regex.
          404 — endpoint not present in store. Generic body
                 ``{"error": "subscription not found"}``; the
                 supplied endpoint is NOT echoed (pin §11.6.16).
                 NO bus event emitted; NO store mutation.
          500 — push store malformed.
          204 — happy path. push_unsubscribe event emitted.
        """
        from karasu.ui.push_store import (
            PushStoreError,
            PushStoreNotFound,
            compute_endpoint_hash,
            remove_subscription,
        )

        payload = self._read_push_unsubscribe_body()
        if payload is _PUSH_BODY_TOO_LARGE:
            self._send(413, b"payload too large", "text/plain")
            return
        if payload is _PUSH_MALFORMED_JSON:
            self._send(
                400,
                b'{"error": "invalid request"}',
                "application/json",
            )
            return
        if payload is _PUSH_BODY_NOT_OBJECT:
            self._send(
                422,
                b'{"error": "request body must be an object"}',
                "application/json",
            )
            return
        if payload is _PUSH_INVALID_FIELDS:
            self._send(
                422,
                b'{"error": "invalid endpoint"}',
                "application/json",
            )
            return

        assert isinstance(payload, dict)
        endpoint = payload["endpoint"]
        endpoint_hash = compute_endpoint_hash(endpoint)

        try:
            remove_subscription(PUSH_STORE_PATH, endpoint=endpoint)
        except PushStoreNotFound:
            # Pin §11.6.13: 404 path emits ZERO bus events. The
            # server silence is the audit truth — no store
            # mutation, no human_decision. The body is generic
            # so the supplied endpoint never echoes back.
            self._send(
                404,
                b'{"error": "subscription not found"}',
                "application/json",
            )
            return
        except PushStoreError:
            self._send(
                500,
                b'{"error": "push store malformed"}',
                "application/json",
            )
            return

        _emit_human_decision(
            "push_unsubscribe",
            {"endpoint_hash": endpoint_hash},
        )

        self._send(204, b"", "application/octet-stream")

    def _read_push_subscribe_body(self) -> "dict[str, Any] | object":
        """Read + validate the subscribe POST body.

        Validation order matches brief §3-B:
          1. Content-Length cap (413).
          2. JSON parse failure (400 sentinel).
          3. Non-object root (422 sentinel).
          4. Missing / wrong-shape required fields (422 sentinel).
          5. Categories shape (422 sentinel).
          6. Endpoint regex (422 sentinel).

        Returns either the validated dict
        ``{"subscription": {...}, "categories": [...]}`` (with
        categories canonical-sorted per pin §11.6.10) or one of
        the push sentinels.
        """
        try:
            declared = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            declared = 0
        if declared > _PUSH_BODY_MAX_BYTES:
            return _PUSH_BODY_TOO_LARGE
        if declared == 0:
            return _PUSH_MALFORMED_JSON

        body = self.rfile.read(declared)
        if not body:
            return _PUSH_MALFORMED_JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _PUSH_MALFORMED_JSON
        if not isinstance(payload, dict):
            return _PUSH_BODY_NOT_OBJECT

        subscription = payload.get("subscription")
        categories = payload.get("categories")

        if not isinstance(subscription, dict):
            return _PUSH_INVALID_FIELDS
        endpoint = subscription.get("endpoint")
        keys = subscription.get("keys")
        if not isinstance(endpoint, str) or not endpoint:
            return _PUSH_INVALID_FIELDS
        if not _PUSH_HTTPS_ENDPOINT_RE.match(endpoint):
            return _PUSH_INVALID_FIELDS
        if not isinstance(keys, dict):
            return _PUSH_INVALID_FIELDS
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        if not isinstance(p256dh, str) or not p256dh:
            return _PUSH_INVALID_FIELDS
        if not isinstance(auth, str) or not auth:
            return _PUSH_INVALID_FIELDS

        if not isinstance(categories, list):
            return _PUSH_INVALID_FIELDS
        # Pin §11.6.10 — closed enum, no duplicates. Empty array
        # is allowed (zero-noise subscription per pin §11.6.9).
        from karasu.ui.push_store import PUSH_CATEGORIES

        seen: set[str] = set()
        for c in categories:
            if not isinstance(c, str):
                return _PUSH_INVALID_FIELDS
            if c not in PUSH_CATEGORIES:
                return _PUSH_INVALID_FIELDS
            if c in seen:
                return _PUSH_INVALID_FIELDS
            seen.add(c)

        # Canonical sort order — easier to test, easier to grep
        # the bus later. Maps each input to its position in the
        # documented enum so duplicates cannot smuggle through
        # via an alternate ordering.
        canonical = [c for c in PUSH_CATEGORIES if c in seen]

        return {
            "subscription": {
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            "categories": canonical,
        }

    def _read_push_unsubscribe_body(self) -> "dict[str, Any] | object":
        """Read + validate the unsubscribe POST body.

        Same sentinel discipline as
        :meth:`_read_push_subscribe_body`. Successful return is
        ``{"endpoint": "<url>"}``."""
        try:
            declared = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            declared = 0
        if declared > _PUSH_BODY_MAX_BYTES:
            return _PUSH_BODY_TOO_LARGE
        if declared == 0:
            return _PUSH_MALFORMED_JSON

        body = self.rfile.read(declared)
        if not body:
            return _PUSH_MALFORMED_JSON
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _PUSH_MALFORMED_JSON
        if not isinstance(payload, dict):
            return _PUSH_BODY_NOT_OBJECT

        endpoint = payload.get("endpoint")
        if not isinstance(endpoint, str) or not endpoint:
            return _PUSH_INVALID_FIELDS
        if not _PUSH_HTTPS_ENDPOINT_RE.match(endpoint):
            return _PUSH_INVALID_FIELDS

        return {"endpoint": endpoint}

    # ---- UI-13 login / logout handlers ---------------------------

    def _handle_login_post(self) -> None:
        """POST /auth/login per §3-B + §3-F.

        Anonymous endpoint (CSRF-cookie-exempt — the cookie
        does not exist pre-login). Origin/Referer match
        enforced in deployed posture. Validation order:

          400 — body NOT valid JSON.
          413 — body > 4 KiB.
          422 — non-object body OR missing/wrong-shape username
                / password fields.
          403 — Origin/Referer mismatch (deployed posture).
          429 — per-IP OR per-credentials burst tripped.
          401 — credentials don't verify. Generic body
                ``{"error":"could not sign in"}``; no
                "username unknown" branch (timing parity via
                dummy_password_verify).
          200 — success. Body ``{"ok": true}`` + Set-Cookie
                session + Set-Cookie csrf.
          503 — auth not configured (defensive; cmd_ui only
                reaches this branch when configure_auth is
                inconsistent).
        """
        if AUTH_NO_AUTH or _AUTH_CREDS_CACHE is None:
            self._send(
                503,
                b'{"error":"auth not configured"}',
                "application/json",
            )
            return

        if not origin_matches(
            request_origin=self.headers.get("Origin"),
            request_referer=self.headers.get("Referer"),
            expected_origins=AUTH_EXPECTED_ORIGINS,
            deployed=AUTH_DEPLOYED,
        ):
            self._send(
                403,
                b'{"error":"forbidden"}',
                "application/json",
            )
            return

        result = self._read_login_body()
        if result is _LOGIN_BODY_TOO_LARGE:
            self._send(413, b"payload too large", "text/plain")
            return
        if result is _LOGIN_MALFORMED_JSON:
            self._send(
                400,
                b'{"error":"invalid request"}',
                "application/json",
            )
            return
        if result is _LOGIN_BODY_NOT_OBJECT:
            self._send(
                422,
                b'{"error":"request body must be an object"}',
                "application/json",
            )
            return
        if result is _LOGIN_INVALID_FIELDS:
            self._send(
                422,
                b'{"error":"invalid credentials shape"}',
                "application/json",
            )
            return

        assert isinstance(result, tuple)
        body, is_form = result
        username = body["username"]
        password = body["password"]

        client_ip = self._ip_for_rate_limit()
        rl = _AUTH_RATE_LIMIT
        if rl is not None and not rl.check(
            client_ip=client_ip, username_attempted=username
        ):
            self._send(
                429,
                b'{"error":"too many attempts"}',
                "application/json",
            )
            return

        creds = _AUTH_CREDS_CACHE
        auth_ok = False
        if username != creds.username:
            # Timing parity: pay a scrypt cost on the no-username
            # branch so wrong-username and wrong-password requests
            # take comparable time (§3-G + pin §11.6.7).
            dummy_password_verify()
        elif verify_password(creds.password_hash, password):
            auth_ok = True

        if not auth_ok:
            if rl is not None:
                rl.record_failure(
                    client_ip=client_ip, username_attempted=username
                )
            _auth_log.warning("login failed (ip=%s)", client_ip)
            # Brief §3-E lines 644-648 + Codex P1 round 1
            # binding: form mode re-renders login.html with
            # the error slot visible; JSON mode returns the
            # generic 401 body the JS fetch path consumes.
            if is_form:
                self._send_login_rerender()
            else:
                self._send(
                    401,
                    b'{"error":"could not sign in"}',
                    "application/json",
                )
            return

        # Success path.
        if rl is not None:
            rl.record_success(client_ip=client_ip, username=username)
        _auth_log.info(
            "login ok (user=%s, ip=%s)", creds.username, client_ip
        )

        session_token = issue_session_token(creds=creds)
        csrf_token = issue_csrf_token(
            creds=creds,
            username=creds.username,
            gen=creds.credentials_generation,
        )
        cookies = self._build_session_cookies(session_token, csrf_token)
        if is_form:
            # Brief §3-E: form success → 302 + cookies +
            # Location: /. The browser follows; the GET to /
            # then sees a valid session and serves the PWA
            # shell (index.html).
            self._send(
                302,
                b"",
                "text/plain",
                extra_headers=(("Location", "/"),) + cookies,
            )
        else:
            self._send(
                200,
                b'{"ok":true}',
                "application/json",
                extra_headers=cookies,
            )

    def _handle_logout_get(self) -> None:
        """GET /auth/logout — anonymous + idempotent (§3-D).

        Same-origin Origin/Referer check enforced in deployed
        posture (Codex round 2 P2 binding): cross-site forced-
        logout via image tags / prefetch / third-party
        redirects must not log Victor out. On 403 the cookies
        are NOT cleared. On success the session + csrf cookies
        are cleared via Max-Age=0 and the response redirects
        to /."""
        if AUTH_NO_AUTH:
            # No-auth posture: nothing to clear; redirect home.
            self._send(
                302,
                b"",
                "text/plain",
                extra_headers=(("Location", "/"),),
            )
            return

        if not origin_matches(
            request_origin=self.headers.get("Origin"),
            request_referer=self.headers.get("Referer"),
            expected_origins=AUTH_EXPECTED_ORIGINS,
            deployed=AUTH_DEPLOYED,
        ):
            self._send(
                403,
                b'{"error":"forbidden"}',
                "application/json",
            )
            return

        cookies = self._build_clear_cookies()
        self._send(
            302,
            b"",
            "text/plain",
            extra_headers=(("Location", "/"),) + cookies,
        )

    def _handle_logout_post(self) -> None:
        """POST /auth/logout — auth+CSRF required (§3-D).

        Reached only when ``_authorize_request`` already
        accepted the session + CSRF token. Clears cookies and
        returns 204 (the JS-driven affordance from the PWA
        shell consumes the empty body and reloads ``/``)."""
        cookies = self._build_clear_cookies()
        self._send(
            204,
            b"",
            "application/octet-stream",
            extra_headers=cookies,
        )

    def _read_login_body(
        self,
    ) -> "tuple[dict[str, str], bool] | object":
        """Parse + validate the login body.

        Codex P1 round 1 audit binding 2026-05-08 + brief §3-E
        lines 644-648: the form MUST work with JS disabled.
        Two transport shapes are accepted, picked by request
        Content-Type:

          * ``application/x-www-form-urlencoded`` — form
            submission; success returns 302 + Set-Cookie +
            Location:/ ; auth failure returns 200 + login.html
            re-rendered with the error slot visible.
          * ``application/json`` (default fallback) — fetch()
            transport from the JS layer; success returns 200
            ``{"ok": true}`` + Set-Cookie ; auth failure
            returns 401 + generic JSON.

        Returns ``(parsed_dict, is_form_submission)`` on
        success or one of the LOGIN sentinels.
        """
        content_type = self.headers.get("Content-Type", "").lower()
        is_form = content_type.startswith("application/x-www-form-urlencoded")

        try:
            declared = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            declared = 0
        if declared > _LOGIN_BODY_MAX_BYTES:
            return _LOGIN_BODY_TOO_LARGE
        if declared == 0:
            return _LOGIN_MALFORMED_JSON
        body = self.rfile.read(declared)
        if not body:
            return _LOGIN_MALFORMED_JSON

        if is_form:
            try:
                parsed = parse_qs(
                    body.decode("utf-8"), keep_blank_values=True
                )
            except (UnicodeDecodeError, ValueError):
                return _LOGIN_MALFORMED_JSON
            u_list = parsed.get("username") or []
            p_list = parsed.get("password") or []
            # Codex P2 round 2 audit binding 2026-05-08:
            # login parsing at the remote boundary must be
            # unambiguous. Repeated ``username`` or
            # ``password`` parameters get the generic 422
            # rather than silently authenticating against
            # the first value.
            if len(u_list) != 1 or len(p_list) != 1:
                return _LOGIN_INVALID_FIELDS
            username = u_list[0]
            password = p_list[0]
            if not username or not password:
                return _LOGIN_INVALID_FIELDS
            return ({"username": username, "password": password}, True)

        # JSON path (default).
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _LOGIN_MALFORMED_JSON
        if not isinstance(payload, dict):
            return _LOGIN_BODY_NOT_OBJECT
        username = payload.get("username")
        password = payload.get("password")
        if not isinstance(username, str) or not username:
            return _LOGIN_INVALID_FIELDS
        if not isinstance(password, str) or not password:
            return _LOGIN_INVALID_FIELDS
        return ({"username": username, "password": password}, False)

    def _send_login_rerender(self) -> None:
        """Form-mode auth-failure path per brief §3-E:
        200 + login.html re-render with the error slot
        populated. Strips the standalone ``hidden`` boolean
        attribute from the ``id="login-error"`` element via
        regex so the chunk-5 multi-line attribute layout
        (and any future re-formatting) keeps working without
        a templating engine."""
        html = (STATIC_DIR / "login.html").read_bytes()
        html = re.sub(
            rb'(id="login-error"[^>]*?)\s+hidden(\s|>)',
            rb"\1\2",
            html,
            count=1,
        )
        self._send(200, html, "text/html; charset=utf-8")

    def _build_session_cookies(
        self, session_token: str, csrf_token: str
    ) -> tuple[tuple[str, str], ...]:
        """Compose Set-Cookie headers for a fresh login.

        Brief §3-C session cookie attributes (lines 402-407
        + 1520-1522 verbatim binding; Codex P1 round 1 audit
        2026-05-08 caught the prior SameSite=Lax drift):
          HttpOnly + SameSite=Strict + Path=/
          Max-Age = DEFAULT_SESSION_TTL_SECONDS (14d)
          Secure when AUTH_DEPLOYED (HTTPS posture)

        Brief §3-F CSRF cookie attributes:
          NOT HttpOnly (the JS reads it for double-submit)
          SameSite=Strict + Path=/
          Max-Age = same as session
          Secure when AUTH_DEPLOYED
        """
        from karasu.ui._auth import DEFAULT_SESSION_TTL_SECONDS

        secure = "; Secure" if AUTH_DEPLOYED else ""
        max_age = DEFAULT_SESSION_TTL_SECONDS
        session = (
            f"{SESSION_COOKIE_NAME}={session_token}; "
            f"Max-Age={max_age}; Path=/; HttpOnly; "
            f"SameSite=Strict{secure}"
        )
        csrf = (
            f"{CSRF_COOKIE_NAME}={csrf_token}; "
            f"Max-Age={max_age}; Path=/; SameSite=Strict{secure}"
        )
        return (("Set-Cookie", session), ("Set-Cookie", csrf))

    def _build_clear_cookies(self) -> tuple[tuple[str, str], ...]:
        """Set-Cookie headers that delete the session + csrf
        cookies via Max-Age=0 (browser drops them immediately).
        Attributes mirror the issue path so the browser matches
        the cookie identity for deletion."""
        secure = "; Secure" if AUTH_DEPLOYED else ""
        session = (
            f"{SESSION_COOKIE_NAME}=; Max-Age=0; Path=/; "
            f"HttpOnly; SameSite=Strict{secure}"
        )
        csrf = (
            f"{CSRF_COOKIE_NAME}=; Max-Age=0; Path=/; "
            f"SameSite=Strict{secure}"
        )
        return (("Set-Cookie", session), ("Set-Cookie", csrf))

    # ---- end UI-13 handlers --------------------------------------

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

    def _read_trust_adjust_body(self) -> "dict[str, Any] | object":
        """Read + validate the UI-11b trust adjust JSON body.

        The documented body is ``{"trust_level": 0|1|2}`` with an
        optional string ``reason``. Reasons are trimmed and omitted
        when empty, matching the UI-10 revoke convention.
        """
        try:
            declared = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            declared = 0
        if declared > _TRUST_BODY_MAX_BYTES:
            return _BODY_TOO_LARGE
        if declared == 0:
            return _BODY_NOT_OBJECT
        body = self.rfile.read(declared)
        if not body:
            return _BODY_NOT_OBJECT
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _MALFORMED_BODY
        if not isinstance(payload, dict):
            return _BODY_NOT_OBJECT

        raw_trust = payload.get("trust_level")
        if isinstance(raw_trust, bool) or not isinstance(raw_trust, int):
            return _INVALID_TRUST_LEVEL
        if raw_trust not in _SUPPORTED_TRUST_LEVELS:
            return _INVALID_TRUST_LEVEL

        out: dict[str, Any] = {"trust_after": raw_trust}
        raw_reason = payload.get("reason")
        if isinstance(raw_reason, str):
            trimmed = raw_reason.strip()
            if trimmed:
                out["reason"] = trimmed
        return out

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
    push_store_path: Path | None = None,
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
    ``karasu.yaml`` path the CLI was given. UI-12a adds
    ``push_store_path`` for ``GET /api/push``. Omitting any of
    them leaves the pre-existing default.
    """
    global EVENT_LOG, SCARS_PATH, CONFIG_PATH, PUSH_STORE_PATH
    EVENT_LOG = event_log
    if scars_path is not None:
        SCARS_PATH = scars_path
    if config_path is not None:
        CONFIG_PATH = config_path
    if push_store_path is not None:
        PUSH_STORE_PATH = push_store_path


def configure_auth(
    *,
    credentials_path: Path | None = None,
    no_auth: bool = False,
    deployed: bool = False,
    trusted_proxies: frozenset[str] | None = None,
    expected_origins: tuple[str, ...] = (),
) -> None:
    """Wire the UI-13 auth surface.

    Called by ``cmd_ui`` at startup AFTER credentials have been
    bootstrapped (or the ``--no-auth`` dev flag was passed); also
    called by tests to set up a controlled posture.

    Default ``configure()`` does NOT touch the auth state, so
    pre-UI-13 tests and the legacy ``karasu ui`` invocation
    keep working with ``AUTH_NO_AUTH=True``. UI-13 makes
    ``cmd_ui`` flip ``no_auth=False`` + supply
    ``credentials_path`` so the deployed posture loads creds
    eagerly.

    Brief §3-B fail-closed contract: when ``no_auth=False`` and
    ``credentials_path`` is supplied, this function raises
    ``AuthCredentialsError`` if the file is absent / malformed
    / wrong-mode / missing-fields. The caller (cmd_ui) catches
    and exits 2; tests want the exception surfaced too so a
    fixture mistake produces a loud failure rather than silent
    no-auth fallback.
    """
    global AUTH_NO_AUTH, AUTH_DEPLOYED, AUTH_TRUSTED_PROXIES
    global AUTH_EXPECTED_ORIGINS, AUTH_CREDENTIALS_PATH
    global _AUTH_CREDS_CACHE, _AUTH_RATE_LIMIT
    AUTH_NO_AUTH = no_auth
    AUTH_DEPLOYED = deployed
    if trusted_proxies is not None:
        AUTH_TRUSTED_PROXIES = trusted_proxies
    AUTH_EXPECTED_ORIGINS = expected_origins
    AUTH_CREDENTIALS_PATH = credentials_path
    _AUTH_RATE_LIMIT = LoginRateLimit() if not no_auth else None
    if no_auth:
        _AUTH_CREDS_CACHE = None
        return
    # Codex P1 round 2 audit binding 2026-05-08: auth-
    # enabled startup with no credentials_path is a fail-
    # closed violation per §3-B — silently clearing the
    # cache would leave the listener up but every request
    # would 401 / redirect, hiding the misconfiguration
    # behind an opaque user-facing error. Raise so cmd_ui
    # exits 2 with the same generic stderr line as the
    # missing-file branch.
    if credentials_path is None:
        raise AuthCredentialsError("auth enabled but credentials_path missing")
    _AUTH_CREDS_CACHE = load_credentials(credentials_path)


def _reset_auth_state() -> None:
    """Test helper — restore the pre-UI-13 default. Called by
    fixtures in their teardown so a configure_auth() in one
    test does not leak into the next. NOT part of the public
    surface."""
    global AUTH_NO_AUTH, AUTH_DEPLOYED, AUTH_TRUSTED_PROXIES
    global AUTH_EXPECTED_ORIGINS, AUTH_CREDENTIALS_PATH
    global _AUTH_CREDS_CACHE, _AUTH_RATE_LIMIT
    AUTH_NO_AUTH = True
    AUTH_DEPLOYED = False
    AUTH_TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})
    AUTH_EXPECTED_ORIGINS = ()
    AUTH_CREDENTIALS_PATH = None
    _AUTH_CREDS_CACHE = None
    _AUTH_RATE_LIMIT = None


def run_ui_server(
    host: str = "127.0.0.1",
    port: int = 8787,
    event_log: Path | None = None,
    scars_path: Path | None = None,
    config_path: Path | None = None,
    push_store_path: Path | None = None,
) -> None:
    """Start the UI HTTP server. Blocks until interrupted.

    ``event_log`` overrides the default ``.karasu/events.jsonl``
    bus path; ``scars_path`` overrides the default
    ``.karasu/scars/`` rules directory (UI-10); ``config_path``
    points the UI-11a agent/trust projection at the same
    ``karasu.yaml`` the CLI loaded; ``push_store_path``
    overrides the default ``karasu-push.json`` location for the
    UI-12a read-only push surface. Callers that omit kwargs keep
    the pre-existing defaults.
    """
    if (
        event_log is not None
        or scars_path is not None
        or config_path is not None
        or push_store_path is not None
    ):
        configure(
            event_log=event_log if event_log is not None else EVENT_LOG,
            scars_path=scars_path,
            config_path=config_path,
            push_store_path=push_store_path,
        )
    server = ThreadingHTTPServer((host, port), UIHandler)
    # ASCII arrow + UTF-8 stdout reconfigure: Windows console
    # default cp1252 cannot encode the U+2192 right-arrow, so a
    # plain operator running ``karasu ui`` on a stock terminal
    # crashed at startup. Same scar shape as
    # feedback_subprocess_text_utf8 from the Karasu UI-9.1 work.
    print(f"karasu ui -> http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
