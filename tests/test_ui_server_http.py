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
    original_scars_path = ui_server.SCARS_PATH
    original_config_path = ui_server.CONFIG_PATH
    ui_server.configure(
        event_log=tmp_path / "events.jsonl",
        scars_path=tmp_path / "scars",
        config_path=tmp_path / "karasu.yaml",
    )
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
        ui_server.configure(
            event_log=original_event_log,
            scars_path=original_scars_path,
            config_path=original_config_path,
        )


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


def _post(
    host: str,
    port: int,
    path: str,
    body: bytes = b"",
    content_type: str = "application/json",
) -> tuple[int, bytes, dict[str, str]]:
    """POST ``body`` to ``path`` on the test server.

    Returns ``(status, body, headers)`` with headers
    case-insensitive lower-cased like ``_get``. Empty body is
    legal — the revoke endpoint accepts no body for the "no
    reason" path."""
    url = f"http://{host}:{port}{path}"
    headers = {"Content-Type": content_type}
    if body:
        headers["Content-Length"] = str(len(body))
    request = Request(url, data=body, method="POST", headers=headers)
    try:
        with urlopen(request, timeout=5.0) as response:
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            return response.status, response.read(), response_headers
    except HTTPError as exc:
        response_headers = {k.lower(): v for k, v in exc.headers.items()}
        return exc.code, exc.read(), response_headers


def _seed_scar(correction: dict | None = None) -> str:
    """Record one Scar via ScarEngine; return its id."""
    from karasu.scars import Scar, ScarEngine

    engine = ScarEngine(ui_server.SCARS_PATH)
    scar = engine.record(
        Scar(
            trigger={"classification": "high", "path": "*.py"},
            correction=correction or {"priority": "high"},
        )
    )
    return scar.id


def _seed(events: list[dict]) -> None:
    """Write events to the configured bus. ``ui_http`` already
    points EVENT_LOG at a per-test tmp_path."""
    ui_server.EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with ui_server.EVENT_LOG.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(event) + "\n")


def _write_config(config: dict) -> None:
    """Write the per-test ``karasu.yaml``. JSON is valid YAML,
    and keeps the fixture dependency-free."""
    ui_server.CONFIG_PATH.write_text(json.dumps(config), encoding="utf-8")


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
    # data — human_decision subtype (UI-10+ write-path events)
    "action",
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
            "action": "scar_revoke",
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
    assert projected["action"] == "scar_revoke"
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
# /api/agents — shape lock (UI-11a)
# ---------------------------------------------------------------------------

AGENT_KEYS = frozenset({"name", "trust_level", "handles"})


def test_api_agents_empty_list_when_no_config(
    ui_http: tuple[str, int]
) -> None:
    """No karasu.yaml / no configured adapters → empty JSON list.
    UI-11a must work with no ``karasu watch`` process running."""
    host, port = ui_http
    assert not ui_server.CONFIG_PATH.exists()
    status, body, headers = _get(host, port, "/api/agents")
    assert status == 200
    assert headers.get("content-type") == "application/json"
    assert json.loads(body) == []


def test_api_agents_shape_lock(ui_http: tuple[str, int]) -> None:
    """Configured adapters project to the UI-11a read-only shape.
    The endpoint reads karasu.yaml directly; it does not inspect
    live adapter instances."""
    host, port = ui_http
    _write_config({
        "agents": {
            "claude_code": {
                "trust_level": 2,
                "handles": ["code_change", "implementation"],
            },
            "codex": {
                "repo": "VDP89/Karasu-",
                "trust_level": 0,
                "handles": ["code_review"],
            },
        }
    })

    status, body, headers = _get(host, port, "/api/agents")
    assert status == 200
    assert headers.get("content-type") == "application/json"
    payload = json.loads(body)
    assert isinstance(payload, list)
    assert len(payload) == 2
    for record in payload:
        assert AGENT_KEYS.issubset(record.keys())
        assert isinstance(record["name"], str)
        assert isinstance(record["trust_level"], int)
        assert isinstance(record["handles"], list)

    assert payload[0] == {
        "name": "claude_code",
        "trust_level": 2,
        "handles": ["code_change", "implementation"],
    }
    assert payload[1] == {
        "name": "codex",
        "trust_level": 0,
        "handles": ["code_review"],
    }


def test_api_agents_marks_unsupported_trust_level(
    ui_http: tuple[str, int]
) -> None:
    """Trust values outside {0,1,2} are visible but read-only.
    UI-11a surfaces the raw int plus an unsupported flag instead
    of coercing it into the documented range."""
    host, port = ui_http
    _write_config({
        "agents": {
            "claude_code": {
                "trust_level": 3,
            },
        }
    })

    status, body, _ = _get(host, port, "/api/agents")
    assert status == 200
    payload = json.loads(body)
    assert payload == [
        {
            "name": "claude_code",
            "trust_level": 3,
            "handles": ["code_change", "bug_fix", "implementation"],
            "unsupported": True,
        }
    ]


def test_api_agents_non_integer_trust_level_is_unsupported(
    ui_http: tuple[str, int]
) -> None:
    """Malformed trust_level config should not turn the UI endpoint
    into a 500. Surface the raw value as unsupported/read-only so
    the operator can see and fix the config."""
    host, port = ui_http
    _write_config({
        "agents": {
            "claude_code": {
                "trust_level": "high",
                "handles": ["implementation"],
            },
        }
    })

    status, body, _ = _get(host, port, "/api/agents")
    assert status == 200
    payload = json.loads(body)
    assert payload == [
        {
            "name": "claude_code",
            "trust_level": "high",
            "handles": ["implementation"],
            "unsupported": True,
        }
    ]


def test_post_agent_trust_returns_204_updates_config_and_emits_event(
    ui_http: tuple[str, int]
) -> None:
    """UI-11b success shape: 204 empty body, config trust updated
    for the next watcher run, and a trust_adjust human_decision
    lands on the bus."""
    host, port = ui_http
    _write_config({
        "agents": {
            "claude_code": {
                "trust_level": 1,
                "handles": ["implementation"],
            },
        }
    })
    body = json.dumps({
        "trust_level": 2,
        "reason": "  dogfood can mutate this branch  ",
    }).encode("utf-8")

    status, response_body, _ = _post(
        host, port, "/api/agents/claude_code/trust", body=body
    )

    assert status == 204
    assert response_body == b""

    status, agents_body, _ = _get(host, port, "/api/agents")
    assert status == 200
    assert json.loads(agents_body)[0]["trust_level"] == 2

    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    event = json.loads(raw[-1])
    assert event["type"] == "human_decision"
    assert event["source"] == "ui"
    assert event["data"] == {
        "action": "trust_adjust",
        "agent": "claude_code",
        "trust_before": 1,
        "trust_after": 2,
        "reason": "dogfood can mutate this branch",
    }


def test_post_agent_trust_whitespace_reason_omits_field(
    ui_http: tuple[str, int]
) -> None:
    """Empty / whitespace-only reason is omitted, matching the
    UI-10 revoke convention."""
    host, port = ui_http
    _write_config({"agents": {"claude_code": {"trust_level": 1}}})
    body = json.dumps({"trust_level": 0, "reason": "   "}).encode("utf-8")

    status, _, _ = _post(host, port, "/api/agents/claude_code/trust", body=body)

    assert status == 204
    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    event = json.loads(raw[-1])
    assert event["data"]["action"] == "trust_adjust"
    assert event["data"]["trust_before"] == 1
    assert event["data"]["trust_after"] == 0
    assert "reason" not in event["data"]


def test_post_agent_trust_unknown_agent_returns_404(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _write_config({"agents": {"claude_code": {"trust_level": 1}}})

    status, _, _ = _post(
        host,
        port,
        "/api/agents/no_such_agent/trust",
        body=json.dumps({"trust_level": 2}).encode("utf-8"),
    )

    assert status == 404
    assert not ui_server.EVENT_LOG.exists()


def test_post_agent_trust_unsupported_current_level_returns_422(
    ui_http: tuple[str, int]
) -> None:
    """A configured unsupported value is visible/read-only and
    cannot be mutated through the UI-11b POST path."""
    host, port = ui_http
    _write_config({"agents": {"claude_code": {"trust_level": 3}}})

    status, _, _ = _post(
        host,
        port,
        "/api/agents/claude_code/trust",
        body=json.dumps({"trust_level": 2}).encode("utf-8"),
    )

    assert status == 422
    assert not ui_server.EVENT_LOG.exists()
    _, agents_body, _ = _get(host, port, "/api/agents")
    assert json.loads(agents_body)[0]["trust_level"] == 3


def test_post_agent_trust_invalid_target_level_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _write_config({"agents": {"claude_code": {"trust_level": 1}}})

    status, _, _ = _post(
        host,
        port,
        "/api/agents/claude_code/trust",
        body=json.dumps({"trust_level": 4}).encode("utf-8"),
    )

    assert status == 422
    assert not ui_server.EVENT_LOG.exists()
    _, agents_body, _ = _get(host, port, "/api/agents")
    assert json.loads(agents_body)[0]["trust_level"] == 1


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


# ---------------------------------------------------------------------------
# UI-10 — /api/scars + POST /api/scars/{id}/revoke shape locks
# ---------------------------------------------------------------------------
#
# UI-10 brief §10.5: the /api/scars list ships only the fields
# ScarEngine exposes naturally. ``status`` / ``revoked_at`` /
# ``applied_count`` / ``last_applied_at`` are intentionally
# omitted — the UI synthesises the post-revoke annotation from
# request context + the human_decision event the bus emits.

SCARS_LIST_KEYS = frozenset({"id", "correction_text", "created_at"})


def test_api_scars_empty_list_when_no_scars(ui_http: tuple[str, int]) -> None:
    """No scars recorded → ``{"scars": []}``."""
    host, port = ui_http
    status, body, _ = _get(host, port, "/api/scars")
    assert status == 200
    assert json.loads(body) == {"scars": []}


def test_api_scars_projection_shape_lock(ui_http: tuple[str, int]) -> None:
    """Each scar projects to exactly the SCARS_LIST_KEYS set."""
    host, port = ui_http
    _seed_scar()
    status, body, _ = _get(host, port, "/api/scars")
    assert status == 200
    payload = json.loads(body)
    assert "scars" in payload
    assert len(payload["scars"]) == 1
    record = payload["scars"][0]
    assert set(record.keys()) == SCARS_LIST_KEYS
    assert isinstance(record["id"], str)
    assert isinstance(record["correction_text"], str)
    assert isinstance(record["created_at"], str)


def test_api_scars_excludes_revoked(ui_http: tuple[str, int]) -> None:
    """A revoked scar disappears from the list — the active /
    revoked split lives in ScarEngine, the UI surface mirrors
    it. Annotation in the drawer is the UI's responsibility."""
    from karasu.scars import ScarEngine

    host, port = ui_http
    scar_id = _seed_scar()
    second_id = _seed_scar({"priority": "low"})
    engine = ScarEngine(ui_server.SCARS_PATH)
    assert engine.revoke(scar_id) is True
    status, body, _ = _get(host, port, "/api/scars")
    assert status == 200
    ids = [s["id"] for s in json.loads(body)["scars"]]
    assert ids == [second_id]


def test_post_revoke_returns_204_on_success(ui_http: tuple[str, int]) -> None:
    """Brief §3-E + §11.6.3: POST returns 204 with no body on
    success. The annotation contract derives from re-fetching
    /api/scars and the emitted human_decision event."""
    host, port = ui_http
    scar_id = _seed_scar()
    status, body, _ = _post(
        host, port, f"/api/scars/{scar_id}/revoke"
    )
    assert status == 204
    assert body == b""


def test_post_revoke_emits_human_decision_event(
    ui_http: tuple[str, int]
) -> None:
    """Bus event after a successful revoke MUST be a
    ``human_decision`` with ``data.action="scar_revoke"`` and
    ``data.scar_id`` set; ``data.reason`` only present when the
    operator supplied one."""
    host, port = ui_http
    scar_id = _seed_scar()
    status, _, _ = _post(host, port, f"/api/scars/{scar_id}/revoke")
    assert status == 204
    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    # Newest event is the last line.
    event = json.loads(raw[-1])
    assert event["type"] == "human_decision"
    assert event["source"] == "ui"
    assert event["data"]["action"] == "scar_revoke"
    assert event["data"]["scar_id"] == scar_id
    # No reason supplied → field omitted (brief §10.2).
    assert "reason" not in event["data"]


def test_post_revoke_with_reason_carries_into_event(
    ui_http: tuple[str, int]
) -> None:
    """A trimmed non-empty ``reason`` lands on ``data.reason``."""
    host, port = ui_http
    scar_id = _seed_scar()
    body = json.dumps({"reason": "  not applicable anymore  "}).encode("utf-8")
    status, _, _ = _post(
        host, port, f"/api/scars/{scar_id}/revoke", body=body
    )
    assert status == 204
    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    event = json.loads(raw[-1])
    # Trim runs through the server, not just through the client.
    assert event["data"]["reason"] == "not applicable anymore"


def test_post_revoke_empty_string_reason_omits_field(
    ui_http: tuple[str, int]
) -> None:
    """Brief §10.2: empty / whitespace-only reason MUST be
    omitted from the event payload, not serialised as ``""``."""
    host, port = ui_http
    scar_id = _seed_scar()
    body = json.dumps({"reason": "   "}).encode("utf-8")
    status, _, _ = _post(
        host, port, f"/api/scars/{scar_id}/revoke", body=body
    )
    assert status == 204
    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    event = json.loads(raw[-1])
    assert "reason" not in event["data"]


def test_post_revoke_unknown_id_returns_404(ui_http: tuple[str, int]) -> None:
    host, port = ui_http
    status, _, _ = _post(host, port, "/api/scars/no-such-id/revoke")
    assert status == 404


def test_post_revoke_already_revoked_returns_404(
    ui_http: tuple[str, int]
) -> None:
    """Idempotent at the server boundary: a second revoke for
    the same id is a 404, no second event emitted. The UI
    treats both as 'gone'."""
    host, port = ui_http
    scar_id = _seed_scar()
    assert _post(host, port, f"/api/scars/{scar_id}/revoke")[0] == 204
    bus_lines_after_first = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    status, _, _ = _post(host, port, f"/api/scars/{scar_id}/revoke")
    assert status == 404
    bus_lines_after_second = ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
    assert bus_lines_after_first == bus_lines_after_second


def test_post_revoke_invalid_id_chars_returns_404(
    ui_http: tuple[str, int]
) -> None:
    """Brief §10.1: scar id is [A-Za-z0-9._:-]+ — characters
    outside that set fail the path regex and return 404 (i.e.
    "the scar id at this URL does not exist"). Tests pass URL-
    legal characters that are nonetheless not in the contract:
    ``+`` (URL-reserved but not in the contract) and ``%2F``
    (a percent-encoded slash that does NOT decode into a id
    segment). Spaces would be ideal coverage but urllib rejects
    them client-side before the request is sent."""
    host, port = ui_http
    # ``+`` is URL-legal but absent from the contract regex.
    status, _, _ = _post(host, port, "/api/scars/has+plus/revoke")
    assert status == 404
    # ``%2F`` reaches the server as the literal three characters
    # ``%``, ``2``, ``F`` — none of which are in the regex.
    status, _, _ = _post(host, port, "/api/scars/has%2Fslash/revoke")
    assert status == 404


def test_post_revoke_malformed_json_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    scar_id = _seed_scar()
    status, _, _ = _post(
        host, port, f"/api/scars/{scar_id}/revoke", body=b"not json"
    )
    assert status == 422


def test_post_revoke_non_object_json_returns_422(
    ui_http: tuple[str, int]
) -> None:
    """A JSON list at the top level is not the documented shape."""
    host, port = ui_http
    scar_id = _seed_scar()
    status, _, _ = _post(
        host, port, f"/api/scars/{scar_id}/revoke", body=b"[\"reason\"]"
    )
    assert status == 422


def test_post_revoke_oversized_body_returns_413(
    ui_http: tuple[str, int]
) -> None:
    """Body cap matches the modal textarea cap on the client.
    A hostile peer flooding the endpoint cannot drain memory."""
    host, port = ui_http
    scar_id = _seed_scar()
    huge = b"x" * (ui_server._REVOKE_BODY_MAX_BYTES + 1)
    status, _, _ = _post(
        host, port, f"/api/scars/{scar_id}/revoke", body=huge
    )
    assert status == 413


def test_post_revoke_empty_body_succeeds(ui_http: tuple[str, int]) -> None:
    """Brief §10.2: the modal Revoke button stays enabled
    regardless of the textarea state. An empty body is valid."""
    host, port = ui_http
    scar_id = _seed_scar()
    status, _, _ = _post(host, port, f"/api/scars/{scar_id}/revoke", body=b"")
    assert status == 204


def test_post_to_get_endpoint_returns_405(ui_http: tuple[str, int]) -> None:
    """A POST to /api/health (GET endpoint) is method-not-allowed
    so a typo / wrong-route call surfaces explicitly instead of
    silently 404-ing."""
    host, port = ui_http
    status, _, _ = _post(host, port, "/api/health")
    assert status == 405


def test_post_to_unknown_path_returns_404(ui_http: tuple[str, int]) -> None:
    host, port = ui_http
    status, _, _ = _post(host, port, "/no/such/path")
    assert status == 404


def test_get_to_revoke_endpoint_returns_404(ui_http: tuple[str, int]) -> None:
    """The revoke route is POST-only. GET on the same path falls
    through to the 404 branch (no GET handler matches)."""
    host, port = ui_http
    scar_id = _seed_scar()
    status, _, _ = _get(host, port, f"/api/scars/{scar_id}/revoke")
    assert status == 404


def test_post_revoke_then_scars_list_excludes_it(
    ui_http: tuple[str, int]
) -> None:
    """End-to-end shape lock: revoke via POST, then GET
    /api/scars must not include the revoked id."""
    host, port = ui_http
    scar_id = _seed_scar()
    second_id = _seed_scar({"priority": "low"})
    assert _post(host, port, f"/api/scars/{scar_id}/revoke")[0] == 204
    _, body, _ = _get(host, port, "/api/scars")
    ids = [s["id"] for s in json.loads(body)["scars"]]
    assert ids == [second_id]
