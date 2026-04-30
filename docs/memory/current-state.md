# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: COMPLETED (no-adapter pass validated, F1–F5 closed)
Phase 1C: COMPLETED (real Claude adapter loop validated, F6–F8 closed)
Phase 2: COMPLETED — chunks 1+2+3 merged (#30 #31 #32 #33). Audit accepted with one round of changes (PR #33 contract alignment + redaction).
Phase 3: IN PROGRESS — design doc merged (#34); chunk 3a (LoopController wrapper) shipped. Behaviour-preserving refactor: watcher now delegates queue + worker to `LoopController`. Chunks 3b (react to `human_decision`) and 3c (multi-source plug-in) pending.

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
- GitHub webhook receiver / A2A Agent Cards / review-comment auto-handoff: DEFERRED to Phase 3+ archive (issue #5)
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

## Findings F1–F8 — all resolved

| | Status | PR |
|---|---|---|
| F1 cascade               | resolved (collateral)     | #15 |
| F2 Windows ignore        | resolved                  | #15 |
| F3 1:1 no-route response | resolved (option B)       | #22 |
| F4 no debounce           | resolved                  | #18 |
| F5 watcher exit code 2   | not reproduced post-fix   | (collateral #15) |
| F6 self-noise on bus     | resolved                  | #27 |
| F7 dispatch on delete    | resolved                  | #26 |
| F8 timeout not configurable | resolved               | #28 |

## Current risks

- Cost / latency under continuous editing not measured (single-edit dogfood only)
- No upper bound on adapter concurrency yet (Phase 1 keeps dispatch synchronous)
- Telegram / UI design not started

## Next step (entry point)

```text
Phase 3 chunks 3a + 3b + 3c are pushed and stacked on
feat/loop-controller-{wrapper,react,sources}. Audit gate per the
Phase 2 cadence: maintainer hands the stack to ChatGPT for review
before any new phase opens. See docs/memory/next-session.md.
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
