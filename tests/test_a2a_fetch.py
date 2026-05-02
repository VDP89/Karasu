"""Tests for outbound A2A discovery — Phase 3+ chunk 4b follow-up.

Two layers:

1. ``fetch_card(base_url)`` — stdlib-only HTTP GET against a peer's
   ``/.well-known/agent-card.json`` returning the parsed JSON dict.
2. ``karasu peers <url>`` — read-only CLI wrapper around fetch_card.

End-to-end tests reuse the chunk-4b webhook source's card-serving
machinery so the real round-trip is exercised. Error paths use
``unittest.mock`` to avoid binding ports for failure scenarios.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from karasu.a2a import (
    AGENT_CARD_PATH,
    DEFAULT_FETCH_TIMEOUT,
    AgentCardFetchError,
    build_karasu_card,
    fetch_card,
)
from karasu.a2a.fetch import _resolve_card_url
from karasu.controller.sources.webhook import build_webhook_source
from karasu.eventbus import JsonlEventBus


_VALID_SECRET = "a-super-secret-key-of-at-least-16b"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


def test_resolve_card_url_appends_well_known_when_absent() -> None:
    assert (
        _resolve_card_url("http://127.0.0.1:8080")
        == f"http://127.0.0.1:8080{AGENT_CARD_PATH}"
    )


def test_resolve_card_url_strips_trailing_slash_before_appending() -> None:
    """A trailing slash on the base URL must not produce a double-slash
    path; the well-known URL is canonical without that ambiguity."""
    assert (
        _resolve_card_url("http://127.0.0.1:8080/")
        == f"http://127.0.0.1:8080{AGENT_CARD_PATH}"
    )


def test_resolve_card_url_preserves_explicit_suffix() -> None:
    """If the operator typed the full /.well-known/agent-card.json path
    we leave it alone — assume they know what they want."""
    explicit = f"http://127.0.0.1:8080{AGENT_CARD_PATH}"
    assert _resolve_card_url(explicit) == explicit


def test_resolve_card_url_preserves_query_string() -> None:
    """A naive rstrip+concat would land the suffix after the query
    string, producing an invalid URL. urlparse-based rewrite keeps
    the query attached to the canonical card path."""
    assert (
        _resolve_card_url("http://host/api?x=1")
        == f"http://host/api{AGENT_CARD_PATH}?x=1"
    )


def test_resolve_card_url_preserves_fragment() -> None:
    """Same defence for fragments — they belong to the URL, not to the
    path the suffix is attached to."""
    assert (
        _resolve_card_url("http://host#section")
        == f"http://host{AGENT_CARD_PATH}#section"
    )


# ---------------------------------------------------------------------------
# fetch_card — end-to-end against the real chunk-4b card server
# ---------------------------------------------------------------------------


def test_fetch_card_round_trips_against_real_server(
    bus: JsonlEventBus,
) -> None:
    """Spin up the real webhook source with a card, fetch it, assert
    the dict matches what build_karasu_card produced."""
    card = build_karasu_card(base_url="http://127.0.0.1:1")
    source = build_webhook_source(
        secret=_VALID_SECRET,
        bus=bus,
        submit=lambda e: None,
        host="127.0.0.1",
        port=0,
        agent_card=card,
    )
    source.start()
    try:
        host, port = source.address
        fetched = fetch_card(f"http://{host}:{port}")
    finally:
        source.stop()

    assert fetched["name"] == "karasu"
    assert isinstance(fetched["skills"], list)
    assert len(fetched["skills"]) == 4
    assert fetched["capabilities"] == {
        "streaming": False,
        "pushNotifications": False,
    }


def test_fetch_card_accepts_explicit_well_known_url(
    bus: JsonlEventBus,
) -> None:
    """Passing the full /.well-known/agent-card.json URL is also valid;
    fetch_card does not double-append the suffix."""
    card = build_karasu_card()
    source = build_webhook_source(
        secret=_VALID_SECRET,
        bus=bus,
        submit=lambda e: None,
        host="127.0.0.1",
        port=0,
        agent_card=card,
    )
    source.start()
    try:
        host, port = source.address
        fetched = fetch_card(
            f"http://{host}:{port}{AGENT_CARD_PATH}"
        )
    finally:
        source.stop()

    assert fetched["name"] == "karasu"


def test_fetch_card_on_server_without_card_raises(
    bus: JsonlEventBus,
) -> None:
    """When the operator runs ``karasu serve`` without configuring a
    card, GET /.well-known/agent-card.json returns 404; fetch_card
    surfaces that as a structured error (not a silent dict)."""
    source = build_webhook_source(
        secret=_VALID_SECRET,
        bus=bus,
        submit=lambda e: None,
        host="127.0.0.1",
        port=0,
        agent_card=None,
    )
    source.start()
    try:
        host, port = source.address
        with pytest.raises(AgentCardFetchError, match="HTTP 404"):
            fetch_card(f"http://{host}:{port}")
    finally:
        source.stop()


# ---------------------------------------------------------------------------
# fetch_card — error paths (mock-based)
# ---------------------------------------------------------------------------


def _mock_response(body: bytes) -> "io.BytesIO":
    """Return a minimal context-manager-shaped object that urlopen-callers
    can ``with`` and ``.read()``. ``io.BytesIO`` supports both."""
    return io.BytesIO(body)


def test_fetch_card_raises_on_invalid_json() -> None:
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(
            b"not really json"
        )
        with pytest.raises(AgentCardFetchError, match="invalid JSON"):
            fetch_card("http://example.invalid")


def test_fetch_card_raises_on_top_level_array() -> None:
    """A2A cards are JSON objects. A top-level array is unambiguously
    not a card; surface as a structured error rather than letting
    the caller choke on a list."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(
            b'["not", "an", "object"]'
        )
        with pytest.raises(
            AgentCardFetchError, match="not a JSON object"
        ):
            fetch_card("http://example.invalid")


def test_fetch_card_raises_on_top_level_scalar() -> None:
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(
            b'"a string is not a card"'
        )
        with pytest.raises(
            AgentCardFetchError, match="not a JSON object"
        ):
            fetch_card("http://example.invalid")


def test_fetch_card_raises_on_url_error() -> None:
    """Connection refused / DNS failure / etc. surface as
    AgentCardFetchError so the caller has one exception class to
    catch instead of three urllib classes."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = URLError("connection refused")
        with pytest.raises(AgentCardFetchError, match="network error"):
            fetch_card("http://nowhere.invalid")


def test_fetch_card_raises_on_http_error() -> None:
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = HTTPError(
            url="http://example.invalid",
            code=500,
            msg="Internal Server Error",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        with pytest.raises(AgentCardFetchError, match="HTTP 500"):
            fetch_card("http://example.invalid")


def test_fetch_card_rejects_zero_or_negative_timeout() -> None:
    """Defence against an operator passing ``--timeout 0`` from the
    CLI thinking it means "no timeout" — that's not how urllib reads
    it, and we want fail-fast over a silently hanging fetch."""
    with pytest.raises(ValueError, match="timeout"):
        fetch_card("http://x", timeout=0)
    with pytest.raises(ValueError, match="timeout"):
        fetch_card("http://x", timeout=-1)


def test_fetch_card_default_timeout_is_five_seconds() -> None:
    """Pin the documented default. A future contributor lengthening or
    shortening the default surfaces here."""
    assert DEFAULT_FETCH_TIMEOUT == 5.0


# ---------------------------------------------------------------------------
# karasu peers CLI
# ---------------------------------------------------------------------------


def test_cmd_peers_formats_card(
    bus: JsonlEventBus, capsys, tmp_path: Path
) -> None:
    """End-to-end: real card server + ``main(["peers", URL])``
    pretty-prints the card to stdout, exits 0."""
    card = build_karasu_card(base_url="http://127.0.0.1:1")
    source = build_webhook_source(
        secret=_VALID_SECRET,
        bus=bus,
        submit=lambda e: None,
        host="127.0.0.1",
        port=0,
        agent_card=card,
    )
    source.start()
    try:
        host, port = source.address
        from karasu.__main__ import main

        rc = main(["peers", f"http://{host}:{port}"])
    finally:
        source.stop()

    captured = capsys.readouterr()
    assert rc == 0
    assert "name:        karasu" in captured.out
    # Each baseline skill is listed.
    assert "watch-filesystem" in captured.out
    assert "route-events" in captured.out
    assert "receive-github-webhooks" in captured.out
    assert "record-corrections" in captured.out
    # Capabilities header + values.
    assert "streaming:" in captured.out
    assert "pushNotifications:" in captured.out


def test_cmd_peers_json_flag_emits_raw_json(
    bus: JsonlEventBus, capsys
) -> None:
    """--json prints the raw card JSON; downstream tooling can pipe
    it to jq without parsing the formatted text output."""
    card = build_karasu_card()
    source = build_webhook_source(
        secret=_VALID_SECRET,
        bus=bus,
        submit=lambda e: None,
        host="127.0.0.1",
        port=0,
        agent_card=card,
    )
    source.start()
    try:
        host, port = source.address
        from karasu.__main__ import main

        rc = main(["peers", "--json", f"http://{host}:{port}"])
    finally:
        source.stop()

    captured = capsys.readouterr()
    assert rc == 0
    # The output is parseable JSON with the expected shape.
    parsed = json.loads(captured.out)
    assert parsed["name"] == "karasu"
    assert isinstance(parsed["skills"], list)


def test_cmd_peers_exits_2_on_fetch_failure(capsys) -> None:
    """A network failure / non-2xx status / bad payload should NOT
    raise out of the CLI; print to stderr and exit non-zero so the
    operator sees what went wrong."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.side_effect = URLError("nothing on that port")
        rc = main(["peers", "http://127.0.0.1:1"])

    captured = capsys.readouterr()
    assert rc == 2
    assert "network error" in captured.err
    # Stdout stays clean for tooling that pipes formatted output.
    assert captured.out == ""


def test_cmd_peers_passes_timeout_through(capsys) -> None:
    """--timeout reaches fetch_card; pinned so a future refactor of
    the CLI can't silently drop the kwarg."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(
            b'{"name": "x", "skills": []}'
        )
        rc = main(
            [
                "peers",
                "--timeout",
                "1.5",
                "--json",
                "http://127.0.0.1:1",
            ]
        )

    assert rc == 0
    # Timeout argument propagated to urlopen.
    _args, kwargs = mock_urlopen.call_args
    assert kwargs.get("timeout") == 1.5
