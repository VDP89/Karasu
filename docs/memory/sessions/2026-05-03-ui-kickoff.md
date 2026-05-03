# 2026-05-03 — UI surface kickoff (UI-0 brief + UI-1 rebase)

This session opened the README-Fase-3 (PWA + Advanced) work
that the previous session had teed up. Two PRs merged: UI-0
(design brief seal) and UI-1 (rebase + projection expansion).
The visual direction is now committed to main; the next
chunk (UI-2 design system primitives) is teed up for when
the operator has a computer with a browser available
(Monday target).

## Operator + environment

```text
Operator:           VDP89 (mobile, in transit)
Date:               2026-05-03
OS:                 Linux 6.18.5 (sandboxed Claude Code)
Shell:              bash
Python:             3 (project venv)
Repo:               /home/user/Karasu-
Browser available:  NO (apt-locked sandbox; Playwright
                    Chromium download blocked by upstream
                    registry).
```

## Goal

Open the UI surface work that the previous session's
handoff plan had pointed at. The operator was dissatisfied
with prior ChatGPT-driven UI work on the parallel branch
``feat/ui-1-runtime`` and asked Claude Code to take over the
implementation. ChatGPT continues as auditor only.

The session's specific goal: seal a design direction that
makes the UI legible as "hand-built" within the first 5
seconds of looking at it (operator's words: "guau, ¿quién
hizo esto?"), then bring the parallel-branch scaffold
forward onto current main as a clean foundation for the
chunks that introduce real visible state.

## What this session shipped

```text
PR #62  docs(ui): UI-0 design brief — visual direction sealed
        Doc-only seal of the visual direction.
        Operator-confirmed decisions A-E (rojo cuervo accent,
        Inter Display + JetBrains Mono fonts both SIL OFL 1.1
        self-hosted, archive Win95 mockup, UI-0 explicit).
        Tech stack: TypeScript strict + Vite + vanilla CSS
        variables. No React, no Tailwind, no component library.
        Full design system in §5: color tokens with WCAG AA-
        verified contrast ratios, typography scale, spacing,
        radius / shadow / focus-ring / z-index named layers,
        motion tiers with reduced-motion clamp, the crow
        specification.
        Roadmap UI-1..UI-9 + UI-10+ deferred (out of brief
        scope).
        Audit cadence change: every UI-N PR (UI-1+) MUST ship
        screenshots; motion-touching PRs (UI-5, UI-6, future)
        ALSO ship a ≤5s .webm.

PR #63  feat(ui): UI-1 rebase — bring UI scaffold to current
        main + expand projection
        5 commits cherry-picked from feat/ui-1-runtime onto
        main (with original Victor Del Puerto attribution
        preserved); the 6th was a placeholder stub
        (<REPLACE_WITH_MODIFIED_CONTENT>) and was replaced by
        a fresh cmd_ui written against current main.
        server.py projection expanded to surface the chunk-4c
        bus schema (priority, controller_chain_depth,
        controller_resubmit, resubmit_origin, github_*,
        agent, status, trust_level, correlates,
        classification, requires_human).
        Defensive additions: ?limit clamped via parse_qs,
        path-traversal guard on /assets/*, HTTP request log
        silenced.
        Win95 mockup archived to docs/ui/explorations/ with
        a README documenting the policy.
        scripts/ui_screenshots.py shipped (Playwright-based,
        operator-runnable on a machine with a browser).
        docs/ui/screenshots/UI-1-rebase/README.md with formal
        ONE-TIME screenshot waiver explicitly stating UI-2+
        does NOT inherit it.
```

## Audit cycles

```text
PR #62 round 1  NO APROBADO
                REQUERIDO 1: Lighthouse/SEO contradiction
                  (UI-9 said SEO ≥90; DoD said Lighthouse
                  ≥95 on the four headline metrics, which
                  includes SEO).
                4 NICE-TO-HAVE: accent contrast claim,
                  missing primitive tokens (radius / shadow /
                  focus / z-index), video scope, browser
                  matrix, --error alias.
        round 2  All absorbed in commit ebcaceb. APROBADO.
                Two NICE-TO-HAVE deferred (lint script for
                outline:none → UI-2; document Lighthouse
                runner → UI-9).

PR #63 round 1  NO APROBADO
                REQUERIDO 1: screenshots or formal waiver.
                REQUERIDO 2: possible projection bug
                  (dispatch / response might live under
                  data).
                3 NICE-TO-HAVE: parse_qs, config-aware
                  EVENT_LOG, URL-encoded path-traversal
                  test.
        round 2  REQUERIDO 1 absorbed (formal one-time
                  waiver in screenshots README).
                REQUERIDO 2 was a false positive — verified
                  against the Event dataclass at
                  src/karasu/eventbus/jsonl_bus.py: dispatch
                  / response ARE top-level fields. Pushed
                  back with evidence; round-2 audit
                  accepted.
                NICE-TO-HAVE 1 (parse_qs) absorbed.
                NICE-TO-HAVE 2 / 3 deferred to UI-9.
                APROBADO.
```

## Findings + real-time debugging

### Stub commit on the parallel branch

The 6th UI commit on ``feat/ui-1-runtime`` (553e5ed
"feat(ui): add karasu ui command") had as its entire
``src/karasu/__main__.py`` content the literal string
``<REPLACE_WITH_MODIFIED_CONTENT>``. Cherry-pick attempt
failed with a conflict pointing at that stub. Diagnosed by
``git show 553e5ed:src/karasu/__main__.py``. Aborted the
cherry-pick, picked the 5 real commits in chronological
order, then wrote a fresh ``cmd_ui`` against current main.

Lesson: when cherry-picking from a long-divergent branch,
verify each commit's actual content (not just metadata) is
real before trusting the metadata.

### Round-1 false positive on projection shape

Round 1 of PR #63 audit flagged that the projection might be
reading ``dispatch`` / ``response`` from the wrong level.
The auditor's specific concern: "en el patrón anterior los
eventos suelen tener data.dispatch / data.response dentro
del payload". Verified against
``src/karasu/eventbus/jsonl_bus.py`` lines 26-46: the
``Event`` dataclass declares ``data``, ``dispatch``,
``response`` as siblings (top-level fields), not nested.
``asdict(event)`` produces ``{"type":..., "source":...,
"data":..., "dispatch":..., "response":..., "id":...,
"timestamp":...}``. The smoke test in the round-1 PR proved
this end-to-end (``evt002`` projected ``agent``,
``trust_level``, ``status`` correctly). Pushed back in
round 2 with the dataclass excerpt + smoke test output.
Round 2 accepted.

Lesson: when an auditor flags a structural concern, verify
against the canonical schema definition (the dataclass /
the type) before either fixing or pushing back. Saves at
least one round.

### Sandbox lacked a browser for screenshots

UI-0 mandates screenshots for every UI-N PR. The sandbox
running this session had no Chromium / Chrome / Firefox
installed, ``apt`` repos were broken (PPAs no longer
signed), and Playwright's Chromium download was blocked
by the upstream registry. Three options weighed:

```text
A) Block UI-1 until the sandbox can capture screenshots.
B) Use text-only evidence (curl outputs).
C) Combine: text evidence in-PR + ship the capture script
   for the operator + waive for UI-1 specifically because
   no new visible state was actually introduced.
```

Picked C. The waiver is explicit, scoped to UI-1 only, and
the README pins that UI-2+ does NOT inherit it. The
operator running ``python scripts/ui_screenshots.py
UI-1-rebase`` on their machine can later commit the PNGs;
the waiver text remains for record.

### parse_qs vs split-on-&

Round 2 of PR #63 absorbed the NICE-TO-HAVE swap. The
manual ``query.split("&")`` worked for the simple case but
broke for percent-encoded values, repeated keys, and
empty-value cases. ``urllib.parse.parse_qs`` handles all of
that correctly. Verified end-to-end with ``?limit=2``,
``?limit=0``, ``?limit=abc``, ``?limit=10000``: clamps and
fallbacks behave as documented.

## Decisions made this session

```text
1. Vanilla TS + custom CSS, NOT React + Tailwind. Reason:
   for a surface whose first job is to "look hand-set",
   giving up the framework tax buys exactly that quality at
   the price of ~10% more keystrokes per primitive. One
   person can maintain ~5K LOC of vanilla TS + CSS without
   strain. Discarded React + Tailwind (productive, but
   imprints framework voice on everything).

2. Single accent color (rojo cuervo #d54834), error and
   identity SHARE color, with --error: var(--accent) alias
   for components that want the semantic name. Reason: the
   accent is the crow's eye; conflating error with identity
   is deliberate. The alias lets a future operator split
   error from accent with one token swap if dogfood demands
   it.

3. Inter Display + JetBrains Mono, both SIL OFL 1.1
   self-hosted. Reason: free, premium-quality, license fits
   self-hosting. Discarded Söhne (paid) and Berkeley Mono
   (paid) as future swaps if the project commercialises.

4. Win95 mockup archived to docs/ui/explorations/ with a
   README, NOT deleted. Reason: decision archaeology is the
   point. Recognising the prior work without continuing it
   keeps the trail honest. Discarded "delete entirely".

5. Screenshot capture is the operator's responsibility on
   their machine for now (via scripts/ui_screenshots.py),
   not a sandbox CI job. Reason: simpler; matches the
   operator-in-the-loop cadence we already have. If the
   sandbox ever gets a browser, the script runs there too —
   no code change needed.

6. UI-1 ONE-TIME screenshot waiver, NOT a permanent policy.
   Reason: UI-1 introduces zero new visible state (only
   text-shape JSON projection changes), so screenshots
   would show the same stub HTML as the cherry-picked
   commits already showed. UI-2 onward MUST ship real PNGs.

7. Cherry-pick + replace-the-stub strategy, NOT
   re-implement everything from scratch. Reason: 5 of 6
   commits had real content from the operator's prior work;
   preserving author attribution is the right thing to do.
   Only the stub (which had placeholder content) was
   re-written; that commit's authorship goes to me.

8. Push back on REQUERIDO 2 of PR #63 round 1, with
   evidence, instead of "absorbing" a non-bug. Reason: the
   audit was technically wrong about the bus event shape;
   accepting the finding would have meant either no
   change (dishonest) or breaking the projection (worse).
   Pushed back with the dataclass excerpt; round 2
   accepted. The cadence permits push-back when warranted.
```

## Artifacts left behind

```text
Repo:
  - PRs merged this session: #62 #63 (both squashed).
  - New paths on main:
      docs/ui/ui-0-design-brief.md
      docs/ui/explorations/karasu-win95-runtime-mockup.md
      docs/ui/explorations/README.md
      docs/ui/screenshots/UI-1-rebase/README.md
      scripts/ui_screenshots.py
      src/karasu/ui/__init__.py
      src/karasu/ui/server.py
      src/karasu/ui/static/index.html
      src/karasu/ui/static/assets/   (empty until UI-2 lands
                                      fonts and sprites)
  - New CLI subcommand: karasu ui [--host H] [--port P]

Operator's machine:
  - No artifacts changed. Operator on mobile.
  - Operator targets Monday for the next session (computer +
    browser + Playwright local capture).

External:
  - none.
```

## Lessons learned

1. **A doc-only "brief" PR is the right shape for a design
   pivot.** Two audit rounds of UI-0 cost ~30 minutes total
   and surfaced a real contradiction (Lighthouse / SEO) plus
   a real shape gap (radius / shadow / focus / z-index
   tokens). Shipping any of UI-1 onwards without the brief
   sealed first would have built against unstable
   foundations.

2. **Verify cherry-pick targets, not just metadata.** The
   stub commit on the parallel branch had real metadata
   (commit message, author, date) but placeholder content.
   ``git log`` would never have shown that. ``git show
   <sha>:<path>`` is the cheap check.

3. **Push back on audits when warranted, with evidence.**
   The round-1 projection-shape concern was a false
   positive. Accepting it would have meant either a no-op
   change or breaking the projection. Pushed back with the
   dataclass excerpt + smoke-test output; round 2 accepted.
   This keeps the audit cadence honest in both directions.

4. **One-time waivers are useful when scoped tightly.** UI-1
   genuinely had no new visible state; mandating screenshots
   would have been theatre. The waiver is explicit, scoped,
   and the README pins that no future chunk inherits it.

5. **Frontend audit cadence needs different evidence than
   backend audit.** Diff alone isn't enough. The
   screenshots-mandatory + video-for-motion policy from
   UI-0 §7 is a structural change, not a polish item.

## Next step pointer

```text
See ../next-session.md — pointed at:
  - UI-2 design system primitives + tokens page
    (/design-system) when operator is on a computer with
    a browser. UI-2 introduces the FIRST chunk where new
    visible state lands, so screenshots are mandatory and
    the waiver from UI-1 does NOT extend.
  - Font assets to download (Inter Display + JetBrains
    Mono woff2) — operator runs scripts/ui_fetch_fonts.sh
    locally if/when shipped, OR I download in-sandbox if
    the sandbox has internet to fetch from rsms.me /
    JetBrains.
  - Operator targets Monday.
```
