# UI-4 — event timeline as editorial beats

Captured against the live `/` route running off the synthetic
4-event bus seeded by `scripts/ui_screenshots.py`. Default
viewport 1440x900 except for the narrow shot. Headless
Chromium, dark editorial palette inherited from UI-2.

The timeline replaces the UI-3 canvas-stub when events are
present. The empty-state path (zero events on the bus) is
unchanged from UI-3.

## What to look at

```text
00-timeline-default.png    populated bus, default viewport
  - Timeline column max-width 720 px, centred. Air on both
    sides is a feature; the operator surface is editorial,
    not dashboard.
  - Each row is one typographic line: timestamp (mono, --fs-12,
    --fg-2) on the left, type (display, --fs-16, --fg-1) as
    the typographic accent, path/agent (mono, --fs-14, --fg-2)
    as the muted metadata directly under the type.
  - Latest-on-top: the row stamped 10:00:30 (the controller
    resubmit) sits at the top; the row stamped 10:00:00 (the
    original watcher event) at the bottom.
  - Hairline divider (--fg-3) between rows. NO card chrome
    (no rounded background, no shadow, no padding box, no
    border-around). The line IS the unit.
  - No colour mapping per event type. file_change and
    agent_response render with the same --fg-1 type weight;
    chroma stays reserved for crow state / --accent / --error.

01-timeline-hover.png      first row hovered
  - Subtle --bg-2 background wash on the hovered row. Edges
    of the row stay aligned with the timeline column; no
    layout shift, no scale, no shadow, no accent flood. The
    transition is --duration-micro / --ease-out (color only,
    so it survives prefers-reduced-motion).

02-timeline-focus.png      first row focused via Tab
  - Two-step --focus-ring (2px --bg-0 inset + 2px --accent
    outset) drawn around the first row after one Tab from
    the document root. Each row has tabIndex=0 so the
    operator can keyboard-walk the timeline; the row itself
    is read-only — no navigation, no selection state. The
    focus ring is the entire affordance.

03-timeline-narrow-viewport.png  720x1024
  - Grid collapses to a single column at the 720 px
    breakpoint: timestamp stacks above the content (type +
    meta), gap tightens to --space-2. Reads as compact
    beats; no overflow, no horizontal scroll. The bus path
    in the header still ellipsizes at 40 vw per the UI-3
    rule.
```

## Frozen contracts respected

- UI is read-only against the bus. UI-4 only renders
  `/api/events`; no POST routes, no bus mutation.
- The `/api/events` projection is unchanged. Every visible
  field in a row maps to a UI-1 projection key (timestamp,
  type, path, agent, source).
- No new bus event types, no schema bump. AgentResponse,
  F3, F7, F8, surface=sink, single-worker invariant,
  scar=stored-correction-only, I-001..I-006, TriggerSource
  Protocol — all untouched.
- No `.webm` motion video. UI-4 transitions are micro
  (120 ms) colour shifts on hover, already covered by the
  design system demonstrated in UI-2. UI-5 still owns the
  next motion-introducing chunk and must ship `.webm`
  without exception per the ChatGPT UI-3 audit.

## Editorial guidance baked in

ChatGPT's UI-3 audit pinned a binding constraint set for
UI-4:

- timestamp mono small muted ✓
- type display, the typographic accent ✓
- path/agent muted metadata ✓
- hover/focus very contained ✓
- the largest risk is filling the air UI-3 just earned too
  quickly ✓ (max-width 720 + generous padding + no chrome)

The PR #71 review added one more binding rule that lands in
this chunk: **no cards per event**. Verified — the rows are
single typographic lines with hairline dividers, no card
chrome anywhere on the surface.

## How to reproduce

```bash
pip install playwright
python -m playwright install chromium
python scripts/ui_screenshots.py UI-4-timeline
```

The script seeds a temp `events.jsonl` with the 4 synthetic
events and runs the UI server via `ui_server.configure(...)`
(no `os.chdir`, fixed in UI-2). The UI-4 plan adds a
`press_tab` step so the focus capture is keyboard-driven
rather than synthetic; `wait_ms` runs first so the page's
JS-rendered timeline rows exist before the `hover` /
`press_tab` steps target them.
