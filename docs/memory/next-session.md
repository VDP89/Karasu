# Next Session Entry Point

## Goal

**Phase 3 chunk 3c — multi-source trigger plug-in.**

Chunks 3a (LoopController wrapper) and 3b (react to `human_decision`)
are pushed and stacked. The controller now (a) coordinates dispatch
through one bounded queue + worker, and (b) reacts to chat-recorded
scars by resubmitting the originating `file_change`. Chunk 3c
generalises the trigger surface: the watcher is currently the only
caller of `controller.submit`; chunk 3c introduces a plug-in
interface so additional sources can fan in.

## Scope

```text
What ships in 3c:
- A TriggerSource protocol (or abstract base) with one method:
    start(submit: Callable[[Event], None]) -> None
    stop() -> None
  Sources call ``submit`` to fan events into the controller.
- FilesystemWatcher refactored to implement TriggerSource (no
  behavioural change; the watcher already does this implicitly).
- A new GitHookSource (issue #5 sketch — sketch only, gated behind
  an explicit `karasu hook` invocation, NOT auto-installed in this
  chunk).
- LoopController accepts a list of TriggerSource instances and
  manages their lifecycle alongside the worker + bus subscription.
  start() spawns each source's start; stop() reverses.

What does NOT ship in 3c:
- GitHub webhook receiver (issue #5).
- A2A Agent Cards (issue #5).
- Review-comment auto-handoff (issue #5).
- Auto-installation of git hooks (`karasu install-hooks`).
- Any change to AgentResponse, F3, F7, F8, surface contract.
```

## Surface contract — must respect

```text
- Trigger sources are PRODUCERS. They call submit() and own no
  callback semantics, no scheduling, no retries.
- The controller is the only place that owns the worker queue and
  the bus subscription. Sources do not subscribe to the bus.
- Pipeline still does NOT consume human_decision. The controller's
  bus subscription (chunk 3b) is the only consumer.
- Single-worker invariant remains. Multiple sources fan into the
  same queue; events still process serially.
- Resubmit cap from chunk 3b applies to controller-originated
  events; trigger-source events have their own lifecycle and do
  not consume the cap.
```

## Pre-reads

```text
1. docs/phase-3-loop-controller.md     — chunk 3c design (multi-source goal)
2. docs/memory/current-state.md        — phase + capabilities
3. docs/memory/session-log.md          — chunks 3a + 3b summaries
4. docs/memory/decision-log.md         — controller decisions
5. src/karasu/controller/loop.py       — extension target (start/stop will manage sources)
6. src/karasu/watcher/fs_watcher.py    — first source, will gain a thin TriggerSource adapter
7. issue #5 (archive)                  — git-hook sketch, A2A, webhook
```

## Open questions to resolve while implementing

```text
1. Is TriggerSource a Protocol (PEP 544 structural) or an abstract
   base class? Lean: Protocol — the watcher already has start/stop
   and Python's structural typing keeps the refactor minimal.

2. How does the controller signal a source to stop? Lean: each
   source owns its own daemon thread (the watcher already does);
   stop() on the source signals + joins. The controller does NOT
   try to interrupt arbitrary source threads.

3. Should sources write directly to the bus, or hand events to
   the controller and let it write? Lean: sources write the bus
   event themselves (the watcher already does). The controller is
   not the bus-write authority; it's the dispatch coordinator.

4. Git-hook source — how is it invoked? Lean: ``karasu hook
   <name>`` CLI subcommand reads stdin / argv from the hook
   environment, builds an Event, submits via the controller, and
   exits when the queue drains. Mirrors the sketch in issue #5.
   Auto-installation (`karasu install-hooks`) waits for a later
   chunk.
```

## Do NOT do yet

```text
- Do not start the GitHub webhook receiver (Phase 3+ archive).
- Do not start the A2A Agent Cards work.
- Do not auto-install git hooks; only land the hook source.
- Do not parallelize the controller worker. Multi-source means
  more producers, not more consumers.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
```

## Exit condition

```text
A new feat/* branch, ≤400 LOC, with:
- TriggerSource protocol defined in src/karasu/controller/sources/.
- FilesystemWatcher implements it (no behavioural change).
- GitHookSource sketch with `karasu hook <name>` subcommand.
- LoopController.add_source() / start() / stop() lifecycle.
- Tests for the protocol contract, the git-hook source, and a
  multi-source fan-in (events from two sources interleave correctly
  on the bus).
- Memory files synced; this file pointed at the post-3c audit gate.
```

## Audit gate after chunk 3c

Per the Phase 2 cadence: ChatGPT reviews chunks 3a + 3b + 3c
together once 3c is pushed. The maintainer hands the stack
manually. **No new phase opens until the audit returns.**

## Anchor for the previous sessions

- Phase 1C closed 2026-04-29 (PR #29).
- Phase 2 closed 2026-04-30 (PRs #30 #31 #32 #33 merged after audit
  + condition fix).
- Phase 3 design merged 2026-04-30 (PR #34).
- `feat/loop-controller-wrapper` (PR #35) — chunk 3a code, 11 new
  controller tests.
- `feat/loop-controller-react` (this session) — chunk 3b code, 15
  new controller tests, stacked on PR #35. 177/177 green locally.
