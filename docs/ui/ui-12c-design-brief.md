# Karasu UI — UI-12c Design Brief (server-side push emit)

> Doc-only seal of the visual + structural direction for UI-12c
> specifically. Earned per UI-9 audit pin #1 / UI-12 §11.6.13
> carry-forward: any UI-N that introduces write paths OR new
> runtime dependencies must earn a brief before code. UI-12c
> introduces the FIRST proactive outbound HTTP write surface
> AND the named, scoped `cryptography` runtime dep — both
> earn their own contract sealing here.
>
> Audited and merged BEFORE any UI-12c code chunk opens.
>
> Parallel to:
> - `ui-0-design-brief.md`   (UI-1..UI-9 read-only MVP)
> - `ui-10-design-brief.md`  (UI-10 scar revoke)
> - `ui-11-design-brief.md`  (UI-11 trust adjust)
> - `ui-12-design-brief.md`  (UI-12 family — 16 §11.6 binding pins)
> - `ui-12b-design-brief.md` (UI-12b push opt-in surface)
>
> The UI-12 parent brief is the architecture-level seal for
> the UI-12 family. The UI-12b chunk-level brief sealed the
> client-side write paths. UI-12c earns its OWN chunk-level
> brief because it (a) introduces the cryptography dep — the
> first named, scoped exception to UI-0 §4 since the project
> began; (b) opens an outbound HTTP write surface — Karasu
> calling out to Web Push services; (c) closes Phase 3 exit
> criteria — once UI-12c lands, Telegram ceases to be the
> only push channel.
>
> **STATUS:** CONFIRMED — operator sign-off complete (Victor,
> 2026-05-06: "avanzar" — every default PROPOSAL accepted as
> the binding contract). Codex audit pending out-of-band.

## 0 · Why this brief exists

Codex pin §11.6.13 from the UI-12 brief (PR #93), reaffirmed
verbatim by UI-12b round 2 audit (PR #102):

> *"UI-12c is the only approved dependency exception for Web
>  Push signing. The exception applies ONLY to `cryptography`
>  inside the UI-12c push emit module. Imports outside that
>  module are a regression. The exception does NOT
>  generalise; future chunks asking for additional deps
>  re-open the UI-0 §4 conversation per chunk."*

UI-12a (PR #98) shipped the read display. UI-12b (PR #102)
shipped the write paths — the operator subscribes a browser,
the store records the subscription, the bus emits a
`push_subscribe` `human_decision`. UI-12c is the chunk that
closes the loop: a bus subscriber that classifies events into
push categories, signs VAPID JWTs, and dispatches Web Push
deliveries to every opted-in subscription.

UI-12c is qualitatively different from UI-12a / UI-12b in
three ways:

```text
1. The first proactive OUTBOUND HTTP surface. UI-1..UI-12b
   were strictly request/response — operator polled, surface
   responded. UI-12c lets Karasu reach OUT to Web Push
   services (FCM / APNs / Mozilla autopush). Each delivery
   is a fresh outbound request with VAPID-signed
   credentials. The privacy contract pin §11.6.16 carries
   forward verbatim — raw endpoints stay request-local
   secret across the delivery loop, the prune loop, log
   lines, and bus events.

2. The first runtime dependency exception. UI-0 §4 forbids
   "new build / framework / runtime dependencies". UI-12
   §11.6.13 carved a single, named, scoped exception for
   `cryptography` (the package required for ECDSA P-256
   JWT signing). UI-12c is where that exception
   materialises. The brief locks the import scope in a way
   that future chunks cannot accidentally re-open the
   UI-0 §4 conversation.

3. The first cross-process boundary on the push store. UI-12b
   shipped the store WRITER under a module-level
   threading.Lock (pin §11.6.15) — sufficient for a single
   `karasu ui` process. UI-12c may run push_emit inside the
   `karasu watch` loop controller, in a separate process
   from the UI server. If so, the writer concurrency
   boundary graduates from in-process Lock to filesystem
   lockfile. Forward-carry pin (d) from PR #102 round 2.
```

The 106 binding pins inherited (52 base + 6 UI-10 §0.5 +
12 UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6 + 4 PR
#102 round-2 forward-carry) all carry forward verbatim.
UI-12c adds operational specificity on top — not new
architecture.

## 0.5 · Pins inherited (verbatim, binding)

### From UI-12 §11.6 — 16 pins, all binding

The pins driving UI-12c specifically:

```text
9.  UI-originated writes must not trigger correction push
    notifications.
10. Notification categories are closed to attention,
    errors, and corrections for UI-12.
13. UI-12c is the only approved dependency exception for
    Web Push signing. (Drives §3-C below.)
14. Push emit must be rate-limited and deduplicated
    before delivery. (Drives §3-D below.)
15. Multi-device fan-out must be explicit: each active
    subscription is a separate delivery target.
16. Raw push endpoints are request-local secret material
    and must never be logged, projected, emitted,
    screenshotted, or echoed.
```

Pins 1-8, 11, 12 carry forward but do not directly drive
UI-12c (they bind UI-12a / UI-12b surfaces UI-12c does
NOT touch).

### From UI-12b §11.6 — 16 pins, all binding

The pins driving UI-12c specifically:

```text
11. /api/push read shape from UI-12a MUST NOT change.
12. push_store reader functions from UI-12a MUST NOT
    change.
15. The push_store WRITER MUST hold a module-level
    threading.Lock across the FULL read-modify-write
    transaction. Multi-process scope (filesystem lockfile)
    is out of UI-12b; UI-12c re-audits this boundary.
16. The update-categories endpoint MUST be sourced from
    registration.pushManager.getSubscription() — i.e.
    from the browser's live PushSubscription object —
    and NEVER from /api/push, the DOM, localStorage,
    sessionStorage, any prior server projection, or any
    cached client-side value. (UI-12b client-side; UI-12c
    inherits the privacy invariant.)
```

Pins 1-10, 13-14 carry forward but bind UI-12b client-side
surfaces UI-12c does NOT touch.

### From PR #102 round 2 — 4 forward-carry pins

```text
(a) Do NOT change UI-12b POST response shapes or the
    /api/push read shape while adding emit. UI-12b's
    subscribe / unsubscribe / GET read contracts are now
    frozen.

(b) Remove the manual VAPID seed docs (docs/local-dogfood.md
    "UI-12b — Manual VAPID seed" section) in the SAME PR
    that introduces auto-generation. No two-step doc rot.

(c) Preserve raw endpoint privacy across push delivery,
    410/404 prune, logs, and bus events. Pin §11.6.5 +
    §11.6.16 carry forward verbatim — endpoint_hash is
    the only audit metadata; the raw endpoint stays in
    karasu-push.json (mode 0600) and in the in-flight
    POST to the push service.

(d) Re-audit the writer concurrency boundary if UI-12c
    introduces a second writer process. UI-12b's
    threading.Lock is per-process; if push_emit runs in
    a separate process, graduate to a filesystem
    lockfile (fcntl.flock on POSIX, msvcrt.locking on
    Windows) held across the same transaction.
```

The pins driving each §3 section of THIS brief:

```text
§3-A bus subscriber location:    pin (a), pin (d), §11.6.15
§3-B category classifier:        pins 9, 10
§3-C VAPID JWT signing scope:    pin §11.6.13
§3-D three-layer rate limit:     pin §11.6.14
§3-E 410/404 prune:              pin §11.6.16, pin (c)
§3-F VAPID auto-generation:      pin §11.6.13, pin (b)
§3-G writer concurrency:         pin §11.6.15, pin (d)
§3-H push payload shape:         pins §3-H of UI-12 parent
§3-I test surface:               pin §11.6.14 + UI-12 §7
```

## 1 · Positioning

UI-12a was the watchtower whispering its own state. UI-12b
was the operator opting into being whispered AT. UI-12c is
the watchtower actually whispering — but only when the bus
crosses a threshold the operator opted into, only to the
browsers the operator opted in from, and never as a
broadcast.

> A push delivery is Karasu reaching OUT to a notification
> tray the operator agreed in advance was worth breaking
> quiet for. The contract is editorial silence by default —
> the bus is the audit log, not the notification source;
> the push is the operator's deliberate exception to that
> silence.

The first second of looking at the surface before AND after
UI-12c lands must read identical. UI-12c adds NO visual
delta — it is server-side housekeeping. The footer
affordance (UI-12a) and the modal (UI-12b) already cover
the operator-facing surface. UI-12c is the loop that turns
"Subscribed: 1 subscription" into a real notification when
the bus delivers something the operator asked to be told.

## 2 · Visual references (anchors held)

UI-12c has no visual surface. The OS notification tray is
rendered by the operating system, not by Karasu's CSS. The
shape Karasu controls (title, body, icon, badge, tag, data)
is already specified in UI-12 §3-H + §5.6.

The recording artefact (1 .webm of the edge-to-edge flow)
captures the OS-rendered notification AS IT APPEARS on the
operator's tray. The capture is OS-specific and outside
Karasu's design system; the marketing-as-product anchor
cannot override the OS notification template.

## 3 · Confirmed decisions (operator sign-off complete 2026-05-06)

All decisions below confirmed binding by Victor on 2026-05-06
("avanzar" — every default PROPOSAL accepted as the binding
contract; Codex audit pending out-of-band).

### A) Bus subscriber architecture — where push_emit lives

PROPOSAL — `push_emit` runs as a registered TriggerSource
inside the `LoopController` (the same controller `karasu
watch` already uses for the watcher + Telegram surface).
This is NOT a new process. The benefits:

```text
1. Single-writer guarantee on the push store. The
   threading.Lock from UI-12b §11.6.15 binds the FULL
   read-modify-write transaction; if push_emit is in the
   same process as the UI server's POST handlers, the
   in-process Lock keeps serialising correctly.
   Forward-carry pin (d) is satisfied without graduating
   to a filesystem lockfile — the boundary stays
   in-process.

2. Bus subscription is already the controller's seam.
   Phase 2 / Phase 3 introduced JsonlTailReader for the
   Telegram surface and the bus-reaction reactor (chunk
   3b). push_emit is the third subscriber. Reusing the
   pattern keeps the controller as the single
   bus-subscription coordinator.

3. No new IPC. push_emit reads the bus events directly,
   matches them to the closed category enum, and
   dispatches outbound HTTP through stdlib urllib (or
   http.client). No new IPC primitives, no shared-memory
   ring, no threading.Queue across modules.

4. Lifecycle aligned with karasu watch. push_emit
   start()s when the controller starts and stop()s when
   the controller stops. Operator restart restarts both
   together; no orphan emit threads.

ALTERNATIVES considered:
  - Separate `karasu push-emit` daemon process. Rejected:
    forces the writer concurrency boundary to graduate
    immediately (pin (d)) AND introduces a second
    long-running daemon to monitor in production. UI-12c
    can keep the boundary in-process; the brief reserves
    the right to revisit if a future chunk introduces a
    second writer.
  - Inline inside the UI server's POST handlers. Rejected:
    push_emit is a long-running consumer, not a
    request-bound write path. Inlining would block POST
    handlers on outbound HTTP.
  - Inside `karasu serve` (the GitHub webhook receiver,
    Phase 3+ chunk 4a). Rejected: serve's responsibility
    is webhook ingestion; mixing emit responsibilities
    would conflate the two.
```

[CONFIRMED 2026-05-06]

### B) Category classifier

PROPOSAL — push_emit classifies each bus event against the
closed enum from UI-12 §3-G + pin §11.6.10. The classifier
is pure (input → category | None), runs in-process per
event, and never persists state. The same enum the modal +
the store use:

```text
attention   = agent_response with response.requires_human
              == true
              OR file_change with controller_chain_depth
                 at the controller cap (issue #47 chain
                 cap, default 3)

errors      = agent_response with dispatch.status == "failed"

corrections = human_decision with source != "ui"
              (e.g. /scar or /correct from Telegram, or a
               future inbound surface)
```

Pin §11.6.9 binding: UI-write `human_decision` events
(source == "ui" — scar_revoke, trust_adjust,
push_subscribe, push_unsubscribe) NEVER classify into
`corrections`. The filter is applied INSIDE the classifier,
not as a downstream filter, so UI-write events never
consume rate-limit dedupe slots (pin §11.6.14 ordering
binding from UI-12 §6 UI-12c).

Events outside the three categories:

```text
- file_change without trigger conditions → no category,
  no push.
- agent_response with status="completed" and
  requires_human=false → no category, no push.
- git_event → no category, no push (Phase 3+ git events
  are operator-driven, the operator already saw them).
- Future event types → no category by default; new
  categories earn their own brief.
```

The classifier returns `None` for events outside the
three categories. push_emit handles `None` by skipping;
no rate-limit slot consumed; no log line beyond DEBUG.

[CONFIRMED 2026-05-06]

### C) VAPID JWT signing path + cryptography import scope

PROPOSAL — `cryptography` is the named, scoped exception per
UI-12 §11.6.13 binding. UI-12c materialises it under TWO
new modules; no other module in the codebase may import
the package:

```text
src/karasu/push_emit/__init__.py    Public entry points
                                     (start, stop, dispatch).
                                     NO cryptography import.
src/karasu/push_emit/_signing.py    VAPID JWT signing.
                                     IMPORTS cryptography.
                                     Functions: sign_vapid_jwt,
                                     load_vapid_keys.
src/karasu/push_emit/_keys.py       VAPID auto-generation.
                                     IMPORTS cryptography.
                                     Functions:
                                     generate_vapid_keypair,
                                     bootstrap_if_missing.
```

Import scope test (pin §11.6.13 binding — round 1 P1
candidate):

```text
tests/test_push_emit_import_scope.py
  1. Walks every .py file under src/karasu/.
  2. Greps for `import cryptography`,
                `from cryptography`,
                `cryptography\.` (transitive use).
  3. Asserts the only matches are inside
       src/karasu/push_emit/_signing.py
       src/karasu/push_emit/_keys.py
  4. Test fails if a future chunk imports cryptography
     anywhere else.

The test runs in plain pytest with zero browser dependency.
Lint-style structural inspection follows the established
Karasu pattern (test_lint_ui_css.py, test_ui_sw.py).
```

JWT shape per RFC 8292 (VAPID):

```text
header  { "alg": "ES256", "typ": "JWT" }
claims  { "aud": "<push service origin>",
          "exp": <now + 12h, max 24h per RFC>,
          "sub": "mailto:<operator email>" }
signature  ECDSA P-256 over SHA-256 of
           base64url(header) + "." + base64url(claims).
```

`aud` is computed from the push subscription endpoint:
the origin (scheme + host) of the endpoint URL is the
audience the JWT is signed for. Different push services
(FCM vs APNs vs Mozilla autopush) have different origins;
each delivery's JWT is audience-bound.

`sub` is the operator's contact email. Default to a
configurable value in `karasu.yaml` (e.g.
`push.contact_email`) with a sensible placeholder
(`mailto:operator@localhost.invalid`) if absent. Real Web
Push services (notably Mozilla autopush) require a valid
`sub` for production use; localhost dogfood survives with
the placeholder.

`exp` = `now + 12h`. RFC 8292 caps at 24h; 12h leaves room
for clock skew without reissuing the JWT every minute. The
JWT is cached in-memory per (origin, exp_window) tuple so
repeated dispatches to the same push service within a
12h window reuse the same signature — pure CPU saving;
the JWT is not the rate-limit gate.

`cryptography` API surface used:

```text
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes, serialization

ec.generate_private_key(ec.SECP256R1())
private_key.sign(message, ec.ECDSA(hashes.SHA256()))
private_key.private_numbers().private_value.to_bytes(32, 'big')
public_key.public_numbers() → x, y → uncompressed point bytes
```

DER ↔ b64url helpers stay in stdlib (`base64.urlsafe_b64encode`,
`tail -c 32` semantics in Python). The cryptography import
is confined to ECDSA key gen + signing.

[CONFIRMED 2026-05-06]

### D) Three-layer rate limit (pin §11.6.14 binding)

PROPOSAL — UI-12 §6 UI-12c specified three layers. UI-12c
materialises them as composable filters in this exact order
(outermost first):

```text
Layer 1 (outermost) — UI-write suppression
  Filter:   event.source != "ui"
  Applied:  BEFORE event-id dedupe + per-category debounce.
  Reason:   pin §11.6.9 binding — UI-write events never
            push back. Applying the filter first prevents
            UI-write events from consuming dedupe slots.
            (Codex P1 binding, UI-12 §6 UI-12c verbatim.)

Layer 2 — Per-category debounce
  Filter:   per (subscription_endpoint, category), at most
            ONE push per 5 s. Within the 5 s window, the
            single push that fires carries the MOST RECENT
            event in the burst window.
  Applied:  AFTER UI-write suppression, BEFORE event-id
            dedupe.
  State:    in-memory dict keyed by
            (endpoint_hash, category) → timestamp_of_last_push.
            NOT persisted; restart-cleared by design.
  CLI flag: --push-debounce-ms <int> (default 5000).
            Per-category override via env var
            KARASU_PUSH_DEBOUNCE_<CATEGORY>_MS deferred
            to a future chunk if dogfood demands it.

Layer 3 (innermost) — Event-id dedupe
  Filter:   per (subscription_endpoint, event_id), at most
            ONE push.
  Applied:  AFTER per-category debounce.
  State:    bounded ring per subscription
            (last N=64 dispatched event ids per endpoint).
            NOT persisted; restart-cleared by design.
            (UI-12 §6 UI-12c binding: "the dispatcher
            persists the last N dispatched event ids per
            subscription in-memory (bounded ring; the
            store does NOT persist this state —
            restart-cleared by design)".)
  Reason:   protects against the same event being
            dispatched twice within the dedupe window
            (e.g. a watcher restart re-replaying the
            tail of the bus that the dispatcher already
            handled).

Composition:
  UI-write suppression > per-category debounce >
  event-id dedupe > delivery
```

Each layer is independently testable AND tested in
combination. The combined-test surface verifies the
ordering invariant — UI-write events do not consume
dedupe slots even under burst conditions.

[CONFIRMED 2026-05-06]

### E) 410 / 404 prune semantics (pin §11.6.16 binding)

PROPOSAL — when the push service responds 410 Gone or 404
Not Found to a delivery, the subscription is dead at the
service level. push_emit removes it from the store via
`push_store.remove_subscription` under the same writer
discipline UI-12b shipped:

```text
410 Gone           Subscription explicitly invalidated by
                   the push service (operator unsubscribed
                   in the browser, browser uninstalled the
                   PWA, OS revoked notification permission).
                   Definitive. Prune.

404 Not Found      The endpoint URL is no longer routable
                   (push service evicted the registration,
                   or the registration was never valid).
                   Treat as 410-equivalent. Prune.

500 / 502 / 503    Push service transient failure. Do NOT
                   prune. Log at WARNING with endpoint_hash
                   only (pin §11.6.16). Next dispatch will
                   retry naturally.

429 Too Many       Rate-limited at the push service level
Requests           (separate from Karasu's per-subscription
                   debounce). Honor the Retry-After header
                   if present; otherwise apply a 60 s
                   per-endpoint backoff. Do NOT prune.

Other 4xx          Log at WARNING + endpoint_hash. Do NOT
                   prune (the failure is reported by the
                   push service but the endpoint may still
                   be reachable on a later attempt).
```

Prune semantics — pin §11.6.13 binding from UI-12b
audit-event correspondence:

```text
- The 410 / 404 prune emits ZERO bus events. Pruning is
  server-side housekeeping; the operator did not request
  it (the operator may not even know the subscription
  was orphaned). UI-12b §11.6.13 already carries the
  invariant: bus emits exactly one push_unsubscribe per
  operator-initiated server-side store mutation.
  Push-service-initiated pruning is not operator-initiated
  and emits NO human_decision.

- The pruned subscription's endpoint_hash is logged at
  INFO with the prune reason: "pruned <hash> (410)" or
  "pruned <hash> (404)". The raw endpoint NEVER appears
  in the log line (pin §11.6.16).

- After prune, the next /api/push read sees count-1 and
  the footer affordance flips to "off" if count drops to
  0. The operator's surface reflects the new truth on
  the next 3-second tick — no special signal, no banner,
  no toast.
```

[CONFIRMED 2026-05-06]

### F) VAPID auto-generation on first start (pin §11.6.13 +
       forward-carry pin (b))

PROPOSAL — when `karasu watch` starts and the configured
`karasu-push.json` either does not exist OR exists but
lacks a `vapid` section with both `public` AND `private`,
push_emit auto-generates a fresh ECDSA P-256 keypair and
persists it via the push_store WRITER:

```text
1. Read store via push_store._read_or_empty_store
   (raises PushStoreError on malformed; the controller
   logs at ERROR and EXITS — no silent operation
   against a broken store).
2. If raw.get("vapid") is a dict with non-empty string
   "public" AND "private", skip generation.
3. Otherwise:
   a. Generate ECDSA P-256 keypair via cryptography.
   b. Serialise public as 65-byte uncompressed point →
      b64url no padding (86 chars).
   c. Serialise private as 32-byte raw scalar →
      b64url no padding (43 chars).
   d. Write to store via a NEW push_store helper
      seed_vapid(store_path, *, public, private) that
      uses the same _STORE_LOCK + _atomic_write
      discipline.
   e. Log at INFO: "generated VAPID keypair" (no key
      material in the log line — pin §11.6.16).

The auto-generation runs ONCE on first start; subsequent
starts read the existing keypair and skip. Rotation is
NOT supported — UI-12 §10.4 binding: rotating the
keypair would invalidate every existing subscription
(browsers tied subscriptions to the public key); rotation
is operator-driven (delete the file + restart) and
explicit, never automatic. UI-13+ may earn a rotation
brief if dogfood requires it.
```

Manual VAPID seed doc deletion (forward-carry pin (b)):

```text
The SAME PR that introduces auto-generation MUST delete
the docs/local-dogfood.md "UI-12b — Manual VAPID seed"
section. The deletion is in the same diff so the operator
never sees a state where both the manual seed
instructions AND auto-generation exist (no doc rot).

The replacement docs/local-dogfood.md "UI-12c — Push
delivery walkthrough" section (§7.4 below) covers the
operator's new path: subscribe a browser, trigger an
attention event, confirm the push arrives, click the
notification.
```

[CONFIRMED 2026-05-06]

### G) Writer concurrency boundary (forward-carry pin (d))

PROPOSAL — UI-12c keeps push_emit in the same process as
the UI server (per §3-A above). The writer concurrency
boundary STAYS in-process; pin §11.6.15 (module-level
threading.Lock across the FULL read-modify-write
transaction) carries forward verbatim from UI-12b.

The 410 / 404 prune path uses the existing
`push_store.remove_subscription` which already holds
`_STORE_LOCK`. No new lock primitives, no new shared-state
mechanism, no IPC.

If a future chunk introduces a SECOND writer process (e.g.
splitting push_emit into a `karasu push-emit` daemon, or
a Phase 4 multi-instance deployment with shared push
store), THAT chunk earns the filesystem-lockfile graduation
in its own brief. UI-12c reserves the right to defer; the
brief is honest about scope.

Test surface for concurrency carries forward UI-12b's
16-thread lost-update test (`test_concurrent_appends_do_not_lose_updates`).
UI-12c adds NO new concurrency tests — the lock boundary is
unchanged.

[CONFIRMED 2026-05-06]

### H) Push payload shape (UI-12 §3-H carry-forward)

PROPOSAL — verbatim from UI-12 §3-H (already
[CONFIRMED 2026-05-05]). UI-12c materialises:

```text
title         attention   "Karasu paused — operator review needed."
              errors      "An adapter failed."
              corrections "A scar was recorded out-of-band."
body          "" (empty by design)
icon          /assets/icons/karasu-192.png
badge         /assets/icons/karasu-192.png
tag           "karasu" (singular — fresh push REPLACES
              pending notifications)
data          {
                "url": "/",
                "category": "<attention|errors|corrections>",
                "event_id": "<bus event id>"
              }
silent        false
requireInteraction  false (OS dismisses after standard
                          timeout)
```

Encryption: Web Push payloads are encrypted with the
subscription's `p256dh` + `auth` keys via aes128gcm. The
encryption uses the same `cryptography` module that signs
the JWT; encryption code lives in
`src/karasu/push_emit/_signing.py` per pin §11.6.13.

[CONFIRMED 2026-05-06]

### I) Test surface (pin §11.6.14 + UI-12 §7 audit cadence)

PROPOSAL — three test files cover the UI-12c contract:

```text
tests/test_push_emit_classifier.py
  Pure unit tests against the category classifier:
    - attention: agent_response.requires_human=true
    - attention: file_change at chain cap
    - errors:    agent_response.status="failed"
    - corrections: human_decision source="telegram" /
                                  source="github_webhook"
    - NOT corrections: human_decision source="ui"
                       (each of scar_revoke, trust_adjust,
                       push_subscribe, push_unsubscribe)
    - None: file_change without trigger conditions
    - None: agent_response.status="completed" + 
            requires_human=false
    - None: git_event
    - None: future / unknown event types

tests/test_push_emit_rate_limit.py
  Pure unit tests against the three-layer composition:
    - Layer 1 alone: source="ui" event with category match
                     → suppressed; no dedupe slot consumed
    - Layer 2 alone: two events <5s apart in same category
                     for same endpoint → second debounced;
                     burst-most-recent wins
    - Layer 3 alone: same event_id twice → second deduped
    - L1 + L2 + L3 in combination: UI-write event in
                     burst → suppressed at L1 even with
                     dedupe slots saturated
    - Restart clears state: in-memory dedupe ring + debounce
                            timestamps reset on restart

tests/test_push_emit_dispatch.py
  Integration tests with stdlib HTTPServer mock as the
  push service:
    - Happy path: subscribe → bus event → push dispatched
                  → 201 Created → no store mutation
    - 410 prune: subscribe → bus event → push dispatched →
                 410 → store removes subscription;
                 endpoint_hash logged at INFO with prune
                 reason; ZERO bus events emitted
    - 404 prune: same as 410 (treated equivalent)
    - 5xx no-prune: 503 → store unchanged; subscription
                    still present
    - 429 backoff: Retry-After honored
    - Multi-device fan-out (pin §11.6.15 of UI-12 carry-
      forward): two subscriptions, one bus event, two
      separate POST attempts to the push service
    - VAPID JWT shape: header alg=ES256, claim aud +
                       exp + sub, signature verifies
                       against the public key
    - Privacy negative-shape: capture HTTP requests +
      log lines + bus + store; assert raw endpoint /
      p256dh / auth never appear except in the in-flight
      POST body to the push service

tests/test_push_emit_import_scope.py
  Lint-style: cryptography is imported ONLY inside
  push_emit/_signing.py + push_emit/_keys.py. Pin
  §11.6.13 binding.
```

Playwright integration test (UI-12 §7 UI-12c binding):

```text
tests/test_ui_push_emit_browser.py
  + Mocks PushManager + injects a synthetic push event via
    registration.showNotification (the receiver side from
    UI-12b's sw.js).
  + Asserts the SW push handler renders a notification
    with the §3-H copy.
  + Skipped silently when Playwright is not installed.
```

PNGs + .webm (UI-12 §7 UI-12c):

```text
1-2 PNGs of the OS notification tray as captured by
Playwright (the OS chrome around the notification is
outside Karasu's design system; the PNG is for audit
provenance).

1 .webm of the edge-to-edge flow: operator subscribes
(UI-12b modal flow, reused from existing recording
walker) → push dispatched (synthetic via
registration.showNotification) → notification rendered →
notificationclick → surface tab focuses.
```

[CONFIRMED 2026-05-06]

## 3.5 · Operator pin (binding when sign-off lands)

PROPOSAL — paralleling UI-10 §3.5 + UI-11 §3.5 + UI-12
§3.5 + UI-12b §3.5:

```text
Push delivery UX must read as the operator deliberately
opening a quiet hand-on-shoulder, not as Karasu colonising
the OS notification tray. Three felt properties:

  1. Editorial silence by default. Karasu does not push
     when the bus is uninteresting. The category
     classifier is conservative — better to miss a
     marginal push than to flood the tray.

  2. Single tag = single voice. The tag "karasu" is
     singular by design (UI-12 §3-H binding); a fresh
     push REPLACES pending ones rather than stacking. The
     operator gets the latest pulse, not a queue.

  3. Server silence on housekeeping. The 410 / 404 prune
     loop emits ZERO bus events. The operator does not
     see "Karasu unsubscribed your stale browser at 3am";
     they just see one fewer subscription in the count
     when they next look. Pin §11.6.13 binding.
```

How this pin shapes UI-12c implementation:

```text
- "Editorial silence by default" → the three categories
  are the closed enum; widening earns a future brief.
  The classifier returns None for events outside the
  enum; no rate-limit slot consumed.

- "Single tag = single voice" → tag = "karasu" verbatim;
  no per-category tag, no per-event tag. Pin §11.6.10
  carry-forward.

- "Server silence on housekeeping" → 410 / 404 prune
  emits no human_decision. The bus is the audit log of
  OPERATOR-DRIVEN mutations; push-service-driven
  housekeeping is INFO-level structured logging only.
```

[CONFIRMED 2026-05-06]

## 4 · Tech stack (delta vs UI-0 / UI-12 / UI-12b)

UI-0 §4 + UI-12 §4 + UI-12b §4 still hold. UI-12c adds:

```text
+ cryptography >= 42.0 as a runtime dep. Named, scoped
  exception per UI-12 §11.6.13 binding. Imports confined
  to src/karasu/push_emit/_signing.py +
  src/karasu/push_emit/_keys.py. Pinned by
  test_push_emit_import_scope.py. Pyproject.toml
  documents the exception alongside the version pin.

+ src/karasu/push_emit/ package (NEW) — bus subscriber +
  category classifier + JWT signing + delivery loop +
  prune handler.

+ tests/test_push_emit_*.py — 4 new test files (~600
  LOC total).

NO new build / framework dependency. NO new front-end
files. NO new HTTP API surface (pin (a) carry-forward —
UI-12b POST + GET shapes are frozen).
```

The cryptography exception in pyproject.toml:

```toml
[project]
dependencies = [
    # ... existing deps ...
    # UI-12c §11.6.13 named scoped exception to UI-0 §4.
    # Used ONLY by src/karasu/push_emit/_signing.py +
    # src/karasu/push_emit/_keys.py for VAPID JWT
    # signing + ECDSA P-256 key generation. Import scope
    # pinned by tests/test_push_emit_import_scope.py.
    "cryptography>=42.0",
]
```

## 5 · Design system (delta vs UI-0 / UI-12 / UI-12b)

UI-12c adds NO design-system delta. The .modal-push-* +
.footer-push micro-elements shipped in UI-12b. The OS
notification chrome is OS-rendered and outside Karasu's
design system (UI-12 §5.6 binding).

## 6 · Roadmap (single chunk)

```text
UI-12c — single chunk. ~400 LOC including tests.

  Code:
    src/karasu/push_emit/__init__.py          ~80 LOC
    src/karasu/push_emit/_classifier.py       ~60 LOC
    src/karasu/push_emit/_rate_limit.py       ~80 LOC
    src/karasu/push_emit/_signing.py          ~120 LOC
    src/karasu/push_emit/_keys.py             ~50 LOC
    src/karasu/push_emit/_dispatch.py         ~120 LOC
    src/karasu/loop_controller.py             +20 LOC
                                              (register
                                              push_emit as
                                              TriggerSource)
    src/karasu/push_store.py                  +30 LOC
                                              (seed_vapid
                                              helper)

  Tests:
    tests/test_push_emit_classifier.py        ~150 LOC
    tests/test_push_emit_rate_limit.py        ~200 LOC
    tests/test_push_emit_dispatch.py          ~250 LOC
    tests/test_push_emit_import_scope.py      ~50 LOC
    tests/test_ui_push_emit_browser.py        ~80 LOC
                                              (Playwright,
                                              optional)

  Visual:
    1-2 PNGs of OS notification tray
    1 .webm edge-to-edge

  Docs:
    docs/event-schema.md                       no change
                                               (no new event
                                               types)
    docs/local-dogfood.md                      DELETE
                                               "Manual VAPID
                                               seed" section;
                                               ADD "Push
                                               delivery
                                               walkthrough"
    pyproject.toml                             cryptography
                                               >= 42.0 +
                                               named-exception
                                               comment

Target ~400 LOC excluding tests; ~700 LOC including tests.
Slightly above UI-12b's 400 LOC because the test surface is
larger (4 unit test files + 1 integration + 1 Playwright).
```

UI-12c is the FINAL chunk in the UI-12 family. After
UI-12c merges, Phase 3 exit criteria close — Telegram
ceases to be the only push channel. UI-13+ chunks earn
their own briefs (deployed surface, A2A peer push fan-out,
etc.).

## 7 · Audit cadence (UI-12 §7 + chunk specifics)

Every UI-12* PR carries the UI-12 §7 audit obligations
forward. UI-12c chunk-level specifics:

### 7.1 PR body

```text
- Documents the cryptography dep choice + version pin.
- Justifies the dep against UI-0 §4 explicitly with a
  reference to UI-12 §11.6.13 binding (the named scoped
  exception precedent set by the UI-12 brief).
- Captures operator sign-off on the dep.
- Notes the import scope is pinned by
  test_push_emit_import_scope.py.
```

### 7.2 Test surface

```text
- All 4 unit test files green.
- Integration test (test_push_emit_dispatch.py) green
  with the stdlib HTTPServer mock as the push service.
- Playwright test (test_ui_push_emit_browser.py) green
  OR skipped silently if Playwright is not installed.
- Existing 139 UI tests STILL green (no regression on
  UI-9 / UI-10 / UI-11b / UI-12a / UI-12b).
```

### 7.3 Visual

```text
- 1-2 PNGs of the OS notification tray.
- 1 .webm edge-to-edge: operator subscribes → bus event
  → push arrives → notification clicked → surface
  focuses. Reuses the UI-12b recording walker mock for
  the subscribe leg; adds new frames for the dispatch +
  click legs.
```

### 7.4 Docs

```text
- docs/local-dogfood.md
    DELETE "UI-12b — Manual VAPID seed" section
      (forward-carry pin (b) binding).
    ADD "UI-12c — Push delivery walkthrough":
      1. Run karasu watch (auto-generates VAPID on
         first start if karasu-push.json has no vapid
         section).
      2. Open the surface; click the footer "off" →
         modal → Enable notifications → permission
         grant → subscription lands.
      3. Trigger an attention event (e.g. /scar from
         Telegram, OR a file_change with
         requires_human=true via watcher).
      4. Confirm the push arrives in the OS tray with
         the §3-H title copy.
      5. Click the notification → the surface tab
         focuses (or opens fresh if no tab is open).

- pyproject.toml: cryptography >= 42.0 with the named-
  exception comment.

- docs/memory/decision-log.md: NEW entry for the
  cryptography exception. Documents the precedent
  scope (push_emit ONLY) so a future chunk's
  contributor reads the entry before re-opening the
  UI-0 §4 conversation.

- docs/event-schema.md: NO change. UI-12c does not
  introduce new bus event types.
```

### 7.5 Lighthouse

Re-run after the chunk lands; thresholds unchanged from
UI-10 baseline (Performance 85, Accessibility 95, Best
Practices 95, SEO 90 — UI-9.1 procedural lock). UI-12c is
server-side only; no Lighthouse delta expected.

## 8 · Frozen contracts (UI-12c MUST respect)

```text
- AgentResponse, F3, F7, F8, surface=sink, single-worker
  invariant, scar=stored-correction-only, I-001..I-006,
  TriggerSource Protocol — all frozen.

- The bus event schema (additive only; UI-12c emits NO
  new event types — push delivery is server-side
  housekeeping; pruning emits NO bus events per
  pin §11.6.13).

- The /api/events / /api/health / /api/meta / /api/scars /
  /api/agents projection shapes.

- /api/push read shape from UI-12a (UI-12b §11.6.11):
  {state, categories, subscription_count, vapid_public_key}.
  UI-12c does NOT change this shape (forward-carry pin
  (a) binding).

- POST /api/push/subscribe + POST /api/push/unsubscribe
  shapes from UI-12b: 204 + no body on success; full
  validation matrix per UI-12b §3-B. UI-12c does NOT
  touch these handlers (forward-carry pin (a) binding).

- push_store reader functions from UI-12a (UI-12b
  §11.6.12). UI-12c reads via the existing reader; no
  new reader API.

- push_store WRITER from UI-12b: append_subscription /
  remove_subscription / atomic write / mode 0600 /
  module-level threading.Lock. UI-12c uses
  remove_subscription on prune; adds a NEW seed_vapid
  helper that uses the SAME lock + atomic-write
  discipline.

- The SW fetch handler ordering from UI-8 (UI-12b
  §11.6.4 shape lock). UI-12c does NOT touch sw.js.

- The Lighthouse threshold contract.

- The 106 binding pins inherited (52 base + 6 UI-10 §0.5
  + 12 UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6 +
  4 PR #102 round-2 forward-carry).

- Out-of-band Codex audit (no `@codex review` tag, no
  ChatGPT Codex Connector — operator-mediated only).
```

## 9 · Out of scope for UI-12c

```text
- New visual surfaces. The OS notification chrome is
  OS-rendered (UI-12 §5.6). UI-12c adds no design-system
  delta.

- New bus event types. Push delivery + prune is
  server-side housekeeping; the bus carries the
  ORIGINATING events (agent_response, file_change,
  human_decision) and push_emit routes against them
  in-process.

- Per-event push opt-in (e.g. "push me when THIS
  specific scar fires"). The closed enum of three
  categories is the contract; per-event opt-in earns
  its own brief.

- VAPID rotation. UI-12 §10.4 binding — keys are
  generated once on first need; rotation invalidates
  every existing subscription. UI-13+ may earn a
  rotation brief if dogfood requires it.

- A2A peer push fan-out (Karasu instance pushing to
  another Karasu instance). UI-13+.

- Push body content beyond the editorial title. UI-12
  §3-H binding — body is empty. Richer payloads earn
  a future brief once the editorial-line discipline is
  dogfood-validated.

- Scheduled / quiet-hours / DND respect beyond OS-level
  DND. UI-13+.

- Multi-process writer concurrency (filesystem
  lockfile). Scope deferred to a future chunk that
  introduces a second writer process; the writer
  concurrency boundary stays in-process for UI-12c.

- Push delivery to non-localhost surfaces. UI-12c ships
  local-only; deployed surfaces earn UI-13+ briefs.

- Per-category debounce override via env var. The CLI
  flag --push-debounce-ms is in scope; per-category
  overrides earn a follow-up if dogfood demands them.
```

## 10 · Open questions (operator sign-off needed)

```text
1. push_emit lives inside the LoopController.
   PROPOSAL — same process as karasu watch (§3-A above).
   Forward-carry pin (d) deferred — writer concurrency
   stays in-process. Future chunk earns the
   filesystem-lockfile graduation.
   [CONFIRMED 2026-05-06]

2. cryptography version pin.
   PROPOSAL — `cryptography >= 42.0`. The 42.x line
   landed in 2024 with stable wheels for every supported
   Python version + every supported OS. The lower bound
   is conservative; no upper bound (cryptography
   maintains backwards compatibility for ECDSA APIs).
   [CONFIRMED 2026-05-06]

3. JWT exp window.
   PROPOSAL — 12 hours. RFC 8292 caps at 24h; 12h
   leaves room for clock skew without reissuing the
   JWT every minute. Cached per (origin, exp_window)
   tuple in-memory.
   ALTERNATIVE — 1 hour. More conservative; reduces
   the window in which a stolen JWT could be replayed.
   Rejected by PROPOSAL because Karasu emits push from
   the operator's own infrastructure; the JWT never
   leaves the local process except in the outbound
   POST. The 12h window is operator-felt (one
   karasu watch session typically lasts several hours).
   [CONFIRMED 2026-05-06]

4. VAPID `sub` claim default.
   PROPOSAL — `mailto:operator@localhost.invalid` if
   `karasu.yaml.push.contact_email` is absent. localhost
   dogfood works with the placeholder; deployed
   surfaces should configure the real email.
   ALTERNATIVE — fail fast on missing contact_email;
   refuse to start until configured. More
   strictly-typed but breaks the "first start works
   out of the box" property.
   [CONFIRMED 2026-05-06]

5. Per-category debounce default.
   PROPOSAL — 5 seconds across all three categories
   (UI-12 §6 UI-12c specified 5s). CLI flag
   --push-debounce-ms <int> overrides.
   [CONFIRMED 2026-05-06]

6. Event-id dedupe ring size.
   PROPOSAL — last 64 events per subscription. Bounded
   in-memory; restart-cleared.
   ALTERNATIVE — last 256 events; more headroom for
   bursty buses. Rejected by PROPOSAL because 64 covers
   the typical 5-second debounce window at peak rates
   measured on Phase 3 dogfood (issue #39 saw at most
   ~6 events in 5s under spam).
   [CONFIRMED 2026-05-06]

7. Manual VAPID seed doc deletion timing.
   PROPOSAL — the SAME PR that introduces auto-generation
   deletes the docs/local-dogfood.md "Manual VAPID
   seed" section. Forward-carry pin (b) binding.
   [CONFIRMED 2026-05-06]

8. Playwright integration test scope.
   PROPOSAL — limited to "synthetic push event →
   notification renders". Real edge-to-edge (operator
   subscribes → real push → real notification) is the
   .webm's job; the Playwright test gates the SW
   push handler shape against drift.
   [CONFIRMED 2026-05-06]

9. Push store on a missing parent directory.
   PROPOSAL — the writer (push_store._atomic_write)
   already calls store_path.parent.mkdir(parents=True,
   exist_ok=True). UI-12c reuses; no new behavior.
   Reaffirm rather than re-decide.
   [CONFIRMED 2026-05-06 — carried forward from UI-12b §3-E]

10. Operator email config key location.
    PROPOSAL — `push.contact_email` in karasu.yaml.
    Top-level `push:` section is new; reserve the
    namespace for future push-related config (rotation
    cadence, per-category overrides, etc. when those
    earn briefs).
    [CONFIRMED 2026-05-06]
```

## 11 · Definition of "done" — UI-12c

```text
- One PR, ~700 LOC including tests.
- src/karasu/push_emit/ package with the file split
  documented in §6.
- cryptography >= 42.0 in pyproject.toml with the
  named-exception comment.
- 4 new unit test files green; 1 Playwright test
  green-or-skipped.
- Existing 139 UI tests STILL green (no regression).
- Import scope test
  (test_push_emit_import_scope.py) pins the
  cryptography exception to push_emit/_signing.py +
  push_emit/_keys.py exclusively.
- 1-2 PNGs of OS notification tray + 1 .webm
  edge-to-edge under
  docs/ui/screenshots/UI-12c-emit/ +
  docs/ui/recordings/UI-12c-emit.webm.
- docs/local-dogfood.md updated:
    - "Manual VAPID seed" section DELETED.
    - "Push delivery walkthrough" section ADDED.
- docs/memory/decision-log.md NEW entry for the
  cryptography named-exception precedent.
- Lighthouse re-run; thresholds unchanged.
- Codex audit returns APPROVED or
  APPROVED-with-observations.
- Brief PR (THIS doc) merged BEFORE the UI-12c code
  branch opens.
```

## 11.6 · Implementation pins (Codex audit, pending)

UI-12c earns whatever pins Codex sets on this brief during
the upcoming audit cycle. Anticipated pin shape (mirrors
UI-10 §11.6 / UI-11 §11.6 / UI-12 §11.6 / UI-12b §11.6):

```text
1.  cryptography is imported ONLY from
    src/karasu/push_emit/_signing.py +
    src/karasu/push_emit/_keys.py. Pinned by
    tests/test_push_emit_import_scope.py.
2.  The category classifier returns None for events
    outside the closed enum {attention, errors,
    corrections}. Future categories earn a brief.
3.  UI-write events (source="ui") are filtered at the
    OUTERMOST rate-limit layer (Layer 1) so they do
    NOT consume dedupe slots.
4.  Per-category debounce default is 5 seconds; CLI flag
    --push-debounce-ms <int> overrides. Per-category
    env var overrides deferred to a future chunk.
5.  Event-id dedupe ring is bounded in-memory at 64
    events per subscription. NOT persisted;
    restart-cleared.
6.  410 / 404 prune emits ZERO bus events. Pruning is
    server-side housekeeping; the operator did not
    request it.
7.  500 / 502 / 503 / 429 do NOT prune. 429 honors
    Retry-After.
8.  VAPID auto-generation runs ONCE on first start;
    rotation is operator-driven (delete file +
    restart).
9.  The SAME PR that introduces auto-generation DELETES
    the docs/local-dogfood.md "Manual VAPID seed"
    section. Forward-carry pin (b) binding.
10. /api/push read shape + UI-12b POST shapes are
    FROZEN. Forward-carry pin (a) binding.
11. push_store reader is FROZEN. UI-12c uses
    remove_subscription + the new seed_vapid helper
    only.
12. Writer concurrency stays in-process via
    threading.Lock. Multi-process boundary deferred to
    future chunk.
13. Raw push endpoints are request-local secret
    material (pin §11.6.16 carry-forward). The 410 /
    404 prune logs endpoint_hash only; the in-flight
    POST body is the only place the raw endpoint
    materialises in memory.
14. Multi-device fan-out is explicit: each active
    subscription is a separate POST. Pin §11.6.15 of
    UI-12 carry-forward.
15. JWT cached per (origin, exp_window) tuple
    in-memory. Cache cleared on watcher restart.
16. push_emit lifecycle is bound to LoopController.
    start() registers; stop() flushes any in-flight
    delivery + cleans up state.
```

These are anticipated; final wording lands after Codex's
verdict. Pins flip from anticipated to verbatim binding
once Codex's audit closes.

## 12 · Status

```text
Brief status:        CONFIRMED — operator sign-off complete
                     (Victor, 2026-05-06: "avanzar"). Codex
                     audit pending out-of-band.
Operator sign-off:   COMPLETE (2026-05-06). Every §3 (A-I) +
                     §3.5 + §10 (1-10) PROPOSAL accepted as
                     the binding contract per default. §10.9
                     reaffirmed as carry-forward from UI-12b
                     §3-E (push store missing parent dir
                     handled by the existing writer's
                     mkdir(parents=True, exist_ok=True)).
Codex audit:         REQUESTED out-of-band. Audit prompt
                     delivered to operator at sign-off close
                     (per feedback_audit_prompt_automatic.md).
                     Round 1 verdict ferried back via Victor;
                     round-N follow-ups land in-branch per
                     UI-10 / UI-11 / UI-12 / UI-12b lifecycle.
Implementation:      BLOCKED on this brief's merge.
                     UI-12c code branch does NOT open until
                     this brief lands in main per UI-9
                     audit pin #1 / UI-12 §11.6 / UI-12b
                     §11.6 carry-forward.
                     UI-12c CLOSES Phase 3 exit criteria —
                     Telegram ceases to be the only push
                     channel.
```

The brief follows the lifecycle `ui-10-design-brief.md`
(PR #83), `ui-11-design-brief.md` (PR #87),
`ui-12-design-brief.md` (PR #93), and
`ui-12b-design-brief.md` (PR #100) went through:

```text
1. Implementer drafts the brief as a doc-only PR with
   sign-off markers.
2. Operator reviews and confirms ("avanzar" or
   per-marker). Markers flip to a confirmed-date stamp.
3. Implementer entrega the audit prompt copy-paste to
   the operator immediately.
4. Codex audits the brief; verdict ferried back via
   the operator. Round 1 typically returns 1-2 P0 + a
   handful of P1/P2.
5. Implementer applies follow-ups in-branch. Re-audit
   triggered when Codex round 1 was CHANGES-REQUIRED
   with P0; APPROVED-with-observations + P1/P2 land
   as in-branch follow-ups without a re-audit.
6. Brief PR merges BEFORE the UI-12c code branch opens.
   Claude Code lands the merge per
   feedback_karasu_merge_es_implementer.md.
```
