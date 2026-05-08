"""PWA icon shape-lock test (UI-14 pin §11.6 — icon contract).

UI-14 §3-A seals four PNG icons under
``src/karasu/ui/static/icons/`` referenced by the manifest:

    karasu-192.png            (purpose: any)
    karasu-512.png            (purpose: any)
    karasu-maskable-192.png   (purpose: maskable)
    karasu-maskable-512.png   (purpose: maskable)

The icons are rendered by ``scripts/ui_pwa_icons.py`` (Playwright
headless, no new runtime dep — UI-0 §4 / UI-14 §3-C). This test
locks three layers of the contract:

    1. Filesystem layer — the four files exist and are non-empty
       PNGs at the documented dimensions.
    2. Visual layer — the four corner pixels of every icon are
       full-bleed --bg-0 (#0a0a0b) and the centre is glyph
       (brighter than --bg-0). For maskable icons, points just
       outside the W3C 80 %-diameter safe zone (radius = 40 % of
       canvas) are also full-bleed bg, proving the glyph stays
       inside the safe circle a launcher mask may apply.
    3. Byte layer — SHA-256 hashes match the golden constants
       captured at chunk close. A hash mismatch surfaces drift;
       layers 1 + 2 narrow down whether it's dimensions, palette,
       or pure rendering drift before the operator opens the diff.

The test depends only on Pillow (already a stdlib-of-the-repo
adjacent — pulled by Playwright transitively for screenshot
encoding) so it runs in plain ``pytest`` with zero browser
dependency, matching the static-artefact pattern in
``test_ui_sw.py`` and ``test_lint_ui_css.py``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "icons"

# Literal hex matching tokens.css --bg-0 exactly. Off-by-one channel
# is a regression (UI-8 P2 binding inherited).
BG_0_RGB: tuple[int, int, int] = (0x0A, 0x0A, 0x0B)

# W3C maskable spec safe zone: 80 % diameter circle from canvas
# centre. Radius = 40 % of side. Anything outside is at risk of
# being clipped by a launcher OS mask.
MASKABLE_SAFE_RADIUS_RATIO = 0.40


# ---------------------------------------------------------------------------
# Golden hashes captured at UI-14 chunk close (Playwright + Chromium
# 145.0.7632.6, default device_scale_factor=1, omit_background=False).
#
# A failing hash here is NOT an automatic test failure to ignore —
# it means either a deliberate icon refresh (re-pin the hash) or a
# silent drift from a Playwright/Chromium upgrade. The dimension +
# corner pixel + safe-zone assertions above this block run first
# and tell the operator WHICH layer broke before the hash.
# ---------------------------------------------------------------------------
GOLDEN_SHA256: dict[str, str] = {
    "karasu-192.png":
        "5c6c494b642b8a5eb0d71a6f098b82bad1e6889e35eee2f5afb77edbbca01c0e",
    "karasu-512.png":
        "12e06a97651b1f0abe9e009d87b99bf654d413f4a15cc605f3499c1bad769fc2",
    "karasu-maskable-192.png":
        "ad1cfe552d918259610aa8b93c12788591def11b3bfef4561a501bc038068504",
    "karasu-maskable-512.png":
        "c56644a139b94e0980d16f2d41ae093ba44105e1b99abffa862f6422a3136ba8",
}

ICON_FILES: tuple[tuple[str, int, str], ...] = (
    # filename, expected side, purpose
    ("karasu-192.png", 192, "any"),
    ("karasu-512.png", 512, "any"),
    ("karasu-maskable-192.png", 192, "maskable"),
    ("karasu-maskable-512.png", 512, "maskable"),
)


# ---------------------------------------------------------------------------
# Layer 1 — filesystem
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,_side,_purpose", ICON_FILES)
def test_icon_file_exists_and_is_nonempty_png(
    filename: str, _side: int, _purpose: str
) -> None:
    path = ICONS_DIR / filename
    assert path.is_file(), f"missing icon {path}"
    data = path.read_bytes()
    assert len(data) > 0, f"empty icon {path}"
    # PNG magic: 89 50 4E 47 0D 0A 1A 0A.
    assert data[:8] == b"\x89PNG\r\n\x1a\n", (
        f"{path} is not a PNG (magic bytes mismatch)"
    )


# ---------------------------------------------------------------------------
# Layer 2 — visual contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,side,_purpose", ICON_FILES)
def test_icon_dimensions_match_filename(
    filename: str, side: int, _purpose: str
) -> None:
    path = ICONS_DIR / filename
    with Image.open(path) as img:
        assert img.size == (side, side), (
            f"{filename}: expected {side}x{side}, got {img.size}"
        )


def _rgb(img: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    """Return the RGB triple at (x, y), discarding any alpha. Pillow
    returns RGBA when the source PNG has alpha; we coerce to RGB so
    the assertion compares against ``BG_0_RGB`` cleanly."""
    pixel = img.convert("RGB").getpixel((x, y))
    assert isinstance(pixel, tuple) and len(pixel) == 3
    return pixel  # type: ignore[return-value]


@pytest.mark.parametrize("filename,side,_purpose", ICON_FILES)
def test_icon_corners_are_full_bleed_bg(
    filename: str, side: int, _purpose: str
) -> None:
    """All four corner pixels must be exactly --bg-0. Maskable spec
    requires full-bleed; any-purpose UI-8 sealed the same colour."""
    path = ICONS_DIR / filename
    with Image.open(path) as img:
        corners = {
            "top-left": _rgb(img, 0, 0),
            "top-right": _rgb(img, side - 1, 0),
            "bottom-left": _rgb(img, 0, side - 1),
            "bottom-right": _rgb(img, side - 1, side - 1),
        }
    for name, rgb in corners.items():
        assert rgb == BG_0_RGB, (
            f"{filename} {name} corner = {rgb}, expected {BG_0_RGB}"
        )


@pytest.mark.parametrize("filename,side,_purpose", ICON_FILES)
def test_icon_centre_is_glyph_not_bg(
    filename: str, side: int, _purpose: str
) -> None:
    """Centre pixel must be brighter than --bg-0 — proves the
    crow glyph rendered into the canvas at all."""
    path = ICONS_DIR / filename
    centre = side // 2
    with Image.open(path) as img:
        rgb = _rgb(img, centre, centre)
    luminance_bg = sum(BG_0_RGB)
    luminance_centre = sum(rgb)
    assert luminance_centre > luminance_bg + 30, (
        f"{filename} centre = {rgb}, expected glyph (brighter than "
        f"{BG_0_RGB})"
    )


@pytest.mark.parametrize(
    "filename,side",
    [(f, s) for f, s, p in ICON_FILES if p == "maskable"],
)
def test_maskable_glyph_inside_safe_zone(filename: str, side: int) -> None:
    """For maskable icons, points just outside the W3C 80 %-diameter
    safe zone (radius > 40 % of canvas) must still be full-bleed bg.
    Otherwise a launcher applying a circular mask of that radius
    would clip the glyph.

    Sampled at the four cardinal points just outside the safe radius
    plus the four diagonal points at the safe radius. The latter is
    the tightest constraint — diagonals are where a square crow box
    pushes furthest from centre. A 0.55 box yields corners at
    box/2 * sqrt(2) ≈ 0.389 * side, so the 0.40 radius diagonals
    must be bg.
    """
    path = ICONS_DIR / filename
    centre = side // 2
    safe_r = int(side * MASKABLE_SAFE_RADIUS_RATIO)
    # One pixel outside the safe radius along each cardinal axis.
    just_outside = safe_r + 1
    samples = [
        ("N-out", centre, centre - just_outside),
        ("S-out", centre, centre + just_outside),
        ("E-out", centre + just_outside, centre),
        ("W-out", centre - just_outside, centre),
        # Diagonal points exactly at the safe radius (cos45 ≈ 0.707).
        ("NE-edge", centre + int(safe_r * 0.7071),
         centre - int(safe_r * 0.7071)),
        ("NW-edge", centre - int(safe_r * 0.7071),
         centre - int(safe_r * 0.7071)),
        ("SE-edge", centre + int(safe_r * 0.7071),
         centre + int(safe_r * 0.7071)),
        ("SW-edge", centre - int(safe_r * 0.7071),
         centre + int(safe_r * 0.7071)),
    ]
    with Image.open(path) as img:
        for name, x, y in samples:
            rgb = _rgb(img, x, y)
            assert rgb == BG_0_RGB, (
                f"{filename} maskable safe-zone violation at {name} "
                f"({x},{y}): pixel {rgb} != bg {BG_0_RGB}. The glyph "
                f"extends past the W3C 40 % safe radius and a launcher "
                f"mask may clip it."
            )


# ---------------------------------------------------------------------------
# Layer 3 — byte regression
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("filename,_side,_purpose", ICON_FILES)
def test_icon_sha256_matches_golden(
    filename: str, _side: int, _purpose: str
) -> None:
    path = ICONS_DIR / filename
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    expected = GOLDEN_SHA256[filename]
    assert actual == expected, (
        f"{filename} SHA-256 drift: actual={actual} expected={expected}. "
        f"If the visual + dimension assertions above passed, this is "
        f"likely a Playwright/Chromium version drift — re-running "
        f"scripts/ui_pwa_icons.py produced different bytes for the "
        f"same visual contract. Re-pin the hash or freeze the rendering "
        f"toolchain before merging."
    )
