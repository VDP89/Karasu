# Next Session Entry Point

## Goal

**UI-7 — the Detail panel.** Click a timeline row OR a Live Map
node and a lateral drawer slides in from the right with the
event's pretty-printed JSON. Custom syntax highlighting on the
existing palette (no highlight.js) — same editorial restraint
the rest of the surface earns through hand-set tokens, not
imported themes.

Per UI-0 §6: *"Click on timeline row or map node → lateral
drawer with pretty-printed JSON."* This is the chunk where the
operator goes from *seeing the system think* to *interrogating a
single beat*.

## Binding constraints carried forward (P0)

UI-6 audit added FIVE additional pins for UI-7+ (Codex,
2026-05-04, PR #78 APPROVED-with-observations). Verbatim:

```text
A. The Live Map is now an orientation layer, not a simulation
   layer.
B. UI-7 must not add motion to nodes, edges, timeline rows,
   header, footer, or map chrome unless a new audited chunk
   explicitly earns it.
C. Any new /api/health-derived visual state must ship with
   tests before screenshots.
D. Keep latest-event semantics for flight unless a future PR
   explicitly introduces stateful route memory and tests it.
E. Do not let the detail drawer or inspector compete with the
   crow/map; the surface remains editorial, not dashboard.
```

Pin E is the immediately load-bearing one for UI-7: the drawer
must NOT borrow the visual weight of the crow or the map. Slide
in, present JSON, slide out. No icons, no chrome, no badges.

The seven Codex pins from UI-3 / UI-4 / UI-5 / UI-6 audits stay
binding. The new chunk introduces motion (a drawer panel slides
in) so several pins re-fire:

```text
1. Crow flight may animate; the SHELL must remain still. UI-7
   adds a drawer that slides in over the canvas — the drawer
   IS the new motion surface, but the shell behind it (header,
   timeline beats, map nodes, footer) does NOT shift, scale,
   blur or fade while the drawer opens. The drawer floats,
   the shell stays.

2. Transform belongs to the moving element only. The drawer's
   translate-X transition lives on the drawer itself, not on
   .shell-main, .live-map, the timeline rows, etc. The crow
   in the live-map continues to fly during a drawer-open if
   the bus advances; the two motions are independent.

3. The drawer needs --shadow-2 (the elevation token UI-0 §5.4
   reserves for it). This is the SECOND motion-introducing
   chunk after UI-5 / UI-6, so the audit cadence (PNG + .webm
   ≤ 5 s ≤ 500 KB ≥ 1024×640) applies again WITHOUT exception.

4. Custom syntax highlighting. NO highlight.js, NO prism.
   Use the existing tokens (--accent for keys, --warn for
   strings, --fg-2 for punctuation, --fg-3 for braces) and
   write the highlighter in vanilla TS. ~50 LOC.

5. Reduced motion contract holds. The slide transition clamps
   to 1ms via reset.css's chromatic whitelist; the drawer
   appears instantly. State change still legible.

6. Map nodes / edges still NOT pulse, bounce, glow. Click on
   a node opens the drawer; that click's only visual effect
   on the node is :focus-visible (UI-3 focus ring). No
   "selected" pulse.

7. Any visual state derived from a server projection MUST be
   covered by unit tests. UI-7's projection is whatever
   /api/events already returns plus an ID-targeted single-event
   read; if a new endpoint or field appears, the unit tests
   are NOT optional.
```

## What ships in UI-7

```text
src/karasu/ui/static/css/drawer.css                NEW.
  - .drawer container: position fixed, right edge, slides
    in from off-canvas. Width clamped (min 360 px / 90 vw,
    max 560 px). --bg-1 background, hairline left border.
  - .drawer.is-open: transform: translateX(0). Default state
    is translateX(100%) (off-canvas).
  - .drawer-close button: top-right, --fg-2, hover --fg-1.
  - .drawer-body: scrollable, max-height calc(100vh - header).
  - .drawer-key, .drawer-string, .drawer-number, .drawer-bool,
    .drawer-null: token-driven syntax highlighting.

src/karasu/ui/static/index.html  (extension)
  - <aside class="drawer" hidden> at the bottom of the shell.
  - JS: clickable timeline rows + map nodes that open the
    drawer with the relevant event. Esc / click-outside / X
    button to close.
  - Highlighter in ~50 LOC vanilla TS — operates on the
    JSON.stringify(event, null, 2) output, walks token-by-
    token, emits <span class="drawer-...">.

src/karasu/ui/server.py  (extension)
  - Optional: GET /api/events/<id> for single-event lookup.
    The /api/events list already returns enough; UI-7 can
    open the drawer purely from client-side state (the row
    or node carries the event id, the JS reads from the
    most recent /api/events response). Add the endpoint
    only if the audit asks for it.
  - No projection change otherwise.

tests/test_ui_server.py  (extension if /api/events/<id> ships)
  - Single-event lookup: known id returns 200 + projection;
    unknown id returns 404; bus empty returns 404.

scripts/ui_screenshots.py  (extension)
  - UI-7 capture plan: drawer-closed, drawer-open-on-timeline-
    row, drawer-open-on-map-node, drawer-narrow-viewport.
  - --record-video walks click → open → switch row →
    close, full-shell.

docs/ui/screenshots/UI-7-detail/   NEW.
  - PNGs + README per UI-2..UI-6 pattern.

docs/ui/recordings/UI-7-detail.webm   NEW.
```

## Surface contract — must respect

```text
- UI = read-only sink. UI-7 stays read-only against the bus.
- Frozen contracts: AgentResponse, F3, F7, F8, surface=sink,
  single-worker invariant, scar=stored-correction-only,
  I-001..I-006, TriggerSource Protocol, bus event schema,
  the /api/health additive fields shipped in UI-3..UI-6.
- The empty-state hero from UI-3 stays the first impression.
- The Live Map from UI-6 keeps flying while the drawer is
  open — they are independent motions.
- No build step. CSS / TS ship static.
- No new runtime dependency.
```

## Open questions to resolve while planning

```text
1. Click target on the map node: the dot OR the whole .map-node
   <g>? Hit area vs. label collision. Lean: the whole <g> with
   tabindex (already there); the dot stays small for editorial
   weight but the click registers anywhere over the node group.

2. Drawer payload — full event JSON or filtered projection?
   Lean: the projection (what /api/events already returns).
   Adding the raw bus event would surface schema fields the
   surface contract does NOT cover yet (event_metadata,
   internal trace ids); the projection is the canonical UI
   read.

3. Multiple drawers? Stacked? Lean: ONE drawer at a time. A
   second click closes the first. Avoids a queue, avoids a
   UX that asks the operator to remember which is which.

4. Map-node click → which event opens? The latest event whose
   _flight_route maps to that node. Two cases: source-side
   click (e.g. user) → latest event flying FROM user; target-
   side click (e.g. claude) → latest event flying TO claude.
   Empty if none. Document the rule in the README.

5. Highlighter scope: full JSON syntax (objects / arrays /
   strings / numbers / booleans / null) plus comment-style
   metadata? Lean: full JSON syntax, NO comment styling
   (the projection doesn't carry comments). 5 token classes,
   not 7.
```

## Audit cadence reminder

```text
1. Real PNG screenshots under docs/ui/screenshots/UI-7-detail/
   for every visible state (closed / open-from-timeline /
   open-from-map / narrow-viewport).
2. .webm at docs/ui/recordings/UI-7-detail.webm
   (≤ 5 s, < 500 KB, full-shell ≥ 1024×640).
3. "What to look at" note covering: the drawer slide motion,
   shell stillness behind the drawer, syntax highlighting
   tokens, click-outside / Esc close behaviour.
4. The diff itself.
5. The audit prompt for Codex out-of-band via ChatGPT.
6. Editorial check: pins #1 + #2 — verify SHELL stays still
   while drawer opens. Pin #4 — atan2 unchanged. Pin #5 —
   .webm shows full-shell context.
7. Unit-test check: pin #7 — if /api/events/<id> ships, the
   projection MUST be covered.
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §5.4 (SHADOW — --shadow-2 is
   reserved for the drawer) + §5.5 (motion durations: panel
   240ms ease-out for the drawer slide) + §6 (UI-7 roadmap
   entry).
2. docs/ui/screenshots/UI-6-livemap/README.md — the precedent
   for "what to look at" structure.
3. src/karasu/ui/static/css/timeline.css — feature CSS split
   pattern; drawer.css mirrors it.
4. src/karasu/ui/static/index.html — current shell layout +
   the JS pattern from UI-6 (event delegation, click handling).
5. src/karasu/ui/server.py — add /api/events/<id> here ONLY
   if the audit asks for it; UI-7 can land without a server
   change.
```

## Chunk size estimate

```text
Code:       ~250 LOC (drawer.css + index.html extension +
            highlighter ~50 LOC + tests if endpoint ships)
Assets:     no new SVG (the drawer is pure CSS / type)
Docs:       ~80 LOC (screenshots README)
Tests:      single-event projection if endpoint ships
Total:      under the 400 LOC budget.
```

## Do NOT do yet

```text
- Do NOT animate anything outside .drawer during the slide.
  Pin #1 + #2 binding.
- Do NOT import highlight.js / prism / shiki. The token-driven
  vanilla highlighter is the editorial choice.
- Do NOT introduce node "selected" animations (pulse, glow).
  Pin #6 binding.
- Do NOT crop the .webm to the drawer alone. Pin #5 binding.
- Do NOT introduce a build step.
- Do NOT introduce write paths to the bus.
- Do NOT tag @codex review. Audits stay operator-mediated.
```

## Anchor for the previous sessions

- **UI-6 (Live Map + crow flight) PR open.** `_flight_route`
  projects the LATEST event to a `(source, target)` pair on
  `/api/health.flight` (additive). Five domain nodes painted
  on a static SVG canvas (user / karasu / claude / codex /
  github); the SECOND canonical asset (`crow-flight.svg`,
  adapted from game-icons.net "crow-dive" by Lorc, CC BY 3.0)
  flies between them on bus advances. 22 unit tests + 2
  HTTP-level tests pin the projection BEFORE the visual code
  lands (pin #7). Layout: side-by-side ≥1280 px, stacked
  below; empty-state hero stays the first impression. SVG-
  element bug self-caught in autonomous review:
  `crowFlight.hidden=false` on an `<svg>` creates a non-
  reflecting expando (the IDL `hidden` property is HTMLElement-
  only); fix uses `removeAttribute('hidden')` /
  `setAttribute('hidden','')`. 8 PNGs + 1 .webm 242 KB
  full-shell 1024×640.
- UI-5 (canonical crow + state animations) merged 2026-05-04
  via PR #74 (`904111a`). Three audit rounds before APPROVED.
- UI-4 (event timeline) merged 2026-05-03 via PR #72.
- UI-3 (application shell) merged 2026-05-03 via PR #70.
- 421/422 pytest on Windows local (399 prior + 22 new
  `_flight_route` tests). The same single preexisting failure
  (`test_valid_asset_under_static_dir_is_served`, Windows
  CRLF) remains; CI Linux green.
- Karasu HEAD post-merge: TBD (UI-6 PR open, awaiting audit).
