"""Render Karasu PWA icons to ``src/karasu/ui/static/icons/``.

UI-8 sealed the any-purpose icons (192 / 512) with the crow glyph
sized to ~70 % of the canvas box. UI-14 §3-A extends the manifest
icon array with maskable variants (192 / 512) sized to ~55 % of
the canvas so the glyph stays inside the 80 %-diameter safe zone
the W3C maskable spec assumes a launcher mask may apply.

Why Playwright and not Pillow / cairosvg / resvg:

- Pillow does not rasterise SVG natively.
- Adding ``cairosvg`` / ``resvg-py`` for a one-shot render would
  violate UI-0 §4 (no new runtime dep). UI-14 §3-C re-pinned the
  same constraint at the chunk level.
- Playwright is already in the dev tooling for ``ui_screenshots``
  and the UI-8 baseline of this script. Reusing it costs nothing.

Run from the repo root::

    python scripts/ui_pwa_icons.py              # all four PNGs
    python scripts/ui_pwa_icons.py --maskable   # only maskable

Outputs::

    src/karasu/ui/static/icons/karasu-192.png            (any)
    src/karasu/ui/static/icons/karasu-512.png            (any)
    src/karasu/ui/static/icons/karasu-maskable-192.png   (maskable)
    src/karasu/ui/static/icons/karasu-maskable-512.png   (maskable)

Re-running with the same Playwright + Chromium version is
reproducible; cross-version drift may produce different bytes,
which ``tests/test_ui_icons.py`` surfaces via dimension + corner
pixel + SHA-256 invariants.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "icons"
CROW_SVG = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "crow" / "crow.svg"

# Literal hex matching tokens.css exactly. P2 binding from the UI-8
# design review: an off-by-one channel is a regression.
BG_0 = "#0a0a0b"   # canvas
FG_1 = "#ededf2"   # primary fg — the crow's resting colour

ICON_SIZES: tuple[int, ...] = (192, 512)

# Box ratios. UI-8 sealed 0.70 for any-purpose; UI-14 §3-C sets
# 0.55 for maskable so the glyph corner reaches r = box/2 * sqrt(2)
# = ~38.9 % of canvas, inside the W3C 40 % safe radius with margin.
ANY_RATIO = 0.70
MASKABLE_RATIO = 0.55


@dataclass(frozen=True)
class IconSpec:
    purpose: str   # "any" | "maskable"
    size: int      # 192 | 512
    ratio: float   # crow_box / canvas

    @property
    def filename(self) -> str:
        if self.purpose == "any":
            return f"karasu-{self.size}.png"
        return f"karasu-{self.purpose}-{self.size}.png"


def _all_specs() -> tuple[IconSpec, ...]:
    return (
        *(IconSpec("any", s, ANY_RATIO) for s in ICON_SIZES),
        *(IconSpec("maskable", s, MASKABLE_RATIO) for s in ICON_SIZES),
    )


def _icon_html(spec: IconSpec) -> str:
    """Inline HTML that paints the crow centred on a --bg-0 canvas
    of ``spec.size`` square. The crow uses ``currentColor`` for fill,
    so wrapping it in a span coloured ``--fg-1`` recolours the
    silhouette to the resting tone.
    """
    crow_svg = CROW_SVG.read_text(encoding="utf-8")
    crow_box = int(spec.size * spec.ratio)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {spec.size}px; height: {spec.size}px; overflow: hidden; }}
body {{
    background: {BG_0};
    color: {FG_1};
    display: flex;
    align-items: center;
    justify-content: center;
}}
.icon {{ width: {crow_box}px; height: {crow_box}px; }}
.icon svg {{ width: 100%; height: 100%; display: block; }}
</style>
</head>
<body>
<div class="icon">{crow_svg}</div>
</body>
</html>
"""


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render Karasu PWA icons (any + maskable purposes)."
    )
    parser.add_argument(
        "--maskable",
        action="store_true",
        help=(
            "generate only the maskable PNGs and skip the UI-8 sealed "
            "any-purpose pair (preserves their committed bytes)."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "error: playwright not installed.\n"
            "  pip install playwright\n"
            "  python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    if not CROW_SVG.exists():
        print(f"error: source SVG not found at {CROW_SVG}", file=sys.stderr)
        return 2

    specs = tuple(
        s for s in _all_specs()
        if not args.maskable or s.purpose == "maskable"
    )

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for spec in specs:
                context = browser.new_context(
                    viewport={"width": spec.size, "height": spec.size},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.set_content(_icon_html(spec))
                # Single tick — the canvas is static.
                page.wait_for_timeout(100)
                out = ICONS_DIR / spec.filename
                page.screenshot(path=str(out), omit_background=False)
                context.close()
                print(f"  wrote {out.relative_to(REPO_ROOT)}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
