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
