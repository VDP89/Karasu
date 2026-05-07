# Next Session Entry Point

## Status: Phase 4 (deployed surfaces) — UNSCOPED

main HEAD: `e5c89a7` (UI-12c code chunk merged, 2026-05-07).
0 PRs open. 0 branches open.

UI-12c code closed cleanly: 6 logical commits + 2 round-1
follow-up commits + 1 visuals commit = 9 commits squash-
merged into `e5c89a7`. ~5500 LOC code + tests + docs. Codex
audit closed at round 2 of 5 (round 1 CHANGES-REQ 2 P1 +
visuals binding → all closed in-branch; round 2 APPROVED
clean). The 20 §11.6 pins from the UI-12c brief (`0c2291d`,
PR #104) are now binding implementation contracts in `main`.

**Phase 3 EXIT CRITERIA CLOSED.** Telegram is no longer the
only push channel; the PWA push delivery surface (footer
affordance + modal + VAPID-signed RFC 8291 aes128gcm POSTs
to FCM/APNs/Mozilla autopush) is the operator-facing
notification path. The prototype is complete.

## Context recap (UI-12c code session 2026-05-06 → 2026-05-07)

1. **PR #105** — UI-12c code chunk. 9 commits squash-merged:
   1. `8a534f3` feat(ui-12c): classifier + cross-process
      lockfile + seed_vapid (877 LOC, 31 tests)
   2. `8cdf268` feat(ui-12c): cryptography modules — VAPID
      keygen + JWT + RFC 8291 enc (1337 LOC, 44 tests)
   3. `e9c649f` feat(ui-12c): three-layer rate limit + race
      protection (815 LOC, 17 tests)
   4. `c8ee243` feat(ui-12c): HTTP delivery + 410/404 prune
      + transport privacy (1133 LOC, 19 tests)
   5. `9ac53b4` feat(ui-12c): PushEmit TriggerSource — bus
      subscriber + fan-out (734 LOC, 11 tests)
   6. `6697c81` feat(ui-12c): wire cmd_watch + import scope
      guard + cross-process test + docs (534 LOC, 6 tests)
   7. `92353b0` fix(ui-12c): round-1 audit follow-ups —
      2 P1 closed in-branch (5 regression tests)
   8. `6389b77` docs(ui-12c): visual artefacts — 3 PNGs +
      1 .webm (193 KB)
   9. (squash merge commit `e5c89a7`)

   - Round 1 audit: CHANGES-REQ (2 P1 + 1 P1 visuals
     binding). All 3 closed in-branch.
   - Round 2 audit: APPROVED clean.
   - Loop budget: 2/5.
   - Merge: Claude Code lands the merge per
     `feedback_karasu_merge_es_implementer.md`
     (`gh pr merge 105 --squash --delete-branch`).

2. **PR #106** (this PR) — docs/memory sync after UI-12c
   code merge.

## Entry point for THIS session

**Phase 4 — DEPLOYED SURFACES.** The macro brief is unwritten.
Phase 4 lifts the surface from local-only / single-operator
to deployed / multi-operator. References are dispersed
across the UI-10..UI-12c briefs (every "UI-13+" mention)
and need to be consolidated into a Phase 4 macro brief
BEFORE any Phase 4 chunk opens.

### Anticipated Phase 4 scope (non-binding, source citations)

```text
1. Deployed surface — TLS termination, certificate
   provisioning, public hostname, deployment topology.
   Source: docs/local-dogfood.md "UI-13+ deployed surfaces
   earn their own brief covering certificate provisioning
   + auth + multi-operator push fan-out".

2. Multi-operator authorization — login, session
   management, per-operator audit log filtering, trust
   tier scoping.
   Sources:
   - ui-10-design-brief.md §6 "UI-13+: Multi-operator
     surfaces (deployed Karasu, login, authorization
     tiers, audit log filtering). Earns its own brief; out
     of scope here."
   - ui-11-design-brief.md §9 "Multi-operator
     collaboration / per-user trust. UI-13+."

3. Multi-host writer concurrency — the UI-12c §3-G file
   lock is single-filesystem only (fcntl.flock /
   msvcrt.locking semantics over network filesystems are
   not portable). Deployed surfaces with shared storage
   (NFS / multi-instance deployment) need their own
   concurrency contract.
   Source: ui-12c-design-brief.md §9 "Multi-host /
   multi-machine writer concurrency. ... Phase 4 will
   earn its own concurrency contract."

4. A2A peer push fan-out — Karasu instance pushing to
   another Karasu instance (vs the current FCM/APNs/
   Mozilla autopush per-browser push).
   Source: ui-12c-design-brief.md §9 "A2A peer push
   fan-out (Karasu instance pushing to another Karasu
   instance). UI-13+."

5. Push enhancements (post-UI-12c):
   - Per-event push opt-in beyond the closed enum
     {attention, errors, corrections}.
   - Scheduled / quiet-hours / DND beyond OS-level DND.
   - Push body content beyond the editorial title (richer
     payloads after dogfood validates the editorial-line
     discipline).
   - VAPID auto-rotation (operator-driven today; UI-12
     §10.4 "Auto-rotation is a UI-13+ concern").
   Source: ui-12c-design-brief.md §9 + ui-12-design-brief.md
   §10.4.

6. Per-category push debounce override via env var
   (KARASU_PUSH_DEBOUNCE_<CATEGORY>_MS). Deferred from
   UI-12c per brief §10.5.

7. Operational hardening from Phase 3 dogfood:
   - F9 missing [job-queue] extra (issue #40) — possible
     fix landed; verify status.
   - F10 drain skip warnings (issue #41).
   - F11 Notepad atomic-write tmp (issue #42).
   These were filed during Phase 3 dogfood but not
   formally closed in the UI-N family. Phase 4 may absorb
   them or split a parallel "Phase 3 hardening" PR.
```

### Recommended next move

Operator decides between two paths:

**Path A — Phase 4 macro brief first (mirrors UI-0).**
A doc-only PR consolidating the references above into a
roadmap, locking in §11.6 pins for the family, picking the
FIRST chunk. Audited by Codex out-of-band per the brief-
before-code lifecycle. Macro briefs typically take 2-4
audit rounds; the family that follows is then sealed.

**Path B — Pick one chunk and earn its chunk brief now.**
e.g. "UI-13: deployed surface TLS + auth scaffolding" or
"UI-13: multi-host file lock (NFS-safe primitive)". The
chunk-level brief earns its own audit; the macro brief
follows later as a retroactive consolidation.

Path A is the established pattern (UI-0 macro brief opened
the UI-1..UI-12c family). Path B trades architectural
seal-up-front for faster first-merge. Operator's call.

### Phase 4 brief lifecycle (whichever path)

Per the brief-before-code pattern (UI-9 audit pin #1,
reaffirmed UI-10 / UI-11 / UI-12 / UI-12b / UI-12c):

```text
1. Implementer drafts the brief as a doc-only PR with
   [NEEDS OPERATOR SIGN-OFF] markers. Inherits the 126
   binding pins from UI-0..UI-12c (52 base + 6 UI-10 +
   12 UI-11 + 16 UI-12 + 16 UI-12b + 4 PR #102 round-2
   forward-carry + 20 UI-12c §11.6) plus any new pins
   carried forward from UI-12c round 1 audit (none — the
   UI-12c P1 fixes were privacy + bootstrap fatal, both
   already covered by the existing pins).
2. Operator reviews + confirms ("avanzar" or per-marker).
3. Implementer entrega the audit prompt copy-paste to the
   operator immediately.
4. Codex audits; verdict ferried back via the operator.
5. In-branch follow-ups; re-audit if round 1 was
   CHANGES-REQUIRED with P0.
6. Brief PR merges BEFORE the first Phase 4 code branch
   opens. Claude Code lands the merge per
   feedback_karasu_merge_es_implementer.md.
```

## Accumulated state

- **126 binding pins inherited** (52 base + 6 UI-10 §0.5 +
  12 UI-11 §11.6 + 16 UI-12 §11.6 + 16 UI-12b §11.6 + 4
  PR #102 round-2 forward-carry + 20 UI-12c §11.6).
- **Test suite on main**: 731 passed + 5 skipped + 2
  pre-existing Windows quirks (CRLF + cwd path; documented
  as NOT regressions; verified via stash + retest on main
  during UI-12c work).
- **Lighthouse contract** unchanged from UI-9.1 baseline.
- **Loop budget tracker (last 3 chunks)**:
  - UI-12 brief: 4/5 consumed.
  - UI-12a: 2/5 consumed.
  - UI-12b brief: 3/5 consumed; UI-12b code: 1/5 consumed.
  - UI-12c brief: 4/5 consumed; UI-12c code: 2/5 consumed.

## Open issues

```text
F9  missing [job-queue] extra        (#40, Phase 3 dogfood)
F10 drain skip warnings              (#41, Phase 3 dogfood)
F11 Notepad atomic-write tmp         (#42, Phase 3 dogfood)
```

These three were filed during the Phase 3 live dogfood
(2026-05-02) and are NOT regressions from Phase 3 chunks
3a/3b/3c. They are operational hardening candidates for
Phase 4.

## Operator-side TODOs

```text
- Rename repo: GitHub -> Settings -> Repository name -> "Karasu"
  (current name "Karasu-" is a typo).
- Uninstall ChatGPT Codex Connector App from repo if still
  installed (PR #67 retired working agreement; physical
  uninstall closes the loop).
```

## Phase / prototype status

```text
Phase 1 — Local daemon + Telegram         ✔ CLOSED.
Phase 2 — Git-aware + A2A                 ✔ CLOSED.
Phase 3 — PWA + Advanced                  ✔ CLOSED.
                                            UI-0..UI-12c all
                                            merged. Exit
                                            criteria CLOSED
                                            2026-05-07 by
                                            UI-12c PR #105.
                                            The prototype is
                                            complete.
Phase 4 — Deployed surfaces               ⚠ UNSCOPED.
                                            Macro brief
                                            pending. See
                                            "Entry point for
                                            THIS session"
                                            above.
```
