# Karasu Crow — Asset Spec

> Reconciled in UI-5 against `docs/ui/ui-0-design-brief.md` §5.6.
> The earlier "32×32 pixel-art / 16-bit / no anti-aliasing"
> draft and the mid-PR pixel-art pass are **superseded** by
> the audit-corrected vector approach documented here.

---

## Format

```text
Source asset:    src/karasu/ui/static/assets/crow/crow.svg
Markup:          inline SVG in static/index.html (rect / circle
                 / path elements duplicated so currentColor +
                 state classes work without an external <use>
                 reference)
Format:          SVG, three element types:
                  - 2× <path>      — body silhouette (head +
                                     wing/back), unified under
                                     currentColor
                  - 2× <rect>      — legs in currentColor
                                     (recolour with state)
                  - 1× <circle>    — eye notch, fill matches
                                     canvas (--bg-0 / #0a0a0b)
                                     so it reads as negative
                                     space
viewBox:         0 0 72 72   (OpenMoji native; see Provenance)
shape-rendering: default (vector smooth — no crispEdges)
Aesthetic:       editorial silhouette, vector clean. Karasu is
                 a watchtower; the mark is an instrument, not
                 an app mascot. Pixel-grid + crispEdges was
                 rejected mid-PR (see Provenance § Iteration
                 history).
```

## Display sizes

```text
Header glyph     24 × 24 px  (CSS box; SVG centres inside via
                              preserveAspectRatio="xMidYMid
                              meet" — viewBox 72×72 fits
                              cleanly with no crop)
Empty-state hero 96 × 96 px  (4× the viewBox unit grain →
                              perfectly crisp vector render
                              with full anatomy visible)
```

## Anatomy

The bird is a **perched corvid in profile, facing right**:

```text
head + beak     upper-right quadrant. Beak protrudes up-right
                like a sharp wedge from the head ball.
eye notch       single canvas-coloured dot inside the head.
                Acts as negative space — readable at 96 px,
                a tiny dark spot at 24 px.
body            lower-mass teardrop curving back-left from
                the head, with a flowing wing/back contour
                that ends in a tail wedge at the silhouette's
                back.
legs            two thin verticals hanging from the body
                bottom, central, with a 4-px gap. Anchor
                inside the body fill so neither reads as
                detached.
```

## State classes

The crow is the only element on the surface that earns motion.
Every keyframe lives in `src/karasu/ui/static/css/crow.css`;
nothing else on the page animates beyond the colour and
box-shadow transitions UI-2 already covers.

```text
.crow              base — colour, ambient breathing 4 s loop
                   (translateY 1 px, ease-mag), currentColor.
.crow.processing   --accent + slow pulse: scale 1.04 over 1.6 s,
                   ease-mag, infinite. Composes with the
                   ambient translate via the same transform
                   property (the keyframe declares both).
.crow.waiting      --warn + asymmetric tilt: rotate 0 → 4 deg
                   over 480 ms, ease-out, forwards. The crow
                   leans and HOLDS — no return until the bus
                   state changes.
.crow.error        --accent + sharp shake: translateX
                   0 → -2 → +2 → 0 over 240 ms, ease-mag,
                   single beat (iteration-count: 1, forwards).
                   No loop — looping reads as alarm fatigue.
                   The colour stays accent until the bus state
                   moves on; the keyframe runs once.
```

The eye notch fill (`var(--bg-0)`) is independent of
currentColor: when the body recolours through accent / warn,
the eye remains a hole against the canvas. This is intentional
— the head reads consistent across all four states.

## Reduced motion

`src/karasu/ui/static/css/reset.css` clamps every
`animation-duration` to 1 ms under
`prefers-reduced-motion: reduce` and overrides
`transition-property` to a chromatic whitelist (color,
background-color, border-color, outline-color,
text-decoration-color, fill, stroke, box-shadow). The crow's
transforms therefore stop, but the colour transitions between
states keep their original duration intact. UI-2's contract
carries through unchanged; no crow-specific guard is needed.

## Provenance

The two body silhouette paths are **adapted from OpenMoji
"Black Bird" emoji** (`1F426 200D 2B1B`), licensed under
**Creative Commons Attribution-ShareAlike 4.0 International
(CC-BY-SA 4.0)**. Source:

```text
https://openmoji.org/library/emoji-1F426-200D-2B1B/
```

Karasu's adaptation:

```text
- Strips all stroke-detail elements from the upstream (5
  decorative strokes meant for 72-px emoji rendering — they
  collapse to noise at 24-px header glyph scale).
- Unifies the 2 grey-tone fills under currentColor so the
  silhouette reads as a single editorial mark recolourable
  by state.
- Adds 2 leg <rect> elements anchored inside the body fill.
  Operator-added, not part of upstream.
- Adds 1 eye <circle> filled with the canvas colour, acting
  as negative space. Operator-added, not part of upstream.
```

Karasu is open-source and CC-BY-SA propagates compatibly.
Attribution lives in this file and inside `crow.svg` as a
comment block. Future custom redraws are welcome — the
contract this file documents (4 state classes, keyframe
magnitudes, reduced-motion behaviour, recolourable through
currentColor) survives an asset swap. Only the path / rect /
circle elements change, in both `crow.svg` and the inline
copy in `static/index.html`.

### Iteration history (UI-5 PR #74)

Three asset directions were attempted and rejected before
landing on the OpenMoji-adapted approach:

```text
1. Font Awesome "crow" (CC BY 4.0) vector adaptation.
   Operator rejected: vector-smooth edges read as friendly /
   consumer-app and cut against Karasu's watchtower-as-
   instrument essence.

2. Hand-drawn 16x16 pixel-art with shape-rendering="crispEdges".
   Two passes:
     a. horizontal-low body — operator read as kiwi.
     b. vertical-posture redesign anchored on OpenGameArt
        16x16 raven references. Anatomy was acceptable, but
        Codex pinned a P0 audit finding: pixel-grid +
        crispEdges contradicts UI-0 §5.6 ("SVG, monochrome,
        single path where possible, vector scales beyond")
        and contradicts our own pre-implementation alignment
        ("Vector limpio. Sí. Binding."). Pixel-art read as
        retro game icon, dragging the surface toward
        "tool/game" instead of the Linear/Vercel/Stripe
        Press editorial direction in UI-0.

3. Hand-drawn vector single-path attempts (2 iterations).
   Both failed visually — limited human ability to plan
   complex bezier curves on a coordinate grid without a
   vector editor. Iter 1 looked rocket-shaped; iter 2 looked
   dinosaur-shaped.

Final approach (OpenMoji-adapted) was selected because it:
   - Cumple §5.6 técnicamente (vector, currentColor, scales).
   - Skips the "trace from scratch" trap that ate the prior
     iterations.
   - Has a clean licence trail (CC-BY-SA 4.0, compatible
     with Karasu's open-source posture).
   - Reads as a stylised perched bird, with operator-added
     legs + eye notch closing the gap toward the editorial
     reference (Victor's image 3 — solid silhouette with
     diamond eye + visible legs).
```

## States the crow does NOT carry yet

Per UI-0 §6, the following ship in later chunks:

```text
out-of-signal (UI-8) PWA offline-page easter-egg pose. Same
                     base asset, custom CSS class for any pose
                     change.
```

UI-5 covers idle / processing / waiting / error in the header
and hero slots only. UI-6 adds the flight pose as a SECOND
canonical asset — see below.

---

# Karasu Crow in Flight — UI-6 Asset

> The wings-extended counterpart to `crow.svg`. Painted on the
> Live Map only during a flight transition between two domain
> nodes; swapped back to `crow.svg` when the flight settles.

## Format

```text
Source asset:    src/karasu/ui/static/assets/crow/crow-flight.svg
Markup:          inline SVG in static/index.html (single <path>
                 inside the .live-map container; currentColor
                 propagates from the .crow-flight class set in
                 static/css/map.css)
Format:          SVG, single <path>:
                  - 1× <path>      — full body silhouette with
                                     wings extended + tail
                                     feathers, unified under
                                     currentColor.
                 No <rect>, <circle> or stroke detail. The flight
                 pose carries less anatomical detail than the
                 perched UI-5 asset on purpose — the crow is in
                 motion, the operator's eye reads the silhouette
                 from afar, not the eye notch up close.
viewBox:         0 0 512 512   (game-icons.net native)
shape-rendering: default (vector smooth — no crispEdges)
Aesthetic:       wings extended, asymmetric body curve, tail
                 wedge trailing — a corvid in motion, not in
                 pose. The natural orientation has the head /
                 beak pointing UP; rotation to the path tangent
                 is applied via CSS at render time so the asset
                 can swap without touching JS.
```

## Display sizes

```text
Live Map flight  32 × 32 px  (CSS box; SVG centres inside via
                              the inline viewBox 512×512). The
                              size is small enough to read as a
                              messenger and large enough that the
                              wings-spread silhouette stays
                              legible against the map's hairline
                              edges.
```

## Rotation contract

The flight asset's natural orientation places the head / beak
toward the TOP of the viewBox (path starts at y ≈ 12.6 inside
the 0..512 space and the body radiates downward). The Live Map
needs the beak to lead the path tangent (pin #4: BEAK-LEADING
along path tangent, restrained rotation), so the rendered
rotation is the sum of two pieces:

```text
final rotation = atan2(target.y − source.y, target.x − source.x)
               + asset_offset

asset_offset = 90deg   (compensates the asset's UP-pointing
                        natural orientation; rotating +90°
                        aligns the head to the +x axis)
```

Decoupling the asset offset from the dynamic heading means a
future asset swap (different natural orientation) updates one
CSS variable (`--flight-asset-offset` on `.crow-flight`) instead
of touching JS. The current value is documented in
`static/css/map.css` next to the `.crow-flight` rule.

## Reduced motion

Per UI-2's chromatic whitelist (kept in `static/css/reset.css`),
all transform / opacity / size transitions clamp to 1 ms under
`prefers-reduced-motion: reduce`. The flight transition therefore
becomes an instant relocate from source to target — the crow
still appears at the target position with the source/target
nodes flagged in the accent colour, just without the 600 ms arc.
The state change stays legible without simulating motion the
operator opted out of.

The JS layer in `static/index.html` (`applyFlight`) checks
`window.matchMedia('(prefers-reduced-motion: reduce)').matches`
and uses a single-shot relocate when active; otherwise it kicks
off the two-phase relocate (place at source instantly, force a
layout flush, set target on the next animation frame so the CSS
transition runs).

## Provenance

The single body silhouette path is **adapted from "Crow dive"
by Lorc on Game-icons.net**, licensed under
**Creative Commons Attribution 3.0 (CC BY 3.0)**. Source:

```text
https://game-icons.net/1x1/lorc/crow-dive.html
License: https://creativecommons.org/licenses/by/3.0/
```

Karasu's adaptation:

```text
- Strips the original black background <rect> (Lorc's icon
  ships with a 512×512 black square so the white-on-black
  preview reads on the index page; Karasu needs the silhouette
  alone so it can recolour through currentColor against the
  --bg-1 map canvas).
- Strips the explicit fill="#fff" from the body path so it
  inherits currentColor from the SVG root.
- No path geometry is altered. The dive pose is preserved
  verbatim: wings extended, tail trailing, claws splayed.
- Karasu adds NO new geometry (no eye notch, no extra rect /
  circle), unlike the UI-5 perched asset. At 32-px display
  the perched asset's eye notch reads cleanly because the
  body is folded and dense; the flight asset's silhouette
  is already busy with wing + tail detail, and an additional
  notch would over-detail the in-motion mark.
```

Game-icons.net is open-source and CC BY 3.0 propagates compatibly
with Karasu's posture. Attribution lives in this file and inside
`crow-flight.svg` as a comment block. A swap to a different
flight asset (e.g. a future heraldic-displayed silhouette traced
from a CC0 source) is a path replacement plus an
`--flight-asset-offset` review; the contract documented above
(currentColor recolouring, beak-leading rotation, reduced-motion
snap, single canonical asset) survives the swap.

### Iteration history (UI-6 PR #N)

Six asset directions were evaluated before landing on the
game-icons crow-dive adaptation:

```text
1. Wikimedia Heraldic_Raven.svg (Lokal_Profil, CC BY-SA 2.5)
   500×500. Multi-path with red feet / beak fills + grey eye.
   Wings folded / perched stance — does NOT carry the flight
   pose. Editorially aligned (austere, classical) but unfit for
   the wings-extended contract UI-6 needs.

2. Wikimedia Corneille_essorant.svg (Jacques63, CC BY-SA 4.0)
   580×630. Heraldic "essorant" pose (= in flight, wings
   displayed) — pose correct, license correct. Construction
   wrong: 6 polygons referencing a defs block with extensive
   radial / linear gradients, ~1000 lines of XML, no clean
   currentColor uplift path. Adapting it would mean re-drawing
   the figure to a single fill, defeating the "use a CC asset
   instead of tracing" pattern.

3. Wikimedia White-fronted_tern_volant.svg (Fvasconcellos, CC0)
   131×115 (mm). Wings spread, tern silhouette. License is
   the strongest candidate (CC0 = public domain). Construction
   is 21 paths + 1 ellipse + 1 circle with grey / white / black
   solid fills — adaptable, but the tern's anatomy (marine bird
   with thin pointed wings, hooked beak) reads as not-corvid at
   32 px. UI-6 wants a CROW shape specifically.

4. game-icons.net "raven" (Lorc, CC BY 3.0). 512×512, single
   path. Same construction quality as the chosen asset, but
   wings folded / perched stance — same disqualification as the
   Wikimedia heraldic raven.

5. Wikimedia Coa_Illustration_Elements_Animal_Raven.svg
   (Fox-Davies / Johnston, public domain via 1909 publication).
   Auto-traced line-art line-by-line, perched. Off-brief — the
   feather lines pull the figure toward "naturalist illustration"
   rather than the editorial-instrument silhouette UI-0 §5.6
   pinned.

6. game-icons.net "crow-dive" (Lorc, CC BY 3.0). 512×512,
   single path silhouette, wings AND tail extended,
   recognisable corvid anatomy at 32 px. Adapts cleanly to
   currentColor by stripping the background <rect> and the
   explicit white fill on the body path. CHOSEN.
```

The dive pose carries a slightly more dynamic feel than a
heraldic-displayed silhouette would have. Codex may observe
this on audit; the swap path is the single-CSS-variable +
single-path-replacement contract documented above. If a future
operator-vetted heraldic asset surfaces, this spec stays valid
and only the `crow-flight.svg` body path + provenance block
update.

## Sprite state table — combined

| State        | Asset             | Slot                  | Motion                        |
|--------------|-------------------|-----------------------|-------------------------------|
| idle         | crow.svg          | header glyph + hero   | ambient breathing 4 s loop    |
| processing   | crow.svg          | header glyph          | slow pulse 1.6 s (accent)     |
| waiting      | crow.svg          | header glyph          | asymmetric tilt 480 ms forwards (warn) |
| error        | crow.svg          | header glyph          | sharp shake 240 ms × 1 (accent) |
| flight       | crow-flight.svg   | live-map overlay      | arc relocate 600 ms ease-mag (accent) |
| out-of-signal (UI-8) | TBD       | offline page          | TBD (later chunk)             |
