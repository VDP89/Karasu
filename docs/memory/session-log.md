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

---

## 2026-04-29 (post-audit) — chunk 3 audit fix

Audit verdict (ChatGPT, returned 2026-04-29):
- APPROVE PRs #30, #31, #32 as-is.
- REQUEST CHANGES on PR #33: contract drift. The original `docs/phase-2-surface.md` declared Phase 2 as "outbound + read-only, scar capture deferred", but chunks 2 + 3 shipped slash commands and scar capture. Pick option 1: align the design doc with the shipped behaviour. Two secondary findings: redact unauthorized args in `human_decision`; document classifier-currency in trigger derivation.

What changed:
- `docs/phase-2-surface.md` — cherry-picked onto the chunk 3 branch (originally landed in PR #30) so the contract update lives in PR #33's diff. Surface choice now lists the three chunks; reporter↔surface contract acknowledges scar mutation; pipeline boundary diagram shows chat → ScarEngine; "Out of scope" updated; "Do NOT do" replaces "mutate scars from chat" with "pipeline reaction to human_decision". New `## Revisions` section logs the audit alignment. New "Trigger derivation note" documents that re-classification uses the **currently configured** rules at capture time, not the historical classification.
- `TelegramInterface.handle_write_command` — reordered: authorization checked BEFORE recording the text. Unauthorized callers and unknown commands record minimal metadata only (`"/{name} (unauthorized)"` / `"/{name} (unknown command)"`) instead of the raw args. Authorized calls still record the full `"/{name} {args}"` so the operator can reconstruct what they typed.
- `tests/test_telegram_bot.py` — replaced the audit-trail-on-unauthorized assertion with two redaction tests (one for unauthorized, one for unknown command). 151/151 pass.
- `docs/local-dogfood.md` — clarified the audit-trail / redaction behaviour for the inbound capture section.

Decisions:
- Redaction is asymmetric to keep diagnostics useful: authorized full text (operator can debug their own input), unauthorized minimal metadata (can't be used to exfiltrate via leaked tokens).
- The contract update lives in PR #33, not in #30 or a follow-up. Reasoning: the audit explicitly requested changes on #33; #30 stays as the snapshot the reviewer approved; #33 carries both the new behaviour AND the contract acknowledgment.

Impact:
- PR #33 now self-contained: code + tests + design-doc alignment + memory sync.
- Phase 2 contract is honest: scar capture IS part of Phase 2; the pipeline still does NOT consume `human_decision`.
- No change to AgentResponse, F3, F7, F8.

Next step:
- Maintainer hands PR #33 back to ChatGPT for re-audit. If accepted, merge order #30 → #31 → #32 → #33 stands.

---

## 2026-04-30 — Phase 2 merged + Phase 3 chunk 3a shipped

What changed:
- Audit returned approve for #30/#31/#32 and a final "merge condition" on #33: scrub residual "scar capture deferred" claims before merge. Done in commit f827234 (`docs/memory/current-state.md`, `docs/local-dogfood.md` annotated with LIFTED markers).
- All four PRs squash-merged in order #30 → #31 → #32 → #33. Stack rebases needed on #32 and #33 to retarget base from previous chunk's branch to `main` after each merge. Conflicts resolved automatically by rebase (the duplicate commits skipped as `previously applied`).
- Phase 3 design PR (#34) opened with `docs/phase-3-loop-controller.md` (297 lines). Three chunks defined: 3a wrapper, 3b reaction, 3c multi-source plug-in. Approved and merged.
- Phase 3 chunk 3a implemented on `feat/loop-controller-wrapper`:
  - `src/karasu/controller/loop.py` — new `LoopController` class. Single bounded queue + single daemon worker. `submit`, `start`, `stop`. Synchronous fallback when not started.
  - `src/karasu/watcher/fs_watcher.py` — refactored. Worker thread + queue logic moved out; watcher now constructs (or accepts) a `LoopController` and delegates via `controller.submit`. Backward-compat properties (`_queue`, `_worker`, `_stopping`, `on_event`) preserved so existing tests pass unchanged.
  - `src/karasu/__main__.py` — `cmd_watch` builds the controller explicitly and passes it to the watcher.
  - `tests/test_controller.py` — 11 new tests covering synchronous fallback, lifecycle, in-order processing, bounded-queue overflow, crash containment, restart-while-alive refusal, restart-after-exit, stop-timeout abandonment, and parity (watcher-through-controller produces identical bus output to direct sync calls).
  - `tests/test_watcher.py` — log-message and logger-name assertions updated to point at `karasu.controller.loop`.
  - `docs/architecture.md` — module map updated; new `controller/` entry.
- 162/162 pass locally (151 prior + 11 new).

Decisions:
- Watcher exposes `_queue` / `_worker` / `_stopping` as read-only properties forwarding to the controller. Pure refactor courtesy: existing watcher tests touch these; rather than rewrite all of them, the seam is made transparent. `tests/test_controller.py` drives the controller directly for the new behaviour.
- `cmd_watch` builds the controller explicitly (production path); the watcher's legacy `on_event=...` constructor still works for tests and external callers.
- No new logging convention. The controller logs at `karasu.controller.loop`; the message text changed from `pipeline queue full` to `controller queue full` and from `on_event callback failed` to `controller callback failed`. Tests updated.

Impact:
- Phase 2 fully on main; the Telegram surface is the operational human-facing layer.
- Phase 3 architectural seam in place. Behaviour is identical pre-/post-3a (parity test enforces). Chunks 3b and 3c can extend the controller without touching the watcher.

Next step:
- Audit gate per Phase 2 cadence. After 3a + 3b + 3c are pushed, maintainer hands the stack to ChatGPT for review before any new phase opens.

---

## 2026-04-30 (later) — Phase 3 chunk 3b: controller reacts to human_decision

What changed:
- `src/karasu/controller/loop.py` — extended:
  - Constructor accepts an optional `bus: JsonlEventBus`. When provided, `start()` also spawns a daemon `karasu-controller-bus` thread that polls the bus via `JsonlTailReader` (start_at_end=True) at 0.5 s intervals.
  - `on_bus_event(event, bus)` — pure dispatch. Filters to `human_decision`, skips redacted texts (containing `(unauthorized)` or `(unknown command)`), and routes `/correct` / `/scar` to the reaction handlers.
  - `_react_correct(args, bus)` reuses `interface.commands.find_agent_response` for prefix lookup.
  - `_react_scar(bus)` reuses `interface.commands.latest_agent_response`.
  - `_resubmit_for(agent_response, bus)` — looks up the correlated `file_change` from the bus, enforces `RESUBMIT_CAP=3` per originating id (in-memory, lock-protected), appends a new `file_change` event with `data.controller_resubmit=True` + `data.resubmit_origin=<id>`, and `submit`s it to the worker.
  - `stop()` joins the bus thread first (one last reaction window), then the worker. Either hang past the timeout leaves state intact and refuses future `start()`.
- `src/karasu/__main__.py` — `cmd_watch` constructs the controller with `bus=bus`. Bus subscription fires alongside the worker.
- `tests/test_controller.py` — 15 new tests: filtering (non-`human_decision`, redacted, unknown command, empty args), `/correct` happy path + unknown prefix, `/scar` happy path + empty bus, resubmit cap enforcement, missing `correlates`, missing originating file_change, lifecycle (bus thread spawned with bus / not without bus / joined cleanly), and an end-to-end test that runs the full bus poll → react → submit chain through the live thread.
- 177/177 pass locally (162 prior + 15 new).

Decisions:
- Resubmit cap key = `originating_file_change.id` only (not `(id, scar_id)`). Simpler; bounds the worst case identically. Phase 3+ may extend the key shape once we have escalation events.
- Resubmits re-emit a fresh `file_change` with `source="controller"` + `data.controller_resubmit=True` + `data.resubmit_origin=<id>`. `analyze` can tell them apart from watcher-originated changes; the pipeline treats them like any other file_change (re-classification + scar consultation rerun).
- Bus subscription uses `start_at_end=True` so the controller does not replay the bus on startup. Reactions only fire for events written after `start()`.
- Redaction filter: bus subscription skips texts matching `(unauthorized)` / `(unknown command)`. The surface already rejected those writes; reacting on them would let an attacker spam the controller via redacted markers.
- Bus thread shutdown order: bus first (so a final reaction can submit), worker second. Mirror the lifecycle the watcher already uses for observer + worker.

Impact:
- The Lucy-Syndrome correction loop closes for the first time. Operator types `/correct <prefix> priority=high` in Telegram → surface records `human_decision` + Scar (Phase 2 chunk 3) → controller picks up the bus event → resubmits the originating `file_change` → pipeline applies the new scar via `_apply_scar_override` → adapter dispatches with the corrected priority.
- Single-worker invariant preserved. Resubmits go through the same bounded queue.
- No change to `AgentResponse`, F3, F7, F8, surface contract.

Next step:
- Phase 3 chunk 3c — generalise trigger sources. Currently the watcher is the only `submit` caller. Chunk 3c introduces a plug-in interface so git hooks (issue #5) can fan into the same controller. GitHub webhook and A2A wait until 3c lands.

---

## 2026-04-30 (final) — Phase 3 chunk 3c: TriggerSource protocol + git-hook source

What changed:
- `src/karasu/controller/sources/__init__.py` — new `TriggerSource` Protocol (PEP 544 structural). `runtime_checkable` so `isinstance` confirms conformance. The watcher already had `start`/`stop`; documenting the seam costs a few lines.
- `src/karasu/controller/sources/git_hook.py` — one-shot git-hook source. Pure helpers: `paths_for_hook(hook, runner)` (shells out to `git diff --cached / show / diff-tree`), `build_events(hook, paths)` (one `file_change` per path with `source="git_hook"` + `data.git_hook=<name>` + per-hook `change_type`: staged / committed / merged), and `submit_for_hook(hook, bus, submit, runner)` that wires path-extraction → bus.append → controller.submit.
- `LoopController` extended:
  - `add_source(source)` registers a `TriggerSource`.
  - `start()` calls each source's `start()` AFTER the worker and bus subscription are up.
  - `stop()` calls each source's `stop()` FIRST so producers stop emitting before the worker drains.
  - `run_forever(poll_interval)` — convenience: `start()`, sleep loop, `stop()` on KeyboardInterrupt. Used by `cmd_watch`.
  - Source start/stop exceptions logged (`karasu.controller.loop`) but do not break the controller.
- `src/karasu/watcher/fs_watcher.py` — `start()` no longer calls `start_pipeline()`; only schedules the observer. The controller is responsible for the worker now. `stop()` symmetric. `start_pipeline`/`stop_pipeline` remain as legacy delegators (tests use them). `run_forever` keeps a standalone path that bootstraps both.
- `src/karasu/__main__.py` — `cmd_watch` now calls `controller.add_source(watcher)` + `controller.run_forever()`. New `cmd_hook` subcommand: builds a one-shot controller (no bus subscription), starts it, calls `submit_for_hook`, drains, stops.
- `tests/test_controller_sources.py` (new, 18 tests):
  - Protocol conformance for the recording stub and the watcher.
  - Source lifecycle (start order after worker, stop order before worker).
  - Multiple sources started in registration order.
  - Source `start()` exception logged + worker stays alive.
  - Source `stop()` exception logged + controller shuts down.
  - Multi-source fan-in: two producers submit; events land in FIFO order per source.
  - Git-hook helpers: `SUPPORTED_HOOKS`, `paths_for_hook` for each hook, blank-line skipping, unknown hook handling.
  - `build_events` shape per hook + unknown hook.
  - `submit_for_hook` happy path, no-paths, unsupported-hook ValueError.
  - End-to-end git-hook flow through a live controller.
  - `controller.start()` starts the watcher's observer when the watcher is registered as a source.
- `docs/architecture.md` — controller layer expanded to mention the sources package.

Decisions:
- `TriggerSource` is a `runtime_checkable` Protocol, not an ABC. The watcher already had the right shape; `isinstance(..., TriggerSource)` documents the seam without forcing inheritance. Future sources (webhook receiver, A2A peer) only need `start()` + `stop()`.
- The git-hook source is NOT a registered `TriggerSource`. Hooks are one-shot CLI invocations; long-running registration would force the controller to manage subprocess state we don't need.
- `submit_for_hook` writes to the bus AND calls `submit`. Same pattern the watcher uses (write first, then enqueue).
- The watcher's `start()` no longer bootstraps the worker. The controller is the lifecycle authority for the worker. `start_pipeline`/`stop_pipeline` and `watcher.run_forever` remain as standalone-test paths.
- Source start exceptions are logged but do NOT break the controller. A failed source loses its events, but the worker and other sources keep functioning.
- Source stop ordering is in registration order (not reverse). Stopping producers in the order they were added is simpler and matches the start order; reverse would only matter if sources had inter-dependencies, which the protocol forbids.

Impact:
- Phase 3 surface complete: dispatch coordinator (chunk 3a) → reaction loop (chunk 3b) → multi-source plug-in (chunk 3c).
- Operators can install git hooks via `.git/hooks/<name>` calling `karasu hook <name>`. Pre-commit / post-commit / post-merge events join the same dispatch queue as the watcher's filesystem events.
- No change to `AgentResponse`, F3, F7, F8, surface contract.

Next step:
- Audit gate per Phase 2 cadence. PRs #34 (design) + #35 (chunk 3a) + #36 (chunk 3b) + #37 (chunk 3c) form the stack. Maintainer hands them to ChatGPT for review before any new phase opens.

---

## 2026-05-02 — Phase 3 dogfood validated, F9/F10/F11 filed

> Full bitácora: [`sessions/2026-05-02-phase-3-dogfood.md`](sessions/2026-05-02-phase-3-dogfood.md). The deep dive covers the setup walkthrough, the real-time F9 debugging, the loop-closure moment with Claude's verbatim quote on the priority rewrite, and the lessons learned.

What changed:
- Dogfood ejecutado en sandbox local Windows (Python 3.13.5, Claude Code 2.1.123, python-telegram-bot 22.7). Sandbox `C:\karasu-phase3-sandbox\` con `karasu.yaml` + bot `@Karasu_dogfood_bot` + `allowed_users: [7509793010]`.
- Loop chunk 3b validado end-to-end: `/scar priority=high` en Telegram → surface graba Scar + `human_decision` → controller (94 ms después) detecta y emite `file_change` con `controller_resubmit=true` → pipeline aplica `_apply_scar_override` → claude responde con priority=high.
- Cap enforcement validado: 6 `/scar` consecutivos → exactamente 3 resubmits, 3 warnings de "cap (3) reached", 0 leaks.
- **Claude verbalizó textualmente** "the scar rule fired correctly — that's why this arrives at high", confirmando que el priority rewrite sí llega al adapter (cosa que no podíamos ver en el bus porque agent_response no persiste priority).
- Issue #39 actualizado con tabla completa de evidencia, latencias, observaciones por slot del runbook.
- Tres findings filed:
  - F9 (#40, P1) — `pyproject.toml` falta `[job-queue]` extra. `karasu chat` crashea en fresh install.
  - F10 (#41, P3) — `_drain_job` flooding APScheduler warnings cuando send_message > poll_interval. Cosmetic.
  - F11 (#42, P3) — `DEFAULT_IGNORE *.tmp` no matchea Notepad atomic-write. Cosmetic.
- PR #38 (integration tests + runbook) mergeado a main antes del dogfood. 201 → 202 tests con F11 fix.

Decisions:
- Trust=2 con autonomous execution funciona bien en producción real: Claude editó `sample.py` solo para arreglar un divide-by-zero. No fue bug — es el contrato Phase 1A operando como diseñado.
- Bus poll de 0.5 s da una latencia de detección sub-segundo (94 ms medido). No hay incentivo para tightening la constante.
- Single-worker + cap=3 funciona bajo spam real. La key del cap por `originating_file_change.id` es suficiente.

Impact:
- Phase 3 cerrada con evidencia operacional. Lucy-Syndrome correction loop probado en vivo por primera vez con Claude CLI real.
- Tres focused F-PRs abiertos siguiendo el patrón Phase 1C.
- No bloquea Phase 3+ archive (webhook / A2A / handoff). Una vez F9/F10/F11 mergeen, pre-mortem doc para la siguiente fase.

Next step:
- Mergear F9 + F10 + F11.
- Cerrar issue #39 cuando los tres landeen.
- Phase 3+ archive: pre-mortem doc-only PR primero, después chunks por concept (issue #5).

---

## 2026-05-02 (Phase 3+ chunk 4a) — GitHub webhook receiver

What changed:
- `docs/phase-3-plus-pre-mortem.md` (#48) merged after two audit rounds (APPROVE WITH MINOR REQUIRED CHANGES → all six REQUERIDOS + two NICE-TO-HAVE applied → APPROVE).
- `src/karasu/controller/sources/webhook.py` — new module:
  - `WebhookHandler` (pure logic): HMAC verify with `hmac.compare_digest`, body size cap (1 MiB default, 413 on oversize), JSON parse (422 on malformed), Content-Length sanity (411 on missing/mismatch), in-memory dedup ring (1024 deliveries), event mapping for `pull_request_review_comment.created` → `file_change` with `source="github_webhook"` + full GitHub metadata. Order: size → JSON → HMAC, all BEFORE any side effect.
  - `WebhookSource` (TriggerSource): `http.server.ThreadingHTTPServer` in a daemon thread. `start`/`stop` lifecycle; `address` property exposes the bound port for `port=0` ephemeral binding in tests.
  - `WebhookConfigError`: raised at construction if secret is missing, empty, or shorter than 16 bytes.
  - `build_webhook_source` factory used by `cmd_serve`.
- `src/karasu/__main__.py` — new `karasu serve --host --port` subcommand. Reads `KARASU_WEBHOOK_SECRET`. Fails CLOSED with exit 2 if absent, empty, or short (F-WH-9). Builds the controller + source and `controller.run_forever()`.
- `tests/test_webhook_source.py` — 26 new tests covering F-WH-1/2/3/5/7/8/9/10. Includes end-to-end live HTTP roundtrip on an ephemeral port.
- `docs/local-dogfood.md` — new "Phase 3+ chunk 4a" section. Historical "do not add webhooks" line annotated `(LIFTED in Phase 3+ chunk 4a)`.

Decisions:
- Order of checks (audit F-WH-8): Content-Length → Content-Length match → JSON parse → HMAC verify. Body size and JSON validity rejected BEFORE the signing path so rejection latency cannot leak signing-key timing.
- Secret minimum 16 bytes (audit F-WH-9). Below that → `WebhookConfigError` at handler construction; `cmd_serve` re-checks first to print a friendly error and exit 2 before any port is bound.
- Dedup is in-memory only (audit F-WH-10). Documented constraint: GitHub does not retry on 200, so the post-restart re-delivery window is narrow and acceptable for the MVP.
- Single mapping (`pull_request_review_comment.created`) in chunk 4a. Other event types ack 200 with no event so GitHub's delivery success metric stays clean and chunk 4c can extend mapping without re-engineering.
- Route boundary explicit (audit F-A2A-5): chunk 4a accepts only `POST /webhook`. Other paths/methods → 404/405. Chunk 4b will add `GET /.well-known/agent-card.json` without overlap.
- Did NOT implement per-source-IP rate limit (F-WH-6). The controller's bounded queue is the backstop; if dogfood evidence demands tighter rate limiting it ships in a focused PR rather than bloating chunk 4a.

Impact:
- Phase 3+ archive opened. The webhook receiver is the second long-running source (alongside the watcher) plugging into the chunk-3c TriggerSource Protocol.
- Pipeline still does NOT consume `human_decision`. The webhook receiver is a producer only; it does NOT trigger `/correct` or `/scar`. Issue #47 (cap-local) is unchanged.
- 228/228 tests pass locally (202 prior + 26 new).
- No change to `AgentResponse`, F3, F7, F8, surface contract, single-worker invariant.

Next step:
- Audit the chunk 4a PR. If accepted, merge and arranque chunk 4b (A2A Agent Card). If pre-req constraints land first (NICE-TO-HAVE #1 priority persist + NICE-TO-HAVE #3 startup warning + issue #47 outline), chunk 4c becomes unblocked too.

---

## 2026-05-02 (Phase 3+ chunk 4a, audit follow-up) — F-WH-6 + F-A2A-5 + cmd_serve tests

What changed:
- Audit on PR #49 returned NO APPROVED with one blocking REQUERIDO: F-WH-6 was deferred in the PR body but the pre-mortem listed it as a failure mode requiring 429. Two NICE-TO-HAVE: explicit F-A2A-5 test for POST /.well-known/agent-card.json → 405, and cmd_serve fail-closed tests.
- src/karasu/controller/sources/webhook.py:
  - New `_RateLimiter` class — sliding-window per-source-IP token bucket. Configurable `max_per_window`, `window_seconds=60.0` default. Lock-protected. Cleanup pass when dict size exceeds `_RATE_LIMIT_CLEANUP_THRESHOLD=1024` to bound memory under path-scan attacks.
  - `WebhookHandler` accepts `rate_limit_per_minute: int | None = 60` (default 60/minute, `None` disables — used by tests). Rejects zero / negative with `ValueError`.
  - `handle()` signature gains `source_ip: str = "0.0.0.0"`. Rate limit check runs FIRST, before path / method / body / signing checks, so a flood from one peer cannot drain CPU on the verifier.
  - `_AGENT_CARD_PATH = "/.well-known/agent-card.json"` reserved for chunk 4b. Path is known to the receiver: POST → 405 (method not allowed for the resource, even though 4a doesn't ship GET); GET → 404 with "agent-card not implemented yet" body. Chunk 4b only has to fill the GET branch.
  - HTTP transport (`_RequestHandler._dispatch`) passes `self.client_address[0]` as `source_ip` to the handler.
  - `build_webhook_source` exposes `rate_limit_per_minute` parameter; `__all__` exports `DEFAULT_RATE_LIMIT_PER_MINUTE`.
- tests/test_webhook_source.py — 11 new tests:
  - F-WH-6: returns 429 above threshold, isolates per source IP, runs before path check, can be disabled with None, rejects zero/negative.
  - F-A2A-5: POST /.well-known/agent-card.json → 405, GET → 404 (4a placeholder), GET /webhook → 405.
  - cmd_serve fail-closed: missing / empty / short secret → exit 2 with the right error message, before binding any port. Drives the real `main(["serve", ...])` entry point through monkeypatched env vars.
- 239/239 pass locally (228 prior + 11 new).

Decisions:
- Rate limit check FIRST (audit choice). Cheaper than HMAC verify; protects path-scan attacks. Authenticated bursts pay the limiter cost too — acceptable for MVP since we expect a single GitHub origin.
- /.well-known/agent-card.json is a reserved path in 4a, not just unknown. Returning 405 on POST today means chunk 4b literally only has to add the GET response body.
- `rate_limit_per_minute=None` is supported as an explicit opt-out for tests that need many requests in a row. Production callers should always set a positive integer.
- Cleanup of the IP→deque dict is bounded but lazy (every >1024 entries triggers a sweep); avoids per-call sweeps for the common case.

Impact:
- F-WH-6 contradiction between PR body and pre-mortem closed: the failure mode is implemented and tested, no longer "out of scope".
- F-A2A-5 boundary now pinned in chunk 4a so chunk 4b can extend without re-engineering the route check.
- cmd_serve fail-closed now has automated coverage; previously only manual.
- No change to AgentResponse, F3, F7, F8, surface contract.

Next step:
- Re-audit chunk 4a PR #49. If accepted, merge and arranque chunk 4b (A2A Agent Card) which fills the reserved GET handler.

---

## 2026-05-02 (Phase 3+ chunk 4b) — A2A AgentCard endpoint

What changed:
- Audit on chunk 4a (PR #49) returned APPROVED after the F-WH-6 follow-up commit. Merged. Audit recommendation for 4b: "Arrancá con GET /.well-known/agent-card.json → JSON mínimo válido. Nada más." — minimum viable endpoint, defer fetch_card + karasu peers CLI to a later chunk.
- New `src/karasu/a2a/` package:
  - `card.py` — `AgentCapabilities`, `Skill`, `AgentCard` dataclasses + `build_karasu_card(base_url=None)`. Static skill list (4 baseline: watch-filesystem, route-events, receive-github-webhooks, record-corrections) — adapter-conditional filtering deferred per audit decision (chunk 4b describes baseline capability, not runtime state).
  - `__init__.py` — re-exports.
- `src/karasu/controller/sources/webhook.py`:
  - `WebhookHandler.__init__` accepts optional `agent_card_json: bytes | None`. When set, `GET /.well-known/agent-card.json` returns 200 with that body; when None, returns 404 "agent-card not configured" (chunk 4a placeholder retained as opt-out).
  - HTTP transport sends `Content-Type: application/json` for the card response specifically; other responses stay `text/plain`.
  - `build_webhook_source` accepts `agent_card: AgentCard | None`, serialises it with `json.dumps(..., indent=2)` once at startup (per F-A2A-1 static-snapshot rule), and passes the bytes to the handler.
- `src/karasu/__main__.py` — `cmd_serve` now builds `build_karasu_card(base_url=f"http://{args.host}:{args.port}")` and passes it to `build_webhook_source`. Operators get a published card by default; opting out requires a code change.
- `tests/test_a2a_card.py` — 12 new tests covering capability defaults, camelCase wire keys (F-A2A-2), card field round-trip, JSON encodability, baseline-skill list pin (F-A2A-3), and information-disclosure containment (F-A2A-1: card MUST carry only name/description/version/url/capabilities/skills + skills carry only id/name/description).
- `tests/test_webhook_source.py` — 5 new chunk-4b tests:
  - GET serves card JSON when configured (200 + verbatim body).
  - POST on the card path remains 405 even when card is configured.
  - Rate limit bucket spans paths (per F-WH-6 design).
  - `build_webhook_source` round-trips the card to bytes.
  - End-to-end: GET on a live ephemeral-port server returns 200 + Content-Type: application/json + valid JSON with 4 skills.
- One existing chunk-4a placeholder test (`test_handler_get_on_agent_card_path_returns_404_in_chunk_4a`) renamed and rewritten to assert the new "not configured" 404 body.
- 256/256 pass locally (239 prior + 17 new).

Decisions:
- Static skill list (audit's call): describes baseline capability, not runtime process state. A `karasu serve` instance and a `karasu chat` instance run as separate processes; the card describes Karasu's capabilities across deployments.
- Card published by default (operator must edit code to opt out). Aligns with the audit's "infra sólida de entrada" framing.
- Card pre-serialised at startup (F-A2A-1 static snapshot). No per-request build, no chance of leaking runtime config because the snapshot is taken before any request lands.
- `application/json` Content-Type for the card response only; other responses stay `text/plain` to avoid confusing peers about non-card paths.
- `fetch_card` helper + `karasu peers <url>` CLI deferred to a follow-up. Audit recommendation: "no abras todo de golpe" — outbound discovery isn't needed for the inbound endpoint to be useful.

Impact:
- Karasu now publishes a discoverable A2A AgentCard whenever `karasu serve` is running. Peer agents can read it without authentication.
- F-A2A-5 boundary (POST card → 405) is enforced by the same guard as 4a; chunk 4b only filled in the GET branch.
- No change to AgentResponse, F3, F7, F8, surface contract.

Next step:
- Audit chunk 4b PR. If accepted, merge. Then chunk 4c (review-comment auto-handoff) becomes the next candidate, gated on issue #47 outline AND NICE-TO-HAVE #3 (startup warning) implementation.

---

## 2026-05-02 (Phase 3+ chunk 4c gates) — issue #47 cap-design outline + NICE-TO-HAVE #3 startup warning

What changed:
- Both chunk 4c hard pre-reqs opened in parallel branches.
- Gate 1 — `docs/issue-47-cap-shape` branch: new `docs/phase-3-cap-design.md` (~310 LOC) picks Option B (chain cap with origin-aware tracking via `controller_chain_depth` field on `file_change.data`). `_chain_root()` walks `resubmit_origin` transitively; `_chain_counts[root_id]` is keyed by chain root, not by per-file id. Documents F-CAP-1..F-CAP-4 + test sketch + frozen-contract additivity. PR #53 open, awaiting audit.
- Gate 2 — `feat/trust-startup-warning` branch:
  - `src/karasu/adapters/base.py` — module-level `AUTONOMOUS_TRUST_LEVEL = 2` constant + `_log = logging.getLogger(__name__)`. `AgentAdapter.__init__` emits a structured `logging.WARNING` whenever `trust_level >= AUTONOMOUS_TRUST_LEVEL`. Message names the adapter, the trust level, and points at `docs/local-dogfood.md "Trust gradient — what trust_level actually does in production"`.
  - `src/karasu/__main__.py` — new `_announce_autonomous_adapters(adapters)` helper. Filters adapters by trust >= AUTONOMOUS_TRUST_LEVEL; if any, prints a loud `⚠ trust gradient: adapter(s) [name(trust=N), ...] will mutate operator state without per-call approval.` banner to stderr once per startup. Wired into both `cmd_watch` and `cmd_serve`. Returns silently on empty / sub-threshold adapter lists.
  - `tests/test_trust_startup_warning.py` — 11 new tests:
    - Layer 1 (logging warning): trust=2 / trust=3 emit a WARNING on `karasu.adapters.base`; trust=0 / trust=1 stay silent; message references `local-dogfood.md` + "Trust gradient" anchor; `AUTONOMOUS_TRUST_LEVEL == 2` pinned.
    - Layer 2 (stderr banner): silent when no autonomous adapter present, loud listing autonomous-only by `name(trust=N)` (sub-threshold adapters omitted), every autonomous adapter listed, runbook anchor present, empty list silent.
- Full suite: 267/267 pass locally (256 prior + 11 new).

Decisions:
- NICE-TO-HAVE #3 promoted from doc-only mitigation to hard chunk-4c pre-req per the Phase 3+ pre-mortem audit. The chunk-4c combination is the trigger: auto-handoff at trust >= 2 turns prompt injection from PR comments into autonomous code edits, so operator MUST get visible feedback at startup, not buried in a runbook.
- Two layers (init log + startup banner) on purpose. Init log is for structured collectors / audit trails; banner is for the human running `karasu watch` interactively. They are tested independently so a future refactor can't silently drop either.
- Banner lives in `__main__` (CLI entry point), not in the library, because adapters constructed by tests / SDK consumers should not pollute their stderr. Libraries get the WARNING via the standard `logging` module; CLI users get the banner on top.
- `_FakeAdapter(AgentAdapter)` for test isolation — concrete `dispatch` raises `NotImplementedError`; only `__init__` runs in the trust-warning tests. Keeps the test file independent of `ClaudeCodeAdapter` config requirements.

Impact:
- Both chunk-4c hard pre-reqs are now in flight. PR #53 (cap-design) and the trust-warning PR are independent and can land in any order.
- No change to AgentResponse, F3, F7, F8, surface contract, single-worker invariant. The init warning is observability-only; the banner is a stderr-only side-effect of CLI startup.
- Trust gradient is now pinned at the type level (`AUTONOMOUS_TRUST_LEVEL`), at the runtime level (`logging.WARNING`), at the operator level (stderr banner), and at the doc level (`docs/local-dogfood.md`). A future contributor moving the bar surfaces the change as a visible diff in the dedicated test.

Next step:
- Audit both gate PRs. After both merge, open `feat/review-comment-handoff` (chunk 4c). Phase 3+ archive (issue #5) is essentially closed after 4c.

---

## 2026-05-02 (Phase 3+ chunk 4c gate-2 audit round 1) — REQUERIDO absorbed

What changed:
- Gate 2 (NICE-TO-HAVE #3 startup warning) opened as PR #54. First audit returned NO APROBADO with 1 REQUERIDO + 2 NICE-TO-HAVE.
- REQUERIDO: `_announce_autonomous_adapters(adapters)` had been wired into `cmd_hook` in addition to the contracted `cmd_watch` / `cmd_serve`. Out-of-scope diff that contaminated stderr on every commit.
- Fix (commit ba3994e):
  - Removed the call from `cmd_hook`. Inline doc comment explains why: hook flow is one-shot per commit, operator already opted into the trust gradient when launching the long-running `cmd_watch` / `cmd_serve` session, structured `logging.WARNING` from `AgentAdapter.__init__` still fires for headless collectors.
  - Added `test_banner_is_wired_into_cmd_watch_and_cmd_serve_only` using `inspect.getsource` to pin the wiring boundary: helper string MUST appear in `cmd_watch` and `cmd_serve`, MUST NOT appear in `cmd_hook`. A future contributor adding the helper to a one-shot entry point trips this test.
- NICE-TO-HAVE 2 absorbed: `flush=True` on the banner `print` so the warning is visible immediately even when stderr is line- or block-buffered.
- NICE-TO-HAVE 1 (real integration test of `cmd_watch` / `cmd_serve` through `main([...])`) deferred this round — contract-pin via `inspect.getsource` covers the same regression surface at lower cost; re-flag if auditor escalates to REQUERIDO.
- 268/268 pass locally (267 prior + 1 contract test).

Decisions:
- The cmd_hook silence is a positive contract, not an oversight. Pinning it with a test (not just a comment) is the durable mitigation.
- `inspect.getsource` based contract pins are an acceptable substitute for full integration tests when the alternative requires stubbing process-blocking entry points (`cmd_watch`'s watcher loop, `cmd_serve`'s socket bind). They do not replace integration tests for behaviour, but they cover the wiring-boundary regression class.

Impact:
- PR #54 awaits re-audit. Both chunk-4c gates remain in flight (PR #53 cap-design + PR #54 trust-warning); both still required before chunk 4c opens.
- No frozen-contract changes. AgentResponse, F3, F7, F8, surface=sink, single-worker invariant, scar=stored-correction-only, I-001..I-006, TriggerSource Protocol all untouched.

Next step:
- Re-audit on PR #54. If APROBADO, merge. PR #53 audit awaited in parallel. Once both land on main, open `feat/review-comment-handoff` (chunk 4c).

---

## 2026-05-02 (Phase 3+ chunk 4c) — review-comment auto-handoff

What changed:
- Both chunk-4c gates merged to main: PR #54 (e43808a, gate 2 trust-warning) and PR #53 (6de0c84, gate 1 cap-design outline). Cap-design audit absorbed 3 REQUERIDOS in round 2 (F-CAP-5 cycle/forged-deep lineage, F-CAP-2 source=controller alignment, restart semantics) + 1 NICE-TO-HAVE (eviction sketch).
- New branch `feat/review-comment-handoff` opened off main with both gates landed.
- `src/karasu/router/dispatcher.py` — `Dispatcher.dispatch` now copies `event.data` into `AgentRequest.metadata` so adapters see source-specific fields (`github_body`, `github_author`, `github_pr`, `github_repo`) without widening the named schema. The metadata dict is a copy, not a reference, so adapters cannot mutate the bus event mid-dispatch.
- `src/karasu/adapters/prompt_builder.py` (NEW) — `PromptBuilder` with two branches: default (legacy one-line dispatch summary, identical to pre-chunk-4c) and github (fenced + USER-DATA-labelled + capped). Detection by presence of `metadata["github_body"]`. Constants `DEFAULT_BODY_CAP_BYTES=4096`, `DEFAULT_AUTHOR_CAP_BYTES=256`. `_truncate_with_marker` slices on UTF-8 bytes (not code points) and appends `[truncated, original was N bytes]` on overflow.
- `src/karasu/adapters/claude_code.py` — `ClaudeCodeAdapter` now accepts an optional `prompt_builder` kwarg, defaults to `PromptBuilder()`. `_build_argv` delegates to the builder. The change is back-compat: existing callers without the kwarg get the default one-line prompt.
- `tests/test_router.py` — 3 new tests: metadata round-trip with github_* fields, copy-not-reference (adapters cannot mutate event.data through metadata), watcher events get a metadata dict but no github fields.
- `tests/test_claude_prompt_builder.py` (NEW) — 18 tests covering: default branch matches pre-chunk-4c format, default branch when metadata has no github_body / explicit None, F-HANDOFF-1 USER DATA prefix + triple-backtick fence + author-untrusted label + pr+repo header + missing author/repo defaults, F-HANDOFF-5 cap held + truncation marker + byte-count-not-char-count + DEFAULT_BODY_CAP_BYTES==4096 + DEFAULT_AUTHOR_CAP_BYTES==256 + author cap, construction guards (zero/negative caps rejected), F-HANDOFF-3 ClaudeCodeAdapter wires the injected builder by name + falls back to default when none injected.
- `docs/local-dogfood.md` — new "Phase 3+ chunk 4c" section. Explicit warning on `trust_level >= 2` + auto-handoff combination. What does NOT ship in 4c (multi-rule routing, token-based replies, non-comment sources, A2A negotiation, edited/deleted comments, path-existence fallback, chaining).
- 289/289 pass locally (268 prior + 21 new chunk-4c tests).

Decisions:
- PromptBuilder is a single class with overrideable `build(request)` method, not a registry of named builders. Per the open question in the next-session pre-mortem, the registry waits until LoopController owns the rule table; today one class with two branches is enough.
- Detection of the github branch is metadata-driven (`metadata["github_body"] is not None`), not source-driven (`event.source == "github_webhook"`). The metadata signal is more local; an adapter doesn't need to know which TriggerSource produced the event.
- The metadata dict on `AgentRequest` is `dict(event.data)` — a shallow copy. Sufficient because event.data values are JSON-serialisable scalars / collections; mutation by an adapter on the dict's top level can't reach the bus event. If a future field carries nested mutable state, this needs revisiting.
- author cap = 256 bytes (smaller than body cap because GitHub itself bounds usernames at 39 chars; 256 is defence in depth against forged payloads).
- F-HANDOFF-6 (path-existence fallback to metadata-only prompt for force-push aftermath) is explicitly out of scope. Chunk 4c assumes the path is valid at comment-creation time. Filed as a follow-up.
- `_truncate_with_marker` slices on raw UTF-8 bytes (not code points) so the cap is effective against pathological inputs that pack many bytes into few characters (e.g. CJK or pathological emoji sequences). The decode uses `errors="ignore"` to drop a partial trailing UTF-8 sequence the byte slice may have left.

Impact:
- A `pull_request_review_comment.created` event now flows end-to-end: webhook receiver → bus → dispatcher → ClaudeCodeAdapter → PromptBuilder.build() → claude -p → agent_response. Body is fenced + capped before Claude ever sees it.
- Frozen contracts untouched: AgentResponse, F3, F7, F8, surface=sink, single-worker invariant, scar=stored-correction-only, I-001..I-006, TriggerSource Protocol. The new `AgentRequest.metadata` field already existed in `base.py` (added in a prior chunk, unused); chunk 4c just wires it through.
- Operator's repo is the trust boundary. The library-side mitigations (fence + cap + USER DATA prefix + trust-warning banner) make the risk visible but do not eliminate it. Operators running at `trust_level >= 2` with auto-handoff are giving every PR commenter the ability to drive Claude prompts.

Next step:
- Audit chunk 4c PR. After accepted + merged, the Phase 3+ archive (issue #5) is essentially closed; remaining items (auto-installation of git hooks, additional GitHub event types, A2A negotiation) are open-ended follow-ups.

---

## 2026-05-02 (Phase 3+ chunk 4c hardening) — three NICE-TO-HAVE absorbed

What changed:
- Audit on PR #55 returned APROBADO with no REQUERIDOS but three NICE-TO-HAVE follow-ups. All three landed as a single ~30-LOC hardening PR before any new chunk opened.
- `src/karasu/adapters/prompt_builder.py`:
  - `_fence_for(body)` — dynamic fence length per CommonMark / GitHub Markdown nested-fence rule. Scans the body for the longest run of backticks; opens with one more (minimum 3). A reviewer's inner ``` blocks survive as body content instead of prematurely closing the outer fence. Hardens F-HANDOFF-1 in the realistic case where the comment body itself contains code blocks.
  - `_truncate_with_marker` now emits `[truncated, original was N bytes / M chars]`. Bytes remain the canonical metric (the cap is in bytes); chars are added for human readability.
- `src/karasu/router/dispatcher.py` — inline comment on the `dict(event.data)` line documenting "SHALLOW COPY BY DESIGN" with the rationale and the trigger that would force a revisit (nested mutable state on a future source).
- `tests/test_claude_prompt_builder.py`:
  - Two existing tests updated to assert the new marker format.
  - One renamed (`test_truncation_marker_quotes_original_byte_count_not_char_count` → `test_truncation_marker_uses_bytes_as_canonical_metric`) since both metrics now appear; the intent is still to pin "bytes is the canonical unit".
  - Five new fence tests: 3-backtick fence when body has no backticks; fence grows to 4 when body contains a 3-backtick run with the inner block surviving verbatim; fence grows to 5 with a 4-run; pathological 9-run → 10-backtick fence; fence appears exactly twice.
- 294/294 pass locally (289 prior + 5 new fence tests; 3 truncation-marker tests updated, no net count change there).

Decisions:
- The fence-length scaling is the canonical Markdown approach (not backslash-escape). Operators reading the prompt see the body verbatim; inner ``` blocks stay legible. Escaping would mangle code in comments, which is the worst trade for this surface.
- Bytes-and-chars in the marker, not chars-only or bytes-only. Bytes is the canonical metric (matches the cap configuration); chars is human-friendly. Keeping both keeps everyone's audit story honest.
- The shallow-copy comment in dispatcher.py is scoped narrowly: today's `event.data` values are JSON-shaped scalars / collections, so `dict(event.data)` is sufficient to prevent adapter mutation reaching the bus. The comment names the trigger that would force a deeper copy (nested mutable state on a future source).

Impact:
- Chunk 4c is now hardened against the realistic case where a reviewer pastes their own code block. PR comments containing ``` are no longer a silent prompt-injection vector.
- Frozen contracts untouched.

Next step:
- Audit the hardening PR. If APROBADO, merge. After that, the natural next piece of work is the issue #47 implementation PR (Option B chain cap, design already on main as docs/phase-3-cap-design.md). Phase 3+ archive (issue #5) is essentially closed; remaining items are open-ended follow-ups.

---

## 2026-05-02 (Phase 3+ post-archive) — issue #47 implementation

What changed:
- Implementation of the chain-cap shape designed in PR #53 (`docs/phase-3-cap-design.md`). Closes issue #47 — the last code-shaped item open from the Phase 3+ archive.
- `src/karasu/controller/loop.py`:
  - `RESUBMIT_CAP = 3` → `CHAIN_CAP = 3`. Same magnitude so the Phase 3 dogfood-validated behaviour stays continuous; the new key shape is "chain root" instead of "originating id".
  - New `MAX_CHAIN_WALK_DEPTH = 64` (~21x the cap) and `CHAIN_COUNTS_MAX_SIZE = 1024` (matches the F-WH-2 dedup ring magnitude).
  - `_resubmit_counts` / `_resubmit_lock` renamed to `_chain_counts` / `_chain_lock`.
  - New `_chain_root(file_change, bus)` walks `resubmit_origin` transitively with three layered defences: F-CAP-1 (missing parent → treat current as root), F-CAP-2 (only follow lineage on `source="controller"` events; external sources are roots regardless of which controller_* fields they carry), F-CAP-5 (visited_set + MAX_CHAIN_WALK_DEPTH ceiling, both independent).
  - `_resubmit_for` walks to the chain root, increments the per-root counter under the lock, and persists `controller_chain_depth` on the new bus event. The new event's depth is `parent_depth + 1` ONLY when the parent is itself a controller event with a valid integer depth; otherwise depth resets to 1 (F-CAP-2 alignment with pseudo-code).
  - F-CAP-3 eviction: when `_chain_counts` exceeds `CHAIN_COUNTS_MAX_SIZE`, the insertion-order oldest entry is evicted. Logged at INFO. Worst case is one extra shot at a chain whose counter was evicted — same trade-off as F-WH-10 dedup ring overflow.
- `tests/test_controller.py`:
  - Existing `test_resubmit_cap_enforced` updated to assert `CHAIN_CAP` and to verify `controller_chain_depth=1` is persisted on each spam-at-depth-1 resubmit (preserves Phase 3 dogfood behaviour).
  - 11 new tests covering: chain-root walks (self for watcher event; multi-hop controller lineage), F-CAP-1 missing parent, F-CAP-2 ignores lineage on non-controller source, F-CAP-2 depth resets to 1 when parent is non-controller, F-CAP-5 cycle break (via visited_set), F-CAP-5 pathologically-deep acyclic break (via MAX_CHAIN_WALK_DEPTH ceiling), persisted `controller_chain_depth` on bus, independent chains do not share a cap, F-CAP-3 eviction at tightened ceiling=3, restart semantics (`_chain_counts` empty on a fresh controller; chain-at-cap pre-restart admits one more resubmit post-restart).
- `tests/test_phase3_integration.py`:
  - `test_resubmit_cap_holds_under_spammed_corrections` updated to assert `CHAIN_CAP` and to verify all spam resubmits carry `controller_chain_depth=1`.
- 305/305 pass locally (294 prior + 11 new).

Decisions:
- `CHAIN_CAP = 3` kept the same magnitude as the previous `RESUBMIT_CAP`. The dogfood evidence at 3-of-6 enforcement is still valid because spam-at-depth-1 (the dogfood scenario) increments the same per-chain counter as a progressing chain.
- Eviction policy: insertion-order oldest. Picked one policy (not "oldest or last-touched" as the design doc listed alternatives) per the PR #53 round-2 NICE-TO-HAVE: "elegir una sola policy de eviction: oldest o last-touched, no ambas alternativas". Insertion-order is simpler than last-touched (no per-access bookkeeping) and matches the F-WH-10 ring's shape.
- `CHAIN_COUNTS_MAX_SIZE = 1024` matches the dedup ring magnitude and is well above any plausible operator workload.
- `MAX_CHAIN_WALK_DEPTH = 64` keeps a wide margin over the cap (3) without making forged-deep walk costs measurable in normal cases.
- The cycle-break test patches `_find_file_change` on the controller instance because `JsonlEventBus` is append-only and we need two events whose `resubmit_origin` fields point at each other (impossible to construct purely through `bus.append` because event ids are not known until after append). The patch only swaps the lookup function — the cycle detection itself is the real code path.

Impact:
- Issue #47 closes: chunk 4c's auto-handoff is no longer single-hop-only by external policy; it's bounded by construction at CHAIN_CAP=3 hops per chain. F-HANDOFF-4 (cap distributed-loop amplification) is now bounded.
- Phase 3+ archive (issue #5) is fully closed in terms of code work. Remaining items are all open-ended follow-ups (fetch_card / karasu peers CLI, F-HANDOFF-6 path-existence fallback, persist effective priority on agent_response).
- Frozen contracts untouched. AgentResponse / F3 / F7 / F8 / surface=sink / single-worker / scar=stored-correction-only / I-001..I-006 / TriggerSource Protocol all preserved. The new `controller_chain_depth` field on file_change.data is the additive schema bump described in the design doc.

Next step:
- Audit the PR. After accepted + merged, the only items left are the audit-deferred follow-ups; none are blocking.
