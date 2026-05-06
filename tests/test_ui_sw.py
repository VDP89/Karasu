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


def test_cache_name_constant_exists_and_is_versioned(
    sw_source: str,
) -> None:
    """``CACHE_NAME`` is the bump-versioned constant whose value
    the activate handler diffs against to delete stale caches.
    The bump rule (see sw.js header comment) is binding; a
    sw.js diff that touches caching without bumping CACHE_NAME
    is a regression even if the new value still works at runtime.

    The test pins:
      - ``CACHE_NAME`` is a top-level ``const`` (not a let / var).
      - Value matches ``karasu-ui-vN`` shape (N = chunk version).
    """
    match = re.search(
        r"^const\s+CACHE_NAME\s*=\s*'(?P<name>karasu-ui-v[0-9a-z]+)'\s*;",
        sw_source,
        re.MULTILINE,
    )
    assert match is not None, (
        "CACHE_NAME must be a top-level const matching "
        "'karasu-ui-vN'"
    )
    # Pin against accidental shadowing — there must be exactly
    # one declaration.
    declarations = re.findall(r"^const\s+CACHE_NAME\s*=", sw_source, re.MULTILINE)
    assert len(declarations) == 1, (
        f"CACHE_NAME declared {len(declarations)} times; "
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
