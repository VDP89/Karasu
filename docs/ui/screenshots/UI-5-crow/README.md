# UI-5 — The Crow

> Audit attachments for the chunk that swaps the placeholder
> silhouette for the canonical crow asset and ships the four
> state animations.

## What to look at

```text
The crow has personality; the surface stays editorial.
That is the editorial constraint pinned by ChatGPT in the
UI-4 audit verdict. UI-5 ships motion ONLY on the crow.
Header chrome, timeline rows, footer cells must read as
visibly still while the crow cycles through its four states.

The .webm is the testable artifact for that constraint —
the recording keeps the full 1024 × 640 viewport in frame
(no crop to the crow alone, per the PR #73 pin) so the
auditor can confirm BOTH that the crow moves AND that the
environment does not.
```

## Files

```text
00-crow-idle.png         Header glyph in --fg-1 + footer
                         "crow: idle". Bus has two events
                         (file_change + completed agent_response)
                         so the timeline is populated and the
                         crow is at editorial rest. Ambient
                         breathing keyframe is running but its
                         1 px translate is below the screenshot's
                         visible threshold.
01-crow-processing.png   Header glyph in --accent + footer
                         "crow: processing". Bus tail is a
                         file_change without a closing
                         agent_response, so _crow_state lands
                         on processing. Slow pulse keyframe
                         (scale 1.04 over 1.6 s) running.
02-crow-waiting.png      Header glyph in --warn + footer
                         "crow: waiting". Bus tail is an
                         agent_response with requires_human=true,
                         so _crow_state lands on waiting. The
                         crow holds a 4° tilt (forwards fill
                         mode); the still does not show
                         rotation but the colour shift makes
                         the state legible.
03-crow-error.png        Header glyph in --accent + footer
                         "crow: error". Bus tail is an
                         agent_response with status="failed".
                         The shake keyframe is a 240 ms
                         single-beat (no loop) so capturing it
                         mid-animation is non-deterministic.
                         The script poses this still
                         deliberately by pinning the crow's
                         transform to translateX(-2px) — the
                         keyframe's leftmost extreme — so the
                         beat's signature is visible in the
                         static frame. The shake's actual
                         motion truth lives in UI-5-crow.webm.
04-empty-state-with-canonical-crow.png
                         The 96 px hero crow on the empty
                         state. Same path data as the header
                         glyph, scaled up. Ambient breathing
                         loop is running.
```

## Recording

```text
docs/ui/recordings/UI-5-crow.webm
```

The recording walks idle → processing → waiting → error → idle
inside one Playwright context (1024 × 640 viewport, ~5 s
total wall time). Frame schedule:

```text
0.0 s  - 0.8 s  idle baseline (ambient breathing)
0.8 s  - 1.8 s  processing (slow pulse, --accent)
1.8 s  - 2.8 s  waiting (4° tilt held, --warn)
2.8 s  - 3.8 s  error (single 240 ms shake, --accent)
3.8 s  - 4.6 s  idle recovery (back to --fg-1, breathing)
```

Each transition is server-driven: the script writes a
state-specific event to the bus and forces an immediate
`/api/health` poll via `page.evaluate("await tick()")` so the
class swap fires without waiting for the natural 3 s
`setInterval`. The transition path is therefore production-
real (bus → server projection → fetch → CSS class swap →
keyframe) — only the polling cadence is short-circuited for
the duration of the recording.

Editorial check the recording supports:

```text
✓ The crow visibly changes state across the four transitions.
✓ The header layout (Karasu word-mark, bus path) does not
  shift, jitter, or animate during the cycle.
✓ The timeline rows do not redraw, recolour, or move.
✓ The footer cells (version, last event time, crow label)
  update text content as expected, but no animation runs on
  the layout.
✓ The shake on the error beat is decisive and one-shot — no
  re-trigger loop, no alarm fatigue.
```

If the .webm exceeds the 500 KB audit budget on a future re-
record, transcode with ffmpeg:

```bash
ffmpeg -i UI-5-crow.webm -c:v libvpx-vp9 -crf 35 -b:v 0 \
       -row-mt 1 -an UI-5-crow.transcoded.webm
mv UI-5-crow.transcoded.webm UI-5-crow.webm
```

CRF 35 with VP9 typically halves the size of Playwright's
default VP8 output for this kind of static-shell-with-small-
animated-element content. The current capture (~161 KB) sits
well inside the budget without a transcode pass.

## Legibility at the two display scales (P2 from Codex audit)

```text
24 px header glyph   The 72-unit viewBox renders into a 24 px
                     square. The bird silhouette occupies ~85 %
                     of the box; head + beak + body + 2 legs
                     all read at this scale. The eye notch
                     becomes a sub-pixel dark spot — visible
                     enough to confirm the head's centre but
                     does not dominate.
                     See: 00-crow-idle.png header strip.

96 px hero           4× the header scale. Full anatomy reads
                     cleanly: distinct head ball, sharp beak
                     up-right, eye notch as deliberate negative
                     space, two legs anchored inside the body
                     fill, tail wedge curving back. The vector
                     scales smoothly — no staircase artefacts
                     on the curves, which the earlier pixel-
                     grid pass introduced at 96 px.
                     See: 04-empty-state-with-canonical-crow.png.
```

If the auditor wants a side-by-side comparison composite, both
scales appear together in `00-crow-idle.png` (header strip +
populated timeline) and `04-empty-state-with-canonical-crow.png`
(hero only) — opening both side by side proves the asset
holds at both ends.

## Provenance

The crow body silhouette is **adapted from OpenMoji "Black
Bird" emoji** (`1F426 200D 2B1B`), licensed under CC-BY-SA 4.0:

- [OpenMoji — Black Bird (CC-BY-SA 4.0)](https://openmoji.org/library/emoji-1F426-200D-2B1B/)

Karasu strips upstream's stroke-detail elements, unifies the
two grey-tone fills under `currentColor`, and adds two leg
rectangles + one eye notch as operator-added elements.

See `docs/ui/assets/karasu_sprites_spec.md` § Provenance for
the full design history (FA vector → 2 pixel-art passes →
2 hand-drawn vector attempts → OpenMoji-adapted final) and
the contract that survives a future asset swap.

The two earlier OpenGameArt 16×16 raven references that
informed the rejected pixel-art passes are also recorded
there for posterity:

- [Pixel Raven (CC0)](https://opengameart.org/content/pixel-raven)
- [Owl and Raven Sprites (CC-BY-SA 3.0)](https://opengameart.org/content/owl-and-raven-sprites)
