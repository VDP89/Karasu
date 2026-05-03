# 2026-05-02 (later) — Phase 3+ archive closed + UI handoff plan

This session closed the Phase 3+ archive (issue #5) at the
code level: chunk 4c gates landed, chunk 4c shipped, chunk 4c
hardening + audit-deferred follow-ups absorbed, issue #47
implementation closed, and the three open NICE-TO-HAVE
follow-ups (outbound A2A discovery, F-HANDOFF-6 path fallback,
priority persistence) all merged. Headline outcome: backend
roadmap (README Fase 1 + Fase 2) is **complete**; the only
open phase in the README is **Fase 3 — PWA + Advanced**, and
a parallel branch ``feat/ui-1-runtime`` already has a
ChatGPT-driven UI scaffold that the next session should pick
up and rework.

## Operator + environment

```text
Operator:           VDP89 (mobile, in transit Mon-Sun;
                    computer access expected Monday)
Date:               2026-05-02 (continued from
                    2026-05-02-chunk-4c-gates session)
OS:                 Linux 6.18.5 (sandboxed Claude Code)
Shell:              bash
Python:             3 (project venv)
Repo:               /home/user/Karasu-
```

## Goal

Close every code-shaped item still open in the Phase 3+
archive, leave main in a feature-complete state for README
Fase 1 + Fase 2, and produce a concrete handoff for the next
session (PWA / UI work on the parallel branch).

## What this session shipped (all merged to main)

```text
PR #57  feat(controller): chain cap implementation — closes #47
        Replaces RESUBMIT_CAP=3 (per-originating-id) with
        CHAIN_CAP=3 (per chain) + MAX_CHAIN_WALK_DEPTH=64 +
        CHAIN_COUNTS_MAX_SIZE=1024. Three layered defences in
        _chain_root: F-CAP-1 (missing parent), F-CAP-2 (only
        follow lineage on source="controller"), F-CAP-5
        (visited_set + ceiling). F-CAP-3 eviction
        (insertion-order). 11 new tests. Closes issue #47.

PR #58  feat(a2a): outbound discovery — fetch_card + karasu peers CLI
        Stdlib-only fetch_card(base_url, *, timeout=5.0) that
        returns the parsed JSON dict. AgentCardFetchError wraps
        all failure modes (HTTP non-2xx, network error, invalid
        JSON, non-object top-level). karasu peers <url>
        [--timeout N] [--json] CLI subcommand. 19 new tests.
        Round-2 fix absorbed urlparse-based URL resolution to
        preserve query / fragment.

PR #59  feat(adapters): F-HANDOFF-6 path-existence fallback
        PromptBuilder.path_exists callable (default
        Path.exists with empty-path guard + OSError swallow).
        When the comment's path is absent from the workspace,
        the github branch emits a "(metadata-only)" header
        variant with an explicit "Do NOT attempt edits"
        instruction; body still fenced + capped. 8 new tests.
        Memory cleanup absorbed in same PR.

PR #60  feat(router): persist effective priority on agent_response.data
        Dispatcher.dispatch sets data["priority"] =
        request.priority on the emitted agent_response.
        Additive schema bump. Combined with
        controller_chain_depth (PR #57), agent_response and
        resubmitted file_change events now carry enough
        metadata for analyze to reconstruct the full dispatch
        story (priority + chain depth + correlation) post-hoc,
        even across restarts. 3 new tests.
```

Plus the earlier session work that landed on main during this
arc: PR #53 (cap-design outline), PR #54 (NICE-TO-HAVE #3
trust-warning), PR #55 (chunk 4c base), PR #56 (chunk 4c
hardening). 12 PRs in total across the two sessions; all
audited APROBADO with at most one round of follow-up.

## Test count progression

```text
session start (post-merge of #54 + #53):  267 / 267
after PR #55:                              289 / 289 (+21 chunk 4c)
after PR #56:                              294 / 294 (+5 fence hardening)
after PR #57:                              305 / 305 (+11 chain cap)
after PR #58:                              324 / 324 (+19 fetch + URL parse)
after PR #59:                              332 / 332 (+8 F-HANDOFF-6)
after PR #60:                              335 / 335 (+3 priority persist)
```

## Findings + real-time debugging

### Cap-design audit absorbed three REQUERIDOS

PR #53 round 1 returned NO APROBADO with three blockers:
F-CAP-5 missing (cycle / forged-deep lineage in chain walk),
F-CAP-2 desalignment between text and pseudo-code, restart
semantics ambiguous. Round 2 absorbed all three in commit
``48ae765`` and landed APROBADO.

Key insight: even with F-CAP-2 in place (only walk lineage
on ``source="controller"``), an attacker who sets the lineage
fields once on a single forged event and then issues legitimate
resubmits chained onto it would force a deep walk on every
subsequent ``_resubmit_for``. So the walk cost MUST be bounded
by construction (``visited_set`` + ``MAX_CHAIN_WALK_DEPTH``),
not just by the cap counter.

### Chunk 4c audit: 0 REQUERIDOS

PR #55 landed APROBADO round 1 with three NICE-TO-HAVE
(future-proof truncation marker, fence hardening, metadata
shallow-copy doc note). Bundled all three into PR #56 as a
focused ~30 LOC hardening PR rather than opening separate
follow-ups. Round 2 of #56 absorbed one more NICE-TO-HAVE
(module docstring drift after the hardening) before merge.

### Outbound A2A audit caught real URL parsing gap

PR #58 audit returned APROBADO with a NICE-TO-HAVE flagging
that ``base_url.rstrip("/") + AGENT_CARD_PATH`` would break
for ``http://host/api?x=1`` (suffix lands after the query
string). Auditor explicitly said "merge inmediato sin
cambios" but the gap was correctness-adjacent. Fixed on the
same branch with ``urlparse``/``urlunparse`` + 2 new tests
before merge — kept the history tight (one squash commit).

### Memory file drift surfaced in PR #59 audit

PR #59 audit caught a duplicated "Review-comment auto-handoff"
bullet in ``current-state.md`` (the system-status list and
the "Next step" section both described chunk 4c, with the
"Next step" version stale from before the chunk merged).
Cleaned up on the same branch in commit ``7ce9df1`` before
merge.

## UI parallel branch — pickup plan for next session

Operator stated in this session that they were dissatisfied
with the ChatGPT-driven UI work on a parallel branch and want
Claude Code to take over. ChatGPT continues as auditor only.

### What's on ``feat/ui-1-runtime`` today

```text
src/karasu/ui/__init__.py           5 LOC
src/karasu/ui/server.py            95 LOC  ThreadingHTTPServer
                                            reading events.jsonl,
                                            /api/events endpoint,
                                            crow-state derivation
                                            (idle / processing /
                                            waiting / error).
src/karasu/ui/static/index.html    48 LOC  Stub HTML +
                                            timeline + crow
                                            state. Black/grey,
                                            monospace, NOT the
                                            Win95 mockup yet.
karasu ui  (new CLI subcommand)
docs/ui/karasu-win95-runtime-mockup.md  415 LOC  full spec.
docs/ui/assets/karasu_sprites_spec.md    30 LOC.
```

### Branch state

The branch was forked from main BEFORE chunks 4a / 4b / 4c /
cap-impl / fetch / fallback / priority-persist landed. It is
behind main by approximately 8-9 merged PRs. The ``git diff
main..origin/feat/ui-1-runtime --stat`` shows -5788/+725
because main has all the recent additions; the branch has
only the UI scaffold (+725) and is missing everything else.

### Plan (next session)

1. Bring ``feat/ui-1-runtime`` up to date with main. Cleanest
   path: cherry-pick the 6 UI commits onto a fresh branch
   from main rather than merging the divergent state. The 6
   UI commits are:

   ```text
   20207a5 feat(ui): add UI package
   0b65059 feat(ui): add UI server
   1d5d054 feat(ui): add static UI
   553e5ed feat(ui): add karasu ui command
   1ebfe6e docs(ui): add Win95 Karasu runtime mockup spec
   466e55f assets(ui): add Karasu sprite definitions v1
   ```

2. Once those six commits sit cleanly on top of current main
   (with all the chunk 4c metadata fields available), audit
   the UI surface against the design docs:

   ```text
   docs/ui/phase-ui-design.md         (already on main)
   docs/ui/ui-1-layout.md             (already on main)
   docs/ui/ui-1-runtime-plan.md       (already on main)
   docs/ui/karasu-win95-runtime-mockup.md  (UI branch only)
   ```

3. Identify the gap between the Win95 mockup spec and the
   stub index.html. Prioritise what makes operator value
   first: live timeline + drill-down detail + crow state
   visualisation against the actual bus schema (now that
   ``priority``, ``controller_chain_depth``,
   ``controller_resubmit``, ``github_*`` metadata are all
   stable on the bus).

4. Plan in chunks ≤400 LOC each, same cadence as the backend
   work. Suggested sequence:

   ```text
   chunk UI-1  Cherry-pick the 6 commits onto current main.
               Run pytest. Assert the existing UI server still
               serves events.jsonl correctly with the new
               additive fields.
   chunk UI-2  Win95 layout pass: replace the stub
               index.html with the mockup's panel chrome
               (title bar, sunken panels, button surfaces).
               Static assets only; behaviour unchanged.
   chunk UI-3  Live Map view: render the five-domain graph
               (User / Karasu / Claude / Codex / GitHub)
               with the crow as the in-flight message. Use
               the existing /api/events feed; no schema
               change.
   chunk UI-4  Detail panel: drill-down on an event shows
               the full bus event JSON, including the
               new chunk-4c fields (priority,
               controller_chain_depth, github_* metadata).
   chunk UI-5  Tests for the UI server (HTTP-level,
               not browser). Pin /api/events shape against
               the current bus schema so a future schema
               change surfaces here.
   chunk UI-6+  Push notifications, offline (service worker),
                trust management UI, scar browse/revoke per
                README Fase 3. These are larger and likely
                each needs its own design pass.
   ```

5. Continue using ChatGPT as auditor on each PR (the cadence
   that kept REQUERIDO churn low this session).

### Operational note

Controlled dogfood of chunk 4c on a real GitHub PR with
``trust_level=1`` requires the operator's computer
(``karasu serve`` long-running + GitHub webhook + bus
monitoring). Operator targets Monday. NOT blocking the UI
work — they are independent.

## Decisions made this session

```text
1. Bundle three NICE-TO-HAVE from PR #55 audit into a
   single hardening PR (#56) rather than open three
   follow-ups. Reason: history stays tight; the changes
   share scope (PromptBuilder hardening); audit cycle is
   one round. Discarded: three separate PRs.

2. F-CAP-5 walk ceiling is independent of cycle detection
   (visited_set + MAX_CHAIN_WALK_DEPTH=64). Reason: even
   with F-CAP-2 in place, untrusted producers can craft
   forged-deep acyclic lineage that a cycle-only check
   would miss. Two layered defences are cheap and orthogonal.
   Discarded: a single defence (cycle-only or
   ceiling-only).

3. Eviction policy: insertion-order oldest. Reason: simpler
   than last-touched (no per-access bookkeeping); matches
   F-WH-10 ring shape; one explicit choice per the round-2
   NICE-TO-HAVE on PR #53. Discarded: the
   "oldest or last-touched" alternative listed in the
   design doc.

4. fetch_card returns raw JSON dict, not a reconstructed
   AgentCard dataclass. Reason: the wire format is
   camelCase and the dataclass is snake_case; reconstruction
   would force a second mapping that nothing today consumes.
   Discarded: AgentCard.from_dict.

5. fetch_card timeout <= 0 → ValueError. Reason: an operator
   typing --timeout 0 thinking it means "no timeout" would
   otherwise get urllib's silently-hanging fetch behaviour.
   Discarded: passing through urllib's default.

6. F-HANDOFF-6 path probe runs at prompt-build time, not at
   dispatch time or at receive time. Reason: prompt-build is
   the last point before context reaches the model; the same
   call site already enforces F-HANDOFF-1 / F-HANDOFF-5. The
   probe is injectable so a git-tree-aware variant can swap
   in later. Discarded: dispatch-time / receive-time probes.

7. F-HANDOFF-6 metadata-only branch keeps body fenced +
   capped. Reason: a force-pushed-away path is exactly when
   the comment author's input is most suspect (chain
   reordering, branch deletion as attack surface).
   Weakening F-HANDOFF-1 / F-HANDOFF-5 there would be the
   wrong direction. Discarded: drop the body in the
   metadata-only branch.

8. Persist EFFECTIVE priority (post-override) on
   agent_response.data, not the original. Reason: the
   audit follow-up is about knowing what the adapter
   actually saw; the pre-override value lives on the
   originating file_change already. Discarded: persist both.

9. UI is the next session's work, not this one. Reason:
   different shape (TS / React / SW vs. Python / pytest);
   operator is on mobile and lacks the dev environment.
   The UI parallel branch already has scaffolding to pick
   up from. Discarded: starting UI from scratch in this
   session.
```

## Artifacts left behind

```text
Repo:
  - PRs merged this session: #57 #58 #59 #60 (all squashed).
  - Issue #47 closed (auto, via #57).
  - Phase 3+ archive (issue #5) effectively closed; remaining
    items are operational (dogfood) or speculative.
  - Branch feat/ui-1-runtime (origin) — pre-existing,
    untouched this session, ready for the next pickup.

Operator's machine:
  - No artifacts changed. Operator has been on mobile.

External:
  - none.
```

## Lessons learned

1. **Bundling round-1 NICE-TO-HAVE before merge keeps audit
   churn down.** When the auditor approves merge but flags
   correctness-adjacent NICE-TO-HAVE (PR #58 query/fragment
   handling, PR #56 docstring drift, PR #59 memory drift),
   absorbing on the same branch in a focused commit is
   cheaper than opening a follow-up PR. The auditor gets a
   tighter signal-to-noise on subsequent rounds.

2. **Memory drift surfaces in audits.** Twice this session
   (PR #56 docstring, PR #59 current-state.md) the auditor
   caught text that was correct at write time but stale
   after a recent merge. Lesson: re-read recently-touched
   doc / docstring / comment text before submitting a PR
   for re-audit, especially the ones that summarise
   "current state".

3. **Layered defences against untrusted producers.** F-CAP-5
   (cycle + ceiling) is the canonical example: even when
   another defence (F-CAP-2 source check) seems to make a
   given vector unreachable, untrusted lineage can still
   force expensive walks via constructions that satisfy the
   first defence. Independence of layers is a design
   property worth pinning.

4. **`inspect.getsource` is a viable contract-pin for
   wiring boundaries.** Used twice: once for
   ``cmd_watch / cmd_serve / cmd_hook`` banner wiring (PR
   #54), and conceptually for any "X must be called from Y
   only" boundary. Cheaper than full integration tests when
   the alternative is stubbing process-blocking entry
   points.

5. **README phases vs. internal phases need realignment.**
   Internal phase numbering (Phase 1A/B/C, Phase 2, Phase 3,
   Phase 3+) does NOT match README phase numbering (Fase 1
   = local + telegram, Fase 2 = git + a2a, Fase 3 = PWA).
   Operator asked "how much is left" and the answer
   depended on which numbering scheme. Lesson: when phase
   work concludes, update both the internal session memory
   AND the README/roadmap so future operators (or future-us)
   read consistent numbering.

## Next step pointer

```text
See ../next-session.md — pointed at:
  - Pick up UI work on a fresh branch derived from
    feat/ui-1-runtime (cherry-picked onto current main).
  - Six commits to cherry-pick listed in the bitácora.
  - Win95 mockup spec is the design north star;
    docs/ui/karasu-win95-runtime-mockup.md.
  - ChatGPT continues as auditor only; Claude Code
    drives the UI implementation per operator request.
  - Controlled dogfood of chunk 4c deferred to operator's
    computer time (Monday target).
```
