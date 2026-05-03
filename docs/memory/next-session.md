# Next Session Entry Point

## Goal

**UI-5 — the crow. Sprite asset finalised + state animations.**

Per UI-0 design brief §6, UI-5 is *"the chunk that makes the
'guau' happen"*. The crow stops being a vector silhouette
placeholder and becomes the canonical asset of the surface.
Idle breathing in the header, state colour changes against
real bus events.

UI-5 is the only chunk besides UI-6 (Live Map) that UI-0 §7
flags as motion-introducing. It ships a `.webm` recording in
the same PR — **no exception** per the binding rule ChatGPT
pinned across the UI-3 and UI-4 audits.

## Binding constraints from prior reviews

Two binding rules carried forward, both pinned by ChatGPT in
review verdicts. Treat them as P0 if violated, not as
guidance.

```text
1. .webm REQUIRED, no exception (ChatGPT UI-3 audit pin).
   The crow stops being placeholder/ambient and becomes the
   principal visual asset. Static PNGs alone do NOT close
   the audit. Recording must be ≤5 s, <500 KB, exercise the
   relevant transitions (idle → processing → waiting →
   error → idle), and live under
   docs/ui/recordings/UI-5-crow.webm.

2. "El crow puede tener vida; la superficie no puede perder
   calma" (ChatGPT UI-4 audit pin). The crow can carry
   personality through SVG character + state animations,
   but the surrounding shell (header chrome, timeline,
   footer) must NOT inherit any of that personality. The
   surface stays editorial; only the crow earns motion.
```

## What ships in UI-5

```text
src/karasu/ui/static/assets/crow/
  crow.svg                    NEW canonical crow asset.
                              Per UI-0 §5.6: SVG, monochrome,
                              single path where possible.
                              Sized to render at 16 / 24 /
                              48 / 96 px without anti-aliasing
                              jitter; uses currentColor so
                              CSS state classes recolour the
                              glyph in place.

src/karasu/ui/static/css/crow.css   NEW.
  - .crow base sizing + currentColor binding.
  - Idle ambient breathing: 1px translate-Y over 4 s,
    ease-mag both ways. Subliminal — the crow looks alive
    even at rest.
  - .crow.processing: --accent + slow pulse (UI-0 §5.6 says
    "slow pulse"; lean a 1.6 s ease-out scale 1.00 → 1.04
    cycle, infinite).
  - .crow.waiting: --warn + asymmetric tilt (a small
    rotate of 4° held with no return — the crow leans the
    way the brief describes).
  - .crow.error: --accent + sharp shake, single beat
    (translateX -2 / +2 / 0 over 240 ms ease-mag, NOT
    looping — the operator sees one decisive beat).
  - prefers-reduced-motion: every keyframe animation
    clamped to 1 ms via reset.css (the chromatic whitelist
    keeps colour transitions; transform stops). UI-2's
    contract holds.

src/karasu/ui/static/index.html  (extension)
  - Replaces the placeholder ellipse+circle+triangles
    silhouette with the canonical SVG (inline <svg> or
    <img src> referencing the asset; lean: inline so
    currentColor works without css feature detection).
  - The hero crow on the empty state shares the same path,
    just at 96 px and with the ambient keyframe attached.
  - Header glyph keeps the same currentColor recolouring
    contract from UI-3; UI-5 just swaps the path data.

scripts/ui_screenshots.py  (extension)
  - UI-5 capture plan with PNGs for each state:
      00-crow-idle.png         /, populated bus, idle crow
      01-crow-processing.png   /, populated bus, processing
      02-crow-waiting.png      /, populated bus, waiting
      03-crow-error.png        /, populated bus, error
                                (capture mid-shake or last
                                 frame, doc both)
      04-empty-state-with-canonical-crow.png
                                /, empty bus, hero crow
                                rendered with the new asset
  - The crow state is derived by /api/health from the bus
    tail. To exercise the four states deterministically the
    capture plan needs synthetic events tailored to each
    state precedence path (see _crow_state in server.py:
    error > waiting > processing > idle). Add a per-capture
    `seed_events` hook — a list of synthetic events that
    overrides the default 4-event corpus — so each state
    capture seeds the precedence-winning event tail.

scripts/ui_record.py  (NEW or fold into ui_screenshots)
  - Records a Playwright video (.webm) of the state
    transitions. ≤5 s, <500 KB target. Sequence:
      seed idle → wait 1 s
      seed processing → wait 1 s
      seed waiting → wait 1 s
      seed error → wait 1 s
      seed idle (recovery) → wait 1 s
  - Output: docs/ui/recordings/UI-5-crow.webm.
  - Lean: extend ui_screenshots.py with a `record_video`
    flag rather than spawning a second script. The
    Playwright context API supports `record_video_dir`
    and `record_video_size`; rename the slug-named output
    to UI-5-crow.webm post-hoc.

docs/ui/screenshots/UI-5-crow/  (NEW)
  - The 5 PNGs.
  - README per the UI-2/UI-3/UI-4 pattern, plus a "what to
    look at in the .webm" section pointing the auditor at
    the four transitions and the recovery beat.

docs/ui/recordings/UI-5-crow.webm  (NEW)
  - The recording.
  - <500 KB. If the raw Playwright output exceeds the
    budget, transcode with ffmpeg using the codec already
    referenced in UI-0 §7; document the ffmpeg invocation
    in the screenshots README so the next motion-introducing
    chunk can reproduce.

docs/ui/assets/karasu_sprites_spec.md  (UPDATE)
  - The current placeholder file says "32x32 16-bit style,
    no anti-aliasing". UI-0 §5.6 says "SVG, monochrome,
    single path where possible". The two are not
    compatible; UI-5 reconciles by rewriting the spec file
    to describe the SVG production decisions made in this
    chunk (path source, viewBox, the four state classes,
    the keyframe specs). Anchor the rewrite to UI-0 §5.6 —
    the brief is the contract.
```

## Surface contract — must respect

```text
- UI = read-only sink. UI-5 only adds GET assets and CSS;
  no projection change, no bus mutation.
- No new bus event types. The crow state lives entirely on
  the client; it derives from /api/health, which is
  unchanged.
- No new runtime dependency. Stdlib + the assets shipped
  in UI-2 / UI-4. Playwright stays dev-only (already used
  for screenshots; UI-5 adds video).
- No build step. The SVG is a static asset; the CSS is a
  static file under static/css/.
- Frozen contracts: AgentResponse, F3, F7, F8, surface=sink,
  single-worker invariant, scar=stored-correction-only,
  I-001..I-006, TriggerSource Protocol, bus event schema —
  none touched.
- The empty-state hero from UI-3 stays the first impression
  on a silent bus; UI-5 only changes the SVG path data and
  the keyframe binding.
```

## Open questions to resolve while implementing

```text
1. SVG aesthetic: clean vector vs pixel-art-evoking?
   docs/ui/assets/karasu_sprites_spec.md says "32x32 16-bit
   style, no anti-aliasing"; UI-0 §5.6 says "SVG, monochrome,
   single path where possible". The two read as conflicting
   intent. Lean: §5.6 wins (clean vector, single or two
   paths). The sprites spec gets rewritten to match. If the
   reviewer wants the pixel-art route instead, the SVG
   redraw is contained.

2. Inline SVG vs <img src=...>. currentColor needs the SVG
   to be in the same DOM as the styled ancestor, which
   means inline. Lean: inline. <img> with the asset URL
   would still load fine but loses the recolouring path.

3. Single asset vs per-state assets. The brief leans single
   path (§5.6). State changes are colour + transform, not
   shape morphs. Lean: one SVG, four state classes that
   apply colour + keyframe. (If a state genuinely needs a
   shape change later — say a "fly" state for UI-6 — that's
   when a second asset enters.)

4. Pulse / shake / tilt magnitudes. The brief specifies
   directions (slow pulse, asymmetric tilt, sharp shake)
   but not exact values. Lean: small. 1.04× scale on
   processing pulse, 4° tilt on waiting, ±2 px shake on
   error. The UI-4 review's "the crow can have life; the
   surface cannot lose calm" applies here in spades — go
   smaller than feels exciting in the editor; the audit
   will catch over-animated.

5. .webm size budget. 500 KB cap. Playwright's default
   webm encoder is verbose; if the recording overshoots,
   re-encode with ffmpeg (libvpx-vp9, low CRF) before
   commit.
```

## Audit cadence reminder

Per UI-0 §7 + the binding pins:

```text
1. Real PNG screenshots under docs/ui/screenshots/UI-5-crow/
   for every visible state.
2. .webm recording at docs/ui/recordings/UI-5-crow.webm
   (≤5 s, <500 KB). REQUIRED, no exception.
3. A "what to look at" note covering type/state mapping,
   keyframe magnitudes, and reduced-motion behaviour.
4. The diff itself.
5. The audit prompt for ChatGPT.
6. Editorial check: "el crow puede tener vida; la superficie
   no puede perder calma" — the auditor is invited to
   scrutinise that the surrounding shell did NOT pick up any
   crow personality.
```

## Pre-reads for next session

```text
1. docs/ui/ui-0-design-brief.md §5.6 (The Crow) + §6 (UI-5
   roadmap entry) + §5.5 (motion durations + reduced-motion
   contract).
2. docs/ui/assets/karasu_sprites_spec.md — placeholder file
   that UI-5 will rewrite to match the SVG production
   decisions.
3. src/karasu/ui/static/index.html — current placeholder
   silhouette (ellipse + circle + 2 triangles); UI-5 swaps
   the path data inline.
4. src/karasu/ui/static/css/reset.css — the
   prefers-reduced-motion chromatic whitelist; UI-5 keyframes
   land under this contract.
5. src/karasu/ui/server.py — `_crow_state` precedence (error
   > waiting > processing > idle); UI-5 capture plan needs
   the precedence-winning seed for each state PNG.
6. docs/memory/sessions/ — any prior dogfood notes about
   how the operator perceives the current placeholder; UI-5
   delivers the "guau" moment the brief promises.
```

## Chunk size estimate

```text
Code:       ~250 LOC (SVG inline + crow.css + index.html
            extension + ui_screenshots video extension)
Assets:     1 SVG asset (small), 5 PNGs + 1 webm
Docs:       ~100 LOC (screenshots README + sprites_spec
            rewrite)
Tests:      none in UI-5; UI-9 owns the test chunk.
Total:      under the 400 LOC code budget.
```

## Do NOT do yet

```text
- Do NOT introduce React / Tailwind / any framework. UI-0
  §4 still binding.
- Do NOT extend the bus schema for crow state. The state
  derives from /api/health, which derives from the existing
  projection; no new fields needed.
- Do NOT animate anything outside the crow. Header chrome,
  timeline rows, footer cells, focus rings — all static
  except for the colour transitions UI-2 already covers.
  ("La superficie no puede perder calma" applies here
  literally.)
- Do NOT loop the error shake. UI-0 §5.6: single beat. A
  loop reads as alarm fatigue; the design wants one
  decisive beat per error.
- Do NOT skip the .webm. Static PNGs are necessary but
  not sufficient for UI-5.
- Do NOT introduce the Live Map (UI-6) flight path. UI-5
  ships idle / processing / waiting / error in the header
  and hero slots only. Flight is UI-6's job.
- Do NOT introduce a build step. The SVG and CSS ship
  static.
- Do NOT colour-code event types in the timeline (still
  binding from UI-4). Chroma stays reserved for the crow
  state, --accent, --error.
```

## Anchor for the previous sessions

- UI-4 (event timeline as editorial beats) merged 2026-05-03
  via PR #72 (`13e6270`). APPROVED on the first round.
  ChatGPT added the binding rule "el crow puede tener vida;
  la superficie no puede perder calma" for UI-5.
- UI-3 (application shell + `/api/meta`) merged 2026-05-03
  via PR #70 (`a67d729`). APPROVED on the first round.
  ChatGPT pinned the `.webm`-without-exception rule for
  UI-5 there.
- 392/394 pytest on Windows local. The two failures
  (`test_git_probe::test_git_tree_path_exists_passes_cwd_through`
  and `test_ui_server::test_valid_asset_under_static_dir_is_served`)
  also fail on `main` — preexisting Windows CRLF / cwd
  quirks. CI Linux green.
- Karasu HEAD: `13e6270` at session start. UI-5 branches
  off this commit (or the docs(memory) sync that lands
  before it; both are fast-forward).
