"""PWA icon shape-lock test (UI-14 pin §11.6 — icon contract).

UI-14 §3-A seals four PNG icons under
``src/karasu/ui/static/icons/`` referenced by the manifest:

    karasu-192.png            (purpose: any)
    karasu-512.png            (purpose: any)
    karasu-maskable-192.png   (purpose: maskable)
    karasu-maskable-512.png   (purpose: maskable)

The icons are rendered by ``scripts/ui_pwa_icons.py`` (Playwright
headless, no new runtime dep — UI-0 §4 / UI-14 §3-C). This test
locks two layers of the contract using ONLY the stdlib (Codex
round-2 P1 — Pillow is not declared in pyproject.toml so a clean
``.[dev]`` venv would not have it):

    1. Filesystem layer — the four files exist and are non-empty
       PNGs at the documented dimensions. PNG magic bytes are
       checked verbatim and the IHDR chunk is parsed by hand for
       width / height. No pixel decoding so no zlib /
       filter-reverse / colour-model code is needed.

    2. Byte layer — SHA-256 hashes match the golden constants
       captured at chunk close. A hash mismatch surfaces drift
       at the byte level; the dimension assertions above narrow
       down whether the drift is structural (different size) or
       visual (same size, different content).

The earlier round-1 visual layer (corner / centre / safe-zone
pixel sampling) was dropped at Codex round-2 P1 because it
required Pillow as a dev dep and the brief explicitly avoided
new dev dependencies for icon work. The golden SHA-256 hash is
the equivalent regression guard at the byte level — any visual
drift produces a different byte sequence and trips the hash.
The trade is: a hash failure no longer self-explains WHICH
visual aspect drifted (palette / dimensions / glyph position).
The IHDR dimension parse covers the most likely structural
drift; everything else surfaces as a hash mismatch the operator
investigates with their own image viewer.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "icons"


# ---------------------------------------------------------------------------
# Golden hashes captured at UI-14 chunk close (Playwright + Chromium
# 145.0.7632.6, default device_scale_factor=1, omit_background=False).
#
# A failing hash here is NOT an automatic test failure to ignore —
# it means either a deliberate icon refresh (re-pin the hash) or a
# silent drift from a Playwright/Chromium upgrade. The dimension
# assertions above this block run first and tell the operator
# whether the drift is structural before the hash mismatch surfaces.
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

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(path: Path) -> tuple[int, int]:
    """Parse the IHDR chunk by hand and return (width, height).

    PNG layout (per the W3C spec, libpng documentation, RFC 2083):

        bytes  0..  7   PNG signature (8 bytes)
        bytes  8.. 11   IHDR chunk length (always 13, big-endian
                         uint32)
        bytes 12.. 15   IHDR chunk type (the 4 ASCII bytes
                         ``IHDR``)
        bytes 16.. 19   image width  (big-endian uint32)
        bytes 20.. 23   image height (big-endian uint32)

    We only need the width + height. Everything past byte 23 (bit
    depth, colour type, compression, filter, interlace, CRC) is
    irrelevant to the dimension contract this test pins."""
    with path.open("rb") as fh:
        header = fh.read(24)
    if len(header) < 24:
        raise AssertionError(f"{path} is shorter than a PNG header")
    if header[:8] != PNG_MAGIC:
        raise AssertionError(
            f"{path} does not start with the PNG magic signature"
        )
    if header[12:16] != b"IHDR":
        raise AssertionError(
            f"{path} does not declare an IHDR chunk first — the "
            f"file may be a non-conformant PNG variant or "
            f"truncated. Expected b'IHDR' at offset 12, got "
            f"{header[12:16]!r}."
        )
    width, height = struct.unpack(">II", header[16:24])
    return width, height


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
    assert data[:8] == PNG_MAGIC, (
        f"{path} is not a PNG (magic bytes mismatch)"
    )


@pytest.mark.parametrize("filename,side,_purpose", ICON_FILES)
def test_icon_dimensions_match_filename(
    filename: str, side: int, _purpose: str
) -> None:
    path = ICONS_DIR / filename
    width, height = _png_dimensions(path)
    assert (width, height) == (side, side), (
        f"{filename}: expected {side}x{side}, got {width}x{height}"
    )


# ---------------------------------------------------------------------------
# Layer 2 — byte regression
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
        f"If the dimension assertions above passed, the drift is "
        f"either a Playwright/Chromium version bump OR a deliberate "
        f"icon refresh. Re-pin the hash if the new bytes are correct, "
        f"or freeze the rendering toolchain version before merging."
    )
