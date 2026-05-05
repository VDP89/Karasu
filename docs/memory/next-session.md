# Next Session Entry Point

## Status: UI-12 — push notifications

main HEAD: `007574d` (UI-11b merged, 2026-05-05).
0 PRs open. 0 branches open.

UI-10 and UI-11 are complete. The operator surface now has two
write paths:

- Scar revoke (UI-10): `POST /api/scars/{id}/revoke`
- Trust adjust (UI-11b): `POST /api/agents/{name}/trust`

Both are drawer-earned, modal-gated, intent-only, and emit
auditable `human_decision` events.

## Context recap (UI-11 session 2026-05-05)

1. **PR #88**: docs/memory sync to UI-11a entry point. Merged.
2. **PR #89**: UI-11a — trust read display. Codex APPROVED
   (with malformed-trust guard follow-up applied before merge).
3. **PR #90**: docs/memory sync post-UI-11a. Merged.
4. **PR #91**: UI-11b — trust adjust intent. Victor continued
   with Codex while Claude Code was at token limit. Claude Code
   resumed, audited the Codex-produced PR in lieu of Codex
   (operator directive), and merged. Verdict: APPROVED-with-
   observations (0 P0, 0 P1, 2 P2 non-blocking — yaml comments
   stripped on persist, and event-time vs config-time
   trust_before edge case). No follow-up commits applied.
5. Codex returns to reviewer role for UI-12+.

## Entry point for this session

**UI-12 requires a design brief before any code.**

Per Codex audit pin #1 from UI-9 (reaffirmed in UI-10 and
UI-11 audits):

> *"UI-N+ that introduces write paths must earn a new brief
>  before code."*

Push notifications have their own opt-in / unsubscribe /
privacy surface — a distinct UX category from scar revoke and
trust adjust. The brief must address:

- Opt-in: how the operator subscribes (a verb in the surface,
  or implicit on first visit?).
- Unsubscribe: how to revoke. Same modal pattern?
- Which events trigger a push (all? human_decision only? new
  scar? configurable?).
- SW push handler: this touches `static/sw.js` which is frozen
  by UI-8 audit pins. The brief must explicitly earn any SW
  changes.
- Persistence: the push subscription is a browser artifact, not
  in `karasu.yaml`. Where is the canonical store?
- Localhost HTTPS: Web Push requires HTTPS outside localhost.
  Brief must address the development vs production gap.

**Do NOT open a UI-12 code branch until the brief is written,
operator-confirmed, and Codex-audited.**

## Accumulated state

- 52 binding pins + 12 §11.6 (UI-11 brief) + 6 §0.5
  (UI-10 audit) all carry into UI-12.
- Test suite: 466 passing (2 known Windows CRLF preexisting,
  Playwright tests deselected when no browser).
- Lighthouse: Performance 81-85 variance window, threshold 85.
  Accessibility/Best-practices 95, SEO 90. Contract unchanged.

## Open issues (non-blocking)

```text
#66  fetch_card opt-in retry on 502/503/504 (P2).
#76  THIRD_PARTY_NOTICES.md for OpenMoji (P2).
```

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed (PR #67 retired working agreement; physical
  uninstall closes the loop).
```
