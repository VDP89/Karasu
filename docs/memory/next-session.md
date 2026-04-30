# Next Session Entry Point

## Goal

**Phase 3 audit gate.**

Phase 3 chunks 3a + 3b + 3c are pushed and stacked:

- **PR #34** — design doc `docs/phase-3-loop-controller.md` (merged).
- **PR #35** — chunk 3a: `LoopController` wrapper around the existing pipeline.
- **PR #36** — chunk 3b: bus subscription + reaction (resubmit on `/correct` / `/scar`). Stacked on #35.
- **PR #37** — chunk 3c: `TriggerSource` Protocol + watcher as registered source + `karasu hook` CLI. Stacked on #36.

Per the operator policy: ChatGPT acts as the reviewer. The
maintainer hands the PR set to ChatGPT for the audit. **No new
chunk or phase starts until the audit returns.**

## Pre-reads for the audit

```text
1. docs/phase-3-loop-controller.md     — surface contract (frozen)
2. docs/memory/current-state.md        — phase + capabilities snapshot
3. docs/memory/session-log.md          — chunk-by-chunk record
4. docs/memory/decision-log.md         — durable decisions
5. src/karasu/controller/loop.py       — LoopController (worker + bus + sources)
6. src/karasu/controller/sources/      — TriggerSource Protocol + git_hook
7. src/karasu/watcher/fs_watcher.py    — refactor: source-shaped lifecycle
8. tests/test_controller.py            — 26 tests (chunks 3a + 3b)
9. tests/test_controller_sources.py    — 18 tests (chunk 3c)
```

## Questions ChatGPT should be asked

```text
1. Does the surface contract in docs/phase-3-loop-controller.md
   match the shipped behaviour across chunks 3a + 3b + 3c? Any drift?
2. Is the resubmit cap (3 per originating file_change.id) the
   right shape, or should it be (id, scar_id) keyed?
3. Is the Protocol + duck-typed `start`/`stop` enough as the
   trigger-source contract, or should we move to an ABC?
4. Should the git-hook source persist a `git_hook_run` event on
   the bus to record which hook fired and when, or is the per-
   path `git_hook` field sufficient?
5. The watcher's `start_pipeline`/`stop_pipeline` legacy
   delegators only exist to keep the existing test suite passing.
   Worth removing in a Phase 3+ cleanup, or leave as scaffolding?
```

## If the audit accepts

```text
- Merge #35 → #36 → #37 in order (each base re-targeted to main as
  the previous lands).
- Open the next phase. Three candidates from issue #5 archive:
  GitHub webhook receiver, A2A Agent Cards, review-comment
  auto-handoff. Each plugs into chunk 3c's TriggerSource (or
  one-shot CLI) seam without further controller refactoring.
```

## If the audit asks for changes

```text
- File the requested changes as one focused commit per concern on
  the relevant chunk's branch.
- Keep stack order intact unless the audit asks to collapse the
  chunks — premature collapse loses review history.
- Re-request the audit after the changes are pushed. Do not start a
  new phase until ChatGPT signs off.
```

## Do NOT do during the audit window

```text
- Do not start GitHub webhook / A2A / review-comment handoff work.
- Do not parallelize the controller worker.
- Do not abstract the adapter behind a plugin layer.
- Do not let the pipeline consume human_decision directly.
- Do not touch AgentResponse, F3, F7, F8.
```

## Anchor for the previous sessions

- Phase 1C closed 2026-04-29 (PR #29).
- Phase 2 closed 2026-04-30 (PRs #30 #31 #32 #33 merged after audit
  + condition fix).
- Phase 3 design merged 2026-04-30 (PR #34).
- `feat/loop-controller-wrapper` (PR #35) — chunk 3a, 11 new tests.
- `feat/loop-controller-react` (PR #36) — chunk 3b, 15 new tests.
- `feat/loop-controller-sources` (PR #37) — chunk 3c, 18 new tests.
- 197/197 tests green locally on the chunk-3c tip (88 prior + 30
  Phase 2 + 11 + 15 + 18 + 35 controller / interface / sources).
