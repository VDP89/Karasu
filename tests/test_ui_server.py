"""Tests for ``karasu.ui.server``.

UI-9 deferred items (audit-noted on UI-1 / UI-9):

1. URL-encoded path-traversal coverage for ``/assets/*``. The
   handler's existing guard normalises through ``Path.resolve``
   then ``relative_to(STATIC_DIR.resolve())``; this module pins
   the behaviour against literal ``..``, percent-encoded ``..``
   (``%2E%2E``), and mixed combinations so a future refactor of
   the handler cannot silently regress the boundary.

2. Config-aware ``EVENT_LOG`` constant. ``run_ui_server`` and
   ``configure`` now accept the bus path; ``cmd_ui`` wires it
   from ``karasu.yaml``. Tests verify both the override and
   that ``configure`` persists across requests.
"""

from __future__ import annotations

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Iterator
from urllib.request import urlopen

import pytest

from karasu.ui import server as ui_server


# ---------------------------------------------------------------------------
# Server lifecycle helper
# ---------------------------------------------------------------------------


@pytest.fixture
def ui_http(tmp_path: Path) -> Iterator[tuple[str, int]]:
    """Spin up ``UIHandler`` on a random port for the duration of
    the test. Resets the module ``EVENT_LOG`` to a per-test
    ``tmp_path`` so tests do not race on the default bus path."""
    original_event_log = ui_server.EVENT_LOG
    ui_server.configure(tmp_path / "events.jsonl")
    server = ThreadingHTTPServer(("127.0.0.1", 0), ui_server.UIHandler)
    thread = threading.Thread(
        target=server.serve_forever, name="karasu-ui-test", daemon=True
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


def _get(host: str, port: int, path: str) -> tuple[int, bytes]:
    """Fetch ``path`` from the test server. Returns ``(status, body)``.

    Uses a context manager that swallows the urllib HTTPError so
    4xx / 5xx responses surface as a status / body pair rather
    than a raised exception (closer to "what does an HTTP client
    actually see?")."""
    from urllib.error import HTTPError

    url = f"http://{host}:{port}{path}"
    try:
        with urlopen(url, timeout=5.0) as response:
            return response.status, response.read()
    except HTTPError as exc:
        return exc.code, exc.read()


# ---------------------------------------------------------------------------
# Path-traversal coverage for /assets/*
# ---------------------------------------------------------------------------


def test_literal_dotdot_traversal_is_forbidden(
    ui_http: tuple[str, int]
) -> None:
    """``/assets/../../etc/passwd`` must resolve outside
    ``STATIC_DIR`` and be rejected with 403, not silently served."""
    host, port = ui_http
    status, _ = _get(host, port, "/assets/../../etc/passwd")
    assert status == 403


def test_literal_dotdot_traversal_via_inner_segment_is_forbidden(
    ui_http: tuple[str, int]
) -> None:
    """A traversal that uses inner ``..`` segments (``foo/../..``)
    still resolves above ``STATIC_DIR`` and must trip the guard."""
    host, port = ui_http
    status, _ = _get(
        host, port, "/assets/foo/../bar/../../etc/passwd"
    )
    assert status == 403


def test_url_encoded_dotdot_does_not_traverse(
    ui_http: tuple[str, int]
) -> None:
    """``%2E%2E`` is not URL-decoded by ``BaseHTTPRequestHandler``;
    it lands as a literal filename. The guard does not need to
    reject it explicitly — it simply doesn't match any real file
    and returns 404. Pinned so a future change that adds
    URL-decoding to ``self.path`` does NOT silently turn this
    into a traversal."""
    host, port = ui_http
    status, _ = _get(host, port, "/assets/%2E%2E/etc/passwd")
    # Either 404 (literal filename, no such file) or 403 (resolves
    # under STATIC_DIR but not a file). Both are SAFE — the test
    # asserts the boundary holds, not the specific code path.
    assert status in (403, 404)
    assert status != 200


def test_url_encoded_dotdot_with_encoded_slash_does_not_traverse(
    ui_http: tuple[str, int]
) -> None:
    """``%2E%2E%2F`` (encoded ``../``) — same boundary as the
    encoded-dot test. Must NOT escape ``STATIC_DIR``."""
    host, port = ui_http
    status, _ = _get(
        host, port, "/assets/%2E%2E%2Fetc%2Fpasswd"
    )
    assert status in (403, 404)
    assert status != 200


def test_double_encoded_dotdot_does_not_traverse(
    ui_http: tuple[str, int]
) -> None:
    """``%252E%252E`` (double-encoded — ``%`` itself encoded) must
    decode to ``%2E%2E`` at most, never to ``..``. Defence
    against a hypothetical future middleware that decodes the
    URL once before the handler sees it."""
    host, port = ui_http
    status, _ = _get(
        host, port, "/assets/%252E%252E/etc/passwd"
    )
    assert status in (403, 404)
    assert status != 200


def test_assets_outside_static_dir_unreachable_via_traversal(
    ui_http: tuple[str, int], tmp_path: Path
) -> None:
    """A real file outside STATIC_DIR (a peer of it) is not
    reachable through ``/assets/../`` even though it physically
    exists. Pinning this stops a future refactor that sets
    STATIC_DIR off the import-time location from accidentally
    widening the reachable set."""
    host, port = ui_http
    secret = ui_server.STATIC_DIR.parent / "secret.txt"
    if secret.exists():  # pragma: no cover — defensive cleanup
        secret.unlink()
    secret.write_text("DO NOT SERVE")
    try:
        status, body = _get(host, port, "/assets/../secret.txt")
        assert status == 403
        assert b"DO NOT SERVE" not in body
    finally:
        secret.unlink()


def test_valid_asset_under_static_dir_is_served(
    ui_http: tuple[str, int]
) -> None:
    """Sanity: a real file under ``static/`` is reachable. Pinned
    so a regression that 403s every asset surfaces here."""
    host, port = ui_http
    asset = ui_server.STATIC_DIR / "test_asset.txt"
    asset.write_text("hello\n")
    try:
        status, body = _get(host, port, "/assets/test_asset.txt")
        assert status == 200
        assert body == b"hello\n"
    finally:
        asset.unlink()


def test_index_html_served_at_root(ui_http: tuple[str, int]) -> None:
    host, port = ui_http
    status, body = _get(host, port, "/")
    assert status == 200
    # The chunk-4c stub is still inline-styled HTML; just check the
    # title survives so the route is wired.
    assert b"<title>Karasu UI</title>" in body


# ---------------------------------------------------------------------------
# Config-aware EVENT_LOG
# ---------------------------------------------------------------------------


def test_configure_overrides_event_log(tmp_path: Path) -> None:
    """``configure(path)`` sets the module global so subsequent
    ``_read_events`` calls read from the override. Idempotent —
    calling it twice leaves the second value in place."""
    original = ui_server.EVENT_LOG
    try:
        first = tmp_path / "first.jsonl"
        second = tmp_path / "second.jsonl"
        ui_server.configure(first)
        assert ui_server.EVENT_LOG == first
        ui_server.configure(second)
        assert ui_server.EVENT_LOG == second
    finally:
        ui_server.configure(original)


def test_api_events_reads_configured_path(
    ui_http: tuple[str, int], tmp_path: Path
) -> None:
    """End-to-end: write a synthetic event to the configured path,
    request ``/api/events``, see it through the projection."""
    host, port = ui_http
    event = {
        "id": "abc",
        "timestamp": "2026-05-03T10:00:00Z",
        "type": "file_change",
        "source": "watcher",
        "data": {
            "path": "src/foo.py",
            "classification": "code_change",
            "priority": "high",
        },
        "dispatch": {},
        "response": {},
    }
    # ui_http already pointed EVENT_LOG at tmp_path/events.jsonl.
    ui_server.EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ui_server.EVENT_LOG.write_text(json.dumps(event) + "\n")

    status, body = _get(host, port, "/api/events")
    assert status == 200
    payload = json.loads(body)
    assert len(payload["events"]) == 1
    projected = payload["events"][0]
    assert projected["id"] == "abc"
    assert projected["path"] == "src/foo.py"
    assert projected["priority"] == "high"


def test_api_events_returns_empty_when_log_missing(
    ui_http: tuple[str, int]
) -> None:
    """An operator who runs ``karasu ui`` before ``karasu watch``
    has ever written an event should see an empty projection,
    not a 500."""
    host, port = ui_http
    # ui_http points EVENT_LOG at a path that does not exist yet.
    assert not ui_server.EVENT_LOG.exists()
    status, body = _get(host, port, "/api/events")
    assert status == 200
    payload = json.loads(body)
    assert payload == {"events": []}


def test_run_ui_server_kwarg_calls_configure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``run_ui_server(event_log=PATH)`` must propagate through
    ``configure`` so the module global flips before the server
    starts serving. Verified without actually binding by patching
    ``ThreadingHTTPServer`` to a no-op."""
    captured: dict[str, Path] = {}

    real_configure = ui_server.configure

    def spy(path: Path) -> None:
        captured["path"] = path
        real_configure(path)

    class _ServerStub:
        def __init__(self, address, handler) -> None:
            self.server_address = address

        def serve_forever(self) -> None:
            raise KeyboardInterrupt

        def shutdown(self) -> None:
            pass

    monkeypatch.setattr(ui_server, "configure", spy)
    monkeypatch.setattr(ui_server, "ThreadingHTTPServer", _ServerStub)

    target = tmp_path / "custom.jsonl"
    ui_server.run_ui_server(host="127.0.0.1", port=0, event_log=target)
    assert captured["path"] == target


# ---------------------------------------------------------------------------
# _crow_state precedence (UI-5 — bug caught by Codex on PR #74 re-audit)
# ---------------------------------------------------------------------------
#
# The earlier implementation set ``state = "processing"`` on any
# file_change in the loop and continued; a completed agent_response
# tail with an older file_change therefore resolved to "processing"
# instead of "idle", contradicting the documented "latest event is
# a file_change" rule and miscolouring 00-crow-idle.png. These tests
# pin the corrected precedence so a future refactor cannot regress
# the projection.


def _file_change(idx: int = 1) -> dict:
    return {
        "id": f"fc-{idx:03d}",
        "type": "file_change",
        "data": {"path": f"src/foo_{idx}.py"},
    }


def _agent_response(
    idx: int = 1, *, status: str = "completed", requires_human: bool = False
) -> dict:
    return {
        "id": f"ar-{idx:03d}",
        "type": "agent_response",
        "status": status,
        "requires_human": requires_human,
        "data": {"path": f"src/foo_{idx}.py"},
    }


def test_crow_state_empty_events_is_idle() -> None:
    assert ui_server._crow_state([]) == "idle"


def test_crow_state_latest_file_change_is_processing() -> None:
    assert ui_server._crow_state([_file_change(1)]) == "processing"


def test_crow_state_latest_completed_after_file_change_is_idle() -> None:
    """The bug: file_change followed by a completed agent_response
    used to return "processing" because the loop set state on the
    older file_change and continued. Should be idle — the most
    recent dispatch closed."""
    events = [_file_change(1), _agent_response(1)]
    assert ui_server._crow_state(events) == "idle"


def test_crow_state_failed_anywhere_is_error() -> None:
    """error wins over a later completed agent_response and over
    processing. Operator must see the failure."""
    events = [
        _file_change(1),
        _agent_response(1, status="failed"),
        _agent_response(2, status="completed"),
    ]
    assert ui_server._crow_state(events) == "error"


def test_crow_state_requires_human_anywhere_is_waiting() -> None:
    """waiting wins over a later completed response and over
    processing, but loses to error."""
    events = [
        _file_change(1),
        _agent_response(1, status="completed", requires_human=True),
        _agent_response(2, status="completed"),
    ]
    assert ui_server._crow_state(events) == "waiting"


def test_crow_state_most_recent_trigger_wins() -> None:
    """When error and waiting come from DIFFERENT events, the
    most-recent event determines the state. Operator sees the
    current condition, not historical noise. (When the same
    event triggers both, error wins — checked first per
    iteration.)"""
    # waiting at the tail (most-recent)
    events_waiting_tail = [
        _agent_response(1, status="failed"),
        _agent_response(2, status="completed", requires_human=True),
    ]
    assert ui_server._crow_state(events_waiting_tail) == "waiting"

    # error at the tail (most-recent)
    events_error_tail = [
        _agent_response(1, status="completed", requires_human=True),
        _agent_response(2, status="failed"),
    ]
    assert ui_server._crow_state(events_error_tail) == "error"

    # same event triggers both → error wins (status checked first)
    same_event = [
        _agent_response(1, status="failed", requires_human=True),
    ]
    assert ui_server._crow_state(same_event) == "error"


def test_crow_state_processing_when_latest_is_file_change_after_completed() -> None:
    """A new file_change AFTER a completed agent_response means a
    fresh dispatch is in flight — back to processing."""
    events = [
        _agent_response(1, status="completed"),
        _file_change(2),
    ]
    assert ui_server._crow_state(events) == "processing"


# ---------------------------------------------------------------------------
# _flight_route precedence (UI-6 — Live Map projection)
# ---------------------------------------------------------------------------
#
# Binding decisions confirmed by the operator before UI-6 implementation:
#
#   - Project the LATEST meaningful event. NO memory of older events.
#     NO invented recovery / delivery flight.
#   - file_change watcher / git_hook / git_event       → user → karasu
#   - file_change with controller_resubmit=true        → user → karasu
#     (operator scar; semantically User even though the controller
#     mechanically emits the resubmit)
#   - file_change with github_event / source=github_webhook
#                                                      → github → karasu
#   - file_change with router-assigned agent in flight
#     (dispatch.agent set + dispatch.status pending|dispatched)
#                                                      → karasu → <agent>
#   - agent_response (completed OR failed)             → <agent> → karasu
#   - human_decision                                   → user → karasu
#   - unknown / unmapped event types                   → None (parked)
#   - empty events                                     → None (parked)
#
# Pin #7 (Codex, UI-5 audit re-iteration): every visual state
# derived from /api/health MUST be covered by unit tests BEFORE
# the visual code lands. UI-5 shipped _crow_state without these
# and Codex caught the bug visually instead of structurally; UI-6
# pins the precedence here so the same regression cannot happen.


def _file_change_dispatch(
    idx: int = 1,
    *,
    agent: str | None = None,
    status: str | None = None,
    source: str = "watcher",
    controller_resubmit: bool = False,
    github_event: str | None = None,
) -> dict:
    """Build a projected file_change event for _flight_route tests.

    Mirrors ``_project_event``'s output shape so the tests exercise
    the same view model the projection feeds the UI."""
    return {
        "id": f"fc-{idx:03d}",
        "type": "file_change",
        "source": source,
        "path": f"src/foo_{idx}.py",
        "controller_resubmit": controller_resubmit,
        "github_event": github_event,
        "agent": agent,
        "status": status,
    }


def _agent_response_dispatch(
    idx: int = 1,
    *,
    agent: str | None = "claude_code",
    status: str = "completed",
    requires_human: bool = False,
) -> dict:
    return {
        "id": f"ar-{idx:03d}",
        "type": "agent_response",
        "agent": agent,
        "status": status,
        "requires_human": requires_human,
    }


def test_flight_route_empty_events_is_none() -> None:
    """No events on the bus → no flight. Surface parks the crow."""
    assert ui_server._flight_route([]) is None


def test_flight_route_latest_file_change_watcher_is_user_to_karasu() -> None:
    """A bare watcher file_change is the user editing the working
    tree. Crow flies into the watchtower from the user node."""
    events = [_file_change_dispatch(1, source="watcher")]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_latest_file_change_git_hook_is_user_to_karasu() -> None:
    """Git-hook source still routes from user — the operator drove
    the commit / push that fired the hook."""
    events = [_file_change_dispatch(1, source="git_hook")]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_latest_file_change_with_pending_dispatch_to_claude() -> None:
    """The router has assigned claude_code and the dispatch is
    pending. Outbound leg: karasu → claude."""
    events = [
        _file_change_dispatch(1, agent="claude_code", status="pending"),
    ]
    assert ui_server._flight_route(events) == ("karasu", "claude")


def test_flight_route_latest_file_change_with_dispatched_to_codex() -> None:
    """Same outbound leg semantics for the codex agent. Status
    ``dispatched`` (already on the wire) also counts as in-flight."""
    events = [
        _file_change_dispatch(1, agent="codex", status="dispatched"),
    ]
    assert ui_server._flight_route(events) == ("karasu", "codex")


def test_flight_route_file_change_with_completed_dispatch_falls_back_to_user() -> None:
    """A file_change carrying a dispatch.status="completed" should
    not fly outbound — the agent_response is the canonical inbound
    leg. Defensive: bus consumers that mirror the dispatch status
    onto the originating event must not flip the flight direction."""
    events = [
        _file_change_dispatch(1, agent="claude_code", status="completed"),
    ]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_file_change_with_unknown_agent_falls_back_to_user() -> None:
    """Unknown agent → no Karasu→agent route is invented. The
    file_change still routes user → karasu (the inbound is real)."""
    events = [
        _file_change_dispatch(1, agent="some_future_agent", status="pending"),
    ]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_latest_agent_response_claude_is_claude_to_karasu() -> None:
    """A response from claude_code lands as inbound: claude → karasu."""
    events = [_agent_response_dispatch(1, agent="claude_code")]
    assert ui_server._flight_route(events) == ("claude", "karasu")


def test_flight_route_latest_agent_response_codex_is_codex_to_karasu() -> None:
    events = [_agent_response_dispatch(1, agent="codex")]
    assert ui_server._flight_route(events) == ("codex", "karasu")


def test_flight_route_latest_agent_response_failed_still_routes_agent_to_karasu() -> None:
    """Failed responses still walk Agent → Karasu. Outcome is colour
    (_crow_state's job), not direction."""
    events = [
        _agent_response_dispatch(1, agent="claude_code", status="failed"),
    ]
    assert ui_server._flight_route(events) == ("claude", "karasu")


def test_flight_route_latest_agent_response_no_agent_is_none() -> None:
    """An agent_response without dispatch.agent (an edge case the
    bus shouldn't really produce) returns None rather than guessing."""
    events = [_agent_response_dispatch(1, agent=None)]
    assert ui_server._flight_route(events) is None


def test_flight_route_latest_agent_response_unknown_agent_is_none() -> None:
    """Unmapped agent identifier → no route invented."""
    events = [_agent_response_dispatch(1, agent="future_agent")]
    assert ui_server._flight_route(events) is None


def test_flight_route_latest_github_webhook_via_source_is_github_to_karasu() -> None:
    """source=github_webhook is enough to identify the inbound leg
    even if github_event is not populated on the projection."""
    events = [
        _file_change_dispatch(1, source="github_webhook"),
    ]
    assert ui_server._flight_route(events) == ("github", "karasu")


def test_flight_route_latest_github_webhook_via_github_event_field() -> None:
    """github_event presence is the canonical webhook marker.
    Tested independently of source so future bus refactors that
    move source labels do not silently break the projection."""
    events = [
        _file_change_dispatch(
            1, source="watcher", github_event="pull_request_review_comment"
        ),
    ]
    assert ui_server._flight_route(events) == ("github", "karasu")


def test_flight_route_latest_controller_resubmit_is_user_to_karasu() -> None:
    """Operator scar resubmit. Mechanically the controller emits;
    semantically the User. The map must show human intent entering
    the system, not a self-loop."""
    events = [
        _file_change_dispatch(
            1, source="controller", controller_resubmit=True
        ),
    ]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_latest_human_decision_is_user_to_karasu() -> None:
    events = [
        {"id": "hd-001", "type": "human_decision", "source": "telegram_chat"},
    ]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_latest_git_event_is_user_to_karasu() -> None:
    events = [
        {"id": "ge-001", "type": "git_event", "source": "git_hook"},
    ]
    assert ui_server._flight_route(events) == ("user", "karasu")


def test_flight_route_latest_unknown_event_type_is_none() -> None:
    """A future event type the projection does not know yet returns
    None. The crow stays parked rather than mis-routed."""
    events = [
        {"id": "x-001", "type": "future_event_type", "source": "watcher"},
    ]
    assert ui_server._flight_route(events) is None


def test_flight_route_only_consults_latest_event_no_memory() -> None:
    """A file_change followed by an agent_response → the inbound
    leg wins because the LATEST event is the response. The older
    file_change does NOT contaminate the route. This is the UI-5
    bug pattern (older event leaking into projection) pinned for
    UI-6."""
    events = [
        _file_change_dispatch(1, agent="claude_code", status="dispatched"),
        _agent_response_dispatch(1, agent="claude_code", status="completed"),
    ]
    assert ui_server._flight_route(events) == ("claude", "karasu")


def test_flight_route_new_file_change_after_completed_response() -> None:
    """A fresh file_change after a completed response → outbound
    leg again. The projection follows the latest event without
    stickiness."""
    events = [
        _agent_response_dispatch(1, agent="claude_code", status="completed"),
        _file_change_dispatch(2, agent="codex", status="pending"),
    ]
    assert ui_server._flight_route(events) == ("karasu", "codex")


def test_flight_route_resubmit_overrides_dispatch_assignment() -> None:
    """A controller_resubmit file_change that ALSO carries a router
    dispatch must show user → karasu. The operator-intent leg is
    the meaningful one to surface; the outbound leg appears on the
    next event when the dispatch actually fires its own update."""
    events = [
        _file_change_dispatch(
            1,
            source="controller",
            controller_resubmit=True,
            agent="claude_code",
            status="dispatched",
        ),
    ]
    assert ui_server._flight_route(events) == ("user", "karasu")


# ---------------------------------------------------------------------------
# /api/health surfaces _flight_route (UI-6 — additive field)
# ---------------------------------------------------------------------------


def test_api_health_includes_flight_field_when_events_present(
    ui_http: tuple[str, int]
) -> None:
    """The flight projection must reach the wire as
    ``{"source": ..., "target": ...}`` for the surface JS to pick
    up. Pinned end-to-end so a future projection change that
    forgets to expose ``flight`` regresses here, not visually."""
    host, port = ui_http
    event = {
        "id": "fc-001",
        "timestamp": "2026-05-04T10:00:00Z",
        "type": "file_change",
        "source": "watcher",
        "data": {"path": "src/foo.py", "classification": "code_change"},
        "dispatch": {},
        "response": {},
    }
    ui_server.EVENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    ui_server.EVENT_LOG.write_text(json.dumps(event) + "\n")

    status, body = _get(host, port, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["flight"] == {"source": "user", "target": "karasu"}


def test_api_health_flight_is_null_on_empty_bus(
    ui_http: tuple[str, int]
) -> None:
    """An empty bus returns ``flight: null`` — the surface uses
    null to park the crow rather than render a phantom route."""
    host, port = ui_http
    assert not ui_server.EVENT_LOG.exists()
    status, body = _get(host, port, "/api/health")
    assert status == 200
    payload = json.loads(body)
    assert payload["flight"] is None
