# Next Session Entry Point

## Goal

**README Fase 3 — PWA + Advanced.** Pick up the UI surface
that was sketched on the parallel branch ``feat/ui-1-runtime``
(originally driven by ChatGPT; operator asked Claude Code to
take over). ChatGPT continues as auditor only.

The backend roadmap (README Fase 1 + Fase 2) is complete.
Phase 3+ archive (issue #5) closed at the code level. The
only open phase in the README is the PWA / UI surface.

## Why pick up the parallel branch (not start fresh)

``feat/ui-1-runtime`` already ships:

```text
src/karasu/ui/__init__.py           5 LOC
src/karasu/ui/server.py            95 LOC  ThreadingHTTPServer
                                            reading events.jsonl,
                                            /api/events endpoint,
                                            crow-state derivation
                                            (idle / processing /
                                            waiting / error).
src/karasu/ui/static/index.html    48 LOC  Stub HTML +
                                            timeline + crow
                                            state. Black/grey,
                                            monospace, NOT the
                                            Win95 mockup yet.
karasu ui  (CLI subcommand)
docs/ui/karasu-win95-runtime-mockup.md     415 LOC spec.
docs/ui/assets/karasu_sprites_spec.md       30 LOC.
```

Throwing this away and starting fresh would lose the operator's
UX direction (Win95 chrome, crow-as-message metaphor, five-domain
Live Map). The scaffolding is ~150 LOC of code and ~445 LOC of
spec — small enough to rebase cleanly, large enough that it
encodes real design decisions.

## Branch state — needs rebase

``feat/ui-1-runtime`` was forked from main BEFORE chunks
4a / 4b / 4c / cap-impl / fetch / path-fallback / priority-persist
landed. It is **behind main by approximately 8-9 merged PRs**.

Diff against current main shows 30 files changed because main
has all the recent additions; the branch has only the UI
scaffold (+725 LOC) and is missing everything else.

Cleanest pickup path: **cherry-pick the 6 UI commits onto a
fresh branch from current main** rather than merging the
divergent state. The 6 UI commits (oldest first):

```text
20207a5 feat(ui): add UI package
0b65059 feat(ui): add UI server
1d5d054 feat(ui): add static UI
553e5ed feat(ui): add karasu ui command
1ebfe6e docs(ui): add Win95 Karasu runtime mockup spec
466e55f assets(ui): add Karasu sprite definitions v1
```

## Suggested chunk sequence

```text
chunk UI-1  Cherry-pick the 6 commits onto current main.
            Run pytest. Assert the existing UI server still
            serves events.jsonl correctly with the new
            additive fields (priority, controller_chain_depth,
            github_* metadata). Open as feat/ui-rebase or
            similar. Audit + merge.

chunk UI-2  Win95 layout pass: replace the stub index.html
            with the mockup's panel chrome (title bar, sunken
            panels, button surfaces). Static assets only;
            behaviour unchanged. The Win95 mockup spec is at
            docs/ui/karasu-win95-runtime-mockup.md and the
            sprites at docs/ui/assets/karasu_sprites_spec.md.

chunk UI-3  Live Map view: render the five-domain graph
            (User / Karasu / Claude / Codex / GitHub) with
            the crow as the in-flight message. Use the
            existing /api/events feed; no schema change.

chunk UI-4  Detail panel: drill-down on an event shows the
            full bus event JSON, including the new chunk-4c
            fields (priority, controller_chain_depth,
            github_* metadata).

chunk UI-5  Tests for the UI server (HTTP-level, not browser).
            Pin /api/events shape against the current bus
            schema so a future schema change surfaces here.

chunk UI-6+ Push notifications, offline (service worker),
            trust management UI, scar browse/revoke per
            README Fase 3. Larger; each likely needs its
            own design pass.
```

## Pre-reads for next session

```text
1. docs/ui/phase-ui-design.md            (vision)
2. docs/ui/ui-1-layout.md                (layout v1)
3. docs/ui/ui-1-runtime-plan.md          (runtime plan v1)
4. docs/ui/karasu-win95-runtime-mockup.md  (NORTH STAR — only on
                                            feat/ui-1-runtime)
5. docs/ui/assets/karasu_sprites_spec.md   (sprites — only on
                                            feat/ui-1-runtime)
6. src/karasu/ui/server.py + static/index.html  (current stub
                                            — only on
                                            feat/ui-1-runtime)
```

## Surface contract — must respect

```text
- UI = surface, not orchestrator. The bus (events.jsonl) is
  the source of truth; the UI reads but never writes.
- No new bus event types required. The UI reads existing
  event types (file_change, agent_response, human_decision,
  scar_consultation) and renders them.
- No new dependency on the backend Python code beyond
  ``import json`` / stdlib HTTP. The UI server lives in
  ``src/karasu/ui/`` and depends only on the bus file shape.
- Frozen contracts untouched: AgentResponse, F3, F7, F8,
  surface=sink (the UI is a NEW surface, additive to
  Telegram), single-worker invariant,
  scar=stored-correction-only, I-001..I-006, TriggerSource
  Protocol.
- ``karasu ui`` is read-only in the MVP. No write endpoints
  (no /api/correct, no /api/scar) in the rebase or layout
  chunks. Write paths come later with the trust management
  UI; they MUST go through ScarEngine / human_decision
  events, not through direct bus mutation.
```

## ChatGPT auditor cadence

Same as the backend work: open PR → manual ChatGPT review
through operator → REQUERIDOS / NICE-TO-HAVE → absorb on
same branch → merge. This kept REQUERIDO churn low across
the 12 PRs of this session and the previous one.

## Operational item — chunk 4c dogfood (deferred)

Controlled dogfood of chunk 4c on a real GitHub PR with
``trust_level=1`` requires the operator's computer
(``karasu serve`` long-running + GitHub webhook + bus
monitoring). Operator targets Monday. NOT blocking the UI
work — they are independent.

When the dogfood runs:
- Adapter at ``trust_level=1``.
- Verify the stderr banner from NICE-TO-HAVE #3 lists the
  adapter at startup.
- Drop a review comment on a PR with a fenceable body
  (e.g. containing ` ``` `).
- Watch ``events.jsonl`` for the resulting file_change with
  ``source="github_webhook"``, the dispatched
  agent_response, and the persisted ``priority`` /
  ``controller_chain_depth`` fields.

## Anchor for the previous sessions

- Phase 3 closed 2026-05-02 (DOGFOOD-VALIDATED + AUDIT-ACCEPTED).
- Phase 3+ pre-mortem merged (#48, two audit rounds).
- ``feat/webhook-receiver`` (chunk 4a) merged after F-WH-6 follow-up.
- ``feat/a2a-agent-card`` (chunk 4b) merged.
- ``feat/trust-startup-warning`` (gate 2 of 4c) merged as #54.
- ``docs/issue-47-cap-shape`` (gate 1 of 4c) merged as #53.
- ``feat/review-comment-handoff`` (chunk 4c base) merged as #55.
- ``feat/handoff-hardening`` (chunk 4c hardening) merged as #56.
- ``feat/cap-shape-impl`` (chain cap implementation) merged
  as #57. Closes issue #47.
- ``feat/a2a-fetch-peers`` (chunk 4b outbound discovery)
  merged as #58.
- ``feat/handoff-path-fallback`` (F-HANDOFF-6) merged as #59.
- ``feat/persist-effective-priority`` (Phase 3 audit
  follow-up) merged as #60.
- 335/335 pass on main. Frozen contracts intact.

## Do NOT do yet

```text
- Do not let the UI mutate bus state. Read-only in the MVP.
- Do not bypass ScarEngine / human_decision when writes
  eventually arrive. Same contract as the Telegram surface.
- Do not change the bus schema as part of UI work. New
  fields on bus events must justify themselves outside the
  UI need.
- Do not start chunk UI-6+ (push, offline, trust mgmt)
  before chunks UI-1..UI-5 are on main. Each later chunk
  is large enough to warrant its own design pass.
- Do not start chunk 4c dogfood from the sandbox; it needs
  the operator's computer.
```
