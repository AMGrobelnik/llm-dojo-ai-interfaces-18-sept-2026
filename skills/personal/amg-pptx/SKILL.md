---
name: amg-pptx
description: "Build the author's institute-style presentations (.pptx) with python-pptx: institute template, colour-coded lead+tail bullets, one bullet per line, side illustration, render check. Use whenever the author asks for slides, a deck, or a presentation."
---

# amg-pptx

Builds the author's own talk decks (institute template, colour-coded bullets,
pastel side illustrations). For a **generic** deck (someone else's brand, or an
`html2pptx` workflow), use `anthropic-pptx` instead — this skill is specifically
The author's institute visual style.

## Style rules (see `style/STYLE.md` for the full write-up)

- Bold colour-coded lead phrase + short plain tail, same line, colon-separated
  (navy for neutral, red `C00000` for problems/limits, green `accent6` for
  strengths/fixes).
- One idea per title; a "(2)/(3)" suffix means split the slide, don't cram more in.
- Cap sub-bullets at ~10 words; a comparison/matrix becomes a table or screenshot,
  never nested bullets.
- Content slides: bullets in the left ~57% column, a side illustration in the
  right ~40% column — never full-width text.
- **Rule 6 — one bullet = one line.** Bullets must be self-contained (readable
  without the speaker) but short enough to talk over, not read aloud. If a
  bullet wraps to a second line, fix it in this order: (1) reword it shorter,
  (2) adjust layout — e.g. narrow the picture to widen the text column, (3) only
  as a last resort, drop the font size.
- **Rule 7 — text as big as possible.** Body text is already minimal (one line per bullet). On every slide, scale fonts UP until the layout is full, keeping hierarchy (title > level-1 > level-2 > level-3 > captions), never comically big.
- Side picture stays ≥40% wide. If the longest line, not the height, limits
  the text size, drop to full-width text and put the picture bottom-right in
  the free corner space only if ≥1.6in remain; otherwise no picture on that
  slide. **Layout pick:** the side-picture layout (A) wins whenever it can
  still set level 1 at 28pt or more, unless the below-text layout (B) reaches
  the same level-1 size and gives a larger fitted picture, in which case B
  wins; only when A cannot reach 28pt does the larger level-1 size otherwise
  decide.
- **One bullet = one line.** The fit-up never accepts a wrapped line: it
  measures every rendered line against its own box and fails the build so the
  line gets reworded, rather than shipping a wrap.
- **No standalone headings inside the body.** Everything in a content slide's
  body is a bullet: the section line is a level-1 bullet (bold, colour-coded),
  its items are level-2, their details level-3. Each level's text starts
  ≥0.5in further right than the previous one (`marL` step with a negative
  `indent`, so the glyph hangs in that gap) and carries its own glyph
  (● / • / –); size steps down per level (level 1 ≥ level 2 ≥ level 3) and all
  levels are fitted together by rule 7. Agenda and demo slides use the same
  indent table — one mechanism, no separate headline band.
- **Gutter.** Text and a picture never touch: keep ≥0.3in clear gap between a
  text box's right edge and any picture. For a side picture, narrow the text
  column itself by that 0.3in and check *every* rendered line against **its
  own** box — each paragraph against the column minus that paragraph's own
  indent, at that level's pt size. A line that overflows even at the floor
  size is reworded, not shrunk. In layout A the picture takes whatever column
  width the text does not need, never trading text size for picture width.
- **Pictures anchor bottom-right and may use the footer band.** Every picture
  sits flush with the bottom-right corner of its region and may extend into
  the bottom-right corner of the slide, over the right-hand footer logo/strip,
  down to 0.15in above the slide edge — the ≥1.6in minimum and the layout
  pick still apply. A corner picture is sized as the largest bottom-right
  rectangle *free of text*, not the strip under the last line: for each
  candidate top edge (each line's bottom, plus the body top) the usable width
  is the body's right edge minus the 0.3in gutter minus the right edge of the
  widest line whose span reaches below that top, and the pair maximising the
  picture's area at its aspect ratio wins. It must cover the right footer block
  entirely (otherwise it stops above the footer); it may freely cover the
  slide number's spot — the number moves out of the way instead, see rule 15
  below. A picture that enters the footer band is also narrowed so its left
  edge never passes the left logo + the number box + a gutter (3.04in on the
  institute template); if that narrowing then makes it too narrow to cover the
  right footer block, it stops above the footer (LOGO_TOP) instead, full
  width allowed there — see rule 15.
- **Slide number takes the rightmost free footer spot (rule 15).** Every
  content slide (not the title slide) shows its 1-based position in the deck
  as small muted-grey text (~11-12pt), right-aligned on the footer row. It
  goes in the true bottom-right corner only if the template leaves that
  corner free; the institute template doesn't (its right footer block/logo fills
  it), so the number's default spot is just left of that block instead. Only
  a picture that actually reaches into the footer band can cover the default
  spot — one that stops short of it never counts, however close — in which
  case the number falls back to bottom-centre, then to a spot slid left of
  the picture, then — if nothing is free — stays at the default spot and is
  added last in z-order (on top of every picture), with a warning in the
  build report. A picture is never allowed to reach that point in practice:
  any picture entering the footer band keeps its left edge clear of the
  bottom-left logo, the number box, and a gutter (3.04in on the institute
  template) — narrowed if needed, or dropped back to stopping above the
  footer (LOGO_TOP) if narrowing would leave it too narrow to cover the
  right footer block — so the slide-left fallback slot always exists and
  neither footer logo is ever touched. Verify this programmatically
  (re-open the saved .pptx with python-pptx and assert each content slide's
  number equals its index) as part of the build script — see
  `style/STYLE.md` rule 15 for the full rule.
- **Picture variety (rule 16).** A picture belongs on most content slides,
  not every one; never repeat the same decorative image on two consecutive
  slides — only an actual information-carrying figure (discussed on both,
  passed `key_figure=True`) may. When two neighbouring slides would
  otherwise share a picture, keep it on the one it fits best and drop it
  from the other (text-only layout there, no picture forced in; don't
  generate a replacement image). The build script's report warns whenever
  consecutive slides reference the same image path without `key_figure` —
  see `style/STYLE.md` rule 16 for the full rule.
- **Pictures as big as the space allows (rule 14).** Text is fitted first, but
  every level-1 size from the fitted maximum down to 28pt counts as big
  enough: among all those (layout, size) candidates, the one with the largest
  fitted picture wins (ties to the larger text), and that picture fills the
  largest text-free rectangle at its own aspect ratio — see `style/STYLE.md`
  rule 14 for the full rule, including the in-image text-legibility floor.
- **Pictures are resampled to their displayed size at build time.** `add_visual`
  downsamples each picture to the size it's actually placed at (floor 300dpi,
  never upscaled, Pillow LANCZOS) before handing it to python-pptx, so a deck
  full of high-res screenshots stays under the 25MB limit with no visible
  quality loss; the source figure files on disk are never touched.
- **Flat multi-column list.** For a headline plus a long flat list of short
  items (no side picture, no sub-bullets), use `add_flat_columns_slides`
  instead of `add_hierarchical_bullets`: up to 3 unequal-width columns (each
  exactly as wide as its own longest item), never a shared equal width, font
  floored at 16pt, no item ever wraps. When the list doesn't fit even at that
  floor, it auto-splits into two slides, "<headline> (1/2)"/"(2/2)".
- **Section titles name the theme (rule 17).** A slide title says what the
  slide is about, never a bare counter such as "Tips (2/4)" or "Part 3".
  When one topic spans several slides, each gets its own theme title
  ("Agentic CLIs: hooks"), and a counter is allowed only as a suffix after a
  theme, never as the whole title — see `style/STYLE.md` rule 17 for the
  full rule.
- **End on takeaways (rule 18).** The final slide is "Key takeaways" with at
  most three short level-1 bullets that restate decisions the audience
  should leave with, drawn from the deck's own content. No "Thank you" or
  "Questions?" slide; contact or URL lines, if any, go in one small line
  under the takeaways — see `style/STYLE.md` rule 18 for the full rule.
- **A multi-line title never strands a lone article/preposition/conjunction
  (rule 20).** A word like "a", "the", "of", "and" never ends up alone on the
  last line of a wrapped title. Break a two-line title explicitly at its
  phrase boundary with a line break in the text, each line fitted on its
  own, instead of letting the text box wrap it: "The four AI interfaces: a
  practical guide" breaks after the colon, so the second line is "a
  practical guide", not "practical guide" with "a" stranded above.
  Implementation: `paragraph.add_line_break()` between the two runs, and the
  title font size is the minimum of the per-line fits — see
  `style/STYLE.md` rule 20 for the full rule.
- **Progress marker on section openers (rule 19, nice to have).** When a
  deck walks through an ordered sequence of stages (four interfaces, five
  pipeline steps), each section-opener slide shows the sequence as a
  vertical strip of native shapes in the picture column, all stages listed,
  the current one filled in the template accent colour with white text, the
  rest outlined in muted grey with grey text, small arrows between boxes,
  labels at 20pt or more, identical geometry on every opener. The strip
  counts as a key figure for rule 16 and replaces that slide's decorative
  picture; an opener that already carries an information-carrying figure
  skips it. Try it whenever the deck has such a sequence, drop it when the
  sequence isn't the deck's spine — `add_progress_strip` in
  `scripts/build_deck.py` is the optional helper; see `style/STYLE.md`
  rule 19 for the full rule.

## Slide size

Slides are 16:9 (13.333 x 7.5 in). The institute template you place in
`template/` (see `template/README.md`) must be 16:9; never ship 4:3.

## Workflow

1. Copy `template/institute.pptx` (your own 16:9 template, stripped to just the
   two layouts — see `template/README.md`; none is shipped here) — never
   edit it in place.
2. Copy `scripts/build_deck.py` into your working directory (or run it in
   place) and replace `TITLE`/`AUTHOR`/`DATE_LINE`/`SLIDES` with the real deck
   content. Keep the helpers (`add_hierarchical_bullets`, `add_visual`,
   `add_live_demo`, etc.) as-is unless the layout itself needs to change.
3. Run it with a `pptx`-capable interpreter, e.g.:
   `python3 -c "import pptx"` to confirm, then `python3 scripts/build_deck.py`.
   It writes `deck.pptx` into the current directory.
4. Render every slide to check for wraps/overlaps before showing the author:

   ```text
   soffice --headless --convert-to pdf deck.pptx
   pdftoppm -r 80 -png deck.pdf slide
   ```

   View each `slide-N.png`. Fix any wrapped bullet or overlap per Rule 6 above,
   rebuild, and re-render until every slide is clean.
5. Open the finished deck for the author with LibreOffice Impress (Wayland env vars
   the terminal lacks, per `amg-open-img-ubuntu`):

   ```text
   export WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 \
     DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
   setsid soffice --impress deck.pptx &>/dev/null &
   ```

## Side illustrations

Generate each side illustration with `aii-concept-fig-gen` in `--edit` mode,
passing `assets/style-ref.jpeg` as the style reference (pastel 3D isometric
card look — see the example in `style/STYLE.md` and the rendered sample this
skill was built from). Don't hand-draw placeholder boxes into the final deck;
just set `visual_image` to the path you intend to generate and generate the
real image whenever it's ready. A missing figure file leaves the slide
text-only: no placeholder box, no reserved space; the figure is picked up
automatically once the file exists. `add_visual()` only draws its old
grey-placeholder-box fallback when a slide explicitly opts in with
`visual_placeholder: True`, for the rare case you want a visible marker
while deliberately iterating without the real image yet.

## Speaker notes

Do not add speaker notes unless the author explicitly asks for them.
