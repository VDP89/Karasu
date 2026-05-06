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
    original_push_store_path = ui_server.PUSH_STORE_PATH
    ui_server.configure(
        event_log=tmp_path / "events.jsonl",
        scars_path=tmp_path / "scars",
        config_path=tmp_path / "karasu.yaml",
        push_store_path=tmp_path / "karasu-push.json",
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
            push_store_path=original_push_store_path,
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


# ---------------------------------------------------------------------------
# /api/push — shape lock (UI-12a)
# ---------------------------------------------------------------------------

PUSH_RESPONSE_KEYS = frozenset({
    "state",
    "categories",
    "subscription_count",
    "vapid_public_key",
})


def test_api_push_shape_lock_empty_store(
    ui_http: tuple[str, int]
) -> None:
    """Top-level /api/push response keys are CONTRACT for UI-12a.
    With no store on disk, the projection MUST surface the
    documented enum + zero count + null public key + the
    server-side ``"supported"`` baseline (the client owns the
    "unsupported" / "denied" branches per UI-12 brief §10.9).

    Adding a field to the response requires updating
    PUSH_RESPONSE_KEYS in the SAME PR (UI-11 §11.6.2 carry-
    forward — projection contract changes co-locate with the
    visual that depends on them)."""
    host, port = ui_http
    status, body, headers = _get(host, port, "/api/push")
    assert status == 200
    assert headers["content-type"].startswith("application/json")

    payload = json.loads(body)
    assert set(payload.keys()) == PUSH_RESPONSE_KEYS, (
        f"/api/push key set drift:\n"
        f"  missing: {PUSH_RESPONSE_KEYS - set(payload)}\n"
        f"  extra:   {set(payload) - PUSH_RESPONSE_KEYS}"
    )

    assert payload["state"] == "supported"
    assert payload["categories"] == [
        "attention",
        "errors",
        "corrections",
    ]
    assert payload["subscription_count"] == 0
    assert payload["vapid_public_key"] is None


def test_api_push_with_populated_store(
    ui_http: tuple[str, int]
) -> None:
    """Pin the count + public-key projection against a hand-
    written store so a future refactor cannot silently
    drop either field. Two subscriptions and a non-null public
    key land on the wire."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    store_path.write_text(
        json.dumps({
            "vapid": {
                "public": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCC_0",
                "private": "private-key-MUST-NOT-leak",
            },
            "subscriptions": [
                {
                    "endpoint": "https://fcm.googleapis.com/x",
                    "endpoint_hash": "abc123",
                    "keys": {"p256dh": "p256-1", "auth": "auth-1"},
                    "categories": ["attention"],
                    "created_at": "2026-05-05T00:00:00Z",
                },
                {
                    "endpoint": "https://updates.push.services.mozilla.com/y",
                    "endpoint_hash": "def456",
                    "keys": {"p256dh": "p256-2", "auth": "auth-2"},
                    "categories": ["attention", "errors"],
                    "created_at": "2026-05-05T01:00:00Z",
                },
            ],
        }),
        encoding="utf-8",
    )
    status, body, _ = _get(host, port, "/api/push")
    assert status == 200
    payload = json.loads(body)
    assert payload["subscription_count"] == 2
    assert (
        payload["vapid_public_key"]
        == "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCC_0"
    )


def test_api_push_does_not_leak_raw_endpoint_or_keys(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.5 + §11.6.16 binding — raw endpoint, p256dh,
    auth, and the VAPID *private* key MUST NEVER appear on
    /api/* responses. This test asserts the negative shape so
    a future refactor that loosens projection accidentally
    fails CI before the leak ships."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    raw_endpoint = "https://fcm.googleapis.com/secret-routing-token"
    p256dh = "p256-secret-must-not-leak"
    auth_key = "auth-secret-must-not-leak"
    private_vapid = "private-key-secret-must-not-leak"
    store_path.write_text(
        json.dumps({
            "vapid": {
                "public": "public-ok-to-surface",
                "private": private_vapid,
            },
            "subscriptions": [
                {
                    "endpoint": raw_endpoint,
                    "endpoint_hash": "hash-ok-to-surface",
                    "keys": {"p256dh": p256dh, "auth": auth_key},
                    "categories": ["attention"],
                    "created_at": "2026-05-05T00:00:00Z",
                },
            ],
        }),
        encoding="utf-8",
    )
    status, body, _ = _get(host, port, "/api/push")
    assert status == 200
    body_text = body.decode("utf-8")
    for forbidden in (raw_endpoint, p256dh, auth_key, private_vapid):
        assert forbidden not in body_text, (
            f"forbidden secret material {forbidden!r} appeared "
            f"on /api/push response — pin §11.6 privacy contract "
            f"violation"
        )


def test_api_push_malformed_store_surfaces_500(
    ui_http: tuple[str, int]
) -> None:
    """A malformed store is a real condition (operator
    hand-edited the file, disk corruption, etc.). Surface as
    a 500 rather than silently coercing to an empty count;
    the operator's recourse is to delete the file and let
    UI-12b re-bootstrap."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    store_path.write_text("{ this is not valid JSON", encoding="utf-8")
    status, _, _ = _get(host, port, "/api/push")
    assert status == 500


def test_api_push_top_level_array_in_store_surfaces_500(
    ui_http: tuple[str, int]
) -> None:
    """A2A-style: a JSON array at the root is unambiguously not
    a push store. Surface immediately rather than letting the
    response choke on a missing ``subscriptions`` field."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    store_path.write_text("[1, 2, 3]", encoding="utf-8")
    status, _, _ = _get(host, port, "/api/push")
    assert status == 500


def test_api_push_unreadable_store_surfaces_500(
    ui_http: tuple[str, int]
) -> None:
    """Filesystem error reading the store (permission denied,
    the path is a directory, the device disappeared) folds
    into the same structured 500 contract as malformed JSON.
    Without the OSError → PushStoreError catch the handler
    would let the bare exception trace escape, leaking the
    absolute store path and bypassing the generic
    ``{"error": "push store malformed"}`` body. Codex P2 on
    PR #98 round 1.

    Simulated via a directory at the store path so
    ``read_text`` raises ``IsADirectoryError`` (POSIX) or
    ``PermissionError`` (Windows). Both are ``OSError``
    subclasses."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    if store_path.exists() and store_path.is_file():
        store_path.unlink()
    store_path.mkdir(parents=True, exist_ok=True)
    try:
        status, body, _ = _get(host, port, "/api/push")
        assert status == 500
        # Same generic body as malformed JSON: no path leak,
        # no exception trace.
        assert json.loads(body) == {"error": "push store malformed"}
    finally:
        # Restore so subsequent tests in the module can re-use
        # the fixture's tmp_path / store_path file slot.
        store_path.rmdir()


def test_api_push_invalid_utf8_store_surfaces_500(
    ui_http: tuple[str, int]
) -> None:
    """A store with non-UTF-8 bytes raises
    ``UnicodeDecodeError`` from ``read_text`` BEFORE the JSON
    parser sees it. That is a ``ValueError`` subclass, not an
    ``OSError``, so without a dedicated catch it would escape
    the structured 500 path and reach the wire as a bare
    exception trace (leaking the absolute store path). The
    UnicodeDecodeError → PushStoreError fold makes the body
    identical to malformed-JSON / unreadable-file paths.
    Codex P2 on PR #98 round 2.

    Simulated by writing the forbidden ``\\xff`` lead byte
    to the store. The HTTP body must be the generic error,
    same as the other error branches."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    store_path.write_bytes(b"\xff\xfe\xfd not valid utf-8 here")
    status, body, _ = _get(host, port, "/api/push")
    assert status == 500
    assert json.loads(body) == {"error": "push store malformed"}


def test_api_push_subscriptions_not_a_list_degrades_to_zero(
    ui_http: tuple[str, int]
) -> None:
    """Partial / wrong-shape sub-objects degrade gracefully:
    the count falls to 0 and the public key falls to null
    rather than blowing up the surface. The operator still
    sees a usable footer affordance."""
    host, port = ui_http
    store_path = ui_server.PUSH_STORE_PATH
    store_path.write_text(
        json.dumps({
            "vapid": "not-an-object",
            "subscriptions": "not-a-list",
        }),
        encoding="utf-8",
    )
    status, body, _ = _get(host, port, "/api/push")
    assert status == 200
    payload = json.loads(body)
    assert payload["subscription_count"] == 0
    assert payload["vapid_public_key"] is None


# ===========================================================================
# UI-12b — POST /api/push/subscribe + /api/push/unsubscribe shape locks
# ===========================================================================
#
# Brief §3-B + §7.3 validation matrix. Every error branch's
# response body is generic — the supplied endpoint / keys
# NEVER echo back (pin §11.6.16). The privacy negative-shape
# block at the bottom asserts the absence of sentinel
# substrings across response bodies, the bus, and captured
# logs.


# Sentinel substrings — the privacy negative-shape tests assert
# these never appear in any observable surface (response body,
# bus event, captured logs). Distinct strings per surface so a
# regression naming the wrong leak point is unambiguous.
_PUSH_TEST_ENDPOINT = (
    "https://fcm.googleapis.com/sentinel-DO-NOT-LEAK-7d9f2e"
)
_PUSH_TEST_P256DH = "DO-NOT-LEAK-P256DH-key-material-here"
_PUSH_TEST_AUTH = "DO-NOT-LEAK-AUTH-key-material-here"
_PUSH_TEST_VAPID_PUBLIC = "vapid-public-b64u-OK-to-surface"
_PUSH_TEST_VAPID_PRIVATE = "DO-NOT-LEAK-vapid-private-b64u"


def _seed_vapid(public: str = _PUSH_TEST_VAPID_PUBLIC,
                private: str = _PUSH_TEST_VAPID_PRIVATE) -> None:
    """Seed VAPID keys in the configured push store. UI-12b's
    subscribe handler 503s if the store has no VAPID section."""
    store_path = ui_server.PUSH_STORE_PATH
    raw = {}
    if store_path.exists():
        try:
            raw = json.loads(store_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raw = {}
        except json.JSONDecodeError:
            raw = {}
    raw["vapid"] = {"public": public, "private": private}
    store_path.write_text(json.dumps(raw), encoding="utf-8")


def _push_subscribe_body(
    endpoint: str = _PUSH_TEST_ENDPOINT,
    p256dh: str = _PUSH_TEST_P256DH,
    auth: str = _PUSH_TEST_AUTH,
    categories: list[str] | None = None,
) -> bytes:
    return json.dumps({
        "subscription": {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        },
        "categories": ["attention"] if categories is None else categories,
    }).encode("utf-8")


def _push_unsubscribe_body(endpoint: str = _PUSH_TEST_ENDPOINT) -> bytes:
    return json.dumps({"endpoint": endpoint}).encode("utf-8")


def _read_bus_events() -> list[dict]:
    """Return all bus events as a list of decoded dicts.
    Convenience for negative-shape assertions ("zero new
    events" / "exactly one new event")."""
    if not ui_server.EVENT_LOG.exists():
        return []
    return [
        json.loads(line)
        for line in ui_server.EVENT_LOG.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _store_subscriptions() -> list[dict]:
    """Return the current subscriptions list from the configured
    push store, or [] if the store is missing/empty."""
    store_path = ui_server.PUSH_STORE_PATH
    if not store_path.exists():
        return []
    raw = json.loads(store_path.read_text(encoding="utf-8"))
    subs = raw.get("subscriptions", [])
    return subs if isinstance(subs, list) else []


# ---------------------------------------------------------------------------
# Subscribe — happy path + bus emission
# ---------------------------------------------------------------------------


def test_post_push_subscribe_happy_path_returns_204(
    ui_http: tuple[str, int]
) -> None:
    """Brief §3-B happy path: 204, NO body, store mutated, bus
    carries push_subscribe with endpoint_hash + categories."""
    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/subscribe", body=_push_subscribe_body()
    )
    assert status == 204
    assert body == b""

    subs = _store_subscriptions()
    assert len(subs) == 1
    assert subs[0]["endpoint"] == _PUSH_TEST_ENDPOINT
    assert subs[0]["categories"] == ["attention"]


def test_post_push_subscribe_emits_human_decision(
    ui_http: tuple[str, int]
) -> None:
    """The bus event MUST carry data.action="push_subscribe",
    data.endpoint_hash (sha256-hex), data.categories
    canonical-sorted, source="ui"."""
    from karasu.ui.push_store import compute_endpoint_hash

    host, port = ui_http
    _seed_vapid()
    _post(host, port, "/api/push/subscribe", body=_push_subscribe_body())

    events = _read_bus_events()
    push_events = [e for e in events if e.get("data", {}).get("action") == "push_subscribe"]
    assert len(push_events) == 1
    e = push_events[0]
    assert e["type"] == "human_decision"
    assert e["source"] == "ui"
    assert e["data"]["endpoint_hash"] == compute_endpoint_hash(_PUSH_TEST_ENDPOINT)
    assert e["data"]["categories"] == ["attention"]


def test_post_push_subscribe_canonical_sort_order(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.10 — the documented order is (attention,
    errors, corrections). Categories arriving in any order
    project to that canonical order on the bus."""
    host, port = ui_http
    _seed_vapid()
    _post(
        host, port, "/api/push/subscribe",
        body=_push_subscribe_body(categories=["corrections", "attention", "errors"]),
    )
    events = _read_bus_events()
    e = [x for x in events if x.get("data", {}).get("action") == "push_subscribe"][-1]
    assert e["data"]["categories"] == ["attention", "errors", "corrections"]


def test_post_push_subscribe_idempotent_duplicate_returns_204(
    ui_http: tuple[str, int]
) -> None:
    """Brief §10.2: duplicate subscribe = UPDATE. Second POST
    returns 204; categories overwrite; a fresh push_subscribe
    event lands on the bus regardless (operator intent is
    authoritative)."""
    host, port = ui_http
    _seed_vapid()
    s1, _, _ = _post(host, port, "/api/push/subscribe", body=_push_subscribe_body())
    s2, _, _ = _post(
        host, port, "/api/push/subscribe",
        body=_push_subscribe_body(categories=["errors", "corrections"]),
    )
    assert s1 == 204
    assert s2 == 204

    # Single subscription in the store; categories reflect the
    # second POST's choice.
    subs = _store_subscriptions()
    assert len(subs) == 1
    assert subs[0]["categories"] == ["errors", "corrections"]

    # Two push_subscribe events on the bus, not one.
    events = _read_bus_events()
    push_events = [e for e in events if e.get("data", {}).get("action") == "push_subscribe"]
    assert len(push_events) == 2


def test_post_push_subscribe_empty_categories_allowed(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.9: empty array is allowed as a deliberate
    zero-noise subscription. Bus event records the empty array
    verbatim."""
    host, port = ui_http
    _seed_vapid()
    status, _, _ = _post(
        host, port, "/api/push/subscribe",
        body=_push_subscribe_body(categories=[]),
    )
    assert status == 204
    events = _read_bus_events()
    e = [x for x in events if x.get("data", {}).get("action") == "push_subscribe"][-1]
    assert e["data"]["categories"] == []


# ---------------------------------------------------------------------------
# Subscribe — validation matrix (422 / 413 / 400 / 503)
# ---------------------------------------------------------------------------


def test_post_push_subscribe_missing_subscription_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = json.dumps({"categories": ["attention"]}).encode("utf-8")
    status, _, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 422


def test_post_push_subscribe_missing_endpoint_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = json.dumps({
        "subscription": {"keys": {"p256dh": "x", "auth": "y"}},
        "categories": ["attention"],
    }).encode("utf-8")
    assert _post(host, port, "/api/push/subscribe", body=body)[0] == 422


def test_post_push_subscribe_missing_p256dh_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = json.dumps({
        "subscription": {
            "endpoint": _PUSH_TEST_ENDPOINT,
            "keys": {"auth": _PUSH_TEST_AUTH},
        },
        "categories": ["attention"],
    }).encode("utf-8")
    assert _post(host, port, "/api/push/subscribe", body=body)[0] == 422


def test_post_push_subscribe_missing_auth_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = json.dumps({
        "subscription": {
            "endpoint": _PUSH_TEST_ENDPOINT,
            "keys": {"p256dh": _PUSH_TEST_P256DH},
        },
        "categories": ["attention"],
    }).encode("utf-8")
    assert _post(host, port, "/api/push/subscribe", body=body)[0] == 422


def test_post_push_subscribe_invalid_category_returns_422(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.10 — closed enum. 'broadcast' is not in
    {attention, errors, corrections}."""
    host, port = ui_http
    _seed_vapid()
    body = _push_subscribe_body(categories=["broadcast"])
    assert _post(host, port, "/api/push/subscribe", body=body)[0] == 422


def test_post_push_subscribe_duplicate_categories_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = _push_subscribe_body(categories=["attention", "attention"])
    assert _post(host, port, "/api/push/subscribe", body=body)[0] == 422


def test_post_push_subscribe_endpoint_not_https_returns_422(
    ui_http: tuple[str, int]
) -> None:
    """Brief §3-B — Web Push endpoints are always HTTPS URLs."""
    host, port = ui_http
    _seed_vapid()
    body = _push_subscribe_body(endpoint="http://insecure.example/x")
    assert _post(host, port, "/api/push/subscribe", body=body)[0] == 422


def test_post_push_subscribe_oversized_body_returns_413(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    huge = b"{" + b"x" * (ui_server._PUSH_BODY_MAX_BYTES + 1)
    assert _post(host, port, "/api/push/subscribe", body=huge)[0] == 413


def test_post_push_subscribe_malformed_json_returns_400(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.5 — malformed JSON is 400 (distinct from 422
    non-object branch). Generic body, no JSONDecodeError text."""
    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/subscribe", body=b"{not really json"
    )
    assert status == 400
    assert json.loads(body) == {"error": "invalid request"}


def test_post_push_subscribe_top_level_array_returns_422(
    ui_http: tuple[str, int]
) -> None:
    """Top-level non-object root → 422 with generic body."""
    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/subscribe", body=b"[1, 2, 3]"
    )
    assert status == 422
    assert json.loads(body) == {"error": "request body must be an object"}


def test_post_push_subscribe_top_level_string_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/subscribe", body=b'"some string"'
    )
    assert status == 422
    assert json.loads(body) == {"error": "request body must be an object"}


def test_post_push_subscribe_vapid_missing_returns_503(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.14 — defensive 503 when VAPID is not seeded."""
    host, port = ui_http
    # NO _seed_vapid() — store has no VAPID section.
    status, body, _ = _post(
        host, port, "/api/push/subscribe", body=_push_subscribe_body()
    )
    assert status == 503
    assert json.loads(body) == {"error": "vapid keys not provisioned"}

    # The 503 path MUST NOT mutate the store or emit a bus event.
    assert _store_subscriptions() == []
    push_events = [
        e for e in _read_bus_events()
        if e.get("data", {}).get("action") == "push_subscribe"
    ]
    assert push_events == []


# ---------------------------------------------------------------------------
# Unsubscribe — happy path + bus emission
# ---------------------------------------------------------------------------


def test_post_push_unsubscribe_happy_path_returns_204(
    ui_http: tuple[str, int]
) -> None:
    """Brief §3-B happy path: subscribed first, then 204 on
    unsubscribe; store empties; bus carries push_unsubscribe."""
    host, port = ui_http
    _seed_vapid()
    assert _post(host, port, "/api/push/subscribe", body=_push_subscribe_body())[0] == 204

    status, body, _ = _post(
        host, port, "/api/push/unsubscribe", body=_push_unsubscribe_body()
    )
    assert status == 204
    assert body == b""
    assert _store_subscriptions() == []


def test_post_push_unsubscribe_emits_human_decision(
    ui_http: tuple[str, int]
) -> None:
    from karasu.ui.push_store import compute_endpoint_hash

    host, port = ui_http
    _seed_vapid()
    _post(host, port, "/api/push/subscribe", body=_push_subscribe_body())
    _post(host, port, "/api/push/unsubscribe", body=_push_unsubscribe_body())

    events = _read_bus_events()
    unsub = [e for e in events if e.get("data", {}).get("action") == "push_unsubscribe"]
    assert len(unsub) == 1
    e = unsub[0]
    assert e["type"] == "human_decision"
    assert e["source"] == "ui"
    assert e["data"]["endpoint_hash"] == compute_endpoint_hash(_PUSH_TEST_ENDPOINT)
    # No data.categories on unsubscribe (UI-12b §3-C schema).
    assert "categories" not in e["data"]


# ---------------------------------------------------------------------------
# Unsubscribe — pin §11.6.13: 404 path emits ZERO bus events
# ---------------------------------------------------------------------------


def test_post_push_unsubscribe_unknown_endpoint_returns_404(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.13 — 404 path is server silence as audit
    truth. NO bus event emitted. NO store mutation."""
    host, port = ui_http
    _seed_vapid()
    bus_before = _read_bus_events()
    store_before = _store_subscriptions()

    status, body, _ = _post(
        host, port, "/api/push/unsubscribe",
        body=_push_unsubscribe_body(endpoint="https://no.such.endpoint/x"),
    )
    assert status == 404
    assert json.loads(body) == {"error": "subscription not found"}

    # Pin §11.6.13 binding: zero new events, zero store delta.
    assert _read_bus_events() == bus_before
    assert _store_subscriptions() == store_before


def test_post_push_unsubscribe_after_subscribe_then_unknown_emits_only_one(
    ui_http: tuple[str, int]
) -> None:
    """End-to-end: subscribe → unsubscribe (204, one
    push_unsubscribe) → unsubscribe again with same endpoint
    → 404 with zero new events. Total bus push_unsubscribe
    count = exactly 1."""
    host, port = ui_http
    _seed_vapid()
    _post(host, port, "/api/push/subscribe", body=_push_subscribe_body())
    s1, _, _ = _post(host, port, "/api/push/unsubscribe", body=_push_unsubscribe_body())
    s2, _, _ = _post(host, port, "/api/push/unsubscribe", body=_push_unsubscribe_body())
    assert s1 == 204
    assert s2 == 404

    events = _read_bus_events()
    unsub = [e for e in events if e.get("data", {}).get("action") == "push_unsubscribe"]
    assert len(unsub) == 1


# ---------------------------------------------------------------------------
# Unsubscribe — validation matrix
# ---------------------------------------------------------------------------


def test_post_push_unsubscribe_missing_endpoint_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = json.dumps({}).encode("utf-8")
    assert _post(host, port, "/api/push/unsubscribe", body=body)[0] == 422


def test_post_push_unsubscribe_endpoint_not_https_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = _push_unsubscribe_body(endpoint="http://insecure.example/x")
    assert _post(host, port, "/api/push/unsubscribe", body=body)[0] == 422


def test_post_push_unsubscribe_oversized_body_returns_413(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    huge = b"{" + b"x" * (ui_server._PUSH_BODY_MAX_BYTES + 1)
    assert _post(host, port, "/api/push/unsubscribe", body=huge)[0] == 413


def test_post_push_unsubscribe_malformed_json_returns_400(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/unsubscribe", body=b"not really json"
    )
    assert status == 400
    assert json.loads(body) == {"error": "invalid request"}


def test_post_push_unsubscribe_top_level_number_returns_422(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/unsubscribe", body=b"42"
    )
    assert status == 422
    assert json.loads(body) == {"error": "request body must be an object"}


# ---------------------------------------------------------------------------
# Privacy negative-shape — pins §11.6.5 + §11.6.16
# ---------------------------------------------------------------------------


def _assert_no_secrets_anywhere(
    *,
    response_body: bytes,
) -> None:
    """Negative-shape predicate: the sentinel substrings MUST
    NOT appear in the response body. Used by every error-branch
    test below + the happy-path bus / GET-projection tests."""
    body_text = response_body.decode("utf-8", errors="replace")
    for forbidden in (
        _PUSH_TEST_ENDPOINT,
        _PUSH_TEST_P256DH,
        _PUSH_TEST_AUTH,
        _PUSH_TEST_VAPID_PRIVATE,
        "DO-NOT-LEAK",
    ):
        assert forbidden not in body_text, (
            f"sentinel {forbidden!r} appeared in response body — "
            f"pin §11.6.16 violation"
        )


def _assert_no_secrets_on_bus() -> None:
    """The bus events MUST contain endpoint_hash but NOT the
    raw endpoint, p256dh, or auth. Walks events.jsonl."""
    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8") if ui_server.EVENT_LOG.exists() else ""
    for forbidden in (
        _PUSH_TEST_ENDPOINT,
        _PUSH_TEST_P256DH,
        _PUSH_TEST_AUTH,
        "DO-NOT-LEAK-P256DH",
        "DO-NOT-LEAK-AUTH",
    ):
        assert forbidden not in raw, (
            f"sentinel {forbidden!r} appeared in bus log — pin "
            f"§11.6.5 violation"
        )


def _state_snapshot() -> tuple[int, str]:
    """Capture (bus_event_count, store_raw_text) so an error
    branch can assert ZERO bus + store delta. Codex P1 round 1
    on PR #102: every error branch must prove non-mutation,
    not just generic response body shape."""
    bus_count = len(_read_bus_events())
    store_text = (
        ui_server.PUSH_STORE_PATH.read_text(encoding="utf-8")
        if ui_server.PUSH_STORE_PATH.exists()
        else ""
    )
    return bus_count, store_text


def _assert_no_state_delta(before: tuple[int, str]) -> None:
    """Assert bus + store unchanged since ``before`` snapshot.
    Used after every error branch to pin pin §11.6.5 binding:
    error paths emit zero bus events AND zero store mutation.
    """
    after = _state_snapshot()
    assert after[0] == before[0], (
        f"bus delta on error branch: {before[0]} → {after[0]} — "
        f"pin §11.6.5 violation"
    )
    assert after[1] == before[1], (
        "store mutated on error branch — pin §11.6.5 violation"
    )


def test_subscribe_happy_path_no_secrets_in_response_or_bus(
    ui_http: tuple[str, int]
) -> None:
    """Happy path: 204 has empty body + the bus carries the
    hash but no raw material."""
    from karasu.ui.push_store import compute_endpoint_hash

    host, port = ui_http
    _seed_vapid()
    status, body, _ = _post(
        host, port, "/api/push/subscribe", body=_push_subscribe_body()
    )
    assert status == 204
    _assert_no_secrets_anywhere(response_body=body)
    _assert_no_secrets_on_bus()
    # The hash IS the audit metadata; assert it surfaces.
    expected_hash = compute_endpoint_hash(_PUSH_TEST_ENDPOINT)
    raw = ui_server.EVENT_LOG.read_text(encoding="utf-8")
    assert expected_hash in raw


def test_subscribe_invalid_endpoint_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    """422 path: malformed endpoint, body still carries the
    sentinel keys. Response MUST NOT echo them."""
    host, port = ui_http
    _seed_vapid()
    body = _push_subscribe_body(endpoint="not-a-url-but-sentinel-DO-NOT-LEAK-7d9f2e")
    status, resp_body, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 422
    _assert_no_secrets_anywhere(response_body=resp_body)
    _assert_no_secrets_on_bus()


def test_subscribe_invalid_categories_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = _push_subscribe_body(categories=["broadcast"])
    status, resp_body, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 422
    _assert_no_secrets_anywhere(response_body=resp_body)
    _assert_no_secrets_on_bus()


def test_subscribe_vapid_missing_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    # No _seed_vapid() — sentinel-bearing body still tests the
    # 503 branch's privacy.
    status, resp_body, _ = _post(
        host, port, "/api/push/subscribe", body=_push_subscribe_body()
    )
    assert status == 503
    _assert_no_secrets_anywhere(response_body=resp_body)
    _assert_no_secrets_on_bus()


def test_subscribe_oversized_body_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    # Pad with sentinel substring to prove the 413 path doesn't
    # echo the body.
    huge = (
        b"{\"sentinel\": \"DO-NOT-LEAK-7d9f2e\","
        + b"\"x\": \"" + b"x" * ui_server._PUSH_BODY_MAX_BYTES + b"\"}"
    )
    status, resp_body, _ = _post(host, port, "/api/push/subscribe", body=huge)
    assert status == 413
    _assert_no_secrets_anywhere(response_body=resp_body)


def test_subscribe_malformed_json_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.5 round-2 extension — malformed-body branch
    must not echo the sentinel substring back via parser
    error text."""
    host, port = ui_http
    _seed_vapid()
    # Truncated JSON with sentinel embedded in the raw bytes.
    body = (
        b'{"subscription": {"endpoint": "https://x/sentinel-DO-NOT-LEAK-7d9f2e",'
        b' "keys"'
    )
    status, resp_body, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 400
    _assert_no_secrets_anywhere(response_body=resp_body)


def test_subscribe_top_level_string_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    """422 non-object branch with sentinel-bearing string body."""
    host, port = ui_http
    _seed_vapid()
    body = b'"DO-NOT-LEAK-7d9f2e"'
    status, resp_body, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 422
    _assert_no_secrets_anywhere(response_body=resp_body)


def test_unsubscribe_unknown_endpoint_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    """404 generic body must NOT echo the supplied endpoint
    (pin §11.6.16)."""
    host, port = ui_http
    _seed_vapid()
    sentinel_url = "https://test.example/sentinel-DO-NOT-LEAK-404-path"
    status, resp_body, _ = _post(
        host, port, "/api/push/unsubscribe",
        body=_push_unsubscribe_body(endpoint=sentinel_url),
    )
    assert status == 404
    body_text = resp_body.decode("utf-8")
    assert "DO-NOT-LEAK" not in body_text
    assert sentinel_url not in body_text
    assert json.loads(resp_body) == {"error": "subscription not found"}


def test_unsubscribe_malformed_json_no_secrets_in_response(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    body = b'{"endpoint": "https://x/DO-NOT-LEAK-404",'  # truncated
    status, resp_body, _ = _post(
        host, port, "/api/push/unsubscribe", body=body
    )
    assert status == 400
    _assert_no_secrets_anywhere(response_body=resp_body)


def test_api_push_get_response_no_secrets_after_subscribe(
    ui_http: tuple[str, int]
) -> None:
    """End-to-end: after a successful subscribe with sentinel
    material, GET /api/push must STILL surface only the count
    + public key — never the raw endpoint or keys."""
    host, port = ui_http
    _seed_vapid()
    _post(host, port, "/api/push/subscribe", body=_push_subscribe_body())

    status, body, _ = _get(host, port, "/api/push")
    assert status == 200
    payload = json.loads(body)
    assert payload["subscription_count"] == 1
    assert payload["vapid_public_key"] == _PUSH_TEST_VAPID_PUBLIC

    # Negative shape: the response body MUST NOT carry the
    # sentinel raw endpoint or keys.
    body_text = body.decode("utf-8")
    for forbidden in (
        _PUSH_TEST_ENDPOINT,
        _PUSH_TEST_P256DH,
        _PUSH_TEST_AUTH,
        _PUSH_TEST_VAPID_PRIVATE,
        "DO-NOT-LEAK",
    ):
        assert forbidden not in body_text


# ---------------------------------------------------------------------------
# Codex P1 round 1 on PR #102 — invalid-UTF-8 body coverage
# ---------------------------------------------------------------------------
#
# Pin §11.6.5 binding: every error branch that accepts or
# parses request body material — including non-UTF-8 bytes —
# must surface a generic body, zero bus events, zero store
# delta, and no sentinel material in any captured surface.
# The handler catches UnicodeDecodeError alongside
# JSONDecodeError; this test pins the contract.


def test_post_push_subscribe_invalid_utf8_body_returns_400(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.5 round-1 on PR #102: a body with bytes that
    are not valid UTF-8 (forbidden lead bytes 0xff / 0xfe / 0xfd)
    must surface as 400 with a generic body — no
    UnicodeDecodeError repr, no echo of the raw bytes."""
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()

    # 0xff is the canonical "never valid UTF-8 lead byte"
    # sentinel; embedded with sentinel substring AROUND it so
    # the test proves both the bytes and the substring stay
    # off-wire.
    body = (
        b'\xff\xfe\xfd{"subscription": {"endpoint": '
        b'"https://x/sentinel-DO-NOT-LEAK-utf8"}}'
    )
    status, resp_body, _ = _post(
        host, port, "/api/push/subscribe", body=body
    )
    assert status == 400
    assert json.loads(resp_body) == {"error": "invalid request"}
    _assert_no_secrets_anywhere(response_body=resp_body)
    _assert_no_state_delta(before)


def test_post_push_unsubscribe_invalid_utf8_body_returns_400(
    ui_http: tuple[str, int]
) -> None:
    """Same contract on the unsubscribe POST — non-UTF-8 lead
    bytes surface as 400 with a generic body."""
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()

    body = b'\xff\xfe\xfd{"endpoint": "https://x/DO-NOT-LEAK-utf8"}'
    status, resp_body, _ = _post(
        host, port, "/api/push/unsubscribe", body=body
    )
    assert status == 400
    assert json.loads(resp_body) == {"error": "invalid request"}
    _assert_no_secrets_anywhere(response_body=resp_body)
    _assert_no_state_delta(before)


# ---------------------------------------------------------------------------
# Codex P1 round 1 on PR #102 — full state-delta coverage
# ---------------------------------------------------------------------------
#
# Each error branch below takes a snapshot before the request
# and asserts after-state matches via _assert_no_state_delta.
# The earlier _assert_no_secrets_anywhere helper proves the
# response body is generic; these tests prove the side-effect
# surface is also clean.


def test_subscribe_422_invalid_endpoint_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    body = _push_subscribe_body(endpoint="not-a-url-DO-NOT-LEAK")
    status, _, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 422
    _assert_no_state_delta(before)


def test_subscribe_422_invalid_categories_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    body = _push_subscribe_body(categories=["broadcast"])
    status, _, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 422
    _assert_no_state_delta(before)


def test_subscribe_503_vapid_missing_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    # No _seed_vapid() — defensive 503 path.
    before = _state_snapshot()
    status, _, _ = _post(
        host, port, "/api/push/subscribe", body=_push_subscribe_body()
    )
    assert status == 503
    _assert_no_state_delta(before)


def test_subscribe_413_oversize_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    huge = b"{" + b"x" * (ui_server._PUSH_BODY_MAX_BYTES + 1)
    status, _, _ = _post(host, port, "/api/push/subscribe", body=huge)
    assert status == 413
    _assert_no_state_delta(before)


def test_subscribe_400_malformed_json_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    body = (
        b'{"subscription": {"endpoint": "https://x/sentinel-DO-NOT-LEAK",'
        b' "keys"'
    )
    status, _, _ = _post(host, port, "/api/push/subscribe", body=body)
    assert status == 400
    _assert_no_state_delta(before)


def test_subscribe_422_top_level_array_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    status, _, _ = _post(
        host, port, "/api/push/subscribe", body=b'["DO-NOT-LEAK"]'
    )
    assert status == 422
    _assert_no_state_delta(before)


def test_unsubscribe_404_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    """Pin §11.6.13 binding (also): 404 path emits zero bus
    events AND zero store delta."""
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    status, _, _ = _post(
        host, port, "/api/push/unsubscribe",
        body=_push_unsubscribe_body(
            endpoint="https://no.such.endpoint/DO-NOT-LEAK"
        ),
    )
    assert status == 404
    _assert_no_state_delta(before)


def test_unsubscribe_400_malformed_json_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    body = b'{"endpoint": "https://x/DO-NOT-LEAK",'  # truncated
    status, _, _ = _post(host, port, "/api/push/unsubscribe", body=body)
    assert status == 400
    _assert_no_state_delta(before)


def test_unsubscribe_422_top_level_number_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    status, _, _ = _post(
        host, port, "/api/push/unsubscribe", body=b"42"
    )
    assert status == 422
    _assert_no_state_delta(before)


def test_unsubscribe_413_oversize_no_state_delta(
    ui_http: tuple[str, int]
) -> None:
    host, port = ui_http
    _seed_vapid()
    before = _state_snapshot()
    huge = b"{" + b"x" * (ui_server._PUSH_BODY_MAX_BYTES + 1)
    status, _, _ = _post(host, port, "/api/push/unsubscribe", body=huge)
    assert status == 413
    _assert_no_state_delta(before)
