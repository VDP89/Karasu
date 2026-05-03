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

---

## 2026-05-02 (Phase 3+ post-archive) — A2A outbound discovery (fetch_card + karasu peers)

What changed:
- Audit-deferred follow-up from chunk 4b. Symmetric counterpart to the inbound `/.well-known/agent-card.json` endpoint: an operator can now read a peer agent's card without a third-party HTTP client.
- New `src/karasu/a2a/fetch.py`:
  - `fetch_card(base_url, *, timeout=DEFAULT_FETCH_TIMEOUT)` — stdlib-only (`urllib.request`). Returns the raw decoded JSON dict; the caller decides whether to reconstruct an `AgentCard`.
  - `_resolve_card_url` appends `/.well-known/agent-card.json` if absent; preserves an explicit suffix; strips a trailing slash before appending.
  - `AgentCardFetchError` covers all surfaced failures (HTTP non-2xx, network error, invalid JSON, non-object top-level). One exception class instead of three urllib classes for the caller.
  - `DEFAULT_FETCH_TIMEOUT = 5.0`. Zero / negative timeout → `ValueError`.
  - `AGENT_CARD_PATH = "/.well-known/agent-card.json"` re-exported.
- `src/karasu/a2a/__init__.py` re-exports `fetch_card`, `AgentCardFetchError`, `DEFAULT_FETCH_TIMEOUT`, `AGENT_CARD_PATH`.
- `src/karasu/__main__.py`:
  - New `cmd_peers(args)` — formats the card by default; `--json` prints raw JSON; `--timeout` configures the HTTP timeout. Read-only (no bus access, no side effects).
  - Wired into `build_parser` as `karasu peers <url> [--timeout N] [--json]`.
  - Module docstring updated to list `karasu peers`.
- `tests/test_a2a_fetch.py` (NEW) — 17 tests: URL resolution (3); end-to-end against the real chunk-4b webhook source with a card configured (3, including explicit-suffix and 404-without-card paths); error paths via mocked `urlopen` (5); timeout default pin + zero/negative guard (2); CLI tests (4 — formatted output, --json, fetch failure → exit 2, --timeout passed through).
- 322/322 pass locally (305 prior + 17 new).

Decisions:
- Stdlib-only on purpose. Adding `requests` for one HTTP GET would be a dependency footprint mismatch with the receiver (which also uses stdlib). `urllib.request` is enough and gives per-call timeout + structured exceptions.
- Return the raw JSON dict, not a reconstructed `AgentCard` dataclass. The CLI's job is to render; programmatic consumers can call `from_dict` later if needed. The wire format uses camelCase (e.g. `pushNotifications`); the dataclass uses snake_case. Reconstructing here would force a second snake/camel mapping that nothing today consumes.
- One exception class (`AgentCardFetchError`) wrapping all failure modes. Operators (and tests) catch one type instead of `URLError` / `HTTPError` / `JSONDecodeError` / custom validation errors. Each wrapped exception preserves `__cause__` for postmortem.
- Zero / negative timeout raises `ValueError` rather than relying on urllib's "treat as no timeout" behaviour. Operators typing `--timeout 0` thinking it means "no timeout" would otherwise get a silently-hanging fetch; fail-fast is safer for an outbound HTTP call.
- `cmd_peers` exits 2 (not 1) on fetch failure — same convention as `cmd_serve` / other CLI fail-fast paths in this repo.

Impact:
- Karasu can now both publish (chunk 4b) AND consume A2A AgentCards. The discovery loop is symmetric end-to-end.
- No new runtime dependency. No bus mutation. No surface change.
- Frozen contracts untouched: AgentResponse, F3, F7, F8, surface=sink, single-worker, scar-stored-only, I-001..I-006, TriggerSource Protocol all preserved.

Next step:
- Audit the PR. After merge, two follow-ups remain (F-HANDOFF-6 path-existence fallback, persist effective priority on agent_response.data); none blocking.

---

## 2026-05-02 (Phase 3+ post-archive) — F-HANDOFF-6 path-existence fallback

What changed:
- Audit-deferred follow-up from chunk 4c. Closes F-HANDOFF-6 part 2 (the path-existence half — edited / deleted comments were already filtered at the webhook receiver in chunk 4a).
- `src/karasu/adapters/prompt_builder.py`:
  - New `_default_path_exists(path)` — `Path.exists()` lookup with empty-path-guard and `OSError` swallowing (pathological inputs like embedded NUL on POSIX must not let an `OSError` escape into the prompt builder).
  - `PromptBuilder.__init__` accepts an optional `path_exists` callable, defaulting to `_default_path_exists`. Injectable so tests probe both branches without touching the filesystem and a future deployment can swap in a git-tree-aware probe (e.g. "is this path in HEAD's tree?") without subclassing.
  - `_build_github` probes the workspace at prompt-build time. When the path is present, the existing canonical "Karasu review-comment handoff:" header is emitted unchanged. When the path is absent, the header gains a `(metadata-only)` suffix and a `NOTE: path '<X>' is not present in the current workspace ... Do NOT attempt edits; treat this dispatch as informational only.` block lands between the header and the USER DATA prefix. Body is still fenced + capped — F-HANDOFF-1 / F-HANDOFF-5 primitives are preserved in the metadata-only branch by design (a force-pushed-away path is exactly when input is most suspect).
- `tests/test_claude_prompt_builder.py` — 8 new tests covering: path-present uses canonical header without `(metadata-only)`; path-missing emits the metadata-only header + the NOTE + the `Do NOT attempt edits` instruction + USER DATA still labels the body; metadata-only branch preserves fence+cap; `path_exists` is consulted per build with the request path; default probe treats empty path as missing; default probe handles `OSError` as missing; default probe returns True for an existing tmp_path file; metadata-only branch quotes the path with repr-style quoting so paths with whitespace render unambiguously.
- 332/332 pass locally (324 prior + 8 new). 23 existing prompt_builder tests continued to pass — their assertions hold in both branches because the metadata-only variant is a strict additive on the path-present variant for the security primitives they pin.

Decisions:
- `path_exists` is a callable kwarg, not a config knob. Default is filesystem; tests inject; future git-tree-aware probes inject. Configurability through the YAML would need a runtime resolver registry, which isn't justified yet (one production probe at a time).
- The metadata-only header gets `(metadata-only)` as a suffix, not a prefix. The model's first-line context is still "review-comment handoff"; the suffix makes the missing-path case visible without breaking the canonical mental model.
- Empty path reads as missing (not as cwd). Otherwise an event with `path=""` would silently advertise the operator's repo root as editable. Path probes against `""` return False explicitly.
- `OSError` from `Path.exists` is swallowed and treated as missing. Pathological inputs (embedded NUL, very long paths on Windows, etc.) shouldn't crash the dispatch — the metadata-only fallback is the safe stop.
- The body is still fenced + capped in the metadata-only branch. Reasoning: a force-pushed-away path is exactly when the comment author's input is most suspect (chain reordering, branch deletion). Weakening the F-HANDOFF-1 / F-HANDOFF-5 primitives there would be the wrong direction.

Impact:
- Chunk 4c is now hardened against the second half of F-HANDOFF-6. The first half (edited / deleted comments) is filtered at the receiver. Together: the dispatch the model sees either has a valid editable path OR is explicitly labelled as informational with the model instructed not to edit.
- Frozen contracts untouched.

Next step:
- Audit the PR. After merge, one follow-up remains: persist effective priority on agent_response.data (Phase 3 audit, non-blocking).

---

## 2026-05-02 (Phase 3+ post-archive) — persist effective priority on agent_response

What changed:
- Audit-deferred follow-up from the Phase 3 audit. The agent_response event now carries the EFFECTIVE priority (post any scar / classifier override) on `data.priority` so an operator inspecting `events.jsonl` post-hoc can audit "what priority did this dispatch run at?" without cross-referencing the originating file_change.
- `src/karasu/router/dispatcher.py`:
  - `Dispatcher.dispatch` now sets `data["priority"] = request.priority` on the emitted agent_response. Additive schema bump; old consumers that ignore the field continue to work.
- `tests/test_router.py` — 3 new tests: priority="high" persisted; priority defaults to "normal" when absent on the file_change; post-scar-override priority is what reaches both the adapter AND the agent_response (no audit-trail divergence).
- 335/335 pass locally (332 prior + 3 new).

Decisions:
- Persist the EFFECTIVE priority (post-override), not the original classifier-assigned value. The whole point of the audit follow-up is to know what the adapter actually saw; the pre-override value lives on the originating file_change already.
- Additive schema bump on agent_response.data, not on the dispatch / response sub-dicts. Priority is a request-side attribute (what the dispatcher sent the adapter), so it lives next to `correlates` and `path` in `data`. Keeps the dispatch dict purely about adapter outcome (agent / status / trust_level) and the response dict about content.
- No default value populated when the field is absent on consumer reads — operators reading agent_response.data["priority"] of an old (pre-this-PR) event will get a KeyError, which is the right signal that the field is missing and the audit trail is incomplete for that event. A silent default would mask the gap.

Impact:
- Phase 3 audit's last queued NICE-TO-HAVE is closed.
- Combined with the controller_chain_depth field landed in #57, agent_response and resubmitted file_change events now carry enough metadata for analyze to reconstruct the full dispatch story (priority + chain depth + correlation) post-hoc, even across restarts.
- Frozen contracts untouched.

Next step:
- Audit the PR. After merge, the only items left are operational (controlled dogfood of chunk 4c) or speculative future enhancements (git-tree-aware probe, fetch_card retry). No code work blocking.

---

## 2026-05-03 — effective_priority helper (PR #60 follow-up)

What changed:
- Audit-deferred follow-up from PR #60. Public read-side accessor `karasu.eventbus.effective_priority(event)` returns `event.data["priority"]` (or `None` when absent) so the bus-audit tooling does not duplicate the "None-vs-default" decision at every call site.
- `src/karasu/eventbus/queries.py` (NEW) — owns the helper. Future read-side helpers over `Event` records (chain-depth, correlate-walks, etc.) belong here so `jsonl_bus.py` stays focused on persistence.
- `src/karasu/eventbus/__init__.py` — re-exports `effective_priority` so callers can `from karasu.eventbus import effective_priority`.
- `tests/test_eventbus_queries.py` (NEW) — 5 tests covering: agent_response present, agent_response absent (returns `None`), explicit `None` value, controller-resubmit `file_change` (chunk 3b inherits priority), non-string coercion.
- `docs/event-schema.md` — new "Priority semantics" section explaining that `data.priority` on agent_response is the EFFECTIVE priority and pointing tooling at the helper. Notes that `None` surfaces a real audit-trail gap rather than substituting a default.
- 340/340 pass locally (335 prior + 5 new).

Decisions:
- Helper returns `None`, not a default. PR #60 deliberately avoided populating a default so pre-PR #60 `agent_response` events stay observable as gaps. The helper preserves that semantic contract; callers decide whether `None` is acceptable for their use case (e.g. analyze can show "—", a future analytics pass can flag it).
- Helper coerces to `str`. Bus events round-trip through JSON, so today every priority value is already a string; coercing defensively keeps callers from getting bitten if a future source writes an int / enum / number.
- Did NOT add the optional dual `priority_original` / `priority_effective` fields on `agent_response.data`. The audit listed them as conditional on "analytics surface a need". No analytics consumer exists today, so the additive schema bump is deferred.
- New module under `eventbus/queries.py` rather than free functions inside `jsonl_bus.py`. Persistence and read-side queries are different concerns; splitting them now avoids a future refactor when the second helper lands.

Impact:
- Frozen contracts untouched (additive helper, additive docs section, no schema change).
- The remaining `Future:` entry under `current-state.md` shrinks to "optional dual priority fields if analytics surface a need" — a smaller, conditional follow-up.

Next step:
- Audit the PR. After merge, continue down the remote-friendly queue: optional retry on network error in `fetch_card` (PR #58 follow-up), then git-tree-aware path probe in `PromptBuilder` (PR #59 follow-up). UI-2 still parked until operator has computer + browser.

---

## 2026-05-03 (later) — fetch_card retry on transient network errors (PR #58 follow-up)

What changed:
- Audit-deferred follow-up from PR #58. `fetch_card` now accepts an optional `retries` kwarg (default 0); `karasu peers --retries N` exposes it on the CLI. Designed for the operator who runs `karasu peers` over a flaky link or against a peer that just restarted.
- `src/karasu/a2a/fetch.py`:
  - New constant `DEFAULT_FETCH_RETRIES = 0` — preserves byte-for-byte the previous single-shot semantics for every existing caller. Operators opt in via the kwarg / flag.
  - `fetch_card(base_url, *, timeout=..., retries=0)` loops attempts on `URLError` only. `HTTPError` and downstream JSON / shape errors short-circuit immediately — those are real answers from the peer, not transient network failures, and retrying them would amplify a server outage.
  - Backoff schedule: `0.5 s, 1.0 s, 2.0 s, 4.0 s, 4.0 s, ...` (exponential up to a 4 s cap). Total wall-clock is bounded by `(timeout + backoff) * (retries + 1)`.
  - `_sleep_backoff(attempt)` extracted as a module-level function so tests patch it surgically rather than `time.sleep`. Avoids accidentally swallowing pytest-internal sleeps.
  - `retries < 0` raises `ValueError` (same fail-fast convention as the `timeout <= 0` guard). An operator typing `--retries -1` should not silently degrade to "no retries".
- `src/karasu/a2a/__init__.py` re-exports `DEFAULT_FETCH_RETRIES`.
- `src/karasu/__main__.py`:
  - `cmd_peers` passes `retries` through to `fetch_card`.
  - `--retries` CLI flag added with `default=DEFAULT_FETCH_RETRIES` so the help-text default tracks the constant.
- `tests/test_a2a_fetch.py` — 9 new tests:
  - Default `DEFAULT_FETCH_RETRIES == 0` pinned.
  - `retries=0` (default) → 1 urlopen call, 0 backoff sleeps.
  - 2 URLErrors then 200 with `retries=2` → 3 calls, 2 sleeps, success returned.
  - All URLErrors with `retries=3` → 4 calls, 3 sleeps, final error wrapped.
  - HTTPError with `retries=5` → 1 call, 0 sleeps (no retry on real server answer).
  - Invalid JSON with `retries=3` → 1 call, 0 sleeps (no retry on parse error).
  - `retries=-1` → ValueError.
  - `_sleep_backoff` schedule matches `[0.5, 1.0, 2.0, 4.0, 4.0]` for attempts 0..4.
  - CLI: `--retries 2` propagates to `urlopen.call_count == 3` on URLError.
- 349/349 pass locally (340 prior + 9 new).

Decisions:
- Default `retries=0`. Every existing caller keeps single-shot semantics; opt-in via the kwarg / flag. Avoids retroactively changing the cost / latency profile of a function that 4 places already call.
- Retry only on `URLError`, not on `HTTPError` or JSON / shape errors. The motivating use case is "DNS / TCP hiccup that resolves in <1 s", not "peer is genuinely down" — the latter benefits from the operator seeing the failure quickly. Per F-WH-style fail-fast conventions in this repo.
- Exponential backoff with a 4 s cap. Caps the wall-clock surprise: operator can compute "worst case ~ (timeout + 4) × (retries + 1)" without reading the implementation. Initial 0.5 s is small enough that a single retry on a transient hiccup feels instant.
- Extracted `_sleep_backoff` module-level. Tests patching `time.sleep` directly would swallow sleeps from any other code path that happened to enter via the same call (pytest-asyncio internals, threading shutdown, etc.). Patching the named helper isolates the assertion.
- `--retries` (not `--max-retries` or `--retry-count`). Matches `--timeout` cadence for the same CLI; one flag = one operator concern.

Impact:
- `karasu peers` is more forgiving on flaky networks without changing default behaviour for anyone.
- One more entry strikes off the `Future:` list in `current-state.md`.
- Frozen contracts untouched (additive parameter with backwards-compatible default, additive constant, no schema change).

Next step:
- Continue the remote-friendly queue. Next: git-tree-aware path probe in `PromptBuilder` (PR #59 follow-up), then the UI-0 lint script for bare `outline:none`, then UI-9 deferred items (path-traversal test + EVENT_LOG config-aware).

---

## 2026-05-03 (later still) — git-tree-aware path probe (PR #59 follow-up)

What changed:
- Audit-deferred follow-up from chunk 4c (PR #59). The default `PromptBuilder` probe is `Path.exists` — i.e. "is this file on disk in the working tree?". This change ships a sibling probe that consults the COMMITTED tree at a given ref, so deployments where the repo state is the source of truth (bare repo, divergent workspace) can opt in.
- `src/karasu/adapters/git_probe.py` (NEW):
  - `git_tree_path_exists(path, *, ref="HEAD", cwd=None, timeout=5.0, runner=_default_runner)` — runs `git cat-file -e <ref>:<path>`; returns True on rc=0, False on rc!=0 / empty path / runner error.
  - `_default_runner(argv, cwd, timeout) -> int` — wraps `subprocess.run`, swallows `FileNotFoundError` / `TimeoutExpired` / `OSError` and returns a sentinel non-zero rc. Never raises into the dispatch path.
  - `runner` is injected in the same shape as `karasu.controller.sources.git_hook.GitRunner` — module-level callable type alias, fake `runner` for unit tests, real `_default_runner` in production.
  - `_DEFAULT_GIT_PROBE_TIMEOUT_S = 5.0` — generous enough for cold-cache cat-file on a large repo, short enough that an operator's dispatch never hangs on a wedged git process.
- `src/karasu/adapters/__init__.py` re-exports `git_tree_path_exists` and `PromptBuilder`. The `from karasu.adapters import PromptBuilder, git_tree_path_exists` pattern in the module docstring example now resolves.
- `tests/test_git_probe.py` (NEW) — 17 tests across three layers:
  - Unit (mocked runner): rc=0 → True; rc!=0 → False; empty path skips runner entirely; ref / cwd pass-through; default cwd=None pinned.
  - `_default_runner` error fallthrough: FileNotFoundError, TimeoutExpired, OSError each return a non-zero rc.
  - End-to-end against a real `git init` repo in `tmp_path`: committed file → True; untracked file → False; missing path → False; unknown ref → False; not-a-repo cwd → False. All gated by `pytest.mark.skipif(not _git_available())`.
  - PromptBuilder integration: `path_exists=lambda _: False` → metadata-only branch with "Do NOT attempt edits"; `path_exists=lambda _: True` → full handoff branch.
- 366/366 pass locally (349 prior + 17 new).

Decisions:
- `runner` injected via callable, mirroring the `git_hook` source pattern. Lets tests verify argv shape without spawning real processes; production wiring stays the simple default.
- Probe never raises. The dispatch path is on the hot loop for review-comment handoff; an exception in the probe would break dispatch entirely, which is much worse than a missed "this file is editable" optimization. Failure modes (no git, not a repo, unknown ref, timeout) all collapse to False — the prompt falls through to metadata-only, which is the safer default.
- Default `cwd=None` lets `git` use its own resolution (the calling process's cwd). Pinning this avoids a future "guess via Path.cwd()" change becoming an accidental behavioural shift.
- Empty path short-circuits without invoking the runner. `git cat-file -e <ref>:` is a directory-tree query that could return rc=0 unexpectedly; the existing `_default_path_exists` already returns False on empty, so the git-tree probe matches.
- Probe lives in `karasu.adapters` (not `karasu.eventbus.queries`). It is read-side over the workspace, not over the bus; coupling it to PromptBuilder via the same package is the right neighbourhood.
- `PromptBuilder` itself is unchanged. The injection point landed in PR #59 already; this chunk only supplies the optional implementation.

Impact:
- Three of the original five queued "Future:" entries now closed (priority helper, fetch_card retry, git-tree probe).
- No bus mutation, no schema change, no new runtime dependency. Frozen contracts untouched.

Next step:
- Continue the queue: UI-0 lint script for bare `outline:none` (UI-2 deferred), then UI-9 deferred items (URL-encoded path-traversal test for `/assets/*` + config-aware `EVENT_LOG`).

---

## 2026-05-03 (later still ×2) — UI-0 lint script for bare outline:none

What changed:
- UI-0 round-2 NICE-TO-HAVE — UI-2 deferred lint script catches bare `outline: none` rules that strip the focus ring without the canonical `--focus-ring` replacement. Shipped ahead of UI-2 since it is pure Python tooling (no browser, no design tokens needed yet) and lets every subsequent UI-N PR start from a CI-enforced baseline.
- `scripts/lint_ui_css.py` (NEW):
  - Walks each provided root for `*.css` files and the inline `<style>` block of every `*.html`.
  - For each rule block (`{ ... }`) that contains `outline: none` / `outline: 0` / no-space variants, requires a matching `--focus-ring` reference in the same block. Otherwise flagged as a violation.
  - Reports `path:line: bare 'outline: none' — UI-0 brief §6 requires --focus-ring replacement in the same rule block.`
  - Default scan root: `src/karasu/ui/static`. CLI accepts additional roots: `python scripts/lint_ui_css.py docs/ui/explorations`.
  - Exit 0 = clean, exit 1 = at least one violation.
  - Missing roots are treated as "nothing to scan" (exit 0) so composed CI invocations stay simple.
- `tests/test_lint_ui_css.py` (NEW) — 15 tests across three layers:
  - Unit (`lint_css_text`): bare none / 0 / no-space variants flagged; `outline: none + box-shadow: var(--focus-ring)` allowed; non-bare values (`outline: 2px solid var(--accent)`) allowed; `outline-color: none` NOT matched (different property); multi-block files yield one violation per offending block; at-rule-nested compliant blocks do not mask sibling violations.
  - File-level: CSS suffix routes via `lint_css_text`; HTML inline `<style>` parsed with correct line offsets including the lines BEFORE `<style>`; non-CSS / non-HTML suffixes ignored.
  - End-to-end `main()`: clean tree → exit 0; violation → exit 1 with file:line on stdout; missing root → exit 0.
  - CI pin: `test_live_ui_static_tree_is_clean` runs the lint against `src/karasu/ui/static` and asserts rc=0. Trips automatically when a future UI-N PR introduces a bare `outline: none`.
- 381/381 pass locally (366 prior + 15 new).

Decisions:
- Regex-based, not full CSS parser. The rule is local (a single block) and the scope is small (one stylesheet today, ~5 expected by UI-9). A real parser would be over-engineered for the surface; the regex with `[^{}]` for top-level block matching avoids most of the false-positive surface.
- The `--focus-ring` token is the SOLE accepted replacement signal. UI-0 brief explicitly names it as the canonical mechanism; an operator who wants a different replacement should justify it in the brief first, then update the lint. Avoids the lint becoming permissive over time.
- Missing roots are silent (exit 0), not warnings. CI invocations like `lint_ui_css.py src/karasu/ui/static custom/exploration` should not fail just because the optional second root does not exist on this branch.
- Lives in `scripts/` next to `ui_screenshots.py`, not in `src/karasu/`. It is dev tooling, not runtime code; shipping it inside the package would imply operators can `karasu lint`, which is not the design.
- CI integration via pytest, not a separate GitHub workflow. The repo already runs `pytest -q` on every PR; piggy-backing keeps the lint visible to the same review cadence.
- The script also supports `<style>` blocks in HTML so the current `src/karasu/ui/static/index.html` (inline-styled stub) is covered. Once UI-2 lifts styles into `tokens.css` / `base.css`, the `.html` branch becomes mostly dormant — but it stays as a defence against future inline-style regressions.

Impact:
- UI-2 onward starts from a CI-enforced focus-ring baseline.
- The Phase 3 audit's last UI-0 round-2 NICE-TO-HAVE closes.
- No runtime change. No bus mutation. No new dependency. Frozen contracts untouched.

Next step:
- Last item in the remote-friendly queue: UI-9 deferred (URL-encoded path-traversal test for `/assets/*` + config-aware `EVENT_LOG` constant).

---

## 2026-05-03 (queue close) — UI-9 deferred items shipped

What changed:
- Final entry in the remote-friendly queue: the two UI-9 audit-noted items land now (well before UI-9 itself) so neither becomes deadline pressure later.
- `src/karasu/ui/server.py`:
  - `EVENT_LOG` is still the module-level default but now mutable via `configure(event_log)`.
  - `run_ui_server(host, port, event_log: Path | None = None)` accepts the override; `event_log=None` keeps the pre-existing default for callers that don't supply a config.
  - `_read_events` reads `EVENT_LOG` at call time, so `configure` flips the path even mid-server (useful for tests, transparent to operators).
- `src/karasu/__main__.py`:
  - `cmd_ui` now loads `karasu.yaml` via `_load_config(args.config)` and passes `event_log=_bus_path(config)` through to `run_ui_server`. `karasu watch` and `karasu ui` now read the SAME log when `event_bus.path` is set.
- `tests/test_ui_server.py` (NEW) — 12 tests across two layers:
  - **Path-traversal coverage** (UI-9 audit-noted item):
    - Literal `..` traversal → 403.
    - Inner-segment `..` traversal (`foo/../bar/../..`) → 403.
    - Percent-encoded `%2E%2E` → 403/404 (literal filename, not decoded by `BaseHTTPRequestHandler`).
    - Percent-encoded `%2E%2E%2F` → 403/404.
    - Double-encoded `%252E%252E` → 403/404 (defence against a hypothetical future middleware that decodes once).
    - Real file outside `STATIC_DIR` (a peer of it) is unreachable via `/assets/../`. Pinned because a future refactor that sets `STATIC_DIR` off the import-time location could otherwise widen the reachable set silently.
    - Sanity: a real file under `static/` IS served; index.html responds with `<title>Karasu UI</title>`.
  - **Config-aware EVENT_LOG** (UI-9 audit-noted item):
    - `configure(path)` sets the global; calling it twice leaves the second value in place (idempotent).
    - End-to-end: write a synthetic event to the configured path → `/api/events` returns it through the projection.
    - Missing log → empty projection, not 500.
    - `run_ui_server(event_log=PATH)` calls `configure` (verified via patched `ThreadingHTTPServer`).
- 393/393 pass locally (381 prior + 12 new).

Decisions:
- `configure` mutates a module global rather than threading the path through every function. The handler is a stdlib `BaseHTTPRequestHandler` whose `__init__` signature is fixed; passing per-request state via a global is the documented stdlib pattern. The cost is "tests must save / restore"; the `ui_http` fixture handles that.
- Tests assert `status in (403, 404)` for the encoded-traversal cases. Both are SAFE — the test pins the boundary, not the specific code path. If a future refactor changes which branch fires, the test still asserts "no 200, no escape".
- `cmd_ui` loads the config eagerly; if `karasu.yaml` is absent, the existing fall-through in `_load_config` returns `{}` and `_bus_path({})` returns the default. The UI keeps working from a fresh checkout without a config file.
- Did NOT add a `--event-log` CLI flag. The bus path is a karasu-wide concern (every other CLI command reads `event_bus.path`); duplicating it on the UI command would diverge the contract. Operators set the path in `karasu.yaml` once.
- Did NOT introduce an HTTP-layer URL decoder. The current behaviour ("encoded chars stay literal") is itself the safe default; tests pin it so an accidental decode in a future refactor surfaces as a regression.

Impact:
- `karasu ui` is now usable against any operator's bus path, not just the dogfood default.
- Path-traversal boundary is now explicitly tested. The implementation already held; the test pins it against future refactors.
- All 5 chunks in the remote-friendly queue closed.
- No bus mutation, no schema change. Frozen contracts untouched.

Next step:
- Operator audits the multi-chunk PR offline (ChatGPT review out-of-band, per session preference).
- Local items (UI-2 design system + tokens page) still parked until the operator has a computer with browser. Controlled chunk-4c dogfood likewise.
