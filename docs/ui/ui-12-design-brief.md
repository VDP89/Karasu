# Karasu UI — UI-12 Design Brief (push notifications)

> Doc-only seal of the visual + structural direction for UI-12.
> Audited and merged BEFORE any code chunk opens.
> Parallel to `ui-0-design-brief.md` (UI-1..UI-9 read-only MVP),
> `ui-10-design-brief.md` (UI-10 scar revoke), and
> `ui-11-design-brief.md` (UI-11 trust adjust). Every UI-N
> chunk after this one (N == 12) executes against the
> decisions recorded here.
>
> **STATUS:** DRAFT — operator sign-off pending on §3 + §10
> proposals. Codex audit pending out-of-band post sign-off.
> Open questions in §10 are NOT pre-decided; the document
> lists default proposals so the operator and Codex have a
> concrete shape to ratify or amend.

## 0 · Why this brief exists

Codex pin #1 from the UI-9 audit (PR #81), reaffirmed by the
UI-10 audit (PR #85) and the UI-11 audit (PR #87):

> *"UI-N+ that introduces write paths must earn a new brief
>  before code."*

UI-10 + UI-11 opened two write paths inside the surface
(scar revoke, trust adjust). Both shipped drawer-earned,
modal-gated, intent-only, and emitting auditable
`human_decision` events. UI-12 introduces a **third**
distinct write surface — the operator subscribes the browser
to receive push notifications from Karasu when the bus
crosses an attention threshold.

This is qualitatively different from UI-10 / UI-11:

```text
1. The mutation is browser-state, not bus-state. A push
   subscription is a PushSubscription object owned by the
   browser's push service (FCM / APNs / Mozilla autopush).
   Karasu stores its endpoint to send to it later, but the
   "subscribed-or-not" truth lives in the browser, not the
   bus.

2. The surface gains an outbound channel. Up to UI-11 the
   UI was strictly request/response: the operator polled,
   the operator clicked, the operator typed. UI-12 lets
   Karasu reach out to a notification tray that the
   operator may not even have the surface open to read.
   This is the first proactive surface contract.

3. The opt-in is global, not per-event. Scar revoke and
   trust adjust are verbs against a specific drawer-open
   event. "Subscribe to notifications" is not — it has no
   natural anchor inside the existing watchtower drill-in
   pattern.

4. The implementation touches static/sw.js, which UI-8
   audit pins froze. Any addition has to be earned here
   explicitly.

5. Web Push protocol requires VAPID-signed requests, which
   require ECDSA P-256 signing. UI-0 §4 forbids new build /
   framework / runtime dependencies; this brief must either
   negotiate that constraint, defer server-side emission to
   a later chunk, or split the work so the dep lives behind
   an opt-in code path.
```

The 52 binding pins + 12 UI-11 §11.6 implementation pins +
6 UI-10 §0.5 audit pins (70 total) all carry forward. This
brief does NOT supersede them; it adds the structural
contracts UI-12 needs on top.

## 0.5 · Pins inherited from UI-11 audit

Codex pinned 12 rules on UI-11 (PR #87, 2026-05-05). Every
one applies to UI-12 verbatim, with the relevant subset
called out below because they shape this brief's proposals:

```text
1. Read-before-write split is mandatory for any write path
   (UI-11 §11.6.1, paraphrased). UI-12 inherits: the
   read-only "subscription state visible on the surface"
   chunk ships before the "operator subscribes / unsubs /
   Karasu emits a push" chunk.

2. Projection contract additions land in the SAME PR as
   the visual that depends on them (UI-11 §11.6.2). UI-12
   inherits: if any new field surfaces on /api/health or
   /api/meta to expose subscription state, the shape lock
   updates in the same PR.

3. Read-paths must work without karasu watch running
   (UI-11 §11.6.3). UI-12 inherits: subscription state is
   readable from the surface alone — no IPC to a running
   watcher, no adapter-instance reach-through.

4. Documented enums are the contract; surface unsupported
   values as read-only rather than coercing (UI-11 §11.6.4).
   UI-12 inherits: the notification categories enum is
   fixed; unknown / out-of-range categories on disk are
   surfaced read-only with an "unsupported" tag, never
   silently coerced.

5. Intent-only is the default for any chunk that crosses
   process boundaries (UI-11 §11.6.5). UI-12 inherits: any
   server-side state the running watcher would need to
   read at next start (e.g. a "send pushes from now on"
   flag) is intent-only; the running watcher is not
   expected to live-mutate.

6. Drawer-earned by default (UI-11 §11.6.6). UI-12
   negotiates an exception in §3-A below — push opt-in
   has no agent_response anchor — but the burden is on
   THIS brief to earn the exception.

7. Modal mandatory for trust-changing mutations (UI-11
   §11.6.7). UI-12 inherits: subscription opt-in is gated
   by an explicit confirmation step; no drive-by
   "subscribed because you opened the page" flow.

8. CSS scope discipline (UI-11 §11.6.8). UI-12 inherits:
   any new push-related styles are scoped under their own
   primitive (.push-* or .modal-push-*) and must not leak
   into timeline rows, map nodes, drawer scar rows, or
   trust-adjust modals.

9. Every write emits a human_decision (UI-11 §11.6.9).
   UI-12 inherits: subscribe / unsubscribe events emit
   human_decision with a fixed data.action value
   ("push_subscribe" / "push_unsubscribe" — see §3-D).

10. POST 204 still requires a visible drawer / surface
    refresh (UI-11 §11.6.10). UI-12 inherits: post-confirm
    the surface visibly reflects the new subscription
    state.

11. Playwright covers cancel + confirm + esc + backdrop
    + reason trimming (UI-11 §11.6.11). UI-12 inherits
    cancel / confirm / esc / backdrop; "reason" is not in
    the push subscribe modal scope.

12. .webm reads as deliberate operator intent, not as a
    settings panel (UI-11 §11.6.12). UI-12 inherits — the
    recording must show the operator drilling into the
    push opt-in deliberately, with a clear motive
    surfaced by the surrounding watchtower context.
```

Pin §0.5.6 is the binding negotiation point for this brief.
See §3-A.

## 1 · Positioning

UI-1..UI-11 was the watchtower the operator looks AT. UI-12
is the watchtower whispering BACK — but only when the
operator earned a whisper, only when the bus crosses a
threshold the operator opted in to, and never when the
operator did not deliberately ask to be reached.

> A push notification is the surface refusing silence at a
> specific moment the operator agreed in advance is worth
> breaking quiet for. Karasu does NOT auto-subscribe, does
> NOT prompt on first visit, does NOT show install banners
> or upgrade toasts (UI-8 audit pin #5 binding). The
> notification permission prompt is a verb the operator
> earns by deliberately opting in.

The first second of looking at the UI before AND after UI-12
must read identical. The opt-in affordance is dormant chrome
at most — it does not float, does not pulse, does not nudge.
It lives in a single, quiet place the operator can find when
they want it and ignore otherwise.

When a push DOES fire, the notification copy stays editorial:
single sentence, no badges, no count, no emoji. The body
matches the watchtower's voice — "Karasu paused on a
classifier rule" beats "1 new event!".

## 2 · Visual references (anchors held)

Same anchors as UI-0 §2, UI-10 §2, UI-11 §2:

```text
linear.app          notification settings adjacent to context;
                    the inbox is a destination, not a sidebar
                    interrupt.
vercel.com          notification opt-ins are inline copy +
                    explicit verb, never auto-prompts.
stripe.press        attention through copy + spacing, not
                    chrome.
```

Anti-patterns (UI-0 §4 + UI-8 audit pin #5 still binding):
Material defaults / Tailwind defaults / component-library
chrome / install banners / update toasts / connection badges
all forbidden.

## 3 · Proposed decisions (operator sign-off pending)

All decisions below are PROPOSALS. The operator may accept,
amend, or reject; Codex audits the resulting set before any
UI-12 code branch opens.

```text
A) Surface for the push opt-in affordance:
   PROPOSAL — single footer affordance, QUIET TEXT ONLY,
   never a CTA. The UI-3 footer row already carries
   version + last-event-time + crow state. UI-12 adds a
   fourth slot: a quiet text affordance showing the
   current push state ("Notifications: off" /
   "Notifications: on") that, when clicked, opens a .modal
   (UI-10 primitive reused) listing the categories.
   Codex P2 binding (2026-05-05): the affordance MUST NOT
   be a banner, a badge, a toast, a re-prompt nudge, or
   visually weighted as a call-to-action. Pre-opt-in
   weight is identical to a build-version line; post-opt-
   in weight uses --accent ONLY on the "on" word, never
   on the entire affordance. Codex Q1 verdict: footer
   accepted as the burden-earned exception to pin §0.5.6
   provided the no-CTA constraint holds.
   Rationale: push opt-in has no per-event anchor, so it
   cannot be drawer-earned. The footer is the quietest
   global slot already established by UI-3 — quieter than
   the header, quieter than a dedicated /push page, quieter
   than a toolbar entry. This negotiates an explicit
   exception to pin §0.5.6 (drawer-earned by default).
   ALTERNATIVES considered:
     - Drawer-earned on the first agent_response that
       would have triggered a push (rejected: too clever;
       the operator may never have seen such an event).
     - /push or /settings page (rejected: introduces a
       second surface mode; UI-0 §1 single-pane discipline
       carries forward).
     - Header toolbar entry (rejected: pin §0.5.6 carry-
       forward; header chrome stays clean).
     - Auto-prompt on first visit (rejected: pin §0.5.7
       modal-mandatory + UI-8 pin #5 no-banners; auto-
       prompts violate the editorial restraint anchor).
   [PROPOSAL — operator sign-off pending]

B) Confirmation flow:
   PROPOSAL — Modal overlay, .modal primitive (UI-10).
   Click the footer affordance → .modal opens with the
   three categories (one row per category, checkbox each)
   + a single "Enable notifications" button. Confirming
   triggers the browser's native permission prompt
   (Notification.requestPermission) THEN, if granted,
   PushManager.subscribe(). Cancel / Esc / backdrop close
   the modal without invoking the browser prompt.
   The native permission prompt is part of the flow; the
   modal is the FRICTION before the browser prompt fires
   so the operator does not see a permission dialog they
   did not deliberately request.
   [PROPOSAL — operator sign-off pending]

C) Authentication:
   PROPOSAL — None for UI-12. Same as UI-10 + UI-11:
   surface is operator-local (127.0.0.1). A future
   deployed surface earns its own auth design + its own
   brief (UI-13+).
   [PROPOSAL — operator sign-off pending]

D) Bus event schema for push subscribe / unsubscribe:
   PROPOSAL — Reuse `human_decision` (no new event type)
   with two action values:
     data.action          = "push_subscribe"
     data.endpoint_hash   = <SHA-256 of subscription
                            endpoint, hex-encoded; the
                            raw endpoint URL is sensitive
                            and is NOT placed on the bus>
     data.categories      = ["attention", "errors",
                            "corrections"] (subset of the
                            three documented categories;
                            see §3-G)
   For unsubscribe:
     data.action          = "push_unsubscribe"
     data.endpoint_hash   = <same hash as the prior
                            subscribe event for this
                            subscription>
   Same additive pattern UI-10 (scar_revoke) and UI-11b
   (trust_adjust) used. Pre-UI-10 consumers ignore these
   events as before.
   The full subscription object (endpoint URL, p256dh +
   auth keys) lives in the push subscription store
   (§3-F), NOT on the bus, because the bus is replayable
   and shareable while subscription keys are sensitive.
   Codex P1 binding (2026-05-05): endpoint_hash is
   permitted ONLY as audit metadata on human_decision
   events. It is NOT a functional identifier. Forbidden
   uses, all binding:
     - NOT exposed on /api/* responses other than the
       /api/events projection of human_decision events.
     - NOT used as the lookup key inside the push store
       (§3-F). The store keys subscriptions by their raw
       endpoint URL (or an internal opaque id); the hash
       exists for bus correlation only.
     - NOT correlated with file_change, agent_response,
       or any non-human_decision event.
     - NOT exposed via /api/push response bodies.
   Raw PushSubscription fields (endpoint URL, p256dh,
   auth) NEVER appear on the bus under any circumstance.
   [PROPOSAL — operator sign-off pending]

E) Server endpoints for push:
   PROPOSAL —
     GET  /api/push                returns
                                   {state: "supported"|
                                          "unsupported"|
                                          "denied",
                                    categories: [...],
                                    subscription_count: int,
                                    vapid_public_key: str?}
     POST /api/push/subscribe      body: PushSubscription
                                   JSON + selected categories
                                   → 204 + emits
                                   human_decision
                                   (push_subscribe). Stores
                                   subscription in the
                                   push store (§3-F). 4 KiB
                                   body cap.
     POST /api/push/unsubscribe    body: {endpoint: "<url>"}
                                   (the browser still
                                   holds the
                                   PushSubscription and
                                   supplies its endpoint).
                                   Server matches the
                                   in-store subscription
                                   by endpoint URL,
                                   removes it, hashes the
                                   endpoint internally
                                   ONLY to populate the
                                   bus event's
                                   data.endpoint_hash for
                                   audit correlation.
                                   → 204 + emits
                                   human_decision
                                   (push_unsubscribe).
                                   The endpoint_hash from
                                   §3-D is NOT a body
                                   field on this endpoint
                                   (Codex P1 binding —
                                   hash is not a store
                                   lookup key).
   GET /api/push reads the push store directly, the same
   way GET /api/agents reads karasu.yaml directly. Same SW
   network-only contract holds (api/* never cached).
   The vapid_public_key field is the server's VAPID public
   key in raw URL-safe base64; the client subscribes
   PushManager.subscribe() with this key as
   applicationServerKey. The private half NEVER appears
   in any /api/* response.
   [PROPOSAL — operator sign-off pending]

F) Persistence — push subscription store:
   PROPOSAL — separate JSON file alongside the bus, path
   configurable via `karasu ui --push-store <path>`
   (defaults to `karasu-push.json` next to events.jsonl).
   File shape (top-level keys explicit; vapid +
   subscriptions are independent sections within ONE
   file per Codex P1 — same-file is acceptable provided
   the sections are normalised separately):
     {
       "vapid": {"public": "<b64u>", "private": "<b64u>"},
       "subscriptions": [
         {
           "endpoint": "<full url>",
           "endpoint_hash": "<sha256-hex; cached for
                              bus emission, NOT used as
                              store lookup>",
           "keys": {"p256dh": "<b64u>", "auth": "<b64u>"},
           "categories": ["attention", "errors"],
           "created_at": "<iso8601 utc>"
         },
         ...
       ]
     }
   Codex P1 binding (2026-05-05) — the file is a
   PRIVATE STORE. The following constraints are pinned:
     - Mode 0600 on POSIX. The PR creating the file
       path emits a loud-stderr warning if the parent
       directory is world-readable (mirrors UI-11
       trust-gradient warning pattern).
     - NEVER bus-replayed. The store is not an event
       stream and does not participate in /api/events.
     - NEVER surfaced in /api/* projections (except
       /api/push, and even there only the
       subscription_count and the vapid_public_key —
       no individual subscription contents).
     - NEVER captured in screenshots / .webm / docs.
       UI-12b's PNG / .webm capture seeds use a
       throwaway store and assert no endpoint or key
       material appears in the rendered surface.
     - NEVER committed to git. The path defaults
       alongside events.jsonl, which is already
       gitignored; the brief reaffirms the same
       discipline for the push store.
   VAPID keys are generated on first server start if the
   file is absent (the dep gap in §10.5 gates whether
   first-start can do this with stdlib alone). The store
   is operator-local; it is NOT in karasu.yaml because
   subscriptions are not configuration — they are runtime
   state owned by browsers the operator opted in from.
   ALTERNATIVES considered:
     - karasu.yaml (rejected: not configuration).
     - The bus itself, event-sourced (rejected: keys
       belong off the bus; replayable streams should not
       carry sensitive material).
     - SQLite (rejected: introduces a stateful dep where
       a flat JSON suffices; UI-0 §4 minimalism).
   [PROPOSAL — operator sign-off pending]

G) Notification categories (fixed enum):
   PROPOSAL — three categories, each opt-in independently
   in the modal:
     attention   — agent_response with requires_human=True,
                   OR a file_change that the controller cap
                   would block (chain depth at limit).
     errors      — agent_response with status="failed".
     corrections — human_decision originating from a source
                   other than "ui" (i.e. Telegram /scar or
                   /correct, or a future inbound surface).
                   The UI's own writes (scar_revoke,
                   trust_adjust, push_subscribe,
                   push_unsubscribe) DO NOT trigger this
                   category — pushing the operator's own
                   click back to them is noise.
                   Codex P1 binding (2026-05-05): the
                   UI-originated-write exclusion is a
                   first-class implementation pin
                   (§11.6.9), not an aside. The UI-12c
                   emit path MUST filter on
                   source != "ui" before any push
                   dispatch in this category.
   The enum is closed for UI-12. Future categories earn
   their own brief.
   Unsupported categories on disk (e.g. "broadcast") are
   surfaced read-only with an "unsupported" tag in
   GET /api/push (pin §0.5.4 carry-forward).
   [PROPOSAL — operator sign-off pending]

H) Notification copy (server-side):
   PROPOSAL — single editorial line per category. No body
   beyond the title. Title format:
     attention   "Karasu paused — operator review needed."
     errors      "An adapter failed."
     corrections "A scar was recorded out-of-band."
   data field: {url: "/", category, event_id} so the
   notificationclick handler navigates back to the
   surface focused on the relevant event.
   icon / badge: the canonical crow asset (UI-5)
   192px PNG (already precached for the manifest).
   Tag: "karasu" (singular tag; new pushes replace
   pending ones rather than stacking — operator gets
   the latest pulse, not a notification queue).
   [PROPOSAL — operator sign-off pending]

I) sw.js delta (UI-8 frozen-pin negotiation):
   PROPOSAL — additive only:
     - New 'push' event listener. Reads event.data.json(),
       calls registration.showNotification with the copy
       from §3-H. Does NOT touch the fetch handler
       ordering.
     - New 'notificationclick' event listener. Closes the
       notification, focuses an existing client at the
       surface URL, or opens a new one if none exists.
       Does NOT touch the fetch handler ordering.
     - CACHE_NAME bumps from karasu-ui-v8 to karasu-ui-v12
       per the bump rule in sw.js's header comment (the
       file changed).
   The fetch handler ordering (api/network-only →
   navigate-or-offline → cache-first) is the contract and
   does NOT move. The push + notificationclick listeners
   are independent SW event types; they cannot interfere.
   Codex P0 binding (2026-05-05): the additive claim is
   NOT auditable from diff alone. UI-12b MUST ship a
   shape-lock test that exercises the fetch handler with
   three request shapes and asserts the routing decision
   for each:
     - GET /api/anything → network only (cache miss MUST
       NOT serve a stale response; cache hit MUST NOT
       short-circuit the network request).
     - navigate request to / → network first, fall back
       to /offline.html on rejection.
     - GET /assets/* → cache-first (cache hit serves
       without hitting network; cache miss falls through
       to network).
   The test lives in tests/test_ui_sw.py (or equivalent
   Playwright route-stub setup); it MUST pre-date and
   gate the merge of UI-12b. Any future SW chunk
   re-runs this test as the UI-8 fetch-ordering
   regression gate.
   [PROPOSAL — operator sign-off pending]

J) Single chunk or multi:
   PROPOSAL — three chunks:
     UI-12a — read display + dep negotiation.
              GET /api/push (state + count + vapid public
              key, no subscribe path yet). Footer
              affordance shows current state. NO modal.
              NO sw.js push handler. Earns the dep
              decision in §10.5 IF needed for VAPID key
              generation; otherwise punts the dep to
              UI-12c.
              ~250 LOC.
     UI-12b — opt-in surface + subscription persistence.
              POST /api/push/subscribe + /unsubscribe,
              modal, JS handler, sw.js push handler stub
              (registers the listener but does NOT yet
              receive pushes because no server-side
              emission exists). Categories selectable.
              human_decision events emitted. Playwright
              cancel + confirm + esc + backdrop tests.
              ~400 LOC.
     UI-12c — server-side emit (the actual push path).
              The watcher / loop controller subscribes to
              the bus; on a category-matching event, it
              dispatches a Web Push request to every
              opted-in subscription for that category.
              VAPID JWT signing, dep gap negotiated here
              (see §10.5). subscription pruning on 410
              (browser unsubscribed). ~400 LOC.
   Reason: UI-10 hit ~3000 LOC; pin §0.5.6 / UI-11 §11.6
   binding asks for splits when feasible. UI-12c is the
   chunk that introduces the runtime dep (if §10.5
   negotiates it in); separating it from the surface
   chunks keeps the dep audit isolated.
   [PROPOSAL — operator sign-off pending]
```

## 3.5 · Operator pin (binding when sign-off lands)

Anticipated pin paralleling UI-10 §3.5 + UI-11 §3.5 — adjust
per operator direction:

```text
Push UX must read as the operator deliberately enabling a
quiet hand-on-shoulder, not as Karasu colonising the
operating system's notification tray. Three felt
properties:
  1. Quiet by default — the surface before opt-in is
     identical to today's. No banner, no toast, no nudge,
     no first-visit prompt.
  2. Editorial copy — every notification is one sentence
     in the watchtower's voice. Failure to hold the line
     here turns Karasu into a notification spam source
     and breaks the marketing-as-product anchor.
  3. Reversible from the same place — the unsubscribe
     verb lives in the same modal as subscribe, on the
     same footer affordance. Operators do not hunt for
     opt-out flows in OS settings.
```

How this pin shapes UI-12 implementation if accepted:

```text
- "Quiet by default" → no install / update / connection /
  notification banners. The footer slot is the only
  surface change pre-opt-in; "Notifications: off" is the
  same visual weight as "build: 0.3.x".
- "Editorial copy" → §3-H copy is the contract. Codex
  audits the .webm AND the localised pushes; deviations
  fail audit.
- "Reversible from the same place" → the modal is
  category-stateful; opening it post-subscribe shows the
  current categories + a clear "Unsubscribe" verb at the
  bottom. NOT a separate UI; not a separate flow.
- The operator-feel test: when Victor (or any operator)
  hits the footer affordance for the first time, the
  click should feel like opening a quiet preferences
  pane that ASKS before it pings them, not like
  installing an app that demands permission to keep
  itself relevant.
```

## 4 · Tech stack (delta vs UI-0 §4)

UI-0 §4 still holds. UI-12 deltas:

```text
- The server gains three handlers (GET /api/push, POST
  /api/push/subscribe, POST /api/push/unsubscribe). All
  reuse the same stdlib HTTP plumbing as UI-10 +
  UI-11b's POST handlers.
- The server gains a push subscription store (a JSON
  file at a configurable path; default
  `karasu-push.json` next to the bus). No SQLite, no DB
  driver.
- sw.js gains 'push' + 'notificationclick' event
  handlers (additive; fetch handler ordering unchanged).
  CACHE_NAME bump per the file's documented rule.
- Frontend gains push.js — vanilla module under
  static/js/, registers the SW push subscription, opens
  the modal, calls the subscribe / unsubscribe endpoints.
- DEPENDENCY GAP — Web Push protocol requires VAPID
  signing (ECDSA P-256). Stdlib has no ECDSA. UI-12c
  needs either the `cryptography` package (smaller pill,
  pure-Python wheels everywhere) OR `pywebpush` (turn-
  key Web Push including VAPID). UI-0 §4 forbids new
  build / framework / runtime dependencies; this is the
  binding negotiation in §10.5. UI-12a + UI-12b ship
  WITHOUT the dep — the SW handler is registered but
  the server emits nothing until UI-12c lands.
- No new build / framework / runtime dependency on the
  frontend.
```

## 5 · Design system (delta vs UI-0 §5 + UI-10 §5 + UI-11 §5)

### 5.1 · Reuse, do not invent

Tokens: same. UI-10's `--danger` alias is unchanged. UI-11's
`.modal-trust-*` micro-elements are unchanged. The push
modal introduces NEW micro-elements scoped under .modal per
pin §0.5.8.

### 5.2 · Modal primitive — already exists

`.modal` from UI-10 is the primitive UI-12b reuses verbatim.
Push-specific micro-elements:

```text
.modal-push-categories     fieldset, no border, padding 0.
.modal-push-category       label + checkbox + category name +
                           one-line description. Stacked
                           vertically with --space-3 gap.
.modal-push-category:hover  --bg-2 background wash.
.modal-push-category:has(:checked)  --accent text + outline.
.modal-push-state          single-line state row
                           ("Notifications: on, 2 categories")
                           rendered above the categories
                           when the operator is already
                           subscribed.
.modal-push-unsubscribe    secondary button at the modal
                           foot, only rendered when the
                           operator is currently subscribed.
                           --fg-2 weight (NOT --danger —
                           unsubscribing is reversible
                           per §3.5).
```

Scoped under `.modal` per pin §0.5.8.

### 5.3 · Footer affordance

The footer row gains one slot:

```text
.footer-push          inline text affordance, --fs-12
                      mono, --fg-2 default. Hover →
                      --fg-1. Focus ring same as design
                      system.
.footer-push.is-on    --accent on the "on" word only
                      (not the entire affordance — the
                      crow's voice carries the colour;
                      footer chrome stays neutral).
.footer-push.is-denied  --warn on the "denied" word
                        with no click handler (the
                        operator denied the OS prompt;
                        re-enabling is OS-level).
```

### 5.4 · Motion

No new motion. Modal slide-in reuses UI-10's contract.
The footer affordance has NO state-transition animation —
state changes by class swap, no keyframe.

### 5.5 · The crow

No new state. The five existing states cover UI-12. A
push subscribe / unsubscribe does NOT change the crow's
display because the operator is acting on browser state,
not bus state.

### 5.6 · Notification visuals (tray-side)

The notification card is rendered by the OS, not by
Karasu's CSS. The shape Karasu controls:

```text
title         §3-H copy, single line per category.
body          empty. The OS will fall back to showing
              just the title.
icon          /assets/icons/karasu-192.png (already
              precached).
badge         same icon (Android tray badge).
tag           "karasu" (single tag — new pushes replace
              pending ones).
data          {url, category, event_id}.
silent        false (default).
requireInteraction  false (default; the OS dismisses
                    after its standard timeout).
```

The OS chrome around the notification is OUTSIDE Karasu's
design system; the marketing-as-product anchor cannot
override the OS notification template.

## 6 · Roadmap (chunk-by-chunk)

```text
UI-12a  Push read display + dep negotiation.
          - GET /api/push -> {state, categories,
            subscription_count, vapid_public_key?}
          - HTTP shape lock for GET in same PR.
          - Footer affordance shows current state read
            from the endpoint. No modal.
          - sw.js NOT touched in this chunk.
          - Push subscription store path resolved
            (default + --push-store flag); empty store
            on first start; VAPID keys NOT generated
            until the dep gap is resolved (§10.5) OR
            UI-12c.
          - 1 PNG (footer with "Notifications: off").
          - No .webm (no motion change).
          - Codex audit returns APPROVED or APPROVED-
            with-observations.

UI-12b  Push opt-in surface + subscription persistence.
          - POST /api/push/subscribe -> 204 + emits
            human_decision (push_subscribe).
          - POST /api/push/unsubscribe -> 204 + emits
            human_decision (push_unsubscribe).
          - Modal opens from the footer affordance.
          - .modal-push-* micro-elements.
          - JS handler: openPushModal /
            confirmPushSubscribe / confirmPushUnsubscribe.
          - sw.js gains 'push' + 'notificationclick'
            listeners (additive; fetch handler ordering
            unchanged). CACHE_NAME bump.
          - Fetch-ordering shape-lock test (Codex P0,
            §3-I) lands in this PR before sw.js is
            modified. Three-shape regression test as
            specified in §3-I.
          - VAPID public key surfaced via /api/push;
            the private key is generated AT MOST on
            first POST /api/push/subscribe (the chunk
            that needs it for client-side
            applicationServerKey). Server-side push
            EMISSION is still deferred to UI-12c, so
            the SW push handler receives no real
            traffic during UI-12b — the listener is
            registered for forward-compat.
          - Esc precedence: same as UI-10 + UI-11
            (modal first, drawer second, footer
            affordance third).
          - 4 Playwright tests (cancel + confirm + esc
            + backdrop) per UI-10 / UI-11 pattern.
          - Browser-permission dialog SIMULATION in
            Playwright tests via context.grantPermissions
            / clearPermissions. Real permission dialogs
            are not asserted — only the surface contract
            (cancel before native prompt, native prompt
            fired only after modal confirm).
          - 4-5 PNGs + 1 .webm walking the full flow.
          - HTTP shape locks for POST.
          - docs/event-schema.md additive section for
            push_subscribe + push_unsubscribe.

UI-12c  Server-side emit (the actual push path).
          - Watcher / loop controller subscribes to the
            bus; on a category-matching event, dispatches
            a Web Push to every opted-in subscription
            for that category.
          - VAPID JWT signing — DEP NEGOTIATION HAPPENS
            HERE. Either `cryptography` or `pywebpush`
            lands as a runtime dep, with operator + Codex
            sign-off captured in the chunk's PR body.
          - 410 / 404 handling: prune dead subscriptions
            from the store.
          - Rate-limit / anti-spam policy (Codex P1
            binding, 2026-05-05) — three layers, all
            mandatory:
              1. Event-id dedupe: each event id is
                 dispatched at most once per
                 subscription, regardless of category
                 reclassification or watcher restart
                 within the dedupe window. The
                 dispatcher persists the last N
                 dispatched event ids per subscription
                 in-memory (bounded ring; the store does
                 NOT persist this state — restart-cleared
                 by design).
              2. Per-category debounce: at most one push
                 per category per 5 s per subscription.
                 The debounce coalesces bursts; the
                 single push that fires carries the
                 most recent event in the burst window.
                 Configurable per category at the
                 server-side via a CLI flag or env var
                 (deferred to UI-12c PR review).
              3. UI-write suppression: events with
                 source = "ui" are NEVER dispatched as
                 pushes, regardless of category. Filter
                 applied before the event-id dedupe
                 layer so UI-write events do not consume
                 dedupe slots.
            The three layers compose: event-id dedupe
            inside per-category debounce inside UI-write
            suppression. UI-12c tests pin each layer
            independently AND in combination.
          - Tests: pytest unit + a Playwright test that
            asserts the SW push handler renders a
            notification when given a synthetic push
            payload (PushManager test fixture).
          - 1-2 PNGs (notification tray as captured by
            the OS / Playwright). 1 .webm of the full
            edge-to-edge flow (operator subscribes,
            operator triggers an event, push arrives,
            notification clicked, surface focuses).

UI-13+  (out of scope here. Anticipated: deployed
          surface + auth, A2A peer push fan-out, push
          rate budgets per category.)
```

## 7 · Audit cadence (escalated for write paths)

Every UI-12* PR MUST include everything UI-0 §7 + UI-10 §7
+ UI-11 §7 already required, PLUS:

```text
For UI-12a (read display):
  1. PNG of the footer affordance in "off" state.
  2. PNG of the footer affordance in "denied" state
     (synthetic — OS denial state simulated via
     Playwright permission API).
  3. HTTP shape lock for GET /api/push.
  4. Push store schema documented in PR body. The on-
     disk shape is the contract; operator can inspect
     it directly.

For UI-12b (write affordance):
  1. PNGs for: footer "off", footer "on", modal
     default, modal with categories selected, modal
     post-subscribe (with unsubscribe verb visible),
     modal reduced-motion.
  2. .webm walking footer click → modal → category
     select → confirm → native permission grant
     (granted via Playwright permission API) → modal
     close → footer "on" → modal reopen → unsubscribe
     → footer "off". Pin from UI-3 audit (full-shell
     context >= 1024×640) carries forward.
  3. HTTP shape locks for POST subscribe + unsubscribe.
  4. Bus event schema diff in PR body.
     data.endpoint_hash (NOT the raw endpoint),
     data.action, data.categories all documented in
     docs/event-schema.md in the same PR.
  5. Confirmation-flow regression test: Playwright
     cancel + confirm + Esc + backdrop, asserting that
     cancel does NOT mutate the bus or call
     PushManager.subscribe (mirror of UI-10 + UI-11b
     test_ui_modal pattern).
  6. sw.js diff isolated to push + notificationclick
     listeners; CACHE_NAME bump explicit. Codex P0
     binding (2026-05-05): a shape-lock test
     (tests/test_ui_sw.py or Playwright route-stub
     equivalent) MUST land in the same PR and pass on
     CI before the sw.js change merges. The test
     asserts three routing decisions: /api/* network-
     only, navigate → network-then-offline, /assets/*
     cache-first. Diff review is not the contract; the
     test is the contract.

For UI-12c (server-side emit):
  1. PR body documents the runtime dep choice
     (cryptography vs pywebpush), justifies the gap
     against UI-0 §4, includes operator sign-off.
  2. Tests covering: VAPID JWT generation, push
     dispatch, 410/404 pruning, rate-limit debounce,
     category gating (corrections from source="ui"
     are NOT pushed back to the operator), and the
     "no subscriptions → no work" path.
  3. .webm of the edge-to-edge flow.
  4. docs/local-dogfood.md updated with a new section
     on running with push enabled (VAPID key
     bootstrap, --push-store flag, dep install).
```

## 8 · Frozen contracts (UI-12 MUST respect)

Same as UI-11 §8 + the additive UI-11 schema:

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol — all frozen.
- The bus event schema (additive only; UI-12's
  push_subscribe / push_unsubscribe fields are additive
  on human_decision).
- The /api/events / /api/health / /api/meta / /api/scars
  / /api/agents projection shapes pinned by
  tests/test_ui_server_http.py. Any new field on the
  projection requires an EVENTS_PROJECTION_KEYS update
  in the SAME PR (UI-11 §11.6.2 carry-forward).
- The SW fetch handler ordering from UI-8 (FIRST-BRANCH
  /api/* network-only). UI-12's push + notificationclick
  listeners are SEPARATE SW event types and do not
  modify fetch ordering.
- The Lighthouse threshold contract (Performance 85,
  Accessibility 95, Best Practices 95, SEO 90) with the
  variance window documented post-UI-10 / post-UI-11.
- The 70 binding pins (52 brief pins + 12 UI-11 §11.6
  + 6 UI-10 §0.5).
- UI-8 audit pin #5 (no install banners, no update
  toasts, no connection badges) carries forward to
  cover "no first-visit notification prompt", "no
  notification opt-in toast", "no permission re-prompt
  badge".
```

## 9 · Out of scope for THIS brief

```text
- Deployed (non-localhost) push. UI-12 ships local-only;
  Web Push works on localhost without HTTPS. A future
  deployed surface earns its own brief covering HTTPS
  cert provisioning + auth + push fan-out at scale.
- Authentication / authorization. UI-12 ships local-only.
- Per-event push opt-in (e.g. "push me when THIS
  specific scar fires"). UI-12 categories are coarse;
  finer granularity earns its own brief.
- Notification scheduling / quiet hours / DND respect
  beyond the OS-level DND. UI-13+.
- Push from peers (A2A push fan-out). UI-13+.
- Push body content beyond the editorial title. The
  body is empty by design; richer payloads
  (correlation graph snippet, scar text excerpt) earn
  a future brief once the editorial-line discipline
  is dogfood-validated.
- Multi-device push fan-out beyond "subscribe N
  browsers, push to all of them". Not multi-operator;
  not per-user routing. UI-13+.
- iOS Safari quirks. iOS Safari Web Push exists from
  16.4+ but requires the surface installed as a Home
  Screen PWA. UI-12 documents the constraint; the
  surface degrades gracefully (state="unsupported")
  on browsers that report no PushManager. Codex P2
  binding (2026-05-05): unsupported environments
  degrade to a PASSIVE READ-ONLY status — the footer
  affordance reads "Notifications: unsupported", carries
  NO click handler, NO retry prompt, NO Home-Screen-
  install nudge, NO copy suggesting the operator
  upgrade their browser. Karasu does not insist; it
  reports the platform truth and stays silent. The
  same passive-read-only contract applies to denied
  permission state and to private-browsing contexts
  where PushManager is gated.
- Service worker push REPLAY (e.g. queueing pushes
  while offline). UI-12 fires-and-forgets to the push
  service; replay is the push service's concern.
```

## 10 · Open questions (operator sign-off needed)

All §3 decisions need confirmation. Plus:

```text
1. Notification categories — three, or fewer, or
   more?
   PROPOSAL — three (attention / errors / corrections).
   Rationale in §3-G. Two would conflate operator-
   review-needed with adapter-failure (different
   urgencies); four+ proliferates the modal without
   clear demand. The three are derivable from event
   shape so no per-event tagging is required.
   [PROPOSAL]

2. Default categories on first subscribe:
   PROPOSAL — all three pre-checked. Rationale: the
   operator who deliberately opted in has already
   crossed the "I want to be notified" threshold;
   forcing them to also pick which categories adds
   friction without obvious benefit. Categories are
   easily uncheckable in the same modal post-
   subscribe.
   ALTERNATIVE — "attention" only pre-checked; the
   other two opt-in. More conservative; ensures the
   operator deliberately picks each.
   [PROPOSAL — operator picks default]

3. Subscription store path default:
   PROPOSAL — `karasu-push.json` next to the bus
   (events.jsonl). Mirrors how the bus path is the
   anchor for everything operator-local.
   ALTERNATIVE — `~/.karasu/push.json` (per-user, not
   per-repo). More appropriate if the operator runs
   multiple Karasu instances against the same browser.
   [PROPOSAL — operator picks default; the --push-store
   flag covers the other case either way]

4. VAPID key rotation:
   PROPOSAL — none for UI-12. Keys generated once on
   first need; never rotated. Rotation invalidates
   every existing subscription (browsers tied
   subscriptions to the public key); operator must
   manually delete the store + re-subscribe every
   browser. Auto-rotation is a UI-13+ concern.
   [PROPOSAL]

5. Runtime dependency gap (UI-12c):
   This is THE binding decision. Web Push requires
   VAPID JWT signing, which requires ECDSA P-256.
   Python stdlib has no ECDSA. Options:

     a) Add `cryptography` as a runtime dep. Pure
        Python wheels available everywhere; widely
        audited; ~5 MB installed. Used for VAPID
        JWT only. Clean, surgical.
     b) Add `pywebpush` as a runtime dep. Wraps Web
        Push including VAPID; ~12 MB with deps
        (`cryptography` + `http_ece` + `requests`).
        Turn-key but less audit-able.
     c) Defer UI-12c indefinitely. Ship UI-12a +
        UI-12b only; the SW push handler is
        registered but never receives traffic
        because Karasu emits no pushes. Honest but
        incomplete — the surface promises a feature
        the server never delivers.
     d) Implement VAPID JWT signing without a dep,
        e.g. by shelling out to `openssl` for ECDSA
        signatures. Cross-platform (`openssl` is
        available on every supported OS); no Python
        dep. Ugly but matches the
        shutil-which-stdlib aesthetic of
        ClaudeCodeAdapter. The shelled-out binary
        becomes a runtime requirement instead.

   PROPOSAL — option (a). `cryptography` is the
   smallest defensible pill, the most audit-able, and
   the dep that survives any future signing need
   (e.g. signing webhook outbound deliveries in
   Phase 4+). UI-12c PR body justifies the dep
   against UI-0 §4 explicitly; the dep is gated to
   UI-12c and not loaded by UI-12a / UI-12b code
   paths.
   Codex P0 binding (2026-05-05): "gated to UI-12c
   imports only" is correct technically but
   insufficient as an institutional contract. The
   dep enters the repo as a NAMED, SCOPED EXCEPTION
   to UI-0 §4 — pinned in §11.6.13 of THIS brief.
   The exception:
     - Applies ONLY to `cryptography` (not to
       `pywebpush`, not to `requests`, not to any
       transitively-pulled package beyond what
       `cryptography` itself ships with).
     - Applies ONLY inside the UI-12c push emit
       module (one Python file under
       src/karasu/ui/push/ or similar). Imports
       outside that module are a regression.
     - Does NOT generalise. Future chunks asking
       for additional deps re-open the UI-0 §4
       conversation per chunk; the UI-12c precedent
       does not cover them.
   The UI-12c PR body restates this exception
   verbatim in its description; Codex re-audit on
   UI-12c verifies the import scope.
   [PROPOSAL — operator sign-off binding; Codex
   audit on UI-12c PR re-verifies]

6. Endpoint hash on the bus:
   PROPOSAL — SHA-256 of the endpoint URL, hex-
   encoded. Stable across subscribe / unsubscribe
   pairs (so an audit can see "the operator
   unsubscribed the same browser they subscribed").
   The full endpoint URL is sensitive (it routes to
   the operator's specific browser via FCM/APNs/
   autopush) and stays out of the bus.
   [PROPOSAL]

7. Empty modal close UX:
   PROPOSAL — same as UI-10 §10.6 + UI-11 §10.6.
   First Esc closes modal. Second Esc closes drawer
   (if open). Footer affordance does NOT
   participate in Esc precedence (it is not modal
   chrome).
   [PROPOSAL]

8. Modal lede copy:
   PROPOSAL — single sentence, paralleling UI-11
   §3.5. Suggested:
     "Karasu can ping you when the bus crosses a
      threshold you opted in to. Pick the moments
      worth breaking quiet for."
   The modal foot states the OS-prompt truth:
     "Confirming will ask your browser for
      notification permission."
   No marketing copy, no exclamation, no emoji.
   [PROPOSAL — operator-tunable copy]

9. Browser support fallback:
   PROPOSAL — feature-detect at server load time
   (no — the server can't know the browser). Detect
   client-side; if PushManager is undefined or
   Notification is undefined, /api/push.state ==
   "supported" still (server-side state) but the
   client renders the footer as "Notifications:
   unsupported" with no click handler. iOS Safari
   < 16.4, Firefox in private mode, etc all hit
   this path.
   [PROPOSAL]

10. Dogfood coverage:
    PROPOSAL — UI-12c lands with a docs/local-
    dogfood.md addition: a step-by-step "subscribe
    one browser, trigger an attention event,
    confirm the push arrives". Mirrors how Phase 3
    dogfood validated /scar end-to-end.
    [PROPOSAL]
```

## 11 · Definition of "done"

### UI-12a

```text
- One PR, ~250 LOC including tests.
- GET /api/push endpoint with HTTP shape lock.
- Footer affordance renders current state.
- Push store path resolved (default + --push-store flag).
- 1 PNG of footer "off".
- 1 PNG of footer "denied".
- docs/event-schema.md unchanged (no events emitted yet).
- Codex audit returns APPROVED or APPROVED-with-
  observations.
```

### UI-12b

```text
- One PR, ~400 LOC including tests + the new endpoints.
- POST /api/push/subscribe + /unsubscribe + 204 on
  success.
- HTTP shape locks pinned in the same PR.
- .modal-push-* + .footer-push styles in modal.css /
  footer.css (additive).
- JS: openPushModal + confirmPushSubscribe +
  confirmPushUnsubscribe + wirePushModal.
- sw.js: 'push' + 'notificationclick' listeners
  (additive; fetch ordering unchanged); CACHE_NAME
  bump.
- Playwright cancel + confirm + esc + backdrop tests.
- 4-5 PNGs + 1 .webm walking the full flow.
- docs/event-schema.md updated with push_subscribe +
  push_unsubscribe fields.
- Lighthouse re-run after the chunk lands; thresholds
  unchanged from UI-11 baseline (variance window
  honoured).
- Codex audit returns APPROVED or APPROVED-with-
  observations.
```

### UI-12c

```text
- One PR, ~400 LOC including tests + the dep.
- Watcher / loop controller subscribes to the bus;
  category-matching events dispatch Web Pushes.
- Runtime dep negotiated per §10.5; PR body justifies
  against UI-0 §4 with operator sign-off captured.
- VAPID JWT signing path tested.
- 410 / 404 pruning tested.
- Rate-limit debounce tested.
- 1-2 PNGs of the notification tray.
- 1 .webm of the edge-to-edge flow.
- docs/local-dogfood.md updated with push setup
  steps.
- Lighthouse unchanged (push emission is server-side;
  no surface perf delta).
- Codex audit returns APPROVED or APPROVED-with-
  observations.
```

## 11.6 · Implementation pins (Codex audit, 2026-05-05)

Fifteen pins set by Codex on the UI-12 brief audit
(CHANGES-REQUIRED verdict, in-branch fixes applied to
§3-A / §3-D / §3-E / §3-F / §3-G / §3-I / §6 UI-12b /
§6 UI-12c / §9 / §10.5 before re-audit). All bind UI-12a
/ UI-12b / UI-12c implementation. Verbatim:

```text
1.  UI-12 is the first proactive surface and must remain
    opt-in only.

2.  Push permission must never be requested on first
    visit.

3.  Push opt-in must be exposed only as a quiet footer
    affordance.

4.  UI-12 must not introduce install banners, update
    toasts, connection badges, or permission nudges.

5.  Raw PushSubscription endpoint and keys must never be
    written to the bus.

6.  endpoint_hash may appear only as audit metadata on
    human_decision events.

7.  Push subscription state lives in the browser/store,
    not in the event bus.

8.  Every subscribe/unsubscribe mutation must emit an
    inspectable human_decision event.

9.  UI-originated writes must not trigger correction
    push notifications.

10. Notification categories are closed to attention,
    errors, and corrections for UI-12.

11. Unsupported push environments must degrade to
    passive read-only status.

12. UI-12b must prove service worker fetch handler
    ordering did not regress.

13. UI-12c is the only approved dependency exception
    for Web Push signing.

14. Push emit must be rate-limited and deduplicated
    before delivery.

15. Multi-device fan-out must be explicit: each active
    subscription is a separate delivery target.
```

Pins 5 + 6 + 7 are the privacy contract that drives
§3-D + §3-E + §3-F (endpoint_hash audit-only, raw
endpoint never on bus, hash never as store lookup
key, store classified private). Pin 12 is the §3-I
shape-lock requirement on UI-12b (fetch handler
ordering is no longer auditable from diff alone). Pin
13 is the §10.5 cryptography exception named, scoped,
and non-generalising. Pin 14 is the multi-layer
rate-limit policy in §6 UI-12c (event-id dedupe +
per-category debounce + UI-write suppression). The
remaining pins parallel UI-10 §11.6 / UI-11 §11.6
contracts (modal mandatory, scope discipline, schema
discipline, operator-feel .webm).

## 12 · Status

```text
Brief status:        CHANGES-REQUIRED — fixes applied
                     in-branch (Claude Opus 4.7,
                     2026-05-05). Round 1 audit verdict
                     was CHANGES-REQUIRED; all 8 findings
                     (2 P0 + 4 P1 + 2 P2) addressed by
                     edits to §3-A / §3-D / §3-E / §3-F /
                     §3-G / §3-I / §6 UI-12b / §6 UI-12c /
                     §9 / §10.5. The fifteen Codex-
                     proposed §11.6 pins ratified verbatim.
Operator sign-off:   PENDING on §3 + §10 proposals (the
                     audit substantively endorsed each via
                     the Q1-Q7 yes-with-conditions
                     answers; explicit operator sign-off
                     still required before merge).
Codex audit:         Round 1 returned CHANGES-REQUIRED.
                     Round 2 PENDING (verifies fixes
                     applied; verifies re-formed §3 + §10
                     contract holds the audit's
                     conditions).
Implementation:      BLOCKED until brief merges.
                     UI-12a (read display) ships first per
                     pin §0.5.1 carry-forward; UI-12b
                     (opt-in surface) follows; UI-12c
                     (server-side emit) closes the chunk.
Loop budget:         Round 1 of 5 consumed.
```

The brief follows the lifecycle `ui-10-design-brief.md` (PR
#83) and `ui-11-design-brief.md` (PR #87) went through:
operator sign-off + Codex audit + follow-ups all land on the
same branch before the merge, so the binding contract is in
`main` before UI-12a opens.
