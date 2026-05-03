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
animated-element content. The current capture (~105 KB) sits
well inside the budget without a transcode pass.

## Provenance

The crow is a hand-drawn pixel-art silhouette on a 16-unit
grid; not adapted from any third-party asset. An earlier
UI-5 iteration adapted Font Awesome's "crow" vector icon
(CC BY 4.0); that approach was rejected because vector-
smooth edges read as friendly / consumer-app and cut against
Karasu's watchtower-as-instrument essence. See
`docs/ui/assets/karasu_sprites_spec.md` § Provenance for
the rationale and the contract that survives a future
pixel-layout swap.
