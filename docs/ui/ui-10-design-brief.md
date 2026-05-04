# Karasu UI — UI-10 Design Brief (write paths)

> Doc-only seal of the visual + structural direction for UI-10+.
> Audited and merged BEFORE any code chunk opens.
> Parallel to `ui-0-design-brief.md`, which sealed UI-1..UI-9.
> Every UI-N chunk after this one (N ≥ 10) executes against the
> decisions recorded here.

## 0 · Why this brief exists

Codex pin #1 from the UI-9 audit (PR #81, 2026-05-04):

> *"UI-10+ introduces write paths, so it must earn a new brief
>  before code."*

UI-1..UI-9 shipped the **read-only watchtower MVP**. The bus
was never mutated by the UI; the only state changes the
operator could trigger were observed through Telegram inbound
(`/scar`, `/correct`) which the controller subscribed to and
materialised as `human_decision` + resubmit events.

UI-10+ opens the first **write path inside the UI itself**.
That changes the surface contract in three ways that warrant
their own design seal:

```text
1. The UI gains a destructive action (scar revoke) the operator
   can fire from the browser. Confirmation, undo, and audit
   trail become product surface concerns.

2. The bus gains a new event-emission point the UI is
   responsible for. The schema for that event has to land here
   (in this brief) so its tests + projection can be written
   before the visual code.

3. The trust gradient becomes visible to the operator for the
   first time. Up to UI-9 the trust_level is a backend concept
   surfaced only through `dispatch.trust_level` on the wire
   (and in the UI-7 drawer's pretty-printed JSON). UI-10+
   makes a write-affordance that the trust gradient gates;
   that gating has to be legible.
```

The 28 binding pins from UI-2..UI-9.1 audits all carry forward.
This brief does NOT supersede them; it adds the structural
contracts UI-10+ chunks need on top.

---

## 1 · Positioning

UI-1..UI-9 was *the watchtower*. UI-10+ is *the workshop the
watchtower is already inside* — but the watchtower stays
the visible surface. The operator does not switch modes; they
extend their existing inspection actions with a single new
verb: **revoke**.

> A scar is a stored correction. Revoking a scar is the
> operator saying "this correction does not apply anymore".
> The bus records the revoke as a `human_decision` with
> `data.action = "scar_revoke"`; the ScarEngine consumes it on
> next dispatch and the override stops firing.

The first second of looking at the UI before AND after UI-10
must read identical. The revoke affordance does NOT live in a
new pane, a new toolbar, a new tab. It lives inside the
existing detail drawer (UI-7) on rows / map nodes that resolve
to a `human_decision`-typed event with a recorded scar.

The look is still the marketing. The revoke is a verb the
operator earns by drilling into a specific event, not a button
that floats on the canvas.

## 2 · Visual references (anchors held)

Same anchors as UI-0 §2:

```text
linear.app          editorial restraint; destructive actions
                    inline, never floating. Linear's "Delete
                    issue" is a menu item inside the issue,
                    NOT a button on the timeline.
vercel.com          confirmation dialogs are typographic, not
                    chrome. Single sentence + two buttons.
stripe.press        attention through copy + spacing, not
                    badges / colour fireworks.
```

UI-10+ inherits these. Material defaults / Tailwind defaults /
component-library chrome remain forbidden (UI-0 §4 holds).

## 3 · Confirmed decisions (operator sign-off, 2026-05-04)

All six decisions confirmed binding by Victor on 2026-05-04.

```text
A) Surface for the revoke affordance:
   The UI-7 drawer (existing). NO new pane, NO new tab, NO
   header toolbar.
   [CONFIRMED 2026-05-04]

B) Confirmation flow:
   Modal overlay using --shadow-2 (the elevation token UI-0
   §5.4 reserves for the drawer; the modal sits one layer
   above). Click the revoke button → modal appears with the
   scar's stored correction text + two buttons (Cancel /
   Revoke). NOT a two-step inline; the modal is the friction
   that prevents accidental destructive actions.
   [CONFIRMED 2026-05-04]

C) Authentication:
   None for UI-10. The Karasu UI is operator-local (127.0.0.1)
   and the operator is the human running the process. A
   future deployed-on-server surface (UI-12+) earns its own
   auth design.
   [CONFIRMED 2026-05-04]

D) Bus event schema for revoke:
   New event type? NO. Reuse `human_decision` with:
     data.action       = "scar_revoke"
     data.scar_id      = <id from ScarEngine>
     data.reason       = <optional free-text>
   This stays additive (no schema break for UI-1..UI-9
   consumers) and matches the existing `/correct`+`/scar`
   Telegram inbound pattern.
   [CONFIRMED 2026-05-04]

E) Server endpoint for revoke:
   POST /api/scars/<scar_id>/revoke → emits the
   human_decision event + returns 204. The endpoint is
   the SECOND write path on the server (the first is
   /api/github/webhook); it sits behind the same SW
   network-only contract from UI-8 (Codex pin #3 from UI-7
   audit). No cache.
   GET /api/scars → list current scars + their stored
   correction text. Read-only, additive.
   [CONFIRMED 2026-05-04]

F) Single revoke or batch:
   Single. Batch revokes are a UI-12+ concern; UI-10 ships
   one-scar-at-a-time only. Each revoke is one click +
   modal + one POST.
   [CONFIRMED 2026-05-04]
```

## 3.5 · Operator pin (binding, added 2026-05-04)

Victor added one editorial pin alongside the six §3 confirms.
Treat as P0 for UI-10+ chunks:

```text
Write-path UX must make mutation explicit, reversible only if
the backend supports it, and visually quieter than the
read-only watchtower. The operator should feel: "I am revoking
a scar," not "I am managing a dashboard."
```

How this pin shapes UI-10 implementation:

```text
- "Mutation explicit" → the modal is non-skippable. No
  inline-confirm shortcut, no keyboard accelerator that
  bypasses the modal in UI-10. The friction IS the design.
- "Reversible only if the backend supports it" → UI-10 does
  NOT ship undo. Revoke is final from the UI side; if the
  ScarEngine grows a re-apply / un-revoke path later, that
  earns its own affordance. The brief is honest about
  irreversibility.
- "Visually quieter than the read-only watchtower" → the
  revoke button is NOT --accent (the existing surface accent).
  It is --danger (semantic alias to the same hex; see §5.1).
  The modal is single-column, single-sentence above the
  scar quote, two buttons. No icons, no badges, no chrome
  beyond the existing tokens.
- The operator-feel test: when Victor (or any operator) hits
  Revoke on a real scar in dogfood, the click should feel
  like a deliberate action against ScarEngine, not like
  ticking a checkbox in a settings panel. Codex audit on
  the implementation chunk verifies this against the .webm.
```

## 4 · Tech stack (delta vs UI-0 §4)

UI-0 §4 still holds:

```text
Language     : TypeScript strict (target ES2022)  — unchanged
Build        : Vite                               — unchanged
Framework    : none                               — unchanged
Styling      : hand-written CSS                   — unchanged
Graphics     : SVG inline + CSS animations        — unchanged
Backend      : reuse src/karasu/ui/server.py      — unchanged
PWA          : vanilla service worker             — unchanged
Tests        : Playwright + pytest                — unchanged
```

What changes for UI-10+:

```text
- The server.py grows a POST handler. Until UI-10 the only
  POST path was /api/github/webhook (chunk 4a). The pattern
  is the same: HMAC-or-csrf-protected, JSON body, 204 on
  success. UI-10's POST is operator-local (no HMAC needed,
  see decision C); the SW contract from UI-8 (network-only
  for /api/*) blocks any caching automatically.
- HTTP-level shape locks (UI-9 pattern in
  tests/test_ui_server_http.py) extend to cover the new
  POST endpoint(s) BEFORE the visual code lands.
- The bus event schema gains the documented additive fields
  on human_decision (data.action, data.scar_id, data.reason).
  /docs/event-schema.md updates in the same chunk.
```

## 5 · Design system (delta vs UI-0 §5)

### 5.1 · New colour: --danger (NOT --error)

Up to UI-9, error and accent share `#d54834` (rojo cuervo) —
"error IS the identity" per UI-0 §5.1. That equation breaks for
the destructive verb: a button that says "Revoke" in `--accent`
reads as a regular accent button, not as a destructive one.

```text
--danger:  #d54834 (same hex, different semantic alias)
```

The `--danger` token aliases to the same hex as `--accent`
because the editorial palette is bound. The DIFFERENCE is in
the rule that gates it: `--danger` only appears on
**destructive confirmation buttons in modals**, never on
non-destructive action surfaces. A future operator could split
the alias if dogfood asks for it (e.g. `--danger: #c63a30`,
slightly more saturated); the contract is the alias today.

### 5.2 · New primitive: modal dialog

UI-0 §5.4 reserved `--shadow-2` for the drawer. The UI-10
modal earns the SAME `--shadow-2` because it's also a layer
that floats over the canvas. The drawer can stay open while a
modal opens above it.

```text
.modal             container, max-width 480px, centred,
                   --bg-1 background, --shadow-2 elevation,
                   --radius-1 corners.
.modal-backdrop    full-viewport, rgba(0,0,0,.5), opacity
                   transition 240ms ease-out (chromatic
                   whitelist exception — opacity is not on
                   the whitelist; reduced-motion makes it
                   instant per UI-2 contract).
.modal-title       --fs-20 display, --fg-1, single line.
.modal-body        --fs-14 mono for the scar text quote;
                   --fs-16 display for the editorial sentence
                   above it.
.modal-actions     two buttons, justified end. Cancel
                   secondary (--fg-2 → --fg-1 on hover).
                   Revoke primary (--danger).
```

Single primitive serves UI-10. UI-11+ may add a second modal
type (informational, no destructive action); the .modal +
.modal-actions classes are already future-proofed.

### 5.3 · Motion (delta vs UI-0 §5.5)

```text
durations
  micro     120ms   unchanged
  panel     240ms   modal slide-in (same as drawer)
  flight    600ms   unchanged
  ambient   4000ms  unchanged
  modal-open 240ms ease-out  (new — but reuses panel value)

reduced motion
  Backdrop opacity transition becomes instant (1ms) per the
  reset.css chromatic whitelist (UI-2 contract).
  The modal still appears; only the slide-in is suppressed.
  Same contract as the drawer in UI-7.
```

### 5.4 · The crow (delta vs UI-0 §5.6)

The crow gains NO new state for UI-10. The five existing
states (idle / processing / waiting / error / offline) cover
the full surface. The revoke confirmation is operator-driven
and resolves before the bus advances; the crow's state during
a revoke depends on what events the bus already carries, not
on the revoke action itself.

If the operator triggers a revoke and the resulting
`human_decision` event lands on the bus, the crow's state
follows the existing `_crow_state` precedence rules — no new
branch needed.

## 6 · Roadmap (chunk-by-chunk, UI-10..UI-13)

Each chunk = one PR audited by ChatGPT. ≤400 LOC including
tests. Every chunk **ships something visible and functional**.

```text
UI-10   Scar revoke. The first write path. Adds:
          - GET /api/scars  (list)
          - POST /api/scars/<id>/revoke
          - .modal primitive in CSS
          - Drawer extension for human_decision events with a
            recorded scar: shows the scar text + a "Revoke"
            button.
          - Modal flow: click "Revoke" → modal → confirm →
            POST → bus event lands → drawer refreshes →
            timeline shows the new human_decision event.
          - HTTP shape locks for both endpoints.
          - Unit tests for the new ScarEngine.revoke(...)
            interface.

UI-11   Trust adjust UI. The operator can change a per-adapter
          trust_level from the surface. Read-only display first
          (a small section in the design-system page or the
          drawer), then a write affordance gated behind a
          modal (same .modal primitive).
          May ship as UI-11a (display) + UI-11b (write).

UI-12   Push notifications. The PWA subscribes to a
          server-side push channel; the operator gets a
          desktop notification when an `agent_response` lands
          requires_human=true OR when a github_webhook
          arrives. Reuses the offline.html crow asset for the
          notification icon.
          Earns its own brief because push UX has its own
          opt-in / unsubscribe / privacy surface.

UI-13+  Multi-operator surfaces (deployed Karasu, login,
          authorization tiers, audit log filtering). Earns
          its own brief; out of scope here.
```

## 7 · Audit cadence (escalated for write paths)

Every UI-N PR (N ≥ 10) MUST include everything UI-0 §7 already
required, PLUS:

```text
1. PNG of the new modal in BOTH motion and reduced-motion
   states. The chromatic whitelist contract from UI-2 covers
   the implementation; the audit verifies the PNG.
2. PNG of the drawer with the revoke affordance visible.
3. PNG of the post-revoke surface (drawer reflects the new
   event, timeline shows it).
4. .webm walking click → modal → confirm → result. The modal
   slide-in is the new motion surface; pin #5 from UI-3 audit
   (full-shell context >= 1024×640) carries forward.
5. HTTP shape locks for the new endpoints, landing in the
   same PR as the visual code (Codex pin C from UI-9 audit
   reaches its endpoint here too).
6. Bus event schema diff in the PR body. Any human_decision
   field added must be documented in docs/event-schema.md
   in the same PR.
7. Confirmation-flow regression test: a Playwright test that
   exercises the click → modal → cancel path AND the click
   → modal → confirm → POST path, asserting that cancel does
   NOT mutate the bus.
```

## 8 · Frozen contracts (UI-10+ MUST respect)

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol — all frozen.
- The bus event schema (additive only; UI-10's revoke fields
  are additive on human_decision).
- The /api/events / /api/health / /api/meta projection
  shapes pinned by tests/test_ui_server_http.py (UI-9). Any
  new field on the projection requires an
  EVENTS_PROJECTION_KEYS update in the SAME PR.
- The SW fetch handler ordering from UI-8 (FIRST-BRANCH
  /api/* network-only). Any new POST endpoint sits inside
  /api/* and is therefore network-only by construction.
- The Lighthouse threshold contract from UI-9.1 (Performance
  85, Accessibility 95, Best Practices 95, SEO 90).
- The 28 binding pins from UI-2..UI-9.1.
```

## 9 · Out of scope for THIS brief

```text
- Batch revoke. Single-scar-at-a-time only.
- Undo / redo. The bus IS the audit log; a revoke can be
  countered by another revoke or by a fresh /scar, not by an
  in-UI undo button.
- Authentication / authorization. UI-10 ships local-only.
- Deployed Karasu surface. UI-12+ concern.
- Push notifications. UI-12 concern.
- Trust gradient editing. UI-11 concern.
- New crow state. The five existing states cover UI-10+.
- Multi-operator collaboration. UI-13+ concern.
- A "diff against scar history" surface (showing what the
  scar changed before vs after revoke). Future chunk.
- Keyboard shortcuts beyond the existing Tab / Enter / Esc
  contract (UI-3). A power-user shortcut layer waits for
  UI-13+.
```

## 10 · Open questions resolved (operator sign-off, 2026-05-04)

All six pre-implementation decisions confirmed binding.

```text
1. Scar id format.
   STABLE HASH STRING. NOT UUID. Use the existing ScarEngine
   id if one already exists; otherwise derive deterministic
   hash from the correction content + timestamp/origin
   canonical.
   URL pattern: /api/scars/<scar_id>/revoke
   Allowed character set: [A-Za-z0-9._:-]+ (no /, no ? or #)
   so the path segment is URL-safe without percent-encoding.
   The HTTP shape lock in test_ui_server_http.py pins the
   character set: any id outside the regex is a server-side
   bug, not a UI input concern.
   [CONFIRMED 2026-05-04]

2. Revoke reason — optional.
   Modal renders an optional textarea below the scar quote.
   The text is trim()ed before send; if the trimmed result
   is empty, the field is omitted from the bus event payload
   (NOT serialised as "" sentinel, NOT serialised as null).
   Empty reason MUST NOT block the revoke — the modal's
   Revoke button stays enabled regardless.
   [CONFIRMED 2026-05-04]

3. Cancel button — closes ONLY the modal.
   The underlying drawer stays open at the same row / node
   so the operator can re-attempt or move on without losing
   context. Cancel is purely a "back out of this revoke"
   action, NOT a "close the inspection" action.
   [CONFIRMED 2026-05-04]

4. Post-revoke drawer behaviour — refresh AND annotate.
   After a successful revoke:
     a) Drawer does NOT close.
     b) Drawer body refreshes to reflect the scar's new
        revoked state (timestamp, optional reason).
     c) The annotation must make the revocation visible —
        the operator should SEE that the scar is now
        revoked, not have to infer it from the timeline.
   Implementation note: the drawer reads from /api/scars on
   open; after a successful POST, the drawer re-fetches and
   re-renders. The new human_decision event the bus emitted
   also lands on the timeline by the next /api/events tick.
   [CONFIRMED 2026-05-04]

5. /api/scars list shape lock.
   {scars: [{id, correction_text, created_at, applied_count,
            last_applied_at}]}
   Plus, IF AND ONLY IF the ScarEngine already exposes them
   naturally (no new ScarEngine work):
     status        ("active" | "revoked")
     revoked_at    (ISO-8601 timestamp or null)
   If those two fields would require new ScarEngine
   plumbing, defer them to a UI-10 follow-up — do NOT widen
   UI-10 scope. The HTTP shape lock pins whichever subset
   ships: implementation reads ScarEngine's public surface,
   tests assert what's actually returned.
   [CONFIRMED 2026-05-04]

6. Modal close UX with Esc.
   First Esc closes the modal. Second Esc closes the drawer.
   The modal has focus priority — when open, all keyboard
   events (Esc, Tab, Enter on Cancel/Revoke) target the
   modal first. Click-outside the modal also closes it
   (modal backdrop click); click-outside the drawer (when
   modal is closed) closes the drawer per UI-7's existing
   contract.
   [CONFIRMED 2026-05-04]
```

These six decisions + the §3 (A-F) confirms + the §3.5
operator pin are the binding contract UI-10 implementation
runs against.

## 11 · Definition of "done" for UI-10

```text
- One PR, ≤400 LOC including tests + the new endpoint(s).
- The .modal primitive ships with reduced-motion contract.
- The drawer extension shows the revoke button only on
  human_decision events that resolve to a recorded scar
  (not on every event — the visual surface stays calm).
- The new POST endpoint has a Playwright regression test
  for cancel + confirm paths.
- HTTP shape locks for /api/scars + /api/scars/<id>/revoke.
- docs/event-schema.md updated with the additive
  human_decision fields.
- A .webm walking the full flow under
  docs/ui/recordings/UI-10-revoke.webm.
- PNGs for: drawer with revoke button visible, modal default,
  modal hover, modal reduced-motion, post-revoke surface.
- Lighthouse re-run after the chunk lands; thresholds
  unchanged from UI-9.1 (Performance 85 / 95 / 95 / 90).
- Codex audit returns APPROVED or APPROVED-with-observations.
```

After UI-10, the operator can revoke a scar from the surface
without touching Telegram. UI-11+ chunks add trust adjust + push
notifications, each with their own brief.

## 11.5 · Operator pin reinforced in Definition of done

The UI-10 implementation chunk's audit cadence (§7) carries an
explicit operator-feel check derived from the §3.5 pin:

```text
- Codex audit on UI-10 PR verifies the .webm against the
  question: "does the click → modal → confirm flow read as a
  deliberate action against ScarEngine, or as ticking a
  checkbox in a settings panel?" If it reads as the latter,
  that is a P0 — the editorial pin is binding.
```

## 12 · Status

```text
Brief status:        CONFIRMED — operator sign-off recorded
                     2026-05-04 (six §3 + six §10 + one §3.5
                     pin all confirmed).
Operator sign-off:   COMPLETE.
Codex audit:         PENDING — design-review pre-implementation
                     gate (same pattern as UI-8 design review
                     locked in commit 1f7266d on PR #79).
Implementation:      BLOCKED on this brief merging.
```

Once Codex audits this brief, it merges to main and UI-10
implementation can open against it. The merge sequence for the
UI MVP (#78–#82) is independent and can land in parallel.
