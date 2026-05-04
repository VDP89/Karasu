# Karasu Crow — Asset Spec

> Reconciled in UI-5 against `docs/ui/ui-0-design-brief.md` §5.6.
> The earlier "32×32 pixel-art / 16-bit / no anti-aliasing"
> draft is **superseded but partially honoured**: UI-5 ships a
> pixel-art silhouette (jagged edges, single fill,
> currentColor) at a 16-unit grain. The "16-bit / no anti-
> aliasing" wording maps to `shape-rendering="crispEdges"`;
> the 32-unit grain wording is replaced by 16 because the
> finer grain made the icon read as detailed-mascot rather
> than instrument.

---

## Format

```text
Source asset:    src/karasu/ui/static/assets/crow/crow.svg
Markup:          inline SVG in static/index.html (rect runs
                 duplicated so currentColor + state classes
                 work without an external <use> reference)
Format:          SVG, multiple axis-aligned <rect> elements
                 (one horizontal run of pixels per row),
                 fill="currentColor", shape-rendering="crispEdges"
viewBox:         0 0 16 16   (pixel grain — each viewBox unit
                 is one logical pixel)
Aesthetic:       pixel-art silhouette with hard, jagged edges.
                 No vector-smooth curves. Karasu is a watch-
                 tower; the mark is an instrument, not an app
                 mascot. Vector-rounded silhouettes were
                 explicitly rejected during UI-5 design — they
                 cut against the system's essence.
```

## Display sizes

```text
Header glyph     24 × 24 px  (1.5× the grain — shape-rendering
                              "crispEdges" keeps the rectangles'
                              edges hard at fractional scales)
Empty-state hero 96 × 96 px  (6× the grain — perfectly crisp,
                              every pixel cleanly addresses an
                              integer device-pixel block)
```

The CSS box stays square (24/96) on the design-system spacing
grid; the silhouette occupies most of the pixel grid (x=0..14,
y=2..14) so the visual asset reaches the box edges at both
sizes.

## Pixel layout (16 × 16)

```
0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15
.  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .   y=0
.  .  .  .  .  .  .  X  X  .  .  .  .  .  .  .   y=1  head crown
.  .  .  .  .  .  X  X  X  X  X  .  .  .  .  .   y=2  head expanding
.  .  .  .  .  .  X  X  .  X  X  X  X  .  .  .   y=3  eye notch + beak
.  .  .  .  .  .  X  X  X  X  X  .  .  .  .  .   y=4  head bottom
.  .  .  .  .  X  X  X  X  X  X  .  .  .  .  .   y=5  neck/shoulder
.  .  .  .  X  X  X  X  X  X  X  .  .  .  .  .   y=6  body widening
.  .  .  X  X  X  X  X  X  X  X  .  .  .  .  .   y=7  body widest
.  .  X  X  X  X  X  X  X  X  .  .  .  .  .  .   y=8  body, back curving
.  X  X  X  X  X  X  X  X  .  .  .  .  .  .  .   y=9  body+tail beginning
X  X  X  X  X  X  X  .  .  .  .  .  .  .  .  .   y=10 tail wedge down-back
.  .  .  .  X  X  X  .  .  .  .  .  .  .  .  .   y=11 body bottom (legs anchor)
.  .  .  .  X  .  X  .  .  .  .  .  .  .  .  .   y=12 legs (1-px gap)
.  .  .  .  X  .  X  .  .  .  .  .  .  .  .  .   y=13 feet
.  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .   y=14
.  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .   y=15
```

The anatomy is **vertical-posture perched crow, profile facing
right**. The earlier pass on this PR shipped a horizontal-low
silhouette that the operator read as kiwi; the redesign rotates
the bird's centre of gravity 90° so the head sits high above
the body and the tail extends DOWN-BACK from the body's rear.

Every visible signal earns its pixels:

```text
head ball     y=1..4, x=6..10    a compact 5×4 head sitting on
                                 top of the body. The head is
                                 the silhouette's leading mass;
                                 the body teardrops down from
                                 it.
beak          y=3, x=9..12       three-pixel horizontal stub
                                 protruding right from the
                                 head's mid-row. SHORT — long
                                 beaks read as kiwi or wood-
                                 pecker. Separated from the
                                 body by the head-bottom row
                                 (y=4) and the empty pixel at
                                 (x=8, y=3) which is also the
                                 eye notch.
eye           y=3, x=8           a single empty cell inside the
                                 filled head silhouette,
                                 immediately left of the beak.
                                 Negative space — no fill-rule
                                 needed because the surrounding
                                 rows don't cover it.
body          y=5..9             teardrop expanding from a 6-px
                                 neck (y=5) to an 8-px widest
                                 row (y=7..8) and then narrow-
                                 ing back to the legs anchor.
tail wedge    y=9..10, x=0..6    the body's back curve continues
                                 into a tail that drops DOWN
                                 AND BACK from the body's rear.
                                 The tail's diagonal (back at
                                 y=10 reaches x=0; body's
                                 leading edge at the same row
                                 ends at x=6) is what carries
                                 the silhouette into "perched
                                 crow at rest" rather than
                                 "horizontal kiwi blob".
two legs      x=4 and x=6,       thin one-pixel legs with a
              y=12..13           1-px gap, anchored under the
                                 body's centre (not under the
                                 tail). At 6× scale (96 px
                                 hero) each leg is 6 device
                                 pixels wide — clearly visible.
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

Pixel-art rendering interaction: the crow's transforms move
the WHOLE silhouette (translate, rotate, scale). The pixel
grid stays internally consistent — what shifts is the entire
shape relative to the viewport. `shape-rendering="crispEdges"`
remains in effect throughout the keyframes; the rectangles'
internal edges keep their hard quality even mid-animation.

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

The pixel layout is hand-drawn on the 16-unit grid for UI-5.
Not adapted from any third-party asset. The anatomy
conventions (vertical posture, head ball on top, short
horizontal beak, tail wedge down-back) are cross-validated
against two existing 16×16 raven sprites on OpenGameArt:

```text
- Pixel Raven (CC0)
  https://opengameart.org/content/pixel-raven
  Reference for: vertical posture, distinct head ball, short
  beak. The artist's own notes record their iteration: the
  first idle sprite "looked too much like pigeons", and the
  redesign that converged on this pattern is what shipped.
  Karasu's first UI-5 pass made the same mistake (operator
  read it as kiwi); studying this sprite is what corrected
  the redesign.

- Owl and Raven Sprites (CC-BY-SA 3.0)
  https://opengameart.org/content/owl-and-raven-sprites
  Cross-validation. Independent artist converging on the
  same vertical-posture / head-on-top / tail-down-back
  conventions.
```

Both references show that 16×16 perched crow legibility hinges
on three signals working together: (1) distinct head ball
sitting ON TOP of the body, not fused into a horizontal blob;
(2) short horizontal beak protruding from the head, not a long
beak (which reads kiwi/woodpecker); (3) tail extending DOWN
AND BACK from the body's rear, not a horizontal spike at body
height (which reads kingfisher / generic perched bird).

Karasu's rectangle runs, eye placement, leg spacing and
overall composition are the operator's editorial choices on
the same 16-unit grid; this asset is a hand-drawn
interpretation of the convention, not a copy of either
sprite.

Earlier UI-5 iterations on this branch:

```text
- Font Awesome "crow" vector adaptation (CC BY 4.0).
  Rejected: vector-smooth edges read as friendly /
  consumer-app and cut against Karasu's watchtower-as-
  instrument essence.

- First pixel-art pass (horizontal-low body, head fused
  with body front, tail as horizontal back-spike).
  Rejected: read as kiwi/duck. Root cause was insufficient
  reference-research before designing — corrected on the
  redesign by studying the two OpenGameArt sprites above
  and converging on the cross-validated conventions.
```

Future custom redraws are welcome — the contract this file
documents (16-unit grain, `shape-rendering="crispEdges"`,
four state classes, keyframe magnitudes, reduced-motion
behaviour) survives a pixel-layout swap. Only the rectangle
runs change, in both `crow.svg` and the inline copy in
`static/index.html`.

## States the crow does NOT carry yet

Per UI-0 §6, the following ship in later chunks:

```text
flight (UI-6)        SVG arc-path between two Live Map nodes;
                     600 ms ease-mag with the crow rotating
                     along the tangent so its beak leads.
                     The pixel grid will need to be evaluated
                     at non-orthogonal rotations — see the
                     UI-6 brief once it lands.
out-of-signal (UI-8) PWA offline-page easter-egg pose. Same
                     pixel grid, custom CSS class for any pose
                     change.
```

UI-5 covers idle / processing / waiting / error in the header
and hero slots only. Flight is UI-6's job; the offline pose
is UI-8's. The earlier draft listed nine separate sprite
states (idle / watching / fly_right / fly_left / processing /
waiting / notification / scar / error); UI-5 reduces this to
four because the actual `_crow_state` precedence in
`src/karasu/ui/server.py` only emits four. Notification and
scar do not have dedicated visual states yet — they reach the
operator through the timeline (UI-4) and, in future, the
detail panel (UI-7).
