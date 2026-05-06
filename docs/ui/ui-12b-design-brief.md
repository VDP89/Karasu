# Karasu UI — UI-12b Design Brief (push opt-in surface, write paths)

> Doc-only seal of the visual + structural direction for UI-12b
> specifically. Earned per UI-9 audit pin #1 / UI-12 §11.6.1 carry-
> forward: any UI-N that introduces write paths must earn a brief
> before code. UI-12b is the FIRST proactive write surface in the
> project — the operator subscribes the browser to receive pushes
> from a notification tray that may not even be open.
>
> Audited and merged BEFORE any UI-12b code chunk opens.
>
> Parallel to:
> - `ui-0-design-brief.md`  (UI-1..UI-9 read-only MVP)
> - `ui-10-design-brief.md` (UI-10 scar revoke)
> - `ui-11-design-brief.md` (UI-11 trust adjust)
> - `ui-12-design-brief.md` (UI-12 family — chunk split, sw.js
>                            delta, store schema, copy, dep gap,
>                            16 §11.6 binding pins)
>
> The UI-12 parent brief is the architecture-level seal for the
> UI-12 family. UI-12b earns its OWN chunk-level brief because the
> first proactive write surface deserves the same brief-before-code
> discipline UI-10 / UI-11 / UI-12 ratified.
>
> **STATUS:** APPROVED-with-observations — mergeable. Operator
> sign-off complete (Victor, 2026-05-06: "avanzar"). Codex
> audit closed at round 3 of 5: round 1 CHANGES-REQUIRED
> (1 P0 + 5 P1 + 1 P2, all addressed in-branch); round 2
> CHANGES-REQUIRED (3 P1 + 1 P2, all addressed in-branch);
> round 3 APPROVED-with-observations (1 P2 pin-5 wording
> tightening, applied). Sixteen §11.6 pins ratified as
> binding for UI-12b implementation.

## 0 · Why this brief exists

Codex pin #1 from the UI-9 audit (PR #81), reaffirmed by UI-10
(PR #85), UI-11 (PR #87), and UI-12 (PR #93):

> *"UI-N+ that introduces write paths must earn a new brief
>  before code."*

UI-10 (scar revoke) and UI-11b (trust adjust) were drawer-earned
write paths against bus state. The mutation lived inside the
existing watchtower drill-in pattern: the operator opened a
detail drawer on a specific event, performed a verb against that
event, the bus recorded the verb. Surface-side state was a
projection of bus-side state.

UI-12b is qualitatively different in three ways:

```text
1. The mutation creates a permanent OUTBOUND CHANNEL. Once a
   subscription lands in karasu-push.json, every UI-12c push
   dispatch will reach the operator's notification tray. That
   surface lives outside Karasu's window. The opt-in IS the
   contract that lets Karasu reach out.

2. The chunk introduces the WRITER side of the private push
   store. UI-12a only shipped the reader. Atomic write + 0600
   mode + the never-bus-replay discipline must materialise in
   code here, not in UI-12c (which only consumes the store to
   dispatch pushes).

3. The first end-to-end browser PERMISSION GRANT happens on
   this chunk. The native Notification.requestPermission prompt
   is a verb the operator earns by deliberately drilling into
   the footer affordance + confirming inside Karasu's modal
   first. Pin §11.6.2 binding — there is no path that requests
   permission without an explicit operator click on the modal's
   primary button.
```

The 86 binding pins inherited (52 base + 6 UI-10 §0.5 + 12 UI-11
§11.6 + 16 UI-12 §11.6) all carry forward verbatim. UI-12b adds
operational clarifications on top — not new architecture.

## 0.5 · Pins inherited from UI-12 audit (verbatim, binding)

The 16 §11.6 pins from `ui-12-design-brief.md` (PR #93) bind
UI-12b explicitly. Repeated here as the implementer's working
contract:

```text
1.  UI-12 is the first proactive surface and must remain
    opt-in only.
2.  Push permission must never be requested on first visit.
3.  Push opt-in must be exposed only as a quiet footer
    affordance.
4.  UI-12 must not introduce install banners, update toasts,
    connection badges, or permission nudges.
5.  Raw PushSubscription endpoint and keys must never be
    written to the bus.
6.  endpoint_hash may appear only as audit metadata on
    human_decision events.
7.  Push subscription state lives in the browser/store, not
    in the event bus.
8.  Every subscribe/unsubscribe mutation must emit an
    inspectable human_decision event.
9.  UI-originated writes must not trigger correction push
    notifications.  (UI-12c concern; carried forward.)
10. Notification categories are closed to attention, errors,
    and corrections for UI-12.
11. Unsupported push environments must degrade to passive
    read-only status.
12. UI-12b must prove service worker fetch handler ordering
    did not regress.
13. UI-12c is the only approved dependency exception for Web
    Push signing.  (UI-12c concern; carried forward.)
14. Push emit must be rate-limited and deduplicated before
    delivery.  (UI-12c concern; carried forward.)
15. Multi-device fan-out must be explicit: each active
    subscription is a separate delivery target.  (UI-12c
    concern; carried forward.)
16. Raw push endpoints are request-local secret material and
    must never be logged, projected, emitted, screenshotted,
    or echoed.
```

The pins driving THIS chunk:

```text
Modal entry contract (§3-A):       1, 2, 3, 4, 11
POST contracts (§3-B):             5, 6, 7, 16
Bus event schema (§3-C):           6, 7, 8
Service worker delta (§3-D):       12
Persistence WRITER (§3-E):         5, 7, 11, 16
Default opt-in / HTTPS gap (§3-F): 1, 2, 3, 4, 11
```

Pins 9, 13, 14, 15 are UI-12c concerns. UI-12b inherits them
forward without materialising them in code.

## 1 · Positioning

UI-12a made push state visible (footer four-state read display:
off / on / denied / unsupported). UI-12b is the verb that flips
the state.

```text
The operator clicks the footer →
  modal opens (UI-10 .modal primitive reused, .modal-push-*
    micro-elements from UI-12 §5.2 materialised) →
  three categories pre-checked per §10.2 of UI-12 parent →
  operator clicks "Enable notifications" →
  native Notification.requestPermission fires →
  on grant: PushManager.subscribe →
  POST /api/push/subscribe →
  204 →
  human_decision (push_subscribe) lands on the bus →
  modal closes →
  /api/push re-fetch → footer flips to "on"
```

The first second of looking at the UI before AND after a UI-12b
subscribe must read identical except for the footer state word.
No banners, no toasts, no celebration. Karasu does not announce
that it earned a notification channel; it just reflects the new
truth in the same quiet footer slot.

> A push subscription is the operator deliberately opening a
> reverse channel. The chrome around that act has to read like
> the operator is doing a thing they meant to do, not like
> Karasu is colonising the OS notification tray.

The unsubscribe verb lives in the SAME modal. Reopening the
modal post-subscribe shows current categories + a quiet
"Unsubscribe this browser" secondary button at the modal foot.
Operators do not hunt opt-out flows in OS settings (§3.5
operator-feel pin from UI-12 parent, carried forward).

## 2 · Visual references (anchors held)

Same anchors as UI-0/10/11/12 §2:

```text
linear.app          notification settings adjacent to context;
                    the inbox is a destination, not a sidebar
                    interrupt.
vercel.com          notification opt-ins are inline copy +
                    explicit verb, never auto-prompts.
stripe.press        attention through copy + spacing, not
                    chrome.
```

Anti-patterns (UI-0 §4 + UI-8 audit pin #5 + UI-12 §1 binding):
Material defaults / Tailwind defaults / component-library chrome
/ install banners / update toasts / connection badges /
first-visit permission prompts all forbidden.

## 3 · Confirmed decisions (operator sign-off complete 2026-05-06)

All decisions below confirmed binding by Victor on 2026-05-06
("avanzar" — every default PROPOSAL accepted as the binding
contract; Codex audit pending out-of-band).

### A) Modal entry + copy

PROPOSAL — single `.modal` opened from the footer affordance
click handler. The footer slot exists since UI-12a as a passive
read-only span; UI-12b promotes it to a `<button>` when the
operator's browser supports push (`browserPushSupport()` returns
true) and the permission state is not `denied`.

Modal title:    `Notifications`

Modal lede:     `Karasu can ping you when the bus crosses a`
                `threshold you opted in to. Pick the moments`
                `worth breaking quiet for.`
                (UI-12 §10.8 [CONFIRMED 2026-05-05].)

Modal foot copy:  `Confirming will ask your browser for`
                  `notification permission.`
                  (UI-12 §10.8 [CONFIRMED 2026-05-05].)

Pre-subscribe modal layout (operator has not yet subscribed):

```text
+-----------------------------------------------------------+
|  Notifications                                            |
|                                                           |
|  Karasu can ping you when the bus crosses a               |
|  threshold you opted in to. Pick the moments              |
|  worth breaking quiet for.                                |
|                                                           |
|  [✓] attention    Operator review needed                  |
|  [✓] errors       An adapter failed                       |
|  [✓] corrections  A scar was recorded out-of-band         |
|                                                           |
|  Confirming will ask your browser for                     |
|  notification permission.                                 |
|                                                           |
|                  [ Cancel ]  [ Enable notifications ]     |
+-----------------------------------------------------------+
```

All three categories pre-checked on first open per UI-12 §10.2
[CONFIRMED 2026-05-05]. Operator can uncheck any subset before
clicking primary; primary stays enabled even with zero
categories checked (a zero-category subscribe is a deliberate
"register but stay silent" choice; the bus event records the
empty array).

Post-subscribe modal layout (modal reopens after a successful
subscribe, current state read via `GET /api/push`):

```text
+-----------------------------------------------------------+
|  Notifications                                            |
|                                                           |
|  Karasu can ping you when the bus crosses a               |
|  threshold you opted in to. Pick the moments              |
|  worth breaking quiet for.                                |
|                                                           |
|  Subscribed: 2 categories                                 |
|                                                           |
|  [✓] attention    Operator review needed                  |
|  [ ] errors       An adapter failed                       |
|  [✓] corrections  A scar was recorded out-of-band         |
|                                                           |
|             [ Cancel ]  [ Update categories ]             |
|                                                           |
|              Unsubscribe this browser                     |
+-----------------------------------------------------------+
```

`Update categories` is enabled only when the checked set
diverges from the current store state. Clicking it fires the
idempotent subscribe path (§10.2 of THIS brief). It does NOT
re-trigger the native permission prompt because the browser
subscription is unchanged.

`Unsubscribe this browser` is rendered in `--fg-2` (NOT
`--danger`; reversibility per §3.5 operator pin: re-subscribe is
one click away). Click → POST `/api/push/unsubscribe` → 204 →
modal closes → footer flips to "off".

Cancel, Esc, and backdrop close the modal without mutating
anything (no `PushManager.subscribe`, no POST, no
`human_decision`). Inherited UI-11 §11.6.7 (modal mandatory) +
§11.6.11 (Playwright cancel + confirm + esc + backdrop coverage)
binding.

Unsupported / denied environment branch:

```text
If browserPushSupport() returns false on UI-12a load
OR Notification.permission === "denied" at load time:
  - Footer renders "Notifications: unsupported" or
    "Notifications: denied" in --warn (UI-12a contract).
  - Footer slot is a <span>, NOT a <button> — no click handler
    attached.
  - Modal is unreachable.
  - UI-12b adds NO retry prompt, NO copy nudging the operator
    to enable notifications in OS settings, NO help link.
  - The browser is the source of truth; Karasu does not insist.
```

ALTERNATIVES considered:

- Tooltip-style category descriptions on hover. Rejected: UI-12
  §3-G PROPOSAL G binding — descriptions visible inline, no
  hover-only legibility.
- Two-step modal (categories → confirm → native prompt).
  Rejected: doubles friction without earning anything; the
  native prompt IS the second step in the operator-felt
  sequence.
- Auto-subscribe with checkboxes to opt out per category.
  Rejected: pin §11.6.1 binding — subscription is opt-in, not
  opt-out.
- Surface the unsubscribe verb on the footer directly (e.g.
  long-press footer to unsubscribe). Rejected: pin §11.6.3
  binding — footer is the affordance, modal is the gate; no
  side-channel verbs on the footer.

`[CONFIRMED 2026-05-06]`

### B) POST contracts

PROPOSAL — exactly two write endpoints, both `204` on success,
both inside `/api/*` (network-only by SW construction).

#### POST /api/push/subscribe

Request body (JSON):

```json
{
  "subscription": {
    "endpoint": "https://fcm.googleapis.com/...",
    "keys": {
      "p256dh": "<b64u>",
      "auth":   "<b64u>"
    }
  },
  "categories": ["attention", "errors", "corrections"]
}
```

Body cap: **4 KiB** (mirrors UI-10 / UI-11b cap; real browsers
produce subscribe bodies ~600 bytes).

Validation (all 422 unless noted):

```text
- Body NOT valid JSON → 400. Generic body
  ({"error": "invalid request"}); MUST NOT echo the raw
  request bytes, MUST NOT surface json.JSONDecodeError text,
  MUST NOT include line/column offsets that could leak
  fragments. NO bus event, NO store mutation.
  (Codex round 2 P1 pin: malformed JSON is a handler branch
  distinct from field-level validation, and the response
  body MUST be generic on this branch too.)
- Top-level JSON value NOT an object (e.g. array / string /
  number) → 422. Generic body
  ({"error": "request body must be an object"}); same
  no-echo discipline as above. NO bus event, NO store
  mutation.
- Missing `subscription` / `subscription.endpoint` /
  `subscription.keys.p256dh` / `subscription.keys.auth` /
  `categories` → 422.
- `categories` not a JSON array → 422.
- `categories` containing values outside the closed enum
  {attention, errors, corrections} → 422 (pin §11.6.10).
- `categories` containing duplicate values → 422.
- `categories` empty → ALLOWED. The operator deliberately
  registered without any category opt-ins (zero-noise
  subscription). UI-12c emit will simply never match for this
  endpoint until the operator updates categories. The store
  records the empty array verbatim; the bus event reflects it.
- `subscription.endpoint` not matching
  `^https://[^/]+/.+$` → 422 (Web Push endpoints are always
  HTTPS URLs; a plain HTTP endpoint cannot be a real
  PushSubscription).
- Body size > 4 KiB → 413.
- Idempotent duplicate (same endpoint already in store) →
  204 + UPDATE the entry's categories + emit a fresh
  push_subscribe event. Operator's intent is authoritative.
```

Response: `204`, **NO body**.

Side effects (in order):

```text
1. Compute endpoint_hash = sha256_hex(endpoint).
2. Append (or update) the subscription entry in
   karasu-push.json via push_store writer (atomic write +
   rename, mode 0600). See §3-E.
3. Emit a human_decision event (see §3-C for exact shape).
4. NO log line carries the raw endpoint, the keys, or the
   full subscription dict. The handler logs at INFO with
   "subscribed: <hash> <categories>" only.
```

#### POST /api/push/unsubscribe

Request body (JSON):

```json
{"endpoint": "https://fcm.googleapis.com/..."}
```

Body cap: **4 KiB** (uniform with subscribe; the differential
cap considered in §10.5 was rejected for testing simplicity —
both endpoints share one cap constant).

Validation:

```text
- Body NOT valid JSON → 400. Generic body
  ({"error": "invalid request"}); same no-echo discipline
  as subscribe (Codex round 2 P1 pin). NO bus event, NO
  store mutation.
- Top-level JSON value NOT an object → 422. Generic body
  ({"error": "request body must be an object"}). NO bus
  event, NO store mutation.
- Missing `endpoint` → 422.
- `endpoint` not matching the HTTPS regex above → 422.
- `endpoint` not in the store → 404. The 404 body is generic
  (`{"error": "subscription not found"}`); it does NOT echo
  the supplied endpoint.
- Body size > 4 KiB → 413.
```

Response: `204`, **NO body**.

Side effects (in order):

```text
1. Compute endpoint_hash = sha256_hex(endpoint).
2. Remove the subscription from karasu-push.json via
   push_store writer (atomic write + rename).
3. Emit a human_decision event (see §3-C for exact shape).
4. Same logging discipline as subscribe — hash only, never
   the raw endpoint.
```

Both endpoints sit inside `/api/*` and inherit the SW
network-only contract (UI-8 fetch handler ordering, pin §11.6.12
shape-locked in §3-D). Neither participates in any cache.

#### Browser ⇄ store two-phase mutation contract (Codex P0 round 1, 2026-05-06)

The browser owns the PushSubscription; the server owns the
store. Each write path crosses both surfaces, so each path
needs an explicit ordering + rollback rule. Without it,
either side can be left holding state the other side does
not know about.

##### Subscribe — happy path

```text
1. Preflight: GET /api/push.
   - If state != "supported" or vapid_public_key is null,
     short-circuit per §3-A unsupported branch / §3-E
     VAPID-not-provisioned branch. NO further calls.
2. Open modal. Operator confirms categories + clicks
   "Enable notifications".
3. await Notification.requestPermission().
   - If "denied" or "default": close modal, footer flips to
     "denied" (denied case) or stays "off" (default).
     EMIT NOTHING. NO PushManager call. NO POST.
   - If "granted": continue.
4. await registration.pushManager.subscribe({
       userVisibleOnly: true,
       applicationServerKey: <vapid_public_key bytes>
   })
   - On rejection (browser-side error, e.g. push service
     unreachable): close modal, surface a single-sentence
     editorial error in the modal footer ("Push service
     unreachable. Try again."), no POST, no human_decision,
     no store write. Operator can retry.
   - On success: hold the PushSubscription object as
     `subscription`.
5. await fetch('/api/push/subscribe', {method, body, ...}).
   - On 204: SUCCESS. Close modal. Re-fetch /api/push so
     the footer flips to "on". The bus carries the
     push_subscribe event by the next /api/events tick.
   - On 422 / 413 / 503 / network failure / non-204:
     ROLLBACK (next subsection).
```

##### Subscribe — rollback rule

```text
If step 5 returns anything other than 204, the browser
holds a PushSubscription that the server has no record of.
That is a leaked subscription — UI-12c would never reach
it (because the store has no entry), but the push service
would still hold the endpoint indefinitely.

Rollback (synchronous, before user-visible feedback):

  await subscription.unsubscribe()

The frontend MUST call subscription.unsubscribe() on EVERY
non-204 path. After rollback:
  - Close the modal.
  - Surface a single-sentence editorial error in the modal
    footer that names the failure mode (network /
    validation / VAPID not provisioned).
  - EMIT NOTHING on the bus (no human_decision).
  - The store is unchanged (the failed POST never wrote).
  - The browser is unsubscribed (rollback restores parity).

Both sides are now back to pre-attempt state; the operator
can retry without the leaked subscription.
```

##### Unsubscribe — happy path + rollback

```text
1. Get current subscription from the browser:
     subscription = await registration.pushManager.getSubscription()
   - If null (browser already unsubscribed out-of-band, e.g.
     OS-level revocation): the modal-foot "Unsubscribe this
     browser" verb is NOT rendered (the modal post-subscribe
     layout omits it). For UI-12b an orphaned store entry
     stays in karasu-push.json until UI-12c emit prunes it
     on a 410 Gone from the push service. UI-12b does NOT
     surface raw endpoint material from any /api/* projection
     (the /api/push read shape is frozen at
     {state, categories, subscription_count, vapid_public_key};
     a future maintenance brief — UI-13+ — earns its own
     contract for orphan cleanup).
   - If non-null: continue.
2. await fetch('/api/push/unsubscribe', {endpoint, ...}).
   - On 204: server-side store mutated, push_unsubscribe
     event emitted on the bus. Continue to step 3 with
     audit_emitted=true.
   - On 404 (endpoint already absent from store — orphan
     left by a prior partial flow, or already pruned by a
     parallel writer): server did NOT mutate the store and
     did NOT emit a bus event (per §7.3 server contract).
     Treat as browser-cleanup success and continue to
     step 3 with audit_emitted=false. Both sides converge
     to "unsubscribed" but the bus carries no new
     human_decision because no server mutation occurred.
   - On 422 / 413 / network failure: surface error in modal
     foot, do NOT call subscription.unsubscribe() — the
     browser stays subscribed so a retry can complete the
     server-side removal first.
3. await subscription.unsubscribe()
   - On rejection: surface error in modal foot. The store
     is now empty for this endpoint but the browser still
     holds the subscription. Operator must retry from the
     modal (which will see getSubscription() return non-null
     and offer the unsubscribe verb again; step 2 will
     return 404 the second time — audit_emitted=false on
     the retry — and the flow converges).
   - On success: close modal, footer flips to "off". If
     audit_emitted=true, the push_unsubscribe event lands
     by the next /api/events tick. If audit_emitted=false
     (404 path), the bus carries NO new event — the
     server's silence on 404 is the audit truth (no
     mutation, no event), and the surface refresh just
     reflects the browser's new state.

Order matters: server-removal-first (so the server-side
audit trail is authoritative), then browser-unsubscribe.
If the order were reversed (browser first), a network
failure on step 2 would leave the store with a dead
endpoint that UI-12c would dispatch against (push service
returns 410, UI-12c prunes — eventually) but the operator
would believe they had unsubscribed cleanly.

Audit-event correspondence: exactly one push_unsubscribe
event lands on the bus per server-side store mutation. The
404 convergence path emits zero events; the 204 path emits
exactly one. This composes cleanly with §7.3's server
contract ("Endpoint not in store → 404; NO bus event;
NO store mutation").
```

##### Test coverage (Playwright + HTTP)

```text
The Playwright cancel + confirm + Esc + backdrop +
native-deny suite (§3-A) gains FOUR new tests:

  test_subscribe_post_failure_rolls_back_browser
    Mock POST /api/push/subscribe to return 503.
    Drive the full happy-path UI through to step 5.
    Assert:
      - subscription.unsubscribe was called exactly once.
      - PushManager.getSubscription() returns null
        post-rollback.
      - Bus has zero push_subscribe events.
      - Store has zero subscriptions delta.
      - Modal foot displays an editorial error.

  test_unsubscribe_browser_call_is_made_after_204
    Drive the full happy-path UI through to step 3 of
    unsubscribe. Mock POST /api/push/unsubscribe to return
    204.
    Assert:
      - subscription.unsubscribe was called exactly once
        AFTER the 204 lands.
      - Bus carries exactly one push_unsubscribe event.
      - Store has the entry removed.
      - Footer flips to "off".

  test_unsubscribe_404_converges_with_no_bus_event
    Seed: synthetic subscription in store, then DELETE the
    store entry server-side WITHOUT browser-side awareness
    (simulates a parallel pruner). Operator hits unsubscribe.
    Mock POST /api/push/unsubscribe to return 404.
    Assert:
      - subscription.unsubscribe was called exactly once
        AFTER the 404 lands (Codex round 2 P1 pin: 404 is
        treated as browser-cleanup success).
      - Bus has ZERO new push_unsubscribe events (the
        server emitted nothing on 404 per §7.3).
      - Store delta is zero (already empty).
      - Footer flips to "off".

  test_unsubscribe_browser_failure_after_204_can_retry_via_404
    (Codex round 2 P2 pin.)
    Drive the full happy-path UI through step 2 (POST 204).
    Force subscription.unsubscribe() to reject on the first
    attempt.
    Assert (first attempt):
      - Modal foot displays an editorial error.
      - Store has the entry removed (the 204 already
        mutated it).
      - Browser still holds the subscription.
      - Bus carries exactly one push_unsubscribe (from
        the 204).
    Operator retries via the modal; step 2 now returns 404
    because the store was emptied by the first attempt's
    204; subscription.unsubscribe() succeeds.
    Assert (second attempt):
      - subscription.unsubscribe was called and resolved.
      - Bus carries NO new push_unsubscribe (the 404 path
        emits no audit event).
      - Total bus push_unsubscribe count for the flow is
        exactly one (from the first 204), not two.
      - Footer is "off"; getSubscription() returns null.

The HTTP shape lock in §7.3 already covers the server side
of these flows; the Playwright tests pin the BROWSER side
of the contract — including the 404 convergence path and
the post-204 browser-rejection retry path.
```

#### Privacy reaffirmations (binding)

```text
Pin §11.6.6:  endpoint_hash is audit metadata only. UI-12b
              implementation MUST NOT use the hash as a store
              lookup key. Subscription store keys are the raw
              endpoint URL.
Pin §11.6.16: the raw endpoint never leaves handler scope.
              It is written ONLY to karasu-push.json (mode
              0600) and held only in process memory long
              enough to compute endpoint_hash. No log line,
              no projection, no /api/push body, no error
              response, no test fixture asserting against
              real endpoints — ever carries it.
```

ALTERNATIVES considered:

- Single `POST /api/push` with a verb field. Rejected:
  conflates two distinct privacy contracts into one endpoint.
- `DELETE /api/push/<endpoint>` for unsubscribe. Rejected:
  bare DELETE without body forces the endpoint into the URL
  path, which logs in access logs. POST + JSON body keeps the
  endpoint out of access logs entirely.
- Returning the human_decision event id in the 204 response.
  Rejected: tying the response to the bus event creates a
  cross-write coupling. The surface refresh polls
  `/api/events` on the next tick; the 204-then-poll pattern
  matches UI-10 / UI-11b.
- Asymmetric body caps (4 KiB subscribe, 2 KiB unsubscribe).
  Rejected for testing simplicity — see §10.5. Both endpoints
  share one cap constant.

`[CONFIRMED 2026-05-06]`

### C) Bus event schema (additive to UI-12 §3-D)

PROPOSAL — exact `human_decision` payloads emitted by the two
write paths.

#### push_subscribe

```json
{
  "id": "<event id>",
  "type": "human_decision",
  "ts": "<iso8601 utc>",
  "source": "ui",
  "data": {
    "action": "push_subscribe",
    "endpoint_hash": "<sha256-hex, 64 chars>",
    "categories": ["attention", "errors", "corrections"]
  }
}
```

#### push_unsubscribe

```json
{
  "id": "<event id>",
  "type": "human_decision",
  "ts": "<iso8601 utc>",
  "source": "ui",
  "data": {
    "action": "push_unsubscribe",
    "endpoint_hash": "<sha256-hex, 64 chars>"
  }
}
```

Field semantics:

```text
data.endpoint_hash
  hashlib.sha256(endpoint.encode("utf-8")).hexdigest().
  Stable across subscribe / unsubscribe pairs for the same
  endpoint, so an audit can correlate "operator unsubscribed
  the same browser they subscribed". 64-char lowercase hex.

data.categories (push_subscribe only)
  The validated, closed-enum subset. Ordering is canonical
  (attention, errors, corrections) regardless of input
  order — easier to test, easier to grep later. Empty array
  permitted (see §3-B validation).

source = "ui"
  Per UI-12 §3-G PROPOSAL G + pin §11.6.9 binding. UI-write
  events are filtered out of UI-12c's "corrections" push
  category to avoid pushing the operator's own click back to
  them.
```

Pre-UI-10 consumers ignore `data.action` and treat the event as
a generic `human_decision` (UI-11 §10.5 carry-forward).
`EVENTS_PROJECTION_KEYS` already exposes `data.action` from
UI-11a; no projection update needed in UI-12b.

`docs/event-schema.md` gains a "push_subscribe / push_unsubscribe"
section in the same PR. Documentation lands in the same diff as
the emit code (UI-11 §11.6.2 carry-forward).

ALTERNATIVES considered:

- New event type (`push_decision`). Rejected: `human_decision`
  is the established carrier for operator-side mutations
  (UI-10 scar_revoke, UI-11b trust_adjust). Adding a new type
  for push subscribe / unsubscribe would force every bus
  consumer to learn a fourth event type.
- Embed the validated `vapid_public_key` in the event payload.
  Rejected: VAPID public is server-side identity, not operator
  intent; it lives in the store and is surfaced via
  `/api/push.vapid_public_key`. Putting it on the bus would
  mean every consumer that replays the bus has to know which
  public key was current at emit time — schema rot waiting to
  happen.
- Include `data.categories_before` + `data.categories_after`
  on idempotent updates, mirroring UI-11b's
  `data.trust_before` / `data.trust_after`. Rejected: trust
  adjust is a single-value mutation where the delta is the
  payload; categories are a SET where the delta is N
  additions + M removals + the new state. The new state is
  the contract; deltas are reconstructable from the bus.

`[CONFIRMED 2026-05-06]`

### D) Service worker delta + fetch-ordering shape lock

PROPOSAL — additive only. Two new event listeners + the
`CACHE_NAME` bump.

`sw.js` gains:

```js
self.addEventListener('push', (event) => {
  // Reads event.data.json() if present. Falls back to a
  // generic title if no payload was attached (e.g. a
  // payload-less wakeup ping). Calls
  // registration.showNotification with the §3-H copy from
  // UI-12 parent. Does NOT write to any cache. Does NOT
  // fetch.
  // During UI-12b: this listener is registered but never
  // receives traffic because no server-side emission exists
  // until UI-12c lands.
});

self.addEventListener('notificationclick', (event) => {
  // Closes the notification, focuses an existing client at
  // the surface URL via clients.matchAll + client.focus,
  // or opens a new one via clients.openWindow if none
  // exist.
});
```

`CACHE_NAME` bumps from `karasu-ui-v8` to `karasu-ui-v12b`. The
file changed; the bump rule in `sw.js`'s header comment owns
this. (UI-12a did NOT touch sw.js — UI-12 brief §6 PROPOSAL J
reaffirmed that — so the bump skips v9 / v10 / v11 / v12a and
goes directly to v12b.)

#### Fetch handler ordering MUST NOT regress (pin §11.6.12)

The shape-lock test required by UI-12 §3-I lands in THIS PR.
The implementer chooses between:

```text
Option (a): pure-JS unit test in tests/test_ui_sw.py via
            jsdom or a minimal SW-handler harness.
Option (b): Playwright route-stub equivalent that loads the
            real sw.js in a worker context and exercises the
            handler.
```

Both are acceptable; both must exercise the same three branches
with the same three independent assertions:

```text
1. GET /api/anything
   Cache pre-populated with a stale response for the same URL.
   Assert: network was called.
   Assert: cache.match was NOT consulted before network.
   Assert: response came from network.
   Cache miss case (separate sub-assertion):
     Assert: network was called.
     Assert: fallback was NOT served from cache.

2. Navigate request to /
   Assert: network was called first.
   Assert: /offline.html was served on rejection (offline
           branch).
   Assert: cache was NOT consulted on success branch (online
           branch).

3. GET /assets/icons/karasu-192.png
   Cache pre-populated with the asset.
   Assert: cache was consulted.
   Assert: network was NOT called.
   Assert: response came from cache.
   Cache miss case (separate sub-assertion):
     Assert: cache was consulted.
     Assert: network was called as fallback.
```

Commit ordering inside the PR is part of the contract:

```text
1. Test commit lands FIRST. The test passes against the
   UI-8-era sw.js (no push handlers yet). If the test fails
   on baseline, the test itself is a regression and must be
   fixed before the SW diff goes in.
2. SW diff commit lands SECOND. The same test runs and still
   passes. Codex audits this two-commit ordering on the PR
   diff — pin §11.6.12 binding, "fetch handler ordering is no
   longer auditable from diff alone".
```

The push + notificationclick listeners are independent SW event
types from the fetch handler. They cannot interfere
structurally; the test exists to PROVE additive-only by
construction, not to suspect a regression that diff review
would have caught.

ALTERNATIVES considered:

- Skip the shape-lock test and rely on diff review. Rejected:
  pin §11.6.12 binding — diff review is not the contract.
- One combined test that walks all three shapes inside a
  single Playwright capture. Rejected: independent assertions
  surface independent failures; one bundled test masks
  regressions and makes the failure mode hard to localise.
- Defer the test to UI-12c. Rejected: UI-12b is the chunk
  that mutates sw.js; the test gates the diff that introduces
  the risk.

`[CONFIRMED 2026-05-06]`

### E) Persistence — push subscription store WRITER

PROPOSAL — the store schema is already defined in UI-12 §3-F
([CONFIRMED 2026-05-05]). UI-12b implements the WRITER side.
UI-12a shipped the READER side; the file path resolution
(default `<bus_dir>/karasu-push.json`, override via
`karasu ui --push-store <path>`) + the state projection +
`PushStoreError` already live in `src/karasu/ui/push_store.py`.

#### Writer functions (added to push_store.py)

`append_subscription(store_path, subscription_dict)`:

```text
1. Read current store via push_store.read (handles missing-
   file → empty-state branch).
2. If `subscription_dict.endpoint` already present:
     UPDATE the existing entry's `categories` to the new
     validated set.
     Refresh `updated_at` to current iso8601 UTC.
     Leave `created_at` unchanged.
3. If endpoint absent:
     Append a new entry with
       endpoint        (raw URL, the only place it lives at
                        rest)
       endpoint_hash   (sha256-hex, cached for bus emission)
       keys            (p256dh + auth, b64u)
       categories      (validated, closed enum, possibly
                        empty)
       created_at      (iso8601 UTC, naive Z-suffix)
       updated_at      (same as created_at on first append)
4. Write via tmp + rename atomically:
     a) Open `<store_path>.tmp` with mode 0600 on POSIX:
        os.open(tmp, O_CREAT | O_WRONLY | O_EXCL, 0o600)
     b) Write JSON, fsync, close.
     c) os.replace(tmp, store_path).
   On Windows, os.replace is atomic on the same volume; POSIX
   rename is atomic. Both inherited from existing karasu
   writes (events.jsonl writer pattern).
5. If `<store_path>.tmp` already exists (a previous partial
   write left it behind, or a concurrent writer is in flight):
   the writer FAILS FAST with
   PushStoreError("partial write recovery needed").
   The operator manually removes the .tmp; no automatic
   cleanup that could mask a concurrent write.
```

#### Writer lock — read-modify-write atomicity (Codex P1 round 1, 2026-05-06)

```text
The atomic tmp+rename guarantees the FILE on disk is never
partially written, but it does NOT guarantee read-modify-write
atomicity across concurrent server threads. Two threads can
both call push_store.read, both produce diverging entry sets,
both write tmp + rename sequentially — the later write
clobbers the earlier mutation (lost-update race).

UI-12b closes this with a module-level threading.Lock held
across the FULL transaction (read + mutate + write + rename):

  _STORE_LOCK = threading.Lock()

  def append_subscription(store_path, subscription_dict):
      with _STORE_LOCK:
          state = read(store_path)
          state = _mutate(state, subscription_dict)
          _atomic_write(store_path, state)

  def remove_subscription(store_path, endpoint):
      with _STORE_LOCK:
          state = read(store_path)
          state = _filter(state, endpoint)
          _atomic_write(store_path, state)

The lock is module-level (single Lock instance per process)
because the http.server thread pool is the only writer in
scope. The lock is held for the full transaction, NOT
released between read and write.

Multi-process scope is OUT OF SCOPE for UI-12b — only one
`karasu ui` instance writes to a given store path. If a
future chunk introduces a second writer process (e.g. the
UI-12c server-side emitter writes back prune metadata), the
lock graduates to a filesystem lockfile (e.g. fcntl.flock
on POSIX, msvcrt.locking on Windows) held across the same
transaction. UI-12c re-audits this boundary in its own PR.

The .tmp-already-exists branch (step 5 above) remains as
defence-in-depth against a process crash that left a stale
.tmp behind across restarts; the lock prevents lost updates
WITHIN a single process lifetime.
```

`remove_subscription(store_path, endpoint)`:

```text
1. Read current store.
2. Filter the subscriptions list, removing the entry whose
   `endpoint == endpoint` (exact string match).
3. If no entry matched: raise PushStoreNotFound (handler
   maps to 404).
4. If matched: write back atomically as above.
```

#### File mode discipline

```text
POSIX:
  - Mode 0600 enforced via the os.open path above on FIRST
    write (file does not yet exist).
  - On subsequent writes, the writer stat()s the existing
    file BEFORE writing the .tmp. If observed mode is looser
    than 0600 (e.g. 0644), the writer logs a loud-stderr
    warning citing the file path + the observed mode +
    remediation:
      "WARNING: karasu-push.json mode is 0o644; expected
       0o600. Run `chmod 600 <path>`."
    The writer does NOT silently re-mode an existing file
    (that would be a quiet privilege change if the file's
    parent directory was open). The write proceeds because
    the new tmp file IS 0600; the existing file is replaced
    atomically.
  - Mirrors the trust-gradient startup warning pattern (UI-11
    backend) — visible at the layer where it can be acted on,
    not silent and not fatal.

Windows:
  - File mode is advisory; the warning is suppressed.
  - The store path's gitignore (events.jsonl is already
    gitignored, the push store inherits the same parent
    directory by default per UI-12a) + documentation
    discipline carry forward.
```

#### VAPID key generation

Pin §11.6.13 binding: the `cryptography` runtime dep is the
named, scoped exception that lands with **UI-12c**, not earlier.

##### UI behavior when vapid_public_key is null (Codex P1 round 1, 2026-05-06)

```text
The browser CANNOT call PushManager.subscribe without an
applicationServerKey, and applicationServerKey IS the VAPID
public key the server published via GET /api/push. If the
store has no VAPID section, /api/push.vapid_public_key is
null. The frontend MUST detect this and short-circuit BEFORE
the native permission prompt fires:

  loadPushState():
    state = await fetch('/api/push').json()
    if state.vapid_public_key is null:
      mark UI as VAPID-not-provisioned (see below)
      footer continues to render "Notifications: off"
    else:
      normal flow

  Modal opening from footer click is ALLOWED in the VAPID-
  not-provisioned state — the modal is the place where the
  operator finds out WHY they cannot subscribe yet — but:
    - The "Enable notifications" primary button is DISABLED
      (--fg-3 weight, aria-disabled="true").
    - A single-line copy renders below the categories,
      replacing the foot copy "Confirming will ask your
      browser for notification permission." with:
        "VAPID keys not provisioned. See
         docs/local-dogfood.md for manual setup."
    - Notification.requestPermission is NEVER called from
      this state (pin §11.6.2 carry-forward — no permission
      prompt without operator confirmation, and the operator
      cannot confirm because the primary is disabled).
    - PushManager.subscribe is NEVER called.
    - Cancel / Esc / backdrop close the modal as usual; no
      state mutation, no human_decision.

  The server-side 503 (next subsection) STAYS as defensive
  behaviour for forged or stale clients that bypass the
  preflight — e.g. an operator running a UI tab from before
  the keys were provisioned, then the keys appear, then the
  client sends a stale request. The 503 ensures the server
  never accepts a subscribe POST that would fail downstream
  in UI-12c emit.
```

##### Server-side 503 (defensive, not the primary gate)

```text
On POST /api/push/subscribe, if the store has no
"vapid" section OR the section lacks `public` / `private`:
  - The handler returns 503 with body
    {"error": "vapid keys not provisioned"}.
  - The body is generic; it does NOT name the missing field.
  - UI-12b does NOT generate VAPID keys; UI-12b does NOT
    import the cryptography package.

During UI-12b dogfood, the operator generates the keys
manually with openssl (any version 1.0+):
  openssl ecparam -genkey -name prime256v1 -noout -out vapid.pem
  openssl ec -in vapid.pem -pubout -outform DER \
    | tail -c 65 \
    | base64 -w0 \
    | tr '+/' '-_' \
    | tr -d '='
    > vapid_public.b64u
  openssl ec -in vapid.pem -outform DER 2>/dev/null \
    | tail -c 32 \
    | base64 -w0 \
    | tr '+/' '-_' \
    | tr -d '='
    > vapid_private.b64u
The operator pastes the two b64u strings into karasu-push.json's
"vapid" section.

UI-12c replaces this manual step with auto-generation on first
server start AND removes the manual-seed section from
docs/local-dogfood.md in the SAME PR that lands the
cryptography dep. The doc update is part of UI-12c's exit
criteria.
```

#### Privacy reaffirmation (pins §11.6.5 + §11.6.16 binding)

```text
- The store WRITER NEVER logs the raw subscription dict.
- The only debug-level log line is:
    "subscribed: <hash> <categories>"   (on append + update)
    "unsubscribed: <hash>"              (on remove)
- INFO-level logs: same shape, hash only.
- ERROR-level logs (write failures, partial-write recovery):
  hash only; the raw endpoint never appears even in the
  unhappy path.
- Test fixtures use a tmp directory + a synthetic
  subscription whose endpoint contains NO real auth
  material (e.g. https://test.example/<random-hex>).
  Assertions on the bus event MUST verify the absence of
  the raw endpoint + p256dh + auth in the projection +
  in any log capture (privacy negative-shape test, see §7).
```

ALTERNATIVES considered:

- SQLite-backed store. Rejected: UI-12 §3-F PROPOSAL F
  [CONFIRMED 2026-05-05] — JSON; no scope creep.
- Auto-generate VAPID keys with an openssl shell-out in
  UI-12b. Rejected: pin §11.6.13 binding — the named, scoped
  cryptography exception lands with UI-12c, not earlier.
  Bringing crypto generation forward into UI-12b violates the
  pin even if no Python dep changes.
- File mode 0644 with a parent-directory mode 0700.
  Rejected: defence-in-depth; both layers cost nothing and
  the failure modes are different — 0600 covers file-content
  reads regardless of parent-dir traversal holes (e.g. if
  another tool widens the parent dir, the file is still safe
  at rest).
- Pre-write fsync of the parent directory after rename.
  Rejected: complicates the writer for a Windows-incompatible
  guarantee. Crash recovery for the push store is "operator
  re-subscribes the affected browser" — the bus event is the
  audit record either way.

`[CONFIRMED 2026-05-06]`

### F) Default opt-in posture + HTTPS gap

PROPOSAL — UI-12b is opt-in only by default (pin §11.6.1). The
first-visit experience is unchanged from UI-12a:

```text
Footer reads "Notifications: off" in --fg-2 mono.
Identical weight to the build-version line.
No nudge, no first-visit prompt, no install banner, no
update toast. Pin §11.6.4 binding.
```

#### The native permission gate

The native `Notification.requestPermission` call fires ONLY
from `confirmPushSubscribe`, which fires ONLY from the modal's
"Enable notifications" button click handler, which fires ONLY
from operator click on the modal's primary button.

```text
Pin §11.6.2 binding — there is NO path that requests
permission without an explicit operator click on the modal's
primary button.

Concretely:
  - On page load: NO permission call. UI-12a only reads
    Notification.permission to render the footer state;
    requestPermission is NEVER called from any code path
    UI-12a or UI-12b ships.
  - On footer click: NO permission call. The footer click
    opens the modal; that's it.
  - On modal primary click: permission call fires.
  - On modal Cancel / Esc / backdrop / native deny: NO
    permission call (Cancel) or an already-dispatched call
    that the operator denied (native deny).
```

#### HTTPS gap

Web Push API requires a secure context. localhost is considered
secure by all major browsers (Chrome, Firefox, Safari, Edge).
The dev surface served via `karasu ui` binds to `127.0.0.1` by
default, so localhost coverage is automatic.

```text
If the operator binds the surface to a non-localhost address
over plain HTTP (e.g. a LAN IP for cross-device dogfood):
  - The browser reports navigator.serviceWorker as undefined.
  - PushManager is unavailable.
  - UI-12a's browserPushSupport() short-circuits.
  - Footer renders "Notifications: unsupported" with no
    click handler.
  - Modal is unreachable.
  - UI-12b inherits this contract verbatim.

The operator's options for cross-device dogfood are:
  (a) Keep binding to 127.0.0.1 (default).
  (b) Front the surface with a local TLS terminator. The
      documented path is mkcert + caddy:
        mkcert -install
        mkcert localhost <lan-ip>
        caddy reverse-proxy --from https://<lan-ip>:8443 \
                            --to http://127.0.0.1:8000
      docs/local-dogfood.md gains a "TLS for cross-device
      dogfood" section with the exact recipe.
  (c) Wait for UI-13+ deployed surface, which earns its own
      brief covering certificate provisioning + auth + push
      fan-out at scale.
```

UI-12b explicitly does NOT:

```text
- Generate certificates.
- Prompt the operator to install one.
- Add a /api/push response field for "https-required".
- Emit a console.warn or any other client-side nudge about
  HTTPS.
- Add a server-side check that refuses POST /api/push/* over
  non-localhost HTTP. The browser's secure-context gate
  already prevents the surface from ever reaching the POST
  handlers in that case (PushManager.subscribe returns
  before any fetch); a server-side refusal would be
  redundant + would leak operator intent into the response.
```

The unsupported branch is the graceful degradation; pin §11.6.11
binding. Codex P1 from UI-12 (binding): the unsupported branch
degrades to PASSIVE READ-ONLY. UI-12b reaffirms — clicking the
footer in unsupported / denied state is a no-op (no handler
attached); there is no retry prompt, no upgrade nudge, no
help-link tooltip.

ALTERNATIVES considered:

- Add a server-side `/api/push.https_warning` field that
  surfaces "you're on HTTP, push won't work". Rejected: the
  browser already tells the operator (no PushManager); a
  Karasu-side warning would be either redundant or wrong.
- Auto-redirect the surface to HTTPS via mkcert when
  `karasu ui` detects a non-localhost bind. Rejected: scope
  creep; UI-12b is not a TLS terminator.
- Render a footer copy variation on HTTP outside localhost
  ("Notifications: requires HTTPS"). Rejected: the
  unsupported branch already renders "Notifications:
  unsupported" — adding a fifth state inflates the modal-
  unreachable copy without earning anything.

`[CONFIRMED 2026-05-06]`

## 3.5 · Operator pin (binding when sign-off lands)

PROPOSAL — paralleling UI-10 §3.5 + UI-11 §3.5 + UI-12 §3.5:

```text
Subscribe UX must read as the operator deliberately accepting
a hand on the shoulder, not as Karasu installing itself in the
notification tray. Three felt properties:

  1. Categories first, native prompt second. The first click
     on the footer must reveal categories BEFORE the browser
     permission prompt. The native prompt is the second step,
     after the operator confirmed which categories they want
     to be reachable on.

  2. Cancel anywhere leaves no trace. Modal Cancel, Esc,
     backdrop click, native permission deny — any of these
     leaves the surface identical to before the click. No
     partial state, no orphan store entries, no
     human_decision event written for cancelled paths. The
     bus is the audit log; cancelled paths are not audit
     events.

  3. Unsubscribe is one click away from subscribe. Reopening
     the modal post-subscribe shows the unsubscribe verb at
     the modal foot. Operators do not hunt opt-out flows in
     OS settings, do not toggle browser-side notification
     blocks, do not edit JSON files manually.
```

How this pin shapes UI-12b implementation if accepted:

```text
- "Categories first, native prompt second" → the modal's
  primary button is "Enable notifications", NOT
  "Subscribe". confirmPushSubscribe fires
  Notification.requestPermission AFTER the operator confirms
  the categories inside Karasu's modal. If the operator denies
  the native prompt, the modal closes WITHOUT POSTing to
  /api/push/subscribe and WITHOUT writing a human_decision.
  The footer flips to "denied".

- "Cancel leaves no trace" → cancelled paths emit nothing on
  the bus. Only successful subscribes / unsubscribes emit
  human_decision events (pin §11.6.8 binding). Playwright
  tests pin all four cancel paths:
    a) Modal Cancel button.
    b) Esc.
    c) Backdrop click.
    d) Native permission deny (simulated via
       context.clearPermissions / grantPermissions(['notifications'])
       contrast).
  Each path asserts: zero bytes appended to events.jsonl,
  zero bytes in the push store delta, zero
  PushManager.subscribe calls fired, zero POSTs, zero store
  delta. The native-deny path additionally asserts: exactly
  one Notification.requestPermission call fired and resolved
  to "denied"; PushManager.subscribe was NEVER called (browser
  permission denial short-circuits before subscribe per the
  Web Push API contract).

- "Unsubscribe one click away" → reopening the modal post-
  subscribe shows the unsubscribe verb at the modal foot, in
  --fg-2 weight (NOT --danger; unsubscribing is reversible
  by re-subscribing).

- The operator-feel test: when Victor (or any operator)
  hits the footer affordance for the first time, the click
  should feel like opening a quiet preferences pane that
  ASKS before it pings them, not like installing an app
  that demands permission to keep itself relevant. Codex
  audit on the implementation .webm verifies this. Pin
  §11.6.12 of UI-12 (operator-feel .webm) carries forward.
```

`[CONFIRMED 2026-05-06]`

## 4 · Tech stack (delta vs UI-0 / UI-12 §4)

UI-12 §4 still holds. UI-12b deltas:

```text
- The server gains TWO new POST handlers (subscribe +
  unsubscribe), both 204, both /api/* (network-only by SW
  construction).
- src/karasu/ui/push_store.py gains writer functions
  (append_subscription, remove_subscription, atomic_write
  helper). The reader functions UI-12a shipped do NOT
  change.
- sw.js gains push + notificationclick listeners.
  CACHE_NAME bumps to karasu-ui-v12b. Fetch handler
  ordering NOT modified.
- static/js/push.js (new file): wires the footer click →
  modal → confirm flow. ~150 LOC.
- modal.css (or push.css under modal/ scope): materialises
  .modal-push-* micro-elements UI-12 §5.2 already pre-spec'd.
- No new build / framework / runtime dependency. The
  cryptography exception (pin §11.6.13) does NOT activate
  in UI-12b — the chunk ships with manual VAPID seeding and
  no signing.
```

## 5 · Design system (delta vs UI-12 §5)

UI-12 §5 already specified the `.modal-push-*` micro-elements.
UI-12b implements them; no new tokens, no new primitives.

### 5.1 · Reuse, do not invent

Tokens unchanged. `.modal` primitive (UI-10), `.modal-push-categories`
/ `.modal-push-category` / `.modal-push-state` /
`.modal-push-unsubscribe` (UI-12 §5.2) all materialise in
`modal.css` under `.modal` scope per pin §0.5.8 (UI-11 carry-
forward).

### 5.2 · Footer click handler (delta vs UI-12a)

The `.footer-push` affordance shipped passive in UI-12a. UI-12b
adds:

```text
- A click handler that opens the modal IF AND ONLY IF push
  state is "off" or "on" (subscribed). Click on "denied" /
  "unsupported" remains a no-op (no handler attached at all
  in those states).
- The handler is wired in static/js/push.js and gated by the
  same browserPushSupport() short-circuit UI-12a uses.
- DOM shape: footer slot is a <button> when the click handler
  is attached, otherwise a <span>. The DOM swap happens on
  UI-12a load; UI-12b inherits the structure (no UI-12a
  regression — the button vs span distinction was already
  the contract).
- tabindex / role / keyboard activation: <button> gives Tab
  focus + Enter activation natively. No custom keyboard
  handler.
- Visual weight: identical to UI-12a. The button rendering
  shows NO border, NO underline, NO hover background — only
  the foreground state word changes colour per UI-12a CSS.
```

### 5.3 · Motion

Modal slide-in reuses UI-10's contract (240ms ease-out, opacity
+ translateY, reduced-motion clamps to instant). The footer
state-flip post-subscribe is a class swap (no keyframe). No new
motion in UI-12b.

### 5.4 · The crow

No new state. UI-12 §5.5 binding — push events do NOT mutate the
crow because the operator is acting on browser state, not bus
state.

### 5.5 · Visual coverage rule (UI-12a precedent)

UI-12a's third PNG covered `--accent` ("on") via the screenshot
script's eval_js override of `browserPushSupport()`. UI-12b
inherits the same approach for the modal captures: where
browser permission state would otherwise prevent a deterministic
PNG, the screenshot script overrides the browser-state hook
inside Playwright. Production CSS — not the override — owns the
pin §11.6.11 PASSIVE READ-ONLY contract; the screenshots prove
the rendering, not the gate.

## 6 · Roadmap

UI-12b is one chunk:

```text
- POST /api/push/subscribe (204 + emits push_subscribe)
- POST /api/push/unsubscribe (204 + emits push_unsubscribe)
- push_store writer (append, remove, atomic write, mode 0600,
  loud-stderr warning on looser POSIX mode)
- VAPID key gating (503 + manual-seed doc when missing)
- .modal-push-* materialisation in modal.css
- .footer-push click handler in push.js
- sw.js push + notificationclick listeners + CACHE_NAME bump
- tests/test_ui_sw.py (or Playwright equivalent) shape-lock
  test for the three fetch handler branches; commit pre-dates
  sw.js diff
- HTTP shape locks for both POSTs in tests/test_ui_server_http.py
- Playwright: cancel + confirm + Esc + backdrop + native-deny
- 4-5 PNGs covering the modal flow + 1 .webm
- docs/event-schema.md push_subscribe + push_unsubscribe
  sections
- docs/local-dogfood.md "manual VAPID seed" section + (if
  scope allows) "TLS for cross-device dogfood" section

Target ~400 LOC including tests. UI-12 §6 PROPOSAL J binding.
```

After UI-12b:

```text
UI-12c   Server-side emit. Watcher / loop controller subscribes
         to the bus; on a category-matching event, dispatches a
         Web Push to every opted-in subscription for that
         category. Adds the cryptography runtime dep per pin
         §11.6.13 (named, scoped exception). 410/404 prune.
         Three-layer rate limit (event-id dedupe + per-category
         debounce + UI-write suppression — UI-12 §6 UI-12c
         binding). docs/local-dogfood.md "manual VAPID seed"
         section is REMOVED in this PR (auto-generation
         replaces it). ~400 LOC. Closes the Phase 3 prototype
         exit criteria — Telegram ceases to be the only push
         channel.
```

## 7 · Audit cadence (UI-12 §7 + chunk specifics)

Every UI-12* PR carries the UI-12 §7 audit obligations forward.
UI-12b chunk-level specifics:

### 7.1 PNG coverage (4-5 total)

```text
a) Footer "off" → modal default state (categories pre-checked).
   Capture seeded with empty store; modal opened via
   eval_js footer click.
b) Modal with one category unchecked.
   Capture seeded as (a), then category checkbox toggled via
   Playwright before snapshot.
c) Modal post-subscribe (categories + unsubscribe verb visible).
   Capture seeded with one synthetic store subscription.
d) Modal reduced-motion (slide-in clamped).
   Capture with prefers-reduced-motion: reduce media query
   forced via Playwright emulateMedia.
e) Footer "on" after a successful subscribe.
   This PNG already exists from UI-12a (02-footer-push-on.png).
   UI-12b can either reuse or re-shoot; if re-shooting, the
   capture seed is a real subscribe POST flow, not a synthetic
   pre-seeded store.
```

PNG (a) and (c) are the operator-feel anchors — Codex audits
read them as "modal default" and "modal post-subscribe" and
verifies the lede + foot copy match §3-A.

### 7.2 .webm walkthrough

```text
Per pin §11.6.12 of UI-12 (operator-feel) + UI-3 audit pin
(full-shell context >= 1024×640):

  - Frame 0: footer "off", surface idle (one or two events
             on the timeline so the watchtower context is
             visible — empty surface fails the "operator-felt"
             test).
  - Frame ~1s: hover over footer affordance. No nudge, no
               tooltip, no animation. The affordance is
               quiet.
  - Frame ~2s: click footer. Modal slides in (240ms).
  - Frame ~3s: modal default state visible (lede,
               categories pre-checked, foot copy, two
               buttons).
  - Frame ~4s: click "Enable notifications". Native browser
               prompt fires (Playwright permission grant
               simulates "Allow").
  - Frame ~5s: modal closes. Footer flips to "on"
               (--accent on the state word).
  - Frame ~6s: re-click footer. Modal reopens with
               post-subscribe layout.
  - Frame ~7s: click "Unsubscribe this browser".
  - Frame ~8s: modal closes. Footer flips back to "off".

Total ~9 seconds. Single Playwright context. ~250 KB output
(matches UI-6 / UI-12a precedent). No ffmpeg transcode.
```

Codex audits the .webm against the operator-feel pin: "does the
flow read as the operator deliberately enabling a quiet
hand-on-shoulder, or as Karasu installing itself in the
notification tray?" If it reads as the latter, that is a P0 —
the operator-feel pin is binding.

### 7.3 HTTP shape locks for both POSTs

In `tests/test_ui_server_http.py`, additive section. Cases:

```text
POST /api/push/subscribe:
  - Valid → 204, NO body, store updated, push_subscribe
            event on bus.
  - Missing field → 422.
  - Invalid category → 422.
  - Empty categories → 204 (allowed; bus event records
                       empty array).
  - Oversize body → 413.
  - Idempotent duplicate → 204; categories updated; new
                            push_subscribe event emitted.
  - Endpoint not HTTPS → 422.
  - VAPID keys absent in store → 503; NO bus event
                                  emitted; NO store mutation.

POST /api/push/unsubscribe:
  - Valid (endpoint in store) → 204, NO body, store
                                 updated, push_unsubscribe
                                 event on bus.
  - Missing endpoint → 422.
  - Endpoint not HTTPS → 422.
  - Endpoint not in store → 404; NO bus event; NO store
                             mutation.
  - Oversize body → 413.
```

### 7.4 Privacy negative-shape test (mirrors UI-12a)

```text
Setup:
  - Synthetic store with a known sentinel endpoint
    "https://test.example/sentinel-DO-NOT-LEAK-7d9f2e".
  - Synthetic p256dh / auth values containing
    "DO-NOT-LEAK-KEYS".
Triggers:
  - Subscribe POST against the sentinel endpoint.
  - Unsubscribe POST against the sentinel endpoint.
Assertions (all three MUST pass):
  - Bus events for push_subscribe + push_unsubscribe contain
    data.endpoint_hash but NOT the raw endpoint, NOT the
    p256dh, NOT the auth.
  - GET /api/push response body contains
    subscription_count + vapid_public_key but NOT the raw
    endpoint, NOT the p256dh, NOT the auth.
  - Captured INFO + DEBUG + ERROR log lines (collected via
    caplog) contain the endpoint_hash but NOT the raw
    endpoint anywhere.
  - All three sentinel substrings ("DO-NOT-LEAK-7d9f2e",
    "DO-NOT-LEAK-KEYS") are absent from every observable
    surface.

Error-path sentinel coverage (Codex P1 round 1, 2026-05-06):
  Privacy is auditable on the happy path AND on every error
  branch that accepts an endpoint in the request body. The
  test MUST additionally trigger:
    - POST /api/push/subscribe with a malformed endpoint
      (does not match the HTTPS regex) carrying the
      sentinel substring → 422.
    - POST /api/push/subscribe with categories outside the
      enum, body still carrying the sentinel endpoint → 422.
    - POST /api/push/subscribe with VAPID keys absent in
      the store, body carrying the sentinel endpoint → 503.
    - POST /api/push/subscribe with body size > 4 KiB,
      sentinel endpoint embedded inside oversized payload
      → 413.
    - POST /api/push/unsubscribe with an endpoint that is
      NOT in the store but IS sentinel-bearing → 404.
    - POST /api/push/unsubscribe with a malformed endpoint
      → 422.
  For each error branch, assert:
    - HTTP response body is generic (no sentinel substring,
      no raw endpoint, no keys).
    - Bus has zero new events emitted.
    - Store has zero delta (read store hash before + after,
      assert equal).
    - Captured logs contain neither sentinel substring.

Malformed-body sentinel coverage (Codex P1 round 2, 2026-05-06):
  JSON-parse-failure and non-object-body branches sit BEFORE
  field-level validation; an implementation that surfaces
  json.JSONDecodeError text or echoes raw bytes can leak
  sentinel material from a malformed payload. The test MUST
  additionally trigger:
    - POST /api/push/subscribe with a request body that is
      NOT valid JSON, sentinel substring embedded in the
      raw bytes (e.g. b'{"endpoint": "https://...DO-NOT-LEAK..."'
      with the trailing brace truncated) → 400.
    - POST /api/push/subscribe with a top-level JSON array
      whose only element is a sentinel-bearing object → 422.
    - POST /api/push/subscribe with a top-level JSON string
      that contains the sentinel substring → 422.
    - POST /api/push/unsubscribe with a non-JSON body
      carrying the sentinel substring → 400.
    - POST /api/push/unsubscribe with a top-level JSON
      number (e.g. `42`) → 422.
  For each malformed-body branch, assert:
    - HTTP response body matches one of the two generic
      shapes ({"error": "invalid request"} or
      {"error": "request body must be an object"}).
    - Sentinel substring absent from response body.
    - No json.JSONDecodeError text in response body.
    - No line / column offsets in response body that could
      leak fragment positions.
    - Bus has zero new events; store has zero delta.
    - Captured logs contain no sentinel substring AND no
      json.JSONDecodeError repr (the parser exception is
      caught + logged at WARNING with a generic
      "malformed body" message; the underlying exception
      message is NOT logged).

  The malformed-body assertions close the gap that JSON
  parser errors could otherwise leak request fragments via
  exception messages or echoed bodies. Pin §11.6.5 extended
  in round 2.
```

### 7.5 SW fetch ordering shape-lock test (§3-D)

The three-branch test specified in §3-D. Commit lands FIRST in
the PR. SW diff lands SECOND. CI failure on the test commit is
a regression on baseline; SW diff cannot land until baseline
passes.

### 7.6 Documentation

```text
docs/event-schema.md
  Additive section under "human_decision":
    push_subscribe   data.action, data.endpoint_hash,
                     data.categories
    push_unsubscribe data.action, data.endpoint_hash

docs/local-dogfood.md
  New section: "Manual VAPID seed (UI-12b)".
    Lists the openssl commands above + the JSON snippet
    shape. Notes the section is REMOVED when UI-12c lands.
  Optional new section (if scope allows): "TLS for cross-
    device dogfood" with the mkcert + caddy recipe.
```

### 7.7 Lighthouse

Re-run after the chunk lands; thresholds unchanged from UI-10
baseline (Performance 85, Accessibility 95, Best Practices 95,
SEO 90 — UI-9.1 procedural lock). The variance window
documented post-UI-10 / post-UI-11 still applies.

## 8 · Frozen contracts (UI-12b MUST respect)

Same as UI-12 §8 + UI-12a additive contracts:

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol — all frozen.
- The bus event schema (additive only; UI-12b's
  push_subscribe / push_unsubscribe fields are additive on
  human_decision).
- The /api/push read shape from UI-12a (state, categories,
  subscription_count, vapid_public_key) MUST NOT change in
  UI-12b. New fields require an EVENTS_PROJECTION_KEYS
  update + shape lock in the same PR.
- The push_store reader functions from UI-12a MUST NOT
  change. The writer functions are strictly additive.
- The /api/events / /api/health / /api/meta / /api/scars /
  /api/agents / /api/push projection shapes pinned by
  tests/test_ui_server_http.py.
- The SW fetch handler ordering from UI-8. UI-12b's push +
  notificationclick listeners are SEPARATE SW event types
  and do NOT modify fetch ordering — pin §11.6.12 + the
  shape-lock test prove this.
- The Lighthouse threshold contract.
- The 86 binding pins inherited (52 base + 6 UI-10 + 12
  UI-11 + 16 UI-12).
- Out-of-band Codex audit (no `@codex review` tag, no
  ChatGPT Codex Connector — operator-mediated only).
```

## 9 · Out of scope for UI-12b

```text
- Server-side push emission. Pin §11.6.13 binding — the
  cryptography dep + VAPID JWT signing land with UI-12c.
  UI-12b ships the client-side subscribe path; the server
  has no way to actually deliver pushes yet.
- VAPID key auto-generation. UI-12b requires the operator
  to seed the keys manually; UI-12c automates this and
  removes the manual-seed doc section in the SAME PR.
- VAPID key rotation. UI-12 §10.4 [CONFIRMED 2026-05-05]
  binding — no rotation in UI-12b or UI-12c.
- A push bypass for testing (e.g. `karasu push --to <hash>`
  CLI). UI-12c+ scope.
- Multi-device fan-out logic. The endpoint is the natural
  per-browser identity; UI-12c's emit dispatches one HTTP
  request per active subscription per category match
  (pin §11.6.15 binding). UI-12b just persists the
  subscriptions.
- Any UI affordance for managing OTHER browsers'
  subscriptions (e.g. "list 3 subscribed browsers" in the
  modal). The modal acts on THIS browser only; multi-device
  subscription management earns a future brief.
- HTTPS provisioning automation. The dev surface assumes
  localhost; the LAN-dogfood case is deferred to
  docs/local-dogfood.md "TLS for cross-device dogfood".
- Permission re-prompting after a denial. UI-12b's
  unsupported / denied branch is terminal until the
  operator flips OS-level permission. No retry prompt.
- Per-event push opt-in. Categories are coarse (UI-12 §3-G
  binding); finer granularity earns its own brief.
- Notification bodies. UI-12 §3-H binding — title-only,
  empty body. Richer payloads earn a future brief once the
  editorial-line discipline is dogfood-validated.
- iOS Safari Home-Screen-PWA install nudges. UI-12 §9
  binding — degrades to passive read-only without a nudge.
- Service worker push REPLAY (queueing pushes while
  offline). UI-12 §9 binding — fire-and-forget; replay is
  the push service's concern.
- Authentication. UI-12 §3-C [CONFIRMED 2026-05-05] —
  local-only.
```

## 10 · Open questions (operator sign-off needed)

```text
1. Pre-checked categories on first subscribe.
   PROPOSAL — all three pre-checked.
   Already CONFIRMED 2026-05-05 via UI-12 §10.2; carried
   forward into THIS brief verbatim. Reaffirm on UI-12b
   sign-off so the chunk-level brief lists the binding
   contract explicitly.
   [CONFIRMED 2026-05-06 — carried forward from UI-12 §10.2]

2. Idempotent subscribe behavior.
   PROPOSAL — duplicate subscribe (same endpoint) is treated
   as an UPDATE: the existing entry's categories are
   overwritten with the new validated set, created_at is
   preserved, updated_at refreshes. The bus emits a fresh
   push_subscribe event regardless (the operator's intent
   is authoritative).
   ALTERNATIVE — duplicate subscribe is a 409 Conflict; the
   operator must unsubscribe first. More conservative;
   surfaces drift sooner. Rejected by PROPOSAL because the
   operator-feel pin §3.5 binding ("cancel leaves no trace")
   implies "confirm leaves the obvious effect" — overwriting
   categories is the natural outcome of a confirmed flow,
   and 409-then-unsubscribe is friction without a payoff.
   [CONFIRMED 2026-05-06]

3. Unsubscribe modal layout.
   PROPOSAL — same modal as subscribe, opened post-subscribe.
   Bottom secondary button "Unsubscribe this browser"
   closes the modal AFTER firing POST /api/push/unsubscribe.
   Confirm dialog NOT shown — the unsubscribe IS the
   friction; one click + 204 + modal closes + footer flips
   to "off".
   ALTERNATIVE — second-stage confirm modal ("Are you
   sure?"). Rejected because unsubscribing is reversible
   (re-subscribe is one click away) and the operator-feel
   pin opposes friction layers without a destructive
   payoff.
   [CONFIRMED 2026-05-06]

4. Update-categories-only flow.
   PROPOSAL — when the modal reopens post-subscribe and the
   operator changes which categories are checked, "Update
   categories" emits a push_subscribe event (idempotent
   path, §10.2 above) WITHOUT calling
   PushManager.subscribe again. The browser subscription is
   unchanged; only the server-side store + the bus event
   reflect the new selection.
   Note: this is the ONLY path that POSTs
   /api/push/subscribe without firing the native permission
   prompt. The endpoint is already present in the store;
   the WRITER's idempotent branch just updates categories.
   Endpoint sourcing (Codex P2 round 1, 2026-05-06): the
   endpoint posted on the update-categories path MUST be
   read from
   `registration.pushManager.getSubscription()` — i.e.
   from the browser's live PushSubscription object — and
   NEVER from /api/push, the DOM, localStorage, sessionStorage,
   any prior server projection, or any cached client-side
   value. The browser is the sole source of truth for the
   raw endpoint; every other surface holds only the hash.
   ALTERNATIVE — split the path into a third endpoint
   (POST /api/push/categories) so subscribe is always
   accompanied by a fresh PushManager.subscribe. Rejected:
   adds a third write endpoint for one user-flow that is
   indistinguishable from "operator changed their mind on
   categories"; doubles the privacy contract surface for
   no operational gain.
   [CONFIRMED 2026-05-06]

5. Body cap parity (4 KiB on both POSTs).
   PROPOSAL — both subscribe and unsubscribe accept up to
   4 KiB. Subscribe carries the full PushSubscription dict
   (~600 bytes real-world); unsubscribe carries only the
   endpoint URL (~200 bytes real-world). 4 KiB is generous
   for both and lets one cap constant cover both endpoints.
   ALTERNATIVE — 2 KiB cap on unsubscribe (smaller attack
   surface for the bare-endpoint POST). Rejected for
   testing simplicity — uniform cap = one shared constant +
   one shared 413 branch. The privacy boundary is not the
   body size; it's the never-log, never-project discipline
   (§3-B + §3-E).
   [CONFIRMED 2026-05-06]

6. Esc precedence with both modals concurrent.
   PROPOSAL — UI-12b modal cannot stack with another modal
   (the surface has only one modal type per chunk). First
   Esc closes the modal; second Esc closes whatever drawer
   is under it (UI-7); third Esc clears focus to body.
   Same as UI-10 §10.6 + UI-11 §10.6 + UI-12 §10.7.
   Already CONFIRMED 2026-05-05 via UI-12 §10.7; carried
   forward verbatim.
   [CONFIRMED 2026-05-06 — carried forward from UI-12 §10.7]

7. Native permission denial UX.
   PROPOSAL — if the operator clicks "Enable notifications"
   and then denies the native browser prompt:
     1. The modal closes immediately (no error toast).
     2. The footer flips to "denied" (--warn).
     3. NO POST is sent (the browser never produced a
        PushSubscription).
     4. NO human_decision is emitted (cancelled path; pin
        §3.5 binding — "cancel leaves no trace").
   Re-enabling requires OS-level permission flip; the modal
   is unreachable until then.
   [CONFIRMED 2026-05-06]

8. Manual VAPID seed instructions in docs/local-dogfood.md.
   PROPOSAL — UI-12b adds a section with the openssl command
   lines + the JSON snippet shape. UI-12c removes the
   section in the SAME PR that lands the cryptography dep
   (auto-generation supersedes manual seed).
   [CONFIRMED 2026-05-06]

9. TLS-for-dogfood doc section.
   PROPOSAL — UI-12b adds (if scope allows) a
   "TLS for cross-device dogfood" section in
   docs/local-dogfood.md with the mkcert + caddy recipe.
   ALTERNATIVE — defer to a separate doc-only PR after
   UI-12b merges so the chunk LOC budget is preserved.
   ~30 LOC of doc, no code. Rejected by PROPOSAL because the
   TLS gap is the most likely operator-felt friction in
   UI-12b dogfood; surfacing it in the same chunk that ships
   the modal closes the loop.
   [CONFIRMED 2026-05-06]

10. Footer DOM swap timing.
    PROPOSAL — the <button> vs <span> distinction is decided
    on UI-12a's loadPushState() call. UI-12b inherits the
    structure unchanged; the click handler attaches to the
    <button> when push state is "off" or "on" and detaches
    (or never attaches) when state is "denied" or
    "unsupported". State transitions during the session
    (e.g. operator subscribes, footer was a <button> for
    "off", stays a <button> for "on") do NOT swap the DOM
    element type; only the textContent + class swap.
    [CONFIRMED 2026-05-06]
```

## 11 · Definition of "done" — UI-12b

```text
- One PR, ~400 LOC including tests + docs.
- POST /api/push/subscribe + POST /api/push/unsubscribe + 204
  on success, validation per §3-B.
- HTTP shape locks for both POSTs.
- Privacy negative-shape test (raw endpoint never on bus,
  never in /api/push body, never in any log capture).
- push_store writer: append + remove + atomic write + mode
  0600 enforcement on POSIX + loud-stderr warning on looser
  observed mode.
- VAPID key gating: 503 + manual-seed doc when missing.
- .modal-push-* styles in modal.css (additive, scoped under
  .modal per pin §0.5.8).
- static/js/push.js: openPushModal + confirmPushSubscribe +
  confirmPushUnsubscribe + wirePushModal + footer click
  handler.
- sw.js push + notificationclick listeners + CACHE_NAME
  bump (karasu-ui-v8 → karasu-ui-v12b).
- tests/test_ui_sw.py (or Playwright route-stub equivalent)
  shape-lock test pinning the three fetch handler branches;
  commit pre-dates sw.js diff.
- Playwright cancel + confirm + Esc + backdrop + native-deny
  tests (5 paths total).
- 4-5 PNGs covering the modal flow (footer-off → modal-default
  → modal-one-unchecked → modal-post-subscribe → footer-on)
  + 1 .webm walking the full edge-to-edge flow.
- docs/event-schema.md updated with push_subscribe +
  push_unsubscribe sections.
- docs/local-dogfood.md updated with manual VAPID seed
  section (and optionally the TLS-for-dogfood section per
  §10.9).
- Lighthouse re-run after the chunk lands; thresholds
  unchanged from UI-10 baseline (variance window honoured).
- Codex audit returns APPROVED or APPROVED-with-observations.
- Brief PR (THIS doc) merged BEFORE UI-12b code branch
  opens.
```

## 11.6 · Implementation pins (Codex audit, pending)

Sixteen pins set by Codex on the UI-12b brief audit (round 1
CHANGES-REQUIRED, 2026-05-06; in-branch fixes applied to §3-A /
§3-B / §3-E / §3.5 / §7.4 / §10.4 / §11.6 before re-audit).
All bind UI-12b implementation. Verbatim:

```text
1.  Modal entry MUST be footer-only; no other surface opens
    it (footer is the affordance, modal is the gate).
2.  Cancel paths MUST NOT mutate the bus or the store.
    Playwright pins all four cancel paths plus the
    POST-failure rollback path.
3.  Native permission prompt MUST fire only after modal
    confirm. PushManager.subscribe MUST NOT be called when
    Notification.requestPermission resolves to "denied" or
    "default" (browser API contract — there is no fired-and-
    rejected subscribe call on a denied permission; the
    permission gate short-circuits before subscribe).
4.  SW fetch-ordering shape-lock test MUST pre-date the
    sw.js diff in the PR commit ordering.
5.  Privacy negative-shape test MUST cover both POSTs +
    /api/push body + log capture (raw endpoint absent
    everywhere) AND every error branch that accepts or
    parses request body material, including 400 / 422 /
    404 / 413 / 503. The 400 branch (malformed JSON / non-
    UTF-8 bytes) and the 422 branches (non-object body,
    field-level validation) are mandatory because they
    fire BEFORE field validation and can leak request
    fragments through parser exception messages or echoed
    bodies if the implementation is sloppy. Sentinel-
    substring assertions are mandatory on every error
    response body, every captured log, every store delta,
    every bus event count, and every JSONDecodeError /
    UnicodeDecodeError repr.
6.  Idempotent subscribe MUST emit a push_subscribe event
    each time (operator's intent is authoritative).
7.  0600 mode warning MUST surface when the writer
    encounters looser permissions on POSIX. Warning MUST
    NOT silently re-mode the existing file.
8.  Manual VAPID seed instructions MUST be removed from
    docs/local-dogfood.md when UI-12c lands (the UI-12c
    PR body covers the doc deletion).
9.  Categories validation MUST reject duplicates and
    out-of-enum values at 422; empty array MUST remain
    allowed as a deliberate zero-noise subscription
    (§3-B). The store + the bus event record the empty
    array verbatim; UI-12c emit will simply never match
    for that endpoint until categories are updated.
10. The .webm MUST read as deliberate operator intent, not
    as a settings panel flow (operator-feel pin from
    UI-12 §11.6.12 carry-forward).
11. /api/push read shape from UI-12a MUST NOT change.
12. push_store reader functions from UI-12a MUST NOT change.
13. Browser ⇄ store two-phase mutation MUST be transactional
    (§3-B). Subscribe: any non-204 server response triggers
    subscription.unsubscribe() rollback BEFORE user-visible
    feedback; no human_decision emits on rollback paths.
    Unsubscribe: server-removal-first (POST), then
    subscription.unsubscribe(). The 404 path is treated as
    browser-cleanup success (both sides converge to
    "unsubscribed") AND emits ZERO bus events (the server
    did not mutate, so the bus carries no new
    push_unsubscribe — composes with §7.3 server contract).
    Audit-event correspondence: exactly one push_unsubscribe
    on the bus per server-side store mutation; the 204 path
    emits one, the 404 convergence path emits zero. The
    Playwright suite pins:
      - subscribe rollback (POST failure → browser
        unsubscribe → no bus event)
      - post-204 unsubscribe (POST 204 → browser unsubscribe
        → exactly one bus event)
      - 404 convergence (POST 404 → browser unsubscribe →
        zero bus events)
      - post-204 browser-rejection retry (first attempt 204
        emits one event, browser-unsubscribe rejects;
        second attempt 404 emits zero; total bus count = 1)
14. The frontend MUST short-circuit BEFORE
    Notification.requestPermission when /api/push.vapid_public_key
    is null. The modal opens (so the operator finds out
    why), the primary button is DISABLED, and no native
    permission prompt fires from this state. Server-side
    503 stays as defensive behaviour for forged / stale
    clients that bypass the preflight.
15. The push_store WRITER MUST hold a module-level
    threading.Lock across the FULL read-modify-write
    transaction (read + mutate + write + rename). The
    atomic tmp+rename does NOT alone prevent lost updates;
    the lock does. Multi-process scope (filesystem
    lockfile) is out of UI-12b; UI-12c re-audits this
    boundary.
16. The update-categories-only POST endpoint MUST be
    sourced from registration.pushManager.getSubscription()
    — i.e. from the browser's live PushSubscription object
    — and NEVER from /api/push, the DOM, localStorage,
    sessionStorage, any prior server projection, or any
    cached client-side value. The browser is the sole
    source of truth for the raw endpoint.
```

Pins 1-10 + 12 parallel UI-10 §11.6 / UI-11 §11.6 / UI-12
§11.6 contracts (drawer / modal / scope / privacy / schema /
operator-feel). Pin 11 freezes the UI-12a read shape. Pins
13-16 are the four bindings Codex set on round 1
specifically for UI-12b (P0 two-phase mutation, P1 VAPID-null
UI behavior, P1 writer lock, P2 endpoint sourcing
discipline). Pin 9 was rewritten in round 1 to remove the
internal contradiction with §3-B (empty categories allowed
as zero-noise subscription). Pin 5 was extended in round 1
(error-body sentinel assertions) and again in round 2
(malformed-JSON / non-object-body sentinel assertions). Pin
3 was clarified in round 1 to remove the
"fired-and-rejected PushManager.subscribe" misstatement.
Pin 13 was extended in round 2 to incorporate the 404
no-event clarification (server emits zero events on the
404 path; browser still converges via subscription.unsubscribe()).
Round 2 also removed a §3-B reference to a future
`/api/push.subscriptions` raw-endpoint projection that
would have violated pin §11.6.11 (frozen UI-12a read
shape) + pin §11.6.16 (raw endpoint never on /api/*).

## 12 · Status

```text
Brief status:        APPROVED-with-observations + operator
                     sign-off complete. Mergeable.
Operator sign-off:   COMPLETE (2026-05-06). Every §3 (A-F) +
                     §3.5 + §10 (1-10) PROPOSAL accepted as
                     the binding contract per default. The
                     two §10 questions carried forward from
                     UI-12 (§10.1 pre-checked categories,
                     §10.6 Esc precedence) reaffirmed without
                     deviation.
Codex audit:         Round 1: CHANGES-REQUIRED (1 P0 + 5 P1
                     + 1 P2). All seven findings addressed
                     in-branch:
                       P0  §3-B browser-store two-phase
                            rollback contract added.
                       P1  §3-E + §3-F VAPID-null UI
                            behavior defined (modal opens
                            but primary disabled; no native
                            prompt; server 503 defensive).
                       P1  §3-E module-level threading.Lock
                            added across full read-modify-
                            write transaction.
                       P1  §7.4 privacy negative-shape test
                            extended to cover all error
                            branches (422 / 404 / 413 / 503).
                       P1  §3.5 native-deny assertion
                            corrected (Notification permission
                            denial short-circuits before
                            PushManager.subscribe; zero
                            subscribe calls on deny path).
                       P1  §11.6 anticipated pin 9
                            contradiction with §3-B fixed
                            (empty categories allowed; only
                            duplicates + out-of-enum
                            rejected).
                       P2  §10.4 update-categories-only
                            endpoint sourcing pinned to
                            registration.pushManager
                            .getSubscription() (never DOM /
                            localStorage / cached values).
                     Pins 13-16 added to §11.6; pin 5 + pin 9
                     extended; pin 3 clarified.

                     Round 2: CHANGES-REQUIRED (3 P1 + 1 P2).
                     All four findings addressed in-branch:
                       P1  §3-B unsubscribe 404 audit-event
                            ambiguity fixed (404 path emits
                            zero bus events; audit_emitted
                            flag tracks state). Pin 13
                            extended.
                       P1  §3-B `/api/push.subscriptions`
                            raw-endpoint projection
                            reference removed (would have
                            violated pin §11.6.11 +
                            §11.6.16). Orphan handling
                            deferred to UI-12c 410 prune.
                       P1  §3-B + §7.4 malformed JSON +
                            non-object body validation rows
                            added (400 / 422 with generic
                            bodies; no JSONDecodeError text;
                            no offset leakage). Pin 5
                            extended again.
                       P2  Third + fourth Playwright tests
                            added (404 convergence,
                            post-204 browser-rejection retry).

                     Round 3: APPROVED-with-observations
                     (1 P2). Finding addressed in-branch:
                       P2  Pin 5 verbatim wording extended
                            to name 400 explicitly alongside
                            422 / 404 / 413 / 503; mandatory
                            sentinel assertions on every
                            JSONDecodeError / UnicodeDecodeError
                            repr called out.

                     Codex audit CLOSED at round 3 of 5.
                     Loop budget: 3 of 5 consumed.
                     Sixteen §11.6 pins ratified as binding.
Implementation:      BLOCKED on this brief's merge.
                     UI-12b code branch does NOT open until
                     this brief lands in main per UI-9
                     audit pin #1 / UI-12 §11.6 carry-
                     forward.
```

The brief follows the lifecycle `ui-10-design-brief.md` (PR
#83), `ui-11-design-brief.md` (PR #87), and `ui-12-design-brief.md`
(PR #93) went through:

```text
1. Implementer drafts the brief as a doc-only PR with
   sign-off markers.
2. Operator reviews and confirms ("segun tus criterios" or
   per-marker). Markers flip to a confirmed-date stamp.
3. Implementer entrega the audit prompt copy-paste to the
   operator immediately.
4. Codex audits the brief; verdict ferried back via the
   operator. Round 1 typically returns 1-2 P0 + a handful
   of P1/P2.
5. Implementer applies follow-ups in-branch. Re-audit
   triggered when Codex round 1 was CHANGES-REQUIRED with
   P0 (THIS brief's case); APPROVED-with-observations +
   P1/P2 land as in-branch follow-ups without a re-audit.
6. Brief PR merges BEFORE the UI-12b code branch opens.
```
