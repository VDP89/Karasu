# Next Session Entry Point

## Status: UI-12b CODE chunk — brief sealed, code branch can open

main HEAD: `b07aae3` (UI-12b design brief PR #100 merged,
2026-05-06).
0 PRs open. 0 branches open.

UI-12b brief is now binding contract in main. UI-12a (read
display) shipped at PR #98. UI-12b code chunk is the next
working PR.

```text
Notifications: off       (--fg-2)   supported, no subscription
Notifications: on        (--accent) supported, ≥1 subscription
Notifications: denied    (--warn)   Notification.permission denied
Notifications: unsupported (--warn) no SW / no PushManager / etc.
```

UI-12a's `GET /api/push` returns `{state, categories,
subscription_count, vapid_public_key}`; raw endpoint material
never leaves the store (pins §11.6.5 + §11.6.16, locked by
negative-shape HTTP test). UI-12b adds the WRITER side: two
POSTs + push_store writer + modal + sw.js push handlers + 4
Playwright tests + privacy negative-shape extended to all
error branches.

## Context recap (UI-12b brief session 2026-05-06)

1. **PR #100**: UI-12b design brief (doc-only, ~2160 lines).
   - Sign-off: Victor "avanzar" 2026-05-06; 17 markers
     flipped to `[CONFIRMED 2026-05-06]`.
   - Round 1 audit: CHANGES-REQUIRED (1 P0 + 5 P1 + 1 P2).
     All 7 closed in-branch:
       P0 §3-B browser ⇄ store two-phase mutation contract
          (subscribe rollback via subscription.unsubscribe();
          unsubscribe server-removal-first; 2 Playwright
          tests pinned). Pin 13 added.
       P1 §3-E + §3-F VAPID-null UI behavior (modal opens
          but primary disabled; no native prompt; server 503
          stays defensive). Pin 14 added.
       P1 §3-E module-level threading.Lock across full
          read-modify-write transaction. Pin 15 added.
       P1 §7.4 privacy negative-shape extended to error
          branches. Pin 5 extended.
       P1 §3.5 native-deny corrected (Notification permission
          denial short-circuits before PushManager.subscribe).
          Pin 3 clarified.
       P1 §11.6 anticipated pin 9 contradiction with §3-B
          fixed (empty categories allowed; only duplicates +
          out-of-enum rejected).
       P2 §10.4 endpoint sourcing pinned to
          registration.pushManager.getSubscription() (never
          DOM/localStorage/cached). Pin 16 added.
   - Round 2 audit: CHANGES-REQUIRED (3 P1 + 1 P2). All 4
     closed in-branch:
       P1 §3-B unsubscribe 404 audit-event ambiguity
          (audit_emitted flag; 404 emits zero events).
          Pin 13 extended.
       P1 §3-B `/api/push.subscriptions` raw-endpoint
          projection reference removed (would have violated
          pins §11.6.11 + §11.6.16). Orphan handling
          deferred to UI-12c 410 prune.
       P1 §3-B + §7.4 malformed JSON + non-object body
          validation rows added (400 + 422 generic; no
          JSONDecodeError text; no offset leakage; 5
          sentinel-bearing tests). Pin 5 extended again.
       P2 test_unsubscribe_browser_failure_after_204_can_retry_via_404
          + test_unsubscribe_404_converges_with_no_bus_event
          added (4 Playwright tests total).
   - Round 3 audit: APPROVED-with-observations (1 P2). Fix
     in-branch:
       P2 Pin 5 verbatim wording extended to name 400
          explicit + JSONDecodeError/UnicodeDecodeError repr.
   - Codex audit CLOSED at round 3 of 5. Loop budget: 3/5.
   - Merge: Claude Code lanzo `gh pr merge 100 --squash
     --delete-branch` per Victor's working agreement
     ("el merge no es del operador").

## Entry point for THIS session

**UI-12b CODE chunk. ~400 LOC.**

Brief at `docs/ui/ui-12b-design-brief.md` is binding. The
16 §11.6 pins constrain implementation. Suggested branch:
`feat/ui-12b-push-opt-in-surface` (mirrors
`feat/ui-12a-push-read-display`).

### Deliverables

```text
src/karasu/ui/server.py
  + POST /api/push/subscribe handler (validation matrix
    per §3-B: 400 malformed JSON, 422 non-object, 422
    field-level, 422 categories duplicates/out-of-enum,
    422 endpoint not HTTPS, 413 oversize, 503 VAPID
    missing, 204 happy + idempotent UPDATE).
  + POST /api/push/unsubscribe handler (400 / 422 /
    404 / 413 / 204).
  + Both handlers compute endpoint_hash sha256-hex,
    write store via push_store writer, emit
    human_decision with source="ui".
  + Logging discipline: hash only, never raw endpoint.

src/karasu/ui/push_store.py
  + append_subscription(store_path, subscription_dict)
    - Read current store (UI-12a reader untouched).
    - UPDATE existing entry's categories OR append new.
    - Atomic write via O_CREAT|O_WRONLY|O_EXCL, mode
      0o600 on POSIX.
    - Module-level threading.Lock across full
      read-modify-write (pin 15).
  + remove_subscription(store_path, endpoint)
    - Filter by exact endpoint match.
    - Raise PushStoreNotFound on miss (handler → 404).
  + File mode discipline: stat existing file before
    write; loud-stderr warning if observed mode > 0600
    on POSIX; never silently re-mode.

src/karasu/ui/static/css/modal.css
  + .modal-push-categories (fieldset, no border, padding 0).
  + .modal-push-category (label + checkbox + name + desc).
  + .modal-push-state (single-line "Subscribed: N categories").
  + .modal-push-unsubscribe (secondary --fg-2 button).
  All scoped under .modal per pin §0.5.8.

src/karasu/ui/static/js/push.js (NEW, ~150 LOC)
  + Footer click handler (state-gated: opens modal only
    on "off" / "on"; "denied" / "unsupported" handler-less).
  + openPushModal()
  + confirmPushSubscribe() — implements §3-B subscribe
    happy path + rollback rule:
    1. Preflight GET /api/push (already loaded by UI-12a).
    2. Notification.requestPermission().
    3. PushManager.subscribe({applicationServerKey}).
    4. POST /api/push/subscribe.
    5. On non-204: subscription.unsubscribe() rollback;
       no human_decision; modal foot error.
  + confirmPushUnsubscribe() — implements §3-B unsubscribe
    flow with audit_emitted tracking:
    1. registration.pushManager.getSubscription().
    2. POST /api/push/unsubscribe (audit_emitted=true on
       204; audit_emitted=false on 404).
    3. subscription.unsubscribe() (after server confirm).
  + VAPID-null short-circuit: modal opens with primary
    disabled when /api/push.vapid_public_key is null.

src/karasu/ui/static/sw.js
  + 'push' event listener.
  + 'notificationclick' event listener (clients.matchAll +
    client.focus or clients.openWindow).
  + CACHE_NAME bumps karasu-ui-v8 → karasu-ui-v12b.
  + Fetch handler ordering UNCHANGED.

tests/test_ui_sw.py (NEW)
  + Three-branch fetch-ordering shape-lock test:
    1. GET /api/* → network only (cache pre-populated;
       network was called; cache.match NOT consulted).
    2. Navigate / → network first, /offline.html on
       rejection.
    3. GET /assets/* → cache first (hit) / fall through
       to network (miss).
  + Commit MUST pre-date sw.js diff in PR ordering (pin 4).

tests/test_ui_server_http.py (extended)
  + Subscribe shape lock: 204 happy, 422 missing field,
    422 invalid category, 422 empty categories ALLOWED
    → 204, 413 oversize, 204 idempotent duplicate, 422
    not HTTPS, 503 VAPID missing, 400 malformed JSON,
    422 non-object body.
  + Unsubscribe shape lock: 204 happy, 422 missing
    endpoint, 422 not HTTPS, 404 unknown, 413 oversize,
    400 malformed JSON, 422 non-object body.

tests/test_ui_push_privacy.py (NEW or merged with existing
                              negative-shape tests)
  + Sentinel-substring assertions across:
    - Bus events (data.endpoint_hash present; raw
      endpoint, p256dh, auth ABSENT).
    - GET /api/push response body.
    - Captured INFO + DEBUG + ERROR logs.
  + Error-path coverage: 422 invalid endpoint, 422
    invalid categories, 503 VAPID missing, 413 oversize,
    404 unsubscribe, 422 unsubscribe malformed.
  + Malformed-body coverage: truncated JSON, JSON array,
    JSON string, non-JSON unsubscribe body, JSON number
    unsubscribe — all sentinel-bearing.
  + Each error branch asserts: generic body (no sentinel),
    no JSONDecodeError text, no offset leakage, zero new
    bus events, zero store delta, no sentinel in logs.

Playwright suite (existing modal tests + 4 new)
  + Existing: cancel + confirm + Esc + backdrop +
    native-deny (5 paths).
  + NEW: test_subscribe_post_failure_rolls_back_browser.
  + NEW: test_unsubscribe_browser_call_is_made_after_204.
  + NEW: test_unsubscribe_404_converges_with_no_bus_event.
  + NEW: test_unsubscribe_browser_failure_after_204_can_retry_via_404.

scripts/ui_screenshots.py extended
  + UI-12b capture plan:
    - footer-off → modal-default (categories pre-checked).
    - modal with one category unchecked.
    - modal post-subscribe (categories + unsubscribe verb).
    - modal reduced-motion (slide-in clamped).
    - footer-on after successful subscribe.
  + .webm walkthrough: footer hover → click → modal →
    Enable notifications → permission grant simulated →
    modal close → footer "on" → re-click → modal reopen →
    Unsubscribe → modal close → footer "off". ~9s, 1024×640.

docs/event-schema.md
  + Additive section under "human_decision":
    push_subscribe   data.action, data.endpoint_hash,
                     data.categories, source="ui"
    push_unsubscribe data.action, data.endpoint_hash,
                     source="ui"

docs/local-dogfood.md
  + New section: "Manual VAPID seed (UI-12b)" with
    openssl commands + JSON snippet shape. Notes the
    section is REMOVED when UI-12c lands.
  + (If scope allows) "TLS for cross-device dogfood"
    section with mkcert + caddy recipe.
```

### Lifecycle

Same out-of-band Codex audit pattern (no `@codex review`
tag, no ChatGPT Codex Connector). Operator ferries verdicts.
Brief PR is already merged; no brief-vs-code dependency.

After UI-12b code merges, UI-12c opens (server-side emit +
`cryptography` dep + 410/404 prune + 3-layer rate-limit).
UI-12c closes Phase 3 exit criteria.

## Brief lifecycle (UI-10 / UI-11 / UI-12 / UI-12b confirmed)

```text
1. Implementer drafts the brief as a doc-only PR with
   sign-off markers.
2. Operator reviews and confirms ("avanzar" or per-marker).
   Markers flip to a confirmed-date stamp.
3. Implementer entrega the audit prompt copy-paste to
   the operator immediately (per
   feedback_audit_prompt_automatic.md).
4. Codex audits the brief; verdict ferried back via the
   operator. Round 1 typically returns 1-2 P0 + a handful
   of P1/P2.
5. Implementer applies follow-ups in-branch. Re-audit
   triggered when Codex round 1 was CHANGES-REQUIRED with
   P0 (UI-12b's case: 3 audit rounds before APPROVED).
6. Brief PR merges BEFORE the code branch opens. Claude
   Code lands the merge per
   feedback_karasu_merge_es_implementer.md (NOT the
   operator).
```

## Accumulated state

- 102 binding pins inherited (52 base + 6 UI-10 §0.5 + 12
  UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6).
- Test suite on main: 527 passing, 2 preexisting Windows
  CRLF / POSIX-path quirks (also fail on `main` pre-UI-12a;
  documented). 0 regressions.
- Lighthouse contract unchanged (87/95/95/90 with
  performance threshold lowered to 85 under operator-signed
  rationale).

## Open issues

```text
(none — #66, #76, #77 all closed during UI-12 wave)
```

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed (PR #67 retired working agreement; physical
  uninstall closes the loop).
- Optional cleanup: delete merged feature branches via the
  GitHub UI (PR auto-deletes on squash-merge but the
  pre-stack branches from earlier sessions may linger).
```

## Phase / prototype status

```text
Phase 1 — Local daemon + Telegram         ✔ CLOSED.
Phase 2 — Git-aware + A2A                 ✔ CLOSED.
Phase 3 — PWA + Advanced                  ⚠ EXIT CRITERIA
                                            BLOCKED ON UI-12.
                                            UI-12a ✔ merged.
                                            UI-12b brief
                                              ✔ merged.
                                            UI-12b code ←
                                              NEXT.
                                            UI-12c queued
                                              behind UI-12b
                                              code.
                                            UI-12c merge
                                              closes the
                                              prototype.
```
