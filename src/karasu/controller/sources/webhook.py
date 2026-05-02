"""GitHub webhook receiver — Phase 3+ chunk 4a.

A long-running ``TriggerSource`` that accepts GitHub webhook
POSTs, verifies them, dedups by ``X-GitHub-Delivery``, and
translates supported event types into ``file_change`` events on
the bus. Plugs into :class:`LoopController` like any other source.

The webhook receiver is one-way GitHub → bus. It does NOT respond
to GitHub with anything beyond HTTP status. No auto-comments, no
PR mutations, no token-based GitHub operations. Surface contract
holds: this is a producer, not an orchestrator.

The handler logic (HMAC, body size, JSON parse, dedup, mapping)
lives in :class:`WebhookHandler` as a pure object so tests can
exercise it without binding a port. :class:`WebhookSource` is the
thin HTTP transport on top.

See ``docs/phase-3-plus-pre-mortem.md`` chunk 4a for the contract
and failure modes (F-WH-1..F-WH-10).
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
from collections import deque
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable

from karasu.eventbus import Event, JsonlEventBus

_log = logging.getLogger(__name__)

# F-WH-9: secrets shorter than this are rejected at startup. 16 bytes
# is the minimum useful length for HMAC-SHA256 signing keys; shorter
# values almost always indicate a misconfiguration.
MIN_SECRET_LENGTH = 16

# F-WH-8: Content-Length cap. GitHub's own webhook docs cap delivery
# bodies at 25 MB, but for a single-operator MVP 1 MiB covers every
# realistic event we map (review comments, PR metadata). Operators
# raise it via the constructor if their workflow needs more.
DEFAULT_MAX_BODY_BYTES = 1 * 1024 * 1024

# F-WH-2: in-memory dedup ring. Sized to a typical busy-day delivery
# count for a small project; larger projects can configure higher.
# Per F-WH-10: NOT persisted across restart. GitHub does not retry
# on 200 responses, so post-restart re-delivery is a narrow window.
DEFAULT_DEDUP_RING_SIZE = 1024


class WebhookConfigError(ValueError):
    """Raised when the receiver is constructed with an unsafe config.

    F-WH-9 (audit): startup must fail closed if the HMAC secret is
    missing, empty, or shorter than ``MIN_SECRET_LENGTH``. Catching
    this lets ``cmd_serve`` exit with a clean status code instead of
    letting a stack trace through.
    """


class WebhookHandler:
    """Pure GitHub-webhook request handler.

    No HTTP, no sockets — just bytes in, ``(status, body, event)``
    out. The HTTP transport lives in :class:`WebhookSource`.

    Order of checks is intentional (F-WH-8 audit):

    1. Body size (Content-Length header) — reject 413 BEFORE reading
       the body so a hostile peer can't drain memory.
    2. JSON parse — reject 422 on malformed bodies.
    3. HMAC verify — constant-time comparison; 401 on mismatch.

    Steps 1 and 2 happen before the HMAC check intentionally so the
    rejection latency cannot leak signing-key timing.
    """

    def __init__(
        self,
        secret: bytes,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        dedup_ring_size: int = DEFAULT_DEDUP_RING_SIZE,
    ) -> None:
        if not secret or len(secret) < MIN_SECRET_LENGTH:
            raise WebhookConfigError(
                f"webhook secret must be at least {MIN_SECRET_LENGTH} bytes; "
                f"got {len(secret) if secret else 0}"
            )
        self._secret = secret
        self._max_body_bytes = max_body_bytes
        self._delivered: deque[str] = deque(maxlen=dedup_ring_size)
        self._delivered_set: set[str] = set()
        self._lock = threading.Lock()

    def handle(
        self,
        path: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
    ) -> tuple[int, bytes, Event | None]:
        """Process one request.

        Returns ``(status_code, response_body, file_change_event_or_None)``.
        Caller writes status + body to the wire and (if event is not
        None) submits the event to the controller.
        """
        # F-A2A-5: enforce route boundary. Only POST /webhook is
        # accepted in chunk 4a. Other paths/methods get 405; chunk 4b
        # will add GET /.well-known/agent-card.json without breaking
        # this guard because that's a different path.
        if path != "/webhook":
            return 404, b"not found\n", None
        if method != "POST":
            return 405, b"method not allowed\n", None

        # F-WH-8 (1/3): Content-Length BEFORE anything else.
        try:
            declared_len = int(headers.get("content-length", "0"))
        except ValueError:
            return 411, b"content-length required\n", None
        if declared_len > self._max_body_bytes:
            return 413, b"payload too large\n", None
        if declared_len != len(body):
            return 411, b"content-length mismatch\n", None

        # F-WH-8 (2/3): JSON parse BEFORE HMAC. Malformed bodies
        # never reach the verifier.
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return 422, b"malformed json\n", None
        if not isinstance(payload, dict):
            return 422, b"json body must be an object\n", None

        # F-WH-8 (3/3) + F-WH-1: HMAC verify with constant-time compare.
        signature = headers.get("x-hub-signature-256", "")
        if not self._verify_signature(body, signature):
            return 401, b"signature mismatch\n", None

        # F-WH-2 + F-WH-10: delivery dedup. Repeats are 200 no-op so
        # GitHub doesn't retry; the file_change is NOT re-emitted.
        delivery_id = headers.get("x-github-delivery", "")
        if delivery_id and self._is_duplicate(delivery_id):
            return 200, b"duplicate delivery\n", None
        if delivery_id:
            self._record_delivery(delivery_id)

        # F-WH-5: lossy mapping mitigation. Only one event type maps
        # in chunk 4a; everything else acks 200 with no event so the
        # operator can extend mapping later without breaking GitHub's
        # delivery success metric.
        event_type = headers.get("x-github-event", "")
        action = payload.get("action", "")
        file_change = self._map_event(event_type, action, payload)
        if file_change is None:
            return 200, b"event accepted, no mapping\n", None
        return 200, b"event accepted\n", file_change

    def _verify_signature(self, body: bytes, header_value: str) -> bool:
        if not header_value.startswith("sha256="):
            return False
        expected = hmac.new(self._secret, body, sha256).hexdigest()
        provided = header_value[len("sha256=") :]
        return hmac.compare_digest(expected, provided)

    def _is_duplicate(self, delivery_id: str) -> bool:
        with self._lock:
            return delivery_id in self._delivered_set

    def _record_delivery(self, delivery_id: str) -> None:
        with self._lock:
            if len(self._delivered) == self._delivered.maxlen:
                evicted = self._delivered[0]
                self._delivered_set.discard(evicted)
            self._delivered.append(delivery_id)
            self._delivered_set.add(delivery_id)

    @staticmethod
    def _map_event(
        event_type: str, action: str, payload: dict
    ) -> Event | None:
        """Translate a supported GitHub event into a ``file_change``.

        Chunk 4a maps ``pull_request_review_comment.created`` only.
        Other event types ack 200 without producing a bus event.
        """
        if event_type != "pull_request_review_comment":
            return None
        if action != "created":
            return None
        comment = payload.get("comment") or {}
        pr = payload.get("pull_request") or {}
        repo = payload.get("repository") or {}
        path = comment.get("path")
        if not path:
            return None
        return Event(
            type="file_change",
            source="github_webhook",
            data={
                "path": path,
                "change_type": "review_comment",
                "github_event": event_type,
                "github_action": action,
                "github_pr": pr.get("number"),
                "github_repo": repo.get("full_name"),
                "github_comment_id": comment.get("id"),
                "github_author": (comment.get("user") or {}).get("login"),
                "github_body": comment.get("body", ""),
            },
        )


class WebhookSource:
    """``TriggerSource`` wrapping :class:`WebhookHandler` with HTTP transport.

    Lifecycle:
    - ``start()`` binds the listener (host, port from constructor),
      spawns a daemon thread serving requests via
      ``http.server.ThreadingHTTPServer``.
    - ``stop()`` calls ``shutdown()`` + ``server_close()`` and joins
      the thread. Idempotent.
    """

    def __init__(
        self,
        handler: WebhookHandler,
        bus: JsonlEventBus,
        submit: Callable[[Event], None],
        host: str = "127.0.0.1",
        port: int = 8080,
    ) -> None:
        self._handler = handler
        self._bus = bus
        self._submit = submit
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._server is not None:
            return
        handler_factory = _make_request_handler_class(
            self._handler, self._bus, self._submit
        )
        self._server = ThreadingHTTPServer(
            (self._host, self._port), handler_factory
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="karasu-webhook",
            daemon=True,
        )
        self._thread.start()
        _log.info(
            "webhook receiver listening on http://%s:%d/webhook",
            self._host,
            self._server.server_address[1],
        )

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            if self._thread.is_alive():
                _log.warning(
                    "webhook receiver thread did not exit within 5.0s; "
                    "abandoning."
                )
        self._server = None
        self._thread = None

    @property
    def address(self) -> tuple[str, int] | None:
        """Bound (host, port) — useful for tests with ``port=0``."""
        if self._server is None:
            return None
        return self._server.server_address[:2]


def _make_request_handler_class(
    handler: WebhookHandler,
    bus: JsonlEventBus,
    submit: Callable[[Event], None],
) -> type[BaseHTTPRequestHandler]:
    """Build a request-handler class closed over the application
    state.

    ``http.server`` instantiates the handler per-request; closing
    over the application state via this factory keeps the request
    handler stateless.
    """

    class _RequestHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 — http.server convention
            self._dispatch("POST")

        def do_GET(self) -> None:  # noqa: N802
            self._dispatch("GET")

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            # Route http.server's stderr noise through the package logger.
            _log.debug("webhook %s - " + format, self.address_string(), *args)

        def _dispatch(self, method: str) -> None:
            length = 0
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            # Cap the read at the handler's max + 1 so an obviously
            # oversized body never gets fully buffered.
            read_cap = handler._max_body_bytes + 1
            body = self.rfile.read(min(length, read_cap)) if length > 0 else b""
            request_headers = {k.lower(): v for k, v in self.headers.items()}
            status, response_body, event = handler.handle(
                self.path, method, request_headers, body
            )
            self.send_response(status)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(response_body)
            if event is not None:
                appended = bus.append(event)
                try:
                    submit(appended)
                except Exception:
                    _log.exception(
                        "webhook submit failed for event %s", appended.id
                    )

    return _RequestHandler


def build_webhook_source(
    *,
    secret: str,
    bus: JsonlEventBus,
    submit: Callable[[Event], None],
    host: str = "127.0.0.1",
    port: int = 8080,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    dedup_ring_size: int = DEFAULT_DEDUP_RING_SIZE,
) -> WebhookSource:
    """Construct a :class:`WebhookSource` end-to-end.

    Raises :class:`WebhookConfigError` if the secret is unsafe.
    Used by ``cmd_serve``; tests usually build the pieces by hand.
    """
    handler = WebhookHandler(
        secret=secret.encode("utf-8") if isinstance(secret, str) else secret,
        max_body_bytes=max_body_bytes,
        dedup_ring_size=dedup_ring_size,
    )
    return WebhookSource(
        handler=handler,
        bus=bus,
        submit=submit,
        host=host,
        port=port,
    )


__all__: Iterable[str] = (
    "WebhookHandler",
    "WebhookSource",
    "WebhookConfigError",
    "build_webhook_source",
    "DEFAULT_MAX_BODY_BYTES",
    "DEFAULT_DEDUP_RING_SIZE",
    "MIN_SECRET_LENGTH",
)
