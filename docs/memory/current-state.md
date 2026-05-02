# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: COMPLETED (no-adapter pass validated, F1–F5 closed)
Phase 1C: COMPLETED (real Claude adapter loop validated, F6–F8 closed)
Phase 2: COMPLETED — chunks 1+2+3 merged (#30 #31 #32 #33). Audit accepted with one round of changes (PR #33 contract alignment + redaction).
Phase 3: COMPLETED + DOGFOOD-VALIDATED + AUDIT-ACCEPTED — chunks 3a + 3b + 3c merged (#34 #35 #36 #37). Live dogfood 2026-05-02 (issue #39) validated end-to-end: `/scar` → controller resubmit (94 ms) → pipeline applies scar → second dispatch with `priority=high` → response back to Telegram. Cap held at 3 under spam. Three operational findings filed: F9 (#40), F10 (#41), F11 (#42). Audit forward-look returned by ChatGPT and recorded in [`docs/memory/phase-3-dogfood-audit-2026-05-02.md`](phase-3-dogfood-audit-2026-05-02.md): 2 REQUERIDOS applied this PR (trust=2 docs warning + cap-local-per-origin issue), 1 NICE-TO-HAVE applied (sessions template), 2 NICE-TO-HAVE queued for Phase 3+ hardening (priority persist + startup warning).

## System status

- Core pipeline: watcher → classifier → router → adapter → reporter ✔
- JSONL bus + TailReader ✔
- CLI consumer: `karasu tail` ✔
- CLI analyzer: `karasu analyze` ✔
- Cross-platform ignore matching (forward-slash normalization) ✔
- Debounce per `(path, change_type)` with 250 ms default ✔
- Dispatcher suppresses `agent_response` when no adapter handles ✔
- Real `ClaudeCodeAdapter` end-to-end via `claude -p` ✔
- Cross-platform CLI shim resolution via `shutil.which` ✔
- `dispatch_on` per classifier rule + `code_change` excludes `deleted` by default ✔
- `DEFAULT_IGNORE` covers bus, logs and tmp files ✔
- Per-adapter `timeout_s` configurable from YAML ✔
- Telegram outbound sink (`karasu chat`) ✔
- Telegram read-only slash commands (`/status`, `/agents`, `/scars`) ✔
- Telegram inbound scar capture (`/correct`, `/scar`) ✔ — strict whitelist; pipeline does NOT consume in Phase 2
- `LoopController` (single-worker dispatch coordinator) ✔ — behaviour-preserving wrapper around the existing pipeline
- Controller bus subscription + reaction (`/correct`, `/scar` resubmit) ✔ — chunk 3b. Cap: 3 resubmits per originating `file_change`. Resubmits emit a fresh `file_change` with `controller_resubmit=True`.
- `TriggerSource` Protocol + watcher as registered source ✔ — chunk 3c. Controller manages source lifecycle in `start`/`stop`.
- `karasu hook <pre-commit|post-commit|post-merge>` ✔ — git-hook source as a one-shot CLI. Submits `file_change` events with `source="git_hook"` and `data.git_hook=<name>`.
- `karasu serve --host --port` ✔ (Phase 3+ chunk 4a) — GitHub webhook receiver. HMAC-verified, body-size-capped (1 MiB), dedup ring (1024 deliveries), maps `pull_request_review_comment.created` → `file_change` with `source="github_webhook"` + `github_*` metadata. Per-source-IP rate limit (60/min default, 429 over). Fails CLOSED on missing/short secret (F-WH-9). Implements `TriggerSource`.
- A2A Agent Card endpoint ✔ (Phase 3+ chunk 4b) — `karasu serve` also serves `GET /.well-known/agent-card.json` with the static `AgentCard` JSON describing 4 baseline skills (watch-filesystem, route-events, receive-github-webhooks, record-corrections). Discovery only; capability negotiation deferred. POST on the card path → 405 (F-A2A-5 boundary held).
- Review-comment auto-handoff: DEFERRED (chunk 4c — pre-reqs: issue #47 outline + NICE-TO-HAVE #3 startup warning)
- Pipeline still does NOT consume `human_decision` directly — only the controller reads them and resubmits a `file_change` so `Pipeline._apply_scar_override` picks up the chat-recorded scar on the next dispatch

## Verified behavior (Phase 1C closed)

- Adapter invocation works non-interactive on every OS (Linux, macOS, Windows `.CMD` shim)
- Empty / malformed `command` config fails fast at startup
- `-p` / `--print` is appended exactly once even when the operator already supplied it
- Atomic-write deletions (the transient `deleted` event from a write-then-rename save) no longer reach the adapter for `code_change`
- The bus and operator-side log captures stay off the watcher's stream by default
- Long-running adapter calls can be raised past the 120 s constructor default by setting `agents.<name>.timeout_s`

## Phase 1C dogfood metrics (issue #25)

| Step | Time |
|------|------|
| `file_change` written | 20:21:10.851 |
| `agent_response` written | 20:21:49.335 |
| End-to-end | ~38.5 s |

`karasu analyze` final pass: duplication factor 1.0×, max events/sec 1, watcher exit clean. Output of `claude -p` was substantive — auto-discovery let it read `sample.py`, `karasu.yaml` and `events.jsonl` and reason about the dispatch payload.

## Findings F1–F11

| | Phase | Status | PR |
|---|---|---|---|
| F1 cascade               | 1B | resolved (collateral)     | #15 |
| F2 Windows ignore        | 1B | resolved                  | #15 |
| F3 1:1 no-route response | 1B | resolved (option B)       | #22 |
| F4 no debounce           | 1B | resolved                  | #18 |
| F5 watcher exit code 2   | 1B | not reproduced post-fix   | (collateral #15) |
| F6 self-noise on bus     | 1C | resolved                  | #27 |
| F7 dispatch on delete    | 1C | resolved                  | #26 |
| F8 timeout not configurable | 1C | resolved               | #28 |
| F9 missing [job-queue] extra | 3 dogfood | filed              | #40 |
| F10 drain skip warnings  | 3 dogfood | filed                  | #41 |
| F11 Notepad atomic-write tmp | 3 dogfood | filed              | #42 |

## Current risks

- Cost / latency under continuous editing not measured (single-edit dogfood only)
- No upper bound on adapter concurrency yet (Phase 1 keeps dispatch synchronous)
- Telegram / UI design not started

## Phase 3 dogfood metrics (issue #39)

| Step | Time |
|------|------|
| `/scar` sent → controller resubmit | 94 ms |
| Resubmit → second `agent_response` | ~28-30 s (puro `claude -p`) |
| End-to-end `/scar` → corrected response in Telegram | ~29 s |

Cap enforcement: 6 `/scar` rapid-fire → exactly 3 resubmits, 3 cap warnings, 0 leaks. Single-worker invariant preserved. Bus shows `controller_resubmit=true` + `resubmit_origin` traceability. Claude verbalized "the scar rule fired correctly — that's why this arrives at high" — direct confirmation that `_apply_scar_override` rewrote priority on the resubmit.

## Next step (entry point)

```text
Phase 3+ chunk 4c — review-comment auto-handoff.
HARD pre-reqs (BOTH must land before this chunk opens):
  1. Issue #47 (cap-local-per-origin) outline plan.
  2. NICE-TO-HAVE #3 — startup warning when adapter
     trust_level >= 2 (implementation, not just docs).
6 failure modes filed (F-HANDOFF-1..6) including prompt
injection, trust=2 amplification, prompt bloat. See
docs/phase-3-plus-pre-mortem.md § 4c and
docs/memory/next-session.md.

Optional follow-ups for chunk 4b (NICE-TO-HAVE, not blocking 4c):
- fetch_card helper + karasu peers <url> CLI for outbound discovery.

Queued hardening tasks (NICE-TO-HAVE from Phase 3 audit):
- Persist effective priority on agent_response.data.
```

## Do NOT do yet

```text
- Do not parallelize or batch adapter calls. Single-worker
  invariant is preserved; reaction in chunk 3b is also
  serialized through the same controller.
- Do not abstract the adapter behind a plugin layer.
- Do not let the pipeline consume `human_decision` events
  directly. The controller observes the bus and re-submits
  file_change events; `human_decision` itself is never the
  pipeline input.
- Do not touch AgentResponse, F3 dispatcher semantics, F7
  dispatch_on, F8 timeout_s — all four remain frozen.
```
