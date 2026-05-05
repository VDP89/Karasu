"""Fetch a peer agent's A2A AgentCard.

Outbound A2A discovery — the symmetric counterpart to the
inbound endpoint that ``karasu serve`` mounts at
``/.well-known/agent-card.json`` (chunk 4b). Audit-deferred from
chunk 4b; lands as a follow-up after the Phase 3+ archive.

Stdlib-only on purpose: no extra runtime dependency just to do
one HTTP GET. ``urllib.request`` covers the surface and gives
us per-call timeout + structured exceptions.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen


DEFAULT_FETCH_TIMEOUT = 5.0
DEFAULT_FETCH_RETRIES = 0
DEFAULT_FETCH_RETRY_HTTP_STATUSES: frozenset[int] = frozenset()
AGENT_CARD_PATH = "/.well-known/agent-card.json"

# Recommended opt-in set for transient-flavoured HTTP errors. Not the
# default — the default stays empty so existing callers are byte-for-
# byte unchanged. Surfaced for the CLI --help text and for any
# programmatic caller that wants the canonical set without re-deriving
# it.
RECOMMENDED_RETRY_HTTP_STATUSES: frozenset[int] = frozenset({502, 503, 504})

# Exponential backoff between retry attempts. The initial delay
# is intentionally small (sub-second): the most common URLError
# in practice is a brief DNS / TCP hiccup that resolves on the
# next attempt. The cap stops long retry sequences from compounding
# into a wall-clock surprise — total wall-clock is bounded by
# ``(timeout + backoff) * (retries + 1)``.
_BACKOFF_INITIAL_SECONDS = 0.5
_BACKOFF_MAX_SECONDS = 4.0


class AgentCardFetchError(Exception):
    """Raised when a peer's AgentCard cannot be fetched or parsed."""


def fetch_card(
    base_url: str,
    *,
    timeout: float = DEFAULT_FETCH_TIMEOUT,
    retries: int = DEFAULT_FETCH_RETRIES,
    retry_http_statuses: frozenset[int] = DEFAULT_FETCH_RETRY_HTTP_STATUSES,
) -> dict[str, Any]:
    """Fetch a peer's AgentCard JSON.

    ``base_url`` is the peer's address; if it does not already end
    in ``AGENT_CARD_PATH`` we append it. The returned dict is the
    raw decoded JSON — the caller decides whether to reconstruct
    an :class:`AgentCard` dataclass or just inspect the payload.

    Raises :class:`AgentCardFetchError` on:

    - Network failure (refused connection, DNS, etc.).
    - Non-2xx HTTP status.
    - Body that is not valid JSON.
    - Body that is not a top-level JSON object.

    Timeout defaults to :data:`DEFAULT_FETCH_TIMEOUT` (5 s); the
    caller can override per fetch.

    ``retries`` (default 0) controls how many additional attempts
    are made on a transient failure. By default only
    :class:`URLError` (network glitch — refused connection, DNS,
    TCP reset) triggers a retry; :class:`HTTPError` (server
    returned a non-2xx, i.e. answered) and JSON / shape errors
    (server answered with garbage) are surfaced immediately.

    ``retry_http_statuses`` (default empty) extends the retry
    surface to a caller-chosen set of HTTP status codes. When an
    :class:`HTTPError` arrives whose ``code`` is in this set, the
    same retry loop applies — same ``retries`` budget, same
    exponential backoff, shared with :class:`URLError` retries
    ("transient = transient"). Statuses outside the set continue
    to surface immediately. Recommended opt-in for proxy / load-
    balancer hiccups: ``{502, 503, 504}``
    (:data:`RECOMMENDED_RETRY_HTTP_STATUSES`). Default empty
    preserves byte-for-byte the pre-issue-#66 single-shot-on-HTTP
    semantics.

    Backoff between attempts is exponential, starting at
    ``_BACKOFF_INITIAL_SECONDS`` and capped at
    ``_BACKOFF_MAX_SECONDS``.
    """
    if timeout <= 0:
        raise ValueError(f"timeout must be > 0, got {timeout}")
    if retries < 0:
        raise ValueError(f"retries must be >= 0, got {retries}")
    for status in retry_http_statuses:
        # bool is a subclass of int in Python; reject explicitly so
        # frozenset({True}) does not silently coerce to {1}.
        if not isinstance(status, int) or isinstance(status, bool):
            raise ValueError(
                f"retry_http_statuses must contain ints, got {status!r}"
            )
        if status < 100 or status >= 600:
            raise ValueError(
                f"retry_http_statuses must be HTTP status codes "
                f"(100-599), got {status}"
            )
    url = _resolve_card_url(base_url)
    request = Request(url, headers={"Accept": "application/json"})

    body: bytes | None = None
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read()
            break
        except HTTPError as exc:
            # The server answered with a non-2xx. By default that's
            # a real response and we surface it. If the caller
            # opted this status into the retry set, treat it as
            # transient and reuse the URLError retry path.
            if exc.code in retry_http_statuses and attempt < retries:
                _sleep_backoff(attempt)
                continue
            raise AgentCardFetchError(
                f"HTTP {exc.code} fetching {url}"
            ) from exc
        except URLError as exc:
            if attempt < retries:
                _sleep_backoff(attempt)
                continue
            raise AgentCardFetchError(
                f"network error fetching {url}: {exc.reason}"
            ) from exc

    # Defensive: the loop above either assigns ``body`` and
    # breaks, or raises. Asserting keeps mypy / readers honest.
    assert body is not None
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise AgentCardFetchError(
            f"invalid JSON from {url}: {exc}"
        ) from exc
    if not isinstance(payload, dict):
        raise AgentCardFetchError(
            f"agent card from {url} is not a JSON object "
            f"(got {type(payload).__name__})"
        )
    return payload


def _sleep_backoff(attempt: int) -> None:
    """Block for the exponential-backoff delay before retry ``attempt+1``.

    Extracted so tests can patch a single function instead of
    ``time.sleep`` (which would catch unrelated sleeps from
    pytest internals if any).
    """
    delay = min(
        _BACKOFF_INITIAL_SECONDS * (2 ** attempt),
        _BACKOFF_MAX_SECONDS,
    )
    time.sleep(delay)


def _resolve_card_url(base_url: str) -> str:
    """Append the well-known card path if ``base_url`` does not already
    end with it. Preserves the operator's exact URL when they
    explicitly wrote the full path.

    Uses urllib.parse so query / fragment / userinfo / port survive
    the rewrite. A bare-string ``rstrip + concat`` would break for
    inputs like ``https://host/api?x=1`` (the suffix would land
    after the query string, producing an invalid URL).
    """
    parsed = urlparse(base_url)
    if parsed.path.endswith(AGENT_CARD_PATH):
        return base_url
    new_path = parsed.path.rstrip("/") + AGENT_CARD_PATH
    return urlunparse(parsed._replace(path=new_path))
