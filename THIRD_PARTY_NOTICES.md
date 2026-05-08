# Third-party notices

Karasu redistributes a small number of third-party assets and
fonts. Each entry below records the upstream source, the
licence terms, and any modifications Karasu has made.

Asset-level attributions also live inline next to the file
they describe (e.g. inside `src/karasu/ui/static/assets/crow/crow.svg`,
`docs/ui/assets/karasu_sprites_spec.md`,
`src/karasu/ui/static/fonts/LICENSE-Inter.txt`,
`src/karasu/ui/static/fonts/LICENSE-JetBrainsMono.txt`).
This file is the discovery surface; the inline copies remain
the source of truth for each asset.

## OpenMoji — "Black Bird" (`1F426 200D 2B1B`)

```text
Used in:    src/karasu/ui/static/assets/crow/crow.svg
            (the canonical Karasu crow asset, header glyph
            and 96-px hero crow on the empty-state surface)
Source:     https://openmoji.org/library/emoji-1F426-200D-2B1B/
Project:    https://openmoji.org/
Licence:    Creative Commons Attribution-ShareAlike 4.0
            International (CC-BY-SA 4.0)
Licence URL: https://creativecommons.org/licenses/by-sa/4.0/
```

### Modifications

- The two body silhouette paths from the upstream emoji are
  retained but stripped of stroke-detail elements (5
  decorative strokes meant for 72-px emoji rendering, which
  collapse to noise at the 24-px header glyph scale).
- The two grey-tone body fills are unified under
  `currentColor` so the silhouette reads as a single
  editorial mark recolourable through the four UI-5 state
  classes.
- Two leg `<rect>` elements are added in `currentColor` —
  operator-added, not part of upstream OpenMoji.
- One eye `<circle>` is added, filled with the canvas
  background colour (`var(--bg-0)` inline; `#0a0a0b`
  standalone), acting as negative space against the body
  fill — operator-added, not part of upstream OpenMoji.
- UI-14 §3-A adds four pre-rendered PWA icon PNG
  derivatives at:
    - `src/karasu/ui/static/icons/karasu-192.png` (UI-8)
    - `src/karasu/ui/static/icons/karasu-512.png` (UI-8)
    - `src/karasu/ui/static/icons/karasu-maskable-192.png` (UI-14)
    - `src/karasu/ui/static/icons/karasu-maskable-512.png` (UI-14)
  All four are rasterizations of the modified
  `static/crow/crow.svg` produced by Playwright headless
  (see `scripts/ui_pwa_icons.py`). The any-purpose pair
  renders the crow at 70 % of the canvas; the maskable
  pair renders at 55 % so the glyph stays inside the W3C
  80 %-diameter safe zone a launcher mask may apply (per
  manifest spec). No new dependency, no glyph editing —
  the maskable variants are PURELY a different render
  ratio of the same modified SVG. The CC-BY-SA chain
  documented above propagates to all four PNG outputs.

CC-BY-SA propagates compatibly with Karasu's own licence. See
`docs/ui/assets/karasu_sprites_spec.md` § Provenance for the
full iteration history that led to the OpenMoji-adapted
direction.

## Inter (Inter Display)

```text
Used in:    src/karasu/ui/static/fonts/
              inter-display-400.woff2
              inter-display-500.woff2
              inter-display-700.woff2
            Loaded via @font-face in
            src/karasu/ui/static/css/tokens.css and surfaced
            through the --font-display token (UI-2 design
            system).
Version:    Inter 4.x family (Display subfamily).
Source:     https://github.com/rsms/inter
Licence:    SIL Open Font License, Version 1.1 (OFL-1.1)
Licence URL: https://scripts.sil.org/OFL
            Full text shipped at
            src/karasu/ui/static/fonts/LICENSE-Inter.txt
```

### Modifications

None. The `.woff2` files are subset-and-converted artefacts
of the upstream Inter Display weights 400 / 500 / 700; no
glyph editing, no metric changes. Conversion was performed
by `scripts/ui_fetch_fonts.sh` (idempotent, woff2 magic-byte
verified).

## JetBrains Mono

```text
Used in:    src/karasu/ui/static/fonts/
              jetbrains-mono-400.woff2
              jetbrains-mono-500.woff2
              jetbrains-mono-700.woff2
            Loaded via @font-face in
            src/karasu/ui/static/css/tokens.css and surfaced
            through the --font-mono token (UI-2 design
            system).
Version:    JetBrains Mono 2.304.
Source:     https://github.com/JetBrains/JetBrainsMono
Licence:    SIL Open Font License, Version 1.1 (OFL-1.1)
Licence URL: https://scripts.sil.org/OFL
            Full text shipped at
            src/karasu/ui/static/fonts/LICENSE-JetBrainsMono.txt
```

### Modifications

None. The `.woff2` files are subset-and-converted artefacts
of the upstream JetBrains Mono weights 400 / 500 / 700; no
glyph editing, no metric changes. Conversion was performed
by `scripts/ui_fetch_fonts.sh`.

## Python runtime dependencies

Python packages that Karasu depends on at runtime are listed
in `pyproject.toml`. Each carries its own licence in the
package's distribution metadata; this file does not duplicate
those entries. If a future runtime dependency requires
explicit attribution beyond what its packaging metadata
covers, add a section here.

## Adding a new entry

When introducing a new third-party asset (font, icon, sprite,
sound, dataset, etc.), add a section above following the
template:

```text
## <Name>

\`\`\`text
Used in:    <repo path(s)>
Version:    <version or revision>
Source:     <upstream URL>
Licence:    <SPDX identifier or licence name + version>
Licence URL: <canonical licence URL>
\`\`\`

### Modifications

<bullet list of changes, or "None.">
```

Inline attribution at the file level still applies — this
file is a discovery index, not a substitute for per-file
provenance.
