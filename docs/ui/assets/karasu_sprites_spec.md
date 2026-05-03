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
.  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .   y=1
.  .  .  .  .  .  X  X  X  .  .  .  .  .  .  .   y=2  head top
.  .  .  .  .  X  X  X  X  X  .  .  .  .  .  .   y=3  head ball
.  .  .  .  .  X  X  .  X  X  X  X  X  X  .  .   y=4  eye notch + beak
.  .  .  .  .  X  X  X  X  .  .  .  .  .  .  .   y=5  head bottom
.  .  .  .  X  X  X  X  .  .  .  .  .  .  .  .   y=6  neck step
.  .  .  X  X  X  X  X  X  X  .  .  .  .  .  .   y=7  shoulder
.  .  X  X  X  X  X  X  X  X  X  .  .  .  .  .   y=8  body
.  .  X  X  X  X  X  X  X  X  X  .  .  .  .  .   y=9  body
X  X  X  X  X  X  X  X  X  X  .  .  .  .  .  .   y=10 tail-spike + body, continuous
.  .  .  .  X  X  X  X  X  .  .  .  .  .  .  .   y=11 body bottom
.  .  .  .  X  .  .  X  .  .  .  .  .  .  .  .   y=12 legs (2-px gap)
.  .  .  .  X  .  .  X  .  .  .  .  .  .  .  .   y=13 legs
.  .  .  .  X  .  .  X  .  .  .  .  .  .  .  .   y=14 feet
.  .  .  .  .  .  .  .  .  .  .  .  .  .  .  .   y=15
```

Every visible signal earns its pixels:

```text
beak          y=4, x=8..13   six-pixel run protruding right
              from the head ball, separated by an empty pixel
              above (y=3 stops at x=9) and the head's natural
              edge below (y=5 stops at x=8). The gap on three
              sides is what makes the beak read as a beak and
              not as a wing or a misaligned body cell.
eye           y=4, x=7       a single empty cell INSIDE the
              filled head silhouette. Negative space — no
              fill-rule needed because the surrounding rows
              don't cover it.
tail spike    y=10, x=0..1   the bird's back-most extent.
              Continuous with the body run (x=0..9 unbroken on
              y=10) so it reads as the tail end, not a
              detached dot.
two legs      x=4 and x=7,   thin one-pixel legs with a 2-pixel
              y=12..14       gap. At 6× scale (96 px hero) each
              leg is 6 device pixels wide — clearly visible.
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
Not adapted from any third-party asset. An earlier UI-5
iteration adapted Font Awesome's "crow" vector icon
(CC BY 4.0); that approach was rejected by the operator on
two grounds:

```text
1. Vector-smooth edges read as friendly / consumer-app and
   cut against Karasu's watchtower-as-instrument essence.
2. The mark needed enough deliberate craft to not blur into
   the Claude Code mascot or any other generic editorial
   bird icon. Pixel art at 16 × 16 grain, jagged edges,
   single colour signals "designed for THIS surface" without
   reaching for ornament.
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
