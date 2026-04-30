# Phase 3 — LoopController (design)

Design document for the next architectural layer. Design-only — no
code in this PR. Same shape as `docs/phase-2-surface.md`: pick the
contract, freeze the boundary, size the first code chunk.

## Goal

Karasu's pipeline today (`watcher → classifier → dispatcher →
adapter → reporter`) processes one event at a time, synchronously,
on a single worker thread. Phase 1 + Phase 2 work confirmed this
shape is enough for filesystem-driven dogfood. It is NOT enough
for:

- **Reacting to `human_decision` events** on the bus (Phase 2
  chunk 3 records them; the pipeline ignores them).
- **Multiple trigger sources** beyond the watcher (git hooks,
  GitHub webhooks, A2A peers — issue #5).
- **Retries / timeouts / scheduling** that an async Claude call
  fails or hangs.

The LoopController is the layer that owns those concerns.

This document fixes the controller contract before any code is
written.

## Scope choice — incremental, not big-bang

```text
Decision:
- Phase 3 ships in three chunks. Each is independently shippable
  and reviewable (≤400 LOC, including tests).

  chunk 3a — Controller as a wrapper (no behaviour change)
    - Introduces ``LoopController`` that wraps the existing
      Pipeline. The watcher hands events to the controller; the
      controller hands them to the pipeline.
    - Single trigger source (filesystem watcher). Single worker
      thread. Synchronous dispatch. No retries.
    - Goal: refactor without behavioural change. Tests must show
      the bus output is bit-for-bit identical to the current
      pipeline on a fixed event sequence.

  chunk 3b — React to human_decision
    - LoopController reads human_decision events on the bus and
      may RE-DISPATCH the originating file_change. The /correct
      and /scar handlers from Phase 2 produce a "rerun this
      classification" hint that the controller picks up.
    - Still single worker, single trigger source. The reaction
      is an additional input, not parallelism.

  chunk 3c — Trigger source plug-in interface
    - Generalises "watcher → controller" to "trigger source N →
      controller". Git hooks (issue #5) become the second source.
    - GitHub webhook receiver waits for chunk 3d unless an
      operator demand justifies it earlier.

- Phase 3+ archive (issue #5: A2A Agent Cards, review-comment
  auto-handoff, GitHub webhook receiver) plugs into chunk 3c's
  trigger interface and chunk 3b's reaction loop. Each becomes its
  own focused PR.

Reason:
- The Phase 2 cadence proved that small chunks audited individually
  beat one big architectural PR. Same model here.
- Chunk 3a is mechanical; chunk 3b is semantic; chunk 3c opens the
  surface. Splitting them keeps each audit focused.

Discarded:
- Big-bang (controller + reactions + multi-source in one PR):
  ~1500 LOC, impossible to review well, defeats the review-loop
  policy in CLAUDE.md.
- Skip 3a, jump to 3b: would mix architectural change with
  semantic change. If 3b breaks the bus output, it's harder to
  tell whether the controller wrapper or the reaction logic is at
  fault.
- Skip 3a + 3b, jump to 3c: trigger sources without a controller
  to coordinate them = the same single-worker pipeline with more
  inputs, no benefit.
```

## Controller contract (chunks 3a + 3b)

```text
Decision:
- LoopController is a class with one public entry point:
  ``submit(event: Event) -> None``.
- Inside, it owns:
    * a bounded queue (``queue.Queue``, same shape the watcher
      already uses internally)
    * a single worker thread that pops events and dispatches them
      through the existing ``Pipeline``
    * a state record per dispatch: which event id, which adapter
      ran, success/failure, which human_decision events
      correlate (chunk 3b)
- The watcher's existing worker thread is REPLACED by the
  controller's. ``FilesystemWatcher`` keeps the inotify-side
  drain but hands its events to ``controller.submit`` instead of
  invoking ``pipeline()`` directly.
- chunk 3b: the controller subscribes to the bus via
  ``JsonlTailReader`` (same primitive Phase 2 uses) and reacts
  to ``human_decision`` events whose text matches the pattern
  ``/correct <event_id>`` or ``/scar``. When a match arrives, the
  controller looks up the originating ``file_change`` and submits
  it again. The new dispatch passes through ``Pipeline._apply_scar_override``
  which now finds the chat-recorded scar and applies it.

Reason:
- Reuses every Phase 1 / Phase 2 primitive. No new bus event types.
- The replacement of the watcher's worker thread keeps the
  "single worker, single dispatch" invariant the pipeline tests
  rely on.
- Reaction via re-submit (not via mutating the in-flight pipeline
  state) keeps the reaction path testable in isolation.
```

### Boundary diagram

```text
chunk 3a (refactor):

  watcher (inotify) ──► controller.submit(event) ──► queue
                                                       │
                                                       ▼
                                            worker thread (single)
                                                       │
                                                       ▼
                                                pipeline(event)
                                                       │
                                                       ▼
                                              bus.append(...)


chunk 3b (reaction):

  watcher ──► controller.submit ──► queue ──► worker ──► pipeline
                                                                  │
                                                                  ▼
                                                              bus.append
                                                                  │
                                              JsonlTailReader ◄───┘
                                                       │
                                                       ▼
                                          controller.on_event(human_decision)
                                                       │
                                                       ├─ /correct <id> -> resubmit file_change with id
                                                       ├─ /scar         -> resubmit latest file_change
                                                       └─ else         -> no-op


chunk 3c (multi-source):

  watcher ─┐
  git hook ─┼──► controller.submit(event)
  ...     ─┘
```

## Frozen contracts (must NOT change in Phase 3)

```text
- AgentResponse, F3, F7, F8 (Phase 1 freeze; Phase 2 confirmed).
- Surface contract from docs/phase-2-surface.md:
  surface = sink on the read side; surface mutates ScarEngine
  via /correct + /scar; surface does NOT call the controller
  directly. The controller observes the bus.
- Pipeline._apply_scar_override semantics. Chat-recorded scars
  fire via this existing path; we do not invent a second
  consultation route.
- Single-worker invariant. Phase 3 introduces a CONTROLLER, not
  parallelism. Adapter concurrency stays one-at-a-time.
```

## Open questions to resolve while implementing

```text
1. Reaction loop: how many resubmits before the controller gives
   up? Lean: cap at 3 per (event_id, scar_id) tuple, then
   record an escalation event for the operator. Phase 1 had no
   retry; introducing a real one needs a stop rule.

2. Re-classification on resubmit: the controller submits the
   same Event object, so the classifier runs again. Does that
   pick up the new scar? Current Pipeline._apply_scar_override
   reads ScarEngine.find each time, so yes — but tests must
   confirm a chat-recorded scar fires on the very next resubmit,
   not after a process restart.

3. Telemetry: should the controller emit "controller_event" types
   on the bus for each submit / dispatch / reaction, or stay
   invisible? Lean: stay invisible in 3a, add minimal
   "controller_action" events in 3b so the operator can /tail
   the loop.

4. Failure handling: when the adapter hangs or returns
   status=failed, the current pipeline records it on the bus and
   moves on. Does the controller retry? Lean: NO in 3a; YES with
   exponential backoff in a future chunk only after we measure a
   real failure.

5. Async vs threaded: python-telegram-bot's Application uses
   asyncio. The pipeline + watcher use threads. Should the
   controller be async?  Lean: stay threaded. asyncio.run is
   already isolated to TelegramInterface.send and run_application;
   adding a second event loop for the controller doubles the
   complexity without a clear benefit.
```

## First PR plan (chunk 3a)

```text
Branch:  feat/loop-controller-wrapper
Scope:   ≤400 LOC including tests.
Goal:    introduce LoopController as a no-behaviour-change wrapper
         around the existing pipeline. Bus output is bit-for-bit
         identical on a fixed event sequence.

Files touched:
- src/karasu/controller/__init__.py        (new; ~5 LOC)
- src/karasu/controller/loop.py            (new; ~80 LOC)
- src/karasu/watcher/fs_watcher.py         (rewire on_event from
                                            pipeline → controller; ~10 LOC)
- src/karasu/__main__.py                   (wire LoopController
                                            into cmd_watch; ~15 LOC)
- tests/test_controller.py                 (new; ~150 LOC,
                                            including parity test)
- tests/test_pipeline.py / test_watcher.py (no semantic change;
                                            adjust if needed)
- docs/architecture.md                     (update module map; ~20 LOC)
- docs/memory/{current-state, session-log,
  decision-log, next-session}.md           (sync; ~40 LOC)

Behaviour shipped:
- LoopController(pipeline, queue_size=...) class.
- .submit(event) is the only public method besides .start() / .stop().
- Single worker thread, daemon, joins on .stop().
- No reaction logic, no retries, no telemetry — all reserved for
  later chunks.
- Watcher routes events through controller.submit().

Tests:
- Parity: feed N file_change events to the watcher with the
  controller wired vs. the legacy direct path; assert the same
  list of bus events comes out (same types, same correlations).
- Worker lifecycle: .start() spawns one thread, .stop() joins it
  cleanly, no daemon leaks.
- Bounded queue: filling past capacity drops the oldest pending
  event with a warning (same policy the watcher uses today).
- Crash containment: if the pipeline raises, the worker logs and
  continues; subsequent submits still process.

Out of this PR:
- Reaction to human_decision (chunk 3b).
- Trigger source plug-in (chunk 3c).
- Retries, telemetry events, async runtime.
```

## Do NOT do in Phase 3

```text
- LoopController as a state machine with explicit phases. Single
  worker + queue is enough for the synchronous invariant.
- Async event loop. Threads stay; asyncio is contained to the
  Telegram surface.
- Pipeline replacement. The controller WRAPS, never replaces, the
  current Pipeline.
- Touch AgentResponse, F3 dispatcher semantics, F7 dispatch_on,
  F8 timeout_s. All four remain frozen.
- Mutate scars from the controller. Scars are written by the
  surface (Phase 2 chunk 3) and read by the pipeline. The
  controller observes outcomes; it does not author them.
- Open Phase 3+ archive items (git hooks, webhooks, A2A) before
  chunks 3a + 3b are merged. Trigger source plug-in (3c) opens
  that surface intentionally and in scope.
```

## Exit condition for chunk 3a

```text
- LoopController shipped, tested, parity-verified.
- Watcher uses controller.submit. Bus output identical to pre-3a
  on a fixed sequence (regression test asserts).
- docs/architecture.md updated with the new layer.
- Memory files synced; next-session points at chunk 3b
  (reaction loop).
- Audit gate per the Phase 2 cadence: chunks 3a + 3b + 3c get
  reviewed by ChatGPT before any new phase opens.
```

## Anchor

Phase 2 closed 2026-04-29 (PRs #30, #31, #32, #33 merged).
Audit accepted with one round of changes (PR #33 contract
alignment + redaction). 151/151 tests on main.

LoopController design opens the next architectural cycle. Same
review-loop policy: design PR first, then small code chunks, audit
gate before phase transitions.
