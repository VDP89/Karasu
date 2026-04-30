# Session Log

## 2026-04-28 — Observability stack completed

What changed:
- PR #9: JsonlTailReader (fixed atomic consumption + unicode split)
- PR #10: `karasu tail` CLI
- PR #11: Local dogfood runbook
- PR #12: `karasu analyze` CLI

Decisions:
- Observability-first approach validated
- No UI/Telegram before data
- Event noise must be measured before any filtering

Impact:
- Karasu is now a fully observable system (input → storage → output → analysis)

Next step:
- Run Phase 1B dogfood locally
- Collect real metrics
- Decide on debounce/filtering based on data

---

## 2026-04-28 (later) — Phase 1B dogfood, F1–F5 closed

What changed:
- PR #15: Windows ignore-pattern bug (F2). Resolved F1 (cascade) and F5 (watcher exit) collaterally.
- PR #18: Debounce per `(path, change_type)` (F4).
- PR #22: Dispatcher suppresses `agent_response` when no adapter handles (F3, option B).

Metrics:
- Baseline → Final on the same workload: 3022 → 11 events. Duplication factor 253× → 2.75×. Peak ev/s 203 → 2.

Impact:
- Bus is clean and measurable. Phase 1B closed.

Next step:
- Phase 1C — wire the real Claude adapter and validate the full loop end-to-end.

---

## 2026-04-29 — Phase 1C closed, F6–F8 shipped

What changed:
- PR #24: ``ClaudeCodeAdapter`` made non-interactive (``-p``), shim-resolved (``shutil.which``), config-hardened (empty command, Windows path, ``-p`` dedupe).
- PR #26: ``Pipeline._should_dispatch`` filter — ``code_change`` excludes ``deleted`` by default; per-rule ``dispatch_on`` override.
- PR #27: ``DEFAULT_IGNORE`` extended to ``events.jsonl``, ``*.log``, ``*.tmp``.
- PR #28: Per-adapter ``timeout_s`` configurable from YAML.
- Issue #25: Phase 1C dogfood results documented end-to-end.

Decisions:
- Adapter contract (``AgentResponse``) does not need redesign before Phase 2 (validated by Codex review on PR #24 + issue #25).
- ``dispatch_on`` is per-rule + classification-default, NOT a hardcoded global; default for ``code_change`` is ``("created", "modified")``.
- ``moved`` is already mapped to ``modified`` by the watcher, so the default tuple does not need to list it.
- Empty ``command`` in YAML must fail fast as a structured ``AgentResponse(error="config")``, not a misleading ``FileNotFoundError`` on ``-p``.
- ``shlex.split(command, posix=(os.name != "nt"))`` — non-POSIX parsing on Windows so backslashes survive.
- ``timeout_s`` per-agent overrides constructor default; absent → 120 s default.

Impact:
- The dogfood loop ``file_change → classify → dispatch → claude -p → agent_response`` runs end-to-end on every OS.
- The bus stops carrying its own JSONL, log captures, and atomic-rename deletions for code-review classification.
- Operators can raise the adapter timeout for refactor-scale dispatches without editing source.

Next step:
- Phase 2 — design the human surface (UI / Telegram / controller). The exit condition of Phase 1C confirmed no contract redesign is needed.

---

## 2026-04-29 (later) — Phase 2 chunk 1: Telegram outbound sink

What changed:
- `docs/phase-2-surface.md` — surface picked (Telegram outbound, read-only), reporter↔surface contract on paper, first PR sized.
- `TelegramInterface.drain(reader, reporter)` — pulls events from `JsonlTailReader`, runs `HumanReporter`, returns `Report`s.
- `TelegramInterface.send(report)` — lazy-imports `python-telegram-bot`, posts one chat message via `Bot.send_message`.
- `TelegramInterface(chat_id=...)` — explicit destination for outbound.
- `karasu chat` rewritten: fail-fast on missing token or chat id, drain loop forwarding agent_response → Telegram, polling interval configurable via `interface.telegram.poll_interval`.
- `_telegram_chat_id` — env (`KARASU_TELEGRAM_CHAT_ID`) over YAML (`interface.telegram.chat_id`); raises on non-integer.
- `tests/test_telegram_bot.py` (12 tests) and `tests/test_main.py` (+6 tests). 106/106 pass locally.
- `docs/local-dogfood.md` — Phase 2 Telegram section appended.

Decisions:
- Surface = sink. No orchestration. Subscribes via existing primitives, no new ones invented.
- `Report(text, needs_decision)` is enough; do not pre-extend.
- Inbound stays read-only on the bus (`human_decision`) — pipeline does NOT react in Phase 2.
- Whitelist (`allowed_users`) preserved for the future inbound chunk; default (empty) allows anyone, since no inbound handler ships in chunk 1.
- `chat_id` is mandatory at startup. Refuse to start if absent — single-operator default.

Impact:
- Operator can leave the laptop and still receive `agent_response` events on Telegram.
- The bus stays the canonical record; Telegram is one of multiple potential surfaces (terminal `karasu tail` is the other already).
- No change to `AgentResponse`, F3, F7, or F8 contracts.

Next step:
- Phase 2 chunk 2 — decide between read-only slash commands (`/status`, `/agents`, `/scars`) or inbound scar-capture (`/correct`, `/scar`). Both are documented as deferred in `docs/phase-2-surface.md`.

---

## 2026-04-29 (still later) — Phase 2 chunk 2: read-only slash commands

What changed:
- `src/karasu/interface/commands.py` — pure formatters: `format_status(bus)`, `format_agents(adapters)`, `format_scars(scars)`. No telegram dependency; tests call them directly.
- `TelegramInterface.handle_command(name, user_id)` — pure dispatch. Whitelist check first (short-circuits before provider runs), then provider lookup, then call. Returns canned strings for unauthorized / unknown / not-configured.
- `TelegramInterface.run_application(reader, reporter, poll_interval)` — wires the actual `python-telegram-bot` Application: three CommandHandlers + a JobQueue task that calls `drain` and forwards reports. ``pragma: no cover`` — pure pieces are tested separately.
- `karasu chat` rewritten again: builds adapters/scars/providers, hands them to the interface, calls `run_application`. The manual drain loop is gone.
- `tests/test_interface_commands.py` (8 tests) and `tests/test_telegram_bot.py` (+5 tests). 118/118 pass locally.
- `docs/local-dogfood.md` — slash-command section appended.

Decisions:
- Providers are lambdas closing over runtime state, not new dataclasses. `Report` is the only contract on the surface side; commands stay format-text-out-on-demand.
- Whitelist short-circuits before the provider runs. Tests assert the provider is not consulted on unauthorized calls (no timing leak).
- `run_application` is the only place `python-telegram-bot.Application` is built. Drain happens via the JobQueue, not a parallel thread — single event loop.

Impact:
- Operator can poll Karasu state from Telegram without leaving the chat: version, event counts, last event, registered agents, active scars.
- Outbound flow from chunk 1 is preserved (drain runs as a JobQueue task at the same `poll_interval`).
- No change to `AgentResponse`, F3, F7, F8 contracts.

Next step:
- Phase 2 chunk 3 — inbound scar capture. `/correct <event_id> field=value` and `/scar field=value` parse the message, derive the trigger from the latest `agent_response`, record a Scar via ScarEngine. Pipeline still does NOT react in Phase 2.

---

## 2026-04-29 (final) — Phase 2 chunk 3: inbound scar capture

What changed:
- `src/karasu/interface/commands.py` — pure write handlers: `parse_correction`, `validate_correction`, `find_agent_response` (prefix-match, ambiguity-aware), `latest_agent_response`, `derive_trigger`, `capture_correct`, `capture_scar`. All errors are returned as user-facing reply strings; nothing raises out of a chat handler.
- `TelegramInterface.handle_write_command(name, user_id, args)` — strict whitelist: empty `allowed_users` rejects every write. Always records `human_decision` first so the audit trail survives even on rejection.
- `run_application` registers two more `CommandHandler`s for `/correct` and `/scar`; their python-telegram-bot glue strips the leading "/<name>" and hands the rest to `handle_write_command`.
- `karasu chat` builds `correct_handler` / `scar_handler` lambdas closing over `bus`, `scars`, and the configured `RuleClassifier`. Adds `_classifier(config)` reuse.
- `tests/test_interface_commands.py` (+24 tests) and `tests/test_telegram_bot.py` (+8 tests). 150/150 pass locally.
- `docs/local-dogfood.md` — inbound capture section appended.

Decisions:
- Trigger derivation re-classifies the path with the configured `RuleClassifier` instead of trying to recover classification from the on-disk `file_change` (the watcher writes file_change BEFORE the classifier runs; classification is in-memory only). Same `RuleClassifier` instance produced the original dispatch, so the trigger matches.
- Scar correction allowlist (`classification`, `priority`, `path`) is enforced surface-side at capture time, mirroring `Pipeline.SUPPORTED_SCAR_KEYS`. Operators learn at the moment of capture, not at the next dispatch.
- Write commands have stricter whitelist than reads: empty `allowed_users` rejects every write. Reads keep their chunk-1 / 2 default (empty == allow anyone) for low-risk visibility.
- Every write attempt records a `human_decision` event regardless of outcome — accepted, rejected, unauthorized. Audit trail survives surface bugs.
- `find_agent_response` raises on ambiguous prefix (git-style); operator must use a longer prefix. Prevents silent picking of the wrong target.

Impact:
- Phase 2 surface complete. Operator can read state and turn corrections into durable scars from Telegram.
- ScarEngine is the only state mutated by chunk 3. Pipeline still does NOT consume `human_decision` events in Phase 2 — the override loop is an explicit next-phase responsibility.
- No change to `AgentResponse`, F3, F7, F8 contracts. Phase 1 work intact.

Next step:
- Audit gate. Maintainer hands PRs #31 + #32 + #33 to ChatGPT for review. No new chunk or phase starts until the audit returns.
