# 2026-05-02 — Chunk 4c hard pre-reqs (gates 1 + 2)

Phase 3+ chunk 4c (review-comment auto-handoff) was promoted in
the pre-mortem audit (PR #48) to require two hard pre-reqs on
main before opening: an issue #47 cap-design outline, and a
runtime startup warning for adapters at `trust_level >= 2`.
This session opened both gates as parallel PRs and absorbed the
first round of audit findings on gate 2.

## Operator + environment

```text
Operator:           VDP89
Date:               2026-05-02
OS:                 Linux 6.18.5 (sandboxed)
Shell:              bash
Python:             3 (project venv)
Repo:               /home/user/Karasu-
```

## Goal

Open the two hard pre-reqs of chunk 4c so the chunk itself can
be scheduled. The two PRs are independent and can merge in any
order; chunk 4c does not open until both are on main.

```text
Gate 1: Issue #47 cap-local-per-origin — outline plan
        (doc-only) of a Phase 3+ design extension to the
        controller cap shape. Without it, F-HANDOFF-4 (cap
        distributed-loop amplification) is unbounded.

Gate 2: NICE-TO-HAVE #3 — startup warning when an adapter is
        constructed at trust_level >= 2. Promoted from
        "recommendation" to hard pre-req in the pre-mortem
        audit because the chunk-4c combination (auto-handoff
        + trust>=2) is the one where prompt injection from
        PR comments becomes autonomous code edits.
```

## Setup walkthrough

Two parallel branches off main:

```text
$ git checkout -b docs/issue-47-cap-shape
$ git checkout -b feat/trust-startup-warning
```

Branches are independent; either gate could land first.

## Findings + real-time debugging

### Gate 1 — cap-design Option B picked

Reviewed three alternatives in `docs/phase-3-cap-design.md`:

```text
Option A: global session counter (one bucket per process)
Option B: chain cap with origin-aware tracking via
          `controller_chain_depth` field on file_change.data
Option C: hybrid (Option B + a soft global ceiling)
```

Picked **Option B**. Chain root walks `resubmit_origin`
transitively; `_chain_counts[root_id]` keyed by chain root,
not per-file id. CHAIN_CAP=3. Documented F-CAP-1..F-CAP-4 +
test sketch + frozen-contract additivity (the new field is an
additive schema bump, contract-preserving).

Doc landed as PR #53.

### Gate 2 — implementation, two layers

Implemented on `feat/trust-startup-warning`:

1. `src/karasu/adapters/base.py` gained
   `AUTONOMOUS_TRUST_LEVEL = 2` (module-level constant) and
   `_log = logging.getLogger(__name__)`. `AgentAdapter.__init__`
   emits a structured `logging.WARNING` whenever
   `trust_level >= AUTONOMOUS_TRUST_LEVEL`. Message names the
   adapter, the level, and points at `docs/local-dogfood.md`
   "Trust gradient — what trust_level actually does in
   production".

2. `src/karasu/__main__.py` gained
   `_announce_autonomous_adapters(adapters)` — filters by
   threshold and prints a loud `⚠ trust gradient: …` banner
   to stderr listing autonomous adapters by `name(trust=N)`.
   Wired into `cmd_watch` and `cmd_serve`.

11 new tests in `tests/test_trust_startup_warning.py`.

PR #54 opened. 267/267 green at that point.

### Gate 2 — first audit cycle: NO APROBADO

Audit returned 1 REQUERIDO + 2 NICE-TO-HAVE:

```text
REQUERIDO  cmd_hook also called _announce_autonomous_adapters.
           Out of contract — chunk's scope was watch + serve
           only; the hook flow is one-shot per commit and
           polluting its stderr is noise. Plus untested.

NICE-TO-HAVE 1  Add a real integration test of cmd_watch /
                cmd_serve through main(["watch", ...]) /
                main(["serve", ...]) — not just the helper.
NICE-TO-HAVE 2  Use flush=True on the banner so the warning
                is visible immediately even when stderr is
                line- or block-buffered.
```

The cmd_hook leak was a real over-reach in the diff. Removed
the call. Added inline doc comment explaining why the hook
flow is silent (operator already opted in via cmd_watch /
cmd_serve in their long-running session; the structured
logging.WARNING from `__init__` still fires for headless
collectors).

### Contract-pin test for the wiring boundary

Rather than just removing the call and trusting the diff, added
a contract test that uses `inspect.getsource` to assert:

```text
helper string in inspect.getsource(cmd_watch)   ✔
helper string in inspect.getsource(cmd_serve)   ✔
helper string in inspect.getsource(cmd_hook)    ✘ (negated)
```

A future contributor adding the helper to a one-shot entry
point trips this test.

NICE-TO-HAVE 2 (flush=True) applied — one-line cost, aligns
with banner-must-be-visible-immediately semantics.

NICE-TO-HAVE 1 (real integration test of cmd_watch / cmd_serve
through main) deferred. cmd_watch blocks on the watcher thread;
cmd_serve binds a real port. Stubbing them is heavier than the
contract-pin equivalent already shipped. Re-flag as REQUERIDO
in the next round if the auditor says so.

## Evidence captured

```text
PR #53  docs/issue-47-cap-shape   awaiting first audit
PR #54  feat/trust-startup-warning  first audit NO APROBADO
        commit b23160d  initial implementation (267/267)
        commit ba3994e  REQUERIDO + NICE-TO-HAVE 2 applied
                        (268/268 — added contract-pin test)
```

Test counts:

```text
Pre-session:           256 / 256
After gate 2 v1:       267 / 267 (+11 trust-warning tests)
After gate 2 audit-fix: 268 / 268 (+1 wiring contract test)
```

## Decisions made

1. **Cap shape: Option B (chain cap with origin-aware
   tracking).** Reason: bounds the actual failure mode
   (F-HANDOFF-4 distributed-loop amplification) without a
   global rate limit that would penalise legitimate parallel
   work. Discarded Option A (too coarse) and Option C (hybrid
   adds complexity for marginal gain).

2. **NICE-TO-HAVE #3: two layers, not one.** Reason: structured
   `logging.WARNING` covers headless collectors / audit
   trails / `karasu serve` under a service manager; loud
   stderr banner covers the human running `karasu watch`
   interactively. Buried log lines are easy to miss. Tested
   independently so a future refactor can't silently drop
   either.

3. **`AUTONOMOUS_TRUST_LEVEL` as a module-level constant.**
   Reason: single named constant for runtime check + test
   pin. A future contributor moving the bar surfaces the
   change as a visible diff in the dedicated test
   (`test_autonomous_trust_level_constant_is_2`).

4. **Banner lives in `__main__`, not in the library.**
   Reason: adapters constructed by tests / SDK consumers
   should not pollute their stderr. Libraries get the
   WARNING via standard `logging`; CLI users get the banner
   on top.

5. **`cmd_hook` is intentionally silent at the banner layer.**
   Reason: one-shot per-commit flow; banner on every commit
   is noise. Operator already opted in via the long-running
   `cmd_watch` / `cmd_serve` session. Pinned with a contract
   test using `inspect.getsource`.

6. **NICE-TO-HAVE 1 (real cmd_watch/cmd_serve integration
   test) deferred this round.** Reason: contract-pin test
   covers the same regression surface at lower cost; if
   auditor escalates to REQUERIDO in round 2, ship the heavy
   integration test then.

## Artifacts left behind

```text
Repo:
  - PR #53 — docs(memory): cap-local-per-origin outline
             (gate 1, awaiting first audit)
  - PR #54 — feat(adapters): NICE-TO-HAVE #3 startup warning
             (gate 2, awaiting re-audit after first round)
  - tests/test_trust_startup_warning.py — 12 tests
  - docs/phase-3-cap-design.md — Option B design

  Files modified (gate 2):
  - src/karasu/adapters/base.py  (constant + warning)
  - src/karasu/__main__.py       (announce helper + wiring)
  - tests/test_trust_startup_warning.py  (12 tests)

Operator's machine:
  - Two open PRs awaiting Codex audit.
External:
  - none
```

## Lessons learned

1. **Read the diff for over-reach before opening the PR.**
   The cmd_hook leak was a 1-line diff scope expansion that
   the audit caught immediately. A 30-second `git diff` re-read
   asking "does every change here serve the stated scope?"
   would have caught it pre-PR.

2. **Contract-pin tests via `inspect.getsource` are cheap and
   surface refactor regressions.** They don't replace integration
   tests, but they're free insurance against "someone adds the
   helper to a new entry point and nobody notices".

3. **Two parallel gate PRs, independent, is the right shape.**
   Either can land first; failure on one doesn't block the other.
   When two pre-reqs are truly independent, do not stack them.

4. **`AUTONOMOUS_TRUST_LEVEL` as a named constant beats a magic
   `2` literal.** The dedicated `== 2` test pin is the
   tripwire: moving the bar is a visible diff at three sites
   (constant, runtime check, test). If a future tier "4 = full
   write access to remote infra" appears, this scaffolding
   already supports it.

## Next step pointer

```text
See ../next-session.md — pointed at:
  - PR #53 audit (gate 1)
  - PR #54 re-audit after the REQUERIDO fix (gate 2)
  - chunk 4c (feat/review-comment-handoff) opens once both
    gates land on main.
```
