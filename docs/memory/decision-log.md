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

