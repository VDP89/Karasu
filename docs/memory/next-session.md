# Next Session Entry Point

## Status: UI-12c — server-side push emit (NEXT)

main HEAD: `8434391` (UI-12b code chunk merged, 2026-05-06).
0 PRs open. 0 branches open.

UI-12b code closed cleanly: 21 files, +4435 / -15 lines, 139
tests passing on Windows. Codex audit closed at round 2 of 5
(round 1 CHANGES-REQ 3 P1 → all closed in-branch; round 2
APPROVED clean). The 16 §11.6 pins from the UI-12b brief
are now binding implementation contracts in `main`.

## Context recap (UI-12b code session 2026-05-06)

1. **PR #102**: UI-12b code chunk. 9 initial logical
   commits + 1 round-1 follow-up = 10 commits total:
   1. `029c411` test(ui-12b): SW fetch-ordering shape lock —
      pre-dates sw.js diff (pin §11.6.4)
   2. `a55156d` feat(ui-12b): SW push + notificationclick +
      CACHE_NAME bump (additive — same shape lock still
      passes)
   3. `fecb6fa` feat(ui-12b): push_store writer with
      threading.Lock + atomic 0600
   4. `576e8ec` feat(ui-12b): POST /api/push/subscribe +
      /unsubscribe handlers
   5. `60ec190` test(ui-12b): HTTP shape locks + privacy
      negative-shape (happy + error + malformed)
   6. `8807c0b` feat(ui-12b): modal.css push micro-elements
      + push.js + index.html wiring
   7. `7dbd549` test(ui-12b): Playwright modal flows — pin
      §11.6.13 four flows
   8. `[screenshots]` docs(ui-12b): screenshot script
      extension + 4 modal PNGs
   9. `e94c719` docs(ui-12b): event schema + manual VAPID
      seed walkthrough
   10. `1abd75b` fix(ui-12b): round-1 audit follow-ups —
       3 P1s closed in-branch (Test 4 retry flow,
       state-delta + UTF-8 privacy, .webm 462 KB)

   - Round 1 audit: CHANGES-REQUIRED (3 P1, no P0). All 3
     closed in-branch.
   - Round 2 audit: APPROVED clean.
   - Loop budget: 1/5.
   - Merge: Claude Code lands the merge per
     feedback_karasu_merge_es_implementer.md (`gh pr merge
     102 --squash --delete-branch`).

2. **PR #103** (this PR): docs/memory sync after UI-12b
   code merge.

## Entry point for THIS session

**UI-12c — server-side push emit. Closes Phase 3 exit
criteria (Telegram ceases to be the only push channel).**

UI-12c is the chunk that introduces the `cryptography`
runtime dep as the named, scoped exception per UI-12
§11.6.13. The implementation requires:

### Deliverables

```text
src/karasu/push_emit.py (NEW, ~200-300 LOC)
  + Bus subscriber (similar to TelegramInterface pattern in
    Phase 2 — JsonlTailReader feeding a single-thread loop).
  + Category classifier on each bus event:
      attention   = agent_response with requires_human=True,
                    OR a file_change that the controller cap
                    would block (chain depth at limit)
      errors      = agent_response with status="failed"
      corrections = human_decision originating from a source
                    OTHER THAN "ui" — UI-write events MUST
                    NOT push back to the operator (pin §11.6.9)
  + VAPID JWT signing via cryptography (P-256 ECDSA + JWT
    ES256). Imports gated to this module (the named, scoped
    exception per UI-12 §11.6.13 — UI-12c is the ONLY
    approved import site).
  + Push delivery via stdlib urllib.request (or
    http.client). One HTTP POST per active subscription per
    matching event. Headers: Authorization (VAPID JWT),
    Crypto-Key, Content-Encoding (aes128gcm if payload
    encrypted, otherwise empty), TTL.
  + 410 Gone / 404 Not Found prune: when the push service
    returns 410 / 404, remove the subscription from the
    store (under _STORE_LOCK).
  + Three-layer rate limit (UI-12 brief §6 binding):
      1. Event-id dedupe — each event id is dispatched at
         most once per subscription.
      2. Per-category debounce — at most one push per
         category per 5 s per subscription.
      3. UI-write suppression — events with source="ui"
         NEVER dispatch as pushes regardless of category.
         Filter applied BEFORE event-id dedupe so UI-write
         events do not consume dedupe slots.

src/karasu/push_emit_keys.py (NEW or merged into push_emit.py)
  + VAPID key auto-generation on first server start when
    karasu-push.json has no "vapid" section. ECDSA P-256
    keypair via cryptography.hazmat.primitives.asymmetric.ec.
    Public key serialised as raw uncompressed point (65 bytes
    → 86-char b64u). Private key serialised as 32-byte raw
    scalar (43-char b64u).
  + Persists the keypair into the store via
    _atomic_write (push_store writer, mode 0600).
  + REMOVES the docs/local-dogfood.md "Manual VAPID seed"
    section in the SAME PR (pin §11.6.13 binding).

pyproject.toml
  + cryptography = ">=42" (or current LTS) added under
    [project] dependencies. Scoped exception to UI-0 §4
    documented in the PR body (UI-12 §11.6.13 binding).

tests/test_push_emit.py (NEW)
  + VAPID JWT generation tested (header alg=ES256, claim
    aud / exp / sub).
  + Category classifier tested on each event shape.
  + Three-layer rate limit:
      - event-id dedupe: same id dispatched at most once
      - per-category debounce: 5 s window
      - UI-write suppression: source="ui" never dispatches
  + 410 / 404 prune: subscription removed from store + bus
    carries no event (pruning is server-side housekeeping;
    no human_decision).
  + cryptography import scope test: imports are confined
    to push_emit.py + push_emit_keys.py; no other module
    transitively imports cryptography.

scripts/ui_screenshots.py
  + 1-2 PNGs of the OS notification tray (Playwright
    notification capture). The recording walker from UI-12b
    can be extended to a full edge-to-edge .webm: operator
    subscribes → triggers an event → push arrives → click
    notification → surface focuses.

docs/event-schema.md
  + No new event types. Push delivery is server-side
    house­keeping; the bus sees the originating events
    (agent_response, file_change, human_decision) and the
    push receiver routes against them in-process.

docs/local-dogfood.md
  + DELETE the "UI-12b — Manual VAPID seed" section. UI-12c
    auto-generates on first server start; the operator step
    disappears.
  + Add a "UI-12c — Push delivery walkthrough": subscribe a
    browser via the modal, trigger an attention event (e.g.
    a /scar from Telegram or a file_change with
    requires_human=true), confirm the push arrives in the
    OS tray, click the notification to focus the surface
    tab.
```

### Forward-carry pins from Codex round-2 audit on UI-12b (PR #102)

Codex flagged four binding pins for UI-12c in the
APPROVED-clean verdict. Apply during the UI-12c brief
phase:

```text
1. Do NOT change UI-12b POST response shapes or the
   /api/push read shape while adding emit. UI-12b's
   subscribe / unsubscribe / GET read contracts are now
   frozen.

2. Remove the manual VAPID seed docs (docs/local-dogfood.md
   "UI-12b — Manual VAPID seed" section) in the SAME PR
   that introduces auto-generation. No two-step doc rot.

3. Preserve raw endpoint privacy across push delivery,
   410/404 prune, logs, and bus events. Pin §11.6.5 +
   §11.6.16 carry forward verbatim — endpoint_hash is the
   only audit metadata; the raw endpoint stays in
   karasu-push.json (mode 0600) and in the in-flight POST
   to the push service.

4. Re-audit the writer concurrency boundary if UI-12c
   introduces a second writer process. UI-12b's
   threading.Lock is per-process; UI-12c's emit might run
   in a separate process from the UI server (the watcher's
   loop). If so, graduate to a filesystem lockfile
   (fcntl.flock on POSIX, msvcrt.locking on Windows) held
   across the same transaction.
```

### UI-12c brief lifecycle

Per the established brief-before-code pattern (UI-9 audit
pin #1, reaffirmed UI-10 / UI-11 / UI-12 / UI-12b): UI-12c
introduces the `cryptography` dep + new write paths
(VAPID gen + push delivery), so it earns its own brief
before any code lands.

```text
1. Implementer drafts ui-12c-design-brief.md as a doc-only
   PR with [NEEDS OPERATOR SIGN-OFF] markers. Inherits
   118 binding pins (52 base + 6 UI-10 §0.5 + 12 UI-11
   §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6 + 16
   anticipated UI-12b implementation pins folded in by
   round 2 audit + the 4 forward-carry pins above).
2. Operator reviews + confirms ("avanzar" or per-marker).
3. Implementer entrega the audit prompt copy-paste to the
   operator immediately.
4. Codex audits; verdict ferried back via the operator.
5. In-branch follow-ups; re-audit if round 1 was
   CHANGES-REQUIRED with P0.
6. Brief PR merges BEFORE the UI-12c code branch opens.
   Claude Code lands the merge per
   feedback_karasu_merge_es_implementer.md.
```

## Accumulated state

- 106 binding pins inherited
  (52 base + 6 UI-10 §0.5 + 12 UI-11 §11.6 + 16 UI-12 §11.6
  + 16 UI-12b §11.6 + 4 UI-12b round-2 forward-carry pins).
  PR #101 already counted the 16 UI-12b §11.6 pins in its
  102 total; PR #102 round 2 added only the 4 forward-carry
  pins (no separately-ratified implementation pins beyond
  the 16 §11.6 already in scope).
- Test suite on main: 139 passing on Windows for UI tests
  alone; full suite ~593 passing + 3 skipped (POSIX-only)
  + 2 known Windows CRLF/POSIX-path quirks documented.
- Lighthouse contract unchanged.

## Open issues

```text
(none — #66, #76, #77 all closed during UI-12 wave;
no UI-12b regressions or follow-ups left open.)
```

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed (PR #67 retired working agreement; physical
  uninstall closes the loop).
```

## Phase / prototype status

```text
Phase 1 — Local daemon + Telegram         ✔ CLOSED.
Phase 2 — Git-aware + A2A                 ✔ CLOSED.
Phase 3 — PWA + Advanced                  ⚠ EXIT CRITERIA
                                            BLOCKED ON UI-12c.
                                            UI-12a ✔ merged.
                                            UI-12b brief ✔ merged.
                                            UI-12b code ✔ merged.
                                            UI-12c brief ←
                                              NEXT (doc-only PR).
                                            UI-12c code queued
                                              behind brief.
                                            UI-12c code merge
                                              CLOSES the prototype.
```
