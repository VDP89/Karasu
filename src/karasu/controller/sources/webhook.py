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
import time
from collections import deque
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING, Callable, Iterable

from karasu.eventbus import Event, JsonlEventBus

if TYPE_CHECKING:
    from karasu.a2a import AgentCard

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

# F-WH-6: per-source-IP rate limit. Sliding-window token bucket.
# Defaults sized for a small project; operators tune via the
# WebhookHandler constructor (or pass ``rate_limit_per_minute=None``
# to disable for tests / trusted networks).
DEFAULT_RATE_LIMIT_PER_MINUTE = 60
# Cleanup empty buckets when the dict grows past this — bounds
# memory under path-scan / IP-spoof attacks. Cheap dict scan.
_RATE_LIMIT_CLEANUP_THRESHOLD = 1024


class _RateLimiter:
    """Per-source-IP sliding-window rate limiter.

    F-WH-6 mitigation. Each ``allow(source_ip)`` call records the
    current monotonic time in that IP's deque, drops entries older
    than ``window_seconds``, and returns ``False`` if the bucket
    is full. Thread-safe; the HTTP server is multi-threaded.
    """

    def __init__(
        self,
        max_per_window: int,
        window_seconds: float = 60.0,
    ) -> None:
        if max_per_window <= 0:
            raise ValueError(
                f"rate limit must be positive; got {max_per_window}"
            )
        self._max = max_per_window
        self._window = window_seconds
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, source_ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._buckets) > _RATE_LIMIT_CLEANUP_THRESHOLD:
                self._cleanup_locked(now)
            bucket = self._buckets.setdefault(source_ip, deque())
            # Drop entries that fell out of the window.
            cutoff = now - self._window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True

    def _cleanup_locked(self, now: float) -> None:
        # Caller holds the lock. Drop buckets whose newest entry has
        # already aged out — those IPs haven't sent in over ``window``.
        cutoff = now - self._window
        stale = [
            ip
            for ip, bucket in self._buckets.items()
            if not bucket or bucket[-1] <= cutoff
        ]
        for ip in stale:
            del self._buckets[ip]


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

    # F-A2A-5 (audit): /.well-known/agent-card.json is reserved for
    # chunk 4b. In chunk 4a the path is known to the receiver but not
    # yet implemented. Listed here so the route-boundary check can
    # answer 405 on POST (method-not-allowed for this resource) even
    # before chunk 4b mounts the GET handler.
    _AGENT_CARD_PATH = "/.well-known/agent-card.json"

    def __init__(
        self,
        secret: bytes,
        max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
        dedup_ring_size: int = DEFAULT_DEDUP_RING_SIZE,
        rate_limit_per_minute: int | None = DEFAULT_RATE_LIMIT_PER_MINUTE,
        agent_card_json: bytes | None = None,
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
        # Chunk 4b: optional pre-serialised AgentCard JSON. When set,
        # GET /.well-known/agent-card.json returns 200 with this body.
        # When None, we keep the chunk-4a placeholder (404 "not
        # implemented yet") so the route boundary is still pinned but
        # operators who don't want to publish a card can opt out.
        self._agent_card_json = agent_card_json
        # F-WH-6: rate limiter. ``None`` disables (used by tests that
        # need to make many requests; production always sets a limit).
        self._rate_limiter: _RateLimiter | None = (
            _RateLimiter(rate_limit_per_minute)
            if rate_limit_per_minute is not None
            else None
        )

    def handle(
        self,
        path: str,
        method: str,
        headers: dict[str, str],
        body: bytes,
        source_ip: str = "0.0.0.0",
    ) -> tuple[int, bytes, Event | None]:
        """Process one request.

        Returns ``(status_code, response_body, file_change_event_or_None)``.
        Caller writes status + body to the wire and (if event is not
        None) submits the event to the controller. Caller passes the
        peer's source IP so the rate limiter (F-WH-6) can bucket
        per-origin.
        """
        # F-WH-6: per-source-IP rate limit. Runs FIRST, before any
        # path / method / body / signing work, so a flood from a
        # single peer cannot drain CPU on the verifier path.
        if self._rate_limiter is not None and not self._rate_limiter.allow(
            source_ip
        ):
            return 429, b"too many requests\n", None

        # F-A2A-5: enforce route boundary. /webhook accepts POST only;
        # /.well-known/agent-card.json is reserved for chunk 4b — POST
        # there is method-not-allowed for the resource (405) even
        # though chunk 4a doesn't yet implement GET. Anything else is
        # 404. Chunk 4b adds the GET handler without changing this
        # guard.
        if path == "/webhook":
            if method != "POST":
                return 405, b"method not allowed\n", None
        elif path == self._AGENT_CARD_PATH:
            if method != "GET":
                return 405, b"method not allowed\n", None
            # Chunk 4b: serve the pre-serialised AgentCard JSON when
            # configured; fall back to the chunk-4a placeholder when
            # the operator opts out of publishing a card.
            if self._agent_card_json is not None:
                return 200, self._agent_card_json, None
            return 404, b"agent-card not configured\n", None
        else:
            return 404, b"not found\n", None

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
            # F-WH-6: pass the peer IP into the handler so the rate
            # limiter can bucket per-origin. ``client_address`` is
            # ``(host, port)`` per BaseHTTPRequestHandler.
            source_ip = (
                self.client_address[0] if self.client_address else "0.0.0.0"
            )
            status, response_body, event = handler.handle(
                self.path, method, request_headers, body, source_ip=source_ip
            )
            # Chunk 4b: serve the AgentCard JSON with the right
            # Content-Type so peers parse it without sniffing.
            # Other responses stay text/plain.
            content_type = (
                "application/json"
                if (
                    self.path == handler._AGENT_CARD_PATH
                    and method == "GET"
                    and status == 200
                )
                else "text/plain; charset=utf-8"
            )
            self.send_response(status)
            self.send_header("Content-Length", str(len(response_body)))
            self.send_header("Content-Type", content_type)
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
    rate_limit_per_minute: int | None = DEFAULT_RATE_LIMIT_PER_MINUTE,
    agent_card: "AgentCard | None" = None,
) -> WebhookSource:
    """Construct a :class:`WebhookSource` end-to-end.

    Raises :class:`WebhookConfigError` if the secret is unsafe.
    Used by ``cmd_serve``; tests usually build the pieces by hand.

    Chunk 4b: when ``agent_card`` is supplied the handler serves it
    on ``GET /.well-known/agent-card.json``. The card is serialised
    once at startup (per F-A2A-1: static snapshot, no runtime drift).
    """
    card_json: bytes | None = None
    if agent_card is not None:
        import json as _json

        card_json = _json.dumps(agent_card.to_dict(), indent=2).encode("utf-8")
    handler = WebhookHandler(
        secret=secret.encode("utf-8") if isinstance(secret, str) else secret,
        max_body_bytes=max_body_bytes,
        dedup_ring_size=dedup_ring_size,
        rate_limit_per_minute=rate_limit_per_minute,
        agent_card_json=card_json,
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
    "DEFAULT_RATE_LIMIT_PER_MINUTE",
    "MIN_SECRET_LENGTH",
)
