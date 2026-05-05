# Next Session Entry Point

## Status: UI-11b — trust gradient WRITE affordance

main HEAD: `e535c95` (UI-11a merged, 2026-05-05).
0 PRs open. 0 branches open after this docs sync merges.
52 binding pins accumulated.

UI-11a is complete and merged (#89). It landed the read layer
required before any write affordance:

- `GET /api/agents` reads `karasu.yaml` directly.
- `/api/events` projection includes `data.action`.
- HTTP shape locks cover `/api/agents` and the projection key.
- Drawer displays `trust_level: N` for `agent_response` events.
- Unsupported trust values render read-only instead of being coerced.

UI-11b is now unblocked by pin §11.6.1.

## Context recap

2026-05-05 UI-11a session:

1. **PR #88 merged** before work resumed.
   Docs/memory sync pointed the repo to UI-11a.

2. **PR #89 implemented and merged**.
   Branch: `feat/ui-11a-trust-display`.
   Commit on main: `e535c95`.

3. **Codex audit result**:
   - P0: none
   - P1: none
   - P2: two small follow-ups
   - Verdict: APPROVED

4. **Audit follow-up applied before merge**:
   `/api/agents` now handles malformed `trust_level` config
   values such as `trust_level: high` by surfacing the raw
   value with `unsupported: true`, rather than 500ing.

5. **Verification**:
   - CI green on Python 3.10 and 3.12.
   - Required PNG captured at
     `docs/ui/screenshots/UI-11a-trust-display/00-drawer-trust-visible.png`.
   - Local full pytest on Windows remained at 471 passed / 2
     known pre-existing Windows failures:
     `test_git_probe.py::test_git_tree_path_exists_passes_cwd_through`
     and `test_ui_server.py::test_valid_asset_under_static_dir_is_served`.

## Entry point for this session

Branch `feat/ui-11b-trust-write` from `main`.

### UI-11b deliverables (~400 LOC target, but audit coherence wins)

```text
1. POST /api/agents/{name}/trust
   - Returns 204 on success.
   - Emits a human_decision event:
       data.action       = "trust_adjust"
       data.agent        = <adapter name>
       data.trust_before = <current displayed value>
       data.trust_after  = <selected value>
       data.reason       = <optional trimmed reason>
   - INTENT-ONLY: does NOT mutate running adapter instances.
   - Does NOT imply live adapter mutation in copy or UI.
   - Local-only surface, same auth posture as UI-10 / UI-11a.

2. HTTP shape locks
   - POST success -> 204, empty body.
   - Event emitted with exact action + agent + trust_before +
     trust_after fields.
   - Unknown agent -> 404.
   - Unsupported configured trust_level -> read-only; POST should
     not offer or accept mutation from that state.
   - Invalid target trust outside {0,1,2} -> 422.
   - Empty / whitespace reason omitted; non-empty reason trimmed.

3. Drawer extension
   - Existing UI-11a trust row gains an Adjust button only when:
       event.type == "agent_response"
       trust_level is one of {0,1,2}
       agent is present and loadable from /api/agents
   - No global toolbar, no /agents page, no settings surface.
   - Unsupported values show raw value + unsupported tag and no
     Adjust button.

4. Modal
   - Reuse UI-10 .modal primitive.
   - Add .modal-trust-options / .modal-trust-option in modal.css.
   - Radio options only: 0 / 1 / 2.
   - Inline descriptions visible, not tooltip-only:
       0 = quarantined / approval required
       1 = assistive
       2 = autonomous mutation
   - Copy MUST include:
       "Recorded intent. Applies after watch restart."
   - Optional reason field, same trim/omit convention as UI-10.

5. Client JS
   - openTrustModal(event)
   - confirmTrustAdjust()
   - wireTrustModal()
   - Esc precedence: modal first, drawer second.
   - Post-confirm annotation in drawer must read like recorded
     intent, not "trust now N".

6. Docs
   - docs/event-schema.md additive section for UI trust_adjust
     human_decision variant.
   - PR body includes bus schema diff.

7. Visual artifacts
   - PNG: drawer with Adjust button.
   - PNG: modal default.
   - PNG: modal with reason typed.
   - PNG: modal reduced-motion.
   - PNG: post-confirm drawer annotation.
   - .webm walking click -> modal -> confirm -> result.

8. Playwright regression
   - cancel does not mutate / emit event.
   - confirm emits event.
   - Esc modal-first behavior.
   - backdrop closes modal only, drawer stays open.
   - reason trimming / omission if reason is included.
```

## Precedents to reuse

```text
- UI-10 Scar revoke:
  - _emit_human_decision helper.
  - POST 204 + no response body.
  - .modal primitive.
  - modal cancel/confirm/Esc/backdrop Playwright pattern.
  - re-fetch/annotate drawer after a successful write.

- UI-11a Trust read:
  - GET /api/agents.
  - CONFIG_PATH wiring via cmd_ui -> run_ui_server -> configure.
  - drawer-trust-row markup and CSS.
  - unsupported trust handling.
  - data.action projection shape lock.
```

## Binding pins for UI-11b

Most actionable P0 pins from `docs/ui/ui-11-design-brief.md` §11.6:

```text
§11.6.5  UI-11b is INTENT-ONLY. Modal and post-confirm
         surface must state the adjustment is recorded for the
         next watcher run / requires watch restart.

§11.6.6  Drawer-earned only. No /agents page, no toolbar,
         no global trust settings surface.

§11.6.7  Mutation requires modal confirmation. No inline
         trust change shortcut.

§11.6.8  The modal offers only documented values {0,1,2};
         unsupported configured values remain read-only.

§11.6.9  Every trust mutation emits an inspectable bus event.

§11.6.10 POST success may return 204, but post-confirm UI must
         visibly refresh/annotate the drawer so the operator sees
         the recorded intent.

§11.6.11 Playwright must cover cancel-does-not-mutate,
         confirm-emits-event, Esc modal-first behavior, and
         reason trim/omit if a reason field is present.

§11.6.12 .webm must show full-shell operator feel.
```

The earlier pins also still bind:

```text
- Do NOT imply live adapter mutation.
- Do NOT cache /api/* under any circumstances.
- Do NOT add install banners, update toasts, connection badges.
- Do NOT lower Lighthouse thresholds without operator-signed rationale.
- Do NOT introduce a build step or bundler.
- Do NOT let the pipeline consume human_decision directly.
- Do NOT touch AgentResponse, F3, F7, F8.
```

## Audit cadence for UI-11b

Per the UI-11 brief:

```text
1. HTTP shape locks for POST.
2. Bus event schema diff in PR body.
3. docs/event-schema.md updated in the same PR.
4. Playwright regression: cancel + confirm + Esc + backdrop.
5. 4-5 PNGs + 1 .webm.
6. Codex audit out-of-band via ChatGPT before merge.
```

## After UI-11b merges

```text
UI-12: push notifications.
Requires own brief because push UX has opt-in, unsubscribe,
permission, and privacy surface.
```

## Open issues (non-blocking)

```text
#66  fetch_card opt-in retry on 502/503/504 (P2).
#76  THIRD_PARTY_NOTICES.md for OpenMoji + dependencies (P2).
#77  stale UI-6 tracker; UI-6 already merged.
```

## Operator-side TODOs

```text
- Rename repo: GitHub Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Confirm ChatGPT Codex Connector App remains uninstalled /
  unused for this repo.
```
