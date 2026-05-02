# Next Session Entry Point

## Goal

**Phase 3+ chunk 4a — GitHub webhook receiver (`feat/webhook-receiver`).**

Phase 3+ archive pre-mortem doc landed (`docs/phase-3-plus-pre-mortem.md`).
Three concepts mapped (webhook receiver / A2A Agent Cards /
review-comment auto-handoff), failure modes filed per concept,
recommended order is 4a → 4b → 4c. Chunk 4a opens once the
pre-mortem PR audits.

## Scope (chunk 4a)

```text
What ships:
- src/karasu/controller/sources/webhook.py — WebhookSource
  implementing TriggerSource Protocol. http.server.ThreadingHTTPServer
  in a daemon thread. HMAC verify against KARASU_WEBHOOK_SECRET.
  Dedup by X-GitHub-Delivery (1024-deep ring). Maps
  pull_request_review_comment.created → file_change with
  source="github_webhook" and github_* metadata fields.
- karasu serve --host --port CLI subcommand.
- TriggerSource registration via controller.add_source(webhook).
- Tests covering: HMAC verify (good/bad), dedup, lifecycle
  start/stop, event mapping shape.

What does NOT ship in 4a:
- A2A Agent Card endpoint (chunk 4b).
- Auto-handoff prompt builder (chunk 4c).
- Other GitHub event types (push, issue, workflow_run).
- Token-based GitHub mutations (Karasu stays one-way GitHub→bus).
```

## Surface contract — must respect

```text
- WebhookSource is a PRODUCER, like the watcher. It writes
  file_change events to the bus, calls controller.submit, and
  exits (no responses, no orchestration).
- HMAC verification with hmac.compare_digest. 401 on mismatch.
  Never log the secret.
- Dedup is in-memory only (resets on process restart). Not
  durable; that's intentional for the MVP.
- HTTP server bound to 127.0.0.1 by default. External exposure
  is operator opt-in (--host 0.0.0.0).
- The webhook receiver does NOT trigger /correct or /scar.
  Issue #47 (cap-local) stays as-is; webhook events are independent
  file_changes.
```

## Pre-reads

```text
1. docs/phase-3-plus-pre-mortem.md       — chunk 4a design (failure modes F-WH-1..F-WH-7)
2. docs/phase-3-loop-controller.md       — TriggerSource Protocol contract
3. src/karasu/controller/sources/__init__.py — Protocol definition
4. src/karasu/controller/sources/git_hook.py — sister implementation, one-shot
5. issue #5                              — original sketch (HMAC, dedup, mapping)
6. issue #47                             — cap-local-per-origin (don't worsen)
```

## Open questions to resolve while implementing

```text
1. KARASU_WEBHOOK_SECRET — env var only, or also accept from YAML
   like KARASU_TELEGRAM_TOKEN? Lean: env-only, mirrors the bot
   token policy.

2. Dedup ring size — 1024 default. Configurable via YAML? Lean:
   constant in source, no knob until evidence demands one.

3. host/port defaults — 127.0.0.1:8080? Lean: yes; document the
   --host 0.0.0.0 path explicitly with a security note.

4. Backpressure — when controller queue is full, the webhook
   handler should respond 429, not 200. Otherwise GitHub thinks
   delivery succeeded. Lean: 429 on queue.Full from submit.
```

## Do NOT do yet

```text
- Do not implement A2A Agent Cards (chunk 4b).
- Do not implement auto-handoff (chunk 4c).
- Do not let the webhook receiver mutate GitHub state.
- Do not parallelize the controller worker.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
- Do not bypass the cap (issue #47).
```

## Exit condition

```text
A new feat/webhook-receiver branch, ≤400 LOC, with:
- WebhookSource implementing TriggerSource (start/stop).
- karasu serve subcommand wired into __main__.
- Tests for HMAC verify (compare_digest), dedup (idempotent on
  repeat delivery), lifecycle (clean start/stop), event mapping
  (round-trip metadata).
- docs/local-dogfood.md updated with the karasu serve section.
- Memory files synced; this file pointed at chunk 4b (A2A card).
```

## Audit gate after chunk 4a

Per the standard cadence: chunk 4a pushed, manual ChatGPT review,
findings absorbed as F-style PRs (if any), merge, then chunk 4b.

## Anchor for the previous sessions

- Phase 3 closed 2026-05-02 (PRs #34/#35/#36/#37, dogfood #39, F-PRs #40/#41/#42, docs #43/#44/#46).
- Audit accepted; cap-local-per-origin filed as #47 for Phase 3+ planning.
- Pre-mortem PR (this session) — `docs/phase-3-plus-pre-mortem.md`. 202/202 tests green; no source files touched.
