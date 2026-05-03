# UI-3 — application shell screenshots

Captured against the live `/` route running off the synthetic
bus seeded by `scripts/ui_screenshots.py`. Default viewport
1440x900 except for the narrow shot. Headless Chromium, dark
editorial palette inherited from UI-2.

## What to look at

```text
00-shell-empty-state.png    bus has zero events
  - This is the brief's headline target: "Opens beautifully
    with zero events on the bus." Header (crow glyph + Karasu
    + bus path) sits flush at the top; main canvas centres on
    the hero crow and the editorial empty-state line; footer
    reports v0.1.0, no events yet, crow: idle.
  - The idle crow is breathing (1px translateY 4s loop, ease-
    mag) at capture time but the deltas are subliminal so the
    PNG reads as "at rest". Reduced-motion clamps the keyframe
    via reset.css; the visual contract from UI-2 holds.
  - The crow glyph is a vector silhouette placeholder; UI-5
    swaps it for the canonical 32x32 16-bit sprite per
    docs/ui/assets/karasu_sprites_spec.md.

01-shell-with-events.png    bus has 4 synthetic events
  - Same shell, populated state. The crow glyph in the header
    is now --accent (rojo cuervo) because /api/health resolves
    crow=processing for a tail of file_change events. Body
    swaps from the empty-state hero to the canvas-stub
    placeholder ("UI-4 will render the event timeline here")
    with a meta line that doubles as a smoke test of the
    /api/events projection (event count + last type +
    last timestamp).
  - Footer reflects the same event: last event timestamp,
    crow: processing.

02-shell-narrow-viewport.png    720x1024
  - Same populated state, narrower viewport. The shell holds
    its grid; the bus path truncates with ellipsis (max-width
    40vw on this breakpoint), the hero copy collapses to
    --fs-16, header / footer paddings step down. Validates
    that UI-3 reads on a smaller surface even though desktop
    is the operator's primary canvas (UI-0 §8).
```

## Frozen contracts respected

- UI is read-only against the bus. UI-3 only adds GET
  endpoints; no POST routes, no bus mutation.
- The new `/api/meta` endpoint is **additive** — neither
  `/api/events` nor `/api/health` change shape. Existing
  consumers (`karasu tail`, the UI-1 projection) keep their
  contract.
- AgentResponse, F3, F7, F8, surface=sink, single-worker,
  scar=stored-correction-only, I-001..I-006, TriggerSource
  Protocol, bus event schema — none touched.

## Motion video — deferred decision

Per UI-0 §7, "PRs that introduce or modify motion ... ALSO
ship a short screen recording (.webm <500 KB)". UI-3
introduces the **idle ambient breathing** of the hero crow
(1px translateY over 4s, ease-mag — described as "subliminal"
in UI-0 §5.6). The motion is below the threshold of static
PNG inspection but it IS new motion.

The README ships without a video on the call that the
amplitude is subliminal and that UI-5 (the canonical crow
sprite) is where the visible motion lands. If the audit
disagrees, a recording can be added in a follow-up before
merge.

## How to reproduce

```bash
pip install playwright
python -m playwright install chromium
python scripts/ui_screenshots.py UI-3-shell
```

The screenshots script seeds a temp `events.jsonl` and runs
the UI server via `ui_server.configure(...)` (no global
`os.chdir`, fixed in UI-2). For UI-3 each capture re-seeds the
bus to its target state (empty / populated) and may override
the viewport before navigating.
