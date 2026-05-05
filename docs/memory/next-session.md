# Next Session Entry Point

## Status: UI-12a — IN FLIGHT (code on a branch, PNGs pending)

main HEAD: `db03710` (memory sync after #93/#94/#95 merges).
0 PRs open. **1 branch in flight** that the next session
must pick up:

```text
Branch:        feat/ui-12a-push-read-display
HEAD commit:   a07c255 (feat(ui): UI-12a — push notification
               read display (PNGs deferred))
Status:        Code + tests landed. PNGs deferred. Not yet
               opened as a PR.
Suite:         512 passing, 1 skipped, 0 regressions on
               this branch.
LOC:           ~870 vs brief target ~250. Justified in
               commit message via pin §0.5.6 audit-coherence
               carve-out (privacy-contract pins §11.6.5 +
               §11.6.16 require positive AND negative shape
               locks; trimming would weaken privacy
               coverage).
```

## Why this hook exists

The session that began UI-12a (Claude Code on web,
2026-05-05) hit two environment limits:

1. **Playwright Chromium download blocked** — the harness
   sandbox has no internet for Chromium artifact + no
   system browser. PNGs (1× footer-off + 1× footer-denied)
   are part of UI-12a §11 DoD; cannot be generated here.
2. **LOC overrun decision** — the chunk landed at ~870 LOC
   vs the brief's ~250 target. Justified by privacy-pin
   coverage but worth an explicit operator + Codex call
   before opening the PR.

The next desktop session has Playwright + Chromium and can
unblock both items in one pass.

## To continue from desktop

```bash
# 1. Sync local main + checkout the in-flight branch.
git fetch origin
git checkout feat/ui-12a-push-read-display
git pull --ff-only

# 2. Verify the suite is still green on your machine.
pytest -q
# Expected: 512 passed, 1 skipped, 0 failed.

# 3. Generate the two PNGs the brief §11 DoD requires.
#    Playwright is already a dev pseudo-dep (used by
#    UI-5/UI-6 .webm + every PNG capture script).
pip install playwright            # if not already
python -m playwright install chromium
python3 scripts/ui_screenshots.py UI-12-push
# Outputs to docs/ui/screenshots/UI-12-push/:
#   00-footer-push-off.png
#   01-footer-push-denied.png
# The "denied" capture overrides window.browserPushSupport
# via eval_js because Notification.permission is read-only
# in the browser; the override is documented inline in
# the CAPTURES["UI-12-push"] entry.

# 4. Visually inspect the two PNGs:
#    - 00-footer-push-off.png   → "Notifications: off"
#                                  rendered with --fg-2
#                                  (neutral, identical
#                                   weight to the build-
#                                   version line).
#    - 01-footer-push-denied.png → "Notifications: denied"
#                                   with the "denied" word
#                                   in --warn (passive
#                                   read-only — pin §11.6.11).

# 5. Commit the PNGs.
git add docs/ui/screenshots/UI-12-push/
git commit -m "docs(ui): UI-12a — regenerated PNGs (off + denied)"
git push

# 6. Decide on the LOC overrun:
#    A) Ship as-is and let Codex audit pin / waive the
#       overrun.
#    B) Trim tests/test_ui_push_store.py from 14 → ~8
#       tests (collapse the partial-shape degradation
#       group and the malformed-store group). Drops
#       ~120 LOC. Privacy pin coverage stays intact
#       because the negative-shape HTTP test
#       (test_api_push_does_not_leak_raw_endpoint_or_keys)
#       is in the OTHER file and is not touched.

# 7. Open the PR.
gh pr create --base main \
   --head feat/ui-12a-push-read-display \
   --title "feat(ui): UI-12a — push notification read display" \
   --body "<see template below>"

# 8. Ferry the diff to ChatGPT for round-1 audit.
#    Use the audit-prompt skeleton at the bottom of this
#    file. Loop budget: 0/5 rounds consumed.

# 9. Apply audit fixes (or counter-argue per
#    docs/review-loop.md) → merge.

# 10. After merge, sync memory:
#     - current-state.md: UI-12a row goes from "← NEXT"
#       to "✔ PR #N merged".
#     - next-session.md: Status → UI-12b (opt-in surface,
#       ~400 LOC, sw.js + modal + shape-lock test).
```

## Audit prompt skeleton (copy-paste into ChatGPT)

```
You are Codex, the iterative auditor for the Karasu repository
(VDP89/Karasu-). You are reviewing a feature commit that
implements UI-12a per the merged UI-12 design brief
(docs/ui/ui-12-design-brief.md, PR #93).

## Artifact under review

Branch feat/ui-12a-push-read-display. Single commit a07c255
(plus the follow-up PNG commit if regenerated separately).

  src/karasu/ui/push_store.py        (new, ~160 LOC)
  src/karasu/ui/server.py            (+85)
  src/karasu/__main__.py             (+14)
  src/karasu/ui/static/index.html    (+104, footer + JS)
  scripts/ui_screenshots.py          (+45, UI-12-push plan)
  tests/test_ui_push_store.py        (new, 14 tests)
  tests/test_ui_server_http.py       (+6 tests)
  tests/test_ui_server.py            (+1 spy update)

Total ~870 LOC vs brief target ~250. Justified in commit
message by privacy-pin coverage (§11.6.5 + §11.6.16
require positive AND negative shape locks).

## Binding pins this chunk must respect

UI-12 brief §11.6 (16 pins). Most relevant for UI-12a:

  §11.6.1 Read-before-write order (UI-12a ships before
          UI-12b/c).
  §11.6.3 Read paths must work without `karasu watch`
          running.
  §11.6.5 Raw PushSubscription endpoint and keys never on
          /api/* (or anywhere outside the store).
  §11.6.6 Footer affordance only — no /push page, no
          header toolbar, no global settings surface.
          UI-12a renders the footer slot.
  §11.6.10 Categories closed to {attention, errors,
           corrections} for UI-12.
  §11.6.11 Unsupported environments degrade to PASSIVE
           READ-ONLY (no click handler, no retry prompt,
           no Home-Screen-install nudge).
  §11.6.16 Raw push endpoints are request-local secret
           material; never logged / projected /
           emitted / screenshotted / echoed.

§11.6.13 (cryptography exception) does NOT apply yet —
UI-12a does not import cryptography. UI-12c earns it.

## Ask

Verdict-shaped audit (P0 / P1 / P2 per
docs/review-loop.md). Specific questions:

  1. Privacy contract — does
     test_api_push_does_not_leak_raw_endpoint_or_keys
     close §11.6.5 + §11.6.16 sufficiently, or is there
     another leak path the test misses (e.g. error
     responses, log output, stack traces)?
  2. State enum — does the JS browserPushSupport()
     correctly cover unsupported branches (no SW, no
     PushManager, no Notification, denied)? Does the
     "supported" → "off" / "on" branch correctly read
     subscription_count without leaking
     subscription contents?
  3. LOC overrun — is the ~870 LOC justified by audit
     coherence, or should the unit tests in
     test_ui_push_store.py collapse from 14 → ~8?
  4. PNG coverage — are 2 PNGs sufficient (off +
     denied), or should a third one cover the
     "supported / unconfigured" boundary?
  5. CLI flag — is `karasu ui --push-store PATH` the
     right shape, or should it pull from karasu.yaml
     like the bus path does (UI-9 deferred follow-up
     pattern)?
  6. Anything missing or risky.

Diff follows.

---

[paste `git show a07c255` here, plus the PNG-commit diff
if you regenerated them separately]
```

## What landed in commit a07c255

### Production code

| File | Lines | Role |
|------|-------|------|
| `src/karasu/ui/push_store.py` | +161 (new) | `PushStoreState` dataclass, `read_push_store(path)`, `project_push_state_payload(state)`, `PushStoreError`, `PUSH_CATEGORIES = ("attention", "errors", "corrections")` |
| `src/karasu/ui/server.py` | +85 | `PUSH_STORE_PATH` global, `configure(push_store_path=...)`, `run_ui_server(push_store_path=...)`, `_list_push_state()`, GET `/api/push` handler with `PushStoreError` → 500 |
| `src/karasu/__main__.py` | +14 | `karasu ui --push-store PATH` flag, default `karasu-push.json`, threaded into `run_ui_server` |
| `src/karasu/ui/static/index.html` | +104 | `<span class="meta footer-push">`, inline `.footer-push.is-on/off/denied/unsupported` CSS rules, `browserPushSupport()` + `loadPushState()` + `renderPushFooter()` JS, called once on init (no polling — push state changes only via subscribe / unsubscribe, both UI-12b territory) |

### Tests (20 new)

| File | Tests | Coverage |
|------|-------|----------|
| `tests/test_ui_push_store.py` | 14 (new file) | empty store, populated store, partial degradation, malformed errors, projection privacy, enum lock |
| `tests/test_ui_server_http.py` | +6 | HTTP shape lock (`PUSH_RESPONSE_KEYS = {state, categories, subscription_count, vapid_public_key}`), populated store projection, **negative shape: raw endpoint / p256dh / auth / VAPID private key MUST NOT appear in /api/push body**, malformed → 500, top-level array → 500, partial degradation |
| `tests/test_ui_server.py` | +1 | spy update for `run_ui_server_kwarg_calls_configure` (now includes `push_store_path`) |

### Screenshot plan (PNGs not yet generated)

| Capture | Strategy |
|---------|----------|
| `00-footer-push-off.png` | Default state. Empty store on first start; `loadPushState` reads `/api/push` → `subscription_count=0` → "off". |
| `01-footer-push-denied.png` | `eval_js` overrides `window.browserPushSupport` to return `'denied'`, then re-calls `loadPushState`. `Notification.permission` is read-only in the browser, so we cannot reach this state via Playwright permission API alone. |

## Frozen contracts honoured by this chunk

- UI-8 `sw.js` fetch handler ordering — UI-12a does NOT
  touch `sw.js`. UI-12b earns the push + notificationclick
  listeners + the three-shape fetch-ordering shape-lock
  test.
- `cryptography` runtime dep — NOT introduced here. UI-12c
  earns the §11.6.13 exception.
- Bus event schema — UI-12a emits NO events
  (`docs/event-schema.md` unchanged).
- The 86 binding pins inherited (52 base + 6 UI-10 §0.5
  + 12 UI-11 §11.6 + 16 UI-12 §11.6) all still hold.

## Accumulated state (unchanged from PR #96)

- 86 binding pins inherited.
- Test suite on `main` HEAD: 483 passing.
- Test suite on `feat/ui-12a-push-read-display` branch:
  512 passing, 1 skipped (= 483 + 20 new + a few from the
  test reorganisation done elsewhere; net +29 vs main
  HEAD).
- Lighthouse contract unchanged.

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed.
- Optional cleanup: delete merged feature branches via the
  GitHub UI:
    docs/ui-12-design-brief                 (merged in #93)
    chore/third-party-notices               (merged in #94)
    feat/a2a-retry-http-statuses            (merged in #95)
    docs/memory-sync-after-93-94-95         (merged in #96)
    claude/continue-repo-work-bOs9o         (working branch
                                              before split)
```

## Phase / prototype status

```text
Phase 1 — Local daemon + Telegram         ✔ CLOSED.
Phase 2 — Git-aware + A2A                 ✔ CLOSED.
Phase 3 — PWA + Advanced                  ⚠ EXIT CRITERIA
                                            BLOCKED ON UI-12.
                                            UI-12a in flight
                                            (this hook).
                                            UI-12b + UI-12c
                                            queued behind it.
                                            UI-12c merge
                                            closes the
                                            prototype.
```
