"""Auth middleware tests — UI-13 §3-D anonymous-path
perimeter (Codex round 1 P1 binding 2026-05-07) + macro
pin §11.6.6 carry-forward + UI-14 §3-G extension
(3 entries inside the existing /assets/icons/ namespace:
512-any closes the UI-13 manifest-vs-whitelist gap, the
two maskable variants ship with manifest §3-A SEALED).

Covers ``is_anonymous_path`` against the EXACT whitelist
documented in §3-D + §3-H + §3-G (UI-14):

  GET /
  GET /assets/css/{login,tokens,reset,base}.css
  GET /assets/icons/karasu-192.png
  GET /assets/icons/karasu-512.png            (UI-14 §3-G)
  GET /assets/icons/karasu-maskable-192.png   (UI-14 §3-G)
  GET /assets/icons/karasu-maskable-512.png   (UI-14 §3-G)
  GET /assets/crow/crow.svg
  GET /assets/manifest.json
  GET /assets/sw.js
  GET /assets/fonts/*.woff2  (entire dir)
  GET /auth/logout           (anonymous + idempotent)
  POST /auth/login           (CSRF-cookie-exempt)

EVERY OTHER (method, path) is auth-required by default.
The middleware test surface here pins:
  * Each whitelist member explicitly returns True.
  * Look-alike paths (/login, /Auth/login, trailing slash,
    case differences) return False so the perimeter is the
    exact set, not a prefix-loose superset.
  * POST /auth/logout is auth+CSRF required (§3-D logout
    split; Codex round 1 P1 binding).
  * /api/* and /design-system are NEVER anonymous.
  * Methods other than GET / POST never grant anonymous
    access (HEAD, PUT, DELETE, OPTIONS, PATCH)."""

from __future__ import annotations

import pytest

from karasu.ui._auth import is_anonymous_path


# ---------------------------------------------------------------------------
# GET — exact-set whitelist members
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/assets/css/login.css",
        "/assets/css/tokens.css",
        "/assets/css/reset.css",
        "/assets/css/base.css",
        "/assets/icons/karasu-192.png",
        "/assets/icons/karasu-512.png",            # UI-14 §3-G
        "/assets/icons/karasu-maskable-192.png",   # UI-14 §3-G
        "/assets/icons/karasu-maskable-512.png",   # UI-14 §3-G
        "/assets/crow/crow.svg",
        "/assets/manifest.json",
        "/assets/sw.js",
        "/auth/logout",
    ],
)
def test_anonymous_get_paths(path: str) -> None:
    assert is_anonymous_path("GET", path) is True


# ---------------------------------------------------------------------------
# GET — fonts directory prefix
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/assets/fonts/InterDisplay-Regular.woff2",
        "/assets/fonts/InterDisplay-Bold.woff2",
        "/assets/fonts/JetBrainsMono-Regular.woff2",
        "/assets/fonts/JetBrainsMono-Bold.woff2",
        "/assets/fonts/anything-else.woff2",
        "/assets/fonts/subdir/nested.woff2",
    ],
)
def test_anonymous_fonts_prefix(path: str) -> None:
    """The entire /assets/fonts/ directory is anonymous per
    §3-D + §3-H so login renders without a font flash."""
    assert is_anonymous_path("GET", path) is True


def test_anonymous_fonts_root_without_trailing_slash_rejected() -> None:
    """Prefix is "/assets/fonts/" with the trailing slash
    binding — a request for "/assets/fonts" (no slash) is NOT
    inside the anonymous set."""
    assert is_anonymous_path("GET", "/assets/fonts") is False


# ---------------------------------------------------------------------------
# POST — login is the only anonymous POST
# ---------------------------------------------------------------------------


def test_anonymous_post_login() -> None:
    assert is_anonymous_path("POST", "/auth/login") is True


def test_post_logout_is_not_anonymous() -> None:
    """§3-D logout split (Codex round 1 P1 binding): GET
    /auth/logout is anonymous + idempotent; POST /auth/logout
    is auth+CSRF required (the JS-driven explicit logout
    affordance)."""
    assert is_anonymous_path("POST", "/auth/logout") is False


def test_post_root_is_not_anonymous() -> None:
    assert is_anonymous_path("POST", "/") is False


# ---------------------------------------------------------------------------
# Auth-required paths — /api/*, /design-system, others
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/events"),
        ("GET", "/api/health"),
        ("GET", "/api/meta"),
        ("GET", "/api/agents"),
        ("GET", "/api/push"),
        ("POST", "/api/push/subscribe"),
        ("POST", "/api/push/unsubscribe"),
        ("GET", "/design-system"),
        ("GET", "/index.html"),
        ("GET", "/static/anything"),
    ],
)
def test_auth_required_paths(method: str, path: str) -> None:
    assert is_anonymous_path(method, path) is False


# ---------------------------------------------------------------------------
# Look-alike paths (perimeter must be EXACT, not loose)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        "/login",                        # bare /login is not a route
        "/auth/login",                   # /auth/login is POST-only;
                                         # GET /auth/login is auth-required
        "/Auth/login",                   # case mismatch
        "/auth/login/",                  # trailing slash drift
        "/auth/login.html",              # extension drift
        "//",                            # double slash
        "/auth",                         # parent of /auth/login
        "/assets/css/login",             # missing extension
        "/assets/css/LOGIN.css",         # case mismatch
        "/assets/css/login.css.map",     # source-map drift
        "/assets/icons/karasu-128.png",  # size not in manifest
        "/assets/icons/karasu-maskable.png",          # no size
        "/assets/icons/karasu-maskable-256.png",      # size not
                                                      # in manifest
        "/assets/icons/karasu-maskable-192",          # missing
                                                      # extension
        "/assets/icons/Karasu-Maskable-192.png",      # case
                                                      # mismatch
        "/assets/crow/crow.png",         # wrong extension
        "/assets/manifest",              # missing extension
        "/assets/sw",                    # missing extension
        "/assets/SW.js",                 # case mismatch
        "/favicon.ico",                  # not in the whitelist
                                         # (UI-13 ships favicon
                                         # in a future amendment
                                         # if at all per §3-D)
        "/assets/icons/favicon.ico",     # ditto
    ],
)
def test_lookalike_paths_not_anonymous(path: str) -> None:
    assert is_anonymous_path("GET", path) is False


# ---------------------------------------------------------------------------
# Methods other than GET / POST
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "method",
    ["HEAD", "PUT", "DELETE", "OPTIONS", "PATCH", "TRACE", "CONNECT"],
)
def test_non_get_post_methods_never_anonymous(method: str) -> None:
    """Even on the GET-anonymous URLs, non-GET / non-POST
    methods are not in the whitelist — the route handler can
    405 them, but the auth perimeter must not waive auth."""
    for path in ("/", "/auth/login", "/auth/logout", "/assets/sw.js"):
        assert is_anonymous_path(method, path) is False


def test_lowercase_method_not_anonymous() -> None:
    """Method matching is case-sensitive on the canonical
    "GET" / "POST" tokens. The HTTP server in front normalises
    method casing; the perimeter does not have to defend
    against an unnormalised input but must not silently
    accept either."""
    assert is_anonymous_path("get", "/") is False
    assert is_anonymous_path("post", "/auth/login") is False


# ---------------------------------------------------------------------------
# Empty / pathological inputs
# ---------------------------------------------------------------------------


def test_empty_method_not_anonymous() -> None:
    assert is_anonymous_path("", "/") is False


def test_empty_path_not_anonymous() -> None:
    assert is_anonymous_path("GET", "") is False


def test_query_string_not_anonymous() -> None:
    """The middleware receives the path component pre-split
    from the query string. A path that still carries a
    query string is NOT in the exact-match whitelist."""
    assert is_anonymous_path("GET", "/?next=/secret") is False


def test_fragment_not_anonymous() -> None:
    assert is_anonymous_path("GET", "/#section") is False


def test_path_traversal_in_exact_match_set_rejected() -> None:
    """Path normalisation lives in the HTTP server layer; for
    paths in the EXACT-match part of the whitelist the
    perimeter rejects unnormalised traversal verbatim because
    the string doesn't match an entry. (The fonts dir uses a
    prefix match by design — defending against unnormalised
    traversal is the HTTP server's responsibility per the
    §3-D NOTE.)"""
    assert is_anonymous_path("GET", "/auth/../auth/login") is False
    assert is_anonymous_path("GET", "/sw.js/../auth/login") is False
