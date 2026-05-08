"""SW update lifecycle shape-lock test (UI-14 §3-F SW Update
Lifecycle Lock — anticipated pin §11.6).

UI-14 §3-F is the ONLY explicit deviation from a prior shape-
lock that UI-14 earns. UI-8 sealed
``self.skipWaiting() + self.clients.claim()`` as the SW
lifecycle. UI-14 §3-F supersedes that for UPDATE events while
preserving the FIRST-LOAD shape:

  FIRST-LOAD (no existing controller): skipWaiting + claim,
                                       same as UI-8.
  UPDATE     (existing controller present): NEITHER. The new
                                       SW installs as
                                       "waiting" until the
                                       page posts
                                       {type:"SKIP_WAITING"}
                                       in response to the
                                       footer Refresh button
                                       (§3-B / §11.6.9).

This test pins three surfaces structurally (lint-style, no
browser dependency):

  1. sw.js install / activate / message handler discipline +
     activate broadcast of install-prompt-reset + cache name
     bump v13 → v14 + POST_AUTH precache extensions.
  2. The fetch handler is UNCHANGED — UI-14 §3-F bounded the
     deviation to install + activate + message handlers. The
     pre-auth / post-auth cache split (UI-13 §3-H) and fetch
     ordering (UI-12b §11.6.4) are sealed and tested by
     test_ui_sw.py; this file pins the negative-shape
     boundary so a future edit cannot smuggle a fetch /
     cache-routing change under the §3-F umbrella.
  3. install.js page-side update lifecycle: 60-minute poll
     cadence, registration.update() call, state 'update'
     present, refresh button → SKIP_WAITING postMessage,
     controllerchange → reload.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static"
SW_PATH = STATIC_DIR / "sw.js"
INSTALL_JS_PATH = STATIC_DIR / "js" / "install.js"
INDEX_HTML_PATH = STATIC_DIR / "index.html"

# UI-14 cache names. v13 → v14 forces a clean swap on first
# activation under UI-14.
EXPECTED_PRE_AUTH_CACHE = "karasu-ui-login-v14"
EXPECTED_POST_AUTH_CACHE = "karasu-ui-v14"


def _strip_js_comments(source: str) -> str:
    """Remove /* ... */ + // comments so token assertions only
    inspect executable code, not contract narration."""
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    source = re.sub(r"//[^\n]*", "", source)
    return source


@pytest.fixture(scope="module")
def sw_source() -> str:
    assert SW_PATH.is_file(), f"sw.js not found at {SW_PATH}"
    return SW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def sw_code(sw_source: str) -> str:
    return _strip_js_comments(sw_source)


@pytest.fixture(scope="module")
def install_js_source() -> str:
    assert INSTALL_JS_PATH.is_file(), f"install.js not found at {INSTALL_JS_PATH}"
    return INSTALL_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_js_code(install_js_source: str) -> str:
    return _strip_js_comments(install_js_source)


@pytest.fixture(scope="module")
def index_html() -> str:
    assert INDEX_HTML_PATH.is_file()
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 1A — sw.js cache names bumped to v14
# ---------------------------------------------------------------------------


def test_sw_pre_auth_cache_bumped_to_v14(sw_source: str) -> None:
    pattern = re.compile(
        r"const\s+PRE_AUTH_CACHE_NAME\s*=\s*['\"]"
        + re.escape(EXPECTED_PRE_AUTH_CACHE)
        + r"['\"]"
    )
    assert pattern.search(sw_source), (
        f"sw.js does not declare PRE_AUTH_CACHE_NAME = "
        f"{EXPECTED_PRE_AUTH_CACHE!r}. UI-14 bumps v13 → v14 to "
        f"force a clean swap of the pre-auth cache (manifest "
        f"body + icons changed)."
    )


def test_sw_post_auth_cache_bumped_to_v14(sw_source: str) -> None:
    pattern = re.compile(
        r"const\s+POST_AUTH_CACHE_NAME\s*=\s*['\"]"
        + re.escape(EXPECTED_POST_AUTH_CACHE)
        + r"['\"]"
    )
    assert pattern.search(sw_source), (
        f"sw.js does not declare POST_AUTH_CACHE_NAME = "
        f"{EXPECTED_POST_AUTH_CACHE!r}. UI-14 bumps v13 → v14 "
        f"to force a clean swap of the post-auth cache "
        f"(install.js + maskable PNGs added)."
    )


# ---------------------------------------------------------------------------
# 1B — POST_AUTH precache list extensions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "asset",
    [
        "/assets/icons/karasu-maskable-192.png",
        "/assets/icons/karasu-maskable-512.png",
        "/assets/js/install.js",
    ],
)
def test_post_auth_precache_extended(sw_source: str, asset: str) -> None:
    """UI-14 §3-A maskable PNGs + §3-B install.js belong to the
    authenticated PWA shell; precaching them under the post-auth
    bucket keeps the offline shell intact."""
    assert asset in sw_source, (
        f"sw.js POST_AUTH_PRECACHE_URLS is missing UI-14 asset "
        f"{asset!r}."
    )


# ---------------------------------------------------------------------------
# 2 — install handler: skipWaiting ONLY on first-load
# ---------------------------------------------------------------------------


def test_sw_install_skipwaiting_is_conditional(sw_code: str) -> None:
    """§3-F SEALED: the new SW must NOT call skipWaiting on
    UPDATE events. The implementation gates the call behind a
    first-load detector. A bare ``self.skipWaiting()`` outside
    a conditional is a regression to the UI-8 lifecycle."""
    # Find every skipWaiting call in install handler.
    install_block = _extract_handler_body(sw_code, "install")
    assert install_block is not None, "install handler not found in sw.js"
    # Must contain a skipWaiting call.
    assert "skipWaiting" in install_block, (
        "install handler does not call skipWaiting at all — "
        "first-load PWAs would never activate. Restore the "
        "first-load branch."
    )
    # The call must be inside a branch — heuristic: the literal
    # "skipWaiting" appears after at least one ``if`` keyword in
    # the install body. Use \b boundaries to survive arbitrary
    # indentation (newline + spaces before ``if``) without
    # false-matching identifiers that contain "if".
    pre_skip = install_block.split("skipWaiting", 1)[0]
    assert re.search(r"\bif\s*\(", pre_skip), (
        "install handler calls skipWaiting unconditionally — "
        "§3-F SEALED requires gating on first-load (no existing "
        "controller). UI-8 unconditional behaviour regressed."
    )


def test_sw_install_first_load_helper_present(sw_code: str) -> None:
    """The first-load helper distinguishes update from initial
    install. Present as a callable in the SW so the gate is
    auditable from a single point."""
    pattern = re.compile(
        r"function\s+isFirstLoad\s*\(\s*\)|isFirstLoad\s*=\s*function"
    )
    assert pattern.search(sw_code), (
        "sw.js does not declare an isFirstLoad helper — §3-F "
        "expects a single auditable predicate gating the install/"
        "activate fast path."
    )


def test_sw_first_load_frozen_at_install(sw_code: str) -> None:
    """Codex round-2 P1 SEALED — the first-load classification
    must be captured ONCE during install and read frozen during
    activate. Re-reading ``self.registration.active`` inside the
    activate handler would skip clients.claim on the FRESH-
    INSTALL path the brief explicitly preserves: by activate-
    time the new SW has transitioned to activating/activated and
    registration.active references the new worker (not null as
    on first-load).

    The fix is a module-level frozen variable set in install and
    read in activate. This test pins the negative shape: the
    activate handler must NOT contain the literal
    ``self.registration.active`` (the only legitimate read site
    is install-time + the helper-internal capture)."""
    activate_block = _extract_handler_body(sw_code, "activate")
    assert activate_block is not None, "activate handler not found"
    assert "self.registration.active" not in activate_block, (
        "activate handler re-reads self.registration.active. "
        "Codex round-2 P1: capture the first-load classification "
        "ONCE in install (e.g. ``_firstLoadClassification = "
        "!self.registration.active``) and reuse the frozen value "
        "in activate via the isFirstLoad() helper. By activate-"
        "time the new SW has transitioned and the predicate "
        "flips to false even on a fresh install — clients.claim "
        "would be skipped, breaking the §3-F SEALED preservation "
        "of the UI-8 first-load behaviour."
    )
    install_block = _extract_handler_body(sw_code, "install")
    assert install_block is not None, "install handler not found"
    # The capture should happen in install: a write to a module-
    # level variable that isFirstLoad() later reads. We check for
    # the assignment shape rather than a specific variable name
    # so a refactor that renames the variable still passes.
    capture_pattern = re.compile(
        r"_firstLoadClassification\s*=\s*[!\(]"
        r"|"
        r"firstLoad\s*=\s*[!\(]"
    )
    assert capture_pattern.search(install_block), (
        "install handler does not capture the first-load "
        "classification into a module-level variable — without "
        "the capture there is nothing for activate to read frozen."
    )


# ---------------------------------------------------------------------------
# 3 — activate handler: clients.claim ONLY on first-load
# ---------------------------------------------------------------------------


def test_sw_activate_clientsclaim_is_conditional(sw_code: str) -> None:
    activate_block = _extract_handler_body(sw_code, "activate")
    assert activate_block is not None, "activate handler not found"
    assert "clients.claim" in activate_block, (
        "activate handler does not call clients.claim — fresh "
        "PWA installs would never take over open clients."
    )
    pre_claim = activate_block.split("clients.claim", 1)[0]
    assert re.search(r"\bif\s*\(", pre_claim), (
        "activate handler calls clients.claim unconditionally — "
        "§3-F SEALED requires gating on first-load."
    )


# ---------------------------------------------------------------------------
# 4 — activate broadcasts install-prompt-reset
# ---------------------------------------------------------------------------


def test_sw_activate_broadcasts_install_prompt_reset(sw_source: str) -> None:
    """§3-B / §11.6.9 — on every activate the SW posts
    install-prompt-reset to all open clients so install.js
    clears its 30-day dismiss key. Uses matchAll with
    includeUncontrolled:true to reach tabs that still answer
    to the previous SW (we can't depend on clients.claim per
    §3-F)."""
    # The broadcast must reference both the matchAll shape AND
    # the message type literal.
    assert "matchAll" in sw_source, (
        "sw.js activate handler does not call clients.matchAll "
        "to broadcast install-prompt-reset."
    )
    assert "includeUncontrolled" in sw_source, (
        "sw.js does not pass includeUncontrolled to matchAll — "
        "tabs answering to the previous SW would not receive "
        "the install-prompt-reset broadcast."
    )
    assert '"install-prompt-reset"' in sw_source or (
        "'install-prompt-reset'" in sw_source
    ), (
        "sw.js does not post a {type:'install-prompt-reset'} "
        "message anywhere — the install dismiss reset contract "
        "is not implemented."
    )


# ---------------------------------------------------------------------------
# 5 — SKIP_WAITING message handler
# ---------------------------------------------------------------------------


def test_sw_message_handles_skip_waiting(sw_code: str) -> None:
    """§3-F SEALED — the SW listens for {type:'SKIP_WAITING'}
    posted by install.js when the user clicks Refresh, and
    calls self.skipWaiting() with no other side effect.

    The literal token must appear in EXECUTABLE CODE (not just
    a comment) and must be part of a conditional that calls
    skipWaiting."""
    assert "SKIP_WAITING" in sw_code, (
        "sw.js does not handle the SKIP_WAITING message type — "
        "the Refresh affordance has no SW counterparty."
    )
    # The SKIP_WAITING branch must call skipWaiting itself.
    skip_branch_pattern = re.compile(
        r"SKIP_WAITING['\"][^{}]*?\)\s*\{[^{}]*?skipWaiting"
        r"|"
        r"data\.type\s*===\s*['\"]SKIP_WAITING['\"][^{}]*?skipWaiting",
        re.DOTALL,
    )
    assert skip_branch_pattern.search(sw_code), (
        "sw.js handles SKIP_WAITING but does not call "
        "self.skipWaiting() inside the branch."
    )


# ---------------------------------------------------------------------------
# 6 — fetch handler UNCHANGED (regression boundary)
# ---------------------------------------------------------------------------


def test_sw_fetch_handler_still_present(sw_code: str) -> None:
    """§3-F SEALED bounded the lifecycle deviation to install +
    activate + message handlers. The fetch handler must still
    exist; test_ui_sw.py pins its ordering — this test pins
    the existence so a deletion under §3-F's banner is
    impossible."""
    assert "addEventListener('fetch'" in sw_code or (
        'addEventListener("fetch"' in sw_code
    ), (
        "sw.js fetch handler removed — §3-F SEALED bounded the "
        "lifecycle change to install/activate/message handlers; "
        "fetch is OUT OF SCOPE."
    )


def test_sw_fetch_handler_branches_unchanged(sw_code: str) -> None:
    """Sanity-check the three sealed fetch branches are still
    referenced (api network-only, navigation network-first,
    static cache-first). Detailed ordering test lives in
    test_ui_sw.py; this is a smoke check tying the negative-
    shape boundary."""
    assert "/api/" in sw_code, "fetch handler missing /api/* branch"
    assert "navigate" in sw_code, "fetch handler missing navigation branch"
    assert "caches.match" in sw_code, (
        "fetch handler missing cache-first static branch"
    )


# ---------------------------------------------------------------------------
# 7 — install.js page-side update lifecycle
# ---------------------------------------------------------------------------


def test_install_js_polls_60_minutes(install_js_code: str) -> None:
    """§3-F SEALED at 60-minute poll cadence. Constant must be
    the exact ms expression so a future edit to 30 / 90 / etc.
    breaks the test and forces an explicit brief amendment."""
    pattern = re.compile(r"60\s*\*\s*60\s*\*\s*1000")
    assert pattern.search(install_js_code), (
        "install.js does not declare the 60-minute update poll "
        "interval as `60 * 60 * 1000` ms."
    )


def test_install_js_calls_registration_update(install_js_code: str) -> None:
    """install.js must call registration.update() inside the
    polling tick — that's how the browser is asked to fetch a
    fresh sw.js. ``setInterval`` alone without the .update()
    call is dead code."""
    assert "setInterval" in install_js_code, (
        "install.js does not schedule the update poll via "
        "setInterval."
    )
    assert ".update(" in install_js_code, (
        "install.js does not call registration.update() inside "
        "the polling tick."
    )


def test_install_js_listens_for_updatefound(install_js_code: str) -> None:
    """§3-F SEALED — the page learns of a waiting SW via
    registration.addEventListener('updatefound', ...) +
    statechange to 'installed' on the new SW. Without this
    wiring, the refresh affordance never surfaces between
    poll ticks."""
    assert "updatefound" in install_js_code, (
        "install.js does not listen for the registration "
        "'updatefound' event."
    )
    assert "statechange" in install_js_code, (
        "install.js does not listen for the installing SW's "
        "'statechange' event."
    )


def test_install_js_has_update_state(install_js_code: str) -> None:
    """The five-state machine includes 'update' (mutual-
    exclusion winner per §11.6.9)."""
    assert "'update'" in install_js_code or '"update"' in install_js_code, (
        "install.js does not reference the sealed 'update' "
        "state — §11.6.9 mutual exclusion contract not "
        "implemented."
    )


def test_install_js_refresh_posts_skip_waiting(install_js_code: str) -> None:
    """The Refresh click handler posts SKIP_WAITING to the
    waiting SW. Without this, clicking Refresh does nothing
    and the new SW stays waiting indefinitely."""
    assert "SKIP_WAITING" in install_js_code, (
        "install.js Refresh handler does not post SKIP_WAITING."
    )
    assert "postMessage" in install_js_code, (
        "install.js does not call postMessage — Refresh button "
        "cannot signal the waiting SW."
    )


def test_install_js_reloads_on_controllerchange(install_js_code: str) -> None:
    """§3-F SEALED — when the new SW takes over after
    SKIP_WAITING, the page reloads so the operator sees the
    new shell. Without this, the user sees the old shell
    served by the new SW until manual refresh."""
    assert "controllerchange" in install_js_code, (
        "install.js does not register a controllerchange "
        "listener."
    )
    assert "location.reload" in install_js_code, (
        "install.js does not call window.location.reload() — "
        "the new SW takes over but the page never refreshes "
        "to render under it."
    )


# ---------------------------------------------------------------------------
# 8 — index.html: refresh button in markup
# ---------------------------------------------------------------------------


def test_index_html_has_refresh_button(index_html: str) -> None:
    """The Refresh button must exist in static markup so
    install.js can show/hide it via render(). Creating the
    button dynamically would couple §11.6.9 mutual-exclusion
    layout to JS execution — the brief expects the affordance
    surface to be inert until JS upgrades it."""
    pattern = re.compile(
        r"<button[^>]*class=['\"][^'\"]*footer-install-refresh"
        r"[^'\"]*['\"]",
        re.IGNORECASE,
    )
    assert pattern.search(index_html), (
        "index.html does not declare a button with class "
        "footer-install-refresh inside the footer-install slot."
    )


def test_index_html_refresh_button_starts_hidden(index_html: str) -> None:
    """The refresh button must ship with the ``hidden`` attribute
    so it is invisible until install.js render() flips it. A
    visible-by-default button would render mid-page-load before
    install.js decides the state."""
    pattern = re.compile(
        r"<button[^>]*class=['\"][^'\"]*footer-install-refresh"
        r"[^'\"]*['\"][^>]*\bhidden\b",
        re.IGNORECASE | re.DOTALL,
    )
    assert pattern.search(index_html), (
        "footer-install-refresh button is not marked hidden in "
        "static markup — it would render briefly on first paint."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_handler_body(source: str, event_name: str) -> str | None:
    """Return the body of the addEventListener('<event>', ...)
    callback so per-handler assertions don't get false positives
    from unrelated parts of sw.js. Returns None if the handler
    is missing (a separate test surfaces that as a higher-
    priority failure than a body-content drift)."""
    pattern = re.compile(
        r"addEventListener\(\s*['\"]"
        + re.escape(event_name)
        + r"['\"]\s*,\s*\(?[^)]*\)?\s*=>\s*\{",
    )
    match = pattern.search(source)
    if match is None:
        return None
    # Walk the brace-balanced body starting at the opening { of
    # the arrow function so nested if/try/etc. stay inside.
    start = match.end() - 1  # pointer to the opening {
    depth = 0
    end = None
    for i in range(start, len(source)):
        c = source[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        return None
    return source[start + 1:end]
