# Next Session Entry Point

## Goal

**UI-4 — event timeline as editorial beats.**

Per UI-0 design brief §6, chunk UI-4 turns the empty-state
canvas (UI-3) into a populated timeline of bus events
rendered as typographic lines, NOT table rows. The brief is
explicit: *"Each event is a typographic line, not a table
row: timestamp (mono), type (display), path / agent (muted).
Hover and focus states. Connects to `/api/events`; no Live
Map yet."*

UI-4 is the chunk where the operator surface stops being
empty and starts being **read**. It is the highest-risk
visual chunk so far: a mistuned scale or a busy hover state
silently undoes the calm UI-3 just earned.

## Editorial guidance pinned by ChatGPT (UI-3 audit)

The reviewer flagged the central risk explicitly. Treat the
following as binding constraints, not suggestions:

```text
- Timestamp:   mono, small, muted (--font-mono / --fs-12 /
               --fg-2). Reads as metadata, never the focal
               point.
- Type:        display, the typographic accent of the row
               (--font-display / --fs-16 weight ui or
               display / --fg-1). Single visual emphasis
               per row.
- Path/agent:  muted, secondary metadata
               (--fg-2 / --fs-14 / --font-mono for paths,
               --font-display for agent names). Below the
               type in visual weight, never above.
- Hover/focus: very contained. Subtle --bg-2 background
               shift; the design-system focus ring on Tab.
               No translation, no zoom, no accent flood.
- The largest risk of UI-4 is filling the air UI-3 just
  earned too quickly. Generous vertical rhythm, max-width
  cap on the timeline column, no chrome decoration.
```

Anchor those rules in the implementation. If a token /
spacing decision feels generous, lean generous; if it feels
tight, walk it back one stop.

## What ships in UI-4

```text
src/karasu/ui/static/index.html  (extension)
  - The canvas-stub branch ("UI-4 will render the event
    timeline here") is replaced by a real <ol class="timeline">
    rendered into the same main slot. The empty-state branch
    (zero events) is unchanged from UI-3.
  - Each event row is a single line:
      [timestamp mono small muted]
      [type display 16 fg-1]
      [path or agent mono / display 14 fg-2]
    Stacked or in-row depending on viewport; never as a
    table.
  - JS gains a tiny renderer that takes the /api/events
    projection and produces the row DOM. Reuse the existing
    setInterval from UI-3 (3s poll); no new poll loop.
  - Latest event on top. The bus is append-only and the
    operator wants the most recent first.
  - max-width 720px on the timeline column, centred. The
    column does NOT span the canvas — air on both sides is
    a feature.

src/karasu/ui/static/css/  (optional split, lean: yes)
  Inline <style> in index.html grew during UI-3. UI-4 is the
  natural moment to peel timeline-specific rules into
  static/css/timeline.css and load it from index.html. Keeps
  index.html under ~250 LOC of style and lets future chunks
  add their own *.css without bloating the inline block.

scripts/ui_screenshots.py  (extension)
  Add a UI-4 capture plan with at least:
    00-timeline-default.png        populated bus, default vp
    01-timeline-hover.png          one row hovered
    02-timeline-focus.png          one row focused via Tab
    03-timeline-narrow-viewport.png 720x1024 narrow

docs/ui/screenshots/UI-4-timeline/  (NEW)
  REAL PNG screenshots. UI-1 waiver does NOT extend.
```

## Surface contract — must respect

```text
- UI = read-only sink. UI-4 reads /api/events and renders;
  no POST routes, no bus mutation.
- No new bus event types. No projection changes (UI-1
  already surfaces every chunk-4c field).
- No new runtime dependency. Stdlib + the woff2 already
  shipped in UI-2.
- No build step. Static HTML / CSS / inline JS, same as
  UI-2 / UI-3.
- The empty state from UI-3 is the FIRST IMPRESSION when
  the bus is silent. UI-4 must not change that path; the
  swap to the populated timeline only happens when
  events.length > 0.
- Frozen contracts: AgentResponse, F3, F7, F8, surface=sink,
  single-worker invariant, scar=stored-correction-only,
  I-001..I-006, TriggerSource Protocol, bus event schema
  (additive only via backend chunks; UI-4 does not change
  it).
```

## Open questions to resolve while implementing

```text
1. Latest-first vs earliest-first. Lean: latest on top.
   The bus is append-only; the operator coming back to the
   surface wants the most recent context, not the first
   change of the day.

2. Priority highlighting. priority="high" events could earn
   a thin --accent left border or an italicised type label.
   Lean: NO highlighting in UI-4. The brief warned UI-4
   about filling too fast; layering visual cues on top of
   the type accent doubles the noise. Defer to a UI-7
   detail drawer or a UI-N filter chunk if the need
   surfaces empirically.

3. Type-to-accent mapping. file_change vs agent_response vs
   human_decision could each get a dedicated colour. Lean:
   NO. --fg-1 for the type label across the board. The
   type word IS the accent (typography over chroma); colour
   stays reserved for the crow state and --accent stays
   reserved for affordance / error.

4. Auto-scroll on new events. With latest-on-top + 3 s
   poll, new rows appear at the top while the operator may
   be reading older context. Lean: NO auto-scroll. New rows
   prepend; the scroll position stays anchored to whatever
   row the operator is reading. Optional UI-9 follow-up:
   small "n new events" pill that flashes when the top
   shifts.

5. Empty `tail.type` / `tail.timestamp`. The render must
   degrade gracefully — `'event'` and `'—'` placeholders
   per the UI-3 footer pattern. Already proven in UI-3.

6. CSS split. UI-2 put fonts/tokens/reset/base under
   static/css/. UI-3 kept timeline-relevant rules inline.
   UI-4 should split timeline.css out so index.html stays
   readable. Lean: yes, split. Inline <style> still owns
   the shell-header / shell-footer / empty-state rules
   (those are specific to the shell, not the timeline).
```

## Audit cadence reminder

Per UI-0 §7, the UI-4 PR MUST include:

```text
1. Real PNG screenshots under docs/ui/screenshots/UI-4-timeline/.
2. A "what to look at" note in the PR body pointing the
   auditor at: type-vs-mono rhythm, vertical density,
   hover/focus subtlety, narrow-viewport collapse.
3. The diff itself.
4. The audit prompt for ChatGPT (same copy-paste flow).
5. NO motion video required for UI-4 (static-only chunk —
   timeline transitions, if any, are micro / 120ms colour
   shifts on hover, already covered by the design system
   demonstrated in UI-2).
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §6 UI-4 + §5.2 (typography)
   + §5.3 (spacing). Type / spacing rules ARE the spec for
   this chunk.
2. docs/memory/session-log.md tail (UI-2 + UI-3 closes) —
   the bug pattern that bit UI-3 ([hidden] specificity) is
   worth keeping in mind when UI-4 touches the same
   .empty-state / .canvas-stub toggle.
3. src/karasu/ui/static/index.html (current shell,
   post-UI-3) — the canvas-stub branch is what UI-4
   replaces.
4. src/karasu/ui/server.py — _project_event already
   surfaces every field UI-4 needs (timestamp, type, path,
   agent, classification, priority, controller_resubmit,
   github_*). No projection change needed.
5. docs/ui/screenshots/UI-3-shell/README.md — for the
   "what to look at" note style and the audit-prompt
   pattern.
```

## Chunk size estimate

```text
Code:    ~200 LOC (HTML extension + new timeline.css + JS
         renderer)
Assets:  none (fonts already shipped in UI-2)
Docs:    ~80 LOC (screenshots README)
Tests:   none in UI-4; UI-9 owns the test chunk.
Total:   well under the 400 LOC budget.
```

## Do NOT do yet

```text
- Do NOT introduce React / Tailwind / any framework. UI-0
  §4 still binding.
- Do NOT colour-code event types. The type word is the
  accent; chroma stays reserved for crow state / affordance
  / error.
- Do NOT auto-scroll. New events prepend; operator
  scrolls.
- Do NOT add filters / search / pagination in UI-4. UI-9
  owns the operator-tooling chunk.
- Do NOT touch /api/events shape. The projection is the
  canonical contract.
- Do NOT start UI-5 (crow sprite + state animations) as
  part of UI-4. UI-5 is its own chunk and ships .webm
  without exception per the ChatGPT UI-3 review.
- Do NOT introduce a build step. Vite enters when a chunk
  needs TypeScript modules; UI-4 is HTML/CSS/inline-JS.
- Do NOT introduce a Live Map (UI-6) or detail drawer
  (UI-7).
```

## Anchor for the previous sessions

- UI-2 (design system + tokens page) merged 2026-05-03
  via PR #69 (`6ec5203`). One audit round; P0 on
  `prefers-reduced-motion` (clamp was global, not chromatic-
  whitelisted) fixed in `ae975f3`.
- UI-3 (application shell + `/api/meta`) merged 2026-05-03
  via PR #70 (`a67d729`). APPROVED on the first round.
  ChatGPT pinned a binding rule: **UI-5 ships `.webm`
  without exception** because the crow becomes the
  principal visual asset there.
- 392/394 pytest on Windows local. The 2 failures
  (`test_git_probe::test_git_tree_path_exists_passes_cwd_through`
  and `test_ui_server::test_valid_asset_under_static_dir_is_served`)
  also fail on `main` — preexisting Windows CRLF / cwd
  quirks. CI Linux green.
- Karasu HEAD: `a67d729` at session start. UI-4 branches
  off this commit.
