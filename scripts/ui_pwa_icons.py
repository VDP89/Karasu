"""Render the canonical crow asset to PWA icon PNGs.

UI-8 ships a Web App Manifest with home-screen icons at 192×192
and 512×512. The icons MUST recolour through Karasu's palette so
the installed PWA tile reads as the same editorial mark as the
header glyph — not a generic browser fallback.

Pillow does not rasterise SVG natively, and adding cairosvg or
resvg-py to the dev dependencies for a one-shot render would
violate UI-0 §4 (no new runtime dep). Playwright is already in
the tooling for screenshots, so we use it: render an inline HTML
page that embeds the canonical crow.svg at the target box size
against the --bg-0 canvas, screenshot, save the PNG.

Run from the repo root:

    python scripts/ui_pwa_icons.py

Outputs:

    src/karasu/ui/static/icons/karasu-192.png
    src/karasu/ui/static/icons/karasu-512.png

The PNGs are committed as static assets so the SW pre-cache list
references stable files; re-running the script is reproducible
because the same SVG + the same render dimensions yield the same
output.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ICONS_DIR = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "icons"
CROW_SVG = REPO_ROOT / "src" / "karasu" / "ui" / "static" / "crow" / "crow.svg"

# Literal hex matching tokens.css exactly. P2 binding from the
# UI-8 design review: an off-by-one channel is a regression.
BG_0 = "#0a0a0b"   # canvas
FG_1 = "#ededf2"   # primary fg — the crow's resting colour

ICON_SIZES = (192, 512)


def _icon_html(size: int) -> str:
    """Build an inline HTML page that paints the crow centred on a
    --bg-0 square at exactly ``size`` × ``size`` pixels.

    The crow uses ``currentColor`` for fill, so wrapping it in a
    span with ``color: --fg-1`` recolours the silhouette to the
    canonical resting colour. The crow occupies ~70% of the box;
    the surrounding margin keeps the silhouette readable when the
    PWA tile is rendered with rounded corners by the OS.
    """
    crow_svg = CROW_SVG.read_text(encoding="utf-8")
    crow_box = int(size * 0.7)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
html, body {{ width: {size}px; height: {size}px; overflow: hidden; }}
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


def main() -> int:
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

    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            for size in ICON_SIZES:
                context = browser.new_context(
                    viewport={"width": size, "height": size},
                    device_scale_factor=1,
                )
                page = context.new_page()
                page.set_content(_icon_html(size))
                # Give the SVG one frame to lay out; the canvas
                # is static so a single tick is enough.
                page.wait_for_timeout(100)
                out = ICONS_DIR / f"karasu-{size}.png"
                page.screenshot(path=str(out), omit_background=False)
                context.close()
                print(f"  wrote {out.relative_to(REPO_ROOT)}")
        finally:
            browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
