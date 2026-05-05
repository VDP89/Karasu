"""HTTP-level shape locks for the Karasu UI projection (UI-9).

UI-1 through UI-8 shipped the projection surface incrementally:

  UI-3   /api/meta              {version, bus_path}
  UI-4   /api/events            {events: [<projected event>...]}
  UI-3+  /api/health            {status, events, crow}
  UI-6   /api/health.flight     {source, target} | null  (additive)
  UI-8   /assets/sw.js          + Service-Worker-Allowed: / header
  UI-8   /offline.html          additive route
  UI-8   /assets/manifest.json  {name, theme_color, background_color, ...}

These tests pin the wire shapes against the bus schema so a
future projection change must update the lock in the same PR.
This is the "pin C" lesson from the UI-5 / UI-6 audits taken to
its endpoint: every visible state derived from the server gets
a structural test before the visual code lands. UI-9 closes
the test surface for the read-only watchtower MVP.

Codex pin #1 from the UI-8 audit (PR #80): UI-9 should validate
the PWA contracts with tests where feasible — /api/* network-
only (covered indirectly by the projection shape locks), the
/assets/sw.js Service-Worker-Allowed header, /offline.html
route, manifest colors. All four are exercised below.
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from karasu.ui import server as ui_server


# ---------------------------------------------------------------------------
# Server lifecycle helper — mirror of the fixture in test_ui_server.py.
# Kept local so this module is self-contained and a future split into a
# parallel test process does not need to share fixtures across files.
# ---------------------------------------------------------------------------


@pytest.fixture
def ui_http(tmp_path: Path) -> Iterator[tuple[str, int]]:
    original_event_log = ui_server.EVENT_LOG
    ui_server.configure(tmp_path / "events.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.UIHandler)
    thread = threading.Thread(
        target=server.serve_forever, name="karasu-ui-http-test", daemon=True
    )
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield host, port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
        ui_server.configure(original_event_log)


def _get(
    host: str, port: int, path: str
) -> tuple[int, bytes, dict[str, str]]:
    """Fetch ``path`` from the test server. Returns
    ``(status, body, headers)``. Headers are flattened to a
    case-insensitive lower-case dict so the tests can assert on
    Service-Worker-Allowed without worrying about casing."""
    url = f"http://{host}:{port}{path}"
    try:
        with urlopen(Request(url), timeout=5.0) as response:
            headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, response.read(), headers
    except HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, exc.read(), headers


def _seed(events: list[dict]) -> None:
    """Write events to the configured bus. ``ui_http`` already
    points EVENT_LOG at a per-test tmp_path."""
    ui_server.EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ui_server.EVENT_LOG.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


# ---------------------------------------------------------------------------
# /api/events — shape lock
# ---------------------------------------------------------------------------
#
# The projection in src/karasu/ui/server.py::_project_event picks
# specific fields off the raw bus event. UI-1..UI-8 readers depend
# on this exact shape. A new field is fine (additive); a removed
# or renamed field breaks the timeline / drawer / map.
#
# Every key listed below MUST appear on every response (with
# ``None`` when the underlying bus event did not carry the value).
# The shape is the contract.

EVENTS_PROJECTION_KEYS = frozenset({
    "id",
    "timestamp",
    "type",
    "source",
    # data — common
    "path",
    "classification",
    "priority",
    # data — controller resubmits (chain cap, issue #47)
    "controller_resubmit",
    "resubmit_origin",
    "controller_chain_depth",
    # data — github webhook metadata (chunks 4a + 4c)
    "github_event",
    "github_action",
    "github_pr",
    "github_repo",
    "github_author",
    # data — agent_response correlation (Phase 1B / F3)
    "correlates",
    # dispatch
    "agent",
    "status",
    "trust_level",
    # response
    "requires_human",
})


def test_api_events_projection_shape_lock(
    ui_http: tuple[str, int]
) -> None:
    """A fully-populated event must round-trip through the
    projection with EXACTLY the documented set of keys. Adding a
    field requires updating EVENTS_PROJECTION_KEYS in the same PR
    that ships the field; removing a field requires an explicit
    deprecation."""
    host, port = ui_http
    full_event = {
        "id": "evt-001",
        "timestamp": "2026-05-04T12:00:00Z",
        "type": "file_change",
        "source": "github_webhook",
        "data": {
            "path": "src/foo.py",
            "classification": "code_change",
            "priority": "high",
            "controller_resubmit": True,
            "resubmit_origin": "evt-000",
            "controller_chain_depth": 1,
            "github_event": "pull_request_review_comment",
            "github_action": "created",
            "github_pr": 42,
            "github_repo": "VDP89/Karasu-",
            "github_author": "reviewer1",
            "correlates": "evt-000",
        },
        "dispatch": {
            "agent": "claude_code",
            "status": "completed",
            "trust_level": 1,
        },
        "response": {
            "content": "done",
            "requires_human": False,
        },
    }
    _seed([full_event])

    status, body, _ = _get(host, port, "/api/events")
    assert status == 200
    payload = json.loads(body)
    assert "events" in payload, "top-level shape: {events: [...]}"
    assert isinstance(payload["events"], list)
    assert len(payload["events"]) == 1
    projected = payload["events"][0]

    # Every documented key must appear, no extras.
    assert set(projected.keys()) == EVENTS_PROJECTION_KEYS, (
        "projection drift — diff:\n"
        f"  missing: {EVENTS_PROJECTION_KEYS - set(projected)}\n"
        f"  extra:   {set(projected) - EVENTS_PROJECTION_KEYS}"
    )

    # Spot-check field passthrough so a renaming bug fails here
    # rather than visually downstream.
    assert projected["id"] == "evt-001"
    assert projected["path"] == "src/foo.py"
    assert projected["controller_resubmit"] is True
    assert projected["github_pr"] == 42
    assert projected["agent"] == "claude_code"
    assert projected["status"] == "completed"
    assert projected["requires_human"] is False


def test_api_events_top_level_shape_on_empty_bus(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    assert not ui_server.EVENT_LOG.exists()
    status, body, _ = _get(host, port, "/api/events")
    assert status == 200
    payload = json.loads(body)
    assert payload == {"events": []}, (
        "empty-bus shape lock: must be exactly {events: []}, not "
        "{events: null} or any other variant"
    )


# ---------------------------------------------------------------------------
# /api/health — shape lock (UI-3 + UI-6 flight field)
# ---------------------------------------------------------------------------

HEALTH_KEYS = frozenset({"status", "events", "crow", "flight"})


def test_api_health_shape_lock(ui_http: tuple[str, int]) -> None:
    """Top-level /api/health response keys are CONTRACT. UI-3
    shipped status/events/crow; UI-6 added flight (additive). No
    removal allowed without a coordinated UI change."""
    host, port = ui_http
    status, body, _ = _get(host, port, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert set(payload.keys()) == HEALTH_KEYS, (
        f"health shape drift: missing={HEALTH_KEYS - set(payload)}, "
        f"extra={set(payload) - HEALTH_KEYS}"
    )
    # Empty bus → flight is null (UI-6 contract).
    assert payload["flight"] is None
    assert payload["events"] == 0
    assert payload["crow"] == "idle"


def test_api_health_flight_shape_when_populated(
    ui_http: tuple[str, int]
) -> None:
    """When /api/health.flight is non-null, it MUST be exactly
    {source, target} — no extra keys (Codex pin "no invented
    recovery flight" from UI-6 audit lives in the projection;
    this pin lives on the wire)."""
    host, port = ui_http
    _seed([
        {
            "id": "fc-001",
            "timestamp": "2026-05-04T12:00:00Z",
            "type": "file_change",
            "source": "watcher",
            "data": {"path": "src/foo.py"},
            "dispatch": {},
            "response": {},
        }
    ])
    status, body, _ = _get(host, port, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["flight"] is not None
    assert set(payload["flight"].keys()) == {"source", "target"}
    assert payload["flight"]["source"] == "user"
    assert payload["flight"]["target"] == "karasu"


# ---------------------------------------------------------------------------
# /api/meta — shape lock (UI-3)
# ---------------------------------------------------------------------------

META_KEYS = frozenset({"version", "bus_path"})


def test_api_meta_shape_lock(ui_http: tuple[str, int]) -> None:
    host, port = ui_http
    status, body, _ = _get(host, port, "/api/meta")
    assert status == 200
    payload = json.loads(body)
    assert set(payload.keys()) == META_KEYS, (
        f"meta shape drift: missing={META_KEYS - set(payload)}, "
        f"extra={set(payload) - META_KEYS}"
    )
    # Both fields are strings (or ``"unknown"`` for version).
    assert isinstance(payload["version"], str)
    assert isinstance(payload["bus_path"], str)


# ---------------------------------------------------------------------------
# /assets/sw.js — Service-Worker-Allowed: / header (UI-8 P1#1 pin)
# ---------------------------------------------------------------------------


def test_sw_js_carries_service_worker_allowed_header(
    ui_http: tuple[str, int]
) -> None:
    """The SW registered from /assets/sw.js scopes to root only
    if the response carries ``Service-Worker-Allowed: /``. Without
    the header the browser rejects the registration with
    SecurityError because the SW's default scope is its own
    directory (/assets/). Codex P1 binding from the UI-8 design
    review."""
    host, port = ui_http
    status, body, headers = _get(host, port, "/assets/sw.js")
    assert status == 200
    assert headers.get("service-worker-allowed") == "/", (
        "Service-Worker-Allowed header missing or wrong value — "
        "SW registration will fail at the root scope"
    )
    # Sanity: the body is the actual SW source, not a stub.
    assert b"CACHE_NAME" in body, (
        "sw.js body unexpected — CACHE_NAME constant should be "
        "present per the UI-8 docstring contract"
    )


def test_sw_js_other_assets_do_not_carry_the_header(
    ui_http: tuple[str, int]
) -> None:
    """Only sw.js gets the SW-Allowed header. Other static assets
    must NOT carry it — adding it to every response would be a
    functional no-op but the regression check is structural."""
    host, port = ui_http
    # Pick a known static asset that ships in the repo.
    status, _, headers = _get(host, port, "/assets/manifest.json")
    assert status == 200
    assert "service-worker-allowed" not in headers


# ---------------------------------------------------------------------------
# /offline.html — additive route (UI-8)
# ---------------------------------------------------------------------------


def test_offline_html_route_serves_offline_shell(
    ui_http: tuple[str, int]
) -> None:
    """The /offline.html route is reachable directly so the audit
    can open the page during the screenshot pass without faking a
    network failure. The SW also references it as its navigation
    fallback target."""
    host, port = ui_http
    status, body, headers = _get(host, port, "/offline.html")
    assert status == 200
    assert headers.get("content-type", "").startswith("text/html")
    # The editorial copy is the contract for the offline page.
    assert b"The bus is unreachable" in body, (
        "offline.html body drift — the editorial sentence is the "
        "copy contract documented in screenshots/UI-8-pwa/README.md"
    )
    # The .crow.offline class must be present so the perched
    # crow renders in the out-of-signal posture.
    assert b"crow offline" in body or b'class="crow offline' in body, (
        "offline.html missing the .offline state class on the crow"
    )


# ---------------------------------------------------------------------------
# /assets/manifest.json — colour parity with tokens.css (UI-8 P2#3 pin)
# ---------------------------------------------------------------------------


def test_manifest_colours_match_tokens_css_exactly(
    ui_http: tuple[str, int]
) -> None:
    """Codex P2 binding from the UI-8 design review: manifest hex
    values MUST match tokens.css exactly. An off-by-one channel is
    a regression — the audit will diff the values, this test
    fails first."""
    host, port = ui_http
    status, body, _ = _get(host, port, "/assets/manifest.json")
    assert status == 200
    manifest = json.loads(body)

    tokens_path = (
        ui_server.STATIC_DIR / "css" / "tokens.css"
    )
    tokens = tokens_path.read_text(encoding="utf-8")

    # The manifest's background_color is the canvas (--bg-0).
    assert manifest["background_color"] == "#0a0a0b"
    assert "--bg-0: #0a0a0b" in tokens, (
        "tokens.css drift: --bg-0 no longer #0a0a0b — the "
        "manifest needs to be re-synced in the same PR"
    )

    # The manifest's theme_color is the panel surface (--bg-1).
    assert manifest["theme_color"] == "#131316"
    assert "--bg-1: #131316" in tokens, (
        "tokens.css drift: --bg-1 no longer #131316 — the "
        "manifest needs to be re-synced in the same PR"
    )


def test_manifest_top_level_shape_lock(
    ui_http: tuple[str, int]
) -> None:
    """Manifest top-level keys are the documented PWA contract.
    Adding optional keys (e.g. ``shortcuts``, ``screenshots``) is
    fine; removing ``name`` / ``start_url`` / ``icons`` /
    ``display`` would break the install flow."""
    host, port = ui_http
    status, body, _ = _get(host, port, "/assets/manifest.json")
    assert status == 200
    manifest = json.loads(body)
    required = {
        "name",
        "short_name",
        "start_url",
        "scope",
        "display",
        "background_color",
        "theme_color",
        "icons",
    }
    assert required.issubset(manifest.keys()), (
        f"manifest missing required keys: {required - manifest.keys()}"
    )
    # Standalone display is the editorial choice — anything else
    # would surface browser chrome on installed PWAs.
    assert manifest["display"] == "standalone"
    # Root scope is what makes the SW + the navigation fallback
    # cover the entire site.
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"
    # Both icon sizes (192 + 512) are required for the install
    # prompt to render correctly across platforms.
    icon_sizes = {icon["sizes"] for icon in manifest["icons"]}
    assert {"192x192", "512x512"}.issubset(icon_sizes)
