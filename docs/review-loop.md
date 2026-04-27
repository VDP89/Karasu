# Review loop policy

How Karasu's agents — currently Claude Code and Codex — coordinate
on a pull request without dragging a human into every iteration.

## Per-finding decision tree

For every finding raised in a review, classify it before acting:

| Verdict on the finding | Action                                                       |
|-----------------------:|--------------------------------------------------------------|
| Correct, small (<30 lines, single module) | Fix, push, reply on the thread.       |
| Correct, large or architectural | Stop. Escalate to the user.                          |
| Wrong (false positive, already fixed elsewhere, irrelevant) | Reply on the thread with the reasoning. Do **not** push a fix. Do **not** request a re-review. |
| Ambiguous (depends on a design choice not yet made) | Escalate to the user.            |

A finding is "wrong" when at least one of these holds:

- The behavior described does not actually occur. Mentally execute
  the code or write a test to confirm.
- The proposed fix contradicts a deliberate design choice already
  agreed upon (in this doc, in `docs/`, or in a previous PR).
- The same fix has already been applied at a different location and
  the reviewer didn't notice.

The standard is symmetrical: it applies whether the finding came
from Codex or from Claude Code.

## Loop budget

A "round" is one Codex review followed by the implementer's reply
or fixup commit.

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

After requesting a review (`@codex review` or equivalent):

- Wait at most **5 minutes** for the response.
- At 5 minutes with no response, switch to other work on a different
  branch. Do not poll. Do not ping again immediately.
- The PR webhook subscription will deliver Codex's review when it
  arrives, regardless of which branch you're working on.
- If 30 minutes pass with no response, post one diagnostic comment
  (`@codex still alive?`) and continue.

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

- All P1 findings on the latest commit are resolved.
- All P2 findings on the latest commit are either resolved or
  counter-argued with the implementer's reasoning visible on the
  thread.
- CI is green.
- No outstanding deadlock.
- No outstanding escalation awaiting user input.
