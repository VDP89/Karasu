# Next Session Entry Point

## Goal

**Phase 3+ archive — pre-mortem doc-only PR first, then chunks.**

Phase 3 is COMPLETE + DOGFOOD-VALIDATED (issue #39 closed cleanly).
Three F-PRs filed from the dogfood (#40, #41, #42) — all small,
all P1/P3, none blocking architectural work. Once they merge,
Phase 3+ archive (issue #5) opens.

## Phase 3+ archive concepts (issue #5 — sketch + sized)

```text
1. GitHub webhook receiver
   - HMAC-SHA256 verify against X-Hub-Signature-256
   - Translator: pull_request_review_comment.created → file_change
     with source=github + metadata (github_pr, github_repo, ...)
   - CLI: karasu serve --host --port
   - Delivery dedup via X-GitHub-Delivery
   - Plugs into chunk 3c TriggerSource if long-running, or one-shot
     CLI like git_hook if invoked per-event

2. A2A Agent Cards
   - AgentCard / Skill / AgentCapabilities dataclasses
   - build_karasu_card() with 4 core skills
   - fetch_card(base_url) over httpx
   - WebhookServer.handle_get(path) serves /.well-known/agent-card.json
   - Discovery + capability negotiation; cosmetic without LoopController
     (which we have now), so meaningful from this phase forward

3. Review-comment auto-handoff
   - Dispatcher copies event.data into AgentRequest.metadata
   - ClaudeCodeAdapter._build_prompt() detects github_body + github_pr,
     emits "Address this review comment ..." prompt
   - Reference implementation; LoopController will eventually generalize
     this with a rule table
```

## Recommended order

```text
1. Pre-mortem (docs-only): docs/phase-3-plus-pre-mortem.md
   For each of the three concepts: failure modes, frozen-contract
   risks, scope of damage if implemented wrong. Mirror the
   Phase 2 / Phase 3 design-first cadence.

2. After audit accept: pick ONE concept (likely webhook receiver —
   smallest scope, plugs into existing TriggerSource pattern).
3. Chunk by chunk per the standard cadence (≤400 LOC, focused PR,
   audit before merge).
```

## Frozen contracts (must NOT change)

```text
- AgentResponse (Phase 1A)
- F3 dispatcher semantics (suppression on no-route)
- F7 dispatch_on (code_change excludes deleted by default)
- F8 timeout_s per-agent
- Surface contract from docs/phase-2-surface.md
- Single-worker invariant (controller + worker + bus subscription
  serial through one queue)
- Scar = stored correction only (docs/scar-engine.md "Golden rule")
- I-001..I-006 invariants in docs/decisions.md
```

## Pre-reads for the pre-mortem

```text
1. docs/phase-3-loop-controller.md     — chunk 3a/3b/3c contract
2. docs/scar-engine.md                 — Golden rule
3. docs/decisions.md                   — I-001..I-006 invariants
4. docs/memory/current-state.md        — phase + capabilities
5. issue #5 (open)                     — Phase 3+ archive sketches
6. issue #39 (closed, dogfood)         — what real loop behavior looks like
7. src/karasu/controller/sources/      — TriggerSource pattern
```

## Do NOT do yet

```text
- Do not start webhook receiver / A2A / handoff implementation
  before the pre-mortem doc lands and gets audited.
- Do not parallelize the controller worker.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
- Do not bypass the audit gate.
```

## Anchor

- Phase 3 closed 2026-05-02 (PRs #34/#35/#36/#37 merged, #38 integration tests, #39 dogfood closed).
- F9 (#40), F10 (#41), F11 (#42) filed from dogfood. All small, two cosmetic, one P1.
- 202/202 tests green on main after F11.
- Bot `@Karasu_dogfood_bot` exists in the operator's Telegram for any future smoke runs.
