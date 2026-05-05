# UI-9 — server tests + reduced-motion smoke

UI-9 closes the read-only watchtower MVP. The chunk is
verification-only: zero new endpoints, zero projection changes,
zero shell affordances. Pure test + audit infrastructure over
the surface UI-1..UI-8 already shipped.

## What ships

```text
tests/test_ui_server_http.py          10 HTTP-level shape lock
                                      tests pinning the wire
                                      contracts for /api/events,
                                      /api/health, /api/meta,
                                      /assets/sw.js (the
                                      Service-Worker-Allowed
                                      header), /offline.html
                                      (route + body + .offline
                                      class), and
                                      /assets/manifest.json
                                      (colour parity with
                                      tokens.css + top-level
                                      shape).
scripts/ui_lighthouse.py              CLI runner. Spins up the
                                      server, runs Lighthouse via
                                      npx, asserts thresholds
                                      95 / 95 / 95 / 90, writes
                                      a JSON report to
                                      docs/ui/lighthouse/<date>.json.
docs/ui/lighthouse/README.md          Threshold contract +
                                      Lighthouse-recommendations-
                                      to-ignore list (Codex
                                      pin #2 binding).
docs/ui/screenshots/UI-9-tests/       This directory — 5 PNGs
                                      forcing prefers-reduced-
                                      motion: reduce on every
                                      surface state.
```

The chunk introduces NO production code. The only `src/`
file touched is the existing
`scripts/ui_screenshots.py` which gains a `reduced_motion`
plan key plus a `UI-9-tests` capture entry.

## What to look at — reduced-motion surface integrity

Each PNG forces `prefers-reduced-motion: reduce` via Playwright
`emulate_media`. Under that media query, `static/css/reset.css`
restricts `transition-property` to a chromatic whitelist
(`color`, `background-color`, `border-color`, `outline-color`,
`text-decoration-color`, `fill`, `stroke`, `box-shadow`); every
transform / opacity / size transition becomes effectively
instant. The captures verify that the surface still renders
correctly without the motion that UI-2..UI-8 carry by default.

| File | What you should see |
|---|---|
| `00-empty-state-reduced-motion.png` | Empty hero with the perched crow STATIC (ambient breathing loop paused). The single editorial sentence renders normally. |
| `01-timeline-reduced-motion.png` | UI-4 timeline with rows visible, no hover transition mid-shot, type token / meta line legible. |
| `02-livemap-reduced-motion.png` | UI-6 Live Map. Source / target nodes flagged in `--accent` (chromatic — runs at full duration); the crow flight INSTANT-relocated to the target rather than arc-animated. |
| `03-drawer-reduced-motion.png` | UI-7 drawer in the open state — slide is instant under reduced motion, not animated. JSON highlighter renders the 5 token classes correctly. |
| `04-offline-reduced-motion.png` | UI-8 offline page. `.crow.offline` is already static (`animation: none` + `rotate(4deg)` + `opacity 0.7`); reduced motion does not change anything for this page — the capture pins that fact. |

## What changes vs. the default-motion captures

```text
UI-2..UI-5 ambient breathing       → paused
UI-5 processing pulse              → frozen
UI-5 waiting tilt forwards         → still applies (forwards
                                      animation; the *transform*
                                      is the steady state, not
                                      a transition)
UI-5 error shake                   → no shake (single beat
                                      animation, transform
                                      whitelist excludes
                                      transform)
UI-6 600 ms ease-mag flight arc    → instant relocate
UI-7 240 ms drawer slide           → instant appearance
UI-7 backdrop fade-in               → instant appearance
                                      (opacity not on chromatic
                                       whitelist)
UI-8 .crow.offline                 → unchanged (already static)
```

Colour transitions still run at full duration in every shot —
that is the chromatic whitelist contract.

## Editorial pins to verify

The seventeen binding pins from UI-2..UI-8 audits all hold.
UI-9 introduces zero new motion / endpoint / shell affordance,
so each pin re-fires trivially:

```text
1. SHELL still — every reduced-motion PNG shows header /
   timeline / map / footer / drawer / offline shell static.
   The chunk literally cannot regress this pin (no production
   code change touches the shell).

2. Transform isolation — same.

3. /api/health-derived state unit-tested — UI-9 closes the
   loop. Every projection now has a structural shape lock
   in tests/test_ui_server_http.py BEFORE any future visual
   change can drift the wire.

4. Beak-leading tangent — UI-6 maths unchanged, captured
   under reduced motion in 02 (instant relocate respects
   the heading via the same atan2 formula).

5. .webm full-shell context — n/a for UI-9 (no new motion).

6. Map nodes / edges no perform — verifiable in 02.

7. /api/health unit tests — see test_ui_server_http.py.

A. Map = orientation, not simulation — captured under
   reduced motion in 02.

B. UI-N must not add motion to nodes / edges / timeline /
   header / footer / map chrome — UI-9 adds zero motion.

C. /api/health-derived state needs tests — UI-9 SHIPS the
   tests. Every projection state surface is now pinned.

D. Latest-event semantics for flight — projection unchanged.

E. Drawer / inspector does not compete with crow / map —
   UI-9 adds nothing to the drawer.

UI-8 P1 contracts:
P1#1. /api/* network-only is FIRST-BRANCH in sw.js — the
      HTTP shape locks verify the server-side live
      projection (the tests hit the server directly; they
      do NOT exercise the browser service worker). The SW
      network-only rule remains covered structurally by
      the sw.js fetch handler ordering shipped in UI-8 plus
      the manual DevTools verification path documented in
      docs/ui/screenshots/UI-8-pwa/README.md. UI-9 rules
      out a server-side regression that would corrupt the
      live projection; UI-8 + the manual path rule out a
      client-side regression that would cache it. Codex P2
      polish on PR #81 audit clarified the boundary.
P1#2. Empty localStorage → muted "bus —" — verifiable in
      offline.html body (test pins the editorial sentence,
      not the bus line, but the manual verification path
      in UI-8-pwa/README.md covers it).
P1#3. CACHE_NAME explicit + bump rule — sw.js docstring +
      lighthouse README cross-reference.

UI-8 P2 polish:
P2#1. Offline pose signal-lost — verifiable in 04.
P2#2. No .webm for static infrastructure — UI-9 honours
      this by absence (no new motion = no recording).
P2#3. Manifest hex matches tokens.css — pinned by
      test_manifest_colours_match_tokens_css_exactly.
```

## Codex pins from UI-8 audit (PR #80) honoured

```text
1. UI-9 should validate the PWA contracts with tests where
   feasible — DONE. /api/* shape locks (which depend on the
   SW not caching them), /assets/sw.js Service-Worker-Allowed
   header, /offline.html route + body + .offline class,
   manifest colour parity with tokens.css, manifest top-level
   shape. All in tests/test_ui_server_http.py.

2. Lighthouse is verification, not design driver — DONE.
   docs/ui/lighthouse/README.md ships an explicit
   "Recommendations to ignore" list. The runner asserts
   thresholds; it does NOT prescribe shell additions.

3. SW cache behavior boring: explicit version, explicit
   precache, no runtime caching for live projections — pinned
   by the UI-8 sw.js (no UI-9 change required, the contract
   was set in UI-8 and tests/test_ui_server_http.py
   structurally depends on it).

4. Tests touching SW behavior prefer deterministic
   assertions — the UI-9 tests assert response headers and
   body shapes, not browser SW state.

5. No install banners, update toasts, connection badges,
   "offline mode" dashboard furniture — UI-9 ships ZERO
   new shell affordances. Pin satisfied by absence.
```

## Test plan

```bash
# Unit + HTTP shape locks (the verification surface this
# chunk lands).
python -m pytest tests/test_ui_server_http.py -v

# Full pytest run — UI-9 must keep the existing coverage
# green.
python -m pytest

# Reduced-motion smoke (regenerate the PNGs above).
python scripts/ui_screenshots.py UI-9-tests

# Lighthouse run (requires Node + Chromium).
python scripts/ui_lighthouse.py
```

## What is NOT here

- No new server endpoint. The chunk does not touch
  `src/karasu/ui/server.py`.
- No new schema field. Bus event shape unchanged.
- No `.webm`. The reduced-motion captures are still snapshots,
  not recordings — there is no motion left under the media
  query that needs a recording to demonstrate.
- No SW unit test. Service workers run in a browser context;
  asserting on `navigator.serviceWorker.controller` from
  Playwright is a pin #4 violation (browser-state magic). The
  manual verification path in UI-8-pwa/README.md covers it.
- No Lighthouse run committed for this PR. The runner is
  available; the actual report depends on the operator's
  local Chrome version + Node setup. Future chunks (or a CI
  job once HTTPS is available) commit reports under
  `docs/ui/lighthouse/<date>.json`.
