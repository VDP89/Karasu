# UI-8 — PWA shell + offline page screenshots

Karasu becomes installable. `manifest.json` declares the app +
icons, `sw.js` precaches the static shell + serves
`offline.html` when navigation requests fail to reach the
network. The visual surface gains nothing new on the live page;
the offline page is the easter egg per UI-0 §6 — the crow
waits in an out-of-signal pose with the operator's last-known
bus path muted below.

**No `.webm`** for this chunk. Codex P2 binding from the UI-8
design review: the offline page is static infrastructure; the
only motion is the existing crow ambient breathing already
covered by UI-5.webm. UI-8 is the first chunk after UI-5 to
legitimately skip the recording.

## Files in this directory

```text
00-index-with-manifest.png            Live shell unchanged from UI-7
                                      with the manifest link, theme-
                                      color meta, and SW registration
                                      added. Verify the additions do
                                      NOT regress the rendered surface.
01-offline-page-default.png           /offline.html with a populated
                                      last-known bus path. Crow in the
                                      .crow.offline pose (rotate 4deg +
                                      opacity 0.7), single editorial
                                      sentence, bus path muted in mono.
02-offline-page-empty-storage.png     /offline.html with empty
                                      localStorage. The bus line
                                      collapses to "bus —" — the
                                      em-dash placeholder Codex P1
                                      pinned. NEVER undefined / null /
                                      a fake path.
03-offline-narrow-viewport.png        720×1280 viewport. The offline
                                      shell stays readable on tablet /
                                      phone form factors with the same
                                      populated bus path as 01.
```

## Editorial pins to verify

The five Codex pins from the UI-7 audit + the three P1 + three
P2 from the UI-8 design review all hold.

### Carryover from UI-7 audit (5 pins)

```text
1. PWA shell must not add visual excitement.
   Verify in 00: index.html visually identical to UI-7's
   drawer-closed. The manifest link, theme-color meta, and
   SW registration are <head> + <script> additions, not new
   surface chrome. Inspect the diff for any new badge / toast /
   connection indicator — there is none.

2. Offline page may use the crow, but in an out-of-signal pose
   only. No flight, pulse, shake, or map animation.
   Verify in 01 / 03: crow is rotated 4deg + opacity 0.7,
   nothing else moves. The .crow.offline class also overrides
   animation: none so the ambient breathing loop from UI-5
   stops on this page (a static frame is the contract).

3. Service worker must not cache stale bus / event JSON.
   Verify in src/karasu/ui/static/sw.js fetch handler:

     1. /api/* → fetch(request) ONLY. No cache match.
     2. navigate → fetch(request).catch(() =>
                                     caches.match('/offline.html')).
     3. static → caches.match(request).then(hit || fetch).

   Ordering is the contract. Any refactor that lets /api/*
   fall through to caches.match() is a P0 regression.

4. New offline / connection visual state needs deterministic
   test or documented manual verification path.
   Manual paths shipped here in this README — see "Manual
   verification" below.

5. Drawer (UI-7) remains an inspection layer; offline / PWA
   affordances do NOT add badges, toasts, or dashboard chrome.
   Verify in 00: no install toast, no SW-status badge, no
   connection indicator added to the header / footer / drawer.
   The browser may still show its own install prompt — that
   is browser chrome, not Karasu chrome.
```

### P1 — structural contracts (3)

```text
1. /api/* network-only is FIRST-BRANCH in sw.js.
   Confirmed by inspection: the /api/ branch returns BEFORE
   the navigation branch and BEFORE the static cache-first
   branch.

2. Empty localStorage → muted "bus —" placeholder.
   Confirmed in capture 02; the offline page boot script
   reads localStorage with a try/catch, falls back to '—'
   on null / undefined / private-mode error.

3. CACHE_NAME explicit + bump rule documented.
   const CACHE_NAME = 'karasu-ui-v8' in sw.js. Bump rule
   written into the sw.js docstring AND into this README
   (see "Bump rule" below).
```

### P2 — polish (3)

```text
1. Offline pose is signal-lost, NOT injured. rotate(4deg) +
   opacity 0.7. No droop, shake, blink, pulse, grayscale.
   Confirmed in 01 / 03.

2. No .webm required for UI-8.
   Honoured by absence — the offline page is static and the
   ambient breathing on the live shell is already covered
   by UI-5.webm.

3. Manifest colours match tokens.css exactly.
   manifest.json:
     "background_color": "#0a0a0b"  // == --bg-0
     "theme_color":      "#131316"  // == --bg-1
   Diff against src/karasu/ui/static/css/tokens.css to
   verify no off-by-one channel drift.
```

## Bump rule

```text
Bump CACHE_NAME in src/karasu/ui/static/sw.js whenever any
of the following changes:

  - sw.js itself
  - offline.html
  - manifest.json
  - any file under static/css/
  - any font under static/assets/fonts/
  - any crow asset (crow.svg, crow-flight.svg, icons/)

Bump pattern: 'karasu-ui-v8' → 'karasu-ui-v9' (chunk number).
The activate handler deletes any cache whose name does not
match CACHE_NAME, so a bumped value cleans up the old shell
on first navigation under the new SW.

This rule is documented inside sw.js itself (the docstring at
the top references this README) so a future PR that touches
the SW or any precached asset has the discipline pinned in
both places.
```

## Manual verification

Two paths to verify the SW + offline contract without going
through Codex audit infrastructure:

```text
A. DevTools — Application > Service Workers.
   1. Open DevTools while on http://127.0.0.1:8787/.
   2. Confirm a service worker is registered with status
      "activated and is running" and source /assets/sw.js.
   3. Tick the "Offline" checkbox at the top of the panel.
   4. Refresh the page (Ctrl+R / Cmd+R).
   5. Expect /offline.html rendered (crow in offline pose +
      editorial sentence + last-known bus path).
   6. Untick "Offline", refresh again — live surface returns.

B. DevTools — Network throttling.
   1. Open DevTools > Network.
   2. Throttle to "Offline".
   3. The shell stays loaded (already cached); /api/events
      and /api/health requests fail.
   4. The existing tick() catch handler logs the failure
      and leaves the surface as-is (UI-3 "leave the surface
      as-is" contract). NO stale projection is shown — the
      cached state from before the disconnect remains; new
      ticks fail without overwriting.
   5. Throttle back to "No throttling" — live polling resumes.

Both paths exercise pin #3 (the SW must never serve stale
/api/* responses). Path A also exercises the offline.html
fallback (pin #2 + #4).
```

## Layout decisions

```text
>= 720 px viewport: offline page renders centred with 56ch
                    max-width copy and 96px hero crow.
<= 720 px viewport: empty-state typography drops one step
                    (--fs-20 → --fs-16) so the editorial
                    sentence keeps its rhythm at narrow
                    widths.
```

## What is NOT here

- No PNG of the install prompt. The install prompt is browser
  chrome (the browser decides when / whether to show it based
  on engagement heuristics), not Karasu's UI surface.
- No PNG of the SW lifecycle (install / activate / controlling).
  Those are DevTools-side observations; the audit verifies via
  the manual path above.
- No automated SW test. The chromatic whitelist + the SW fetch
  handler ordering are documented contracts; pytest stays at
  41/42 green (the one preexisting Windows CRLF failure carries
  forward; CI Linux green). A future chunk could add a tiny
  Playwright assertion for `navigator.serviceWorker.controller`
  non-null after first reload — not blocking UI-8.
- No reduced-motion offline PNG. The .crow.offline class is
  static (animation: none); reduced motion does not change
  anything for this page.
