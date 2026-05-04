# Next Session Entry Point

## Goal

**UI-6 — the Live Map. Five domain nodes + crow flight per bus event.**

Per UI-0 design brief §6, UI-6 is *"the chunk where the watchtower
becomes coordinated motion"*. Five fixed nodes (User / Karasu /
Claude / Codex / GitHub) with edges defined by the bus event flow.
On each `file_change` / `agent_response` / `human_decision`, the
canonical crow shipped in UI-5 flies between the relevant nodes
along an SVG arc-path, 600 ms ease-mag, beak leading the tangent.

UI-6 is the second motion-introducing chunk after UI-5; it ships
a `.webm` recording in the same PR — **no exception** per the
binding rule Codex pinned across UI-3 / UI-5 audits.

## Binding constraints from UI-3 / UI-4 / UI-5 audits (P0)

Seven binding rules carried forward, all pinned by Codex in
prior audit verdicts. Treat as P0 if violated, NOT as guidance.

```text
1. Crow flight may animate; the SHELL must remain still.
   (Inherits "el crow puede tener vida; la superficie no
   puede perder calma" from UI-4 + extends to the new map
   chrome.)

2. Flight transform belongs ONLY to the crow / flying-crow
   element. Header chrome, timeline rows, footer cells, AND
   the new map chrome (nodes, edges, labels, container) are
   editorially still. No transform / animation on any of
   those.

3. UI-6 needs a SECOND asset: crow-flight.svg with wings
   extended. Do NOT rotate the perched UI-5 crow and call it
   flight — wings are folded; rotating the perched crow reads
   as "tossed by the air", not flying. Source candidates
   (same hunt pattern as UI-5): OpenMoji bird default pose,
   Wikimedia "flying crow silhouette", heraldic raven
   displayed. CC-licensed; attribute in the asset comment +
   sprites_spec.md.

4. The flying crow must be BEAK-LEADING along the path
   tangent, with RESTRAINED rotation. Compute heading via
   atan2(dy, dx) on each animation frame (or as a single
   transform-origin + rotate at midpoint if frame-by-frame
   is too noisy). Keep the rotation magnitude functional,
   not theatrical — if the crow looks like it's doing
   barrel rolls, the magnitude is too large.

5. UI-6 .webm must show full-shell context (1024 × 640 or
   wider — the map will need horizontal real estate). NOT a
   cropped animation demo focused only on the flying crow.
   Auditor must be able to confirm BOTH that the crow flies
   AND that nothing else moves from a single frame.

6. Live Map nodes / edges must NOT pulse, bounce, glow, or
   "perform" unless a later audited chunk explicitly earns
   that motion. Static nodes + a flying crow is the entire
   choreography for UI-6. Hover states for nodes are OK
   (colour transition only, per UI-2's chromatic whitelist).

7. Any visual state derived from /api/health (or any other
   server projection) MUST be covered with unit tests.
   UI-5 caught _crow_state mid-audit because the projection
   bug shipped to PNG / .webm artefacts; UI-6 adds at least
   one new projection (which node is "active" given the bus
   tail), so the precedence MUST be pinned in
   tests/test_ui_server.py before the visual code lands.
```

## What ships in UI-6

```text
src/karasu/ui/static/assets/crow/crow-flight.svg   NEW.
  - Wings extended silhouette per UI-0 §5.6 (vector,
    monochrome, currentColor, scales).
  - viewBox sized for the flight pose (probably wider than
    UI-5's 72×72 to fit the wings).
  - Source: TBD — operator-vetted CC-licensed asset adapted
    to currentColor + the editorial vibe (austere, instrument,
    not friendly).
  - Optional: small operator-added details (eye notch in same
    canvas-colour pattern as UI-5).

src/karasu/ui/static/css/map.css                   NEW.
  - .live-map container: grid layout for the five nodes,
    fixed positions in the available canvas area.
  - .node base: dot or small mark + label. Static; hover
    colour transition only (UI-2 chromatic whitelist).
  - .edge: optional faint hairline (--fg-3) between
    connected nodes — purely visual scaffolding for the
    flight path. May be omitted if the flight arc itself
    reads enough.
  - .crow-flight base: position absolute over the map,
    transform-origin centre, transitions wired in JS.

src/karasu/ui/static/index.html  (extension)
  - New <section class="live-map"> in main, alongside the
    existing timeline. May replace the timeline as the
    "default view" or sit beside it — design call for the
    chunk plan.
  - Inline <svg class="crow-flight"> with the canonical
    flight asset, hidden by default.
  - JS in the existing <script> block: subscribes to /api/events,
    on each new event computes (source_node, target_node)
    and triggers a flight transition.

src/karasu/ui/server.py  (extension)
  - NEW projection helper: _flight_route(events) → returns
    (source, target) tuple identifying which two nodes the
    most-recent event flies between. Mirrors _crow_state's
    pattern: read-only projection over the event tail.
  - /api/health gains a `flight` field with this projection
    (additive, doesn't break UI-3..UI-5 consumers).

tests/test_ui_server.py  (extension)
  - Unit tests for _flight_route covering: each event
    type → expected (source, target); empty events →
    (None, None); precedence on multiple recent events.
  - Mandatory per Codex pin #7 (state projection bugs must
    be covered with unit tests). UI-5 shipped without these
    and the bug went visual before being caught.

scripts/ui_screenshots.py  (extension)
  - UI-6 capture plan: PNGs at flight midpoints + at-rest
    states + the empty-state map (no events).
  - --record-video continues to work; the recording walks
    a dispatch chain (file_change → agent_response →
    human_decision → resubmit) so the auditor sees multiple
    flights in one .webm.

docs/ui/screenshots/UI-6-livemap/   NEW.
  - PNGs + README per UI-2/UI-3/UI-4/UI-5 pattern.
  - "What to look at" section covering: which event types
    fly between which nodes, the flight transform tangent,
    and the SHELL stillness (re-confirming pin #1 + #2).

docs/ui/recordings/UI-6-livemap.webm   NEW.
  - The recording.
  - <500 KB. Same transcoding fallback as UI-5 if needed.
  - Full-shell viewport per pin #5.

docs/ui/assets/karasu_sprites_spec.md   (UPDATE)
  - Document crow-flight.svg as a SECOND canonical asset.
  - Provenance + CC attribution for the flight pose source.
  - State table reads now: idle/processing/waiting/error
    use crow.svg; flight uses crow-flight.svg as a phase
    overlay during transitions.
```

## Surface contract — must respect

```text
- UI = read-only sink. UI-6 only adds GET /api/health
  field (additive); no projection change to /api/events;
  no bus mutation.
- No new bus event types. The flight phase derives entirely
  from existing event tail.
- No new runtime dependency. Stdlib + the assets shipped
  in UI-2..UI-5. Playwright stays dev-only.
- No build step. SVG and CSS ship static.
- Frozen contracts: AgentResponse, F3, F7, F8, surface=sink,
  single-worker invariant, scar=stored-correction-only,
  I-001..I-006, TriggerSource Protocol, bus event schema —
  none touched.
- The empty-state hero from UI-3 stays the first impression
  on a silent bus; UI-6 introduces the map only when events
  populate the projection.
```

## Open questions to resolve while planning

```text
1. Map vs timeline: replace, sit beside, or toggle? UI-3
   shipped the timeline as the default "events exist" view.
   Does UI-6's map replace it, sit alongside (split view),
   or get toggled by a UI-7 detail panel? Lean: sit alongside
   in a two-column layout on wide viewports, stacked on
   narrow. Confirm with operator before coding.

2. Flight route projection: deterministic per event type, or
   data-driven from event metadata? Lean: deterministic
   table — file_change → User→Karasu, agent_response →
   adapter→Karasu, github_webhook → GitHub→Karasu, etc.
   Keep the table small and document it in the spec.

3. Multiple concurrent dispatches: queue, parallel, or
   coalesce? Karasu's single-worker invariant means at most
   one dispatch in flight at the pipeline level, but the
   visual flight (600 ms) may overlap with the next event's
   queued flight. Lean: queue strictly — if a flight is in
   progress, the next event's flight starts on completion.
   Avoids visual chaos; matches the pipeline's serial truth.

4. Reduced motion for flight: per UI-2's chromatic whitelist,
   transforms clamp to 1 ms. Flight stops being a flight
   under reduced-motion. Lean: instead, swap the crow asset
   to crow-flight.svg at the SOURCE node + INSTANT relocate
   to the TARGET node + swap back to crow.svg. No transition,
   but the state change is still legible.

5. Flight asset hunt: OpenMoji bird default pose vs Wikimedia
   "Carrion crow in flight" vs heraldic raven displayed. The
   heraldic option is most aligned editorially (austere,
   instrument, classical). Investigate first.
```

## Audit cadence reminder

Per UI-0 §7 + the binding pins:

```text
1. Real PNG screenshots under docs/ui/screenshots/UI-6-livemap/
   for every visible state.
2. .webm recording at docs/ui/recordings/UI-6-livemap.webm
   (≤5 s, <500 KB). REQUIRED per Codex UI-3 pin.
3. A "what to look at" note covering type/node mapping,
   flight rotation magnitudes, and reduced-motion behaviour.
4. The diff itself.
5. The audit prompt for Codex (out-of-band via ChatGPT).
6. Editorial check: pin #1 + #2 + #6 — verify SHELL stays
   still. Pin #5 — verify .webm shows full-shell context.
7. Unit-test check: pin #7 — _flight_route projection MUST
   be covered. UI-5 shipped without _crow_state tests and
   Codex caught the bug visually instead of structurally.
   Don't repeat.
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §5.6 (crow assets) +
   §6 (UI-6 roadmap entry) + §5.5 (motion durations,
   ease-mag for flight, reduced-motion contract).
2. docs/ui/assets/karasu_sprites_spec.md — UI-5's spec +
   the "States the crow does NOT carry yet" section that
   pre-documents the flight asset contract.
3. src/karasu/ui/server.py — _crow_state + _read_events
   patterns to mirror for _flight_route.
4. src/karasu/ui/static/css/crow.css — UI-5's keyframes,
   ease-mag definition, reduced-motion contract — same
   primitives apply to flight.
5. src/karasu/ui/static/index.html — current shell layout
   (header / main / footer grid). UI-6's map slots into
   main.
6. tests/test_ui_server.py — _crow_state unit tests as the
   pattern to follow for _flight_route.
```

## Chunk size estimate

```text
Code:       ~300 LOC (crow-flight.svg + map.css + index.html
            extension + _flight_route + tests + ui_screenshots
            UI-6 capture plan)
Assets:     1 SVG asset (crow-flight, small), 5+ PNGs + 1 webm
Docs:       ~100 LOC (screenshots README + sprites_spec
            update for the flight asset)
Tests:      _flight_route precedence (mandatory per pin #7)
Total:      under the 400 LOC code budget.
```

## Do NOT do yet

```text
- Do NOT animate anything outside .crow-flight during a
  flight. Pin #1 + #2 binding.
- Do NOT rotate the perched UI-5 crow as a substitute for a
  proper flight asset. Pin #3 binding.
- Do NOT introduce node "performance" animations (pulse,
  glow, bounce). Pin #6 binding.
- Do NOT crop the .webm to the flying crow alone. Pin #5
  binding.
- Do NOT ship the projection without unit tests. Pin #7
  binding — UI-5's audit caught _crow_state visually because
  no tests pinned the precedence; don't repeat.
- Do NOT introduce a build step. SVG and CSS ship static.
- Do NOT colour-code event types in the timeline (still
  binding from UI-4). Chroma stays reserved for the crow
  state, --accent, --error.
- Do NOT introduce write paths to the bus. UI-10+ scope.
```

## Anchor for the previous sessions

- **UI-5 (canonical crow + state animations) merged 2026-05-04
  via PR #74 (`904111a`).** Three audit rounds before APPROVED:
  (1) FA vector → operator rejected (consumer-mascot); (2) pixel-
  art pivot → Codex P0 (off-brief per UI-0 §5.6); (3) audit-
  response vector adapted from OpenMoji "Black Bird"
  (CC-BY-SA 4.0, attributed) + operator-added legs and eye
  notch; (4) Codex caught a separate `_crow_state` projection
  bug on re-audit (completed-tail mis-rendered as processing);
  fix re-checks LATEST event explicitly + 7 unit tests pin the
  precedence. APPROVED with observations on the 5th round.
  P2 (root NOTICE / THIRD_PARTY_NOTICES.md for OpenMoji
  licence trail) deferred as a follow-up issue.
- UI-4 (event timeline) merged 2026-05-03 via PR #72
  (`13e6270`). APPROVED first round.
- UI-3 (application shell) merged 2026-05-03 via PR #70
  (`a67d729`). APPROVED first round.
- 399/394 pytest on Windows local (392 prior + 7 new
  `_crow_state` tests). The two preexisting failures
  (`test_git_probe::test_git_tree_path_exists_passes_cwd_through`
  and `test_ui_server::test_valid_asset_under_static_dir_is_served`)
  remain — Windows CRLF / cwd quirks; CI Linux green.
- Karasu HEAD: `904111a` at session close. UI-6 branches off
  this commit (or the docs(memory) sync that lands before
  it; both are fast-forward).
