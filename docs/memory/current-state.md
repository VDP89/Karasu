# Current State — Karasu

## Phase

Phase 1A: COMPLETED
Phase 1B: COMPLETED (no-adapter pass validated, F1–F5 closed)
Phase 1C: COMPLETED (real Claude adapter loop validated, F6–F8 closed)
Phase 2: COMPLETED — chunks 1+2+3 merged (#30 #31 #32 #33). Audit accepted with one round of changes (PR #33 contract alignment + redaction).
Phase 3: COMPLETED + DOGFOOD-VALIDATED + AUDIT-ACCEPTED — chunks 3a + 3b + 3c merged (#34 #35 #36 #37). Live dogfood 2026-05-02 (issue #39) validated end-to-end: `/scar` → controller resubmit (94 ms) → pipeline applies scar → second dispatch with `priority=high` → response back to Telegram. Cap held at 3 under spam. Three operational findings filed: F9 (#40), F10 (#41), F11 (#42). Audit forward-look returned by ChatGPT and recorded in [`docs/memory/phase-3-dogfood-audit-2026-05-02.md`](phase-3-dogfood-audit-2026-05-02.md): 2 REQUERIDOS applied this PR (trust=2 docs warning + cap-local-per-origin issue), 1 NICE-TO-HAVE applied (sessions template), 2 NICE-TO-HAVE queued for Phase 3+ hardening (priority persist + startup warning).
UI surface progress (PWA roadmap — main HEAD `e535c95`, 2026-05-05):
- UI-0  (design brief)              ✔ PR #62  merged (`92e2c91`).
- UI-1  (rebase + projection)       ✔ PR #63  merged (`4819d7b`).
- UI-2  (design system + tokens)    ✔ PR #69  merged (`6ec5203`).
- UI-3  (application shell)         ✔ PR #70  merged (`a67d729`).
- UI-4  (event timeline)            ✔ PR #72  merged (`13e6270`).
- UI-5  (canonical crow + anims)    ✔ PR #74  merged (`904111a`).
- UI-6  (Live Map + crow flight)    ✔ PR #78  merged (2026-05-05).
- UI-7  (Detail panel / drawer)     ✔ PR #79  merged (2026-05-05).
- UI-8  (PWA shell + offline)       ✔ PR #80  merged (2026-05-05).
- UI-9  (server tests + Lighthouse) ✔ PR #81  merged (2026-05-05).
- UI-9.1 (server perf)              ✔ PR #82  merged (2026-05-05).
- UI-10 brief (write paths brief)   ✔ PR #83  merged (2026-05-05, doc-only).
- Lighthouse baseline post-MVP      ✔ PR #84  merged (`aa7d45e`).
- UI-10 (scar revoke impl)          ✔ PR #85  merged (`b89047c`).
- Lighthouse baseline post-UI-10    ✔ PR #86  merged (`9ed761c`).
- UI-11 brief (trust adjust)        ✔ PR #87  merged (`37b51ba`, doc-only).
- UI-11a (trust read display)       ✔ PR #89  merged (`e535c95`).
- UI-11b (trust write affordance)   ✔ PR #91  merged (`007574d`).
- UI-12  (push notifications)       ← NEXT. Earns own brief before code.

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
- `GET /api/agents` ✔ (UI-11a) — read-only trust display source. Reads `karasu.yaml` directly via the configured `CONFIG_PATH` so it works with no `karasu watch` process running. Returns configured adapters with `name`, `trust_level`, `handles`, plus `unsupported: true` for trust values outside `{0,1,2}` or malformed values such as `"high"`. Does not instantiate adapters and does not reach into live adapter instances.
- `/api/events` projection includes `data.action` ✔ (UI-11a) — additive field with HTTP shape lock in the same PR so UI-11b can distinguish `scar_revoke` / `trust_adjust` human_decision events without scraping raw drawer JSON.
- `scripts/ui_fetch_fonts.sh` ✔ — idempotent, woff2 magic-byte verified.
- `scripts/ui_screenshots.py` ✔ — per-slug capture plan; per-capture `seed` (populate/truncate the bus) and `viewport` (override 1440x900) knobs; per-capture `press_tab` step (real keyboard-driven focus, not synthetic `.focus()`); `_apply_step` runs `wait_ms` first so JS-rendered targets exist before hover / press_tab fire; fresh Playwright context per capture so viewport overrides don't leak; bus seeded via `ui_server.configure(...)` instead of `os.chdir` (Windows tempdir cleanup race fixed).
- UI event timeline ✔ (UI-4) — `static/css/timeline.css` (first feature CSS split). `.timeline` is a `<ol>` with max-width 720 px, centred. Each row is a single typographic line: `<time>` mono `--fs-12 --fg-2`, type display `--fs-16 --fg-1` (the only accent), meta mono `--fs-14 --fg-2`. Hairline `--fg-3` between rows; `--bg-2` hover wash; design-system `--focus-ring` on Tab via `.event-row[tabindex=0]`. Latest-on-top via reversed copy; full re-render every 3 s tick. Narrow viewport (≤720 px) collapses to a single column. Empty-state branch from UI-3 is unchanged.
- UI canonical crow asset ✔ (UI-5) — `src/karasu/ui/static/assets/crow/crow.svg` adapted from OpenMoji "Black Bird" (1F426 200D 2B1B), CC-BY-SA 4.0. Two body fill paths unified under `currentColor`, plus operator-added 2× `<rect>` legs (currentColor) and 1× `<circle>` eye notch (`var(--bg-0)`, acts as negative space against the body recolour). viewBox 72×72, no `shape-rendering="crispEdges"` — vector smooth at all sizes. Renders cleanly at 24 px header glyph and 96 px hero (4× viewBox grain). Provenance + iteration history (FA vector → 2× pixel-art → 2× hand-drawn vector → OpenMoji-adapted) in `docs/ui/assets/karasu_sprites_spec.md`.
- UI crow state animations ✔ (UI-5) — `src/karasu/ui/static/css/crow.css` defines `.crow` base (currentColor + ambient breathing 4 s loop, translateY 1 px ease-mag) plus four state classes: `.crow.processing` (--accent + slow pulse, scale 1.04 over 1.6 s, infinite); `.crow.waiting` (--warn + 4° asymmetric tilt, forwards-fill — leans and holds); `.crow.error` (--accent + sharp shake, ±2 px translateX over 240 ms, single beat — looping reads as alarm fatigue). Reduced-motion: keyframes clamp to 1 ms via `reset.css` chromatic whitelist; only colour transitions remain. Motion lives ONLY on `.crow` per UI-4 audit pin "el crow puede tener vida; la superficie no puede perder calma".
- `_crow_state` precedence (UI-5 audit fix) ✔ — `src/karasu/ui/server.py::_crow_state` walks events reverse-chronologically and returns at the first match: error (most-recent failed) > waiting (most-recent requires_human=True) > processing (LATEST event is file_change) > idle. The earlier implementation set state="processing" on any tail file_change and continued, which mis-resolved a completed-agent_response tail to processing. Codex P0 on re-audit caught the bug; fix re-checks the LATEST event explicitly. Pinned by 7 unit tests in `tests/test_ui_server.py` (empty events, latest file_change, completed-after-file_change, failed anywhere, requires_human anywhere, most-recent-trigger-wins error/waiting, new file_change after completed).
- `_flight_route` projection ✔ (UI-6) — `src/karasu/ui/server.py::_flight_route` consults the LATEST event only and returns `(source, target)` ∈ `{user, karasu, claude, codex, github}` or `None` (parked). Mapping table: `file_change` watcher / git_hook → user → karasu; `file_change` with `controller_resubmit=true` → user → karasu (operator scar); `file_change` with `github_event` / `source=github_webhook` → github → karasu; `file_change` with router-assigned dispatch (`agent` set + `status` ∈ {pending, dispatched}) → karasu → claude/codex; `agent_response` (completed OR failed) → claude/codex → karasu; `human_decision` → user → karasu; `git_event` → user → karasu; unknown / unmapped → None. Stricter than `_crow_state` (no reverse walk) by design — operator's binding "no invented recovery flight" rule. Surfaced additively as `/api/health.flight = {source, target} | null`. Pinned by 22 unit tests + 2 HTTP-level tests in `tests/test_ui_server.py`.
- `scripts/ui_screenshots.py` extended (UI-5) — per-state `STATE_CORPORA` so each PNG seeds the precedence-winning event for `_crow_state`; `--record-video` flag walks idle → processing → waiting → error → idle inside one Playwright context (1024×640 viewport, ~5 s total, ~112 KB output, no ffmpeg transcode needed); cross-drive `shutil.move` for Windows temp-dir → repo-dir handoff; `eval_js` step for the deliberate frozen-frame error PNG (`translateX(-2px)` pinned because the 240 ms one-shot beat is non-deterministic to capture mid-animation; motion truth lives in the `.webm`).
- `scripts/ui_screenshots.py` extended (UI-6) — `FLIGHT_CORPORA` registry (six entries: flight-user-karasu, flight-karasu-claude, flight-claude-karasu, flight-github-karasu, flight-controller-resubmit, flight-parked) so each PNG seeds the latest-event tail that lands a specific `_flight_route` pair; `_resolve_seed_events` walks both STATE_CORPORA and FLIGHT_CORPORA so UI-5 and UI-6 plans coexist; `--record-video` for UI-6 walks the dispatch chain (file_change → karasu→claude → claude→karasu → github→karasu → controller-resubmit → parked) inside ONE Playwright context (1024×640 full-shell, ~6 s total, ~242 KB output).

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
- Telegram remains temporary until the PWA notification path lands

## Phase 3 dogfood metrics (issue #39)

| Step | Time |
|------|------|
| `/scar` sent → controller resubmit | 94 ms |
| Resubmit → second `agent_response` | ~28-30 s (puro `claude -p`) |
| End-to-end `/scar` → corrected response in Telegram | ~29 s |

Cap enforcement: 6 `/scar` rapid-fire → exactly 3 resubmits, 3 cap warnings, 0 leaks. Single-worker invariant preserved. Bus shows `controller_resubmit=true` + `resubmit_origin` traceability. Claude verbalized "the scar rule fired correctly — that's why this arrives at high" — direct confirmation that `_apply_scar_override` rewrote priority on the resubmit.

## Next step (entry point)

```text
main HEAD: 007574d (UI-11b trust adjust intent, 2026-05-05).
0 PRs open. 0 branches open.

UI-10 + UI-11 COMPLETE. Both write paths are on main:
  - UI-10: scar revoke (POST /api/scars/{id}/revoke)
  - UI-11a: trust read display (GET /api/agents + data.action projection)
  - UI-11b: trust adjust intent (POST /api/agents/{name}/trust,
    intent-only, persists to karasu.yaml, emits bus event)

Entry point: UI-12 — push notifications.
Requires own brief before code (UI-9 audit pin #1 + UI-0 §6).
Push UX has its own opt-in / unsubscribe / privacy surface.

Remaining items (non-blocking):
- Issue #66: fetch_card opt-in retry on 502/503/504 (P2).
- Issue #76: THIRD_PARTY_NOTICES.md for OpenMoji (P2).
- Operator-side: rename repo Karasu- → Karasu (GitHub Settings).
- Operator-side: uninstall ChatGPT Codex Connector App if still
  installed (PR #67 retired the bot; physical uninstall closes loop).
```

## Do NOT do yet

```text
- Do NOT imply live adapter mutation in any UI-11 copy
  (pin §11.6.5 — INTENT-ONLY).
- Do NOT add /agents page, header toolbar, or global trust
  settings surface (pin §11.6.6).
- Do NOT add trust values above 2 to the modal (pin §11.6.4).
- Do NOT cache /api/* under any circumstances (SW network-only).
- Do NOT add install banners, update toasts, connection badges
  (UI-8 audit pin #5).
- Do NOT lower Lighthouse thresholds without operator-signed
  rationale (UI-9.1 procedural lock).
- Do NOT introduce a build step or bundler (UI-0 §4).
- Do not parallelize or batch adapter calls. Single-worker
  invariant is preserved.
- Do not abstract the adapter behind a plugin layer.
- Do not let the pipeline consume `human_decision` events
  directly. The controller resubmits as file_change.
- Do not touch AgentResponse, F3, F7, F8 — all frozen.
```
