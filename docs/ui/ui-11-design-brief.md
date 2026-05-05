# Karasu UI — UI-11 Design Brief (trust adjust)

> Doc-only seal of the visual + structural direction for UI-11.
> Audited and merged BEFORE any code chunk opens.
> Parallel to `ui-0-design-brief.md` (UI-1..UI-9 read-only MVP)
> and `ui-10-design-brief.md` (UI-10 scar revoke). Every UI-N
> chunk after this one (N == 11) executes against the
> decisions recorded here.
>
> **STATUS:** CONFIRMED — operator sign-off complete on §3 +
> §10 decisions (Victor, 2026-05-05: "confirmado segun tus
> criterios" — every default proposal accepted as the
> binding contract). Awaiting Codex audit out-of-band before
> merge.

## 0 · Why this brief exists

Codex pin #1 from the UI-9 audit (PR #81) reaffirmed by the
UI-10 audit (PR #85):

> *"UI-N+ that introduces write paths must earn a new brief
>  before code."*

UI-10 opened the first write path inside the surface (scar
revoke). UI-11 introduces the **second** write path: trust
gradient adjust. The trust gradient gates how autonomously
each adapter mutates operator state; making it mutable from
the UI is a higher-blast-radius write than scar revoke,
because the value persists across dispatches and is
fundamental to the F-CAP / autonomous-warning surface.

The 34 binding pins from UI-2..UI-10 audits all carry forward.
This brief does NOT supersede them; it adds the structural
contracts UI-11 needs on top.

## 0.5 · Pins inherited from UI-10 audit

Codex pinned six rules on UI-10's audit (PR #85, 2026-05-05)
that bind UI-11 explicitly:

```text
1. Write verbs remain drawer-earned, not global chrome.
2. Any destructive or trust-changing mutation must use a
   confirmation modal unless this brief explicitly earns a
   different flow.
3. Pre-confirmation --danger styling is allowed only when the
   action is still gated by modal confirmation.
4. Every mutation must emit a bus event that the operator
   can inspect.
5. If timeline / display logic needs to distinguish
   human_decision subtypes, surface data.action in the
   projection with shape-lock tests in the SAME PR.
6. Keep write-path PRs scoped to one verb whenever possible;
   if a chunk exceeds the LOC target, justify by audit
   coherence, not convenience.
```

## 1 · Positioning

UI-10 was the watchtower's first scalpel — a single, narrow,
destructive verb (revoke) limited to one event type
(`human_decision` resolving to a recorded scar). UI-11 stays
in the same register but moves up the gradient: the operator
adjusts the autonomy level of an adapter.

> Trust gradient is not chrome. It is the contract that
> determines whether Karasu will mutate the operator's
> working tree without asking. Adjusting it is a deliberate
> act, not a settings panel.

The operator does NOT get a "trust manager" UI. Trust adjust
is a verb that lives on the **agent_response** event in the
detail drawer — the same drawer-earned pattern UI-10
established. Click an agent_response → see the trust_level
the dispatch ran at → optionally adjust it → modal confirmation.

Pin §0.5.1 binding: write verbs stay drawer-earned. UI-11 does
NOT add a header section, a dedicated `/agents` page, or a
toolbar entry. The verb appears only after the operator drills
into a specific agent's response.

## 2 · Visual references (anchors held)

Same anchors as UI-0 §2 + UI-10 §2:

```text
linear.app          editorial restraint; settings adjacent to
                    context, never floating in their own pane.
vercel.com          "Change deployment limits" lives inside the
                    deployment, not in a sidebar.
stripe.press        attention through copy + spacing, not chrome.
```

Material defaults / Tailwind defaults / component-library
chrome remain forbidden (UI-0 §4).

## 3 · Confirmed decisions (operator sign-off complete 2026-05-05)

All decisions below confirmed binding by Victor on 2026-05-05
("confirmado segun tus criterios" — every default proposal
accepted as the binding contract).

```text
A) Surface for the trust adjust affordance:
   PROPOSAL — The UI-7 drawer (existing). Same surface UI-10
   used. The verb appears only when the open event is an
   agent_response (the dispatch actually carrying a
   trust_level). NO new pane, NO new tab, NO new
   "/agents" page, NO header toolbar.
   [CONFIRMED 2026-05-05]

B) Confirmation flow:
   PROPOSAL — Modal overlay, .modal primitive (UI-10).
   Same friction-IS-the-design contract. Drop-down select
   in the modal (radio buttons, not free-text) with the
   three documented levels (0 / 1 / 2). Modal mandatory
   per pin §0.5.2.
   [CONFIRMED 2026-05-05]

C) Authentication:
   PROPOSAL — None for UI-11. Same as UI-10: surface is
   operator-local (127.0.0.1). UI-12+ deployed surfaces earn
   their own auth design.
   [CONFIRMED 2026-05-05]

D) Bus event schema for trust adjust:
   PROPOSAL — Reuse `human_decision` (no new event type)
   with:
     data.action          = "trust_adjust"
     data.agent           = <adapter name string>
     data.trust_before    = <int — the value before>
     data.trust_after     = <int — the value after>
     data.reason          = <optional free-text>
   Mirrors the additive pattern UI-10 used for scar_revoke.
   No schema break for UI-1..UI-10 consumers.
   [CONFIRMED 2026-05-05]

E) Server endpoints for trust adjust:
   PROPOSAL —
     GET  /api/agents            list current adapters + trust_levels
     POST /api/agents/{name}/trust    update trust + emit event
   The list endpoint reads from the configured adapters
   (the same source `cmd_watch` builds the adapter set
   from). The POST emits the human_decision event +
   returns 204 with no body. Same SW network-only contract
   from UI-8 holds (api/* network-only).
   [CONFIRMED 2026-05-05]

F) Persistence semantics — INTENT vs LIVE-MUTATION:
   PROPOSAL — INTENT only. The POST emits the bus event; it
   does NOT mutate the running adapter's `trust_level`
   attribute. Reason: `karasu ui` and `karasu watch` are
   separate processes; the UI server cannot reach the
   AgentAdapter instances of the watcher. A live-mutation
   path would require either (a) IPC between processes or
   (b) a controller subscription that reads the bus and
   updates adapters — both expand UI-11 into controller
   work and violate pin §0.5.6 (one verb per chunk).
   The honest UI-11 contract: emit the intent. Operator
   restarts `karasu watch` to pick up the new value, OR a
   later UI-12+ chunk earns the live-mutation pathway with
   its own brief.
   [CONFIRMED 2026-05-05 — most important decision in the
   brief; binds UI-11 scope to INTENT-only emit. Live
   adapter mutation deferred to UI-12+ with its own brief.]

G) Trust value range exposed by the modal:
   PROPOSAL — 0 / 1 / 2 (enum), rendered as three radio
   buttons. AUTONOMOUS_TRUST_LEVEL = 2 is the documented
   high-water mark in `src/karasu/adapters/base.py:21`;
   higher integers ARE technically allowed by the code
   but have no documented semantics. Conservative:
   restrict UI-11 to the documented range. A future
   chunk earns higher values with explicit semantics.
   [CONFIRMED 2026-05-05]

H) Single agent or batch:
   PROPOSAL — Single. Batch trust adjust is a UI-12+
   concern; UI-11 ships one-agent-at-a-time only. Each
   adjust is one click + modal + one POST.
   [CONFIRMED 2026-05-05]

I) Chunk split:
   PROPOSAL — Two chunks.
     UI-11a — read display: GET /api/agents + drawer
              extension that surfaces the current
              trust_level on agent_response events
              (read-only, no modal). HTTP shape lock for
              GET. Pin §0.5.5 (surface data.action in
              projection) lands HERE so the timeline can
              distinguish scar_revoke vs trust_adjust
              from the next UI-11b emit onwards. ~250 LOC.
     UI-11b — write affordance: POST endpoint, modal,
              JS handler, Playwright cancel/confirm tests,
              .webm. ~400 LOC.
   Reason: UI-10 hit ~3000 LOC; pin §0.5.6 binding asks
   for splits when feasible. UI-11a is small enough to
   land independently AND validates the read surface
   before the write.
   [CONFIRMED 2026-05-05]
```

## 3.5 · Operator pin (binding when sign-off lands)

Anticipated pin paralleling UI-10 §3.5 — adjust per operator
direction:

```text
Trust-adjust UX must make the gradient legible (the operator
must see the current value AND understand what each level
means before changing it), reversible only via the same
verb (NOT via Undo), and visually quieter than the
read-only watchtower. The operator should feel: "I am
raising Claude's trust level from 1 to 2, knowing that 2
means autonomous mutation," not "I am ticking a checkbox
in a settings panel."
```

How this pin shapes UI-11 implementation if accepted:

```text
- "Gradient legible" → the modal renders a one-line
  description per trust level (0 = quarantined, 1 = assistive,
  2 = autonomous), sourced from docs/local-dogfood.md so the
  copy stays in sync with the canonical doc. NOT a tooltip;
  visible inline.
- "Reversible only via the same verb" → no Undo. To go from
  trust=2 back to trust=1, the operator runs trust_adjust
  again. The bus is the audit log.
- "Visually quieter than the read-only watchtower" → no
  --danger except on the destructive direction (raising trust)
  or on the modal Confirm. Lowering trust uses --fg-1 (neutral)
  because reducing autonomy is not destructive in the same
  sense.
- The operator-feel test: when Victor (or any operator) hits
  Adjust on a real agent in dogfood, the click should feel
  like a deliberate trust gradient change, not like ticking
  a settings dropdown. Codex audit on the implementation
  chunk verifies this against the .webm.
```

## 4 · Tech stack (delta vs UI-0 §4)

UI-0 §4 still holds. UI-11 deltas:

```text
- The server gains a SECOND POST handler. UI-10's revoke is
  the precedent; the trust-adjust handler reuses
  _emit_human_decision and the same 204-on-success pattern.
- The /api/events projection grows ONE field: data.action.
  Pin §0.5.5 binding — the field surfaces in UI-11a so
  UI-11b can key timeline visuals on it. Shape lock pinned
  same PR.
- No new build / framework / runtime dependency.
```

## 5 · Design system (delta vs UI-0 §5 + UI-10 §5)

### 5.1 · Reuse, do not invent

Tokens: same. UI-10 introduced `--danger`; the alias is
already in `tokens.css`. Pin §0.5.3 binding: drawer
pre-confirmation `--danger` exception only applies when modal
confirmation gates the mutation. UI-11's drawer Adjust button
lives one click away from the modal; the alias scope holds
(documented in `modal.css` already).

### 5.2 · Modal primitive — already exists

`.modal` from UI-10 is the primitive UI-11 reuses verbatim.
The dropdown / radio inside the modal is a NEW micro-element:

```text
.modal-trust-options    fieldset, no border, padding 0.
.modal-trust-option     label + radio + level number +
                        one-line description. Stacked
                        vertically with --space-3 gap.
.modal-trust-option:hover  --bg-2 background wash.
.modal-trust-option:checked-within  --accent text + outline.
```

These are scoped under `.modal` so they cannot leak to the
rest of the surface.

### 5.3 · Motion (delta vs UI-10 §5.3)

No new motion. Modal slide-in reuses UI-10's contract.
Reduced-motion contract identical.

### 5.4 · The crow

No new state. The five existing states cover UI-11+. A
trust adjust does NOT change the crow's display because the
gradient is operator-set, not bus-driven.

## 6 · Roadmap (chunk-by-chunk)

```text
UI-11a  Trust gradient READ display.
          - GET /api/agents -> [{name, trust_level, handles}]
          - HTTP shape lock for GET in same PR.
          - data.action surfaced in _project_event (pin
            §0.5.5 binding) + EVENTS_PROJECTION_KEYS update.
          - Drawer extension: when the open event is an
            agent_response, show "trust_level: N" alongside
            the existing JSON body. Read-only; no
            affordance to mutate yet.
          - 1 PNG (drawer with trust visible).
          - No .webm (no motion change).

UI-11b  Trust gradient WRITE affordance.
          - POST /api/agents/{name}/trust -> 204
          - Drawer extension: "Adjust" button alongside the
            trust_level display. Click opens .modal with
            the three-radio gradient picker.
          - .modal-trust-* micro-elements.
          - JS handler: openTrustModal / confirmTrustAdjust.
          - Esc precedence: same as UI-10 (modal first,
            drawer second).
          - 4 Playwright tests (cancel + confirm + esc +
            backdrop) per UI-10 pattern.
          - 4-5 PNGs + 1 .webm walking the full flow.
          - HTTP shape locks for POST.
          - docs/event-schema.md additive section for the
            trust_adjust action.

UI-12   Push notifications. (Out of THIS brief; earns its
          own brief because push UX has its own opt-in /
          unsubscribe / privacy surface.)

UI-13+  (out of scope here.)
```

## 7 · Audit cadence (escalated for write paths)

Every UI-11* PR MUST include everything UI-0 §7 + UI-10 §7
already required, PLUS:

```text
For UI-11a (read-only):
  1. PNG of the drawer with trust_level visible.
  2. HTTP shape lock for GET /api/agents.
  3. EVENTS_PROJECTION_KEYS update covering data.action so
     the projection contract is pinned BEFORE UI-11b's
     timeline visuals depend on it.

For UI-11b (write):
  1. PNGs for: drawer with Adjust button, modal default,
     modal with reason typed, modal reduced-motion, post-
     adjust drawer reflecting the new trust value.
  2. .webm walking click → modal → confirm → result. Pin
     #5 from UI-3 audit (full-shell context >= 1024×640)
     carries forward.
  3. HTTP shape locks for POST.
  4. Bus event schema diff in PR body. data.trust_before /
     data.trust_after / data.agent / data.reason all
     documented in docs/event-schema.md in the same PR.
  5. Confirmation-flow regression test: Playwright
     cancel + confirm + Esc + backdrop, asserting that
     cancel does NOT mutate the bus (mirror of UI-10
     test_ui_modal.py).
```

## 8 · Frozen contracts (UI-11 MUST respect)

Same as UI-10 §8 + the additive UI-10 schema:

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol — all frozen.
- The bus event schema (additive only; UI-11's trust adjust
  fields are additive on human_decision).
- The /api/events / /api/health / /api/meta / /api/scars
  projection shapes pinned by tests/test_ui_server_http.py.
  Any new field on the projection requires an
  EVENTS_PROJECTION_KEYS update in the SAME PR (pin
  §0.5.5).
- The SW fetch handler ordering from UI-8 (FIRST-BRANCH
  /api/* network-only). Any new POST endpoint sits inside
  /api/* and is therefore network-only by construction.
- The Lighthouse threshold contract (Performance 85,
  Accessibility 95, Best Practices 95, SEO 90) with the
  variance window documented post-UI-10.
- The 34 binding pins from UI-2..UI-10.
```

## 9 · Out of scope for THIS brief

```text
- Live mutation of the running adapter's trust_level
  attribute. UI-11 emits intent; the operator restarts
  karasu watch (or a later chunk earns the live-mutation
  path).
- Authentication / authorization. UI-11 ships local-only.
- Push notifications. UI-12 concern.
- Batch trust adjust. UI-12+ concern.
- New crow state. The five existing states cover UI-11.
- A "trust history" surface (showing past adjustments).
  The bus IS the audit log; if a future chunk wants a
  filtered history view, it earns its own brief.
- Multi-operator collaboration / per-user trust. UI-13+.
- Setting trust_level above 2. The dropdown caps at 2.
```

## 10 · Open questions (operator sign-off needed)

All §3 decisions need confirmation. Plus:

```text
1. Trust value descriptions for the modal:
   PROPOSAL — sourced verbatim from docs/local-dogfood.md
   "Trust gradient — what trust_level actually does in
   production":
     0 = quarantined (no autonomous mutation; agent only
         responds to direct operator approval)
     1 = assistive (agent runs but does NOT mutate; output
         is a suggestion the operator applies)
     2 = autonomous (agent mutates the working tree without
         per-call approval; the gradient pin / startup
         warning gate this)
   If the doc has different wording, the brief uses THE
   DOC, not this proposal.
   [CONFIRMED 2026-05-05]

2. Which agents the surface lists:
   PROPOSAL — every adapter in the running config (read
   from `karasu.yaml.agents`). The config is the canonical
   source; whatever cmd_watch instantiates is what UI-11
   shows. If an agent is configured but its module fails
   to import, list it with `trust_level: null` and a note
   ("not loadable") rather than hiding it.
   [CONFIRMED 2026-05-05]

3. Does the UI server READ from karasu.yaml directly, or
   does it ONLY surface what `cmd_watch` already
   instantiated?
   PROPOSAL — read karasu.yaml directly. The UI server is
   already a separate process; cross-process state sharing
   adds complexity. The config IS the contract — even if
   `karasu watch` has not been started, `karasu ui`
   should still list the configured adapters.
   [CONFIRMED 2026-05-05]

4. POST validation:
   PROPOSAL —
     - {trust_level: int} — required.
     - 0 <= trust_level <= 2 (matches the modal's range).
     - 422 on invalid type / out of range.
     - 404 on unknown agent name.
     - 4 KiB body cap (same as UI-10 revoke).
   [CONFIRMED 2026-05-05]

5. data.action backwards compatibility:
   The /correct + /scar Telegram path emits human_decision
   with data = {user, text}. Pre-UI-10 events do NOT have
   data.action. UI-11a's _project_event addition must
   handle the field's absence:
   PROPOSAL — projection returns data.action verbatim
   when present, None when absent. Timeline / drawer
   consumers branch on the action value; the missing
   action is treated as the legacy Telegram-style
   human_decision (same display as today).
   [CONFIRMED 2026-05-05]

6. Modal close UX with Esc:
   PROPOSAL — same as UI-10 §10.6. First Esc closes
   modal. Second Esc closes drawer.
   [CONFIRMED 2026-05-05]
```

## 11 · Definition of "done"

### UI-11a

```text
- One PR, ~250 LOC including tests.
- GET /api/agents endpoint with HTTP shape lock.
- _project_event surfaces data.action; EVENTS_PROJECTION_KEYS
  updated; tests pinned.
- Drawer extension: trust_level visible on agent_response
  events.
- 1 PNG of the drawer.
- docs/event-schema.md additive section if the projection
  documentation needs an update.
- Codex audit returns APPROVED or APPROVED-with-observations.
```

### UI-11b

```text
- One PR, ~400 LOC including tests + the new endpoint.
- POST /api/agents/{name}/trust + 204 on success.
- HTTP shape locks pinned in the same PR.
- .modal-trust-options + .modal-trust-option styles in
  modal.css (additive).
- Drawer extension: Adjust button alongside trust_level.
- JS: openTrustModal + confirmTrustAdjust + wireTrustModal.
- Playwright cancel + confirm + esc + backdrop tests.
- 4-5 PNGs + 1 .webm walking the full flow.
- docs/event-schema.md updated with trust_adjust fields.
- Lighthouse re-run after the chunk lands; thresholds
  unchanged from UI-10 baseline (variance window honoured).
- Codex audit returns APPROVED or APPROVED-with-observations.
```

## 11.6 · Implementation pins (will be filled by Codex audit)

This section is intentionally empty in the DRAFT. After
Codex audits the brief and operator sign-off lands on §3 +
§10, this section will carry the implementation pins (like
§11.6 of the UI-10 brief did).

## 12 · Status

```text
Brief status:        CONFIRMED (operator sign-off complete
                     2026-05-05 on every §3 + §10 decision).
Operator sign-off:   COMPLETE (2026-05-05).
Codex audit:         PENDING (out-of-band via ChatGPT).
Implementation:      BLOCKED on the brief merging.
```

The brief mirrors the lifecycle `ui-10-design-brief.md` went
through (PR #83): operator sign-off + Codex audit + follow-ups
all landed on the same branch before the merge, so the
binding contract is in `main` before UI-11a opens.
