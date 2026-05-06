"""Outbound HTTP delivery to Web Push services.

Brief §3-E + §3-H + pin §11.6.16. The first proactive
outbound HTTP surface in Karasu — every other surface is
request/response.

Per-event flow:

  1. Look up the subscription in the store by endpoint_hash.
     If absent, the operator unsubscribed mid-debounce; log
     INFO "<hash> pruned before dispatch" and return.
  2. Compute the JWT audience from the subscription's
     endpoint origin. Look up / sign / cache the VAPID JWT
     for that origin (one cache entry per origin; 12 h
     refresh window per pin §11.6.15).
  3. Build the §3-H payload, encrypt via :mod:`._encryption`.
  4. POST the encrypted body with the Authorization,
     Content-Encoding, Content-Length, TTL, and Topic
     headers.
  5. Handle the response:
        201/200/204 → success. INFO log endpoint_hash only.
        410 / 404   → prune via push_store.remove_subscription
                       (no bus event emitted; pin §11.6.13).
        429         → honor Retry-After (or default 60 s);
                       set per-endpoint backoff; do NOT prune.
        5xx         → log WARNING; do NOT prune.
        4xx other   → log WARNING; do NOT prune.
        Transport   → log endpoint_hash + exception TYPE only;
        exception     NEVER log str/repr/exc_info/__cause__/
                       __context__/traceback.

Privacy pin §11.6.16 + §11.6.13:
  * The raw endpoint URL materialises ONLY as the outbound
    REQUEST TARGET URL. The body is RFC 8291 ciphertext.
  * Logs carry endpoint_hash + exception type. Never raw URL,
    never exception message, never exc_info.
  * 410/404 prune emits ZERO bus events.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from cryptography.hazmat.primitives.asymmetric import ec

from karasu.eventbus import Event
from karasu.push_emit._encryption import encrypt_payload
from karasu.push_emit._signing import (
    DEFAULT_EXP_SECONDS,
    audience_for,
    sign_vapid_jwt,
)
from karasu.ui.push_store import (
    PushStoreNotFound,
    _read_or_empty_store,
    remove_subscription,
)

_log = logging.getLogger(__name__)

# Brief §3-H title strings — closed enum, keyed by category.
_TITLES = {
    "attention": "Karasu paused — operator review needed.",
    "errors": "An adapter failed.",
    "corrections": "A scar was recorded out-of-band.",
}

# Brief §3-H push payload constants.
_ICON = "/assets/icons/karasu-192.png"
_BADGE = "/assets/icons/karasu-192.png"
_TAG = "karasu"  # singular: fresh push REPLACES pending notifications
_URL = "/"

# Brief §3-E binding: 60 s per-endpoint backoff on 429 when
# Retry-After is absent.
DEFAULT_BACKOFF_SECONDS = 60.0
DEFAULT_TTL_SECONDS = 60


@dataclass
class HttpResponse:
    """Lightweight HTTP response shape for the dispatcher.

    The HTTP client is injectable; tests pass a stub that
    constructs ``HttpResponse`` directly. Real transport uses
    :func:`_urllib_post` which adapts ``urllib.request``
    return values into this shape.
    """

    status: int
    headers: Mapping[str, str] = field(default_factory=dict)


# Type alias: the HTTP client signature. Returns an
# HttpResponse OR raises an exception (urllib.error.URLError,
# socket.timeout, etc.) for transport-level failures.
HttpPost = Callable[[str, bytes, Mapping[str, str], float], HttpResponse]


def _urllib_post(
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout: float,
) -> HttpResponse:
    """Stdlib HTTP POST via urllib.request.

    Adapts urllib's behaviour (raise HTTPError for non-2xx,
    return Response for 2xx) into a uniform HttpResponse so
    the dispatcher can branch on ``status`` consistently.
    """
    req = urllib.request.Request(url, data=body, method="POST")
    for name, value in headers.items():
        req.add_header(name, value)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return HttpResponse(
                status=resp.status,
                headers={k.lower(): v for k, v in resp.headers.items()},
            )
    except urllib.error.HTTPError as exc:
        # urllib raises HTTPError for non-2xx. Read the
        # status + headers for the dispatcher's error
        # handling. The body is intentionally NOT carried
        # forward (push services may include the endpoint URL
        # in error bodies).
        return HttpResponse(
            status=exc.code,
            headers={k.lower(): v for k, v in (exc.headers or {}).items()},
        )


@dataclass
class DispatcherConfig:
    """Persistent config for :class:`PushDispatcher`.

    The dispatcher constructs once on ``PushEmit.start()`` and
    runs for the lifetime of the watcher. The private key is
    loaded once at start; rotation requires a watcher restart
    (brief §10.4).
    """

    store_path: Path
    private_key: ec.EllipticCurvePrivateKey
    public_key_b64u: str
    subject: str
    ttl_seconds: int = DEFAULT_TTL_SECONDS
    request_timeout: float = 10.0


class PushDispatcher:
    """Outbound HTTP delivery + 410/404 prune for one watcher
    process.

    Shared state:
      * ``_jwt_cache`` — per-origin signed JWT + its exp claim.
        Reused across deliveries to the same push service for
        the lifetime of the JWT (pin §11.6.15).
      * ``_backoff_until`` — per-endpoint 429 backoff
        deadlines (monotonic). Cleared on successful dispatch.

    Threading: the dispatcher is invoked from the rate-limit
    timer thread, ONE call at a time per (endpoint_hash,
    category). Multiple categories CAN run in parallel for
    distinct timers, so the caches are guarded by a
    :class:`threading.Lock`.
    """

    def __init__(
        self,
        config: DispatcherConfig,
        *,
        http_post: HttpPost | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._http_post = http_post or _urllib_post
        self._monotonic = clock or time.monotonic
        self._jwt_cache: dict[str, tuple[str, int]] = {}
        self._backoff_until: dict[str, float] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    def dispatch(
        self,
        event: Event,
        endpoint_hash: str,
        category: str,
    ) -> None:
        """Deliver one push to the subscription matching
        ``endpoint_hash``.

        Multi-device fan-out is the responsibility of
        :class:`PushEmit` upstream — it iterates each
        subscription whose categories match the classified
        event and calls :meth:`dispatch` once per (subscription,
        category) tuple. The dispatcher itself handles a
        single (endpoint_hash, category) call.
        """
        subscription = self._lookup_subscription(endpoint_hash)
        if subscription is None:
            _log.info(
                "push_emit: %s pruned before dispatch", endpoint_hash
            )
            return

        # Per-endpoint 429 backoff check.
        now = self._monotonic()
        with self._lock:
            backoff_until = self._backoff_until.get(endpoint_hash)
        if backoff_until is not None and now < backoff_until:
            _log.warning(
                "push_emit: %s backoff active (%.1fs remaining); skipping",
                endpoint_hash,
                backoff_until - now,
            )
            return

        try:
            self._send(event, endpoint_hash, category, subscription)
        except urllib.error.URLError as exc:
            self._log_transport_failure(endpoint_hash, exc)
        except (TimeoutError, ConnectionError, OSError) as exc:
            self._log_transport_failure(endpoint_hash, exc)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _lookup_subscription(
        self, endpoint_hash: str
    ) -> dict[str, Any] | None:
        """Return the subscription dict whose endpoint hash
        matches, or ``None`` if absent / store empty."""
        store = _read_or_empty_store(self._config.store_path)
        subs = store.get("subscriptions")
        if not isinstance(subs, list):
            return None
        for entry in subs:
            if not isinstance(entry, dict):
                continue
            if entry.get("endpoint_hash") == endpoint_hash:
                return entry
        return None

    def _send(
        self,
        event: Event,
        endpoint_hash: str,
        category: str,
        subscription: dict[str, Any],
    ) -> None:
        endpoint = subscription["endpoint"]
        keys = subscription.get("keys") or {}
        p256dh_b64 = keys.get("p256dh")
        auth_b64 = keys.get("auth")
        if not isinstance(p256dh_b64, str) or not isinstance(auth_b64, str):
            _log.warning(
                "push_emit: %s subscription missing p256dh/auth; skipping",
                endpoint_hash,
            )
            return

        from base64 import urlsafe_b64decode

        def _b64u(s: str) -> bytes:
            return urlsafe_b64decode(s + "=" * (-len(s) % 4))

        try:
            p256dh = _b64u(p256dh_b64)
            auth = _b64u(auth_b64)
        except Exception:
            _log.warning(
                "push_emit: %s subscription keys not valid b64u; skipping",
                endpoint_hash,
            )
            return

        # JWT for the audience.
        audience = audience_for(endpoint)
        jwt = self._jwt_for_audience(audience)

        # Payload + encrypt.
        plaintext = self._build_payload(event, category)
        try:
            body = encrypt_payload(
                p256dh=p256dh, auth=auth, plaintext=plaintext
            )
        except ValueError as exc:
            # Defensive — payload size cap, bad keys, etc.
            _log.warning(
                "push_emit: %s encryption failed (%s); skipping",
                endpoint_hash,
                type(exc).__name__,
            )
            return

        headers = {
            "Authorization": f"vapid t={jwt}, k={self._config.public_key_b64u}",
            "Content-Encoding": "aes128gcm",
            "Content-Length": str(len(body)),
            "TTL": str(self._config.ttl_seconds),
            "Topic": category,
        }

        response = self._http_post(
            endpoint, body, headers, self._config.request_timeout
        )
        self._handle_response(response, endpoint_hash)

    def _build_payload(self, event: Event, category: str) -> bytes:
        """Serialise the §3-H push payload to UTF-8 bytes."""
        title = _TITLES.get(category, "Karasu")
        payload = {
            "title": title,
            "body": "",
            "icon": _ICON,
            "badge": _BADGE,
            "tag": _TAG,
            "data": {
                "url": _URL,
                "category": category,
                "event_id": event.id,
            },
            "silent": False,
            "requireInteraction": False,
        }
        return json.dumps(payload, separators=(",", ":")).encode("utf-8")

    def _jwt_for_audience(self, audience: str) -> str:
        """Cached VAPID JWT for ``audience``.

        Pin §11.6.15: cached per (origin, exp_window). A new
        JWT is signed when the cache is missing OR the cached
        JWT's ``exp`` claim is within 5 minutes of expiry.
        """
        margin = 5 * 60  # refresh 5 min before expiry
        with self._lock:
            cached = self._jwt_cache.get(audience)
            if cached is not None:
                jwt, exp = cached
                if time.time() + margin < exp:
                    return jwt

            jwt = sign_vapid_jwt(
                audience=audience,
                subject=self._config.subject,
                private_key=self._config.private_key,
            )
            # Recover the exp claim by re-parsing the claims
            # part — sign_vapid_jwt does not return it.
            from base64 import urlsafe_b64decode

            claims_b64 = jwt.split(".")[1]
            claims_raw = urlsafe_b64decode(
                claims_b64 + "=" * (-len(claims_b64) % 4)
            )
            claims = json.loads(claims_raw.decode("ascii"))
            exp = int(claims["exp"])
            self._jwt_cache[audience] = (jwt, exp)
            return jwt

    def _handle_response(
        self, response: HttpResponse, endpoint_hash: str
    ) -> None:
        status = response.status
        if 200 <= status < 300:
            _log.info("push_emit: dispatched %s (%d)", endpoint_hash, status)
            with self._lock:
                self._backoff_until.pop(endpoint_hash, None)
            return
        if status in (404, 410):
            self._prune(endpoint_hash, status)
            return
        if status == 429:
            self._record_backoff(endpoint_hash, response.headers)
            return
        # Other 4xx and 5xx: log + no-prune.
        _log.warning(
            "push_emit: %s push service returned %d (no prune)",
            endpoint_hash,
            status,
        )

    def _prune(self, endpoint_hash: str, status: int) -> None:
        """410 / 404 → remove subscription from store. ZERO bus
        events emitted (pin §11.6.13)."""
        # Look up the raw endpoint by hash (we re-read so the
        # remove call has the latest store).
        store = _read_or_empty_store(self._config.store_path)
        subs = store.get("subscriptions") or []
        endpoint: str | None = None
        for entry in subs:
            if (
                isinstance(entry, dict)
                and entry.get("endpoint_hash") == endpoint_hash
            ):
                endpoint = entry.get("endpoint")
                break
        if not isinstance(endpoint, str):
            _log.info(
                "push_emit: pruned %s (%d) — already absent",
                endpoint_hash,
                status,
            )
            return
        try:
            remove_subscription(self._config.store_path, endpoint=endpoint)
        except PushStoreNotFound:
            # Race with another writer (e.g. operator
            # unsubscribed in the UI between the lookup and
            # this removal). The store is already in the
            # desired state; INFO log + return.
            pass
        _log.info("push_emit: pruned %s (%d)", endpoint_hash, status)
        # No bus event emitted by design.

    def _record_backoff(
        self, endpoint_hash: str, headers: Mapping[str, str]
    ) -> None:
        retry_after = headers.get("retry-after")
        delay = DEFAULT_BACKOFF_SECONDS
        if isinstance(retry_after, str):
            try:
                delay = max(float(retry_after), 0.0)
            except ValueError:
                # Could be HTTP-date format; we don't parse
                # those. Fall back to default.
                delay = DEFAULT_BACKOFF_SECONDS
        with self._lock:
            self._backoff_until[endpoint_hash] = self._monotonic() + delay
        _log.warning(
            "push_emit: %s 429; backing off %.1fs", endpoint_hash, delay
        )

    def _log_transport_failure(
        self, endpoint_hash: str, exc: BaseException
    ) -> None:
        """Brief §3-E + Codex P2 round 2 transport-exception
        privacy:

          * Log endpoint_hash + exception TYPE only.
          * NEVER pass the exception object to the formatter
            (its str() / repr() / args / __cause__ / __context__
            can resurface the raw endpoint URL).
          * NEVER use exc_info=True / logger.exception() — the
            traceback frames carry the URL too.
          * Do NOT prune. Do NOT mutate the store. Do NOT emit
            a bus event. Next dispatch retries naturally on a
            new event.

        The literal log shape is the only safe form: a
        formatted string with type(exc).__name__ + the
        endpoint_hash. Anything else risks a privacy
        regression.
        """
        _log.warning(
            "push_emit: %s transport failure (%s)",
            endpoint_hash,
            type(exc).__name__,
        )
