"""Tests for the GitHub webhook receiver — Phase 3+ chunk 4a.

Failure-mode coverage per ``docs/phase-3-plus-pre-mortem.md``:

- F-WH-1   HMAC verification (good / bad / missing header)
- F-WH-2   delivery dedup (idempotent on repeat)
- F-WH-3   resource leak on shutdown (start / stop without leak)
- F-WH-5   metadata round-trip (review-comment → file_change)
- F-WH-6   per-source-IP rate limiting (429 over threshold,
           per-IP isolation, runs before path check)
- F-WH-7   route boundary (only POST /webhook accepted)
- F-WH-8   payload DoS (oversize → 413; malformed JSON → 422; both
           BEFORE HMAC, no signing-key timing leak)
- F-WH-9   missing or short secret → fail-closed (handler + cmd_serve)
- F-WH-10  dedup is in-memory (declared)
- F-A2A-5  /.well-known/agent-card.json reserved (POST → 405,
           GET → 404 in chunk 4a; 4b adds the GET handler)

F-WH-4 (loop amplification) holds trivially because the receiver
doesn't trigger /correct or /scar.
"""

from __future__ import annotations

import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from hashlib import sha256
from pathlib import Path

import pytest

from karasu.controller import LoopController
from karasu.controller.sources.webhook import (
    DEFAULT_DEDUP_RING_SIZE,
    DEFAULT_MAX_BODY_BYTES,
    MIN_SECRET_LENGTH,
    WebhookConfigError,
    WebhookHandler,
    WebhookSource,
    build_webhook_source,
)
from karasu.eventbus import Event, JsonlEventBus

VALID_SECRET = b"a-super-secret-key-of-at-least-16b"


def _sign(body: bytes, secret: bytes = VALID_SECRET) -> str:
    return "sha256=" + hmac.new(secret, body, sha256).hexdigest()


def _review_comment_payload(
    *,
    path: str = "src/foo.py",
    pr_number: int = 7,
    repo: str = "vdp89/karasu-",
    author: str = "vdp89",
    body: str = "review me",
) -> bytes:
    return json.dumps(
        {
            "action": "created",
            "comment": {
                "id": 12345,
                "path": path,
                "user": {"login": author},
                "body": body,
            },
            "pull_request": {"number": pr_number},
            "repository": {"full_name": repo},
        }
    ).encode("utf-8")


def _headers(
    body: bytes,
    *,
    event: str = "pull_request_review_comment",
    delivery: str = "delivery-1",
    sign: bool = True,
    signature: str | None = None,
) -> dict[str, str]:
    return {
        "content-length": str(len(body)),
        "x-github-event": event,
        "x-github-delivery": delivery,
        "x-hub-signature-256": signature
        if signature is not None
        else (_sign(body) if sign else "sha256=" + "0" * 64),
    }


# ---------------------------------------------------------------------------
# F-WH-9 — fail-closed on bad secret
# ---------------------------------------------------------------------------


def test_handler_rejects_missing_secret() -> None:
    with pytest.raises(WebhookConfigError, match="at least"):
        WebhookHandler(secret=b"")


def test_handler_rejects_short_secret() -> None:
    with pytest.raises(WebhookConfigError, match="at least"):
        WebhookHandler(secret=b"too-short")


def test_handler_accepts_secret_at_minimum_length() -> None:
    secret = b"x" * MIN_SECRET_LENGTH
    handler = WebhookHandler(secret=secret)
    assert handler is not None


# ---------------------------------------------------------------------------
# F-WH-7 — route boundary
# ---------------------------------------------------------------------------


def test_handler_rejects_non_webhook_path() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    status, _, event = handler.handle(
        "/.well-known/agent-card.json", "GET", _headers(body), body
    )
    assert status == 404
    assert event is None


def test_handler_rejects_non_post_method_on_webhook() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    status, _, event = handler.handle("/webhook", "GET", _headers(body), body)
    assert status == 405
    assert event is None


# ---------------------------------------------------------------------------
# F-WH-8 — payload / body DoS, ordering before HMAC
# ---------------------------------------------------------------------------


def test_handler_rejects_oversize_body_with_413_before_hmac() -> None:
    handler = WebhookHandler(secret=VALID_SECRET, max_body_bytes=100)
    body = b"x" * 200
    # Signature is intentionally bogus — proves the size check
    # rejects 413 BEFORE the HMAC verify (which would have
    # returned 401).
    status, _, event = handler.handle(
        "/webhook",
        "POST",
        {
            "content-length": "200",
            "x-hub-signature-256": "sha256=" + "0" * 64,
        },
        body,
    )
    assert status == 413
    assert event is None


def test_handler_rejects_malformed_json_with_422_before_hmac() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = b"not json {"
    status, _, event = handler.handle(
        "/webhook",
        "POST",
        {
            "content-length": str(len(body)),
            "x-hub-signature-256": "sha256=" + "0" * 64,
        },
        body,
    )
    assert status == 422
    assert event is None


def test_handler_rejects_non_object_json_with_422() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = b"[1, 2, 3]"
    status, _, event = handler.handle(
        "/webhook",
        "POST",
        {
            "content-length": str(len(body)),
            "x-hub-signature-256": "sha256=" + "0" * 64,
        },
        body,
    )
    assert status == 422
    assert event is None


def test_handler_rejects_missing_content_length_with_411() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    status, _, _ = handler.handle(
        "/webhook",
        "POST",
        {"x-hub-signature-256": _sign(body)},
        body,
    )
    assert status == 411


def test_handler_rejects_content_length_mismatch_with_411() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    headers = {
        "content-length": str(len(body) + 100),  # lies
        "x-hub-signature-256": _sign(body),
    }
    status, _, _ = handler.handle("/webhook", "POST", headers, body)
    assert status == 411


# ---------------------------------------------------------------------------
# F-WH-1 — HMAC verification
# ---------------------------------------------------------------------------


def test_handler_accepts_valid_signature() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    status, _, event = handler.handle(
        "/webhook", "POST", _headers(body), body
    )
    assert status == 200
    assert event is not None
    assert event.type == "file_change"


def test_handler_rejects_invalid_signature_with_401() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    status, _, event = handler.handle(
        "/webhook",
        "POST",
        _headers(body, signature="sha256=" + "0" * 64),
        body,
    )
    assert status == 401
    assert event is None


def test_handler_rejects_missing_signature_header_with_401() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    headers = {"content-length": str(len(body))}
    status, _, event = handler.handle("/webhook", "POST", headers, body)
    assert status == 401
    assert event is None


def test_handler_rejects_signature_with_wrong_prefix() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    raw_hex = hmac.new(VALID_SECRET, body, sha256).hexdigest()
    # Right hex, wrong prefix (sha1 instead of sha256).
    status, _, _ = handler.handle(
        "/webhook",
        "POST",
        _headers(body, signature="sha1=" + raw_hex),
        body,
    )
    assert status == 401


# ---------------------------------------------------------------------------
# F-WH-2 — delivery dedup
# ---------------------------------------------------------------------------


def test_handler_dedup_returns_200_on_repeat_delivery() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()
    headers = _headers(body, delivery="dup-1")

    status1, _, event1 = handler.handle("/webhook", "POST", headers, body)
    status2, _, event2 = handler.handle("/webhook", "POST", headers, body)

    assert status1 == 200
    assert event1 is not None
    assert status2 == 200
    assert event2 is None  # no event re-emitted


def test_handler_dedup_does_not_collide_across_delivery_ids() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload()

    s1, _, e1 = handler.handle(
        "/webhook", "POST", _headers(body, delivery="d-1"), body
    )
    s2, _, e2 = handler.handle(
        "/webhook", "POST", _headers(body, delivery="d-2"), body
    )

    assert s1 == 200 and e1 is not None
    assert s2 == 200 and e2 is not None  # different delivery id, fires again


def test_handler_dedup_evicts_oldest_when_ring_fills() -> None:
    handler = WebhookHandler(secret=VALID_SECRET, dedup_ring_size=2)
    body = _review_comment_payload()

    handler.handle("/webhook", "POST", _headers(body, delivery="a"), body)
    handler.handle("/webhook", "POST", _headers(body, delivery="b"), body)
    # Ring is full; "c" pushes "a" out.
    handler.handle("/webhook", "POST", _headers(body, delivery="c"), body)

    # "a" is no longer in the ring; replay fires fresh.
    _, _, event = handler.handle(
        "/webhook", "POST", _headers(body, delivery="a"), body
    )
    assert event is not None


# ---------------------------------------------------------------------------
# F-WH-5 — event mapping (review_comment → file_change with metadata)
# ---------------------------------------------------------------------------


def test_handler_maps_review_comment_created_to_file_change() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = _review_comment_payload(
        path="src/karasu/__main__.py",
        pr_number=42,
        repo="vdp89/karasu-",
        author="alice",
        body="please rename this",
    )
    _, _, event = handler.handle("/webhook", "POST", _headers(body), body)

    assert event is not None
    assert event.source == "github_webhook"
    assert event.data["path"] == "src/karasu/__main__.py"
    assert event.data["change_type"] == "review_comment"
    assert event.data["github_event"] == "pull_request_review_comment"
    assert event.data["github_action"] == "created"
    assert event.data["github_pr"] == 42
    assert event.data["github_repo"] == "vdp89/karasu-"
    assert event.data["github_comment_id"] == 12345
    assert event.data["github_author"] == "alice"
    assert event.data["github_body"] == "please rename this"


def test_handler_other_event_types_ack_without_event() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = json.dumps({"action": "opened"}).encode("utf-8")
    status, _, event = handler.handle(
        "/webhook",
        "POST",
        _headers(body, event="pull_request"),
        body,
    )
    assert status == 200
    assert event is None  # not mapped in chunk 4a


def test_handler_other_action_acks_without_event() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = json.dumps(
        {"action": "edited", "comment": {"path": "foo.py"}}
    ).encode("utf-8")
    status, _, event = handler.handle("/webhook", "POST", _headers(body), body)
    assert status == 200
    assert event is None  # F-HANDOFF-6: edited / deleted are no-op


def test_handler_review_comment_without_path_acks_without_event() -> None:
    handler = WebhookHandler(secret=VALID_SECRET)
    body = json.dumps(
        {"action": "created", "comment": {"id": 1, "user": {}, "body": ""}}
    ).encode("utf-8")
    status, _, event = handler.handle("/webhook", "POST", _headers(body), body)
    assert status == 200
    assert event is None  # F-HANDOFF-6: missing path → no-op


# ---------------------------------------------------------------------------
# F-WH-3 — lifecycle (start / stop, no port leak)
# ---------------------------------------------------------------------------


def _build_source(
    bus: JsonlEventBus, submitted: list[Event], port: int = 0
) -> WebhookSource:
    return build_webhook_source(
        secret=VALID_SECRET.decode("utf-8"),
        bus=bus,
        submit=submitted.append,
        host="127.0.0.1",
        port=port,
    )


def test_source_start_stop_releases_port(bus: JsonlEventBus) -> None:
    submitted: list[Event] = []
    source = _build_source(bus, submitted, port=0)
    source.start()
    address = source.address
    assert address is not None
    assert source._thread is not None and source._thread.is_alive()

    source.stop()
    assert source._server is None
    assert source._thread is None

    # Restarting on the same port (chosen ephemeral) should work
    # because stop() called server_close().
    source._port = address[1]
    source.start()
    try:
        assert source._thread is not None and source._thread.is_alive()
    finally:
        source.stop()


def test_source_stop_is_idempotent(bus: JsonlEventBus) -> None:
    submitted: list[Event] = []
    source = _build_source(bus, submitted)
    source.stop()  # never started — must not raise
    source.start()
    source.stop()
    source.stop()


# ---------------------------------------------------------------------------
# End-to-end live HTTP — webhook → bus → submit
# ---------------------------------------------------------------------------


def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    req = urllib.request.Request(
        url, data=body, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_source_end_to_end_post_appends_event_to_bus(
    bus: JsonlEventBus,
) -> None:
    submitted: list[Event] = []
    source = _build_source(bus, submitted, port=0)
    source.start()
    try:
        host, port = source.address
        body = _review_comment_payload(path="src/x.py")
        headers = {
            "Content-Length": str(len(body)),
            "Content-Type": "application/json",
            "X-GitHub-Event": "pull_request_review_comment",
            "X-GitHub-Delivery": "live-1",
            "X-Hub-Signature-256": _sign(body),
        }
        status = _post(f"http://{host}:{port}/webhook", body, headers)
        assert status == 200

        # Wait for the request handler to finish appending.
        deadline = time.monotonic() + 2.0
        while not submitted and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(submitted) == 1
        assert submitted[0].source == "github_webhook"
        assert submitted[0].data["path"] == "src/x.py"

        bus_events = list(bus.read())
        assert any(e.id == submitted[0].id for e in bus_events)
    finally:
        source.stop()


def test_source_end_to_end_rejects_bad_signature_with_401(
    bus: JsonlEventBus,
) -> None:
    submitted: list[Event] = []
    source = _build_source(bus, submitted, port=0)
    source.start()
    try:
        host, port = source.address
        body = _review_comment_payload()
        headers = {
            "Content-Length": str(len(body)),
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
        }
        status = _post(f"http://{host}:{port}/webhook", body, headers)
        assert status == 401
        assert submitted == []
    finally:
        source.stop()


# ---------------------------------------------------------------------------
# Integration with LoopController as a registered TriggerSource
# ---------------------------------------------------------------------------


def test_source_works_as_registered_trigger_source(
    bus: JsonlEventBus,
) -> None:
    seen: list[Event] = []
    controller = LoopController(seen.append)
    source = build_webhook_source(
        secret=VALID_SECRET.decode("utf-8"),
        bus=bus,
        submit=controller.submit,
        host="127.0.0.1",
        port=0,
    )
    controller.add_source(source)
    controller.start()
    try:
        host, port = source.address
        body = _review_comment_payload(path="src/y.py")
        headers = {
            "Content-Length": str(len(body)),
            "X-GitHub-Event": "pull_request_review_comment",
            "X-GitHub-Delivery": "live-2",
            "X-Hub-Signature-256": _sign(body),
        }
        assert _post(f"http://{host}:{port}/webhook", body, headers) == 200

        deadline = time.monotonic() + 2.0
        while not seen and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(seen) == 1
        assert seen[0].data["path"] == "src/y.py"
    finally:
        controller.stop()


# ---------------------------------------------------------------------------
# F-WH-6 — per-source-IP rate limiting (audit-required)
# ---------------------------------------------------------------------------


def test_handler_rate_limit_returns_429_above_threshold() -> None:
    handler = WebhookHandler(secret=VALID_SECRET, rate_limit_per_minute=3)
    body = _review_comment_payload()

    # First three from one IP go through (200 with event).
    for i in range(3):
        status, _, _ = handler.handle(
            "/webhook",
            "POST",
            _headers(body, delivery=f"d-{i}"),
            body,
            source_ip="1.2.3.4",
        )
        assert status == 200

    # Fourth from the SAME IP gets capped with 429 BEFORE any other
    # check. Body and signature both still valid; the rate limit
    # decides regardless.
    status, response_body, event = handler.handle(
        "/webhook",
        "POST",
        _headers(body, delivery="d-3"),
        body,
        source_ip="1.2.3.4",
    )
    assert status == 429
    assert b"too many requests" in response_body
    assert event is None


def test_handler_rate_limit_isolates_per_source_ip() -> None:
    handler = WebhookHandler(secret=VALID_SECRET, rate_limit_per_minute=2)
    body = _review_comment_payload()

    # IP A consumes its full bucket.
    handler.handle(
        "/webhook", "POST", _headers(body, delivery="a-1"), body,
        source_ip="1.1.1.1",
    )
    handler.handle(
        "/webhook", "POST", _headers(body, delivery="a-2"), body,
        source_ip="1.1.1.1",
    )
    status_a, _, _ = handler.handle(
        "/webhook", "POST", _headers(body, delivery="a-3"), body,
        source_ip="1.1.1.1",
    )
    assert status_a == 429

    # IP B has its own fresh bucket.
    status_b, _, event_b = handler.handle(
        "/webhook", "POST", _headers(body, delivery="b-1"), body,
        source_ip="2.2.2.2",
    )
    assert status_b == 200
    assert event_b is not None


def test_handler_rate_limit_runs_before_path_check() -> None:
    """F-WH-6 ordering: rate limit caps cost regardless of path.

    Even a request to an unknown path counts toward the bucket.
    Otherwise an attacker could path-scan unbounded.
    """
    handler = WebhookHandler(secret=VALID_SECRET, rate_limit_per_minute=2)
    handler.handle(
        "/", "GET", {"content-length": "0"}, b"", source_ip="9.9.9.9"
    )
    handler.handle(
        "/foo", "GET", {"content-length": "0"}, b"", source_ip="9.9.9.9"
    )
    status, _, _ = handler.handle(
        "/bar", "GET", {"content-length": "0"}, b"", source_ip="9.9.9.9"
    )
    assert status == 429


def test_handler_rate_limit_disabled_when_none() -> None:
    """``rate_limit_per_minute=None`` disables the limiter entirely.

    Used by tests that need to make many requests; production callers
    should always set a positive limit.
    """
    handler = WebhookHandler(secret=VALID_SECRET, rate_limit_per_minute=None)
    body = _review_comment_payload()
    for i in range(50):
        status, _, _ = handler.handle(
            "/webhook",
            "POST",
            _headers(body, delivery=f"unbounded-{i}"),
            body,
            source_ip="3.3.3.3",
        )
        assert status == 200


def test_handler_rate_limit_rejects_zero_or_negative() -> None:
    with pytest.raises(ValueError, match="positive"):
        WebhookHandler(secret=VALID_SECRET, rate_limit_per_minute=0)
    with pytest.raises(ValueError, match="positive"):
        WebhookHandler(secret=VALID_SECRET, rate_limit_per_minute=-1)


# ---------------------------------------------------------------------------
# F-A2A-5 — explicit route boundary on /.well-known/agent-card.json
# ---------------------------------------------------------------------------


def test_handler_post_on_agent_card_path_returns_405() -> None:
    """Even before chunk 4b mounts the GET handler, POST on the
    reserved A2A path is method-not-allowed (NOT 404). This pins
    the route boundary so chunk 4b only has to add a GET handler
    without rewriting the boundary check."""
    handler = WebhookHandler(secret=VALID_SECRET)
    body = b'{"action": "created"}'
    status, _, event = handler.handle(
        "/.well-known/agent-card.json",
        "POST",
        {"content-length": str(len(body))},
        body,
    )
    assert status == 405
    assert event is None


def test_handler_get_on_agent_card_path_returns_404_in_chunk_4a() -> None:
    """Chunk 4a doesn't ship the GET handler yet; the path is
    reserved but unimplemented. Chunk 4b will replace this with the
    static AgentCard JSON."""
    handler = WebhookHandler(secret=VALID_SECRET)
    status, response_body, event = handler.handle(
        "/.well-known/agent-card.json",
        "GET",
        {"content-length": "0"},
        b"",
    )
    assert status == 404
    assert b"not implemented yet" in response_body
    assert event is None


def test_handler_get_on_webhook_returns_405() -> None:
    """Mirror of the agent-card boundary: GET on /webhook is also
    method-not-allowed for the resource."""
    handler = WebhookHandler(secret=VALID_SECRET)
    status, _, _ = handler.handle(
        "/webhook", "GET", {"content-length": "0"}, b""
    )
    assert status == 405


# ---------------------------------------------------------------------------
# cmd_serve fail-closed tests (NICE-TO-HAVE #2)
# ---------------------------------------------------------------------------


def test_cmd_serve_exits_2_when_secret_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    """F-WH-9: missing KARASU_WEBHOOK_SECRET → exit 2 BEFORE any
    port is bound. Verified through ``main`` so we exercise the
    real fail-closed path."""
    monkeypatch.delenv("KARASU_WEBHOOK_SECRET", raising=False)
    monkeypatch.chdir(tmp_path)
    from karasu.__main__ import main

    rc = main(["serve", "--port", "0"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "KARASU_WEBHOOK_SECRET is not set" in err


def test_cmd_serve_exits_2_when_secret_empty(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("KARASU_WEBHOOK_SECRET", "")
    monkeypatch.chdir(tmp_path)
    from karasu.__main__ import main

    rc = main(["serve", "--port", "0"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "KARASU_WEBHOOK_SECRET is not set" in err


def test_cmd_serve_exits_2_when_secret_too_short(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys
) -> None:
    monkeypatch.setenv("KARASU_WEBHOOK_SECRET", "too-short")  # 9 bytes < 16
    monkeypatch.chdir(tmp_path)
    from karasu.__main__ import main

    rc = main(["serve", "--port", "0"])
    err = capsys.readouterr().err
    assert rc == 2
    assert "at least" in err
