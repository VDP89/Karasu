# Next Session Entry Point

## Goal

**Phase 3+ chunk 4b — A2A Agent Card endpoint.**

Phase 3+ chunk 4a (`feat/webhook-receiver`) shipped the GitHub
webhook receiver as a registered TriggerSource (PR after #48,
228/228 tests). Pre-mortem audit closed. Chunk 4b mounts
`GET /.well-known/agent-card.json` on the **same HTTP server**
as the webhook (per F-A2A-5 route boundary), so it reuses chunk
4a's transport. Discovery only — NOT capability negotiation.

## Scope (chunk 4b)

```text
What ships:
- src/karasu/a2a/__init__.py            (export AgentCard, Skill, etc.)
- src/karasu/a2a/card.py                (dataclasses + build_karasu_card)
- src/karasu/a2a/fetch.py               (fetch_card via httpx for peers)
- src/karasu/controller/sources/webhook.py
                                         (mount GET /.well-known/agent-card.json)
- src/karasu/__main__.py                (karasu peers <url> CLI)
- tests/test_a2a_card.py                (~80 LOC)
- docs sync                             (~30 LOC)

Total: ≤300 LOC.

What does NOT ship in 4b:
- Capability negotiation
- Peer authentication
- Peer event ingestion
- Auto-handoff (chunk 4c)
```

## Surface contract — must respect (F-A2A-5)

```text
- Card endpoint is GET-only, unauthenticated, no body, no rate
  limit beyond the receiver's global one.
- Webhook endpoint stays POST-only, HMAC-verified, body-size-limited.
- No path overlap. Cross-method requests return 405.
- The card is a static snapshot built once at startup. No dynamic
  fields, no PII / config leakage.
- build_karasu_card consults _adapters(config) and only emits
  skills whose underlying adapter is live (F-A2A-3 capability
  false positives).
```

## Pre-reads

```text
1. docs/phase-3-plus-pre-mortem.md § 4b   — failure modes F-A2A-1..F-A2A-5
2. src/karasu/controller/sources/webhook.py — chunk 4a transport to extend
3. https://a2aproject.org/spec             — A2A spec snapshot (record version)
```

## Open questions to resolve while implementing

```text
1. Skill list — exactly which skills do we publish? Lean: 4 core
   (watch-filesystem, route-events, receive-github-webhooks,
   record-corrections). Each conditional on its underlying
   adapter / source being configured.

2. Card freshness — static (built at startup) or dynamic (re-read
   config on each GET)? Lean: static. Operators restart karasu
   serve when config changes; tying card freshness to GET would
   add a config-reload code path we don't need yet.

3. Where does fetch_card live in the CLI? Lean: karasu peers <url>
   subcommand prints the AgentCard JSON. No persistence; just a
   discovery probe.
```

## Do NOT do yet

```text
- Do not implement capability negotiation (Phase 3++ scope).
- Do not let the card endpoint mutate any state.
- Do not implement chunk 4c (review-comment auto-handoff).
- Do not bypass F-A2A-5 route boundary.
- Do not touch AgentResponse, F3, F7, F8.
- Do not let the pipeline consume human_decision directly.
```

## Exit condition

```text
A new feat/a2a-agent-card branch, ≤300 LOC, with:
- AgentCard / Skill / AgentCapabilities dataclasses with explicit
  field names matching the A2A spec.
- build_karasu_card(config) returns the live snapshot (skills
  filtered by registered adapters).
- WebhookSource serves GET /.well-known/agent-card.json with the
  static JSON; rejects POST on that path with 405.
- fetch_card(base_url) helper.
- karasu peers <url> CLI subcommand.
- Tests cover: card shape, capability filter, route boundary
  (cross-method 405), fetch_card round-trip against a fake
  server.
- Memory files synced; this file pointed at chunk 4c (or its
  pre-reqs).
```

## Pre-reqs for the chunk AFTER this one (chunk 4c)

```text
Both must be on main before feat/review-comment-handoff opens:

1. Issue #47 — at least an outline plan (cap shape decided).
2. NICE-TO-HAVE #3 — startup warning when adapter
   trust_level >= 2. Promoted to hard pre-req by the Phase 3+
   pre-mortem audit.

Chunk 4b can land independently; no chunk-4c pre-req affects 4b.
```

## Anchor

- Phase 3 closed 2026-05-02 (DOGFOOD-VALIDATED + AUDIT-ACCEPTED).
- Phase 3+ pre-mortem merged (#48, two audit rounds).
- `feat/webhook-receiver` (chunk 4a, this PR) — 26 new tests,
  228/228 green locally. WebhookHandler + WebhookSource,
  `karasu serve` subcommand, F-WH-1..F-WH-10 covered.
