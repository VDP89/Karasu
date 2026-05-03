# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: COMPLETED (no-adapter pass validated, F1–F5 closed)
Phase 1C: COMPLETED (real Claude adapter loop validated, F6–F8 closed)
Phase 2: COMPLETED — chunks 1+2+3 merged (#30 #31 #32 #33). Audit accepted with one round of changes (PR #33 contract alignment + redaction).
Phase 3: COMPLETED + DOGFOOD-VALIDATED + AUDIT-ACCEPTED — chunks 3a + 3b + 3c merged (#34 #35 #36 #37). Live dogfood 2026-05-02 (issue #39) validated end-to-end: `/scar` → controller resubmit (94 ms) → pipeline applies scar → second dispatch with `priority=high` → response back to Telegram. Cap held at 3 under spam. Three operational findings filed: F9 (#40), F10 (#41), F11 (#42). Audit forward-look returned by ChatGPT and recorded in [`docs/memory/phase-3-dogfood-audit-2026-05-02.md`](phase-3-dogfood-audit-2026-05-02.md): 2 REQUERIDOS applied this PR (trust=2 docs warning + cap-local-per-origin issue), 1 NICE-TO-HAVE applied (sessions template), 2 NICE-TO-HAVE queued for Phase 3+ hardening (priority persist + startup warning).
UI surface progress (PWA roadmap):
- UI-0 (design brief)         ✔ PR #62 merged (`92e2c91`).
- UI-1 (rebase + projection)  ✔ PR #63 merged (`4819d7b`).
- UI-2 (design system + tokens) ✔ PR #69 merged (`6ec5203`). One audit round (P0 on `prefers-reduced-motion`); fix in `ae975f3` switched to `transition-property` chromatic whitelist.
- UI-3 (application shell)    ✔ PR #70 merged (`a67d729`). APPROVED on the first round, no P0/P1/P2. ChatGPT pinned a binding rule for UI-5: ship `.webm` without exception because the crow becomes the principal visual asset there.
- UI-4..UI-9 pending per UI-0 §6 roadmap.

## System status

- Core pipeline: watcher → classifier → router → adapter → reporter ✔
- JSONL bus + TailReader ✔
- CLI consumer: `karasu tail` ✔
- CLI analyzer: `karasu analyze` ✔
- Cross-platform ignore matching (forward-slash normalization) ✔
- Debounce per `(path, change_type)` with 250 ms default ✔
- Dispatcher suppresses `agent_response` when no adapter handles ✔
- Dispatcher persists effective priority on `agent_response.data` ✔ — additive schema bump (Phase 3 audit follow-up). The post-scar-override priority that actually reached the adapter is recorded so `analyze` can audit dispatch priority post-hoc without cross-referencing the originating `file_change`. Public accessor: `karasu.eventbus.effective_priority(event)` — returns the priority string or `None` when the field is absent (pre-PR #60 events). Tooling that audits the bus reads through this helper instead of duplicating the None-vs-default decision per call site. See `docs/event-schema.md` "Priority semantics".
- Real `ClaudeCodeAdapter` end-to-end via `claude -p` ✔
- Cross-platform CLI shim resolution via `shutil.which` ✔
- `dispatch_on` per classifier rule + `code_change` excludes `deleted` by default ✔
- `DEFAULT_IGNORE` covers bus, logs and tmp files ✔
- Per-adapter `timeout_s` configurable from YAML ✔
- Telegram outbound sink (`karasu chat`) ✔
- Telegram read-only slash commands (`/status`, `/agents`, `/scars`) ✔
- Telegram inbound scar capture (`/correct`, `/scar`) ✔ — strict whitelist; pipeline does NOT consume in Phase 2
- `LoopController` (single-worker dispatch coordinator) ✔ — behaviour-preserving wrapper around the existing pipeline
- Controller bus subscription + reaction (`/correct`, `/scar` resubmit) ✔ — chunk 3b. Cap: chain cap with origin-aware tracking (issue #47 — `CHAIN_CAP=3`, `MAX_CHAIN_WALK_DEPTH=64`, `CHAIN_COUNTS_MAX_SIZE=1024`). `_chain_root` walks `resubmit_origin` transitively with F-CAP-1 (missing parent → treat current as root), F-CAP-2 (only follow lineage on `source="controller"` events), F-CAP-5 (visited_set + ceiling) defences. Resubmits emit a fresh `file_change` with `controller_resubmit=True` and persist `controller_chain_depth` on `data` so analyze can audit chain depth across restarts. Live `_chain_counts` is in-memory and per-process (does NOT recover after restart by design).
- `TriggerSource` Protocol + watcher as registered source ✔ — chunk 3c. Controller manages source lifecycle in `start`/`stop`.
- `karasu hook <pre-commit|post-commit|post-merge>` ✔ — git-hook source as a one-shot CLI. Submits `file_change` events with `source="git_hook"` and `data.git_hook=<name>`.
- `karasu serve --host --port` ✔ (Phase 3+ chunk 4a) — GitHub webhook receiver. HMAC-verified, body-size-capped (1 MiB), dedup ring (1024 deliveries), maps `pull_request_review_comment.created` → `file_change` with `source="github_webhook"` + `github_*` metadata. Per-source-IP rate limit (60/min default, 429 over). Fails CLOSED on missing/short secret (F-WH-9). Implements `TriggerSource`.
- A2A Agent Card endpoint ✔ (Phase 3+ chunk 4b) — `karasu serve` also serves `GET /.well-known/agent-card.json` with the static `AgentCard` JSON describing 4 baseline skills (watch-filesystem, route-events, receive-github-webhooks, record-corrections). Discovery only; capability negotiation deferred. POST on the card path → 405 (F-A2A-5 boundary held).
- A2A outbound discovery ✔ (chunk 4b follow-up) — `fetch_card(base_url, *, timeout=5.0, retries=0)` does a stdlib-only HTTP GET against a peer's `/.well-known/agent-card.json` and returns the parsed JSON dict. `karasu peers <url>` is the CLI wrapper: read-only, prints either formatted text (default) or raw JSON (`--json`). Configurable timeout (`--timeout`) and retries (`--retries`). All errors (network failure, non-2xx, bad JSON, non-object payload, zero/negative timeout, negative retries) surface as `AgentCardFetchError` / `ValueError` so the caller has a small exception surface. Retry policy (PR #58 follow-up): only `URLError` (transient network failure) triggers a retry; `HTTPError` (server answered with a non-2xx) and JSON / shape errors are NOT retried — those are the peer's real answer, not a network glitch. Backoff is exponential (0.5 s → 1.0 s → 2.0 s → cap at 4.0 s).
- Trust-gradient startup warning ✔ (NICE-TO-HAVE #3, hard pre-req for chunk 4c) — `AgentAdapter.__init__` emits a structured `logging.WARNING` on `karasu.adapters.base` whenever `trust_level >= AUTONOMOUS_TRUST_LEVEL` (=2). `cmd_watch` / `cmd_serve` additionally print a loud stderr banner once at startup listing every autonomous adapter by `name(trust=N)`. Both layers reference `docs/local-dogfood.md` "Trust gradient — what trust_level actually does in production".
- Review-comment auto-handoff ✔ (Phase 3+ chunk 4c) — `Dispatcher` copies `event.data` into `AgentRequest.metadata` as a shallow copy; `PromptBuilder` (`src/karasu/adapters/prompt_builder.py`) detects the github branch by presence of `metadata["github_body"]` and produces a USER-DATA-labelled, capped (4 KiB body / 256 B author), fenced prompt. Fence length is dynamic: one longer than the longest backtick run in the body, so a reviewer's own ` ``` ` blocks survive as content rather than closing the fence prematurely (F-HANDOFF-1 hardening). Truncation marker quotes both bytes and chars. When the comment's path is absent from the workspace (force-pushed away, branch deleted, etc.), the builder falls back to a metadata-only variant whose header is suffixed `(metadata-only)`, includes a `Do NOT attempt edits` note, and still fences the body as USER DATA (F-HANDOFF-6). The path probe is injectable (`path_exists` callable) so tests / git-tree-aware deployments can swap it. `ClaudeCodeAdapter` accepts an optional `prompt_builder` kwarg and delegates prompt construction. F-HANDOFF-1, F-HANDOFF-3, F-HANDOFF-5, F-HANDOFF-6 all addressed.
- Pipeline still does NOT consume `human_decision` directly — only the controller reads them and resubmits a `file_change` so `Pipeline._apply_scar_override` picks up the chat-recorded scar on the next dispatch
- UI design system primitives ✔ (UI-2) — `static/css/{tokens,reset,base}.css` + 6 self-hosted woff2 (Inter Display 4.x + JetBrains Mono v2.304, both SIL OFL 1.1, ~616 KB). `prefers-reduced-motion` clamp uses a `transition-property` chromatic whitelist so color and box-shadow keep their original durations while transform/opacity/filter/size become instant.
- UI design-system documentation page ✔ (UI-2) — `GET /design-system` serves a live render of every token (palette swatches with contrast labels, type scale, spacing, radius, shadow, focus ring, z-index, motion). Unlinked from the operator surface; doubles as the visual regression baseline for UI-3..UI-9.
- UI application shell ✔ (UI-3) — three-row sticky-grid layout (header + main + footer). Header: vector crow glyph (placeholder; UI-5 swaps with the canonical 32x32 sprite) + agent name + bus path right-aligned with ellipsis. Crow glyph recolours via class swap on `/api/health` state (`--fg-1` / `--accent` / `--warn`). Main: empty state (96px hero crow breathing 1px translateY 4s ease-mag, single editorial sentence) when zero events; canvas-stub placeholder when events exist. Footer: version + last event time + crow state. `[hidden] { display: none !important; }` global safety net keeps `el.hidden = true` from being outranked by class-level `display:` rules.
- `GET /api/meta` ✔ (UI-3) — `{version, bus_path}` for the surface to render its own version line and bus-path badge. `version` via `importlib.metadata` (stdlib, no new runtime dep) with `"unknown"` fallback. Additive: `/api/events` and `/api/health` shapes unchanged.
- `scripts/ui_fetch_fonts.sh` ✔ — idempotent, woff2 magic-byte verified.
- `scripts/ui_screenshots.py` ✔ — per-slug capture plan; per-capture `seed` (populate/truncate the bus) and `viewport` (override 1440x900) knobs; fresh Playwright context per capture so viewport overrides don't leak; bus seeded via `ui_server.configure(...)` instead of `os.chdir` (Windows tempdir cleanup race fixed).

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
README Fase 1 + Fase 2: COMPLETE.
README Fase 3 (PWA + Advanced): IN PROGRESS.

UI surface progress:
  UI-0 (design brief)         ✔ PR #62 merged (92e2c91).
  UI-1 (rebase + projection)  ✔ PR #63 merged (4819d7b).
  UI-2 (design system + tokens) ✔ PR #69 merged (6ec5203).
  UI-3 (application shell)    ✔ PR #70 merged (a67d729).
  UI-4 (event timeline as editorial beats)   <-- next.
  UI-5 (crow sprite + state animations)      pending per
                                              UI-0 brief.
                                              .webm
                                              required, no
                                              exception
                                              (ChatGPT
                                              UI-3 review
                                              pin).
  UI-6..UI-9                  pending per UI-0 brief
                                              roadmap.
  UI-10+ (write paths, push, trust mgmt) out of brief
                                       scope until UI-MVP
                                       lands.

The UI MVP is read-only against the bus. karasu ui
[--host H] [--port P] (defaults 127.0.0.1:8787) starts a
ThreadingHTTPServer that serves the static shell + the
JSON projection at /api/events and /api/health (and the
new /api/meta from UI-3). The projection is the canonical
contract; UI-4..UI-9 render against it.

See docs/memory/next-session.md for UI-4's detailed plan
and the editorial guidance ChatGPT pinned in the UI-3
audit ("timestamp mono pequeño, tipo de evento como acento
tipográfico, path/agente como metadata secundaria, hover/
focus muy contenido — el mayor riesgo de UI-4 será llenar
demasiado rápido el vacío que UI-3 acaba de ganar").

Remaining items beyond the UI MVP:

- Dogfood controlado de chunk 4c con un PR real a
  trust_level=1 — operativo, no código (requiere
  computadora). NOT blocking UI.
- Future: optional dual priority_original /
  priority_effective fields on agent_response.data if
  analytics surface a need (audit-noted on PR #60). The
  effective_priority(event) helper itself shipped (PR
  #65); the dual fields stay deferred until a consumer
  needs them.
- Future: opt-in retry on transient HTTP statuses
  (502/503/504) in fetch_card — issue #66, P2. Adds an
  optional `retry_http_statuses` parameter; default empty
  set preserves the current "do not retry on HTTP errors"
  semantics. Not blocking; pick up when revisited.

Operator-side TODOs no Claude Code session can perform
from this MCP surface:
  - Rename repo: GitHub → Settings → General →
    Repository name → `Karasu` (current name `Karasu-`
    is a typo).
  - Uninstall the ChatGPT Codex Connector GitHub App
    from the repo: GitHub → Settings → Integrations →
    Applications → ChatGPT Codex Connector →
    Uninstall. PR #67 (squash → cab7d92) already
    retired the Codex bot from working agreements;
    the App uninstall closes the loop physically.
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
