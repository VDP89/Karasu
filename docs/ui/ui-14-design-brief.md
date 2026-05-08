# Karasu UI — UI-14 Design Brief (PWA installable surface)

> Status: **SIGN-OFF COMPLETE 2026-05-08 — Codex audit
> pending.**
>
> Estimated scope: ~800–1500 LOC including tests + docs (per
> Phase 4 macro brief §3-D estimate).
>
> Operator: Victor Del Puerto.
> Implementer: Claude Code.
> Auditor: Codex (via ChatGPT, operator-mediated).
>
> This brief is the second chunk-level brief of Phase 4. UI-13
> closed the auth foundation (PR #109, `6e283a8`); UI-14 earns
> the "app-like" frontier on top of that surface. The macro
> brief (PR #107 §3-D) binds the chunk sequence as
> **UI-13 → UI-14 PWA installable → UI-15+ native (CONDITIONAL)**.
> The recent corrigendum PR #112 (`825183a`) restored that
> binding after a sync-drift overlook had named UI-14 as
> "multi-operator authorization"; multi-operator stays in the
> Phase 4.y deferred bucket.
>
> The brief follows the shape that UI-12..UI-13 sealed: §0
> existence + §0.5 inherited pins + §1 positioning + §2 visuals
> + §3 confirmed decisions (each sub-decision marked
> **[SEALED]** or **[PROPOSAL — NEEDS OPERATOR SIGN-OFF]**) +
> §3.5 operator pin + §4 tech stack delta + §5 design system
> delta + §6 roadmap + §7 audit cadence + §8 frozen contracts
> + §9 out of scope + §10 open questions + §11 anticipated
> §11.6 pins + §12 status.

## 0 · Why this brief exists

UI-13 closed the deployed-auth foundation. Karasu now has a
secure, single-operator surface reachable from the public
internet via a reverse proxy (caddy/nginx termination) with
scrypt credentials, signed-cookie sessions, double-submit
CSRF, and a fail-closed startup contract. The operator can
already log in from a phone browser and drive the system.

What is still missing is the **app posture**. Karasu is a
website behind credentials; it is not an app. On iOS Safari
the surface lives inside the regular browser chrome with no
install seam, and Web Push does not fire at all unless the
PWA is installed (Apple platform constraint, sealed by
Webkit since iOS 16.4). On Android Chrome the install
prompt is browser-driven and currently un-anchored — the
operator has no in-surface affordance, and the browser's
own banner is exactly the kind of nag UI-8 audit pin #5
ruled out. On the desktop the SW update strategy
(`skipWaiting + clients.claim` from UI-8) reloads
long-running tabs without warning, which is acceptable for
localhost iteration but disruptive on a deployed surface
the operator may keep open across sessions.

UI-14 closes those gaps without reopening the load-bearing
contracts behind it. The chunk earns:

1. **Web app manifest** (`name`, `short_name`, `display`,
   `scope`, `start_url`, `theme_color`, `background_color`,
   `orientation`, `icons` array including maskable).
2. **Install affordance** — a discreet, deliberate footer
   slot that lights up only when the browser fires
   `beforeinstallprompt`, with persistent dismiss state. No
   banners. No first-visit hint.
3. **Icons** — the canonical crow adapted to the icon shape
   contract (`any` + `maskable` variants at 192 + 512 px
   minimum). Provenance tracked under
   `THIRD_PARTY_NOTICES.md` if the maskable variant adapts
   from a CC-licensed source per
   `feedback_hunt_cc_assets_before_drawing.md`.
4. **Mobile layout audit** — pass over the existing
   UI-4/UI-7 breakpoints at narrow viewports
   (320/360/375/414 logical px), with one optional new
   `<360 px` breakpoint reserved if and only if screenshots
   demand it. The audit is corrective, not exploratory.
5. **iOS / Android push compatibility audit** — the UI-12c
   pipeline shipped against desktop Chrome headless. UI-14
   walks the install-then-subscribe flow on iOS Safari +
   Android Chrome with the deployed surface and documents
   the platform constraints in `docs/deploy-runbook.md` (or
   a sibling `docs/pwa-install.md`).
6. **Service worker update strategy** — replace
   `skipWaiting + clients.claim` with **update-on-navigation
   + user-visible refresh affordance** for the deployed
   posture. This is a deliberate revisit of the UI-8
   shape-lock (the only such revisit in UI-14) and is called
   out explicitly so Codex and the operator can audit the
   trade-off.

What UI-14 does **not** earn:

- Any change to the auth surface (UI-13 sealed).
- Any change to push delivery, VAPID, or server-side emit
  (UI-12c sealed).
- Any change to the bus shape, `/api/*` contracts, or
  controller / pipeline / classifier (Phase 1–3 sealed).
- Native packaging (UI-15+ conditional, deferred unless
  UI-14 dogfood surfaces a concrete platform need).
- Multi-operator authorization, multi-host writer
  concurrency, A2A peer push fan-out, push enhancements
  beyond the closed enum, per-category debounce env
  override, or direct-TLS in karasu (all Phase 4.y
  deferred).

In one sentence: **UI-14 makes the already-secure surface
installable and usable as a real app, and stops there.**

## 0.5 · Pins inherited (verbatim, binding)

UI-14 inherits the full 165-pin stack from prior briefs.
The chunk respects every pin without exception. The
following categories are restated to anchor the audit, not
to weaken the inheritance:

```text
- UI-0  §4    no build step / no bundler / vanilla CSS + ES modules.
- UI-2  §6.1  design system tokens are the single source of truth
              for color / spacing / type / motion / radius / shadow.
- UI-3  §0.5  the application shell is one editorial canvas; no
              competing chrome.
- UI-4  §...  timeline as editorial beats; no decoration.
- UI-5  §...  motion lives ONLY on .crow; the surface stays calm.
- UI-7  §...  drawer is read-only projection of the canonical event.
- UI-8  audit pin #5  no install banners / update toasts / connection
              badges.
              (UI-14 §3-B install affordance does NOT violate this —
               affordance is footer-anchored, no banner posture.)
- UI-8  §SW   sw.js fetch handler ordering is shape-locked; the
              update strategy IS reopened by UI-14 §3-F (called out
              explicitly), but ordering / cache routing / pre-auth
              vs post-auth split (UI-13 §3-H) is not.
- UI-9.1 procedural lock on Lighthouse thresholds.
- UI-10 §0.5 (6 pins)  scar revoke contract.
- UI-11 §11.6 (12 pins) trust adjust contract.
- UI-12 §11.6 (16 pins) push notifications contract; pin §11.6.2
              (NEVER request push permission on first visit) carries
              forward unchanged for UI-14 — install posture is
              decoupled from notification posture.
- UI-12b §11.6 (16 pins) push opt-in contract.
- UI-12c §11.6 (20 pins) push emit + cryptography scope contract;
              the runtime cryptography import scope binding remains
              CONFINED to push_emit per UI-12 §11.6.13. UI-14 does
              NOT add cryptography deps.
- UI-13  §11.6 (20 pins) auth surface contract; FAIL-CLOSED startup
              + LOOPBACK-BIND + URL CONTRACT (/auth/* + /assets/*
              + the §3-D path perimeter) all binding.
- Phase 4 macro §11.6 (19 pins)  threat model + secret inventory +
              roadmap binding sequence + done definition + loop
              budget.
- Phase 4 macro §3-D (binding sequence, this brief's authority).
- Phase 4 macro §3-B (single-operator scope; multi-operator deferred).
```

The full per-pin enumeration lives in the prior briefs.
This brief does not duplicate them; the audit prompt
(§7-A) instructs Codex to check UI-14 deltas against the
inherited stack with no carve-outs.

## 1 · Positioning

UI-14 is a **polish frontier**, not a load-bearing
frontier. The load-bearing frontier was UI-13 (the network
trust boundary moved from "localhost is inherently
trusted" to "the network is not"). UI-14 sits on top: the
surface is already secure, already mobile-reachable,
already push-capable in principle. UI-14 makes the
ergonomics match the security.

Three product framings UI-14 honors:

1. **Editorial calm.** The surface remains UI-3's editorial
   canvas. The install affordance does not animate, does not
   pulse, does not interrupt the operator's reading
   posture. It is a single line in the footer that lights
   up to `--accent` when actionable and stays at `--fg-2`
   otherwise. The crow's animation budget (UI-5) does not
   extend to install state.
2. **Install is opt-in.** The browser's own install banner
   is suppressed where browser APIs allow (e.g., Chromium's
   `beforeinstallprompt.preventDefault()` swallow). The
   operator decides; Karasu offers, never insists. UI-14
   ships exactly one install seam, and the operator can
   ignore it for the lifetime of the session.
3. **iOS is a documented limitation, not a hidden one.**
   The brief is explicit that iOS Web Push requires PWA
   installation; the deploy-runbook documents the install
   walkthrough for iOS Safari (Share → Add to Home Screen)
   and the post-install push subscription flow. UI-14 does
   not pretend Safari-tab push works.

UI-14 closes Phase 4's "real platform, web-first" frame
(macro brief §3-E item 4). Native packaging (UI-15+) only
opens if dogfood after UI-14 surfaces a concrete platform
need that the PWA cannot meet — iOS background push
reliability beyond what installed-PWA delivers, Android
background sync, App Store distribution. Until then UI-14
is the close.

## 2 · Visual references (anchors held)

```text
UI-3   application shell        (post-auth canvas)
UI-4   editorial timeline       (long-form reading posture)
UI-5   canonical crow + motion  (the only animated element)
UI-7   detail drawer            (event projection)
UI-12a footer push state slot   (passive read-only)
UI-12b modal opt-in surface     (deliberate confirm flow)
UI-13  login screen primitive   (pre-auth visual)
```

UI-14 introduces **one** new visual primitive: the install
affordance in the footer (§3-B). It is anchored to the
`--meta` slot family that UI-12a established for the push
state line, NOT a new chrome element. The header, main
canvas, drawer, modal, login screen, and timeline are all
unchanged.

The maskable icon variant may force one design-side
decision (the safe area inside the 80% radial mask cuts
off pixels at the corners; the canonical crow as currently
sized risks losing the head detail). §3-C documents the
fallback path.

## 3 · Confirmed decisions (operator sign-off pending)

### A) Web app manifest fields

**[SEALED]** — `name`, `short_name`, `display`, `scope`,
`start_url`.

```text
File: src/karasu/ui/static/manifest.webmanifest
       (served at GET /manifest.webmanifest, anonymous-OK
        per UI-13 §3-D path perimeter — manifest is one of
        the small inert pre-auth assets the browser needs
        to discover the install posture).

Sealed fields:
{
  "name":        "Karasu",
  "short_name":  "Karasu",
  "display":     "standalone",
  "scope":       "/",
  "start_url":   "/"
}
```

Reasoning:

- `name` and `short_name` both `"Karasu"`. No submarca, no
  marketing string. The product name is the editorial
  identity.
- `display: "standalone"`. Per operator binding: *"si lo
  querés como app real, que se sienta app"*. No
  `minimal-ui` (which keeps a thin browser chrome strip
  with reload + share buttons — defeats the install).
- `scope: "/"`. The PWA owns the full origin. There is no
  carve-out for `/api/*` or `/auth/*` because the browser
  treats scope as the navigation boundary; sub-paths are
  still served by the same origin and the auth middleware
  decides who sees what.
- `start_url: "/"`. UI-13's auth middleware decides: an
  unauthenticated visit lands on the login surface; an
  authenticated visit lands on the application shell. No
  manifest-side branching. (`start_url` does NOT carry
  query strings — adding `?source=pwa` is sometimes
  recommended for analytics, but Karasu has no analytics
  layer and the macro brief §3-C item 1 binds operator
  state behind auth, so we do not introduce a tracking
  vector.)

[SEALED 2026-05-08]

**[PROPOSAL — NEEDS OPERATOR SIGN-OFF]** — `theme_color`,
`background_color`, `orientation`, `icons` array, optional
fields.

```text
PROPOSAL:
{
  "theme_color":      "#0a0a0b",
  "background_color": "#0a0a0b",
  "orientation":      "any",
  "icons": [
    { "src": "/assets/icons/karasu-192.png",
      "sizes": "192x192", "type": "image/png",
      "purpose": "any" },
    { "src": "/assets/icons/karasu-512.png",
      "sizes": "512x512", "type": "image/png",
      "purpose": "any" },
    { "src": "/assets/icons/karasu-maskable-192.png",
      "sizes": "192x192", "type": "image/png",
      "purpose": "maskable" },
    { "src": "/assets/icons/karasu-maskable-512.png",
      "sizes": "512x512", "type": "image/png",
      "purpose": "maskable" }
  ],
  "categories":       ["productivity", "utilities"],
  "lang":             "en",
  "dir":              "ltr"
}
```

Reasoning:

- `theme_color` and `background_color` both `#0a0a0b` —
  inferred from the existing `--bg-0` token. The brief
  treats this as PROPOSAL until UI-14 chunk code verifies
  the value against `static/css/tokens.css` and against
  the screenshots produced by `scripts/ui_screenshots.py`
  (the PNG should be visually indistinguishable from the
  app shell's empty state).
- `orientation: "any"`. The shell is editorial reading;
  both portrait and landscape work. Locking to `portrait`
  would be a UX regression on tablet.
- `icons` array: PROPOSAL-pending the maskable variant
  audit (§3-C). The canonical crow at 24/96 px (UI-3 / UI-5
  baseline) does not directly translate to 192/512 PNG
  rasterization without padding rules. §3-C documents the
  pipeline.
- `categories`, `lang`, `dir` are nice-to-have for app
  store / install prompt copy. PROPOSAL.

The chunk-level brief (this doc) reserves the right to add
or remove optional manifest fields based on
browser-compat checks (`https://developer.mozilla.org/...
/Manifest`). The optional fields and icon array shape are
SEALED at the values listed above; the chunk verifies the
`theme_color` / `background_color` hex against
`static/css/tokens.css` at implementation time and amends
in a follow-up commit if the token resolves to a different
value.

[SEALED 2026-05-08 — operator sign-off complete]

### B) Install prompt posture

**[SEALED 2026-05-08]** — discreet footer affordance, no
banners, NO iOS modal, persistent dismiss.

```text
SHAPE:
The footer (UI-3 footer slot family — version, last event
time, crow state, push state — UI-12a established the
fourth slot) gains a fifth slot:

  Install: <state>

Where <state> ∈ { "available" | "ready" | "installed" |
"unsupported" }.

Behavior:

  unsupported  : browser does not fire beforeinstallprompt
                 AND is not iOS Safari (no install path).
                 Render in --fg-2 (passive); no click handler.

  available    : browser fired beforeinstallprompt; UI-14
                 captured + saved the event. Render in
                 --accent. Click triggers prompt.userChoice
                 flow. Keyboard-accessible: Tab to focus +
                 Enter activates.

  ready        : iOS Safari path — no beforeinstallprompt
                 API, but the browser supports A2HS. Render
                 in --accent text "Install: ready" with a
                 single-line inline hint "(Share → Add to
                 Home Screen)" rendered in --fg-2 alongside.
                 NO CLICK HANDLER. The iOS install gesture
                 is browser-native; UI-14 surfaces the
                 instruction inline, in the footer, and
                 stops there. Full educational walk-through
                 lives in docs/pwa-install.md (§3-E
                 deliverable).

  installed    : navigator.standalone === true OR
                 matchMedia('(display-mode: standalone)').
                 Render in --fg-2 ("Install: installed").
                 No click handler.

PIN: NO BANNERS. NO MODAL ANYWHERE — desktop, Chromium,
Android, OR iOS. NO TOAST. NO FIRST-VISIT HINT.
NO CHROME-INSIDE-THE-APP for iOS instruction. The
affordance is the footer line in all four states; iOS
"ready" state ships its hint inline in the same footer
slot, NOT as a modal opened on click. iOS users learn the
install gesture from the inline hint or from
docs/pwa-install.md, never from a JS-driven modal that
UI-14 raises.

DISMISS:
After a successful prompt that the user declined ("Not
now"), the affordance returns to "available" but the
operator can dismiss the slot via a small × at the right
edge of the line. Dismiss persists in localStorage as
`karasu.install.dismissed_at` (ISO-8601). Re-shows after
30 days OR if a new SW activates (signaling the operator
the surface evolved).

PIN §11.6 candidate: localStorage IS used for the dismiss
state, and ONLY the dismiss state. No session material,
no operator state, no event projection ever materialises
in localStorage (UI-12b §11.6.16 carry-forward; UI-14
re-binds for install).
```

Reasoning:

- UI-8 audit pin #5 ("no install banners / update toasts /
  connection badges") is the design constraint. UI-14
  honors it strictly: the only NEW visual is a footer line.
- Operator binding 2026-05-08: *"footer slot only. Nada de
  modal iOS por ahora. Si hace falta educación para iOS,
  que viva en docs/pwa-install.md, no en chrome dentro de
  la app."* The earlier proposal split (footer slot +
  iOS one-shot modal on click) is REJECTED at sign-off;
  iOS instruction lives ONLY as inline hint in the
  "ready" state and in `docs/pwa-install.md`.
- The 30-day re-show window stands. Permanent dismiss +
  an evolving surface is a worse outcome than gentle
  re-surfacing.

[SEALED 2026-05-08 — operator sign-off complete; footer slot only, NO iOS modal]

### C) Icons + maskable handling

**[SEALED 2026-05-08]** — canonical crow baseline; pre-
rendered PNGs checked into the repo; NO new dev dependency.

```text
SOURCE:
src/karasu/ui/static/assets/crow/crow.svg
  (canonical UI-5 asset, viewBox 72×72, currentColor,
   OpenMoji-adapted CC-BY-SA 4.0 with operator legs + eye).

DELIVERY (operator-pinned 2026-05-08):
Pre-rendered PNGs are checked into the repo as binary
files. NO build pipeline is shipped. NO new runtime
dependency. NO new dev dependency.

  Operator binding: "pre-renderizadas checkeadas en repo.
  Evitemos meter dev dep solo para iconos en este chunk.
  Script opcional si ya usa libs existentes, pero no
  dependencia nueva."

OPTIONAL HELPER SCRIPT (within existing deps only):
A helper `scripts/ui_icons.py` MAY land if it can be
written using ONLY libraries already pinned in the dev
deps (Pillow already pinned for `scripts/ui_screenshots.py`
PNG diffing). cairosvg is NOT a current dev dep and SHALL
NOT be added by UI-14.

  Path A (if Pillow alone suffices via PIL.ImageDraw +
  upstream rasterisation of the SVG done outside the
  script): land the helper as a regen utility. Dev
  workflow: re-run the script when the canonical crow
  changes, commit the new PNGs.

  Path B (if Pillow alone cannot rasterise SVG): no
  helper script. The operator regenerates PNGs by hand
  (any tool of choice — Inkscape CLI, Figma export, etc.)
  and commits them. The brief documents the maskable
  inset (12.5%) and the size targets so the regen is
  reproducible.

The chunk implementation tries Path A first; if Pillow's
SVG support is insufficient (Pillow does NOT ship a
native SVG rasteriser), falls to Path B without
introducing any new dependency.

OUTPUT (committed binaries):
src/karasu/ui/static/assets/icons/
  karasu-192.png            (any, 192×192)
  karasu-512.png            (any, 512×512)
  karasu-maskable-192.png   (maskable; 12.5% safe-area
                             padding; 192×192)
  karasu-maskable-512.png   (maskable; 12.5% safe-area
                             padding; 512×512)

License continuity: every emitted PNG carries the same
CC-BY-SA 4.0 chain as the source SVG. The operator's
additions (legs + eye notch) merge into the file under
the more-restrictive license per share-alike. The
THIRD_PARTY_NOTICES.md addition lists OpenMoji + the
Karasu adaptation chain.

FALLBACK CHAIN (operator-pinned 2026-05-08):
If the canonical crow at 12.5% safe-area inset crops the
beak / legs visibly (initial dogfood test), the chunk
applies the fallback path in this order:

  1. Re-tighten the canonical crow's SVG body (operator-
     side adjustment to crow.svg or a sibling crow
     variant scoped to icon use). PREFERRED.
  2. Glyph-only maskable (simplified bird silhouette OR
     Karasu wordmark tuned for the radial mask).
     LAST RESORT.

ADAPTING A WIDER OPENMOJI SILHOUETTE IS EXPLICITLY
REJECTED at sign-off — the canonical crow is the
established identity (UI-5 + UI-8 + UI-12a + UI-13).
Switching to a different silhouette ONLY for icons would
introduce a brand split between the surface crow and the
launcher icon.

The audit artefact is the rendered PNG at 192 px shown
inside the maskable-test radial mask (Chrome devtools
provides the visualization; or the public maskable.app
harness for visual proof). Committed under
docs/ui/screenshots/UI-14-icons/ alongside the surface
PNGs.
```

Reasoning:

- `feedback_hunt_cc_assets_before_drawing.md` is the
  governing memory: do not draw new icons from scratch
  before exhausting CC-licensed candidates. The canonical
  crow itself is the result of the UI-5 8-iteration hunt
  and remains the source.
- Operator binding 2026-05-08 rejects cairosvg dev dep.
  Pre-rendered PNGs in the repo are the simpler path:
  binaries in `src/karasu/ui/static/assets/icons/` ship as
  package data, no build step, consistent with UI-0 §4
  "no build / no bundler" rule applied generously
  (script-based regen does not violate UI-0; the runtime
  delivery is static files with or without the helper).
- License chain unchanged: every committed PNG inherits
  CC-BY-SA 4.0. THIRD_PARTY_NOTICES.md was added by
  PR #94 (`ade1fc3`); UI-14 extends with the icon entries.
- Fallback chain locked to two options (re-tighten →
  glyph-only). OpenMoji-wider was a third option in the
  proposal; operator removed it to keep brand identity
  intact.

[SEALED 2026-05-08 — operator sign-off complete; pre-rendered PNGs, no new dev dep, fallback chain locked]

### D) Mobile layout audit

**[PROPOSAL — NEEDS OPERATOR SIGN-OFF]** — corrective audit
of existing breakpoints, one optional new breakpoint.

```text
TARGET VIEWPORTS (logical px):
  320  — iPhone SE 1st gen, narrow phones
  360  — Android baseline (Pixel, Samsung A-series)
  375  — iPhone Mini / SE 2nd / 8 / X-XS
  414  — iPhone Plus / Max
  768  — tablet portrait
  1024 — tablet landscape / small laptop

EXISTING BREAKPOINTS (UI-3 / UI-4 / UI-7):
  none formal. Layout uses fluid CSS grid with max-widths.
  UI-4 timeline collapses to single column ≤720 px.
  UI-7 drawer is full-width on mobile by virtue of being
  inside the canvas grid that already collapses.

AUDIT METHOD:
scripts/ui_screenshots.py extended (UI-14 plan):
  capture the application shell + login surface + push
  modal + drawer + design-system page at every target
  viewport. Side-by-side comparison.

  CSS that demonstrably breaks (overlap, truncation,
  unreadable type, missed touch targets <44 px) earns a
  fix in the EXISTING file (no new CSS file unless the
  fix is meaningful — e.g., a media query block dedicated
  to <360 px).

OPTIONAL <360 px BREAKPOINT:
The brief reserves room for ONE new media query at
@media (max-width: 359px) covering specific narrow-phone
fixes IF screenshots demand it. Triggers:
  - Footer slot text wrap that breaks the editorial
    rhythm.
  - Header crow + agent name + bus path crashing.
  - Modal / drawer touch targets falling below 44 px.

OUT OF SCOPE for the audit:
  - Adding hover affordances designed for mouse-only.
  - Reflowing the timeline beyond UI-4's existing collapse.
  - Reskinning the design system tokens.
  - Adding a dedicated mobile layout file or "mobile mode"
    toggle. Single layout, responsive throughout.
```

Reasoning:

- Operator binding: *"auditar y ajustar lo existente,
  permitiendo un breakpoint estrecho <360px si las
  capturas lo justifican. No sellaría 'no new
  breakpoints'; eso puede trabar una corrección real."*
- The audit is **corrective**, not exploratory. UI-14 does
  not redesign mobile; it confirms the existing CSS holds
  and patches what does not.
- 44 px is the WCAG 2.1 minimum touch target. UI-14 does
  not negotiate down from that.

[SEALED 2026-05-08 — operator sign-off complete; default is "only-if-screenshots-demand", with the audit free to land the breakpoint as part of the chunk if the captures justify it]

### E) iOS Safari + Android Chrome push compatibility

**[SEALED]** — iOS Web Push requires installed PWA. Document
the constraint; do not pretend Safari-tab push works.

```text
CONSTRAINT (Apple):
On iOS 16.4+ (released March 2023), Web Push works ONLY
when the page has been added to the Home Screen as a PWA
("Save to Home Screen" via the Share menu). In Safari
itself (regular browser tab), the JavaScript Push API is
gated and the user-facing permission prompt does not
appear. This is a platform decision by Apple, not a bug.

UI-14 BINDING:

1. The PWA's push opt-in modal (UI-12b) detects the iOS
   in-Safari case via `navigator.standalone === false` AND
   user-agent matches iOS Safari. In that branch, the
   modal's primary CTA changes from "Enable notifications"
   to "Install Karasu first" with a one-line link to the
   install affordance (§3-B), and the rest of the flow
   remains gated.

2. After install, when the operator opens the home-screen
   icon, `navigator.standalone === true`, and the modal
   reverts to its standard UI-12b flow.

3. Android Chrome supports Web Push in both browser-tab
   and installed-PWA postures. UI-14 does NOT artificially
   gate Android push behind install. The install
   affordance is independently offered.

4. Documentation is the binding deliverable for this
   sub-decision. UI-14 ships **docs/pwa-install.md (NEW)**
   — single page covering install + push flow per
   platform. Operator-pinned 2026-05-08:
   *"docs/pwa-install.md nuevo. El deploy-runbook es
   para server/deploy; PWA install merece doc propia."*
   docs/deploy-runbook.md is NOT extended for this
   purpose; it stays focused on server bring-up.

5. UI-14 does NOT add iOS-specific push code. The UI-12c
   server-side emit pipeline is platform-agnostic — VAPID
   + RFC 8291 aes128gcm POSTs to the endpoint URL the
   browser supplied. Apple's autopush endpoint just works
   as long as the subscription was created from an
   installed PWA. UI-14 verifies; UI-14 does not modify.

PLATFORM MATRIX (audit deliverable, captured in dogfood):

  Desktop Chrome  + push   ✔ already validated UI-12c
  Desktop Firefox + push   best-effort; not in §3-E gate
  Desktop Safari  + push   ✔ if running macOS 13+ Ventura
                           and PWA installed via Safari's
                           "Add to Dock"; UI-14 documents
                           but does not gate on it.
  Android Chrome  + push   in-tab OR installed; UI-14
                           validates both.
  Android Firefox + push   best-effort; not in §3-E gate
  iOS Safari      tab      install-only path; UI-14
                           explicitly documents.
  iOS Safari      A2HS     ✔ post-install push subscribe;
                           UI-14 validates end-to-end on
                           Victor's device.
```

Reasoning:

- Operator binding: *"documentar sealed que en iOS Web
  Push requiere PWA instalada. No fingir compatibilidad
  Safari-tab."* The sealed item IS the documentation, not
  a code change.
- The UI-12b modal already handles the unsupported-push
  branch (`browserPushSupport()` returns
  `state: "unsupported"`). UI-14 refines the iOS-Safari-
  in-tab case to surface the install path instead of a
  generic "your browser does not support notifications"
  message.
- Firefox is excluded from the §3-E binding gate by
  design. Karasu is operator-software for Victor's stack;
  Firefox is best-effort but not a release blocker.

[SEALED 2026-05-08 — iOS push requires installed PWA; UI-14
delivers documentation + UI-12b modal copy adjustment, no
new code path]

### F) Service worker update strategy

**[SEALED 2026-05-08 — EXPLICIT DEVIATION FROM UI-8
SHAPE-LOCK]** — replace `skipWaiting + clients.claim` with
**update-on-navigation + user-visible refresh affordance**
for the deployed PWA posture.

> **Deviation marker (binding).** This sub-decision is the
> ONLY explicit revisit of a prior shape-lock in UI-14.
> UI-8 sealed `self.skipWaiting()` on install +
> `self.clients.claim()` on activate as the SW lifecycle.
> UI-14 §3-F supersedes that lifecycle for UPDATE events
> (a NEW SW activating over an existing one) while
> preserving UI-8's behavior for the FIRST-LOAD case
> (no existing SW). The new shape-lock is
> **`UI-14 §3-F SW Update Lifecycle Lock`** and binds
> every future chunk that touches sw.js install / activate
> / message handlers. UI-15+ reopens this lock only via a
> new chunk-level brief earning a SEALED revisit.
>
> Operator pin 2026-05-08: *"Acepto update-on-navigation
> + refresh affordance. Rechazo mantener skipWaiting +
> clients.claim agresivo para una PWA instalada. Pero
> esto tiene que ir muy claramente marcado como desviación
> ganada de UI-8, con shape-lock nuevo."*

```text
CURRENT BEHAVIOUR (UI-8 / UI-12b sealed):
sw.js calls self.skipWaiting() on install and
self.clients.claim() on activate. Effect: a new SW takes
over open clients immediately on activation. Long-running
tabs reload on next fetch without warning.

PROBLEM:
On a deployed PWA the operator may keep the app open across
multiple sessions. An aggressive skipWaiting reload mid-
read disrupts UX. Also: skipWaiting on a PWA the operator
just installed is paradoxical — the SW that activated to
serve the install IS the one that should keep serving until
a deliberate update event.

PROPOSED NEW BEHAVIOUR:
1. Install:    NEW sw.js installs as "waiting" (no
               skipWaiting). The active SW continues
               serving open clients.
2. Activate:   NO clients.claim. The new SW only takes
               over future client visits.
3. Discovery:  The page polls registration.update() every
               60 minutes (or on navigation event,
               whichever fires first). When a NEW
               registration.waiting is detected, the page
               surfaces a refresh affordance in the footer
               slot family:
                 "Update available. [Refresh]"
               The Refresh button posts a message
               { type: 'SKIP_WAITING' } to the waiting SW;
               the waiting SW listens for that message and
               calls self.skipWaiting(). Page then calls
               window.location.reload() in the next
               navigation tick.
4. First-load: A fresh visit (no existing SW) installs
               and activates with skipWaiting + claim,
               same as today. The "no claim on update"
               rule applies ONLY to update events, not to
               the initial install.

WHY NOT MORE AGGRESSIVE:
A "force update on navigation" without a refresh
affordance still surprises the operator. The footer slot
gives them control: ignore until convenient, then accept.

UI-8 SHAPE-LOCK INTERACTION:
UI-8 sealed sw.js ordering for the FETCH handler. UI-14
does NOT touch the fetch handler. The change is in the
install + activate event handlers and adds a message
handler. The pre-auth/post-auth cache split (UI-13 §3-H)
is unchanged. Codex audit pin candidate: verify UI-14 does
NOT alter sw.js fetch path or cache routing.

TEST SURFACE:
tests/test_ui_sw_update.py (NEW):
  - Install does NOT call skipWaiting on UPDATE; DOES on
    fresh install (proxy: no controller present in
    registration object).
  - Activate does NOT call clients.claim on UPDATE.
  - Message handler { type: 'SKIP_WAITING' } triggers
    skipWaiting AND no other side effect.
  - Polling cadence: 60 min default; flag --update-poll-
    interval-seconds (defer to chunk if it's worth
    exposing) overridable for dogfood.
```

Reasoning:

- Operator binding: *"proposal hacia update on navigation
  / user-visible refresh affordance, no skipWaiting
  agresivo para PWA instalada. Pero esto necesita
  auditoría porque toca UI-8 shape-lock."*
- The change is **opt-in by activation**: the operator
  always sees the refresh affordance before the new SW
  takes over. UX truth carries the technical truth.
- The shape-lock concern is real and called out in §11.6
  (anticipated pin) so Codex round 1 audits the boundary
  explicitly.

[SEALED 2026-05-08 — operator sign-off complete; explicit deviation from UI-8 shape-lock; new shape-lock `UI-14 §3-F SW Update Lifecycle Lock` binding for all future chunks touching sw.js lifecycle handlers]

### G) Auth interaction (PWA shell + login)

**[SEALED]** — anonymous install permitted; pre-auth shell
is login-capable only; no bus/app-state pre-auth.

```text
INSTALL POSTURE:
The browser fires beforeinstallprompt on ANY visit that
meets the install criteria (manifest valid, SW installed,
HTTPS, user engagement signals). UI-14 does NOT gate the
install affordance behind authentication — the operator
can install Karasu before logging in.

POST-INSTALL OPEN:
The installed PWA opens at start_url ("/"). UI-13's auth
middleware decides:
  - No session cookie OR invalid cookie → render the
    login surface (login.html + login.css + login.js, all
    UI-13 sealed primitives).
  - Valid session cookie → render the application shell.

WHAT THE PWA SHELL SHIPS PRE-AUTH:
Per UI-13 §3-D path perimeter (binding):

  PRE-AUTH ANONYMOUS allowed:
    GET /                       (login page if not authed)
    GET /login                  (login page)
    GET /assets/css/login.css
    GET /assets/css/tokens.css  (parsed by login.css)
    GET /assets/css/reset.css
    GET /assets/css/base.css
    GET /assets/css/typography.css
    GET /assets/fonts/*         (woff2 self-hosted)
    GET /assets/icons/*         (PWA icons; UI-14 ADDS to
                                 the anonymous list)
    GET /favicon.ico
    GET /manifest.webmanifest   (UI-14 ADDS — required for
                                 install detection)
    GET /sw.js                  (UI-13 sealed: anonymous
                                 with strict scope)
    POST /auth/login            (rate-limited)
    GET  /auth/logout, POST /auth/logout

  EVERYTHING ELSE auth-gated:
    GET /api/* (events, health, meta, agents, push)
    POST /api/push/subscribe, POST /api/push/unsubscribe
    GET /design-system

UI-14 BINDING ADDITION:
The manifest path (/manifest.webmanifest) and the icon
paths (/assets/icons/karasu-*.png) join the anonymous
allow-list. The brief documents this explicitly because
UI-13's path perimeter is shape-locked; UI-14 is the
chunk earning the additions.

PIN: NO BUS / EVENT / SCAR / TRUST / PUSH STATE LEAKS
PRE-AUTH. The PWA shell pre-auth is the login surface +
its CSS/fonts/icons, period. There is no "skeleton shell
that loads then auths" pattern; the empty-state shell is
post-auth only.

PIN: SW PRE-AUTH/POST-AUTH CACHE SPLIT (UI-13 §3-H)
UNCHANGED. UI-14's update strategy (§3-F) modifies the
SW lifecycle but does NOT modify the cache routing or
key ranges. Pre-auth cache (login assets) and post-auth
cache (shell assets) remain disjoint per UI-13 sealed.
```

Reasoning:

- Operator binding: *"anonymous install permitido, pero
  solo instala el login-capable shell. Nada de
  bus/app-state pre-auth. Después el usuario inicia
  sesión dentro de la PWA."*
- UI-13's path perimeter is the source of truth. UI-14
  surgically adds two paths (manifest + icons) and zero
  data exposure.
- The session lives in the cookie. The PWA, like the
  browser tab, picks up the session cookie automatically
  on relaunch. No PWA-specific auth code path. The
  cookie's `SameSite=Strict` (UI-13 sealed) holds because
  the PWA shares the registered origin.

[SEALED 2026-05-08]

### H) Branding

**[SEALED]** — `Karasu` everywhere. Crow canonical. No
submarca, no marketing string.

```text
name        : "Karasu"
short_name  : "Karasu"
icon source : src/karasu/ui/static/assets/crow/crow.svg
              (UI-5 canonical, OpenMoji-adapted CC-BY-SA 4.0
               with operator additions; preserved)
display     : "standalone" (§3-A sealed)

App label   on iOS Home Screen + Android launcher: "Karasu".
Accessible name (the long-form label some screen readers
read on focus when display=standalone) is "Karasu" via
manifest.name.

NO:
  - "Karasu Operator" / "Karasu Console" / etc.
  - Tagline strings inside the manifest.
  - Multiple icon variants tied to "branding modes".
  - Light-mode icon variant in UI-14 — the surface is
    dark-only by design (UI-2 tokens). If browsers
    request a light-mode icon (Chrome's
    color_scheme_dark / color_scheme_light keys exist as
    extensions), defer to a future chunk.
```

Reasoning:

- Operator binding: *"`Karasu` como name y short_name.
  Crow canónico en iconos. No renombrar ni inventar
  submarca."*
- The crow has earned its identity through UI-5 + UI-8
  + UI-12a + UI-13 (the login screen hero crow uses the
  same canonical SVG). UI-14 continues that line.
- Light-mode icons are deferred. The surface is dark; the
  icon is dark-canvas-on-dark-fill. If a launcher renders
  it on a light background (Android home screen with
  light wallpaper), the maskable variant's safe-area fill
  (`#0a0a0b`) is the visual frame.

[SEALED 2026-05-08]

### I) Frozen contracts UI-14 MUST NOT reopen

**[SEALED]** — operator pin (§3.5 binding).

```text
UI-14 does NOT modify:

1. Auth surface (UI-13):
     - karasu-auth.json schema or scrypt parameters.
     - Session cookie format, signing, or TTL.
     - CSRF mechanism (signed double-submit).
     - Trusted-IP derivation.
     - Rate-limit windows or backoff.
     - Anonymous-path perimeter (except the two SEALED
       additions in §3-G: manifest + icons).
     - Login surface visual primitive (UI-13 §3-E).
     - Fail-closed startup contract or loopback-bind
       contract.

2. Push delivery (UI-12c):
     - VAPID keypair shape, bootstrap, or rotation.
     - aes128gcm encryption parameters.
     - Push store schema, file lock, or atomic write.
     - Server-side emit pipeline (classifier → rate-limit
       → dispatcher → urllib POST).
     - Cryptography import scope (CONFINED to push_emit).
     - Endpoint privacy discipline (endpoint_hash + type
       only).

3. Bus / pipeline / controller (Phases 1-3):
     - Event schema (file_change / agent_response /
       human_decision / git_event).
     - Classifier rules or dispatch_on semantics.
     - Adapter trust gradient (per-system; not per-user).
     - Controller chain cap, scar override, source
       lifecycle.
     - Telegram interface (still active alongside PWA).

4. API contracts:
     - GET /api/events, /api/health, /api/meta, /api/agents
     - GET /api/push, POST /api/push/{subscribe,unsubscribe}
     - POST /auth/login, GET+POST /auth/logout
     - GET /design-system
     All response shapes are shape-locked; UI-14 reads but
     does not modify.

5. Visual contracts:
     - UI-3 application shell layout.
     - UI-4 timeline rendering.
     - UI-5 canonical crow SVG + state animations.
     - UI-7 detail drawer.
     - UI-12a/b push surface.
     - UI-13 login screen.
     UI-14's only NEW visual is the install affordance
     footer slot (§3-B).

UI-14 MAY modify:
  - sw.js install + activate + message handlers
    (§3-F SEALED — UI-14 §3-F SW Update Lifecycle Lock,
    explicit deviation from UI-8).
  - static/index.html (footer slot for install).
  - static/css/footer.css (or wherever the meta slot
    family lives) — install affordance styling.
  - static/js/install.js (NEW — beforeinstallprompt
    capture, dismiss state, refresh affordance).
  - static/manifest.webmanifest (NEW).
  - static/assets/icons/* (NEW pre-rendered PNGs checked
    into the repo per §3-C SEALED — no build pipeline).
  - scripts/ui_icons.py (OPTIONAL helper; lands ONLY if
    Pillow alone suffices per §3-C SEALED Path A;
    otherwise dropped per Path B).
  - tests/test_ui_install.py (NEW).
  - tests/test_ui_icons.py (NEW).
  - tests/test_ui_sw_update.py (NEW).
  - tests/test_ui_manifest.py (NEW).
  - docs/pwa-install.md (NEW per §3-E SEALED;
    docs/deploy-runbook.md is NOT extended for PWA
    install content).
  - THIRD_PARTY_NOTICES.md addendum for the icon
    PNG adaptation chain.
```

[SEALED 2026-05-08]

## 3.5 · Operator pin (binding)

> **UI-14 makes the already-secure surface installable
> and usable as a real app, and stops there. UI-14 does
> NOT reopen auth, push delivery, or server-side emit.
> UI-14 is a polish frontier on top of the load-bearing
> UI-13 frontier.**

This pin overrides any temptation in §3 sub-decisions or
§4–§11 to widen scope. If a sub-decision implies a change
to auth, push delivery, or server-side emit, the
sub-decision is wrong; refactor the sub-decision, not the
sealed contract.

The §3-F SW update strategy is the single explicit revisit
of a prior shape-lock (UI-8) and is called out for Codex
P0 review precisely because revisits are exceptional. Any
other revisit attempt is a brief failure.

[BINDING — operator-pinned 2026-05-08]

## 4 · Tech stack delta (vs UI-0..UI-13 + Phase 4 macro)

```text
NEW runtime files:
  src/karasu/ui/static/manifest.webmanifest
  src/karasu/ui/static/assets/icons/karasu-{192,512}.png
  src/karasu/ui/static/assets/icons/karasu-maskable-{192,512}.png
                                  (PRE-RENDERED PNGs, checked
                                   into the repo per §3-C
                                   sealed; NO build pipeline
                                   ships)
  src/karasu/ui/static/js/install.js

OPTIONAL helper script (NOT runtime; only if usable
within existing dev deps):
  scripts/ui_icons.py            (lands ONLY if Pillow alone
                                  can rasterise; otherwise
                                  the operator regenerates
                                  PNGs by hand per §3-C
                                  sealed Path B)

MODIFIED runtime files:
  src/karasu/ui/static/sw.js          (§3-F update strategy
                                       + message handler)
  src/karasu/ui/static/index.html     (manifest link tag +
                                       footer install slot)
  src/karasu/ui/static/css/footer.css (or equivalent slot
                                       file — install
                                       affordance styling)
  src/karasu/ui/server.py             (route /manifest.web-
                                       manifest with correct
                                       Content-Type +
                                       anonymous-OK; route
                                       /assets/icons/* same;
                                       both join the
                                       UI-13 §3-D anonymous
                                       allow-list)

NEW tests:
  tests/test_ui_install.py     (install affordance shape +
                                dismiss state + iOS modal
                                copy)
  tests/test_ui_icons.py       (golden PNG hash + maskable
                                safe-area assertion)
  tests/test_ui_sw_update.py   (install/activate/message
                                handler discipline)
  tests/test_ui_manifest.py    (manifest shape validation +
                                anonymous routing test +
                                Content-Type pin)

NEW docs:
  docs/pwa-install.md          (per-platform install +
                                push walkthrough; OR an
                                expansion of
                                docs/deploy-runbook.md
                                — chunk picks)

NEW dev deps:
  NONE. Operator-pinned 2026-05-08: pre-rendered PNGs are
  checked into the repo; UI-14 SHALL NOT introduce a new
  dev dependency (cairosvg explicitly rejected). The
  optional `scripts/ui_icons.py` helper, if it lands at
  all, must use ONLY libraries already pinned (Pillow is
  already pinned for `scripts/ui_screenshots.py`); if
  Pillow does not suffice, the helper is dropped and
  the operator regenerates PNGs by hand per §3-C Path B.

NO new runtime dependencies.
NO new cryptography use.
NO new network calls beyond what UI-12c already does.
NO new system integration (no electron, no tauri, no
   wrapper toolkits — UI-15+ is conditional).
```

Reasoning:

- Operator-pinned 2026-05-08 rejects the cairosvg dev dep.
  Pre-rendered PNGs in the repo are the simpler path:
  binaries in `src/karasu/ui/static/assets/icons/` ship as
  package data, no build step, no rasterisation toolchain
  in the project surface. The optional helper script is
  bounded to existing deps.
- The UI-0 §4 ban on build steps applies to the **runtime
  delivery pipeline**. Pre-rendered PNGs are already
  static; the optional helper (if it lands) is operator-
  side regeneration, not a runtime artefact.

## 5 · Design system delta (vs UI-0..UI-13)

```text
TOKENS:
  No new color tokens unless §3-A theme_color verification
  reveals a gap.

  Optional new spacing/typography tokens for the install
  affordance footer slot are deferred to chunk
  implementation if needed; default is to reuse the meta
  slot family from UI-12a.

COMPONENTS:
  NEW: install-affordance (footer slot variant).
  NEW: refresh-affordance (footer slot variant — surfaces
       when sw.js update is waiting per §3-F).
  NEW: ios-install-modal (modal variant — informational
       only; opens on user click in iOS Safari path).

CSS FILES:
  No new dedicated CSS file unless an audit-driven mobile
  fix earns one (§3-D <360 px breakpoint).

JS FILES:
  install.js (NEW; vanilla ES module, no toolchain).

ANIMATION BUDGET:
  The install affordance does NOT animate. The crow keeps
  its sole ownership of motion (UI-5 binding).

PWA-SPECIFIC CSS (display-mode standalone):
  When `matchMedia('(display-mode: standalone)')` matches,
  UI-14 applies a body class `is-installed`. The class is
  used SOLELY to hide the install affordance (it has
  served its purpose). NO other layout changes when
  installed; the surface is the same in browser tab and
  installed PWA per the editorial calm pin.
```

## 6 · Roadmap (single chunk; possible split)

```text
DEFAULT: single chunk.

UI-14 ships as one PR sized at the macro brief estimate
(~800-1500 LOC including tests + docs). The shape:

  Commit 1: scripts/ui_icons.py + dev deps + golden PNGs
            + test_ui_icons.py.
  Commit 2: manifest.webmanifest + server.py routing +
            test_ui_manifest.py + UI-13 anonymous allow-
            list extension.
  Commit 3: install.js + footer slot + index.html +
            install.css (or extension of existing) +
            test_ui_install.py.
  Commit 4: sw.js update strategy + test_ui_sw_update.py.
  Commit 5: mobile layout audit fixes + ui_screenshots.py
            extensions + screenshots/.
  Commit 6: docs/pwa-install.md (or deploy-runbook.md
            extension) + THIRD_PARTY_NOTICES.md if needed.
  Commit 7+: Codex audit follow-ups in-branch.

POSSIBLE SPLIT: 14a + 14b.
Trigger: brief itself + audit identify > 1500 LOC OR an
audit pin requires a stacked chunk.
  UI-14a: manifest + icons + install affordance + mobile
          audit (visual + ergonomic earn).
  UI-14b: SW update strategy + iOS push compat docs +
          deploy-runbook addendum (lifecycle earn).
The split is NOT speculative — it earns its own
chunk-level brief (per UI-9 audit pin #1) only if the
single-chunk path overruns.

LOOP BUDGET: 5 rounds per Codex audit. Brief audit + chunk
code audit are independent budgets.
```

## 7 · Audit cadence

UI-14 inherits the audit cadence from UI-12c §7 + Phase 4
macro §7 + UI-13 §7 carry-forward. Specifically:

```text
A) BRIEF AUDIT:
   This document goes to Codex (operator-mediated via
   ChatGPT) immediately after operator sign-off on the
   §3 sub-decisions. The audit prompt template is the
   one feedback_audit_prompt_automatic.md sealed:

     - PR link
     - Branch + base + commit
     - Diff stat
     - What this brief ships (numbered)
     - Inherited pins honored
     - Audit artefacts (none for the brief — code + PNGs
       come with UI-14 chunk PR)
     - Specifically flag any:
         P0: contract violations vs UI-13/UI-12c shape-lock
         P0: missing §11.6 pins where the brief implies a
             constraint without naming it
         P1: ambiguity in §3 SEALED items
         P1: scope creep (anything that re-opens auth /
             push delivery / server-side emit)
         P2: editorial / language / formatting

B) CODE AUDIT:
   Earned per commit batch on the UI-14 chunk PR. Same
   5-round budget. Inherited audit prompt shape.

C) ROUND-1 EXPECTATION:
   2-4 P0/P1 findings are normal for a chunk-level brief
   that touches a prior shape-lock (§3-F SW). The brief
   anticipates Codex pinning the SW deviation as P0 round
   1 ("either revert to UI-8 skipWaiting+claim and accept
   the long-tab disruption, or document the new contract
   verbatim"). The brief chooses the second; the audit
   round 1 is expected to refine the contract language,
   not reject the deviation.

D) MERGE DISCIPLINE:
   Per feedback_karasu_merge_es_implementer.md, Claude
   Code (implementer) lands the merge after Codex APPROVED
   or APPROVED-with-observations. Brief PR is leaf-on-
   main; --delete-branch safe.
```

## 8 · Frozen contracts UI-14 MUST respect

(Mirrors §3-I, restated as a pre-audit check-list.)

```text
[ ] auth surface unchanged
    karasu-auth.json schema, scrypt parameters, session
    cookie shape, CSRF mechanism, trusted-IP, rate-limit,
    anonymous-path perimeter (except SEALED additions in
    §3-G: manifest + icons), login screen visual,
    fail-closed startup, loopback-bind contract.
[ ] push delivery unchanged
    VAPID keypair, aes128gcm, push store schema, file
    lock, atomic write, server-side emit pipeline,
    cryptography scope, endpoint privacy.
[ ] bus + pipeline + controller unchanged
    event schema, classifier rules, dispatch_on, adapter
    trust gradient (per-system, not per-user), controller
    chain cap, scar override, source lifecycle, Telegram
    interface.
[ ] API shapes unchanged
    /api/events, /api/health, /api/meta, /api/agents,
    /api/push, /api/push/{subscribe,unsubscribe},
    /auth/login, /auth/logout, /design-system.
[ ] visual contracts unchanged
    UI-3 shell, UI-4 timeline, UI-5 crow + motion, UI-7
    drawer, UI-12a/b push surface, UI-13 login screen.
[ ] UI-0 §4 no-toolchain rule respected
    runtime delivery is static files + ES modules. Build
    artefacts (icon PNGs) acceptable as long as the runtime
    pipeline does NOT bundle / transpile / build.
[ ] UI-5 motion budget respected
    only .crow animates. Install affordance is static.
[ ] UI-9.1 Lighthouse threshold respected
    no regressions on a/lcp/cls vs the post-UI-13 baseline.
    Install affordance + manifest + sw.js update strategy
    SHOULD improve installability (Lighthouse PWA category)
    without regressing perf.
```

## 9 · Out of scope for UI-14

```text
1. Native packaging (UI-15+ conditional). UI-14 does NOT
   evaluate electron / tauri / capacitor. The macro brief
   §3-D defers native to "earned IF dogfood after UI-13 +
   UI-14 proves the PWA cannot do something the operator
   needs".

2. Multi-operator authorization, audit log filtering by
   operator, role/permission tiers per-user. Phase 4.y
   deferred per macro brief §3-B.

3. Multi-host writer concurrency. Phase 4.y deferred.

4. A2A peer push fan-out. Phase 4.y deferred.

5. Push enhancements beyond the closed enum (per-event
   opt-in, scheduled / quiet-hours / DND, VAPID
   auto-rotation). Phase 4.y deferred.

6. Per-category push debounce env override. Phase 4.y
   deferred (originally scoped UI-12c §10.5).

7. Direct-TLS in karasu (--tls-cert / --tls-key).
   Phase 4.y deferred per UI-13 §3-A; reverse-proxy
   termination is the sealed production shape.

8. Light-mode icon variant. Deferred unless dogfood
   surfaces a need.

9. App store distribution (Microsoft Store, Play Store,
   App Store). Conditional on UI-15+; UI-14 does not
   prepare submission packages.

10. Analytics / install funnel telemetry. Karasu has no
    analytics layer; UI-14 does not introduce one. The
    macro brief §3-C item 1 binds operator state behind
    auth, and a tracking pixel/beacon is operator state
    that anonymous endpoints would expose.

11. Push category subscription UI from inside the
    installed PWA. Already shipped in UI-12b; UI-14 does
    not modify.

12. Notification action buttons (the "actions" array in
    showNotification). UI-12c sealed body=empty + the
    notification copy contract; UI-14 does not extend.

13. Background sync, periodic sync, content indexing,
    web share target, file handler, protocol handler.
    All PWA-API options that UI-14 explicitly does not
    earn. Each would re-open a prior contract or
    introduce platform-specific surface area.

14. Splash screen customization beyond what manifest
    fields give "for free" (Chromium auto-generates a
    splash from theme_color + background_color + 512 px
    icon). UI-14 does not add splashscreens/ assets.

15. Multi-language support (manifest "name" /
    "description" localization). Karasu is operator-
    English; localization is post-Phase-4.
```

## 10 · Open questions (operator sign-off complete)

ALL Q1–Q12 resolved 2026-05-08. The §3 sub-decisions are
fully sealed. Resolutions ferried into the relevant §3
subsections; this section preserves the question/answer
record for audit traceability.

```text
[Q1] §3-A theme_color / background_color
     RESOLVED: ok defaults — "#0a0a0b" inferred from
     --bg-0. Chunk implementation verifies the hex
     against tokens.css; amends in follow-up commit
     if the token resolves to a different value.

[Q2] §3-A icons array: 4 entries (192/512 × any/maskable)
     RESOLVED: ok defaults.

[Q3] §3-A optional fields: categories / lang / dir
     RESOLVED: ok defaults — include all three with the
     proposed values (productivity+utilities / en / ltr).

[Q4] §3-B install affordance shape
     RESOLVED: footer slot ONLY. NO iOS modal. iOS
     education lives in docs/pwa-install.md, not in
     chrome-inside-the-app. §3-B SEALED.

[Q5] §3-B dismiss persistence window
     RESOLVED: ok defaults — 30 days, plus reset on new
     SW activation.

[Q6] §3-C maskable fallback chain
     RESOLVED: re-tighten the canonical crow's SVG first;
     glyph-only maskable as last resort. Adapting a
     wider OpenMoji silhouette is REJECTED — preserves
     brand identity (crow stays crow). §3-C SEALED.

[Q7] §3-D <360 px breakpoint
     RESOLVED: ok defaults — only-if-screenshots-demand,
     audit free to land it.

[Q8] §3-F SW update strategy
     RESOLVED: accept update-on-navigation + user-visible
     refresh affordance. EXPLICIT DEVIATION FROM UI-8
     SHAPE-LOCK. New shape-lock
     `UI-14 §3-F SW Update Lifecycle Lock` binding for
     all future chunks touching sw.js lifecycle handlers.
     §3-F SEALED with deviation marker.

[Q9] §6 single chunk vs split
     RESOLVED: ok defaults — single chunk; split only
     if scope overruns.

[Q10] §4 cairosvg dev dep vs pre-rendered PNGs
      RESOLVED: pre-rendered PNGs checked into the repo.
      NO new dev dep. Optional `scripts/ui_icons.py`
      helper lands ONLY if Pillow alone suffices.
      §3-C + §4 SEALED.

[Q11] §3-E docs target
      RESOLVED: docs/pwa-install.md (NEW). The
      deploy-runbook stays focused on server bring-up;
      PWA install earns its own doc. §3-E SEALED.

[Q12] iOS Safari A2HS copy preview
      OBSOLETE — iOS modal removed by Q4 resolution.
      Inline hint copy "(Share → Add to Home Screen)"
      is the entire UI surface; chunk drafts the
      docs/pwa-install.md walkthrough + audit catches.
```

[ALL RESOLVED 2026-05-08 — operator sign-off complete; brief is fully sealed]

## 11 · §11.6 anticipated pins (Codex audit, pending)

The following pins are the brief's anticipated binding
constraints. Codex audit may add, drop, or reword. Each
pin compiles to a binding implementation contract on PR
merge.

```text
§11.6.1 — UI-14 makes the already-secure surface
          installable. Auth, push delivery, and
          server-side emit MUST NOT be modified. Any code
          path that loads from src/karasu/ui/_auth.py,
          src/karasu/push_emit/, or src/karasu/eventbus.py
          unchanged is the only shape that audits clean.

§11.6.2 — NEVER request push permission from install flow.
          Install posture is decoupled from notification
          posture (UI-12 §11.6.2 carry-forward; UI-14
          re-binds).

§11.6.3 — NO install banners. NO install toasts. NO
          first-visit hints. NO modal-on-load. The install
          affordance is the footer slot ONLY (with the
          iOS-only one-shot modal opening on USER CLICK
          per §3-B). UI-8 audit pin #5 binds.

§11.6.4 — manifest.webmanifest is anonymous-reachable.
          icons/ paths are anonymous-reachable. NO other
          anonymous-allow-list extension is permitted by
          UI-14. The UI-13 §3-D path perimeter is the
          authority; UI-14 §3-G surgically adds two paths.

§11.6.5 — NO operator state, NO bus events, NO scar log,
          NO trust state, NO push subscriptions, NO
          session material in manifest fields, in
          install.js, in localStorage (except the dismiss
          state per §3-B), in icons (no QR-encoded
          payloads), or in any UI-14 surface. Pre-auth
          shell is the login surface, period.

§11.6.6 — sw.js fetch handler ordering is NOT modified
          (UI-8 sealed). UI-14 modifies install +
          activate + message handlers ONLY. Cache routing
          (UI-13 §3-H pre-auth/post-auth split) is NOT
          modified.

§11.6.7 — sw.js update strategy [UI-14 §3-F SW Update
          Lifecycle Lock — EXPLICIT DEVIATION FROM UI-8]:
          NEW SWs install as "waiting"; NEW SWs do NOT
          call clients.claim on activate. The page
          surfaces a refresh affordance when
          registration.waiting is detected. The waiting
          SW calls skipWaiting ONLY in response to a
          postMessage({ type: 'SKIP_WAITING' }) sent by
          the page after USER CLICK on the refresh
          affordance. The first-load case (no existing
          SW) retains UI-8 skipWaiting+claim. Future
          chunks touching sw.js install / activate /
          message handlers MUST audit against this new
          lock; UI-15+ reopens it only via a chunk-level
          brief earning a SEALED revisit.

§11.6.8 — install.js stores ONLY the dismiss state in
          localStorage (key: karasu.install.dismissed_at,
          ISO-8601 string). NO other localStorage writes.
          NO sessionStorage writes. Negative-shape test
          binding.

§11.6.9 — refresh affordance lives in the SAME footer slot
          family as install affordance (mutually exclusive
          render — at most ONE of {install state line,
          refresh state line} renders at any time). The
          editorial calm pin (UI-3 / UI-5) does not allow
          two competing footer affordances.

§11.6.10 — iOS Safari path: NO MODAL ANYWHERE
           [SEALED 2026-05-08]. The "ready" state in the
           footer slot renders an inline hint "(Share →
           Add to Home Screen)" in --fg-2 alongside the
           "Install: ready" accent text. NO click handler
           on the iOS path. NO JS-driven install trigger
           (impossible on iOS by platform anyway). NO
           redirect. Full educational walk-through lives
           in docs/pwa-install.md (§3-E sealed
           deliverable), NEVER as chrome inside the app.

§11.6.11 — display-mode: standalone CSS (body.is-installed
           class) hides ONLY the install affordance. NO
           other layout / chrome / behavior change. The
           surface is identical inside the installed PWA
           and inside a browser tab (modulo the missing
           browser chrome). Editorial calm pin.

§11.6.12 — Maskable icon safe-area inset is 12.5% per
           spec.whatwg.org/manifest. The PNG MUST visibly
           preserve the canonical crow's silhouette inside
           the radial 80% mask. Test artefact: the
           rendered PNG inside the mask visualization.

§11.6.13 — Icon provenance: every emitted PNG inherits
           the source SVG's CC-BY-SA 4.0 license chain.
           THIRD_PARTY_NOTICES.md SHALL document the
           OpenMoji adaptation chain + Karasu-side
           additions. NO attribution-stripped icons.

§11.6.14 — beforeinstallprompt event capture: install.js
           CAPTURES the event via preventDefault() and
           saves the event reference for later prompt()
           call. The event is NEVER auto-prompted. The
           dismiss state in localStorage acts as the
           gating layer; if dismissed_at is within the
           30-day window AND no new SW activation since,
           the affordance renders as "available" but the
           click is no-op until window expires (or
           operator clears localStorage).

§11.6.15 — Mobile layout audit deliverable is a set of
           PNGs at 320/360/375/414 viewports for each
           surface (login, shell, drawer, modal,
           design-system page). Audit findings drive
           CSS fixes IN-PLACE. NO new mobile-mode toggle.
           NO user-agent sniffing. NO conditional
           rendering by viewport size beyond CSS media
           queries.

§11.6.16 — install.js + manifest.webmanifest + icons/* +
           pwa-install.md docs MUST NOT contain raw push
           endpoints, raw VAPID secrets, raw session
           tokens, raw credentials, raw scrypt hashes, OR
           any other secret material. Pin §11.6.16
           carry-forward verbatim from UI-12c.

§11.6.17 — iOS push branch in UI-12b modal copy: when
           navigator.standalone === false on iOS, the
           modal primary CTA changes copy AND links to
           the install affordance. The push subscription
           flow (PushManager.subscribe) is NOT called in
           that branch (would silently fail on iOS Safari
           tab). UI-14 modifies the COPY ONLY; the
           UI-12b code path post-install is identical.

§11.6.18 — Telegram interface remains active alongside
           the PWA. UI-14 does NOT remove the Telegram
           bot, NOT modify the Telegram inbound /
           outbound flows, NOT change the controller's
           Telegram source registration.

§11.6.19 — UI-14 chunk PR test surface MUST NOT regress
           the inherited test count (985 passing on main
           HEAD post-UI-13). Net delta is positive
           (~50-100 new tests anticipated).

§11.6.20 — ALL §3 SEALED items in this brief are binding
           on the UI-14 code chunk; ALL §3 PROPOSAL items
           flip to SEALED at operator sign-off OR are
           amended in a brief follow-up commit before the
           code branch opens.
```

## 12 · Status

```text
Brief status:    SIGN-OFF COMPLETE 2026-05-08 — all §3
                 sub-decisions sealed, all §10 questions
                 resolved. Awaiting Codex audit.
Brief audit:     pending (round 1 not started).
Brief loop budget: 5 (round 1 not started).

Brief PR:        #113
Brief base:      main
Brief HEAD:      docs/ui-14-brief
Brief diff:      doc-only.

Code chunk PR:   not opened. Earns its own brief-before-
                 code lifecycle gate (UI-9 audit pin #1):
                 brief PR merges → code branch opens.

Phase 4 status:  FIRST CHUNK CLOSED (UI-13 PR #109,
                 6e283a8); UI-14 is SECOND CHUNK,
                 currently at brief-stage with sign-off
                 complete.

Sealed deviations from prior shape-locks:
  - UI-8 SW lifecycle (§3-F): NEW shape-lock
    `UI-14 §3-F SW Update Lifecycle Lock` binding for
    every future chunk that touches sw.js install /
    activate / message handlers. UI-15+ reopens only
    via a SEALED revisit. This is the ONLY deviation
    in UI-14.

Inherited pins:  165 binding (52 base + 6 UI-10 §0.5 + 12
                 UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b
                 §11.6 + 4 PR #102 round-2 forward-carry +
                 20 UI-12c §11.6 + 20 UI-13 §11.6 + 19
                 Phase 4 macro). UI-14 anticipates +20
                 §11.6 pins (this brief §11) bringing the
                 stack to 185 on UI-14 close (subject to
                 audit refinement).

Test suite:      985 passing on main HEAD (post-UI-13).
                 UI-14 anticipates ~50-100 new tests; net
                 delta positive.

Lighthouse:      UI-9.1 baseline holds. UI-14 anticipates
                 PWA-category improvement (manifest +
                 icons + SW update strategy lift the
                 installability score) without perf
                 regression.

Next step:       Implementer (Claude Code) entrega the
                 Codex audit prompt copy-paste to the
                 operator immediately after this commit
                 (per feedback_audit_prompt_automatic.md).
                 Codex audits; verdict ferried back via
                 the operator. In-branch follow-ups;
                 re-audit if round 1 returns CHANGES-
                 REQUIRED with P0. Brief PR merges
                 BEFORE the UI-14 code branch opens.
```

---

> **Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>**
> **Co-Audited-By: Codex (via ChatGPT, operator-mediated) — pending**
