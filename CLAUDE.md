# CLAUDE.md

Karasu is an adaptive coordination layer between AI agents. See
`README.md` for the user-facing description and `docs/architecture.md`
for the module layout.

## Working agreements

- **PR-first.** Open a feature branch + PR for every chunk of work.
  Never push to `main` directly.
- **Tag `@codex review` on every PR.** Codex acts as the reviewer for
  this repo via the ChatGPT Codex Connector GitHub App.
- **Address findings autonomously per `docs/review-loop.md`.** Don't
  escalate to the user for routine review iterations. Close the loop
  yourself unless the policy says to stop.
- **One PR per chunk, small chunks.** A PR over ~400 lines is a sign
  the chunk should have been split.

## When to escalate

See `docs/review-loop.md`. In short: deadlock, loop-budget exhausted,
architectural decision, or ambiguous finding.

## When to stop

After `@codex review`, wait up to 5 minutes for the reply. If silence,
move to another branch and keep working — the webhook will bring you
back when there's something to act on.
