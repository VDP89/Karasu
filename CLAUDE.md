# CLAUDE.md

Karasu is an adaptive coordination layer between AI agents. See
`README.md` for the user-facing description and `docs/architecture.md`
for the module layout.

## Working agreements

- **PR-first.** Open a feature branch + PR for every chunk of work.
  Never push to `main` directly.
- **Reviews are iterative and out-of-band, via Codex (mediated through
  ChatGPT).** The operator pastes the PR diff and the audit prompt into
  a ChatGPT conversation, Codex returns the verdict, and the operator
  ferries it back. Codex is therefore an **iterative auditor of every
  UI-N and backend chunk in this repo**, not a passive reader — the
  binding constraints currently shaping UI-5 (`.webm` required without
  exception, "el crow puede tener vida; la superficie no puede perder
  calma", and the recording-must-show-the-shell pin) are all Codex
  audit pins ferried back from prior chunks.
  Do NOT tag `@codex review` and do NOT rely on the ChatGPT Codex
  Connector GitHub App — the operator does not want automated bot
  reviews on this repo. The flow stays operator-mediated by design.
- **Address findings autonomously per `docs/review-loop.md`.** Don't
  escalate to the user for routine review iterations. Close the loop
  yourself unless the policy says to stop.
- **One PR per chunk, small chunks.** A PR over ~400 lines is a sign
  the chunk should have been split.

## Collaboration & attribution

Karasu is built by a small dual-AI loop, mediated by the operator:

```text
- Claude Code (Anthropic)        primary implementer. Writes the
                                 code, runs the tests, opens the PR.
- Codex (OpenAI, via ChatGPT)    iterative auditor. Reads the PR
                                 diff + the audit prompt, returns
                                 verdicts, pins binding constraints
                                 that future chunks must respect.
- Operator                       routes between the two; lands the
                                 merge; resolves architectural
                                 ambiguity.
```

When recording authorship in commits and PR bodies, credit the loop:

```text
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
Co-Audited-By: Codex (via ChatGPT, operator-mediated)
```

The README's "What Karasu does" section already names Codex as part of
the routing problem the project solves; this section names Codex as
part of how the project itself is built.

## When to escalate

See `docs/review-loop.md`. In short: deadlock, loop-budget exhausted,
architectural decision, or ambiguous finding.

## When to stop

After requesting a ChatGPT review out-of-band, wait for the
operator to ferry the verdict back. If they have not replied
within ~5 minutes, move to another branch and keep working — they
will return with the audit when ready.
