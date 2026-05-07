"""Service worker fetch-handler shape-lock test (UI-12b pin §11.6.4).

Codex pin §11.6.12 from the UI-12 brief and pin §11.6.4 from the
UI-12b brief require the SW fetch handler ordering to be
auditable from a structural test, not from diff review alone:

    1. /api/* → network-only.
    2. Navigation → network first, /offline.html on rejection.
    3. /assets/* (and everything else) → cache-first.

UI-12b's sw.js delta adds ``push`` + ``notificationclick``
event listeners. Those are independent SW event types from the
``fetch`` event, so they cannot interfere structurally — but
the audit pin demands that the additive-only claim is PROVED
by a test, not asserted by the implementer.

The test file commit pre-dates the sw.js diff in the PR commit
ordering (UI-12b §3-D / pin §11.6.4): the test passes against
the UI-8-era sw.js (no push listeners yet). When the sw.js
change lands in the next commit, the same assertions still
pass — that's the proof of additivity.

The shape lock is implemented as a structural source-level
check rather than a Playwright fixture so it runs in plain
``pytest`` with zero browser dependency. Lint-style tests are
the established Karasu pattern for static UI artefacts (see
``test_lint_ui_css.py``).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SW_PATH = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "sw.js"


@pytest.fixture(scope="module")
def sw_source() -> str:
    """Read the live sw.js source. Failing here means the file
    moved — that is itself a regression worth surfacing
    explicitly rather than letting downstream tests confuse the
    operator with a downstream NoneType crash."""
    assert SW_PATH.is_file(), f"sw.js not found at {SW_PATH}"
    return SW_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Branch ordering — the contract
# ---------------------------------------------------------------------------


def _fetch_handler_body(source: str) -> str:
    """Return the body of the ``fetch`` event listener.

    The listener is registered with
    ``self.addEventListener('fetch', (event) => { ... })``;
    the body inside that arrow function is what the test
    inspects. Returning the matched text rather than re-parsing
    the whole file keeps the structural assertions tight to the
    handler we care about.
    """
    match = re.search(
        r"self\.addEventListener\(\s*['\"]fetch['\"]\s*,\s*"
        r"\(event\)\s*=>\s*\{(?P<body>.*?)\n\}\s*\)\s*;",
        source,
        re.DOTALL,
    )
    assert match is not None, "fetch event listener not found in sw.js"
    return match.group("body")


def _branch_starts(body: str) -> dict[str, int]:
    """Return the character offset of each routing branch's
    ``if`` line so the test can assert their ordering."""
    api_match = re.search(
        r"if\s*\(\s*url\.pathname\.startsWith\(\s*['\"]/api/['\"]\s*\)\s*\)",
        body,
    )
    nav_match = re.search(
        r"if\s*\(\s*event\.request\.mode\s*===\s*['\"]navigate['\"]\s*\)",
        body,
    )
    return {
        "api": api_match.start() if api_match else -1,
        "navigate": nav_match.start() if nav_match else -1,
    }


def test_fetch_handler_first_branch_is_api_network_only(
    sw_source: str,
) -> None:
    """Branch 1: ``/api/*`` is the FIRST conditional in the
    handler, returns ``fetch(event.request)`` directly, and
    exits via ``return`` so it never falls through to the
    cache. A regression here is the UI-8 P0 bug Codex named.
    """
    body = _fetch_handler_body(sw_source)
    starts = _branch_starts(body)

    assert starts["api"] >= 0, "no /api/* branch in fetch handler"
    assert starts["navigate"] >= 0, "no navigate branch in fetch handler"
    assert starts["api"] < starts["navigate"], (
        "/api/* branch must come BEFORE the navigate branch — "
        "otherwise a navigate request to /api/foo could short-"
        "circuit before the network-only rule fires."
    )

    # Slice to the /api/ branch's block so we can prove it
    # responds with a bare network fetch and returns.
    api_block = body[starts["api"] : starts["navigate"]]
    assert (
        re.search(r"event\.respondWith\(\s*fetch\(\s*event\.request\s*\)\s*\)", api_block)
        is not None
    ), "the /api/* branch must call event.respondWith(fetch(event.request))"
    assert (
        re.search(r"caches\.match", api_block) is None
    ), "the /api/* branch MUST NOT consult caches.match — pin §11.6.4"
    assert (
        re.search(r"\breturn\b", api_block) is not None
    ), "the /api/* branch must return so it does not fall through"


def test_fetch_handler_second_branch_is_navigate_with_offline_fallback(
    sw_source: str,
) -> None:
    """Branch 2: navigation requests try the network first and
    fall back to the cached ``/offline.html`` on rejection.
    Cache-first is forbidden because a stale shell would mask
    a live-but-malformed deploy.
    """
    body = _fetch_handler_body(sw_source)
    starts = _branch_starts(body)
    assert starts["navigate"] > starts["api"]

    # Slice from the navigate `if` to the end of its block.
    # A simple heuristic: the next /api/* block is gone, so the
    # navigate block runs until the cache-first event.respondWith
    # at the bottom of the handler. We grep for the offline
    # fallback INSIDE that slice.
    nav_block = body[starts["navigate"] :]
    assert (
        re.search(
            r"fetch\(\s*event\.request\s*\)\.catch\(\s*\(\s*\)\s*=>\s*"
            r"caches\.match\(\s*['\"]/offline\.html['\"]\s*\)\s*\)",
            nav_block,
        )
        is not None
    ), (
        "navigate branch must be fetch(...).catch(() => caches.match("
        "'/offline.html')) — network first, offline shell on reject."
    )


def test_fetch_handler_third_branch_is_cache_first_for_static_assets(
    sw_source: str,
) -> None:
    """Branch 3: assets fall through to cache-first.

    The implementation is ``caches.match(event.request).then(
    (hit) => hit || fetch(event.request))`` — cache hit serves
    without hitting the network; cache miss falls through to
    network. This is the LAST event.respondWith in the handler.
    """
    body = _fetch_handler_body(sw_source)
    cache_first = re.search(
        r"caches\.match\(\s*event\.request\s*\)\s*\.then\(\s*"
        r"\(hit\)\s*=>\s*hit\s*\|\|\s*fetch\(\s*event\.request\s*\)\s*\)",
        body,
    )
    assert cache_first is not None, (
        "cache-first branch must be the asset fallback at the bottom "
        "of the fetch handler"
    )

    # The cache-first block must come AFTER the navigate branch
    # so the api/* + navigate decisions cannot fall through.
    starts = _branch_starts(body)
    assert (
        cache_first.start() > starts["navigate"]
    ), "cache-first must be the LAST branch in the fetch handler"


def test_api_branch_does_not_share_returns_with_other_branches(
    sw_source: str,
) -> None:
    """Each branch's ``return`` statement is structural — it
    prevents fall-through into the next branch. A regression
    that drops the ``return`` after ``event.respondWith`` would
    let a single request hit MULTIPLE branches before the
    handler exits, and that's the kind of silent miss diff
    review cannot catch reliably.

    Count: at minimum two ``return`` statements before the
    cache-first responder (one for /api/*, one for navigate).
    """
    body = _fetch_handler_body(sw_source)
    cache_first = re.search(
        r"caches\.match\(\s*event\.request\s*\)\s*\.then",
        body,
    )
    assert cache_first is not None
    pre_cache = body[: cache_first.start()]
    returns = re.findall(r"\breturn\b", pre_cache)
    assert len(returns) >= 2, (
        "fetch handler must have >= 2 returns BEFORE the cache-first "
        "branch (api/* and navigate); found "
        f"{len(returns)} — the ordering contract is broken."
    )


# ---------------------------------------------------------------------------
# Cache name discipline
# ---------------------------------------------------------------------------


def test_cache_name_constants_split_pre_and_post_auth(
    sw_source: str,
) -> None:
    """UI-13 §3-H binding: the SW splits its cache into two
    named buckets so a logged-out browser cannot serve PWA
    shell bytes from the SW.

      PRE_AUTH_CACHE_NAME  = 'karasu-ui-login-vN'
      POST_AUTH_CACHE_NAME = 'karasu-ui-vN'

    The bump rule (see sw.js header comment) is binding for
    BOTH names independently. A sw.js diff that touches
    caching without bumping the affected version is a
    regression even if the new value still works at runtime.
    """
    pre_match = re.search(
        r"^const\s+PRE_AUTH_CACHE_NAME\s*=\s*"
        r"'(?P<name>karasu-ui-login-v[0-9a-z]+)'\s*;",
        sw_source,
        re.MULTILINE,
    )
    assert pre_match is not None, (
        "PRE_AUTH_CACHE_NAME must be a top-level const matching "
        "'karasu-ui-login-vN'"
    )
    post_match = re.search(
        r"^const\s+POST_AUTH_CACHE_NAME\s*=\s*"
        r"'(?P<name>karasu-ui-v[0-9a-z]+)'\s*;",
        sw_source,
        re.MULTILINE,
    )
    assert post_match is not None, (
        "POST_AUTH_CACHE_NAME must be a top-level const matching "
        "'karasu-ui-vN'"
    )
    # Pin against accidental shadowing — exactly one canonical
    # declaration of each.
    for name in ("PRE_AUTH_CACHE_NAME", "POST_AUTH_CACHE_NAME"):
        declarations = re.findall(
            rf"^const\s+{name}\s*=", sw_source, re.MULTILINE
        )
        assert len(declarations) == 1, (
            f"{name} declared {len(declarations)} times; "
            "there must be exactly one canonical declaration"
        )


# ---------------------------------------------------------------------------
# UI-12b additive listeners — DEFERRED assertions
# ---------------------------------------------------------------------------
#
# These tests do NOT yet assert the presence of ``push`` /
# ``notificationclick`` listeners — the test commit lands first,
# and the sw.js change lands second per pin §11.6.4. After the
# sw.js change lands (commit 2), the test_ui_sw module gains a
# parallel test that asserts the two new listeners exist AND
# that the four shape-lock tests above STILL pass. The
# pre-existing tests are the regression gate; the new listener
# tests are the additive proof.


# ---------------------------------------------------------------------------
# UI-13 §3-H — pre-auth EXACT set + message handler + page hook
# ---------------------------------------------------------------------------


def _precache_list(source: str, name: str) -> list[str]:
    """Return the URLs declared in ``const <name> = [...]``."""
    match = re.search(
        rf"^const\s+{name}\s*=\s*\[(?P<body>.*?)\];",
        source,
        re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"{name} not found in sw.js"
    return re.findall(r"'([^']+)'", match.group("body"))


def test_pre_auth_precache_matches_brief_3h_exact_set(sw_source: str) -> None:
    """UI-13 §3-H lines 1007-1024 binding EXACT set:

       /
       /assets/css/login.css
       /assets/css/tokens.css
       /assets/css/reset.css
       /assets/css/base.css
       /assets/crow/crow.svg
       /assets/icons/karasu-192.png
       /assets/manifest.json
       /assets/fonts/*.woff2 (entire dir)

    The PWA app shell, push.js, modals, and 512.png + crow-
    flight.svg are explicitly EXCLUDED at lines 1030-1036.
    """
    urls = set(_precache_list(sw_source, "PRE_AUTH_PRECACHE_URLS"))

    required = {
        "/",
        "/assets/css/login.css",
        "/assets/css/tokens.css",
        "/assets/css/reset.css",
        "/assets/css/base.css",
        "/assets/crow/crow.svg",
        "/assets/icons/karasu-192.png",
        "/assets/manifest.json",
    }
    missing = required - urls
    assert not missing, f"pre-auth precache missing required keys: {missing}"

    # Forbidden keys per §3-H lines 1030-1036.
    forbidden = {
        "/index.html",
        "/offline.html",
        "/assets/js/push.js",
        "/assets/icons/karasu-512.png",
        "/assets/crow/crow-flight.svg",
        "/assets/css/timeline.css",
        "/assets/css/crow.css",
        "/assets/css/map.css",
        "/assets/css/drawer.css",
    }
    leaked = forbidden & urls
    assert not leaked, (
        f"pre-auth precache MUST NOT include PWA-shell assets: {leaked}"
    )

    # Fonts dir is binding "entire dir stays cached pre-auth".
    fonts = {u for u in urls if u.startswith("/assets/fonts/")}
    assert fonts, "pre-auth precache must include /assets/fonts/*.woff2"
    for u in fonts:
        assert u.endswith(".woff2"), f"unexpected non-woff2 font asset: {u}"


def test_post_auth_precache_excludes_pre_auth_set(sw_source: str) -> None:
    """The post-auth list must not duplicate items already in
    the pre-auth set — otherwise a cache version bump on one
    side leaves the other holding stale bytes for the same
    URL key."""
    pre = set(_precache_list(sw_source, "PRE_AUTH_PRECACHE_URLS"))
    post = set(_precache_list(sw_source, "POST_AUTH_PRECACHE_URLS"))
    overlap = pre & post
    assert not overlap, (
        f"pre-auth and post-auth precache lists overlap: {overlap}"
    )

    # The PWA shell delta MUST be in post-auth — these are the
    # bus-capable assets that must NEVER be served pre-auth.
    expected_post = {
        "/offline.html",
        "/assets/js/push.js",
        "/assets/css/timeline.css",
    }
    missing = expected_post - post
    assert not missing, f"post-auth precache missing: {missing}"


def test_install_handler_opens_pre_auth_cache_only(sw_source: str) -> None:
    """The install handler must open PRE_AUTH_CACHE_NAME (not
    the post-auth bucket) so a logged-out browser's first
    visit pre-caches only the §3-H login surface."""
    install_match = re.search(
        r"self\.addEventListener\(\s*['\"]install['\"].*?\n\}\s*\)\s*;",
        sw_source,
        re.DOTALL,
    )
    assert install_match is not None
    install_body = install_match.group(0)
    assert "PRE_AUTH_CACHE_NAME" in install_body, (
        "install handler must open PRE_AUTH_CACHE_NAME"
    )
    assert "POST_AUTH_CACHE_NAME" not in install_body, (
        "install handler MUST NOT touch POST_AUTH_CACHE_NAME — "
        "the post-auth cache fills lazily on auth:granted"
    )


def test_activate_handler_keeps_both_canonical_caches(sw_source: str) -> None:
    """The activate cleanup must preserve BOTH PRE_AUTH and
    POST_AUTH cache names — deleting either would force a
    re-precache cycle on every chunk bump."""
    activate_match = re.search(
        r"self\.addEventListener\(\s*['\"]activate['\"].*?\n\}\s*\)\s*;",
        sw_source,
        re.DOTALL,
    )
    assert activate_match is not None
    body = activate_match.group(0)
    assert "PRE_AUTH_CACHE_NAME" in body
    assert "POST_AUTH_CACHE_NAME" in body


def test_message_handler_swaps_caches_on_auth_events(
    sw_source: str,
) -> None:
    """UI-13 §3-H lines 1038-1045 binding:

      auth:granted → open POST_AUTH_CACHE_NAME, addAll
                     POST_AUTH_PRECACHE_URLS.
      auth:revoked → caches.delete(POST_AUTH_CACHE_NAME).

    The pre-auth cache is NEVER touched by either branch
    (revocation falls back to the existing pre-auth cache;
    granting the second time is a no-op precache repeat)."""
    msg_match = re.search(
        r"self\.addEventListener\(\s*['\"]message['\"].*?\n\}\s*\)\s*;",
        sw_source,
        re.DOTALL,
    )
    assert msg_match is not None, (
        "message handler missing — UI-13 §3-H requires it"
    )
    body = msg_match.group(0)

    # auth:granted branch.
    assert re.search(r"['\"]auth:granted['\"]", body), (
        "auth:granted branch missing"
    )
    assert "POST_AUTH_CACHE_NAME" in body
    assert "POST_AUTH_PRECACHE_URLS" in body

    # auth:revoked branch.
    assert re.search(r"['\"]auth:revoked['\"]", body), (
        "auth:revoked branch missing"
    )
    assert re.search(r"caches\.delete\(\s*POST_AUTH_CACHE_NAME\s*\)", body), (
        "auth:revoked must caches.delete(POST_AUTH_CACHE_NAME)"
    )


# ---------------------------------------------------------------------------
# UI-13 §3-H — page-side fetch interceptor
# ---------------------------------------------------------------------------


INDEX_HTML_PATH = (
    REPO_ROOT / "src" / "karasu" / "ui" / "static" / "index.html"
)
LOGIN_HTML_PATH = (
    REPO_ROOT / "src" / "karasu" / "ui" / "static" / "login.html"
)


def test_index_html_wraps_fetch_for_auth_revocation() -> None:
    """index.html must wrap window.fetch so an /api/* response
    of 401 OR a redirect-to-/ posts auth:revoked to the SW.
    §3-H test surface lines 1087-1099 binding."""
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")
    # The wrapper assigns to window.fetch.
    assert re.search(r"window\.fetch\s*=\s*function", html), (
        "index.html must override window.fetch with an interceptor"
    )
    # Detection branches: status 401 OR redirected.
    assert "401" in html, "interceptor must check response.status === 401"
    assert "redirected" in html, (
        "interceptor must check response.redirected for /auth flow"
    )
    # Posts auth:revoked.
    assert re.search(r"['\"]auth:revoked['\"]", html), (
        "interceptor must postMessage({type:'auth:revoked'})"
    )
    # Only wraps /api/* paths so static assets / nav don't trip
    # the revocation flow.
    assert re.search(r"/api/", html), (
        "interceptor must only act on /api/* requests"
    )


def test_index_html_attaches_csrf_header_on_mutating_api_calls() -> None:
    """UI-13 §3-F + pin §11.6.14 binding: every existing
    UI-10 / UI-11b / UI-12b mutating call must attach the
    ``X-Karasu-CSRF`` header read from the ``karasu_csrf``
    cookie. The chunk-8 implementation centralises this in
    the same window.fetch wrapper that handles auth:revoked
    so individual call sites stay untouched and future
    mutating endpoints inherit the contract."""
    html = INDEX_HTML_PATH.read_text(encoding="utf-8")

    # The wrapper reads karasu_csrf cookie at request time.
    assert "karasu_csrf=" in html, (
        "index.html must read the karasu_csrf cookie "
        "(NOT HttpOnly per §3-F so the JS layer can read it)"
    )
    # The wrapper sets the X-Karasu-CSRF header.
    assert "X-Karasu-CSRF" in html, (
        "index.html must set the X-Karasu-CSRF header"
    )
    # The wrapper restricts attachment to mutating methods.
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        assert f"'{method}'" in html, (
            f"mutating method {method} must be in the attach allowlist"
        )
    # Attachment is /api/*-scoped — the same gate that the
    # auth:revoked branch uses, so login.html and other
    # non-/api fetches are unaffected.
    assert "/api/" in html


def test_login_html_emits_auth_granted_on_success() -> None:
    """login.html success path must postMessage auth:granted to
    the SW so the post-auth cache fills before navigation lands
    at the PWA shell. §3-H lines 1038-1042 binding."""
    html = LOGIN_HTML_PATH.read_text(encoding="utf-8")
    assert re.search(r"['\"]auth:granted['\"]", html), (
        "login.html must postMessage({type:'auth:granted'}) on success"
    )
    # The postMessage must be inside the success branch (r.ok).
    success_match = re.search(
        r"r\.ok\s*\)\s*\{(?P<body>.*?)window\.location\.assign",
        html,
        re.DOTALL,
    )
    assert success_match is not None, (
        "login.html success branch not found"
    )
    assert "auth:granted" in success_match.group("body"), (
        "auth:granted must fire BEFORE the navigation reload"
    )


# ---------------------------------------------------------------------------
# UI-12b additive listeners — DEFERRED assertions
# ---------------------------------------------------------------------------
#
# These tests do NOT yet assert the presence of ``push`` /
# ``notificationclick`` listeners — the test commit lands first,
# and the sw.js change lands second per pin §11.6.4. After the
# sw.js change lands (commit 2), the test_ui_sw module gains a
# parallel test that asserts the two new listeners exist AND
# that the four shape-lock tests above STILL pass. The
# pre-existing tests are the regression gate; the new listener
# tests are the additive proof.


def test_install_handler_uses_skip_waiting(sw_source: str) -> None:
    """``self.skipWaiting()`` is the install handler's contract
    so a freshly-installed SW activates on the next page load
    without requiring a manual refresh. Pinned because dropping
    it would break the cache-bump → cleanup → control flow."""
    install_match = re.search(
        r"self\.addEventListener\(\s*['\"]install['\"].*?self\.skipWaiting\(\s*\)",
        sw_source,
        re.DOTALL,
    )
    assert install_match is not None, (
        "install handler must call self.skipWaiting()"
    )


def test_activate_handler_claims_clients(sw_source: str) -> None:
    """``self.clients.claim()`` lets the activated SW take
    control of clients that were already loaded under the
    previous SW. Without it, the operator has to refresh twice
    after a cache bump for the new fetch ordering to apply."""
    activate_match = re.search(
        r"self\.addEventListener\(\s*['\"]activate['\"].*?self\.clients\.claim\(\s*\)",
        sw_source,
        re.DOTALL,
    )
    assert activate_match is not None, (
        "activate handler must call self.clients.claim()"
    )
