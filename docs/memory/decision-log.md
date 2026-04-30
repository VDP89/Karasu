# Decision Log

## Core principles

- Karasu is a broker, not an agent
- Human is not the message bus
- Observe first, design after

## Phase decisions

### Observability-first (NEW)

Decision:
- Build tail + analyze before any UI or automation

Reason:
- Prevent blind system design
- Quantify event noise before filtering

---

### Event integrity

Decision:
- Atomic consumption in tail reader
- Byte-based splitting (no splitlines)

Reason:
- Prevent silent data loss
- Ensure JSON correctness

---

### Analysis before control

Decision:
- Introduce `karasu analyze` before debounce/controller

Reason:
- Avoid premature optimization
- Base decisions on measured data

---

### F3 — agent_response semantics (issue #17)

Decision:
- The dispatcher emits `agent_response` ONLY when an adapter actually performs work.
- When no adapter handles the classification, dispatcher returns None and the bus carries no `agent_response`.

Reason:
- Bus represents real agent work, not pipeline mechanics.
- The previous 1:1 contract produced ~2× bus volume with zero information value (every no-route response said the same thing).
- "Seen but unhandled" is reconstructable from the originating `file_change` plus the absence of a correlated `agent_response`.
- Aligns with the principle "human is not the message bus" — the bus is a record, not a heartbeat.

Discarded:
- Option A (keep strict 1:1): doubles disk for no information.
- Option C (explicit no-op response): preserves contract but still doubles volume.
- Option B' with periodic summary: defer until trust gradient actually needs unhandled-event accounting.

---

### F7 — dispatch_on semantics (issue #25, PR #26)

Decision:
- `code_change` excludes `deleted` from dispatch by default.
- Per-rule `dispatch_on` overrides the default.
- Other classifications are NOT filtered at the pipeline; the dispatcher remains the single source of "no adapter handles this".

Reason:
- Atomic-write editors (VS Code, Claude Code Write tool, most "atomic save" implementations) emit a `deleted` event on the original path before the new content lands. Dispatching the adapter on that transient state sends it at a path that does not exist yet.
- Hardcoding "no dispatch on delete" globally would break legitimate workflows (security audit, scar/index cleanup, build-config deletion). Per-rule override preserves those.
- Other classifications without a documented default are NOT filtered — keeping the F3 contract that the dispatcher is the only place that decides "no adapter handles this".

Discarded:
- Global ban on dispatch-on-delete: would block valid security/cleanup flows.
- Hardcoding per classification: not extensible.
- Move the filter into the dispatcher: would conflate "no adapter for this classification" (F3) with "this change_type doesn't apply" (F7) — two distinct reasons that operators read differently.

---

### Phase 2 — surface = sink, not orchestrator (PR #30, #31)

Decision:
- Telegram is the Phase 2 primary surface. Outbound (drain → send) and inbound (slash commands, scar capture) both flow through `TelegramInterface`, which subscribes to the JSONL bus via `JsonlTailReader` and never calls into the dispatcher.
- The surface only WRITES `human_decision` events to the bus. It does NOT emit `file_change` or `agent_response`, and the pipeline does NOT consume `human_decision` in Phase 2.

Reason:
- Reuses the existing primitives (`JsonlTailReader`, `HumanReporter`, `Report`, `ScarEngine`) without inventing new ones.
- Keeps F3 / F7 contracts intact: dispatcher remains the only place that decides "no adapter handles this", and `dispatch_on` filtering remains in the pipeline.
- Inbound commands either render state (`/status`, `/agents`, `/scars`) or write a Scar via `ScarEngine.record` (`/correct`, `/scar`). Neither path feeds events back into the watcher loop in Phase 2.

Discarded:
- Web UI / PWA first: zero scaffolding, multi-week build, no incremental validation path.
- Both surfaces in parallel (Telegram + Web): doubles the contract burden in the first PR with no operator demand for the web side.
- Surface-as-orchestrator (LoopController in Phase 2): premature; the synchronous pipeline still works fine for single-edit workloads, and the controller can be designed once we have evidence that scars-from-chat is needed in the loop.

---

### Phase 2 — strict whitelist for write commands (PR #33)

Decision:
- `/correct` and `/scar` reject every call when `allowed_users` is empty, regardless of `user_id`.
- Reads (`/status`, `/agents`, `/scars`) keep their chunk-1 / 2 default (empty whitelist == allow anyone).

Reason:
- Writes mutate `ScarEngine` state. Without an explicit operator whitelist, a leaked bot token would let anyone install scars that change the dispatcher's behaviour.
- Reads are low-risk; refusing them by default would break the chunk-1 happy path of "set token + chat id, see Karasu state from your phone".
- Asymmetric defaults are honest: visibility cheap, mutation explicit.

Discarded:
- Single uniform default: too coarse — either reads break or writes leak.
- Separate YAML key (`require_whitelist_for_writes: true`): adds a knob with one sane setting; better to bake the decision in.
- Trust gradient extension: scope creep; the gradient is per-agent, not per-user.

---

### Phase 3 — TriggerSource Protocol + git-hook one-shot (chunk 3c)

Decision:
- Trigger sources are described by a `runtime_checkable` Protocol (`start`, `stop`). The watcher already had this shape; the protocol documents the seam without forcing inheritance.
- `LoopController` manages a list of registered sources via `add_source`. `start()` calls each source's `start()` AFTER the worker and bus subscription are up; `stop()` calls each source's `stop()` FIRST so producers stop emitting before the worker drains.
- `controller.run_forever()` is the production path for `karasu watch`. The watcher's own `run_forever` remains for standalone tests.
- Git hooks are NOT registered sources. `karasu hook <name>` is a one-shot CLI that builds events and calls `controller.submit` directly, then drains the queue and exits.
- `submit_for_hook(hook, bus, submit, runner)` writes events to the bus AND calls `submit`. Same pattern as the watcher: bus first, queue second.
- Source `start`/`stop` exceptions are logged at `karasu.controller.loop` and do NOT break the controller.

Reason:
- The Protocol approach keeps the seam minimal. Future sources (GitHub webhook receiver, A2A peer) only need `start` + `stop` and can be registered without inheriting from anything.
- One-shot vs long-running is a real distinction. Forcing git hooks into the registered-source model would make the controller manage subprocess state we don't need (the hook IS the subprocess).
- Source exceptions surfaced as warnings rather than crashes preserve the rest of the pipeline. A flaky source loses its events; the worker and other sources keep functioning.

Discarded:
- ABC instead of Protocol: forces inheritance, increases the refactor cost for the watcher and any external producer.
- Make git hooks long-running by polling git status: unnecessary; git fires the hook for us.
- Stop sources in reverse registration order: only matters with inter-source dependencies, which the protocol forbids.
- Make source exceptions fatal: a single bad source would take the whole controller down; not worth the simplicity.

---

### Phase 3 — controller reacts to human_decision via resubmit (chunk 3b)

Decision:
- The controller, not the pipeline, consumes `human_decision` events. It runs a daemon thread that polls the bus via `JsonlTailReader` and routes `/correct` / `/scar` texts to a resubmit handler.
- Reactions are CAPPED: at most `RESUBMIT_CAP = 3` resubmits per originating `file_change.id`. Past the cap, log a warning and skip — the surface already wrote the `human_decision` audit record on the bus, so the operator's correction is preserved even when the controller refuses to fire it again.
- Resubmits emit a fresh `file_change` with `source="controller"`, `data.controller_resubmit=True`, `data.resubmit_origin=<id>`. The pipeline treats it like any other `file_change` and re-runs classification + scar consultation; `_apply_scar_override` picks up the chat-recorded scar.
- The cap key is the originating `file_change.id` only, not `(id, scar_id)`. Simpler and bounds the worst case identically. Phase 3+ may extend the key shape once escalation events are introduced.

Reason:
- Closes the Lucy-Syndrome correction loop without coupling the pipeline to the surface. The pipeline still consumes only `file_change` events; the controller is the new layer that observes the bus for human signal and translates it to a fresh dispatch.
- Re-emitting a fresh `file_change` (rather than mutating the in-flight pipeline state, or re-running the original event by id) keeps the reaction path testable in isolation and visible on the bus for `analyze`.
- The cap is the stop rule the design doc required. Phase 1 had no retry; introducing one needs a bound, and a bound that is also auditable through the bus.
- Bus subscription skips redacted human_decision texts (containing `(unauthorized)` or `(unknown command)`). The surface already rejected those writes; reacting on them would let an attacker spam the controller via redacted markers.

Discarded:
- Make the pipeline consume `human_decision` directly: would entangle the dispatcher with surface input and force every classifier / dispatch_on filter to learn a new event type.
- Mutate the original `file_change` in place / submit by id without re-emitting: invisible on the bus; `analyze` cannot see how many resubmits actually fired.
- Cap by `(originating_id, scar_id)`: requires looking up the scar in `ScarEngine` from the controller; doubles the controller's read surface for no clear win at this stage.
- No cap (rely on operator hygiene): a misbehaving surface or a script-driven `/scar` could drive the dispatcher in an unbounded loop.

---

### Phase 3 — controller as wrapper, watcher delegates (chunk 3a)

Decision:
- Single-worker dispatch logic moves out of `FilesystemWatcher`
  into `LoopController`. The watcher constructs (or accepts) a
  controller and routes events via `controller.submit`.
- The watcher keeps `start_pipeline` / `stop_pipeline` as thin
  delegators and exposes `_queue` / `_worker` / `_stopping` as
  read-only properties that forward to the controller. Existing
  watcher tests pass unchanged.
- `cmd_watch` builds the controller explicitly so chunks 3b and
  3c can extend it without touching the watcher.

Reason:
- Refactor without behavioural change is the chunk-3a goal. The
  parity test in `tests/test_controller.py` enforces that the
  bus output is identical to the direct synchronous path.
- Centralising the worker in the controller frees chunk 3b to
  add a bus subscription + reaction logic without entangling
  the watcher.
- Backward-compat properties on the watcher are explicit refactor
  scaffolding. They can be removed in a later chunk if the test
  suite migrates to drive the controller directly.

Discarded:
- Replace the watcher API entirely (drop `start_pipeline` /
  `stop_pipeline`): would break every existing watcher test in
  one chunk. Rejected for review burden.
- Make the controller optional and fall back to the old inline
  behaviour: doubles the code paths and undermines the chunk-3b
  reaction loop, which assumes the controller is always present.
- Async event loop instead of threads: would force a second
  runtime alongside the Telegram surface. Threads stay.

---

### Phase 2 — redact args in human_decision for unauthorized writes (PR #33, audit fix)

Decision:
- Authorized write commands record the full `/<name> <args>` in the
  `human_decision` event.
- Unauthorized write commands and unknown commands record only the
  command name + outcome label: `"/<name> (unauthorized)"` or
  `"/<name> (unknown command)"`. The raw args are dropped.

Reason:
- The audit (ChatGPT, 2026-04-29) flagged that storing the full
  message text on every attempt is a privacy hazard: a leaked bot
  token lets attackers spam arbitrary content through `/correct`
  / `/scar`, all of which would be persisted verbatim to the bus.
- Operationally only the metadata (command name + outcome) is
  useful in the unauthorized case. The args content is worse than
  useless — it bloats the bus and may contain sensitive strings.
- Authorized callers still get full text so they can debug their
  own input.

Discarded:
- Skip the audit record entirely on unauthorized: loses the
  attempt count needed for any future rate limit / monitoring.
- Hash the args: adds complexity for no operational gain (we don't
  match on the hash).
- Redact for ALL writes including authorized: hurts the operator's
  ability to reconstruct what they typed.

---

### Phase 2 — trigger derivation re-classifies on capture (PR #33)

Decision:
- `/correct` and `/scar` re-derive the Scar trigger by running the configured `RuleClassifier` against the agent_response's path.
- Classification is NOT persisted on the on-disk `file_change`; the watcher writes file_change before the classifier runs, and the classifier only mutates the in-memory copy.

Reason:
- The same `RuleClassifier` instance produces both the original dispatch and the trigger derivation, so the result is identical to what the dispatcher saw.
- Avoids a schema change to `file_change` (would require migration of existing JSONL logs).
- Avoids storing classification on `agent_response` either, which would couple the dispatcher to the surface.

Discarded:
- Persist classification on `file_change` at watch time: the classifier runs after the watcher, so this means re-ordering the pipeline write — outside the Phase 2 contract.
- Persist classification on `agent_response`: easier than the watcher change but still a contract mutation; not justified for one feature.
- Let operators specify `classification` in the correction map: error-prone (operator types it wrong, the trigger never fires).

---

### F8 — adapter timeout configurable per-agent (issue #25, PR #28)

Decision:
- `agents.<name>.timeout_s` reads from YAML and overrides the adapter's constructor default.
- Absent → keep the constructor default (120 s).
- `0`, negatives, and non-numeric values raise `ValueError` at startup with the YAML section name.

Reason:
- Phase 1C dogfood saw ~38 s for an auto-discovery dispatch. Real refactors will exceed 120 s.
- Operators must raise (or lower) the timeout without editing source.
- A silent "timeout = 0 means no timeout" coercion would let a bad config hang the watcher indefinitely. Explicit fail-fast is safer in Phase 1.

Discarded:
- Global `defaults.adapter_timeout_s`: not needed yet; per-agent unblocks Phase 2 work and the operator can copy the same number into multiple agents until a default is required.
- Coerce `0` to "no timeout": opaque footgun.

