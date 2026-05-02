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
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import Request, urlopen


DEFAULT_FETCH_TIMEOUT = 5.0
AGENT_CARD_PATH = "/.well-known/agent-card.json"


class AgentCardFetchError(Exception):
    """Raised when a peer's AgentCard cannot be fetched or parsed."""


def fetch_card(
    base_url: str, *, timeout: float = DEFAULT_FETCH_TIMEOUT
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
    """
    if timeout <= 0:
        raise ValueError(f"timeout must be > 0, got {timeout}")
    url = _resolve_card_url(base_url)
    request = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
    except HTTPError as exc:
        raise AgentCardFetchError(
            f"HTTP {exc.code} fetching {url}"
        ) from exc
    except URLError as exc:
        raise AgentCardFetchError(
            f"network error fetching {url}: {exc.reason}"
        ) from exc
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
