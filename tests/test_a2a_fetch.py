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
    DEFAULT_FETCH_RETRIES,
    DEFAULT_FETCH_RETRY_HTTP_STATUSES,
    DEFAULT_FETCH_TIMEOUT,
    RECOMMENDED_RETRY_HTTP_STATUSES,
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


# ---------------------------------------------------------------------------
# fetch_card — retry on network error (PR #58 follow-up)
# ---------------------------------------------------------------------------


def test_fetch_card_default_retries_is_zero() -> None:
    """Pin the default at 0 so adding retries cannot silently change
    single-shot semantics for any existing caller."""
    assert DEFAULT_FETCH_RETRIES == 0


def test_fetch_card_no_retry_by_default_on_url_error() -> None:
    """retries=0 (default) — one attempt, one URLError, one fetch error.
    No silent retry behind the caller's back."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = URLError("connection refused")
        with pytest.raises(AgentCardFetchError, match="network error"):
            fetch_card("http://example.invalid")
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_card_retries_on_url_error_then_succeeds() -> None:
    """Two URLErrors then a 200 — the third attempt's payload is
    returned. Verifies retry covers transient DNS / TCP hiccups.

    ``io.BytesIO`` is itself a context manager (``__enter__`` returns
    self), which matches what ``with urlopen(...) as response`` needs
    on the success branch."""
    payload = b'{"name": "peer", "skills": []}'
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = [
            URLError("dns hiccup"),
            URLError("tcp reset"),
            _mock_response(payload),
        ]
        result = fetch_card("http://example.invalid", retries=2)
    assert result == {"name": "peer", "skills": []}
    assert mock_urlopen.call_count == 3
    # Backoff fires once per failed attempt before the next try,
    # i.e. exactly ``retries`` times when the final attempt
    # succeeds — never after the last attempt.
    assert mock_sleep.call_count == 2


def test_fetch_card_retries_exhausted_raises_last_error() -> None:
    """All attempts raise URLError → AgentCardFetchError surfaces the
    final reason. Total urlopen calls = retries + 1."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = URLError("still down")
        with pytest.raises(AgentCardFetchError, match="still down"):
            fetch_card("http://example.invalid", retries=3)
    assert mock_urlopen.call_count == 4
    # No sleep after the final (failing) attempt.
    assert mock_sleep.call_count == 3


def test_fetch_card_does_not_retry_on_http_error() -> None:
    """A non-2xx is the server's real answer. Retrying it would be
    wasteful and could amplify a server outage; surface the status
    immediately even when retries > 0."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = HTTPError(
            url="http://example.invalid",
            code=503,
            msg="Service Unavailable",
            hdrs=None,  # type: ignore[arg-type]
            fp=None,
        )
        with pytest.raises(AgentCardFetchError, match="HTTP 503"):
            fetch_card("http://example.invalid", retries=5)
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_card_does_not_retry_on_invalid_json() -> None:
    """Successful HTTP fetch + bad JSON body is not a network glitch.
    Surface immediately; retrying would re-fetch the same garbage."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.return_value.__enter__.return_value = _mock_response(
            b"not really json"
        )
        with pytest.raises(AgentCardFetchError, match="invalid JSON"):
            fetch_card("http://example.invalid", retries=3)
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_card_rejects_negative_retries() -> None:
    """Defence against an operator passing ``--retries -1`` (e.g. via
    a typo or env-var expansion). Fail-fast is safer than silently
    treating it as zero."""
    with pytest.raises(ValueError, match="retries"):
        fetch_card("http://x", retries=-1)


def test_fetch_card_backoff_is_exponential_and_capped() -> None:
    """``_sleep_backoff(attempt)`` honours the documented schedule:
    0.5, 1.0, 2.0, 4.0, 4.0 ... — exponential up to the cap."""
    from karasu.a2a.fetch import (
        _BACKOFF_INITIAL_SECONDS,
        _BACKOFF_MAX_SECONDS,
        _sleep_backoff,
    )

    assert _BACKOFF_INITIAL_SECONDS == 0.5
    assert _BACKOFF_MAX_SECONDS == 4.0
    with patch("karasu.a2a.fetch.time.sleep") as mock_sleep:
        for attempt in range(5):
            _sleep_backoff(attempt)
    delays = [call.args[0] for call in mock_sleep.call_args_list]
    assert delays == [0.5, 1.0, 2.0, 4.0, 4.0]


def test_cmd_peers_passes_retries_through(capsys) -> None:
    """--retries reaches fetch_card. With 2 retries and 3 URLErrors,
    urlopen is called 3 times before exit 2 surfaces."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ):
        mock_urlopen.side_effect = URLError("nothing on that port")
        rc = main(
            [
                "peers",
                "--retries",
                "2",
                "http://127.0.0.1:1",
            ]
        )
    assert rc == 2
    assert mock_urlopen.call_count == 3


# ---------------------------------------------------------------------------
# fetch_card — opt-in retry on transient HTTP statuses (issue #66)
# ---------------------------------------------------------------------------


def _http_error(code: int) -> HTTPError:
    return HTTPError(
        url="http://example.invalid",
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )


def test_fetch_card_default_retry_http_statuses_is_empty() -> None:
    """Pin the default at empty so opting into retry on HTTP errors is
    always an explicit caller decision; existing callers preserve
    their byte-for-byte single-shot-on-HTTP behaviour."""
    assert DEFAULT_FETCH_RETRY_HTTP_STATUSES == frozenset()
    assert isinstance(DEFAULT_FETCH_RETRY_HTTP_STATUSES, frozenset)


def test_fetch_card_recommended_retry_set_is_502_503_504() -> None:
    """The recommended-but-not-default set surfaces from the module so
    the CLI --help text and any programmatic caller can reach for the
    canonical "transient proxy errors" set without re-deriving it."""
    assert RECOMMENDED_RETRY_HTTP_STATUSES == frozenset({502, 503, 504})


def test_fetch_card_retries_on_status_in_retry_set_then_succeeds() -> None:
    """503 then 200 with retries=1 + retry_http_statuses={503} —
    fetch_card retries once, gets the payload on attempt 2."""
    payload = b'{"name": "peer", "skills": []}'
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = [
            _http_error(503),
            _mock_response(payload),
        ]
        result = fetch_card(
            "http://example.invalid",
            retries=1,
            retry_http_statuses=frozenset({503}),
        )
    assert result == {"name": "peer", "skills": []}
    assert mock_urlopen.call_count == 2
    assert mock_sleep.call_count == 1


def test_fetch_card_does_not_retry_on_status_outside_retry_set() -> None:
    """500 with retry_http_statuses={502, 503, 504} — 500 is OUT of
    the set, so it surfaces immediately even with retries available.
    Pin the discrimination so a future refactor cannot accidentally
    widen the retry surface."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = _http_error(500)
        with pytest.raises(AgentCardFetchError, match="HTTP 500"):
            fetch_card(
                "http://example.invalid",
                retries=3,
                retry_http_statuses=RECOMMENDED_RETRY_HTTP_STATUSES,
            )
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_fetch_card_retries_status_then_url_error_share_budget() -> None:
    """502 → URLError → 200 with retries=2 + retry_http_statuses={502}.
    Verifies the "transient = transient" intuition from issue #66:
    a single shared budget covers both kinds of retryable failure."""
    payload = b'{"name": "peer", "skills": []}'
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = [
            _http_error(502),
            URLError("tcp reset"),
            _mock_response(payload),
        ]
        result = fetch_card(
            "http://example.invalid",
            retries=2,
            retry_http_statuses=frozenset({502}),
        )
    assert result == {"name": "peer", "skills": []}
    assert mock_urlopen.call_count == 3
    assert mock_sleep.call_count == 2


def test_fetch_card_retries_exhausted_on_status_raises_last_http_error() -> None:
    """All attempts return 503 with retries=2 + retry_http_statuses=
    {503}. urlopen called 3 times, then AgentCardFetchError surfaces
    the HTTP code from the final attempt."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = _http_error(503)
        with pytest.raises(AgentCardFetchError, match="HTTP 503"):
            fetch_card(
                "http://example.invalid",
                retries=2,
                retry_http_statuses=frozenset({503}),
            )
    assert mock_urlopen.call_count == 3
    # No sleep after the final (failing) attempt — same convention
    # as the URLError exhaustion test above.
    assert mock_sleep.call_count == 2


def test_fetch_card_rejects_non_int_retry_status() -> None:
    """frozenset({'502'}) is a programmer error, not a typo to
    silently coerce. Fail-fast at the validation pass, before any
    HTTP attempt fires."""
    with pytest.raises(ValueError, match="retry_http_statuses"):
        fetch_card(
            "http://example.invalid",
            retry_http_statuses=frozenset({"502"}),  # type: ignore[arg-type]
        )


def test_fetch_card_rejects_bool_retry_status() -> None:
    """bool is a subclass of int in Python; True would silently coerce
    to 1, which is not a valid HTTP status. Reject explicitly."""
    with pytest.raises(ValueError, match="retry_http_statuses"):
        fetch_card(
            "http://example.invalid",
            retry_http_statuses=frozenset({True}),  # type: ignore[arg-type]
        )


def test_fetch_card_rejects_out_of_range_retry_status() -> None:
    """Below 100 or >= 600 is not an HTTP status; a 60 in the set is
    almost certainly a typo for 600 / 504. Surface immediately so the
    operator notices."""
    with pytest.raises(ValueError, match="100-599"):
        fetch_card(
            "http://example.invalid",
            retry_http_statuses=frozenset({99}),
        )
    with pytest.raises(ValueError, match="100-599"):
        fetch_card(
            "http://example.invalid",
            retry_http_statuses=frozenset({600}),
        )


def test_fetch_card_empty_retry_set_preserves_pre_issue_66_semantics() -> None:
    """503 with retries=5 + retry_http_statuses=frozenset() — single-
    shot HTTP behaviour preserved exactly. This is the contract pin
    that callers from before issue #66 rely on; double-checked here
    even though test_fetch_card_does_not_retry_on_http_error already
    covers the no-explicit-set path."""
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ) as mock_sleep:
        mock_urlopen.side_effect = _http_error(503)
        with pytest.raises(AgentCardFetchError, match="HTTP 503"):
            fetch_card(
                "http://example.invalid",
                retries=5,
                retry_http_statuses=frozenset(),
            )
    assert mock_urlopen.call_count == 1
    mock_sleep.assert_not_called()


def test_cmd_peers_passes_retry_http_statuses_through() -> None:
    """--retry-http-statuses 502,503,504 reaches fetch_card with the
    parsed frozenset. With retries=1 and a 503 then a 200, urlopen is
    called twice and the CLI exits 0."""
    from karasu.__main__ import main

    payload = b'{"name": "peer", "skills": []}'
    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ):
        mock_urlopen.side_effect = [
            _http_error(503),
            _mock_response(payload),
        ]
        rc = main(
            [
                "peers",
                "--json",
                "--retries",
                "1",
                "--retry-http-statuses",
                "502,503,504",
                "http://127.0.0.1:1",
            ]
        )
    assert rc == 0
    assert mock_urlopen.call_count == 2


def test_cmd_peers_retry_http_statuses_default_is_empty(capsys) -> None:
    """No --retry-http-statuses → fetch_card receives frozenset(). A
    503 surfaces on attempt 1 even with --retries=3. Pin the CLI
    default so a future change cannot silently turn on HTTP retries
    for every existing operator."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ):
        mock_urlopen.side_effect = _http_error(503)
        rc = main(
            [
                "peers",
                "--retries",
                "3",
                "http://127.0.0.1:1",
            ]
        )
    captured = capsys.readouterr()
    assert rc == 2
    assert "HTTP 503" in captured.err
    assert mock_urlopen.call_count == 1


def test_cmd_peers_rejects_non_integer_retry_http_statuses(capsys) -> None:
    """``--retry-http-statuses 502,abc`` fails fast at argparse
    parsing time; no HTTP attempt fires."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "peers",
                    "--retry-http-statuses",
                    "502,abc",
                    "http://127.0.0.1:1",
                ]
            )
    # argparse exits 2 on a usage error.
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "comma-separated integers" in captured.err
    mock_urlopen.assert_not_called()


def test_cmd_peers_rejects_out_of_range_retry_http_statuses(capsys) -> None:
    """``--retry-http-statuses 99`` (below 100) fails fast — a 99 in
    the set is almost always a typo, never a legitimate status."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen:
        with pytest.raises(SystemExit) as exc_info:
            main(
                [
                    "peers",
                    "--retry-http-statuses",
                    "99",
                    "http://127.0.0.1:1",
                ]
            )
    assert exc_info.value.code == 2
    captured = capsys.readouterr()
    assert "100-599" in captured.err
    mock_urlopen.assert_not_called()


def test_cmd_peers_empty_retry_http_statuses_string_yields_empty_set(
    capsys,
) -> None:
    """``--retry-http-statuses ''`` is the explicit-empty case
    (rare in practice, but argparse accepts the value). Pinned so a
    future caller scripting ``--retry-http-statuses "$VAR"`` against
    an unset env var does not blow up."""
    from karasu.__main__ import main

    with patch("karasu.a2a.fetch.urlopen") as mock_urlopen, patch(
        "karasu.a2a.fetch._sleep_backoff"
    ):
        mock_urlopen.side_effect = _http_error(503)
        rc = main(
            [
                "peers",
                "--retries",
                "3",
                "--retry-http-statuses",
                "",
                "http://127.0.0.1:1",
            ]
        )
    captured = capsys.readouterr()
    assert rc == 2
    assert "HTTP 503" in captured.err
    # Empty set means single-shot semantics, even with --retries=3.
    assert mock_urlopen.call_count == 1
