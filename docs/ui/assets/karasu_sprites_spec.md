# Karasu Crow — Asset Spec

> Reconciled in UI-5 against `docs/ui/ui-0-design-brief.md` §5.6.
> The earlier draft of this file (32×32 pixel-art / 16-bit /
> no anti-aliasing) is **superseded**. UI-0 §5.6 is the
> contract; this file documents the production decisions made
> in UI-5 to satisfy it.

---

## Format

```text
Source asset:    src/karasu/ui/static/assets/crow/crow.svg
Markup:          inline SVG in static/index.html (path data
                 duplicated so currentColor + state classes
                 work without an external <use> reference)
Format:          SVG, single <path>, fill="currentColor"
viewBox:         0 0 640 512  (Font Awesome native viewBox;
                 see "Provenance" below)
fill-rule:       evenodd  (the eye is a sub-path that
                 subtracts from the body silhouette)
Aesthetic:       editorial mark, not pixel-art sprite. Clean
                 vector silhouette in line with the UI-0
                 anchors (Linear, Vercel, Stripe Press).
```

## Display sizes

```text
Header glyph     24 × 19.2 px  (preserveAspectRatio meet
                                inside a 24 × 24 box, with
                                the icon's native 1.25:1
                                aspect ratio honoured)
Empty-state hero 96 × 76.8 px  (same scaling rule, larger
                                box)
```

The CSS box stays square (24/96) so flex layouts in the
header/empty-state remain on the design-system spacing grid.
The icon centres inside the box via the SVG default
`preserveAspectRatio="xMidYMid meet"`.

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

## Provenance & licence

The path data is verbatim from Font Awesome Free 6 ("crow",
solid set), licensed under **Creative Commons Attribution
4.0 International (CC BY 4.0)**. See
<https://fontawesome.com/license/free>. Attribution lives in
`crow.svg` as a comment block; redistributable downstream
provided the attribution travels with the file.

The choice — "copy with class" rather than redraw — was made
in UI-5 after several iterations on a hand-drawn 32×32 path
read as duck rather than crow at every scale tested. Font
Awesome's icon is a known iconic perched-crow silhouette
with a sharp leading beak, distinct head, eye negative space,
and two visible legs; reusing it under the licence saved
several iterations on a problem already well solved
upstream.

If a future redraw is desired (custom Karasu mark instead of
adapted FA icon), the contract this file documents
(viewBox, state classes, keyframes, reduced-motion behaviour)
remains stable — only the path data changes, in both
`crow.svg` and the inline copy in `static/index.html`.

## States the crow does NOT carry yet

Per UI-0 §6, the following ship in later chunks:

```text
flight (UI-6)        SVG arc-path between two Live Map nodes;
                     600 ms ease-mag with the crow rotating
                     along the tangent so its beak leads.
out-of-signal (UI-8) PWA offline-page easter-egg pose. Same
                     path data, custom CSS class.
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
