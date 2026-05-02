# YYYY-MM-DD — <short title of the session>

One-paragraph summary of what the session set out to do and what
came out of it. Names the headline outcome (e.g. "loop validated",
"phase closed", "blocker found") so a future reader can decide in
five seconds whether to keep reading.

## Operator + environment

```text
Operator:           <github handle / org>
Date:               YYYY-MM-DD
OS:                 <e.g. Windows 11 / macOS 14 / Ubuntu 24.04>
Shell:              <cmd / pwsh / bash / zsh>
Python:             <X.Y.Z + path>
Claude Code CLI:    <X.Y.Z + path if relevant>
Other tool versions: <as relevant>
Sandbox:            <path, if a sandbox was used>
Repo:               <path of working clone>
```

## Goal

What this session was trying to accomplish. One paragraph.
Explicit about which contract / phase / chunk it touches and why
it was scheduled for today.

## Setup walkthrough

Concrete commands typed, in the order they ran. Include output
where it was instructive (e.g. version strings that mattered, a
stale entry in `where python` that explained a later issue).

```text
$ <command>
<output>
```

If the setup was identical to a previous session, link to the
prior bitácora and just note the deltas.

## Findings + real-time debugging

Each finding gets a sub-section in the order it surfaced. Include:

- The first symptom that made you suspect it.
- The diagnosis path (how long it took, what tools / logs you used).
- The fix or workaround applied during the session.
- Whether it was filed as an F-finding for a follow-up PR.

If a hypothesis was wrong, write down what you initially thought
and what corrected it. Future contributors will hit the same
mis-cues.

## Evidence captured

Concrete artifacts that prove what happened: bus events with
timestamps, log excerpts, terminal output, screenshots. Quote
verbatim where the wording matters (e.g. an agent's own
acknowledgement that a contract was honoured).

```text
HH:MM:SS.mmmZ  <event-type>  <key fields>  id=<short>
HH:MM:SS.mmmZ  <event-type>  <key fields>  id=<short>
HH:MM:SS.mmmZ  <event-type>  <key fields>  id=<short>
```

## Decisions made

Numbered list of decisions taken **during this session** that were
not already in `decision-log.md`. For each:

- The choice itself.
- One-line reason.
- What was discarded.

If the decision is large enough to live in `decision-log.md`,
file it there too and back-reference here.

## Artifacts left behind

```text
Repo:
  - PRs: #N (one-line desc), #N (one-line desc), …
  - Issues: #N opened/closed
  - Files added / modified beyond the PR list (if any)
Operator's machine:
  - Local artifacts the next session may want to find
External:
  - Bots / accounts / cloud resources created
```

## Lessons learned

Numbered list, written for the next contributor (which may be
future-you). Each lesson is one paragraph max. Cover both:

- What worked and should be repeated.
- What surprised you and should be guarded against.

If a lesson is large enough to be a roadmap item, file an issue
and link it here.

## Next step pointer

```text
See ../next-session.md — pointed at <one-line description of the
next concrete artifact to produce>.
```
