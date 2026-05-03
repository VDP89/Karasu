# Next Session Entry Point

## Goal

**UI-2 — design system primitives + tokens page.**

Per UI-0 design brief (`docs/ui/ui-0-design-brief.md`),
chunk UI-2 lands `tokens.css` (every design token from §5
of the brief), self-hosted woff2 of Inter Display +
JetBrains Mono, a custom minimal CSS reset (NOT
normalize.css), and a `/design-system` page that documents
every token in live code — palette swatches, type scale
samples, spacing examples, radius samples, focus-ring demo,
z-index layer demo, motion examples (with reduced-motion
respected). The page doubles as the visual regression
baseline for subsequent chunks.

This is the FIRST chunk where new visible state lands. The
UI-0 audit cadence (§7) mandates real PNG screenshots for
every UI-N PR (UI-1's one-time waiver does NOT extend).

## Operational pre-req: operator on a computer with a browser

The session running this chunk MUST be on a machine where
Playwright + Chromium can install. The sandbox that ran
UI-0 / UI-1 did not have a browser available, which is why
UI-1 shipped under a one-time screenshot waiver. UI-2 has
no such waiver path.

If the next session is again sandboxed-without-browser, the
chunk MUST stop at the code/asset commit boundary; the
operator (Victor) captures screenshots locally via:

```bash
pip install playwright
python -m playwright install chromium
python scripts/ui_screenshots.py UI-2-tokens
```

…and commits the PNGs before the audit fires.

Operator targets Monday for this chunk on a computer.

## What ships in UI-2

```text
src/karasu/ui/static/assets/fonts/
  inter-display-400.woff2
  inter-display-500.woff2
  inter-display-700.woff2
  jetbrains-mono-400.woff2
  jetbrains-mono-500.woff2
  jetbrains-mono-700.woff2
  Self-hosted, SIL OFL 1.1 both. ~50-100 KB each
  (~400-600 KB total).

src/karasu/ui/static/css/tokens.css
  Every token from UI-0 brief §5: --bg-0..2, --fg-1..3,
  --accent, --error (alias), --ok, --warn, --radius-0..2,
  --shadow-0..2, --focus-ring, --z-base/sticky/overlay/
  modal/toast, motion easings, type scale via
  --font-display / --font-mono / --fs-12..44 / --lh-* /
  --tracking-display.

src/karasu/ui/static/css/reset.css
  Custom minimal reset (~30 lines). NOT normalize.css.
  Box-sizing border-box, body margin reset, button /
  input typography inheritance, form element resets,
  ::selection styling against --accent, prefers-reduced-
  motion media query that clamps non-color transitions
  to 1ms.

src/karasu/ui/static/css/base.css
  Body baseline (--bg-0, --fg-1, font-display 16px),
  scrollbar styling against --bg-1 / --fg-3, focus
  outline replacement using --focus-ring.

src/karasu/ui/static/index.html
  Updated to load tokens.css + reset.css + base.css and
  reference the new fonts. The existing stub timeline +
  crow-state remain functional; no behavioural change.

src/karasu/ui/static/design-system.html  (NEW)
  Live documentation of every token. Sections:
    - Palette: each color swatch with hex + token name +
      contrast ratio against --bg-0.
    - Typography: each scale step rendered with a sample
      sentence; mono samples for code.
    - Spacing: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 80
      visualised as flex gaps.
    - Radius: each --radius-* applied to a sample shape.
    - Focus ring: a button + input that demonstrate the
      ring under keyboard focus.
    - Z-index: stacked panels showing each layer.
    - Motion: hover-triggered samples for micro / panel /
      flight / ambient durations. Reduced-motion respected
      and visually called out.

src/karasu/ui/server.py
  + Route GET /design-system → serves design-system.html.

scripts/ui_fetch_fonts.sh  (NEW)
  Downloads the 6 woff2 files from rsms.me (Inter) and
  github.com/JetBrains/JetBrainsMono. Verifies SIL OFL 1.1
  license is present in each repo before download. Idempotent
  (skips if file already present + size matches expected).

docs/ui/screenshots/UI-2-tokens/
  REAL PNG screenshots:
    00-design-system-default.png  (full /design-system page)
    01-design-system-focus.png    (focus ring demo state)
    02-design-system-motion.png   (motion sample mid-transition,
                                   may need video instead per
                                   UI-0 §7)
    03-index-with-tokens.png     (existing index.html now using
                                   the design system)
```

## Chunk size estimate

```text
Code:    ~150 LOC (CSS + HTML + 1 server route)
Assets:  ~400-600 KB (6 woff2 files, binary)
Docs:    ~80 LOC (UI-2 README + screenshots dir README)
Tests:   none in UI-2; UI-9 owns the test chunk.
Total:   well under the 400 LOC code budget; assets are
         binary-large but small in number (6 files).
```

## Audit cadence reminder

Per UI-0 §7, the UI-2 PR MUST include:

```text
1. Real PNG screenshots under docs/ui/screenshots/UI-2-tokens/.
2. A "what to look at" note in the PR body pointing the
   auditor at: type scale rhythm, palette swatch contrast,
   focus ring visibility, motion subtlety with reduced-motion
   verified.
3. The diff itself.
4. The audit prompt for ChatGPT (same copy-paste flow).
5. NO motion video required for UI-2 (static-only chunk).
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md  (NORTH STAR — every token,
                                  every cadence rule, every
                                  out-of-scope decision)
2. src/karasu/ui/server.py       (current projection +
                                  routing; add /design-system
                                  here)
3. src/karasu/ui/static/index.html (existing stub — UI-2
                                  refactors it to use the
                                  new tokens, no behavioural
                                  change)
4. docs/ui/screenshots/UI-1-rebase/README.md (one-time
                                  waiver text — for the next
                                  session to see why UI-2
                                  needs real screenshots)
5. scripts/ui_screenshots.py     (capture script — run
                                  locally on operator
                                  machine after UI-2 code
                                  lands)
```

## Surface contract — must respect

```text
- UI = read-only sink (UI-0 §9 frozen contracts).
- No new bus event types. No bus mutation.
- No new runtime dependency. Stdlib + the woff2 binary
  assets only. (Playwright is dev-only for screenshots.)
- /design-system is a TOOL page — not part of the operator
  surface. UI-3 (application shell) is the operator entry
  point; /design-system stays accessible but unlinked from
  the main surface.
- Frozen contracts: AgentResponse, F3, F7, F8, surface=sink
  (the UI is a NEW surface, additive to Telegram and
  karasu tail), single-worker invariant,
  scar=stored-correction-only, I-001..I-006, TriggerSource
  Protocol, bus event schema (additive only via backend
  chunks).
```

## Open questions to resolve while implementing

```text
1. Font weight subset. The brief specified weights 400 /
   500 / 700 for both fonts. Do we ship all 3 weights for
   both, or 400 + 700 (simpler) and add 500 only when a
   chunk explicitly needs it? Lean: ship all 3 to match the
   brief exactly; ~600 KB total is acceptable for an
   internal tool.

2. /design-system route gating. Does it stay accessible in
   production builds, or hidden behind a flag? Lean:
   accessible always, unlinked from main surface. Cheap
   debug + visual regression target.

3. tokens.css file location. Inside static/css/ or at
   static/tokens.css? Lean: static/css/ subdirectory so
   future stylesheets (timeline.css, livemap.css, etc.)
   have a clean home.

4. Reduced-motion testing in CI. UI-9 owns the formal test
   chunk, but UI-2 introduces the first motion. Do we add
   a smoke test now? Lean: no, pin in UI-9.
```

## Do NOT do yet

```text
- Do not introduce React / Tailwind / any framework. The
  brief explicitly excludes them.
- Do not let the UI mutate bus state. UI-1..UI-9 are
  read-only.
- Do not introduce a build step. UI-2 ships static CSS +
  HTML directly. Vite enters when UI-3 / UI-4 introduce
  TypeScript modules.
- Do not start UI-3 / UI-4 / etc. as part of UI-2. Each is
  its own chunk per the brief.
- Do not link /design-system from the operator surface.
  It's a tool / debug page, not a feature.
- Do not start chunk 4c controlled dogfood from the
  sandbox; it needs the operator's computer.
```

## Anchor for the previous sessions

- Phase 3+ archive (issue #5) closed in code (4 main
  chunks + 4 follow-ups landed during 2026-05-02).
- README Fase 1 + Fase 2 complete on main; 335/335 pytest.
- UI handoff plan landed in PR #61 (memory snapshot,
  86c1d0e).
- UI-0 brief sealed in PR #62 (92e2c91).
- UI-1 rebase + projection expansion landed in PR #63
  (4819d7b). 5 of 6 cherry-picks from feat/ui-1-runtime
  applied (the 6th was a placeholder stub and was
  re-written). Server projection now surfaces the chunk-4c
  bus schema fields. ONE-TIME screenshot waiver applied
  to UI-1 only; UI-2+ does NOT inherit it.
- karasu ui [--host H] [--port P] CLI live; defaults
  127.0.0.1:8787.
- Operator on mobile until Monday; UI-2 is the entry
  point for the Monday session.
