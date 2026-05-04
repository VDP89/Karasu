# UI-6 — Live Map screenshots

The Live Map paints five fixed domain nodes (user / karasu /
claude / codex / github) and flies the canonical crow between
them whenever the bus advances. Source / target nodes for the
current flight are flagged in `--accent` for the duration of the
600 ms ease-mag arc; everything else on the map (edges, labels,
container, surrounding shell) stays editorially still.

The recording lives at
`docs/ui/recordings/UI-6-livemap.webm` (242 KB) and walks the
dispatch chain across 6 frames so the auditor sees multiple
flight pairs in a single .webm without having to scrub.

## What to look at — the map projection

`/api/health.flight` (additive UI-6 field) carries either
`null` (the bus is silent OR the latest event is unmapped → the
crow parks) or `{"source": <node>, "target": <node>}`.
Precedence is documented in `src/karasu/ui/server.py::_flight_route`
and pinned by 22 unit tests in `tests/test_ui_server.py`. The
short version:

| Latest event                                            | Flight pair       |
|---------------------------------------------------------|-------------------|
| `file_change` (watcher / git_hook)                      | user → karasu     |
| `file_change` with router-assigned dispatch (pending / dispatched) | karasu → claude / codex |
| `file_change` with `controller_resubmit=true`           | user → karasu     |
| `file_change` with `github_event` / `source=github_webhook` | github → karasu |
| `agent_response` (completed OR failed)                  | claude / codex → karasu |
| `human_decision`                                        | user → karasu     |
| `git_event`                                             | user → karasu     |
| anything unmapped (incl. unknown event types)           | null (parked)     |
| empty bus                                               | null (parked)     |

The projection consults the LATEST event only. Older events
do not contaminate the route — a deliberately stricter rule
than `_crow_state`'s reverse walk, motivated by the operator's
"no invented recovery flight" pin. If you're surprised by what
the map shows, look at the latest line of the timeline beside
it: the timeline is the audit trail.

## Files in this directory

```text
00-empty-state-no-map.png             empty bus → empty-state hero, NO map.
                                      The map only appears once events
                                      populate the projection (UI-3 / UI-5
                                      contract carried into UI-6).
01-flight-user-to-karasu.png          latest = file_change watcher.
                                      Crow flies from the user node (left
                                      edge) into the karasu node (centre).
02-flight-karasu-to-claude.png        latest = file_change with claude_code
                                      dispatch pending. Outbound leg the
                                      timeline cannot read on its own.
03-flight-claude-to-karasu.png        latest = agent_response from
                                      claude_code (completed). Inbound
                                      leg, response landed.
04-flight-github-to-karasu.png        latest = github_webhook ingress.
                                      Source = github (top centre);
                                      target = karasu (centre).
05-flight-controller-resubmit.png     latest = controller_resubmit
                                      (operator scar). Same destination
                                      pair as 01 (user → karasu); the
                                      timeline beside it confirms the
                                      controller_resubmit marker so the
                                      auditor reads the semantics, not just
                                      the geometry.
06-flight-parked.png                  latest = unknown event type
                                      (synthetic future_event_type). flight
                                      is null; the crow is hidden and the
                                      map nodes return to --fg-2.
07-livemap-narrow-viewport.png        720×1280 viewport. Side-by-side
                                      collapses to stacked (map on top,
                                      timeline below). Map's aspect-ratio
                                      recovers to 4/3 so the nodes stay
                                      legible at narrow widths.
```

## Editorial pins to verify

These are the seven Codex pins carried forward from UI-3 / UI-4 /
UI-5; the .webm and the PNGs above are the artefacts the auditor
checks them against.

```text
1. Crow flight may animate; the SHELL must remain still.
   Verify in the .webm: header (logo + bus path), timeline rows
   on the right, footer cells (version + last event + crow
   state), .live-map container, .map-edges and node labels are
   all editorially still. Only the crow moves.

2. Flight transform belongs ONLY to .crow-flight.
   Cross-check via the diff: no transform / animation rule lives
   on .live-map, .map-node, .map-edge, the header chrome or any
   timeline element. .map-node--source / .map-node--target only
   shift fill colour (UI-2 chromatic whitelist).

3. SECOND asset shipped: crow-flight.svg with wings extended.
   The perched UI-5 crow is NOT rotated and re-used; the flight
   asset is a separate file under
   src/karasu/ui/static/assets/crow/crow-flight.svg.
   See docs/ui/assets/karasu_sprites_spec.md for provenance:
   adapted from game-icons.net "crow-dive" by Lorc, CC BY 3.0.

4. Beak-leading along path tangent.
   The CSS variable --flight-heading is computed from
   atan2(target.y − source.y, target.x − source.x) in the page
   JS; the asset's natural orientation (head UP) is compensated
   by --flight-asset-offset: 90deg so the head leads the +x
   axis. Magnitudes restrained — no barrel rolls.

5. .webm shows full-shell context.
   Recording viewport is 1024×640; the auditor sees full-shell
   context — header, map, timeline context and footer — without
   cropping to the flying crow alone. Note: 1024 px is BELOW the
   1280 px split breakpoint, so the timeline renders stacked
   below the map in this recording (the side-by-side layout
   shows in PNG 02 et al at the default 1440×900 viewport).

6. Map nodes / edges do NOT pulse, bounce, glow, or perform.
   Only the source / target dots shift fill to --accent for the
   duration of the flight (chromatic whitelist). Hover state on
   .map-node is also a colour-only transition. Verify in the
   .webm by comparing successive frames: the dots that aren't
   currently flagged as source / target stay the same size and
   --fg-2 colour.

7. /api/health-derived visual states are unit-tested.
   _flight_route precedence is pinned by 22 tests in
   tests/test_ui_server.py before the visual code lands.
   pytest tests/test_ui_server.py -v should report these as
   green.
```

## Layout decisions

Per the operator's UI-6 layout call:

```text
>= 1280 px viewport: map + timeline side-by-side (split column).
                     Timeline keeps its UI-4 max-width 720 px;
                     the map fills the remaining horizontal
                     space. Empty-state hero from UI-3 / UI-5
                     stays the first impression on a silent bus
                     — the map only appears once events populate
                     the projection.
<  1280 px viewport: stacked. Map on top, timeline below. The
                     map's aspect-ratio recovers to 4/3 at
                     <= 720 px so the nodes stay legible at
                     narrow widths.
```

Captures 00..06 use the default 1440×900 viewport (split layout);
capture 07 forces 720×1280 to verify the stacked layout.

## What is NOT here

- No PNG of the crow mid-arc. The CSS transition runs over
  600 ms but the `wait_ms=3500` of every capture lets the arc
  settle before the screenshot — the still PNGs land on the
  target. The mid-arc behaviour lives in the .webm, frame by
  frame.
- No scroll-zone capture. Live Map fits in 1024×640 without
  scrolling; the operator never scrolls inside the map.
- No reduced-motion PNG. The contract is documented in
  `docs/ui/assets/karasu_sprites_spec.md` and exercised by the
  JS path under `(prefers-reduced-motion: reduce)`. A future
  capture pass can add it; not blocking UI-6.
