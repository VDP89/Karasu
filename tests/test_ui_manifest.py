"""PWA manifest shape-lock test (UI-14 pin §11.6 — manifest contract).

UI-14 §3-A seals the manifest body and §3-G seals the anonymous
perimeter additions. This test pins both surfaces together so a
drift between manifest icon URLs and the live
``_ANONYMOUS_GET_PATHS`` frozenset surfaces in one place — the
gap UI-13 had (manifest declared ``/assets/icons/karasu-512.png``
while the whitelist only listed the 192) is exactly the failure
mode this test catches.

Layers:

    1. JSON parses (no commas missing, no UTF-8 BOM drift).
    2. Identity fields exact (name, short_name).
    3. Routing fields exact (start_url, scope).
    4. Display fields exact (display, orientation).
    5. Color fields exact AND cross-checked against
       ``static/css/tokens.css`` ``--bg-0`` — UI-13 seed had
       ``theme_color: #131316`` (= ``--bg-1``); UI-14 corrects
       both fields to ``#0a0a0b`` (= ``--bg-0``) so the splash
       screen the browser auto-generates is visually
       indistinguishable from the empty app shell.
    6. App-store metadata exact (categories, lang, dir).
    7. icons array shape: 4 entries, 2 any + 2 maskable, sizes
       192/512, all served from /assets/icons/.
    8. Every icon URL in the manifest is in the live
       ``_ANONYMOUS_GET_PATHS`` frozenset (no manifest-vs-
       whitelist gap).
    9. Every icon URL resolves to an actual file under
       ``static/icons/`` on disk (URL prefix /assets/ → fs
       static/, per server.py:1043-1044).

The test is pure-Python (json + Path + frozenset import) so it
runs in plain ``pytest`` with zero browser dependency, matching
``test_ui_sw.py`` / ``test_ui_icons.py`` / ``test_lint_ui_css.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from karasu.ui._auth import is_anonymous_path


REPO_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static"
MANIFEST_PATH = STATIC_DIR / "manifest.json"
TOKENS_CSS_PATH = STATIC_DIR / "css" / "tokens.css"

# Literal hex matching tokens.css --bg-0 exactly. P2 binding from
# UI-8 inherited; UI-14 §3-A re-binds at the manifest layer.
BG_0_HEX = "#0a0a0b"


@pytest.fixture(scope="module")
def manifest() -> dict:
    """Read + parse the manifest. Failing here means the file
    moved or got malformed JSON — surface that before any field
    assertion confuses the operator with a downstream KeyError."""
    assert MANIFEST_PATH.is_file(), f"manifest not found at {MANIFEST_PATH}"
    raw = MANIFEST_PATH.read_text(encoding="utf-8")
    # Reject UTF-8 BOM — Chrome's manifest parser tolerates it
    # but the file is served as application/manifest+json and a
    # BOM in the middle of an HTTP response invites diagnosis
    # rabbit holes. UI-13 sealed UTF-8 plain.
    assert not raw.startswith("﻿"), "manifest has UTF-8 BOM"
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Layer 2 — identity
# ---------------------------------------------------------------------------


def test_manifest_identity_fields(manifest: dict) -> None:
    assert manifest["name"] == "Karasu"
    assert manifest["short_name"] == "Karasu"


# ---------------------------------------------------------------------------
# Layer 2.5 — app id (brief amendment 2026-05-16 closing
# phase-4-dogfood Finding #5)
# ---------------------------------------------------------------------------


def test_manifest_id_sealed(manifest: dict) -> None:
    """§3-A amendment 2026-05-16: ``id`` sealed at the literal
    ``"/"``. Without ``id``, Chrome derives the App ID from
    ``start_url`` (origin-dependent), so a deploy that moves
    Karasu from ``http://localhost:8787/`` to ``https://<host>/``
    flips the Computed App ID and the installed PWA orphans —
    the operator's launcher shows a duplicate entry and the
    pre-deploy install loses its push subscriptions + cookies.
    The literal ``/`` decouples identity from origin while
    staying inside the manifest scope."""
    assert manifest["id"] == "/"


# ---------------------------------------------------------------------------
# Layer 3 — routing
# ---------------------------------------------------------------------------


def test_manifest_routing_fields(manifest: dict) -> None:
    assert manifest["start_url"] == "/"
    assert manifest["scope"] == "/"


# ---------------------------------------------------------------------------
# Layer 4 — display
# ---------------------------------------------------------------------------


def test_manifest_display_fields(manifest: dict) -> None:
    assert manifest["display"] == "standalone"
    assert manifest["orientation"] == "any"


# ---------------------------------------------------------------------------
# Layer 5 — colors (sealed values + cross-check against tokens.css)
# ---------------------------------------------------------------------------


def test_manifest_colors_match_bg_0(manifest: dict) -> None:
    """Both ``theme_color`` and ``background_color`` collapse to
    ``--bg-0`` so the auto-generated splash screen is visually
    indistinguishable from the app shell empty state. A drift to
    ``--bg-1`` (the UI-13 seed bug) regresses to a two-tone
    splash."""
    assert manifest["theme_color"] == BG_0_HEX
    assert manifest["background_color"] == BG_0_HEX


def test_tokens_css_bg_0_matches_manifest(manifest: dict) -> None:
    """Cross-check the manifest hex against the actual token in
    ``static/css/tokens.css``. If a future chunk re-pins
    ``--bg-0``, this test forces a synchronised manifest update
    rather than letting the two surfaces drift silently."""
    css = TOKENS_CSS_PATH.read_text(encoding="utf-8")
    match = re.search(r"--bg-0:\s*(#[0-9a-fA-F]{3,8})\s*;", css)
    assert match is not None, "tokens.css does not declare --bg-0"
    css_bg_0 = match.group(1).lower()
    assert manifest["theme_color"].lower() == css_bg_0, (
        f"manifest theme_color {manifest['theme_color']} drifted from "
        f"tokens.css --bg-0 {css_bg_0}"
    )
    assert manifest["background_color"].lower() == css_bg_0, (
        f"manifest background_color {manifest['background_color']} "
        f"drifted from tokens.css --bg-0 {css_bg_0}"
    )


# ---------------------------------------------------------------------------
# Layer 6 — app-store metadata
# ---------------------------------------------------------------------------


def test_manifest_categories_sealed(manifest: dict) -> None:
    """§3-A SEALED at exactly ["productivity", "utilities"]. A
    future amendment to add a third category re-opens §3-A."""
    assert manifest["categories"] == ["productivity", "utilities"]


def test_manifest_lang_dir_sealed(manifest: dict) -> None:
    assert manifest["lang"] == "en"
    assert manifest["dir"] == "ltr"


# ---------------------------------------------------------------------------
# Layer 7 — icons array shape
# ---------------------------------------------------------------------------


EXPECTED_ICONS: list[dict] = [
    {
        "src": "/assets/icons/karasu-192.png",
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "any",
    },
    {
        "src": "/assets/icons/karasu-512.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "any",
    },
    {
        "src": "/assets/icons/karasu-maskable-192.png",
        "sizes": "192x192",
        "type": "image/png",
        "purpose": "maskable",
    },
    {
        "src": "/assets/icons/karasu-maskable-512.png",
        "sizes": "512x512",
        "type": "image/png",
        "purpose": "maskable",
    },
]


def test_manifest_icons_count(manifest: dict) -> None:
    """§3-A SEALED at exactly four icons (192-any + 512-any +
    192-maskable + 512-maskable). A drift in count (e.g. someone
    adds a third purpose like "monochrome") re-opens §3-A."""
    assert isinstance(manifest["icons"], list)
    assert len(manifest["icons"]) == 4


@pytest.mark.parametrize(
    "expected",
    EXPECTED_ICONS,
    ids=[i["src"].rsplit("/", 1)[-1] for i in EXPECTED_ICONS],
)
def test_manifest_icon_entry_exact(
    manifest: dict, expected: dict
) -> None:
    icons = {entry["src"]: entry for entry in manifest["icons"]}
    actual = icons.get(expected["src"])
    assert actual is not None, (
        f"icon {expected['src']} missing from manifest"
    )
    for key in ("sizes", "type", "purpose"):
        assert actual[key] == expected[key], (
            f"icon {expected['src']} field {key} drift: "
            f"actual={actual[key]} expected={expected[key]}"
        )


# ---------------------------------------------------------------------------
# Layer 8 — manifest-vs-whitelist consistency (the UI-13 gap)
# ---------------------------------------------------------------------------


def test_every_manifest_icon_url_is_anonymous(manifest: dict) -> None:
    """Closes the UI-13 gap (manifest declared 512.png but the
    anonymous whitelist did not include it). Future icon
    additions to the manifest must extend the whitelist in the
    same commit; this test guarantees the surfaces stay
    synchronised.

    Uses the public ``is_anonymous_path`` API rather than the
    private ``_ANONYMOUS_GET_PATHS`` frozenset so a future
    refactor of the perimeter representation (e.g. adding a
    prefix entry) does not silently break this contract."""
    icon_urls = sorted(entry["src"] for entry in manifest["icons"])
    missing = [
        url for url in icon_urls
        if not is_anonymous_path("GET", url)
    ]
    assert not missing, (
        f"manifest declares icon URL(s) {missing} that are NOT "
        f"anonymous-reachable — anonymous install would 401 on "
        f"these requests, breaking PWA install pre-auth."
    )


# ---------------------------------------------------------------------------
# Layer 9 — manifest-vs-disk consistency (URL → fs path)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "icon_url",
    [i["src"] for i in EXPECTED_ICONS],
)
def test_manifest_icon_url_resolves_on_disk(icon_url: str) -> None:
    """The /assets/ URL prefix maps to the static/ filesystem
    directory (server.py:1043-1044). For each manifest icon URL,
    resolve to the on-disk path and assert the file exists.

    Using URL → fs translation here, not assuming filesystem
    layout matches URL layout — caught by Codex round 2 P1 in
    UI-14 brief drafting where the brief had ``static/assets/``
    paths that did not exist on disk."""
    assert icon_url.startswith("/assets/"), (
        f"icon URL {icon_url} does not start with /assets/"
    )
    fs_relative = icon_url[len("/assets/") :]
    fs_path = STATIC_DIR / fs_relative
    assert fs_path.is_file(), (
        f"manifest icon URL {icon_url} → fs path {fs_path} does "
        f"not exist on disk"
    )
