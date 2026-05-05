# Next Session Entry Point

## Goal

**UI-8 — PWA shell.** `manifest.json`, vanilla service worker,
offline page (with the crow in an "out of signal" state — the
intended easter egg per UI-0 §6).

This is the chunk that turns Karasu's read-only watchtower into
an installable surface — the operator can pin it to a desktop /
home screen, and when the bus / server are unreachable the
service worker serves a hand-built offline page instead of the
browser's default error.

## Binding constraints carried forward (P0)

UI-7 audit added FIVE additional pins for UI-8+ (Codex,
2026-05-04, PR #79 APPROVED-with-observations). Verbatim:

```text
1. PWA shell must not add visual excitement. Manifest /
   offline / service-worker are infrastructure, not a new
   surface.
2. Offline page may use the crow, but in an out-of-signal
   pose; no flight, pulse, shake, or map animation.
3. Service worker must not cache stale bus / event JSON in a
   way that misrepresents live state.
4. If UI-8 introduces any new offline / connection visual
   state, it needs a small deterministic test or documented
   manual verification path.
5. Drawer remains an inspection layer; do not let offline /
   PWA affordances add badges, toasts, or dashboard chrome
   unless explicitly earned.
```

Pin #3 is the load-bearing one for the service-worker design:
/api/events / /api/health / /api/meta MUST be network-only.
Caching them risks the operator reading a stale projection
that contradicts the bus — exactly the kind of "looks live
but isn't" failure UI is designed to avoid. Pin #1 + #2 are
the editorial guardrails (no excitement, no chrome additions).

## UI-8 design review locked (Codex, 2026-05-04)

The audit prompt for UI-8 was reviewed before any code landed.
Verdict: APPROVED-with-observations for the design review /
pre-implementation gate. P0 = none. Three P1 contracts + three
P2 polish items must be respected when the implementation
opens. Verbatim:

### P1 — structural contracts

```text
1. /api/* network-only is FIRST-BRANCH in sw.js.
   The fetch handler must short-circuit /api/* requests before
   any cache-first logic can match them. Intended shape:

     self.addEventListener('fetch', (event) => {
       const url = new URL(event.request.url);

       // 1. /api/* — network-only, always.
       if (url.pathname.startsWith('/api/')) {
         event.respondWith(fetch(event.request));
         return;
       }

       // 2. Navigation — try network, fall back to offline.html.
       if (event.request.mode === 'navigate') {
         event.respondWith(
           fetch(event.request)
             .catch(() => caches.match('/offline.html'))
         );
         return;
       }

       // 3. Static assets — cache-first, only after the
       //    /api/ + navigate branches have already returned.
       event.respondWith(
         caches.match(event.request)
           .then((hit) => hit || fetch(event.request))
       );
     });

   The ordering is the contract. Any refactor that lets /api/*
   fall through to caches.match() is a P0 regression.

2. Empty localStorage on the offline page renders as a muted
   "bus —" (the em-dash placeholder used elsewhere in the
   shell) OR omits the bus line entirely. NEVER undefined,
   null, or a fake path. Lean: render the muted line so the
   shell rhythm is preserved without pretending knowledge.

3. CACHE_NAME is explicit + the bump rule is documented.
   Intended shape:

     const CACHE_NAME = 'karasu-ui-v8';

   And in docs/ui/screenshots/UI-8-pwa/README.md:

     "Bump CACHE_NAME whenever sw.js, offline.html,
      manifest.json, CSS, fonts, or crow assets change."

   This is the most common PWA debugging trap; the discipline
   prevents stale shells across deploys. The docstring at the
   top of sw.js must reference the bump rule.
```

### P2 — polish

```text
1. Offline pose stays "signal lost", not "injured". The
   posture change is rotate(4deg) + opacity 0.7 — no droop,
   no shake, no blink, no pulse, no grayscale filter. The
   ambient breathing loop from UI-5 stays subliminal.

2. No .webm required for UI-8. The offline page is static
   infrastructure; the only motion is the existing crow
   ambient breathing (already covered by the UI-5 .webm).
   PNGs are enough. (UI-6 / UI-7 .webm cadence does not
   carry; UI-8 is the first chunk after UI-5 to legitimately
   skip the recording.)

3. Manifest colours are literal hex MATCHING tokens.css
   exactly. If --bg-0 is #0a0a0b, the manifest's
   background_color is "#0a0a0b" — no rounding, no "close
   enough" drift. The audit will diff the values; an
   off-by-one channel is a P2 regression.
```

### Implementation pins to carry into the code

```text
1. /api/* is network-only, FIRST-BRANCH, never cache-first.
2. Offline page is a separate page, not a fake frozen live map.
3. No install toast, no badge, no connection indicator in the
   main shell.
4. Empty localStorage renders as "bus —" or omits the line.
   Never undefined / null.
5. CACHE_NAME bump rule is documented in sw.js docstring AND
   in the screenshots README.
6. No .webm required unless UI-8 introduces new motion beyond
   the static offline posture.
```

Codex closed the design review with: "Design is clear enough
to implement." Proceed when UI-7 lands and feat/ui-8-pwa
opens off main (or stacked on feat/ui-7-detail until UI-7
merges).

The five Codex pins added on the UI-6 audit + the seven pins
from UI-3 / UI-4 / UI-5 / UI-6 stay binding. UI-8 introduces
NO new motion surface (the offline page is static), so the
shell-stillness pins re-fire trivially. The new constraints
specific to UI-8 are around the service-worker contract:

```text
1. The bus is never mutated. UI-8 is read-only against the
   bus; the SW only caches static assets + the index.html
   shell. /api/events / /api/health / /api/meta MUST NOT be
   cached — they're live state.

2. Offline page lives at /offline.html (or static fallback).
   When the SW intercepts a navigation and the network is
   unreachable, it returns the offline shell. The shell shows
   the crow in an out-of-signal pose (per UI-0 §6, "intended
   easter egg") + a single editorial sentence + the bus path
   the operator was watching.

3. THIRD asset on the table: the out-of-signal crow. UI-5
   shipped crow.svg (perched, four states), UI-6 shipped
   crow-flight.svg (wings extended). UI-8 needs a custom CSS
   class on the EXISTING crow.svg — same base asset, posture
   change via transform / class. NOT a third SVG file unless
   the audit asks for one. Spec it in
   docs/ui/assets/karasu_sprites_spec.md once landed.

4. Service worker is vanilla. NO Workbox. NO build step. The
   SW is hand-written under static/sw.js, registered from
   index.html with a feature-detection guard. Pre-cache list
   is the static manifest of design tokens + fonts + sprites
   committed today; runtime cache is bounded.

5. The manifest declares the crow as the icon at multiple
   sizes (192 + 512 PNG) so the home-screen tile is editorial,
   not generic. Generation can use Pillow or a one-shot
   manual render committed to the repo.

6. Pin C carries: any new /api/health-derived state requires
   unit tests. UI-8 introduces no new server projection.
```

## What ships in UI-8

```text
src/karasu/ui/static/manifest.json                NEW.
  - name: "Karasu", short_name: "Karasu", display: "standalone".
  - theme_color: var(--bg-1) literal hex (manifest doesn't
    resolve CSS vars).
  - background_color: var(--bg-0) literal hex.
  - icons: 192×192 + 512×512 (PNGs derived from crow.svg).
  - start_url: "/", scope: "/".

src/karasu/ui/static/sw.js                        NEW.
  - install: precache the static manifest (CSS, fonts, sprite
    SVGs, index.html, offline.html).
  - activate: cleanup old caches by version key.
  - fetch: navigation requests → offline.html on network
    failure; static asset requests → cache-first; /api/*
    requests → network-only (NEVER cached).

src/karasu/ui/static/index.html  (extension)
  - <link rel="manifest" href="/assets/manifest.json">.
  - Inline SW registration with feature detection
    (if ('serviceWorker' in navigator)).
  - Theme-color meta tag matching the manifest.

src/karasu/ui/static/offline.html                 NEW.
  - Standalone page with the same shell tokens (links to
    /assets/css/{tokens,reset,base}.css + crow.css).
  - Hero crow in out-of-signal state — same crow.svg asset,
    new .crow.offline class for the posture.
  - Single editorial sentence: "The bus is unreachable.
    Karasu will resume when the connection returns."
  - Renders the LAST KNOWN bus_path from localStorage so the
    operator knows which agent surface they were watching.

src/karasu/ui/static/css/crow.css  (extension)
  - .crow.offline state: subtle slump (rotate 4deg + reduced
    opacity?) — TBD in chunk planning, must read as
    "instrument out of signal" not as "broken/dead".

src/karasu/ui/server.py  (extension)
  - GET /assets/manifest.json + GET /assets/sw.js: served by
    the existing static asset handler — sw.js needs the
    Service-Worker-Allowed: / header so it can scope to root.
  - GET /offline.html: served like /design-system (additive
    route, not advertised).
  - No projection change.

scripts/ui_screenshots.py  (extension)
  - UI-8 capture plan: index-with-manifest, offline-page,
    offline-narrow-viewport.
  - --record-video walks the registration logs only if
    Playwright exposes them; otherwise UI-8 ships PNGs only
    (the offline page is static — no motion to record beyond
    the crow's ambient breathing already covered by UI-5
    .webm).

docs/ui/screenshots/UI-8-pwa/   NEW.
  - PNGs + README per UI-2..UI-7 pattern.

docs/ui/assets/karasu_sprites_spec.md  (extension)
  - Document the .crow.offline state as a fifth crow class on
    the existing asset (idle / processing / waiting / error +
    flight asset + offline state on perched asset).
```

## Surface contract — must respect

```text
- UI = read-only sink. UI-8's SW NEVER caches /api/* — those
  responses must hit the live server.
- Frozen contracts: AgentResponse, F3, F7, F8, surface=sink,
  single-worker invariant, scar=stored-correction-only,
  I-001..I-006, TriggerSource Protocol, bus event schema,
  the /api/health additive fields shipped in UI-3..UI-6.
- The empty-state hero from UI-3 stays the first impression.
- The Live Map from UI-6 keeps flying inside the cached
  shell — the SW serves index.html offline but the JS layer
  shows the empty state when /api/events fails to fetch.
- No build step. Vanilla SW + plain manifest.
- No new runtime dependency (Pillow is dev-only for icon
  generation; the icon PNGs commit as static assets).
```

## Open questions to resolve while planning

```text
1. Offline crow pose — slump, sleep, or just dim?
   Lean: subtle slump (rotate 4deg, like the .waiting tilt
   but symmetric and held) + opacity 0.7. Out-of-signal
   should read as "the crow waits for the wire", not as
   "broken". Audit visually.

2. Cache versioning. Cache name embeds the package version
   (read at SW install via importing the version from the
   page, OR hardcoded and bumped per release). Lean:
   hardcoded at SW write time, audit the discipline of
   bumping it per UI-N PR that touches the SW.

3. Manifest icon generation. Pillow render of crow.svg at
   192 / 512 with --bg-0 background, OR commit Inkscape /
   Figma-rendered PNGs. Lean: Pillow one-shot under
   scripts/ for reproducibility; commit the PNGs as the
   canonical asset.

4. Last-known bus_path on offline page — localStorage is
   the simplest persistence. Stored on every successful
   /api/meta tick; read on offline page boot. Lean: yes,
   keeps the offline page useful instead of a generic
   "no signal" sentence.

5. SW registration scope. The default scope is the SW's
   own URL prefix; we want root scope so /api/* is
   intercepted. Requires Service-Worker-Allowed: / header
   on the SW response. Server-side change: 1 line in the
   asset handler when path == /assets/sw.js.
```

## Audit cadence reminder

```text
1. Real PNG screenshots under docs/ui/screenshots/UI-8-pwa/
   for each new state (manifest installed prompt where
   visible, offline page default, offline narrow viewport).
2. Optional .webm if a motion-relevant state appears
   (probably not for UI-8 — the offline page is static).
3. "What to look at" note covering: the crow's offline pose
   (pin #3 — must read as instrument out-of-signal), the
   SW cache version bump discipline (pin #2), the /api/*
   network-only contract (pin #1).
4. The diff itself.
5. The audit prompt for Codex out-of-band via ChatGPT.
6. Editorial check: pins A + E from UI-6 audit — verify the
   offline page does NOT add chrome / dashboard hints; the
   crow stays the visual centre.
7. SW scope check — service-worker-allowed header set, root
   scope verified by manual fetch in DevTools.
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §6 (UI-8 roadmap entry).
2. docs/ui/screenshots/UI-7-detail/README.md — the precedent
   for the "what to look at" + Codex pins A-E structure.
3. src/karasu/ui/static/css/crow.css — the existing four
   state classes; .crow.offline mirrors the .waiting tilt
   pattern.
4. src/karasu/ui/static/index.html — manifest + SW registration
   slot in the head + a tiny boot-time call.
5. src/karasu/ui/server.py — _content_type_for already handles
   .json (manifest) and .js (sw); the asset handler needs the
   Service-Worker-Allowed header for sw.js.
```

## Chunk size estimate

```text
Code:       ~250 LOC (manifest.json + sw.js + offline.html +
            index.html extension + crow.css extension + server
            header tweak)
Assets:     2 PNGs (192 + 512) generated from crow.svg
Docs:       ~80 LOC (sprites_spec extension + screenshots README)
Tests:      none (no new server projection per pin C)
Total:      under the 400 LOC budget.
```

## Do NOT do yet

```text
- Do NOT cache /api/events / /api/health / /api/meta. Bus
  state must hit the live server; the SW is for the static
  shell only.
- Do NOT add Workbox, Vite-PWA, or any SW framework. Vanilla
  per UI-0 §4.
- Do NOT introduce a build step.
- Do NOT introduce write paths to the bus (UI-10+).
- Do NOT add motion to anything outside the existing crow
  states. Pin B from Codex UI-6 audit binding.
- Do NOT add a sw.js cache that grows unbounded — quota /
  expiry contract documented in the file.
- Do NOT tag @codex review.
```

## Anchor for the previous sessions

- **UI-7 (Detail panel) PR open** (`feat/ui-7-detail`, stacked
  on `feat/ui-6-livemap`). Lateral drawer slides in from the
  right when the operator clicks a timeline row OR a Live Map
  node; vanilla 5-token JSON highlighter; close via X /
  click-outside / Esc. Map-node click resolves to the latest
  event whose `_flight_route` pair touches the node (source
  OR target); empty result shows the editorial sentence
  branch. Server side empty by design — pin C cumplido by
  absence. Pointer-events fix on `.live-map-svg` (none) +
  `.map-node` (bounding-box). 6 PNGs + 1 .webm (336 KB,
  1024×640 full-shell).
- **UI-6 (Live Map + crow flight)** APPROVED-with-observations
  by Codex (PR #78). P2 applied as follow-up `a2b9fef`. Five
  pins (A-E) for UI-7+ propagated; UI-7 honoured all five.
- UI-5 merged 2026-05-04 via PR #74 (`904111a`).
- UI-4 merged 2026-05-03 via PR #72.
- UI-3 merged 2026-05-03 via PR #70.
- 421/422 pytest on Windows local (399 + 22 flight_route).
  The same single preexisting failure
  (`test_valid_asset_under_static_dir_is_served`, Windows
  CRLF) remains; CI Linux green.
- Karasu HEAD post-merge: TBD (UI-6 + UI-7 PRs open, awaiting
  audit + merge).
