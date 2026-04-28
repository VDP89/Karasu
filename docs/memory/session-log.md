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

## 2026-04-28 — Phase 1B closure (no-adapter pass)

What changed:
- PR #15: `fix(watch)` normalize event paths to forward-slash. Closed F2 (Windows ignore broken) and collaterally closed F1 (default config feedback cascade) — the cascade existed because the ignore matcher was a no-op on Windows; once paths are forward-slash, the default `.karasu/` ignore filters the bus file correctly.
- PR #18: `feat(watch)` debounce per `(path, change_type)` with 250 ms default. Closed F4. Editor save bursts (5 writes in 250 ms) collapse from ≥6 events to 2 (created + first modified) — distinct change_types preserved.
- PR #22: `fix(router)` suppress `agent_response` when no adapter handles. Closed F3 (option B from issue #17). Bus now represents real agent work; "seen but unhandled" is reconstructable from `file_change` presence + absence of correlated `agent_response`.

Issues closed:
- #14 — Phase 1B dogfood findings (F1–F5 all resolved).
- #17 — F3 design discussion (option B implemented).

Metrics across the three passes against the same dogfood workload:

| Pass             | total | file_change | agent_response | dup factor | peak ev/s |
|------------------|------:|------------:|---------------:|-----------:|----------:|
| Baseline         |  3022 |        1521 |           1501 |       253× |       203 |
| Post F2 + F4     |    65 |          31 |             34 |      2.82× |        19 |
| Post F3 (final)  |    11 |          11 |              0 |      2.75× |         2 |

99.6 % reduction from baseline.

Decisions:
- F3 = option B (suppress no-route response). Option A and C documented as discarded in `decision-log.md`.
- `--delete-branch` chain reaction observed and operational rule recorded: leaf PRs only, descendants close (not retarget) when their base is deleted.
- Surface authority model formalized at the chat layer (rule 1, 1b, 1c in operator's local memory): repo = source of truth; bot Codex = official reviewer; ChatGPT = advisor (off-repo); Claude Code = implementer; user = bus until Karasu replaces that role.

Impact:
- Phase 1B closed. Karasu is observable, measurable, debounced, semantically clean.
- Bus volume per real workload dropped by two orders of magnitude.

Next step:
- Phase 1C: wire a minimal real Claude adapter and validate the full loop. Scope and constraints in `next-session.md`.

---
