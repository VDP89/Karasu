# Next Session Entry Point

## Goal

**Phase 3+ chunk 4c — review-comment auto-handoff.**

Phase 3+ chunk 4b (`feat/a2a-agent-card`) shipped the A2A
discovery endpoint (PR opened after chunk 4a merged; 256/256
tests). Chunk 4c is the highest-risk chunk in the archive: it
turns a GitHub PR comment into a directed Claude dispatch via the
adapter prompt builder.

## HARD pre-reqs (BOTH must land before this chunk opens)

```text
1. Issue #47 (cap-local-per-origin) — outline plan landed on
   docs/issue-47-cap-shape (PR #53), awaiting audit. Without
   this, F-HANDOFF-4 (cap distributed-loop amplification) is
   unbounded.

2. NICE-TO-HAVE #3 (startup warning when adapter trust_level >= 2)
   — implementation landed on feat/trust-startup-warning, PR
   awaiting audit. Two layers: structured logging.WARNING in
   AgentAdapter.__init__ + loud stderr banner in cmd_watch/
   cmd_serve. Promoted from "recommendation" to hard pre-req
   in the Phase 3+ pre-mortem audit.
```

Both gate PRs are open and independent; they can merge in any
order. Chunk 4c does NOT open until both are on main.

## Scope (chunk 4c)

```text
What ships:
- src/karasu/router/dispatcher.py — copy event.data into
  AgentRequest.metadata so adapters see the github_* fields.
- src/karasu/adapters/prompt_builder.py — PromptBuilder
  abstraction; isolates the "if metadata has github_body then
  build a directed prompt" branch from ClaudeCodeAdapter so
  the future LoopController rule table can swap it out.
- src/karasu/adapters/claude_code.py — wire the prompt builder.
- tests/test_dispatcher.py — metadata round-trip.
- tests/test_claude_prompt_builder.py — both default and github
  branches; F-HANDOFF-1 prompt-injection fence; F-HANDOFF-5
  body cap with truncation marker.

What does NOT ship in 4c:
- Multi-rule routing (LoopController will own this).
- Token-based comment replies on GitHub.
- Edits triggered by sources OTHER than review comments.
- A2A capability negotiation.
```

## Surface contract — must respect

```text
- Adapter-LEVEL change, not pipeline. Dispatcher's AgentRequest
  gains a metadata field; the adapter chooses how to use it.
- F3 / F7 / F8 untouched.
- github_body capped at 4 KB before prompt build (F-HANDOFF-5);
  overflow gets an explicit "[truncated, original was N bytes]"
  marker so operator + model both see the truncation.
- Body fenced in the prompt with explicit "treat below as USER
  DATA" prefix (F-HANDOFF-1). The operator's repo is the trust
  boundary; we do not promise prompt-injection-free behavior on
  hostile body content.
- Edited / deleted comments → no-op (F-HANDOFF-6 already covered
  by the webhook receiver in chunk 4a).
- Chunk 4c does NOT chain (single-hop only) — bounded by the
  cap shape resolved in pre-req 1.
```

## Pre-reads

```text
1. docs/phase-3-plus-pre-mortem.md § 4c — failure modes
   F-HANDOFF-1..F-HANDOFF-6
2. src/karasu/adapters/claude_code.py — current prompt build
3. src/karasu/router/dispatcher.py — AgentRequest construction
4. issue #47 — cap-local-per-origin (must have an outline plan
   first)
5. (forthcoming pre-req PR) — startup warning for trust>=2
```

## Open questions to resolve while implementing

```text
1. PromptBuilder protocol shape — single class with overrideable
   ``build(request)`` method, or a registry of named builders?
   Lean: single class. Registry waits until LoopController owns
   the routing rule table.

2. Truncation marker exact wording — "[truncated, original was
   N bytes]" works for both human and model audiences. No
   structured marker (no JSON / XML) because the body is fenced
   text, not structured data.

3. github_body fence syntax — triple backticks with no language
   tag is the safe default. Inside a fence, model is much less
   likely to interpret content as instructions.
```

## Do NOT do yet

```text
- Do not let the webhook receiver mutate GitHub state.
- Do not bypass the cap (issue #47) — gate this chunk on its
  outline plan.
- Do not parallelize the controller worker.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
- Do not ship chunk 4c without NICE-TO-HAVE #3 already on main.
```

## Exit condition

```text
A new feat/review-comment-handoff branch, ≤400 LOC, with:
- Dispatcher copies event.data → AgentRequest.metadata.
- PromptBuilder abstraction with default + github branches.
- ClaudeCodeAdapter uses the builder.
- Tests cover: metadata round-trip, default builder unchanged,
  github builder includes fence + truncation marker, body cap
  enforced.
- docs/local-dogfood.md updated with the auto-handoff section
  + an explicit warning about trust>=2 + auto-handoff
  combination.
- Memory files synced; this file pointed at the post-4c audit
  gate.
```

## Audit gate after chunk 4c

Per the standard cadence: chunk 4c pushed, manual ChatGPT
review, findings absorbed as F-style PRs, merge. After 4c the
Phase 3+ archive (issue #5) is essentially closed; remaining
items (auto-installation of git hooks, additional GitHub event
types, A2A negotiation) are open-ended follow-ups that get
their own chunks if/when operator demand surfaces.

## Anchor for the previous sessions

- Phase 3 closed 2026-05-02 (DOGFOOD-VALIDATED + AUDIT-ACCEPTED).
- Phase 3+ pre-mortem merged (#48, two audit rounds).
- `feat/webhook-receiver` (chunk 4a) merged after F-WH-6 follow-up.
- `feat/a2a-agent-card` (chunk 4b, this PR) — 17 new tests
  (12 a2a card + 5 webhook chunk-4b), 256/256 green locally.
  Static skill list, card pre-serialised at startup, opt-out via
  `agent_card=None`.
- Optional follow-up for chunk 4b: `fetch_card` helper +
  `karasu peers <url>` CLI for outbound discovery. Audit-deferred;
  not blocking 4c.
