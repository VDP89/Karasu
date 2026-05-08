"""PWA install affordance shape-lock test (UI-14 pin §11.6 —
install contract).

UI-14 §3-B seals the install affordance shape: footer slot only,
NO modal anywhere (incl iOS), NO banner, NO toast, four-state
machine, persistent dismiss in localStorage under exactly
``karasu.install.dismissed_at`` with a 30-day re-show window
plus reset-on-SW-activation broadcast.

This test pins the contract structurally — same lint-style
pattern as ``test_ui_sw.py`` and ``test_ui_icons.py``: pure
Python, no browser dependency, runs in plain ``pytest``. The
install behaviour itself is JS code that requires a real
browser to exercise; the test surface here is the SOURCE
INVARIANTS that prevent silent regressions of the sealed
shape (e.g. someone accidentally changes the localStorage key,
introduces a modal, or drops the SW message listener).

Layers:

    1. install.js exists, is loaded by index.html, lives at the
       canonical /assets/js/install.js URL.
    2. localStorage key is exactly the sealed value, used both
       on read + write.
    3. 30-day re-show window present as a constant.
    4. Four-state machine is exhaustive: unsupported, available,
       ready, installed.
    5. SW message listener wired for {type:"install-prompt-reset"}.
    6. NO modal-class invocation, NO banner / toast token (UI-14
       §3-B SEALED rejection of all chrome-inside-the-app for
       the install prompt).
    7. iOS hint copy is exact (sealed verbatim in the brief).
    8. Footer slot id + state class set are exactly what
       index.html ships.
    9. index.html theme-color meta is aligned to --bg-0
       (#0a0a0b) — extends §3-A drift correction to the HTML
       surface so the browser address-bar tint matches the
       installed splash.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static"
INSTALL_JS_PATH = STATIC_DIR / "js" / "install.js"
INDEX_HTML_PATH = STATIC_DIR / "index.html"

INSTALL_JS_URL = "/assets/js/install.js"

# Sealed in §3-B literal verbatim. A drift here is a brief
# violation, not a typo — fail loudly.
SEALED_STORAGE_KEY = "karasu.install.dismissed_at"
SEALED_FOOTER_ID = "footer-install"
SEALED_STATES = ("unsupported", "available", "ready", "installed")
SEALED_IOS_HINT = "(Share → Add to Home Screen)"
SEALED_SW_MESSAGE_TYPE = "install-prompt-reset"
SEALED_THEME_COLOR = "#0a0a0b"


def _strip_js_comments(source: str) -> str:
    """Remove ``/* ... */`` block comments and ``//`` line
    comments. The forbidden-token assertions in Layer 6 below
    inspect EXECUTABLE CODE only — the file header documents
    what UI-14 §3-B forbids, so the words "banner" and "toast"
    legitimately appear in narration and would false-positive
    against a raw substring check."""
    # Block comments — DOTALL so newlines inside are consumed.
    source = re.sub(r"/\*[\s\S]*?\*/", "", source)
    # Line comments.
    source = re.sub(r"//[^\n]*", "", source)
    return source


@pytest.fixture(scope="module")
def install_js() -> str:
    assert INSTALL_JS_PATH.is_file(), (
        f"install.js not found at {INSTALL_JS_PATH}"
    )
    return INSTALL_JS_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_js_code(install_js: str) -> str:
    """Comment-stripped variant for forbidden-token checks."""
    return _strip_js_comments(install_js)


@pytest.fixture(scope="module")
def index_html() -> str:
    assert INDEX_HTML_PATH.is_file(), (
        f"index.html not found at {INDEX_HTML_PATH}"
    )
    return INDEX_HTML_PATH.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Layer 1 — file + script tag
# ---------------------------------------------------------------------------


def test_install_js_loaded_by_index_html(index_html: str) -> None:
    """index.html must reference /assets/js/install.js. The
    pattern mirrors push.js — synchronous load before the
    inline init block."""
    pattern = re.compile(
        r'<script\s+[^>]*src=["\']' + re.escape(INSTALL_JS_URL) + r'["\'][^>]*>'
    )
    assert pattern.search(index_html), (
        f"index.html does not reference {INSTALL_JS_URL}"
    )


# ---------------------------------------------------------------------------
# Layer 2 — localStorage key sealed verbatim
# ---------------------------------------------------------------------------


def test_storage_key_sealed_verbatim(install_js: str) -> None:
    """§3-B SEALED: the localStorage key is
    ``karasu.install.dismissed_at`` (snake_case after the dot).
    A camelCase or alternative drift breaks the contract that
    feedback / dogfood / debug tooling expects."""
    occurrences = install_js.count(f'"{SEALED_STORAGE_KEY}"')
    occurrences += install_js.count(f"'{SEALED_STORAGE_KEY}'")
    assert occurrences >= 1, (
        f"install.js does not declare the sealed localStorage key "
        f"{SEALED_STORAGE_KEY!r}. A drift to dismissedAt or any "
        f"other spelling violates §3-B SEALED."
    )


def test_storage_key_camelcase_drift_rejected(install_js: str) -> None:
    """The brief explicitly uses snake_case. Catch the most
    likely drift (camelCase ``dismissedAt``) so a future edit
    doesn't silently break the contract."""
    assert "dismissedAt" not in install_js, (
        "install.js contains a camelCase 'dismissedAt' — §3-B "
        "SEALED snake_case 'dismissed_at'. Fix the storage key."
    )


# ---------------------------------------------------------------------------
# Layer 3 — 30-day re-show window
# ---------------------------------------------------------------------------


def test_reshow_window_is_30_days(install_js: str) -> None:
    """§3-B SEALED at 30 days. The constant is computed as
    ``30 * 24 * 60 * 60 * 1000`` (ms) so the literal numeric
    expression is the lint surface — a future edit to 7 or 90
    days breaks the test and forces an explicit brief amendment."""
    pattern = re.compile(r"30\s*\*\s*24\s*\*\s*60\s*\*\s*60\s*\*\s*1000")
    assert pattern.search(install_js), (
        "install.js does not declare the 30-day re-show window "
        "as `30 * 24 * 60 * 60 * 1000`. A different numeric "
        "expression may still represent 30 days but the contract "
        "is the literal expression."
    )


# ---------------------------------------------------------------------------
# Layer 4 — four-state machine exhaustive
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", SEALED_STATES)
def test_each_sealed_state_is_referenced(install_js: str, state: str) -> None:
    """All four §3-B states must appear in install.js — either
    as a return value of decideState() or as a string passed to
    render(). A missing state means the slot will never reach
    that machine state at runtime."""
    assert f"'{state}'" in install_js or f'"{state}"' in install_js, (
        f"install.js does not reference the sealed state {state!r}. "
        f"§3-B SEALED four states: {SEALED_STATES}."
    )


# ---------------------------------------------------------------------------
# Layer 5 — SW message contract
# ---------------------------------------------------------------------------


def test_sw_message_listener_wired(install_js: str) -> None:
    """install.js must subscribe to navigator.serviceWorker
    'message' events (the channel sw.js postMessages on
    activate). The listener handles {type:"install-prompt-reset"}
    by clearing the dismiss state. The SW broadcast itself
    lands in UI-14 commit 4; the listener is forward-compatible."""
    assert "navigator.serviceWorker" in install_js, (
        "install.js does not access navigator.serviceWorker — "
        "the SW message contract for install-prompt-reset cannot "
        "be honoured."
    )
    assert "addEventListener" in install_js, (
        "install.js does not register an event listener — see "
        "the SW message contract."
    )
    assert SEALED_SW_MESSAGE_TYPE in install_js, (
        f"install.js does not handle the sealed SW message type "
        f"{SEALED_SW_MESSAGE_TYPE!r}."
    )


# ---------------------------------------------------------------------------
# Layer 6 — NO modal anywhere (UI-8 audit pin #5 + §3-B re-bind)
# ---------------------------------------------------------------------------


_FORBIDDEN_INSIDE_APP_TOKENS = (
    # The modal primitive class lives in css/modal.css; the install
    # affordance must NEVER toggle it. Reaching for .modal in
    # install.js would silently introduce the chrome-inside-the-app
    # the brief explicitly forbade for iOS / Android / desktop.
    ".modal",
    # showModal() is the dialog API; a future contributor might
    # reach for it instead. Same prohibition.
    "showModal",
    # First-visit toast / banner attempts.
    "toast",
    "banner",
)


@pytest.mark.parametrize("token", _FORBIDDEN_INSIDE_APP_TOKENS)
def test_no_modal_or_banner_inside_install_js(
    install_js_code: str, token: str
) -> None:
    """§3-B SEALED: NO MODAL ANYWHERE (incl iOS), NO banner, NO
    toast. UI-8 audit pin #5 carry-forward. The install slot is
    the entire affordance surface.

    Inspects the COMMENT-STRIPPED source so the contract narration
    in the file header (which legitimately mentions these tokens
    as ``what we don't do``) is not the trigger."""
    assert token.lower() not in install_js_code.lower(), (
        f"install.js references {token!r} in EXECUTABLE CODE — "
        f"§3-B SEALED forbids modal / banner / toast surfaces for "
        f"the install affordance. The footer slot is the entire "
        f"surface."
    )


# ---------------------------------------------------------------------------
# Layer 7 — iOS hint copy verbatim
# ---------------------------------------------------------------------------


def test_ios_hint_copy_sealed_verbatim(install_js: str) -> None:
    """§3-B SEALED at exactly ``(Share → Add to Home Screen)``.
    The arrow is the U+2192 RIGHTWARDS ARROW; ASCII ``->`` is a
    drift."""
    assert SEALED_IOS_HINT in install_js, (
        f"install.js does not contain the sealed iOS hint copy "
        f"{SEALED_IOS_HINT!r}. The arrow must be U+2192 (→), not "
        f"ASCII '->'."
    )


# ---------------------------------------------------------------------------
# Layer 8 — footer slot id + DOM contract in index.html
# ---------------------------------------------------------------------------


def test_footer_slot_id_exact(install_js: str, index_html: str) -> None:
    """install.js looks up the slot by id; index.html ships an
    element with that exact id. The two surfaces must agree."""
    assert f"'{SEALED_FOOTER_ID}'" in install_js or (
        f'"{SEALED_FOOTER_ID}"' in install_js
    ), (
        f"install.js does not reference the sealed footer id "
        f"{SEALED_FOOTER_ID!r}."
    )
    assert (
        f'id="{SEALED_FOOTER_ID}"' in index_html
        or f"id='{SEALED_FOOTER_ID}'" in index_html
    ), (
        f"index.html does not declare an element with id="
        f"{SEALED_FOOTER_ID!r}."
    )


def test_footer_slot_has_state_hint_dismiss_children(index_html: str) -> None:
    """The slot has three children: state span, hint span,
    dismiss button. install.js renders all three; if a child is
    missing the runtime crashes silently."""
    # Locate the slot block (single line or multi-line).
    slot_match = re.search(
        r'<span[^>]*id=["\']footer-install["\'][^>]*>(.*?)</span>\s*</footer>',
        index_html,
        re.DOTALL,
    )
    assert slot_match is not None, "footer-install slot not found"
    slot_body = slot_match.group(1)
    assert "footer-install-state" in slot_body, (
        "footer-install slot missing .footer-install-state child"
    )
    assert "footer-install-hint" in slot_body, (
        "footer-install slot missing .footer-install-hint child"
    )
    assert "footer-install-dismiss" in slot_body, (
        "footer-install slot missing .footer-install-dismiss button"
    )


# ---------------------------------------------------------------------------
# Layer 9 — HTML <meta name="theme-color"> aligned to --bg-0
# ---------------------------------------------------------------------------


def test_html_meta_theme_color_aligned(index_html: str) -> None:
    """UI-14 extends §3-A drift correction to the HTML surface:
    <meta name="theme-color"> must match manifest theme_color so
    the browser address-bar tint pre-install matches the
    installed splash. UI-13 seed had this at #131316 (= --bg-1);
    UI-14 corrects to #0a0a0b (= --bg-0)."""
    pattern = re.compile(
        r'<meta\s+name=["\']theme-color["\']\s+content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    match = pattern.search(index_html)
    assert match is not None, (
        "index.html does not declare <meta name=\"theme-color\">"
    )
    actual = match.group(1).lower()
    assert actual == SEALED_THEME_COLOR.lower(), (
        f"index.html theme-color meta is {actual} — UI-14 §3-A "
        f"extension aligns to --bg-0 ({SEALED_THEME_COLOR})."
    )


# ---------------------------------------------------------------------------
# Layer 10 — §3-E iOS Safari push copy refinement
# ---------------------------------------------------------------------------
#
# §3-E SEALED — UI-14 refines the COPY of the push footer's
# "unsupported" line on iOS Safari tab to point operators at the
# install affordance ("Install Karasu first"). ZERO new gating
# logic; ZERO change to PushManager.subscribe or any caller —
# only the label string changes for the iOS-Safari-in-tab case.
# Everywhere else the existing "unsupported" label is unchanged.


SEALED_IOS_POINTER_COPY = "Install Karasu first"


def test_index_html_has_ios_safari_tab_helper(index_html: str) -> None:
    """The detection helper must be a named function so the
    branch is auditable from a single point. Inline UA sniffing
    scattered across loadPushState would re-grow the surface
    §3-E sealed shut."""
    assert "isIOSSafariTab" in index_html, (
        "index.html does not declare an isIOSSafariTab helper — "
        "the §3-E iOS push copy refinement has nowhere to anchor."
    )


def test_ios_pointer_copy_sealed_verbatim(index_html: str) -> None:
    """§3-E SEALED at exactly ``Install Karasu first``. A drift
    to ``Install Karasu`` / ``Install required`` / etc. breaks
    the pointer the operator is expected to read."""
    assert SEALED_IOS_POINTER_COPY in index_html, (
        f"index.html does not contain the sealed §3-E pointer "
        f"copy {SEALED_IOS_POINTER_COPY!r}. The COPY refinement "
        f"is the deliverable; do not paraphrase."
    )


def test_ios_pointer_does_not_alter_subscribe_path(index_html: str) -> None:
    """§3-E SEALED ZERO-change pin: the iOS pointer touches
    the LABEL inside renderPushFooter only. The subscribe call
    site (push.js) is out of scope; the gating predicates
    (browserPushSupport / wirePushFooter) are out of scope.
    This negative-shape test fails if a future edit attempts
    to gate the subscribe call on isIOSSafariTab."""
    # The helper must NOT appear inside browserPushSupport's
    # body or be referenced by wirePushFooter / push.js's
    # subscribe path. The cheapest static proxy: it appears
    # ONLY in the label-selection branch (loadPushState
    # 'unsupported' arm). Count occurrences as a smoke check.
    occurrences = index_html.count("isIOSSafariTab")
    # 1 declaration + 1 call site = 2 expected. Anything more
    # is a regression (the helper leaked into other branches).
    assert occurrences <= 3, (
        f"isIOSSafariTab is referenced {occurrences} times — "
        f"§3-E SEALED restricts it to the push footer label "
        f"refinement only. Suspect leak into "
        f"browserPushSupport / wirePushFooter / subscribe."
    )
