# Next Session Entry Point

## Status: UI-11a — trust gradient READ display

main HEAD: `37b51ba` (UI-11 brief merged, 2026-05-05).
0 PRs open. 0 branches open. 52 binding pins accumulated.

The UI-11 brief (PR #87) is sealed, operator-confirmed, and
Codex-audited. UI-11a is the unblocked entry point.

## Context recap (what happened in the previous session)

2026-05-05 session:

1. **UI MVP merge sequence** executed (#78 → #79 → #80 → #81 →
   #82 in stacked-PR order). Technique: `git diff --binary
   <pre-squash>..<branch>` applied over fresh main for each
   descendant (squash-merge + rebase --onto produces phantom
   conflicts; diff-apply avoids them).

2. **UI-10 (scar revoke)** implemented and merged (#85).
   First write path in the surface. Established patterns:
   - `.modal` CSS primitive (reused by UI-11b).
   - `_emit_human_decision` server helper (reused by UI-11b).
   - POST 204 + JS drawer annotation contract.
   - Playwright cancel/confirm/Esc/backdrop tests.

3. **Lighthouse variance** post-UI-10: Performance drifts
   81–85 with ~50% PASS rate. Threshold stays at 85 (operator-
   signed rationale in `docs/ui/lighthouse/README.md`).
   Pattern: re-run until PASS, commit that report.

4. **UI-11 brief** (PR #87) sealed end-to-end: operator
   sign-off → Codex audit → P1/2×P2 follow-ups applied →
   merge. 12 §11.6 implementation pins set.

## Entry point for this session

Branch `feat/ui-11a-trust-display` from `main`.

### UI-11a deliverables (~250 LOC)

```text
1. GET /api/agents endpoint
   - Reads karasu.yaml directly via the same config loader
     cmd_watch uses. Works with no karasu watch running.
   - Returns JSON array: [{name, trust_level, handles}]
     (status? field is optional — OK to omit in UI-11a).
   - trust_level outside {0,1,2} → include raw int value;
     add "unsupported": true flag (pin §11.6.4).
   - 404 or empty array if no agents configured.

2. HTTP shape lock for GET /api/agents
   - In tests/test_ui_server_http.py (same PR, pin §11.6.2).
   - Assert: status 200, Content-Type JSON, array shape,
     name/trust_level/handles keys present.

3. _project_event extension: data.action
   - src/karasu/ui/server.py::_project_event
   - Add "action": event.data.get("action") (or None).
   - EVENTS_PROJECTION_KEYS constant updated to include
     "action" in the same commit (pin §11.6.2).
   - Shape-lock test updated in tests/test_ui_server_http.py
     (same PR — the 20-key projection shape becomes 21-key).

4. Drawer extension: trust_level visible (read-only)
   - src/karasu/ui/static/js/drawer.js (or inline script):
     when openDrawer(event) is called with an agent_response
     event, render an additional row: "trust_level: N"
     alongside the existing JSON body.
   - For trust_level outside {0,1,2}: render as
     "trust_level: N (unsupported)" — no Adjust button.
   - No Adjust button, no modal, no POST in UI-11a.
   - drawer.css: add .drawer-trust-row rule (minimal —
     reuses existing token stack, no new tokens).

5. 1 PNG: drawer open on an agent_response event showing
   the trust_level row. 1440x900 viewport.
   (No .webm — no motion change. No Playwright — no new
    interaction. PNG only per §11 definition of done.)
```

### Precedents from UI-10 to reuse

```text
- Config path wiring: cmd_ui already passes config_path to
  the UI handler (wired in UI-10). GET /api/agents reads the
  same path. No new wiring needed.
- _emit_human_decision: not called in UI-11a (read-only).
  Relevant for UI-11b.
- tests/test_ui_server_http.py: extend the existing file.
  Pattern: fixture spins up a UIHandler, asserts response.
- scripts/ui_screenshots.py: extend with UI-11a capture plan
  (one entry: drawer-trust-visible at 1440x900).
```

### Files to read before coding

```text
1. src/karasu/ui/server.py        — UIHandler, _project_event,
                                    EVENTS_PROJECTION_KEYS,
                                    load_config path.
2. src/karasu/ui/static/js/       — JS drawer open logic
                                    (openDrawer or equivalent).
3. src/karasu/ui/static/css/      — drawer.css, tokens.css.
4. tests/test_ui_server_http.py   — shape-lock test pattern.
5. docs/ui/ui-11-design-brief.md  — §3-A (surface), §3-E
                                    (endpoints), §3-G (trust
                                    range), §6 (roadmap),
                                    §11.6 (12 pins).
6. src/karasu/adapters/base.py    — AUTONOMOUS_TRUST_LEVEL = 2.
7. src/karasu/config.py (or       — how agents config is
   wherever load_config lives)      loaded from karasu.yaml.
```

## Binding pins for UI-11a (P0 — all 12 §11.6 pins carry)

The four most actionable for UI-11a specifically:

```text
§11.6.1  UI-11a ships BEFORE UI-11b (absolute gate).
§11.6.2  data.action in _project_event + EVENTS_PROJECTION_KEYS
         update + shape-lock test — ALL in the SAME PR.
§11.6.3  Server reads karasu.yaml directly; no IPC, no adapter-
         instance reach-through; works with no karasu watch.
§11.6.4  Trust values {0,1,2} only for the Adjust affordance;
         out-of-range values render as unsupported/read-only.
         (UI-11a: surface the raw int + "unsupported" tag.)
```

The remaining 8 pins (§11.6.5 through §11.6.12) are primarily
UI-11b concerns (modal, Playwright, .webm, intent honesty).
They carry as context; UI-11a does not need to implement them.

## Audit cadence for UI-11a

Per §7 of the brief:

```text
1. 1 PNG of the drawer with trust_level visible.
2. HTTP shape lock for GET /api/agents (same PR).
3. EVENTS_PROJECTION_KEYS update covering data.action
   (same PR, shape-lock test updated).
4. Codex audit out-of-band via ChatGPT before merge.
   Deliver the audit prompt automatically at close
   (per feedback_audit_prompt_automatic.md).
```

## After UI-11a merges

```text
UI-11b (write affordance, ~400 LOC):
  - POST /api/agents/{name}/trust → 204.
  - Drawer: Adjust button alongside trust_level display.
  - .modal-trust-options + .modal-trust-option in modal.css.
  - JS: openTrustModal / confirmTrustAdjust / wireTrustModal.
  - Playwright: cancel + confirm + Esc + backdrop.
  - 4-5 PNGs + 1 .webm walking the full flow.
  - HTTP shape locks for POST.
  - docs/event-schema.md: trust_adjust section.
  - Pin §11.6.5 CRITICAL: modal copy = "Recorded intent.
    Applies after watch restart." NO implication of live
    mutation.
```

## Open issues (non-blocking)

```text
#66  fetch_card opt-in retry on 502/503/504 (P2).
#76  THIRD_PARTY_NOTICES.md for OpenMoji (P2, issue #76).
```

## Operator-side TODOs (cannot be done from this surface)

```text
- Rename repo: GitHub → Settings → Repository name → "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector GitHub App from repo:
  GitHub → Settings → Integrations → Applications →
  ChatGPT Codex Connector → Uninstall.
```

## Anchor: Accumulated binding pins (52 total, P0)

See `docs/ui/ui-11-design-brief.md` §11.6 for the full 12 pins
set by the UI-11 brief audit. The 34 base pins (UI-2..UI-10
audits) and the 6 UI-10 implementation pins all carry forward
into UI-11a and UI-11b.
