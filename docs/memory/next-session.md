# Next Session Entry Point

## Status: UI-12b — opt-in surface (brief required before code)

main HEAD: `f4edfbb` (UI-12a merged, 2026-05-06).
0 PRs open. 0 branches open.

UI-12a (read display) is complete. The operator surface now
shows push state in the footer:

```text
Notifications: off       (--fg-2)  supported, no subscription
Notifications: on        (--accent) supported, ≥1 subscription
Notifications: denied    (--warn)  Notification.permission denied
Notifications: unsupported (--warn) no SW / no PushManager / etc.
```

`GET /api/push` returns `{state, categories, subscription_count,
vapid_public_key}`; raw endpoint material never leaves the store
(pins §11.6.5 + §11.6.16, locked by negative-shape HTTP test).
Default `--push-store` resolves next to the configured bus
(`<bus_dir>/karasu-push.json`); explicit flag wins. UI-12b will
add the WRITER side; the read path already accommodates the
private store (OSError + UnicodeDecodeError + JSON errors all
fold into the same generic 500).

## Context recap (UI-12a session 2026-05-06)

1. **PR #98**: UI-12a — push notification read display.
   Round-1 audit CHANGES-REQUIRED (1 P1 + 2 P2).
   Round-2 audit APPROVED-with-observations (1 P2).
   All findings closed in-branch before merge:
     P1 (round 1) — default push store resolves next to bus
                    via sentinel + `cmd_ui` resolution.
     P2 (round 1) — third PNG `02-footer-push-on.png` covers
                    the `--accent` branch; screenshot server
                    pins push_store_path inside tempdir.
     P2 (round 1) — OSError on `read_text` folds into
                    PushStoreError → structured 500.
     P2 (round 2) — UnicodeDecodeError on `read_text` folds
                    into PushStoreError → structured 500
                    (catches the gap above the OSError catch
                    because UnicodeDecodeError is ValueError,
                    not OSError).
2. **PR #99** (this PR): docs/memory sync after UI-12a.

Loop budget consumed on UI-12a: 2 of 5 rounds.

## Entry point for this session

**UI-12b requires a design brief before any code.**

Per Codex audit pin #1 from UI-9 (reaffirmed in UI-10, UI-11,
and UI-12):

> *"UI-N+ that introduces write paths must earn a new brief
>  before code."*

UI-12b is the FIRST proactive write surface in the project
(the SW push handler reaches OUT of the surface to a
notification tray that may not even be open). The brief must
close:

### Modal contract
- Copy that distinguishes browser-state (subscription) from
  bus-state (UI-10 scar revoke / UI-11 trust adjust).
- Cancel + Esc UX (§11.6.4 — modal mandatory pattern).
- Pre-checked categories on first subscribe (per brief §10.2:
  all three of {attention, errors, corrections}).
- Unsubscribe modal copy + the same Cancel + Esc UX.

### POST contracts
- `POST /api/push/subscribe`: body is the full
  `PushSubscription` dict (endpoint, keys.p256dh, keys.auth)
  + the operator-selected categories. The endpoint is
  request-local secret material (§11.6.16); the response
  echoes only state, never the subscription.
- `POST /api/push/unsubscribe`: body is `{endpoint}` only.
  Bare string carrier of the same secret material. Response
  204 / no body.
- Both must emit a `human_decision` event with
  `endpoint_hash` (sha256-hex of the raw endpoint, NOT the
  endpoint itself) as the only audit metadata (§11.6.6 +
  §11.6.8).

### Service worker scope
- `static/sw.js` gains `push` + `notificationclick` event
  listeners. The fetch handler ordering (UI-8 pin) MUST NOT
  regress — a shape-lock test pins the three branches
  (`/api/*` network-only, navigation offline fallback,
  `/assets/*` cache-first) per pin §11.6.12.

### Persistence
- Store WRITER lands in this chunk: append-on-subscribe,
  remove-on-unsubscribe, `karasu-push.json` mode 0600 on
  POSIX. Atomic write via `tmp + rename` so a partial write
  cannot leave the file unreadable.

### Audit artefacts
- 4-5 PNGs covering the modal subscribe / unsubscribe flow.
- 1 `.webm` showing the operator-felt sequence: footer
  click → modal open → consent → footer flips to "on".
  Per the operator-feel pin: the surface around the modal
  must remain calm (only the modal animates).

### Default opt-in posture
- Pin §11.6.1 binds: opt-in only, no permission requested
  on first visit. The brief must explicitly choose how the
  operator gets to the modal (footer click is the only
  affordance per §11.6.3).

### Localhost vs HTTPS
- Web Push requires HTTPS outside localhost. The brief
  must address how the development surface degrades (or
  bridges) when served over plain HTTP outside localhost.

**Do NOT open a UI-12b code branch until the brief is
written, operator-confirmed, and Codex-audited.**

## Brief lifecycle (UI-10 / UI-11 / UI-12 confirmed)

```text
1. Implementer drafts the brief as a doc-only PR with
   [NEEDS OPERATOR SIGN-OFF] markers on every decision
   that needs the operator's sign-off (typically the
   defaults: pre-checked categories, modal copy, etc.).
2. Operator reviews and confirms ("segun tus criterios" or
   per-marker). Markers flip to [CONFIRMED YYYY-MM-DD].
3. Implementer entrega the audit prompt copy-paste to
   the operator immediately (per
   feedback_audit_prompt_automatic.md).
4. Codex audits the brief; verdict ferried back via the
   operator. Round 1 typically returns 1-2 P0 + a handful
   of P1/P2.
5. Implementer applies follow-ups in-branch. Re-audit
   only if Codex round 1 was CHANGES-REQUIRED with P0;
   APPROVED-with-observations + P1/P2 land as in-branch
   follow-ups without a re-audit, per the UI-2..UI-9.1
   pattern.
6. Brief PR merges BEFORE the UI-12b code branch opens.
```

## Accumulated state

- 86 binding pins inherited (52 base + 6 UI-10 §0.5 + 12
  UI-11 §11.6 + 16 UI-12 §11.6).
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
                                            UI-12b ← brief
                                              NEXT.
                                            UI-12c queued
                                              behind UI-12b.
                                            UI-12c merge
                                              closes the
                                              prototype.
```
