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
flight (UI-6)        SVG arc-path between two Live Map nodes;
                     600 ms ease-mag with the crow rotating
                     along the tangent so its beak leads.
                     Will need a SECOND asset
                     (crow-flight.svg, wings extended). The
                     perched silhouette in this file does NOT
                     animate convincingly under flight — wings
                     are folded; rotating the perched crow
                     reads as "tossed by the air", not flying.
                     Source plan for the flight asset: same
                     hunt pattern as UI-5 (OpenMoji /
                     Wikimedia / heraldic raven displayed,
                     CC-licensed).
out-of-signal (UI-8) PWA offline-page easter-egg pose. Same
                     base asset, custom CSS class for any pose
                     change.
```

UI-5 covers idle / processing / waiting / error in the header
and hero slots only.
