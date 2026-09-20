#!/usr/bin/env python3
"""Assemble the slide sources into one self-contained HTML deck.

The slides are authored for a hosted presentation runtime, which supplies the
page chrome, the fonts, and a couple of custom elements. A venue with bad wifi
supplies none of those, so this rebuilds the same fifteen slides as a single
file that opens from disk: no network, no build step, no runtime.

Usage:  python docs/deck/build.py        (writes docs/pitch-deck.html)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "pitch-deck.html"

CANVAS_W, CANVAS_H = 1920, 1080

# The authoring runtime draws these; a plain browser does not, so they become
# inline SVG with the same box and colour the slide asked for.
SHAPES = {
    "arrow-down": '<polygon points="50,100 0,45 32,45 32,0 68,0 68,45 100,45" />',
    "arrow-right": '<polygon points="100,50 45,100 45,68 0,68 0,32 45,32 45,0" />',
}


def _style_value(style: str, prop: str) -> str | None:
    match = re.search(rf"(?:^|;)\s*{prop}\s*:\s*([^;]+)", style)
    return match.group(1).strip() if match else None


def expand_shapes(html: str) -> str:
    """Replace <x-shape kind="..."> with an equivalent inline SVG."""

    def replace(match: re.Match[str]) -> str:
        kind = match.group("kind")
        style = match.group("style") or ""
        body = SHAPES.get(kind)
        if body is None:
            return ""
        width = _style_value(style, "width") or "40px"
        height = _style_value(style, "height") or "40px"
        fill = _style_value(style, "background") or "currentColor"
        return (
            f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true" '
            f'style="width:{width}; height:{height}; fill:{fill}; flex:none">{body}</svg>'
        )

    return re.sub(
        r'<x-shape\s+kind="(?P<kind>[a-z-]+)"(?:\s+style="(?P<style>[^"]*)")?\s*>'
        r"\s*</x-shape>",
        replace,
        html,
    )


def split_notes(html: str) -> tuple[str, str]:
    """Pull the speaker notes out of the slide body."""
    match = re.search(r"<aside>(.*?)</aside>", html, re.DOTALL)
    if not match:
        return html, ""
    return html.replace(match.group(0), ""), match.group(1).strip()


def build() -> None:
    deck = json.loads((HERE / "deck.json").read_text())
    order: list[str] = deck["order"]

    # The fonts are inlined rather than linked: a venue with no wifi would
    # otherwise fall back to system metrics, and several slides are tight
    # enough that the substitution overflows the canvas.
    font_css = (HERE / "fonts.css").read_text()

    slides: list[str] = []
    notes: list[str] = []
    for index, slide_id in enumerate(order, start=1):
        raw = (HERE / "slides" / f"{slide_id}.html").read_text()
        body, note = split_notes(raw)
        body = expand_shapes(body)
        slides.append(f'<div class="slide" data-index="{index}">{body}</div>')
        notes.append(note)

    notes_json = json.dumps(notes)
    title = deck.get("title", "Deck")

    OUT.write_text(TEMPLATE.format(
        title=title,
        font_css=font_css,
        canvas_w=CANVAS_W,
        canvas_h=CANVAS_H,
        slides="\n".join(slides),
        notes_json=notes_json,
        count=len(slides),
    ))
    kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT.relative_to(HERE.parent.parent)} — {len(slides)} slides, {kb:.0f} KB")
    print("Open it in any browser. No network needed -- the fonts are embedded.")
    print("Arrows or space to move, N for notes, F for fullscreen, P for a print/PDF view.")


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
{font_css}
</style>
<style>
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; padding: 0; height: 100%; overflow: hidden;
    background: #0B1512; font-family: 'IBM Plex Sans', Arial, sans-serif;
  }}
  #stage {{
    position: fixed; inset: 0; display: flex;
    align-items: center; justify-content: center;
  }}
  .slide {{
    width: {canvas_w}px; height: {canvas_h}px;
    position: absolute; transform-origin: center center;
    overflow: hidden; display: none;
  }}
  .slide.current {{ display: block; }}
  /* The slide sources position footers absolutely against the slide box. */
  .slide > section {{ position: relative; width: 100%; height: 100%; }}

  #bar {{
    position: fixed; left: 0; right: 0; bottom: 0; height: 34px;
    display: flex; align-items: center; gap: 16px; padding: 0 14px;
    background: rgba(11,21,18,0.92); color: #7E9A8D;
    font: 500 12px/1 'IBM Plex Mono', monospace; letter-spacing: 0.06em;
    border-top: 1px solid #1E3329; user-select: none;
  }}
  #bar button {{
    background: none; border: 1px solid #1E3329; color: #7E9A8D;
    border-radius: 5px; padding: 4px 9px; cursor: pointer; font: inherit;
  }}
  #bar button:hover {{ color: #C9E3D6; border-color: #2E463B; }}
  #bar .spacer {{ flex: 1; }}

  #notes {{
    position: fixed; right: 0; bottom: 34px; width: 420px; max-height: 46vh;
    overflow-y: auto; padding: 18px 20px; display: none;
    background: #10201A; color: #B8CFC3; border-left: 1px solid #1E3329;
    border-top: 1px solid #1E3329; font-size: 14px; line-height: 1.6;
  }}
  #notes.open {{ display: block; }}
  #notes h3 {{
    margin: 0 0 8px; font: 600 11px/1 'IBM Plex Mono', monospace;
    letter-spacing: 0.14em; text-transform: uppercase; color: #5E7A6D;
  }}

  /* Print / PDF: every slide on its own landscape page, notes inline. */
  @media print {{
    @page {{ size: {canvas_w}px {canvas_h}px; margin: 0; }}
    html, body {{ overflow: visible; background: #fff; height: auto; }}
    #stage {{ position: static; display: block; }}
    #bar, #notes {{ display: none !important; }}
    .slide {{
      display: block !important; position: relative;
      transform: none !important; page-break-after: always; break-after: page;
    }}
  }}
</style>
</head>
<body>
<div id="stage">
{slides}
</div>

<div id="notes"><h3>Speaker notes</h3><p id="notes-body"></p></div>

<div id="bar">
  <button id="prev" type="button">&larr;</button>
  <button id="next" type="button">&rarr;</button>
  <span id="counter"></span>
  <span class="spacer"></span>
  <span>&larr;/&rarr; move &middot; N notes &middot; F fullscreen &middot; P print</span>
  <button id="notes-toggle" type="button">Notes</button>
</div>

<script>
(function () {{
  var NOTES = {notes_json};
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var stage = document.getElementById('stage');
  var counter = document.getElementById('counter');
  var notesPanel = document.getElementById('notes');
  var notesBody = document.getElementById('notes-body');
  var index = 0;

  // The deck is authored on a fixed canvas; scale it to whatever screen it
  // lands on rather than reflowing, so the layout is exactly as designed.
  function fit() {{
    var barHeight = 34;
    var scale = Math.min(
      window.innerWidth / {canvas_w},
      (window.innerHeight - barHeight) / {canvas_h}
    );
    slides.forEach(function (slide) {{
      slide.style.transform = 'scale(' + scale + ')';
    }});
    stage.style.paddingBottom = barHeight + 'px';
  }}

  // Several slides carry more content than the 1920x1080 canvas holds at the
  // authored sizes. Rather than clip them, each is measured at its natural
  // height and scaled down to fit. Measurement needs the slide visible, so
  // display is toggled around it -- a hidden element reports zero height.
  function autofit() {{
    slides.forEach(function (slide) {{
      var section = slide.querySelector('section');
      if (!section) return;
      var wasHidden = !slide.classList.contains('current');
      if (wasHidden) slide.style.display = 'block';

      section.style.transform = '';
      section.style.height = '';
      var natural = section.scrollHeight;
      if (natural > {canvas_h} + 1) {{
        // Give the content the room it actually wants before scaling, so
        // space-between distributes over the real height rather than 1080.
        // scrollHeight omits the container's bottom padding when a flex child
        // overflows, and these slides pin their footer inside that padding --
        // so add it back, or the footer lands on top of the last paragraph.
        var pad = parseFloat(getComputedStyle(section).paddingBottom) || 0;
        section.style.height = (natural + pad) + 'px';
        var k = {canvas_h} / section.scrollHeight;
        section.style.transformOrigin = 'top center';
        section.style.transform = 'scale(' + k + ')';
      }}

      if (wasHidden) slide.style.display = '';
    }});
  }}

  function show(next) {{
    index = Math.max(0, Math.min(slides.length - 1, next));
    slides.forEach(function (slide, i) {{
      slide.classList.toggle('current', i === index);
    }});
    counter.textContent = (index + 1) + ' / ' + slides.length;
    notesBody.textContent = NOTES[index] || 'No notes for this slide.';
    try {{ location.hash = String(index + 1); }} catch (e) {{}}
  }}

  document.getElementById('prev').onclick = function () {{ show(index - 1); }};
  document.getElementById('next').onclick = function () {{ show(index + 1); }};
  document.getElementById('notes-toggle').onclick = function () {{
    notesPanel.classList.toggle('open');
  }};

  document.addEventListener('keydown', function (event) {{
    var key = event.key;
    if (key === 'ArrowRight' || key === 'PageDown' || key === ' ') {{
      event.preventDefault(); show(index + 1);
    }} else if (key === 'ArrowLeft' || key === 'PageUp') {{
      event.preventDefault(); show(index - 1);
    }} else if (key === 'Home') {{ show(0); }}
    else if (key === 'End') {{ show(slides.length - 1); }}
    else if (key === 'n' || key === 'N') {{ notesPanel.classList.toggle('open'); }}
    else if (key === 'f' || key === 'F') {{
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen();
    }} else if (key === 'p' || key === 'P') {{ window.print(); }}
  }});

  window.addEventListener('resize', fit);
  fit();
  autofit();
  // Re-measure once the embedded faces are applied; metrics shift until then.
  if (document.fonts && document.fonts.ready) {{
    document.fonts.ready.then(function () {{ autofit(); fit(); }});
  }}
  var fromHash = parseInt((location.hash || '').slice(1), 10);
  show(isNaN(fromHash) ? 0 : fromHash - 1);
}})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    build()
