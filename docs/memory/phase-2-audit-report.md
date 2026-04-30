# Phase 2 Audit Report

Reviewer briefing for ChatGPT. Self-contained — read this first,
then dive into the stack only when needed.

## What is being audited

Phase 2 of Karasu. Four PRs, stacked:

```text
PR #30  docs/phase-2-surface.md           (design only, no code)
PR #31  feat/telegram-outbound-sink       (chunk 1, base = main)
PR #32  feat/telegram-slash-commands      (chunk 2, base = #31)
PR #33  feat/telegram-scar-capture        (chunk 3, base = #32)
```

Phase 1 (1A → 1C) is closed and on `main`. The end-to-end loop
`file_change → classify → dispatch → claude -p → agent_response`
ran clean on Linux/macOS/Windows in issue #25. F1–F8 resolved.

## What ships in Phase 2

A Telegram surface over the existing JSONL bus. Three concrete
capabilities:

```text
1. Outbound sink (chunk 1)
   - karasu chat polls the bus and forwards every agent_response to
     a configured Telegram chat.
   - KARASU_TELEGRAM_TOKEN + KARASU_TELEGRAM_CHAT_ID required;
     fail-fast on absence.

2. Read-only slash commands (chunk 2)
   - /status, /agents, /scars render Karasu state.
   - Soft whitelist (empty allowed_users = anyone allowed).

3. Inbound scar capture (chunk 3)
   - /correct <event_id-prefix> field=value … resolves an
     agent_response by prefix and records a Scar.
   - /scar field=value … uses the latest agent_response.
   - Strict whitelist (empty allowed_users = no one allowed).
   - Allowed correction fields: classification, priority, path
     (mirrors Pipeline.SUPPORTED_SCAR_KEYS).
   - Every attempt writes a human_decision event before any other
     check — audit trail survives surface bugs.
```

## Contract status

### Frozen (verified untouched in chunks 1–3)

```text
- AgentResponse(content, success, requires_human, metadata)
- F3 dispatcher semantics: agent_response only when an adapter ran.
- F7 dispatch_on per-rule + code_change excludes deleted by default.
- F8 timeout_s per-agent from YAML.
- Pipeline single-event synchronous.
- ScarEngine on-disk format (scars.jsonl).
- JsonlEventBus / JsonlTailReader contracts (PR #9, #10).
- HumanReporter / Report dataclass (no fields added).
```

### New surface contract (introduced by chunk 1, used by 2 + 3)

```text
- TelegramInterface = sink, not orchestrator.
- Subscribes via JsonlTailReader, runs HumanReporter.report(event),
  forwards Report through send().
- Inbound writes human_decision events on the bus and STOPS THERE.
  Pipeline does NOT consume human_decision in Phase 2.
- /correct and /scar mutate ScarEngine via record(). They do NOT
  emit file_change or agent_response. The pipeline's normal scar
  consultation path (Pipeline._apply_scar_override) is unchanged.
```

## Three decisions to validate

These are the architectural calls the reviewer should specifically
weigh. All three are recorded in `docs/memory/decision-log.md`.

### D1 — Surface = sink, not orchestrator

The surface only writes `human_decision`. The pipeline does not
consume it. We could have wired `human_decision` → ScarEngine → next
dispatch in chunk 3, but that would couple the surface to the
controller and force an architectural decision before Phase 3.

**Discarded:** web UI first; both surfaces in parallel; surface as
LoopController.

### D2 — Strict whitelist for writes, soft for reads

Asymmetric defaults. Empty `allowed_users` allows reads but rejects
writes. A leaked bot token is a real concern; mutation needs an
explicit operator allowlist; read visibility doesn't.

**Discarded:** uniform default (too coarse); separate YAML key
`require_whitelist_for_writes` (one sane setting; bake it in);
per-user trust gradient (scope creep).

### D3 — Trigger re-classification on capture

`/correct` and `/scar` re-derive the Scar trigger by running the
configured `RuleClassifier` against the agent_response's path.
Classification is NOT persisted on the on-disk file_change — the
watcher writes file_change before the classifier runs.

The re-derivation uses the same `RuleClassifier` instance that
produced the original dispatch, so the trigger matches.

**Discarded:** persist classification on file_change (pipeline
re-order); persist classification on agent_response (contract
mutation); operator-supplied classification (typo-prone).

## Test summary

```text
Total tests passing locally on chunk-3 tip: 150 / 150
  Prior tests on main:                       88
  Chunk 1 new tests:                        +18
  Chunk 2 new tests:                        +12
  Chunk 3 new tests:                        +32
```

Coverage notes:

```text
- TelegramInterface.run_application is `pragma: no cover` — pure
  glue around python-telegram-bot Application + JobQueue.
  Pure pieces (drain, send, handle_command, handle_write_command)
  are tested in isolation.
- python-telegram-bot is mocked via monkeypatch on sys.modules in
  test_telegram_bot.py — the dependency does not need to be
  network-active for tests.
- ScarEngine is exercised by chunk 3 capture tests with a real
  on-disk JSONL file under tmp_path.
```

## Open questions for the reviewer

```text
Q1. Does the surface contract in docs/phase-2-surface.md match the
    shipped behaviour across chunks 1–3? Any drift?

Q2. Is the trigger-derivation strategy (re-classify path on
    /correct and /scar — D3 above) defensible, or should
    classification be persisted on file_change at watch time?

Q3. Is the strict-whitelist policy on write commands (D2) the right
    default, or should it be opt-in via a separate YAML key?

Q4. The audit-trail-on-every-attempt rule writes a human_decision
    event even on unauthorized rejections. Does this create any
    privacy / volume concerns we missed?

Q5. The CommandHandler glue inside run_application is excluded from
    coverage. Are the pure-piece tests sufficient, or does this
    need its own integration check?

Q6. Diff sizes: #31 +432, #32 +452, #33 +749 (incl. tests + docs).
    Per CLAUDE.md, ~400 LOC is the soft cap. Production code only
    is well under, but #33 is over even with that adjustment due
    to test density. Acceptable, or should chunk 3 split?
```

## Pre-reads for the reviewer

```text
1. docs/phase-2-surface.md             — surface contract
2. docs/memory/current-state.md        — phase + capabilities
3. docs/memory/session-log.md          — chunk-by-chunk record
4. docs/memory/decision-log.md         — D1 / D2 / D3 above
5. src/karasu/interface/telegram_bot.py
6. src/karasu/interface/commands.py
7. tests/test_interface_commands.py    — 32 tests for chunk 2 + 3
8. tests/test_telegram_bot.py          — 25 tests for chunks 1 + 2 + 3
```

Adjacent code worth a read for context:

```text
- src/karasu/pipeline.py               — SUPPORTED_SCAR_KEYS, F7 filter
- src/karasu/router/dispatcher.py      — F3 contract
- src/karasu/scars/engine.py           — Scar / ScarEngine API
- src/karasu/eventbus/jsonl_bus.py     — Event / JsonlEventBus / JsonlTailReader
- src/karasu/reporter/human_reporter.py — Report dataclass
```

## Outcomes the reviewer can return

```text
A. APPROVE Phase 2 as-is.
   → Maintainer merges #31 → #32 → #33 in order, retargeting each
     base to main as the previous lands. Phase 2 becomes part of
     main. Phase 3 (PWA / web UI) or Phase 2+ archive (issue #5,
     git hooks / GitHub webhook / A2A) opens.

B. APPROVE with minor changes.
   → Reviewer comments per file or per finding. Changes go on the
     relevant chunk's branch as new commits (no rebase / squash
     across the stack). Re-request audit when pushed.

C. REQUEST architectural changes.
   → One of D1 / D2 / D3 (or a combination) is rejected. The
     affected chunk is reworked; if D1 is rejected the entire
     surface contract is reopened and chunks 2 + 3 follow.

D. ESCALATE.
   → A finding lands outside Phase 2 — touches a frozen contract
     (AgentResponse, F3, F7, F8) or surfaces a Phase 1 regression.
     Escalate to the maintainer; do not silently fold into a
     chunk PR.
```

## Anchor

Generated 2026-04-29, end of Phase 2 implementation session.
Phase 2 chunks 1+2+3 pushed and waiting on this audit. No new
chunk or phase starts until the reviewer returns.
