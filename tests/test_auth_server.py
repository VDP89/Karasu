"""End-to-end auth surface tests — UI-13 server.py wiring.

Boots a real ``ThreadingHTTPServer`` per test (mirroring the
fixture in ``tests/test_ui_server_http.py``) so the tests
exercise the entire perimeter: cookie parsing, session
verification, CSRF double-submit, Origin matching, login flow
with rate-limit, logout split.

The fixture configures auth eagerly via
``ui_server.configure_auth(...)`` and tears it back down to
the default no-auth posture in cleanup so other test modules
in the suite are unaffected."""

from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterator

import pytest

from karasu.ui import server as ui_server
from karasu.ui._auth import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    issue_csrf_token,
    issue_session_token,
    write_credentials,
)


_USERNAME = "victor"
_PASSWORD = "hunter2"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _start_server(host: str = "127.0.0.1") -> tuple[ThreadingHTTPServer, str, int]:
    server = ThreadingHTTPServer((host, 0), ui_server.UIHandler)
    thread = threading.Thread(
        target=server.serve_forever,
        name="karasu-ui-auth-test",
        daemon=True,
    )
    thread.start()
    return server, server.server_address[0], server.server_address[1]


def _stop_server(server: ThreadingHTTPServer) -> None:
    server.shutdown()
    server.server_close()


@pytest.fixture
def auth_http(tmp_path: Path) -> Iterator[tuple[str, int, Path]]:
    """Boot a UI server with auth enabled (deployed posture
    DISABLED so HTTP loopback works without TLS)."""
    creds_path = tmp_path / "karasu-auth.json"
    write_credentials(creds_path, username=_USERNAME, password=_PASSWORD)

    ui_server.configure(
        event_log=tmp_path / "events.jsonl",
        scars_path=tmp_path / "scars",
        config_path=tmp_path / "karasu.yaml",
        push_store_path=tmp_path / "karasu-push.json",
    )
    ui_server.configure_auth(
        credentials_path=creds_path,
        no_auth=False,
        deployed=False,
        trusted_proxies=frozenset({"127.0.0.1", "::1"}),
        expected_origins=(),
    )
    server, host, port = _start_server()
    try:
        yield host, port, creds_path
    finally:
        _stop_server(server)
        ui_server._reset_auth_state()


@pytest.fixture
def auth_http_deployed(tmp_path: Path) -> Iterator[tuple[str, int, Path, str]]:
    """Boot a UI server with auth enabled in DEPLOYED posture
    (Origin/Referer enforced) on an arbitrary expected
    origin."""
    creds_path = tmp_path / "karasu-auth.json"
    write_credentials(creds_path, username=_USERNAME, password=_PASSWORD)

    ui_server.configure(
        event_log=tmp_path / "events.jsonl",
        scars_path=tmp_path / "scars",
        config_path=tmp_path / "karasu.yaml",
        push_store_path=tmp_path / "karasu-push.json",
    )
    server, host, port = _start_server()
    expected_origin = f"http://{host}:{port}"
    ui_server.configure_auth(
        credentials_path=creds_path,
        no_auth=False,
        deployed=True,
        trusted_proxies=frozenset({"127.0.0.1", "::1"}),
        expected_origins=(expected_origin,),
    )
    try:
        yield host, port, creds_path, expected_origin
    finally:
        _stop_server(server)
        ui_server._reset_auth_state()


@pytest.fixture
def no_auth_http(tmp_path: Path) -> Iterator[tuple[str, int]]:
    """Pre-UI-13 fixture: configure_auth never called →
    AUTH_NO_AUTH stays True. Confirms backwards compat."""
    ui_server.configure(
        event_log=tmp_path / "events.jsonl",
        scars_path=tmp_path / "scars",
        config_path=tmp_path / "karasu.yaml",
        push_store_path=tmp_path / "karasu-push.json",
    )
    server, host, port = _start_server()
    try:
        yield host, port
    finally:
        _stop_server(server)
        ui_server._reset_auth_state()


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------


def _request(
    host: str,
    port: int,
    path: str,
    *,
    method: str = "GET",
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str], list[str]]:
    """Send a request via raw HTTPConnection (no auto-redirect).

    Returns ``(status, body, header_dict, set_cookie_list)``.
    Header dict is case-insensitive lower-cased; Set-Cookie is
    surfaced as a list since it can repeat."""
    conn = HTTPConnection(host, port, timeout=5.0)
    try:
        req_headers = dict(headers or {})
        if body:
            req_headers.setdefault("Content-Length", str(len(body)))
        conn.request(method, path, body=body or None, headers=req_headers)
        resp = conn.getresponse()
        cookies = list(resp.headers.get_all("Set-Cookie") or [])
        return (
            resp.status,
            resp.read(),
            {k.lower(): v for k, v in resp.headers.items()},
            cookies,
        )
    finally:
        conn.close()


def _login(
    host: str,
    port: int,
    *,
    username: str = _USERNAME,
    password: str = _PASSWORD,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes, dict[str, str], list[str]]:
    body = json.dumps({"username": username, "password": password}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    return _request(
        host, port, "/auth/login", method="POST", body=body, headers=headers
    )


def _extract_cookie(
    set_cookies: list[str], name: str
) -> str | None:
    """Pull the cookie value out of a Set-Cookie list."""
    for line in set_cookies:
        head = line.split(";", 1)[0]
        n, _, v = head.partition("=")
        if n.strip() == name:
            return v.strip()
    return None


# ---------------------------------------------------------------------------
# Backwards compat: AUTH_NO_AUTH default keeps old surface working
# ---------------------------------------------------------------------------


def test_no_auth_get_root_serves_index(no_auth_http) -> None:
    host, port = no_auth_http
    status, body, _, _ = _request(host, port, "/")
    assert status == 200
    assert b"<!doctype html>" in body.lower() or b"<!DOCTYPE" in body


def test_no_auth_get_api_events_open(no_auth_http) -> None:
    host, port = no_auth_http
    status, _, _, _ = _request(host, port, "/api/events")
    assert status == 200


def test_no_auth_logout_get_redirects_home(no_auth_http) -> None:
    host, port = no_auth_http
    status, _, headers, _ = _request(host, port, "/auth/logout")
    assert status == 302
    assert headers.get("location") == "/"


# ---------------------------------------------------------------------------
# Auth-enabled posture: anonymous perimeter
# ---------------------------------------------------------------------------


def test_get_root_serves_login_when_no_session(auth_http) -> None:
    host, port, _ = auth_http
    status, body, headers, _ = _request(host, port, "/")
    assert status == 200
    assert b"login-form" in body  # placeholder login.html shipped
    # Should NOT be the index/PWA shell.
    assert b"design-system" not in body or True  # weak; use a stronger marker:
    assert b"<title>Karasu \xe2\x80\x94 Sign in</title>" in body


def test_anonymous_assets_reachable(auth_http) -> None:
    """The anonymous whitelist + the existing asset routing
    cover these paths. (/assets/icons/* and /assets/crow/* are
    referenced from manifest.json + sw.js + login.html but
    routed under STATIC_DIR/assets/* via a separate path the
    chunk-4 wiring does NOT touch — they're tested at the
    perimeter primitive level in test_auth_middleware.py and
    will get HTTP-level coverage when the routing inconsistency
    is fixed in a follow-up.)"""
    host, port, _ = auth_http
    for path in (
        "/assets/css/login.css",
        "/assets/css/tokens.css",
        "/assets/css/reset.css",
        "/assets/css/base.css",
        "/assets/sw.js",
        "/assets/manifest.json",
    ):
        status, _, _, _ = _request(host, port, path)
        assert status == 200, path


# ---------------------------------------------------------------------------
# Auth-required perimeter
# ---------------------------------------------------------------------------


def test_get_api_events_redirects_without_session(auth_http) -> None:
    host, port, _ = auth_http
    status, _, headers, _ = _request(host, port, "/api/events")
    assert status == 302
    assert headers.get("location") == "/"


def test_post_revoke_unauthorized_without_session(auth_http) -> None:
    host, port, _ = auth_http
    status, body, _, _ = _request(
        host,
        port,
        "/api/scars/some-id/revoke",
        method="POST",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert status == 401
    assert b"unauthorized" in body


def test_post_push_subscribe_unauthorized_without_session(auth_http) -> None:
    host, port, _ = auth_http
    status, _, _, _ = _request(
        host,
        port,
        "/api/push/subscribe",
        method="POST",
        body=b"{}",
        headers={"Content-Type": "application/json"},
    )
    assert status == 401


# ---------------------------------------------------------------------------
# POST /auth/login — happy path + Set-Cookie shape
# ---------------------------------------------------------------------------


def test_login_happy_path_sets_both_cookies(auth_http) -> None:
    host, port, _ = auth_http
    status, body, _, set_cookies = _login(host, port)
    assert status == 200
    assert json.loads(body) == {"ok": True}
    session = _extract_cookie(set_cookies, SESSION_COOKIE_NAME)
    csrf = _extract_cookie(set_cookies, CSRF_COOKIE_NAME)
    assert session and csrf


def test_login_session_cookie_attributes(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    raw = next(c for c in set_cookies if c.startswith(SESSION_COOKIE_NAME + "="))
    assert "HttpOnly" in raw
    assert "Path=/" in raw
    assert "SameSite=Lax" in raw
    # Dev posture (deployed=False) → no Secure flag.
    assert "Secure" not in raw


def test_login_csrf_cookie_attributes(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    raw = next(c for c in set_cookies if c.startswith(CSRF_COOKIE_NAME + "="))
    assert "HttpOnly" not in raw  # JS reads the CSRF cookie
    assert "Path=/" in raw
    assert "SameSite=Strict" in raw
    assert "Secure" not in raw


def test_login_deployed_sets_secure(auth_http_deployed) -> None:
    host, port, _, expected_origin = auth_http_deployed
    body = json.dumps({"username": _USERNAME, "password": _PASSWORD}).encode("utf-8")
    _, _, _, set_cookies = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Origin": expected_origin,
        },
    )
    for raw in set_cookies:
        assert "Secure" in raw, raw


# ---------------------------------------------------------------------------
# POST /auth/login — rejection paths
# ---------------------------------------------------------------------------


def test_login_wrong_password_returns_401(auth_http) -> None:
    host, port, _ = auth_http
    status, body, _, set_cookies = _login(host, port, password="wrong")
    assert status == 401
    assert b"could not sign in" in body
    assert set_cookies == []


def test_login_unknown_username_returns_401(auth_http) -> None:
    host, port, _ = auth_http
    status, _, _, set_cookies = _login(host, port, username="someone-else")
    assert status == 401
    assert set_cookies == []


def test_login_malformed_json_returns_400(auth_http) -> None:
    host, port, _ = auth_http
    status, body, _, _ = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=b"not-json{",
        headers={"Content-Type": "application/json"},
    )
    assert status == 400
    assert b"invalid request" in body


def test_login_non_object_body_returns_422(auth_http) -> None:
    host, port, _ = auth_http
    status, _, _, _ = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=b"[1,2,3]",
        headers={"Content-Type": "application/json"},
    )
    assert status == 422


def test_login_missing_fields_returns_422(auth_http) -> None:
    host, port, _ = auth_http
    status, _, _, _ = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=b'{"username":"victor"}',
        headers={"Content-Type": "application/json"},
    )
    assert status == 422


def test_login_oversize_body_returns_413(auth_http) -> None:
    host, port, _ = auth_http
    body = b'{"username":"v","password":"' + (b"x" * 5000) + b'"}'
    status, _, _, _ = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=body,
        headers={"Content-Type": "application/json"},
    )
    assert status == 413


# ---------------------------------------------------------------------------
# Origin / Referer enforcement (deployed posture)
# ---------------------------------------------------------------------------


def test_login_deployed_rejects_wrong_origin(auth_http_deployed) -> None:
    host, port, _, _ = auth_http_deployed
    body = json.dumps({"username": _USERNAME, "password": _PASSWORD}).encode("utf-8")
    status, _, _, _ = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=body,
        headers={
            "Content-Type": "application/json",
            "Origin": "http://attacker.test",
        },
    )
    assert status == 403


def test_login_deployed_rejects_absent_origin_and_referer(auth_http_deployed) -> None:
    host, port, _, _ = auth_http_deployed
    body = json.dumps({"username": _USERNAME, "password": _PASSWORD}).encode("utf-8")
    status, _, _, _ = _request(
        host,
        port,
        "/auth/login",
        method="POST",
        body=body,
        headers={"Content-Type": "application/json"},
    )
    assert status == 403


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


def test_login_rate_limit_after_5_failures(auth_http, monkeypatch) -> None:
    """Under loopback dev posture the rate limiter would
    bypass on 127.0.0.1; force the bypass off by patching the
    is_loopback_ip check inside the rate-limit module."""
    host, port, _ = auth_http
    from karasu.ui import _auth as auth_mod

    monkeypatch.setattr(auth_mod, "is_loopback_ip", lambda _addr: False)

    for _ in range(5):
        status, _, _, _ = _login(host, port, password="wrong")
        assert status == 401
    # 6th attempt — even with the right password — must be 429.
    status, body, _, _ = _login(host, port)
    assert status == 429
    assert b"too many attempts" in body


# ---------------------------------------------------------------------------
# Authenticated requests
# ---------------------------------------------------------------------------


def test_authenticated_get_api_events(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    status, _, _, _ = _request(
        host, port, "/api/events", headers={"Cookie": cookie_header}
    )
    assert status == 200


def test_authenticated_get_root_serves_index(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    status, body, _, _ = _request(
        host, port, "/", headers={"Cookie": cookie_header}
    )
    assert status == 200
    assert b"login-form" not in body  # served the PWA shell, not login


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


def test_post_revoke_with_session_but_no_csrf_returns_403(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    status, body, _, _ = _request(
        host,
        port,
        "/api/scars/some-id/revoke",
        method="POST",
        body=b"{}",
        headers={"Cookie": cookie_header, "Content-Type": "application/json"},
    )
    assert status == 403
    assert b"forbidden" in body


def test_post_with_session_but_csrf_cookie_header_mismatch_returns_403(
    auth_http,
) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    csrf_cookie = _extract_cookie(set_cookies, CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    status, _, _, _ = _request(
        host,
        port,
        "/api/scars/some-id/revoke",
        method="POST",
        body=b"{}",
        headers={
            "Cookie": cookie_header,
            "Content-Type": "application/json",
            CSRF_HEADER_NAME: "tampered." + csrf_cookie.split(".", 1)[1],
        },
    )
    assert status == 403


def test_post_with_session_and_matching_csrf_proceeds(auth_http) -> None:
    """POST that passes auth+CSRF reaches the handler. The
    revoke endpoint then 404s because the scar id doesn't
    exist — but a 404 from the handler proves the perimeter
    let the request through (a 401/403 would mean the
    perimeter blocked it)."""
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    csrf_cookie = _extract_cookie(set_cookies, CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    status, _, _, _ = _request(
        host,
        port,
        "/api/scars/nonexistent-id/revoke",
        method="POST",
        body=b"{}",
        headers={
            "Cookie": cookie_header,
            "Content-Type": "application/json",
            CSRF_HEADER_NAME: csrf_cookie,
        },
    )
    assert status == 404  # not 401/403


# ---------------------------------------------------------------------------
# Logout — GET (anonymous + idempotent + Origin-checked deployed)
# ---------------------------------------------------------------------------


def test_get_logout_dev_redirects_home_and_clears_cookies(auth_http) -> None:
    host, port, _ = auth_http
    status, _, headers, set_cookies = _request(host, port, "/auth/logout")
    assert status == 302
    assert headers.get("location") == "/"
    # Both cookies should be cleared via Max-Age=0.
    session_clear = next(
        (c for c in set_cookies if c.startswith(SESSION_COOKIE_NAME + "=")), None
    )
    csrf_clear = next(
        (c for c in set_cookies if c.startswith(CSRF_COOKIE_NAME + "=")), None
    )
    assert session_clear and "Max-Age=0" in session_clear
    assert csrf_clear and "Max-Age=0" in csrf_clear


def test_get_logout_deployed_rejects_cross_origin(auth_http_deployed) -> None:
    host, port, _, _ = auth_http_deployed
    status, _, _, set_cookies = _request(
        host,
        port,
        "/auth/logout",
        headers={"Referer": "http://attacker.test/"},
    )
    assert status == 403
    # Cookies MUST NOT be cleared on a cross-origin GET (the
    # attacker can't log Victor out via image tag prefetch).
    assert all("Max-Age=0" not in c for c in set_cookies)


def test_get_logout_deployed_accepts_same_origin_referer(
    auth_http_deployed,
) -> None:
    host, port, _, expected_origin = auth_http_deployed
    status, _, headers, _ = _request(
        host,
        port,
        "/auth/logout",
        headers={"Referer": expected_origin + "/some/page"},
    )
    assert status == 302
    assert headers.get("location") == "/"


# ---------------------------------------------------------------------------
# Logout — POST (auth+CSRF required)
# ---------------------------------------------------------------------------


def test_post_logout_requires_auth(auth_http) -> None:
    host, port, _ = auth_http
    status, _, _, _ = _request(host, port, "/auth/logout", method="POST")
    assert status == 401


def test_post_logout_requires_csrf(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    status, _, _, _ = _request(
        host,
        port,
        "/auth/logout",
        method="POST",
        headers={"Cookie": cookie_header},
    )
    assert status == 403


def test_post_logout_clears_cookies_on_success(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)
    csrf_cookie = _extract_cookie(set_cookies, CSRF_COOKIE_NAME)
    assert csrf_cookie is not None
    status, _, _, set_cookies_logout = _request(
        host,
        port,
        "/auth/logout",
        method="POST",
        headers={
            "Cookie": cookie_header,
            CSRF_HEADER_NAME: csrf_cookie,
        },
    )
    assert status == 204
    assert any(
        c.startswith(SESSION_COOKIE_NAME + "=") and "Max-Age=0" in c
        for c in set_cookies_logout
    )
    assert any(
        c.startswith(CSRF_COOKIE_NAME + "=") and "Max-Age=0" in c
        for c in set_cookies_logout
    )


# ---------------------------------------------------------------------------
# Stale / tampered session
# ---------------------------------------------------------------------------


def test_tampered_session_cookie_redirects_to_login(auth_http) -> None:
    host, port, _ = auth_http
    _, _, _, set_cookies = _login(host, port)
    session = _extract_cookie(set_cookies, SESSION_COOKIE_NAME)
    assert session is not None
    tampered = session[:-3] + "AAA"
    status, _, headers, _ = _request(
        host,
        port,
        "/api/events",
        headers={"Cookie": f"{SESSION_COOKIE_NAME}={tampered}"},
    )
    assert status == 302
    assert headers.get("location") == "/"


def test_session_after_credential_rotation_invalidated(
    auth_http, tmp_path: Path
) -> None:
    """Rotate creds on disk → reload via configure_auth →
    existing session cookie no longer verifies."""
    host, port, creds_path = auth_http
    _, _, _, set_cookies = _login(host, port)
    cookie_header = "; ".join(c.split(";", 1)[0] for c in set_cookies)

    write_credentials(creds_path, username=_USERNAME, password="rotated_pw")
    ui_server.configure_auth(
        credentials_path=creds_path,
        no_auth=False,
        deployed=False,
        trusted_proxies=frozenset({"127.0.0.1", "::1"}),
        expected_origins=(),
    )

    status, _, _, _ = _request(
        host, port, "/api/events", headers={"Cookie": cookie_header}
    )
    # gen mismatch + secret mismatch both invalidate; either
    # way the middleware sees an invalid session and redirects.
    assert status == 302


# ---------------------------------------------------------------------------
# configure_auth contract
# ---------------------------------------------------------------------------


def test_configure_auth_fails_closed_on_missing_creds(tmp_path: Path) -> None:
    """no_auth=False + missing credentials_path → raises
    AuthCredentialsError (cmd_ui catches and exits 2 per
    §3-B fail-closed)."""
    from karasu.ui._auth import AuthCredentialsError

    try:
        with pytest.raises(AuthCredentialsError):
            ui_server.configure_auth(
                credentials_path=tmp_path / "missing.json",
                no_auth=False,
                deployed=False,
                trusted_proxies=frozenset({"127.0.0.1"}),
                expected_origins=(),
            )
    finally:
        ui_server._reset_auth_state()


def test_configure_auth_no_auth_clears_state(tmp_path: Path) -> None:
    """no_auth=True drops creds + rate-limit (defensive
    teardown contract)."""
    creds_path = tmp_path / "auth.json"
    write_credentials(creds_path, username="v", password="p")
    try:
        ui_server.configure_auth(
            credentials_path=creds_path,
            no_auth=False,
            deployed=False,
            trusted_proxies=frozenset({"127.0.0.1"}),
            expected_origins=(),
        )
        assert ui_server._AUTH_CREDS_CACHE is not None
        assert ui_server._AUTH_RATE_LIMIT is not None
        ui_server.configure_auth(
            credentials_path=None, no_auth=True
        )
        assert ui_server._AUTH_CREDS_CACHE is None
        assert ui_server._AUTH_RATE_LIMIT is None
    finally:
        ui_server._reset_auth_state()
