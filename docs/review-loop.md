# Review loop policy

How Karasu's agents and the human operator coordinate on a pull
request without dragging the human into every iteration.

**Reviewer:** ChatGPT, out-of-band. The operator pastes the PR
diff and an audit prompt into a ChatGPT conversation and ferries
the verdict back. The earlier "Codex bot via the ChatGPT Codex
Connector GitHub App" wiring was retired on 2026-05-03 — the
operator did not want automated bot reviews on this repo.

Do NOT tag `@codex review` on PRs. The Codex Connector App
remains uninstalled at the repo level by operator decision; any
automated review comment that does appear should be treated as
noise, not as a finding to act on.

## Per-finding decision tree

For every finding raised in a review, classify it before acting:

| Verdict on the finding | Action                                                       |
|-----------------------:|--------------------------------------------------------------|
| Correct, small (<30 lines, single module) | Fix, push, reply on the thread.       |
| Correct, large or architectural | Stop. Escalate to the user.                          |
| Wrong (false positive, already fixed elsewhere, irrelevant) — P2 or lower | Reply on the thread with the reasoning. Do **not** push a fix. Do **not** request a re-review. |
| Wrong — P0 or P1 | Reply with reasoning **and** escalate to the user. Counter-argument alone does not satisfy ship criteria for release-blocking findings. |
| Ambiguous (depends on a design choice not yet made) | Escalate to the user.            |

A finding is "wrong" when at least one of these holds:

- The behavior described does not actually occur. Mentally execute
  the code or write a test to confirm.
- The proposed fix contradicts a deliberate design choice already
  agreed upon (in this doc, in `docs/`, or in a previous PR).
- The same fix has already been applied at a different location and
  the reviewer didn't notice.

The standard is symmetrical: it applies whether the finding came
from the ChatGPT reviewer or from Claude Code itself.

## Loop budget

A "round" is one ChatGPT review followed by the implementer's
reply or fixup commit.

- **Hard cap: 5 rounds per PR.** After round 5, escalate regardless
  of how many findings remain.
- **Theme-repetition cap: 3 rounds on the same module.** If three
  consecutive rounds raise findings against the same file, escalate
  even if each finding is technically distinct — that file is
  signalling it was undercooked and a wider rewrite or a design
  decision is needed.
- **Deadlock: 1 round.** If the reviewer raises a finding, the
  implementer counter-argues, and the reviewer comes back with the
  same finding (same root cause, possibly different wording),
  escalate immediately. Do not oscillate.

Reset the round counter when the PR is rebased onto a substantially
different base (e.g., main has moved several commits).

## Wait timeout

After the operator says they have requested a ChatGPT review:

- Wait at most **5 minutes** for the verdict to come back.
- At 5 minutes with no verdict, switch to other work on a
  different branch. Do not poll. Do not ping the operator.
- The operator will return with the verdict when ready; the
  reviewer is not subscribed to the PR webhook directly, so
  there is no auto-delivery.
- If 30 minutes pass, ask the operator once whether the audit
  is still in flight, then continue working on something else.

## Counter-arguments

When the implementer disagrees with a reviewer finding:

1. Reply on the thread with the reasoning. Cite the specific code,
   test, or doc that contradicts the finding.
2. Do **not** request another review until either (a) you've also
   pushed a related change, or (b) you're explicitly inviting the
   reviewer to push back.
3. If the reviewer comes back with the same finding, that's a
   deadlock. Escalate.

The implementer is allowed to win arguments. A reviewer is a smart
external lint, not an authority. But the implementer must show their
work — "I disagree" is not a counter-argument.

## Escalation

When the user must be involved:

1. Loop budget exhausted (round 5 or theme-repetition cap).
2. Deadlock between reviewer and implementer.
3. Architectural or large change needed.
4. Ambiguous finding that depends on an unmade design decision.
5. Disputed P0 or P1 finding — counter-argument alone cannot close
   a release-blocking gate, so the user must waive it explicitly.

Escalate by:

- Posting a single comment on the PR summarising the disagreement
  in less than 200 words. The user should not have to read the full
  thread to understand the question.
- Tagging the user (Phase 1) or sending the summary via the Telegram
  bot (once Phase 1 is shipped — see `docs/roadmap.md`).
- Stating clearly what decision is needed and what the options are.
- **Stopping.** Do not implement during escalation.

## Ship criteria

A PR is mergeable when all of these hold:

- All P0 findings on the latest commit are resolved, or escalated
  and explicitly waived by the user.
- All P1 findings on the latest commit are resolved, or escalated
  and explicitly waived by the user. Counter-argument alone is
  insufficient for P0 / P1.
- All P2 findings on the latest commit are either resolved or
  counter-argued with the implementer's reasoning visible on the
  thread.
- CI is green.
- No outstanding deadlock.
- No outstanding escalation awaiting user input.
