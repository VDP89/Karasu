# UI-7 — Detail panel screenshots

Click a timeline row OR a Live Map node and a lateral drawer
slides in from the right with the event's pretty-printed JSON
projection. Five-token vanilla highlighter (`json-key` /
`json-string` / `json-number` / `json-bool` / `json-null`)
keyed off the existing palette in `drawer.css` — no
highlight.js, no prism, no shiki.

The recording lives at
`docs/ui/recordings/UI-7-detail.webm` (336 KB) and walks the
full open / switch / close sequence in one Playwright context:
boot → click timeline row → close via Esc → click claude
node → close via backdrop.

## What to look at — drawer behaviour

The drawer is read-only: clicking opens it, clicking outside /
pressing Esc / pressing the X closes it. The bus is never
mutated by UI-7 (write paths arrive in UI-10+). Two click
sources, one drawer:

| Click target            | Resolved event                           |
|-------------------------|------------------------------------------|
| `.event-row`            | event by `dataset.eventId` from `latestEvents` |
| `.map-node`             | latest event whose `_flight_route` pair includes the node id (source OR target) |
| Backdrop / X button / Esc | close                                  |

Map-node lookup walks `latestEvents` newest-first and stops at
the first event whose mapping includes the clicked node. If no
event in the tail involves the node, the drawer still opens but
renders `This node has not seen traffic yet.` (italic, muted) —
the empty body branch.

## Files in this directory

```text
00-drawer-closed.png             Drawer hidden. Verify the shell
                                 is exactly UI-6 with no leak —
                                 no visible backdrop, no chrome
                                 hint that the drawer markup
                                 exists.
01-drawer-from-timeline-row.png  Click on the latest timeline
                                 row → drawer opens with header
                                 (timestamp + type + ×) and the
                                 event JSON highlighted body.
02-drawer-from-map-node-claude.png
                                 Click on the claude node → drawer
                                 opens with the LATEST event whose
                                 _flight_route pair touches claude
                                 (the file_change with the pending
                                 dispatch in this corpus).
03-drawer-empty-node.png         Click on the codex node while the
                                 corpus has no codex traffic →
                                 drawer opens with empty body
                                 ("This node has not seen traffic
                                 yet."). The codex node carries a
                                 :focus-visible ring (UI-3 focus
                                 contract) once focused by the
                                 click.
04-drawer-github-webhook.png     Click on the latest row of a
                                 github-webhook corpus → drawer
                                 body shows the full github_*
                                 metadata (event, action, pr,
                                 repo, author) populated, all
                                 strings rendered through the
                                 highlighter without HTML escapes.
05-drawer-narrow-viewport.png    720×1280 viewport. Drawer takes
                                 100vw at <= 720 px so the
                                 operator on a tablet can read
                                 the JSON full-width.
```

## Editorial pins to verify

The five pins Codex added on the UI-6 audit (PR #78) are all
load-bearing for UI-7. Plus the seven pins carried forward from
UI-3 / UI-4 / UI-5.

```text
A. Live Map = orientation, not simulation.
   Drawer is the new motion surface; the map remains a static
   chrome behind the slide. Verify in the .webm: the crow keeps
   flying its 600 ms arc independently of drawer-open / close;
   the two motions are decoupled. Map nodes / edges do not gain
   any new motion in UI-7.

B. UI-7 must not add motion to nodes, edges, timeline rows,
   header, footer, or map chrome.
   Diff check: drawer.css introduces ONE transition surface
   (.drawer transform 240 ms ease-out) plus ONE colour-only
   transition on .drawer-close hover. No transform / animation
   rule lives on .event-row, .map-node, .map-edge, the header
   chrome or the footer.

C. /api/health-derived state requires unit tests.
   UI-7 adds NO new server projection — it reads /api/events
   exactly as UI-4 ships it and resolves drawer payloads
   client-side. No /api/health.flight change. The server side
   of this PR is empty by design (zero new endpoints, zero
   schema changes). pytest tests/test_ui_server.py -v stays
   green at 41/42 (the one preexisting Windows CRLF failure
   carries forward).

D. Latest-event semantics for flight unless explicitly extended.
   The map-node-click resolver mirrors _flight_route's mapping
   table client-side and walks the tail ONLY for the
   single-node lookup; it does NOT introduce stateful route
   memory or recovery flights. If a node has no traffic yet,
   the result is null and the drawer renders the empty body —
   not an invented "would-fly" pair.

E. Detail drawer must not compete with the crow / map.
   No icons, no chrome badges, no decorative dividers. Drawer
   header is one row: timestamp (mono, muted) + type (display,
   fg-1) + unstyled × close. Body is type only (mono, fg-2,
   highlighted with --accent / --warn / --fg-1 / --fg-3 — the
   existing palette). 5 highlighter classes, not 15. The
   drawer slides in; it does not pulse, breathe, or ornament.
```

The seven pins from earlier audits also hold:

```text
1. Crow flight may animate; the SHELL must remain still.
   Drawer slide IS the new chrome motion; the rest of the
   shell stays still while the drawer opens.

2. Transform belongs only to the moving element. .drawer's
   translateX is the new motion surface; no transform leaks.

3. The drawer earns --shadow-2 (the elevation token UI-0 §5.4
   reserves for it). Visible in the screenshots: the drawer
   floats above the canvas with a soft blur edge, distinct
   from the rest of the shell which uses --shadow-0 / --shadow-1
   only.

4. atan2 beak-leading rotation in UI-6 is unchanged.

5. .webm shows full-shell context (1024×640).

6. Map nodes / edges do NOT pulse, glow, bounce.
   :focus-visible ring on a clicked node is the UI-3 focus
   contract, NOT a UI-7-introduced animation.

7. State projection unit tests — UI-7 introduces no server
   projection, so this pin stays satisfied by the UI-6 tests.
```

## Layout decisions

```text
>= 720 px viewport: drawer width clamp(360px, 40vw, 560px). At
                    1440 px viewport the drawer is 560 px and
                    leaves the shell behind it readable.
<= 720 px viewport: drawer takes 100vw. The JSON body still
                    wraps long strings (white-space: pre-wrap +
                    word-break: break-word) so paths and github
                    URLs do not horizontal-scroll.
```

## What is NOT here

- No PNG mid-slide. The 240 ms transition lives in the .webm;
  the still PNGs land on the open OR closed states. The brief
  follows UI-5 / UI-6 — animation truth is in the recording.
- No reduced-motion PNG. Under `prefers-reduced-motion: reduce`
  the chromatic whitelist in reset.css restricts
  `transition-property` to colour-only properties; the drawer's
  transform and the backdrop's opacity therefore become
  effectively instant rather than animated, and the drawer still
  appears — just without the 240 ms slide / fade. Documented
  with the same wording in drawer.css. A future capture pass
  can add it; not blocking UI-7.
- No new server endpoint screenshots. UI-7 is server-empty —
  pure client-side composition over the existing /api/events
  projection. If a future chunk adds /api/events/<id>, the
  per-id projection unit tests will land WITH the visual code,
  per Codex pin C.
