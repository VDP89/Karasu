# CLAUDE.md

Karasu is an adaptive coordination layer between AI agents. See
`README.md` for the user-facing description and `docs/architecture.md`
for the module layout.

## Working agreements

- **PR-first.** Open a feature branch + PR for every chunk of work.
  Never push to `main` directly.
- **Reviews are out-of-band via ChatGPT.** The operator pastes the
  PR diff and the audit prompt into a ChatGPT conversation and
  ferries the verdict back. Do NOT tag `@codex review` and do NOT
  rely on the ChatGPT Codex Connector GitHub App — the operator
  does not want automated bot reviews on this repo.
- **Address findings autonomously per `docs/review-loop.md`.** Don't
  escalate to the user for routine review iterations. Close the loop
  yourself unless the policy says to stop.
- **One PR per chunk, small chunks.** A PR over ~400 lines is a sign
  the chunk should have been split.

## When to escalate

See `docs/review-loop.md`. In short: deadlock, loop-budget exhausted,
architectural decision, or ambiguous finding.

## When to stop

After requesting a ChatGPT review out-of-band, wait for the
operator to ferry the verdict back. If they have not replied
within ~5 minutes, move to another branch and keep working — they
will return with the audit when ready.
