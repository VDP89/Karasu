# Next Session Entry Point

## Goal

**Phase 3+ chunk 4c — audit gate.**

Chunk 4c (`feat/review-comment-handoff`) shipped on top of both
gates landed (PR #53 cap-design outline + PR #54 trust-warning).
The branch turns a `pull_request_review_comment.created` event
into a directed Claude dispatch via a fenced, capped, USER-DATA-
labelled PromptBuilder. PR open and awaiting audit.

After chunk 4c merges, the Phase 3+ archive (issue #5) is
essentially closed. Remaining items are open-ended follow-ups
that get their own chunks if/when operator demand surfaces.

## What chunk 4c shipped

```text
src/karasu/router/dispatcher.py
  - Dispatcher.dispatch copies event.data into
    AgentRequest.metadata as a shallow copy. Named fields
    (classification / path / priority) stay populated for
    back-compat. The metadata dict is the new escape hatch for
    source-specific fields (github_body, github_author, etc.).

src/karasu/adapters/prompt_builder.py (NEW)
  - PromptBuilder with two branches: default (legacy one-line
    summary, identical to pre-4c) and github (fenced + USER
    DATA prefix + capped). Detection by metadata["github_body"].
  - DEFAULT_BODY_CAP_BYTES=4096, DEFAULT_AUTHOR_CAP_BYTES=256.
  - _truncate_with_marker slices on UTF-8 bytes, errors=ignore
    on the partial trailing sequence; appends
    "[truncated, original was N bytes]" on overflow.
  - Construction guards: zero / negative caps reject with
    ValueError.

src/karasu/adapters/claude_code.py
  - ClaudeCodeAdapter accepts an optional prompt_builder kwarg;
    defaults to PromptBuilder(). _build_argv delegates the
    prompt string to the builder.

tests/test_router.py (3 new)
  - Metadata round-trip: github_* fields land in
    request.metadata.
  - Copy-not-reference: adapter mutation of metadata does NOT
    leak into event.data.
  - Watcher events: metadata is populated but no github fields.

tests/test_claude_prompt_builder.py (NEW, 18 tests)
  - Default branch matches pre-4c format.
  - Default branch when no github_body / explicit None.
  - F-HANDOFF-1 fence + USER DATA prefix + author-untrusted
    label + pr+repo header + missing author/repo defaults.
  - F-HANDOFF-5 cap held + truncation marker + byte-count-not-
    char-count + DEFAULT_BODY_CAP_BYTES==4096 +
    DEFAULT_AUTHOR_CAP_BYTES==256 + author cap.
  - Construction guards for zero/negative caps.
  - F-HANDOFF-3 ClaudeCodeAdapter wires builder by name +
    falls back to default when none injected.

docs/local-dogfood.md
  - New "Phase 3+ chunk 4c" section.
  - Explicit warning on trust_level >= 2 + auto-handoff
    combination.
  - What does NOT ship: multi-rule routing, token-based
    replies, non-comment sources, A2A negotiation, edited /
    deleted comments, path-existence fallback, chaining.

289/289 pass locally (268 prior + 21 new).
```

## Failure modes addressed

```text
F-HANDOFF-1  Prompt injection from PR comments → fence + USER
             DATA prefix.
F-HANDOFF-3  Hardcoded prompt diverges from a future
             LoopController rule table → PromptBuilder
             abstraction injectable into ClaudeCodeAdapter.
F-HANDOFF-5  Prompt bloat from oversized github_body → 4 KiB
             body cap + 256 B author cap + explicit truncation
             marker.
```

## Failure modes deferred (out of scope per chunk-4c contract)

```text
F-HANDOFF-2  Trust=2 + auto-handoff = remote code edits via PR
             comment → covered by NICE-TO-HAVE #3 startup
             warning (gate 2, already on main) + new
             docs/local-dogfood.md section.
F-HANDOFF-4  Cap distributed-loop amplification → covered by
             issue #47 design outline (gate 1, already on
             main); single-hop only in chunk 4c, chaining
             bounded once the implementation PR ships.
F-HANDOFF-6  Stale or missing referent → edited / deleted
             comments already filtered at the webhook
             receiver (chunk 4a). Path-existence fallback to
             metadata-only prompt deferred as a NICE-TO-HAVE
             follow-up.
```

## Audit gate after chunk 4c

Per the standard cadence:

```text
1. PR pushed → manual ChatGPT review.
2. Findings absorbed as round-2 commit on the same branch.
3. Re-audit. Loop until APROBADO.
4. Squash-merge to main. Phase 3+ archive (issue #5)
   essentially closed.
```

Audit prompt focal points:

```text
- F-HANDOFF-1 fence is correct: triple backticks, no language
  tag, USER DATA prefix outside the fence.
- F-HANDOFF-5 cap: 4 KiB body + 256 B author defensible;
  truncation marker quotes BYTE count not char count.
- PromptBuilder shape: single class with overrideable
  build(request) is enough for chunk 4c; registry waits for
  LoopController rule table.
- Dispatcher.metadata is a shallow copy, not a reference;
  pinned by test.
- Frozen contracts untouched: AgentResponse, F3, F7, F8,
  surface=sink, single-worker, scar-stored-only, I-001..I-006,
  TriggerSource.
- F-HANDOFF-6 path-existence fallback explicitly deferred
  with rationale.
```

## Optional follow-ups (NICE-TO-HAVE, none blocking)

```text
- Issue #47 implementation PR (cap shape from PR #53 design;
  Option B chain cap with origin-aware tracking, CHAIN_CAP=3,
  F-CAP-1..F-CAP-5). Independent of chunk 4c.
- fetch_card helper + karasu peers <url> CLI for outbound
  A2A discovery (deferred from chunk 4b).
- Persist effective priority on agent_response.data
  (deferred from Phase 3 audit).
- F-HANDOFF-6 path-existence fallback to "metadata-only"
  prompt for force-pushed-away paths (deferred from chunk 4c
  scope).
- F-HANDOFF-2 in-the-loop dogfood: run chunk 4c at
  trust_level=1 with a real GitHub PR to validate the
  end-to-end flow before raising any adapter to trust>=2.
```

## Do NOT do yet

```text
- Do not let the webhook receiver mutate GitHub state.
- Do not parallelize the controller worker.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
- Do not chain auto-handoff dispatches (chunk 4c is single-
  hop only) until the issue #47 implementation PR ships.
```

## Anchor for the previous sessions

- Phase 3 closed 2026-05-02 (DOGFOOD-VALIDATED + AUDIT-ACCEPTED).
- Phase 3+ pre-mortem merged (#48, two audit rounds).
- `feat/webhook-receiver` (chunk 4a) merged after F-WH-6 follow-up.
- `feat/a2a-agent-card` (chunk 4b) merged.
- `feat/trust-startup-warning` (gate 2 of 4c) merged as #54
  (squash e43808a) after one round of audit absorption
  (cmd_hook over-reach + flush=True NICE-TO-HAVE).
- `docs/issue-47-cap-shape` (gate 1 of 4c) merged as #53
  (squash 6de0c84) after one round of audit absorption
  (F-CAP-5 cycle/forged-deep, F-CAP-2 source=controller
  alignment, restart semantics, eviction sketch).
- `feat/review-comment-handoff` (chunk 4c, this PR) — 21 new
  tests on top of 268 prior. Frozen contracts untouched.
