# Next Session Entry Point

## Goal

**Audit gate — Phase 2 review by ChatGPT before any new chunk.**

Phase 2 chunks 1+2+3 are pushed:

- **PR #30** — design doc `docs/phase-2-surface.md` (no code).
- **PR #31** — chunk 1: outbound Telegram sink.
- **PR #32** — chunk 2: read-only slash commands `/status`, `/agents`, `/scars`. Stacked on #31.
- **PR #33** — chunk 3: inbound scar capture `/correct`, `/scar`. Stacked on #32.

Per the operator policy: ChatGPT acts as the reviewer for this repo and is invoked manually. The maintainer passes the PR set to ChatGPT for the audit. **No new chunk or phase starts until the audit returns.**

## Pre-reads for the audit

```text
1. docs/phase-2-surface.md             — surface contract (the source of truth)
2. docs/memory/current-state.md        — phase + capabilities snapshot
3. docs/memory/session-log.md          — chunk-by-chunk record
4. docs/memory/decision-log.md         — durable decisions
5. src/karasu/interface/telegram_bot.py — TelegramInterface
6. src/karasu/interface/commands.py    — pure formatters + write handlers
7. tests/test_interface_commands.py    — 32 tests
8. tests/test_telegram_bot.py          — 25 tests (drain, send, handle_command, handle_write_command)
```

## Questions ChatGPT should be asked

```text
1. Does the surface contract in docs/phase-2-surface.md match the
   shipped behaviour? Any drift between the design and chunks 1-3?
2. Is the trigger-derivation strategy (re-classify path on /correct
   and /scar) defensible, or should classification be persisted on
   the file_change at watch time?
3. Is the strict-whitelist policy on write commands the right
   default, or should it be opt-in via a separate YAML key?
4. Does the human_decision audit-trail-on-every-attempt rule create
   any privacy / volume concerns we missed?
5. Is the CommandHandler glue in TelegramInterface.run_application
   covered well enough by the pure-piece tests, or does it need its
   own integration check?
```

## If the audit accepts

```text
- Merge #31 → #32 → #33 in order (each base re-targeted to main as
  the previous lands).
- Open Phase 3 entry point: PWA / web UI design doc, OR LoopController
  design doc. Decide based on operator priorities at that point.
- Issue #5 (Phase 2+ archive) becomes the source of next chunks
  (git hooks trigger, GitHub webhook, A2A Agent Card, review-comment
  auto-handoff).
```

## If the audit asks for changes

```text
- File the requested changes as one focused commit per concern on
  the relevant chunk's branch.
- Keep stack order intact unless the audit asks to collapse the
  chunks — premature collapse loses review history.
- Re-request the audit after the changes are pushed. Do not start a
  new phase until ChatGPT signs off.
```

## Do NOT do during the audit window

```text
- Do not start chunk 4 or any Phase 3 work.
- Do not parallelize or batch adapter calls.
- Do not let the pipeline react to scars-from-chat in Phase 2 (the
  human_decision events on the bus are passive records).
- Do not touch AgentResponse, F3, F7, F8.
- Do not introduce a LoopController.
```

## Anchor for the previous sessions

- Phase 1C closed 2026-04-29 (PR #29).
- `docs/phase-2-surface.md` (PR #30) — design only.
- `feat/telegram-outbound-sink` (PR #31) — chunk 1 code, 18 new tests.
- `feat/telegram-slash-commands` (PR #32) — chunk 2 code, 12 new tests, stacked on #31.
- `feat/telegram-scar-capture` (PR #33) — chunk 3 code, 32 new tests, stacked on #32.
- 150/150 tests green locally on the chunk-3 tip.
