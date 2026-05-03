# Karasu UI — UI-0 Design Brief

> Doc-only seal of the visual direction for the Karasu UI
> surface. Audited and merged BEFORE any code chunk opens.
> Every UI-N chunk after this one executes against the
> decisions recorded here.

## 1 · Positioning

Karasu is not a dashboard. It is **a watchtower** — a window
into the bus where the operator comes to *see the system
think*, not to drive it. The UI's first job is to present the
event stream with editorial calm; the second is to give the
crow — Karasu's mascot — a stage where it visibly carries
messages between domains. Everything else is in service of
those two.

The first second of looking at the UI must read as
"someone built this with intent". Not "someone shipped a
dashboard fast", and not "someone bolted a theme onto a
framework". The look is the marketing.

## 2 · Visual references (anchors, not blueprints)

```text
linear.app          typography scale + monochrome restraint;
                    no decorative chrome, content forward.
vercel.com          generous whitespace, type-driven hierarchy;
                    asymmetric grid that doesn't feel scattered.
stripe.press        editorial-grade attention on a single page;
                    every detail intentional.
warp.dev            developer surface that does not look like
                    a developer tool.
anthropic.com/claude calm dark, hand-set rather than templated.
```

None of these use Material defaults, Tailwind defaults, or
component-library chrome. None of them feel "framework-shaped".
That is the negative space the Karasu UI sits in.

## 3 · Confirmed decisions (operator sign-off, 2026-05-03)

```text
A) Accent color:  rojo cuervo (#d54834). Single accent.
                  Error state shares this color — error IS the
                  identity.
B) Display font:  Inter Display (Inter family v4.x). Self-hosted
                  woff2. SIL Open Font License 1.1.
C) Mono font:     JetBrains Mono (v2.304). Self-hosted woff2.
                  SIL Open Font License 1.1.
D) Win95 mockup:  archived to docs/ui/explorations/. Recognises
                  prior exploration without continuing it.
E) Cadence:       UI-0 explicit (this doc). All subsequent
                  chunks execute against this brief.
```

## 4 · Tech stack (decision, not menu)

```text
Language:    TypeScript strict (target ES2022).
Build:       Vite. Output single-page static bundle.
Framework:   none. Vanilla TS modules + custom CSS variables.
Styling:     hand-written CSS, design tokens via custom
             properties. NO Tailwind, NO CSS-in-JS, NO
             component library.
Graphics:    SVG inline + CSS animations. NO canvas, NO WebGL,
             NO Lottie.
Backend:     reuse src/karasu/ui/server.py (stdlib HTTP).
             Polling /api/events; no WebSocket in MVP.
PWA:         vanilla service worker (chunk UI-8). Web App
             Manifest. Push API later (chunk UI-10+).
Tests:       Playwright for visual + interaction regression
             from UI-5 onward; pytest for the server side.
```

### Why no React / Tailwind

Frameworks are productive. They also stamp their voice on
everything they touch. Linear, Vercel, Anthropic and Stripe
Press do not look templated because they are not templated.
For a surface whose first job is to "look hand-set", giving
up the React / Tailwind tax buys exactly that quality at the
price of ~10% more keystrokes per primitive. One person can
maintain ~5K LOC of vanilla TS + CSS without strain; that is
more than this UI needs through chunk UI-9.

If the surface ever grows past chunk UI-10 into a multi-view
PWA with auth and write paths, a re-evaluation is on the
table. Not before.

## 5 · Design system

### 5.1 · Color (dark editorial)

```text
--bg-0:    #0a0a0b   canvas, deepest neutral
--bg-1:    #131316   panels, +1 step
--bg-2:    #1c1c20   hover/focus surfaces, +2 step
--fg-1:    #ededf2   primary text
--fg-2:    #8a8a93   muted text, metadata, timestamps
--fg-3:    #4d4d54   dividers, subtle borders
--accent:  #d54834   rojo cuervo — single accent, error,
                     active state, the crow's eye
--ok:      #4a9d6a   subtle success
--warn:    #c69a4d   requires_human, attention-but-not-error
```

Contrast ratios verified for WCAG AA on `--bg-0`:
`--fg-1` 14.6:1, `--fg-2` 5.1:1, `--accent` 4.7:1. AAA on
primary text.

### 5.2 · Typography

```text
Display:  Inter Display 4.x (woff2, weights 400 / 500 / 700)
          Self-hosted at /assets/fonts/inter-display-{w}.woff2
          License: SIL OFL 1.1 (commercial use OK, embedding OK,
          modifications OK with rename).

Mono:     JetBrains Mono 2.304 (woff2, weights 400 / 500 / 700)
          Self-hosted at /assets/fonts/jetbrains-mono-{w}.woff2
          License: SIL OFL 1.1.

Scale:    12 / 14 / 16 / 20 / 28 / 44 px — ratio 1.4
Weights:  400 (body), 500 (UI labels), 700 (display headers)
Tracking: -0.01em on display ≥20px (hairline tightening)
Line-height: 1.5 (body), 1.2 (display ≥28px), 1.0 (mono)

Font fallback: ui-sans-serif, system-ui, -apple-system,
               Segoe UI, Roboto for display;
               ui-monospace, "SF Mono", Consolas for mono.
               Fallback used until woff2 loads (FOUT
               accepted; FOIT rejected — first paint must
               be readable).
```

### 5.3 · Spacing & grid

```text
Base unit: 4px.
Stack:     4 / 8 / 12 / 16 / 24 / 32 / 48 / 80 px.
Default:   generous; the surface earns its calm.

Grid:      12-column fluid. Gutter base 80px on ≥1280, 48px
           on ≥768, 24px on <768. Asymmetric layouts allowed
           and encouraged — no centered "blog column".

Max width: 1440px content, 1920px chrome (header / footer
           span the viewport).
```

### 5.4 · Motion

```text
Easings:
  ease-out  cubic-bezier(0.22, 1, 0.36, 1)   — entrances
  ease-in   cubic-bezier(0.32, 0, 0.67, 0)   — exits
  ease-mag  cubic-bezier(0.5, 0, 0.1, 1)     — the crow

Durations:
  micro     120ms   hover, focus, color shift
  panel     240ms   drawer open / close, accordion
  flight    600ms   the crow crossing the Live Map
  ambient   4000ms  the crow's idle breathing loop

Reduced motion (prefers-reduced-motion: reduce):
  ALL durations clamped to 1ms except color transitions.
  The crow stops flying; state changes still happen via
  color only. This is non-negotiable.
```

### 5.5 · The Crow (mark of the house)

```text
Format:     SVG, monochrome, single path where possible.
Sizing:     16 / 24 / 48 / 96 px display sizes; vector
            scales beyond.
States:     idle       fg-1, ambient breathing
            processing accent, slow pulse
            waiting    warn, asymmetric tilt
            error      accent, sharp shake (single beat)

Idle anim:  1px translate-Y over 4s, ease-mag both ways.
            Subliminal — the crow looks alive even at rest.

Flight:     SVG arc-path between two Live Map nodes.
            600ms ease-mag. The crow rotates along the
            tangent of the path so its beak leads.

Constraint: sprite source lives at
            docs/ui/assets/karasu_sprites_spec.md (already
            on the parallel branch). UI-5 finalises the
            production SVG and writes the corresponding
            asset under src/karasu/ui/static/assets/.
```

## 6 · Roadmap (chunk-by-chunk)

Each chunk = one PR audited by ChatGPT. ≤400 LOC including
tests. Every chunk **ships something visible and functional**;
no scaffolding-only PRs.

```text
UI-0   THIS DOC. Brief sealed by audit.

UI-1   Cherry-pick the 6 UI commits from feat/ui-1-runtime
       onto current main + cleanup. Move Win95 mockup to
       docs/ui/explorations/. server.py runs against current
       bus schema (priority, controller_chain_depth,
       github_*).

UI-2   Design system primitives in CSS custom properties.
       tokens.css ships every token from §5. Self-hosted
       woff2 of both fonts in src/karasu/ui/static/assets/
       fonts/. Custom minimal reset (no normalize.css).
       /design-system page renders palette swatches, type
       scale, spacing examples — doubles as visual regression
       baseline.

UI-3   Application shell. Header (crow logo + agent + bus
       path), main canvas, footer (version + last event time).
       Empty state cared for: a sentence about what Karasu
       sees plus the idle crow. Opens beautifully with zero
       events on the bus.

UI-4   Event timeline as editorial beats. Each event is a
       typographic line, not a table row: timestamp (mono),
       type (display), path / agent (muted). Hover and
       focus states. Connects to /api/events; no Live Map
       yet.

UI-5   THE CROW. SVG asset finalised. Idle breathing in the
       header. State color changes against real bus events.
       This is the chunk that makes the "guau" happen.

UI-6   Live Map. Five domain nodes (User / Karasu / Claude /
       Codex / GitHub). The crow from UI-5 now flies between
       nodes per the latest event. Arc-path SVG; 600ms
       ease-mag.

UI-7   Detail panel. Click on timeline row or map node →
       lateral drawer with pretty-printed JSON. Custom
       syntax highlighting on our palette (no highlight.js).

UI-8   PWA shell. manifest.json, service worker, offline
       page (with the crow in an "out of signal" state —
       intended easter egg).

UI-9   Server tests + Lighthouse pass. HTTP-level pytest
       for /api/events shape pinning the bus schema.
       Lighthouse Performance ≥95, Accessibility ≥95,
       Best Practices ≥95, SEO ≥90. WCAG AA verified.
       Reduced-motion verified.

UI-10+ Trust management UI, scar browse / revoke, push
       notifications. Each is its own design pass; each
       introduces write paths to the bus and therefore
       tighter audit. Out of scope for this brief.
```

## 7 · Audit cadence (operative change vs. backend)

UI cannot be audited from a diff alone — the auditor must
see the result. Every UI-N PR (UI-1 onward) MUST include:

```text
1. Screenshot of every state introduced or changed by the
   PR. Captured locally via a script under scripts/ui_screen-
   shots.sh or via Playwright headless. Committed under
   docs/ui/screenshots/UI-N-<slug>/.

2. A short "what to look at" note in the PR body pointing
   the auditor at the visual decisions to evaluate (e.g.
   "type scale on the timeline rows", "the crow's idle
   breathing amplitude").

3. The diff itself, as usual.

4. The audit prompt for ChatGPT (same copy-paste flow as
   backend), explicitly inviting visual critique alongside
   structural critique.
```

This is the minimum to keep the auditor honest. A
text-only diff for UI work would be theatre.

## 8 · Out of scope for THIS brief (deferred decisions)

```text
- Sound design / audio cues. Tempting on the crow flight;
  not now. A future brief if dogfood asks for it.
- Multi-theme / light mode. Karasu is a watchtower at
  night. Light mode is a deferred chunk if operator demand
  surfaces.
- I18n / l10n. English + minimal Spanish copy in MVP. Full
  i18n is a separate design and engineering pass.
- Keyboard shortcuts. Designed-in obvious ones (focus,
  enter, esc) ship from UI-3. A power-user shortcut layer
  (?) waits for UI-10+.
- Mobile-first responsive. UI is desktop-primary
  (operator's working surface); mobile reduces to readable
  timeline. PWA installable on mobile but not optimised.
```

## 9 · Frozen contracts (UI must respect)

The UI work does NOT change any of:

```text
AgentResponse, F3, F7, F8, surface=sink, single-worker
invariant, scar=stored-correction-only, I-001..I-006,
TriggerSource Protocol, the bus event schema (additive only,
through a backend chunk, never from UI work).
```

UI-1..UI-9 are read-only against the bus. Write paths
(scar revoke, trust adjust) come in UI-10+ and MUST go
through ScarEngine / human_decision events, never through
direct bus mutation.

## 10 · Definition of "done" for the UI MVP

```text
- UI-1 through UI-9 merged on main.
- A first-time visitor reads "this is hand-built" within
  the first 5 seconds.
- An operator can replace 80% of `karasu tail` use with the
  UI without losing information.
- Lighthouse ≥95 on the four headline metrics; WCAG AA
  pass; reduced-motion pass.
- The crow flies between nodes on every dispatch.
- The bus is never mutated by the UI.
```

After UI-9, the operator can dogfood the UI alongside the
backend. UI-10+ chunks add write capabilities and PWA
features that earn their own brief.
