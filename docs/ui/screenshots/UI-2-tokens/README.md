# UI-2 — design system + tokens page screenshots

Captured against the live `/design-system` route running off
the synthetic bus seeded by `scripts/ui_screenshots.py`.
Viewport 1440x900, headless Chromium, dark editorial palette
straight from the UI-0 brief §5.

## What to look at

```text
00-design-system-default.png  full /design-system page
  - palette swatches: --bg-0..2, --fg-1..3, --accent (rojo
    cuervo), --ok (subtle green), --warn (sand). Contrast
    ratios labelled inline.
  - typographic hierarchy from --fs-44 down to --fs-12, ratio
    1.4. Tracking tightens at -0.01em on display ≥20px.
  - spacing scale 4 / 8 / 12 / 16 / 24 / 32 / 48 / 80 px as
    accent-coloured bars.
  - radius / shadow / z-index / motion sections each render
    their tokens in live code — no static screenshots fake
    the demonstration.

01-design-system-focus.png   focus-ring demo
  - keyboard focus on .focus-button.primary. The two-step
    inset/outset (2px bg-0 + 2px accent) reads against the
    accent fill of the primary button itself, exactly the
    'on any surface' constraint of UI-0 §5.4.

02-design-system-motion.png  flight motion mid-transition
  - .motion-row with label 'flight · 600ms' is hovered and
    the screenshot is taken at ~100ms of the transition. The
    accent dot has moved off baseline; the other three rows
    sit at rest. Demonstrates the 600ms ease-mag duration is
    perceptible without being slow.
  - Static-only chunk per UI-0 §7: motion video NOT required.

03-index-with-tokens.png    operator surface w/ design system
  - existing index.html stub now reads against the new
    tokens. Header band on --bg-1 with hairline shadow,
    timeline rows in JetBrains Mono with --fg-2 timestamp
    + --fg-1 type label, panel cards on --bg-1 with
    --fg-3 dividers.
```

## How to reproduce

```bash
pip install playwright
python -m playwright install chromium
bash scripts/ui_fetch_fonts.sh       # idempotent
python scripts/ui_screenshots.py UI-2-tokens
```

The fetch script downloads the 6 woff2 from rsms.me (Inter)
and the JetBrains/JetBrainsMono v2.304 GitHub tag, both SIL
OFL 1.1. Licenses land alongside the binaries under
`src/karasu/ui/static/fonts/`.

The screenshots script seeds a temp `events.jsonl` with four
synthetic events covering the chunk-4c bus shape (watcher,
agent_response, github webhook, controller resubmit), starts
`karasu.ui.server` against that bus via `configure(...)`
(no global `os.chdir`), and writes the four PNGs.

## UI-0 §7 audit reminder

- Real PNGs ✓ (no waiver, the UI-1 one-time exception does
  NOT extend).
- 'What to look at' note ✓ (this README).
- No motion video required ✓ (static-only chunk).
- Audit prompt for ChatGPT lives in the PR body.
