# Pitch deck sources

Fifteen slides for the SIH26128 presentation, plus the script that assembles
them into a single self-contained file.

| Path | What it is |
|---|---|
| `deck.json` | Slide order, section breaks, font faces |
| `slides/*.html` | One file per slide — a `<section>` on a 1920×1080 canvas, all styles inline, `<aside>` holding the speaker notes |
| `fonts.css` | Latin subsets of the three families, base64-inlined |
| `build.py` | Assembles the above into `../pitch-deck.html` |

## Rebuilding

```bash
python docs/deck/build.py
```

No network and no dependencies — `fonts.css` is already inlined, so the build
works from a clean checkout on a plane.

## Why a built file at all

The deck also lives as a hosted artifact, which is the nicer way to present it
when there is wifi. A hackathon venue is not a reliable place to assume wifi,
so `docs/pitch-deck.html` opens from disk with the fonts embedded and no
runtime: arrows or space to move, `N` for speaker notes, `F` for fullscreen,
`P` for a print view that exports one slide per landscape page.

## Two things the builder does that the sources do not

1. **`<x-shape>` → inline SVG.** The slides use a custom element the hosted
   runtime draws. A plain browser does not know it, so `build.py` substitutes
   an equivalent SVG with the same box and colour.
2. **Autofit.** Nine of the fifteen slides carry more content than 1080px
   holds at the authored sizes. Rather than clip them, each is measured at its
   natural height and scaled to fit. This is measured after the embedded fonts
   apply, because metrics shift until then.

## Regenerating `fonts.css`

Only needed if a slide starts using a new family or weight. It is the one step
that needs network:

```python
# Fetch https://fonts.googleapis.com/css2?family=<spec>&display=swap with a
# browser User-Agent, keep the @font-face blocks commented /* latin */, then
# download each woff2 and replace its url(...) with url(data:font/woff2;base64,...).
# Set font-display:block so text never paints in fallback metrics.
```

The deck's characters all sit inside the `latin` subset, so `latin-ext` and the
Cyrillic/Greek/Vietnamese subsets are deliberately dropped — they roughly
doubled the file for glyphs no slide uses. `≤` and `≥` fall outside every
Google subset and render from a system font; that is expected.
