# Next Session Entry Point

## Status: UI-12a — push read display

main HEAD: `1a88cb4` (fetch_card retry HTTP statuses, 2026-05-05).
0 PRs open. 0 branches open (working chunks all merged).

UI-12 brief is on main. The non-blocking issue queue from
prior sessions is empty:

- **PR #93** — UI-12 design brief (push notifications).
  APPROVED-with-observations + operator sign-off complete.
  Doc-only. Sixteen §11.6 implementation pins binding.
- **PR #94** — THIRD_PARTY_NOTICES.md (closes #76).
  OpenMoji + Inter Display + JetBrains Mono attribution
  index. Operator-reverted the README link on review;
  the root file is discoverable on its own.
- **PR #95** — `fetch_card(retry_http_statuses=…)` (closes
  #66). Opt-in retry surface for transient HTTP statuses,
  default empty preserves byte-for-byte pre-#66 single-shot
  HTTP semantics. APPROVED-with-observations: P2 coverage
  resolved with two new tests (zero-budget-with-populated-
  set, per-recommended-status retry); P2 empty-comma-tokens
  counter-argued to keep the scripting-friendly behaviour.

## Context recap (UI-12 brief + repo hygiene session 2026-05-05)

1. **UI-12 brief lifecycle.** Round 1 audit returned
   CHANGES-REQUIRED (2 P0 + 4 P1 + 2 P2); all 8 fixed in
   branch. Round 2 returned APPROVED-with-observations
   (1 P2 + tightening pin 16); both applied. Operator
   ratified every §3 (A-J) + §10 (1-10) PROPOSAL verbatim
   per default ("Confirmado"). 20 [CONFIRMED 2026-05-05]
   markers. Audit loop closed at 2/5 rounds.
2. **Hard negotiations earned.** §3-A footer affordance
   (drawer-earned exception); §3-D / §3-E endpoint_hash
   audit-only + raw endpoint request-local secret;
   §3-F private push store; §3-I sw.js shape-lock test;
   §10.5 + §11.6.13 `cryptography` exception to UI-0 §4
   (named, scoped, non-generalising).
3. **Repo hygiene.** Two non-blocking issues closed
   (#66, #76). All three chunks split into separate PRs
   per the working agreement; merged in order
   (brief → notices → retry).

## Entry point for this session

**UI-12a — push read display. No new brief required —
the UI-12 brief on main is the binding contract.**

Scope (per UI-12 brief §6 UI-12a + §11.6.1 read-before-
write order):

```text
- GET /api/push -> {state, categories, subscription_count,
  vapid_public_key?}
- HTTP shape lock for GET in same PR.
- Footer affordance reads /api/push, renders the current
  state. No modal. No click handler that opens one.
- sw.js NOT modified in this chunk (UI-12b owns the push
  + notificationclick listeners + the fetch-ordering
  shape-lock test).
- Push subscription store path resolved (default
  `karasu-push.json` next to events.jsonl + --push-store
  flag). Empty store on first start. VAPID keys NOT yet
  generated; that comes with UI-12c.
- 1 PNG of footer "off".
- 1 PNG of footer "denied" (synthetic via Playwright
  permission API).
- No .webm (no motion change in this chunk).
- ~250 LOC including tests.
```

Pin §11.6.6 lock: drawer-earned-by-default DOES NOT apply
to UI-12 — the footer-affordance exception was earned in
the brief. Pin §11.6.3 carry-forward: the read path must
work without `karasu watch` running (no IPC, no adapter
reach-through). Pin §11.6.11 lock: unsupported environments
degrade to PASSIVE READ-ONLY (no click handler, no retry
prompt).

## Accumulated state

- **86 binding pins inherited by UI-12a:**
  - 52 base pins (UI-0..UI-9.1 brief contracts).
  - 6 UI-10 §0.5 audit pins (write-path discipline).
  - 12 UI-11 §11.6 pins (trust adjust implementation).
  - 16 UI-12 §11.6 pins (push notification implementation,
    new this session via PR #93).
- **Test suite: 483 passing** (466 baseline + 17 added by
  PR #95). 1 skipped, 0 known regressions. Playwright
  tests deselected when no browser.
- **Lighthouse:** Performance 81-85 variance window,
  threshold 85. Accessibility/Best-practices 95, SEO 90.
  Contract unchanged.

## Open issues (non-blocking)

```text
(empty)
```

Both prior open issues (#66 + #76) closed this session.

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed (PR #67 retired working agreement; physical
  uninstall closes the loop).
- Optional cleanup: delete merged feature branches via the
  GitHub UI:
    docs/ui-12-design-brief
    chore/third-party-notices
    feat/a2a-retry-http-statuses
    claude/continue-repo-work-bOs9o (working branch; PRs
    were split off it before merge)
```

## Phase / prototype status

Karasu's three roadmap phases now sit at:

```text
Phase 1 — Local daemon + Telegram         ✔ CLOSED (Phase 1C
                                            dogfood validated)
Phase 2 — Git-aware + A2A                 ✔ CLOSED (chunk 4a
                                            webhook + 4b A2A
                                            cards in/out + 4c
                                            review-handoff +
                                            CI/CD on the repo)
Phase 3 — PWA + Advanced                  ⚠ EXIT CRITERIA
                                            BLOCKED ON UI-12.
                                            UI-12a → UI-12b →
                                            UI-12c remaining.
                                            On UI-12c merge
                                            Telegram ceases to
                                            be the only push
                                            channel and the
                                            prototype closes.
```
