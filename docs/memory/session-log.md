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
