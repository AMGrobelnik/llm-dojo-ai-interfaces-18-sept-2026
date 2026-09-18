#!/usr/bin/env python3
"""Build an institute-style deck from template/institute.pptx.

Standalone example: 2 slides driven by the SLIDES data structure below.
Copy this file into your own project and edit TEMPLATE / OUT / SLIDES;
keep the helper functions as-is unless the layout genuinely needs to change.

Re-runnable: always overwrites the output cleanly. The template is only
ever *copied*, never modified in place.
"""

import copy
import io
import itertools
import shutil

# ---- Fit-up helper -------------------------------------------------------
# The author's rule: write the text minimal first (one line per bullet,
# self-contained), then make it as big as fits: scale each slide's fonts up
# until the layout is full, keep the hierarchy (title clearly larger than the
# rest), never comically big. Uniform content-slide title size across the deck.
#
# Measures with the template's *real* font file (not a generic default) so
# the PIL width estimate matches what LibreOffice actually renders.
import subprocess as _subprocess
from math import ceil
from pathlib import Path

from PIL import Image
from PIL import ImageFont as _ImageFont
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.presentation import Presentation as PresentationDoc
from pptx.util import Emu, Pt

EMU_PER_IN = 914400
PX_PER_IN = 96  # PIL measurement is done at 96dpi-equivalent px

BODY_FONT_FAMILY = "Calibri"  # theme +mn-lt -> master bodyStyle default
TITLE_FONT_FAMILY = "Calibri Light"  # theme +mj-lt -> master titleStyle default

LEVEL1_PT_RANGE = (24, 34)
LEVEL2_PT_RANGE = (20, 30)
LEVEL3_PT_RANGE = (18, 26)
LEVEL2_DELTA = 4  # level2 = level1 - 4pt, fixed ratio (never solved independently)
LEVEL3_DELTA = 4  # level3 = level2 - 4pt, same fixed ratio
# Every body line is a bullet at one of three levels, and each level's TEXT
# starts INDENT_STEP further right than the level above it, with the bullet
# glyph hanging in that step. 0.5in is the smallest step that reads as a step
# at a glance (style/STYLE.md "no standalone headings inside the body").
INDENT_STEP = 457200  # 0.5in
LEVEL_MAR_L = {0: INDENT_STEP, 1: 2 * INDENT_STEP, 2: 3 * INDENT_STEP}
LEVEL_BULLET_CHAR = {0: "\u25cf", 1: "\u2022", 2: "\u2013"}
FIT_SAFETY = 0.97  # shrink the column width by this factor before comparing

# OOXML default text-frame inset (0.1in each side) applies to every box here
# (body placeholder and plain textboxes alike) since none of this template's
# bodyPr elements override lIns/rIns — subtract it before comparing widths.
TEXT_INSET_EMU = 91440

# Master bodyStyle paragraph spacing (fixed points, independent of font size):
# lvl1 spcBef=7.51pt, lvl2 spcBef=3.75pt (ppt/slideMasters/slideMaster1.xml).
SPC_BEFORE_PT = {0: 7.51, 1: 3.75, 2: 3.0}
LINE_HEIGHT_MULT = 1.2  # ~OOXML line height per one-line paragraph

_FONT_FILE_CACHE = {}
_FONT_OBJ_CACHE = {}


def _font_file(family: str, bold: bool) -> str:
    key = (family, bold)
    if key not in _FONT_FILE_CACHE:
        query = f"{family}:bold" if bold else family
        out = _subprocess.run(
            ["fc-match", "-f", "%{file}", query],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        _FONT_FILE_CACHE[key] = out.strip()
    return _FONT_FILE_CACHE[key]


def _font(family: str, bold: bool, pt_size: float):
    key = (family, bold, round(pt_size, 1))
    if key not in _FONT_OBJ_CACHE:
        path = _font_file(family, bold)
        px = max(1, round(pt_size * PX_PER_IN / 72))
        _FONT_OBJ_CACHE[key] = _ImageFont.truetype(path, px)
    return _FONT_OBJ_CACHE[key]


def _text_width_px(
    text: str, pt_size: float, bold: bool = False, family: str = BODY_FONT_FAMILY
) -> float:
    if not text:
        return 0.0
    return _font(family, bold, pt_size).getlength(text)


def _emu_to_px(emu: float) -> float:
    return emu / EMU_PER_IN * PX_PER_IN


def _px_to_emu(px: float) -> float:
    return px / PX_PER_IN * EMU_PER_IN


def _pt_to_emu(pt_size: float) -> float:
    return pt_size / 72 * EMU_PER_IN


class FitRun:
    """One run on a fitted line: `text` at `bold` weight."""

    __slots__ = ("bold", "text")

    def __init__(self, text, bold=False):
        self.text = text
        self.bold = bold


class FitParagraph:
    """One rendered (single) line: `level` selects level1 vs level2 pt size
    and spacing; `runs` are the text runs concatenated on that one line."""

    __slots__ = ("level", "runs")

    def __init__(self, runs, level=0):
        self.runs = runs
        self.level = level


def _level3_pt(level1_pt: float) -> float:
    """Level-3 size, derived from level 1 the same way level 2 is: one fixed
    step down, clamped to LEVEL3_PT_RANGE. Never solved independently, so
    level1 >= level2 >= level3 always holds."""
    lo, hi = LEVEL3_PT_RANGE
    return max(lo, min(hi, level1_pt - LEVEL2_DELTA - LEVEL3_DELTA))


def _level_pt(level: int, level1_pt: float, level2_pt: float) -> float:
    if level == 0:
        return level1_pt
    if level == 1:
        return level2_pt
    return _level3_pt(level1_pt)


def _paragraph_fits(
    p: "FitParagraph", level1_pt: float, level2_pt: float, col_width_px: float, family: str
) -> bool:
    pt_size = _level_pt(p.level, level1_pt, level2_pt)
    # A deeper level starts further right, so it has that much less room.
    avail = col_width_px - _emu_to_px(LEVEL_MAR_L[p.level])
    width = sum(_text_width_px(r.text, pt_size, bold=r.bold, family=family) for r in p.runs)
    return width <= avail


def _block_height_emu(paragraphs, level1_pt: float, level2_pt: float) -> float:
    total_pt = 0.0
    for p in paragraphs:
        pt_size = _level_pt(p.level, level1_pt, level2_pt)
        total_pt += SPC_BEFORE_PT.get(p.level, SPC_BEFORE_PT[2])
        total_pt += pt_size * LINE_HEIGHT_MULT
    return _pt_to_emu(total_pt)


def fit_body_pt(
    paragraphs,
    col_width_emu: float,
    avail_height_emu: float,
    family: str = BODY_FONT_FAMILY,
    safety: float = FIT_SAFETY,
    level1_range=LEVEL1_PT_RANGE,
    level2_range=LEVEL2_PT_RANGE,
    level2_delta=LEVEL2_DELTA,
):
    """Largest (level1_pt, level2_pt, fits) in range (1pt steps) such that
    every paragraph's one line fits the column width and the whole block's
    total line height fits `avail_height_emu`. level2 = level1 - level2_delta,
    clamped to level2_range (kept as one fixed ratio, never solved alone).
    `fits` is True only when a size in range genuinely satisfies both
    constraints; when nothing in range does, falls back to the range floor
    with fits=False (caller must not treat that floor size as a real fit)."""
    col_width_px = _emu_to_px(col_width_emu - 2 * TEXT_INSET_EMU) * safety
    lo, hi = level1_range
    l2_lo, l2_hi = level2_range
    for level1_pt in range(hi, lo - 1, -1):
        level2_pt = max(l2_lo, min(l2_hi, level1_pt - level2_delta))
        if all(_paragraph_fits(p, level1_pt, level2_pt, col_width_px, family) for p in paragraphs):
            if _block_height_emu(paragraphs, level1_pt, level2_pt) <= avail_height_emu:
                return level1_pt, level2_pt, True
    return lo, max(l2_lo, min(l2_hi, lo - level2_delta)), False


def _assert_no_wrap(
    paragraphs,
    col_width_emu,
    level1_pt,
    level2_pt,
    slide_label,
    family=BODY_FONT_FAMILY,
    safety=FIT_SAFETY,
):
    """One bullet = one line: a rendered line that does not fit its own box
    would wrap, and the fit-up must never accept that. Raises instead of
    shipping a wrapped bullet — the fix is content (reword it shorter), not a
    smaller slide."""
    col_width_px = _emu_to_px(col_width_emu - 2 * TEXT_INSET_EMU) * safety
    for p in paragraphs:
        if not _paragraph_fits(p, level1_pt, level2_pt, col_width_px, family):
            text = "".join(r.text for r in p.runs)
            raise AssertionError(
                f"{slide_label}: level-{p.level + 1} line would wrap at "
                f"{_level_pt(p.level, level1_pt, level2_pt)}pt in a "
                f"{col_width_emu / EMU_PER_IN:.2f}in column - reword it: {text!r}"
            )


def _fits_width(
    paragraphs, col_width_emu, level1_pt, level2_pt, family=BODY_FONT_FAMILY, safety=FIT_SAFETY
):
    """Whether every paragraph's one line fits `col_width_emu` at the given
    sizes — used to break ties when fit_body_pt had to fall back on both
    candidates (neither fully fits): a width overflow means a visible
    mid-bullet wrap, strictly worse than a candidate that is merely a bit
    short on its (conservative) reserved height."""
    col_width_px = _emu_to_px(col_width_emu - 2 * TEXT_INSET_EMU) * safety
    return all(_paragraph_fits(p, level1_pt, level2_pt, col_width_px, family) for p in paragraphs)


def _wrap_line_count(
    text: str, pt_size: float, box_width_px: float, family: str, bold: bool
) -> int:
    words = text.split()
    if not words:
        return 0
    lines = 1
    cur = words[0]
    for w in words[1:]:
        cand = cur + " " + w
        if _text_width_px(cand, pt_size, bold=bold, family=family) <= box_width_px:
            cur = cand
        else:
            lines += 1
            cur = w
    return lines


def fit_title_pt(
    text: str,
    box_width_emu: float,
    pt_range,
    max_lines: int = 1,
    bold: bool = True,
    family: str = TITLE_FONT_FAMILY,
    safety: float = FIT_SAFETY,
):
    """Largest pt in `pt_range` (1pt steps) such that `text`, greedily
    word-wrapped at `box_width_emu`, needs at most `max_lines` lines."""
    box_width_px = _emu_to_px(box_width_emu - 2 * TEXT_INSET_EMU) * safety
    lo, hi = pt_range
    for pt_size in range(hi, lo - 1, -1):
        if _wrap_line_count(text, pt_size, box_width_px, family, bold) <= max_lines:
            return pt_size
    return lo


HERE = Path(__file__).resolve().parent
SKILL_DIR = HERE.parent
TEMPLATE = SKILL_DIR / "template" / "institute.pptx"
WORK = Path.cwd() / "deck_work" / "deck_base.pptx"
OUT = Path.cwd() / "deck.pptx"

TITLE_BLUE = RGBColor(0x37, 0x71, 0xB3)
NAVY = RGBColor(0x00, 0x20, 0x60)
GREY = RGBColor(0x80, 0x80, 0x80)
DATE_GREY = RGBColor(0x59, 0x59, 0x59)
RED = RGBColor(0xC0, 0x00, 0x00)  # limitations/downsides
GREEN = RGBColor(0x70, 0xAD, 0x47)  # theme accent6 — strengths/positives

# ---- Example content: replace with your own slides -----------------------
TITLE = "Example Institute Deck"
AUTHOR = "The Author"
DATE_LINE = "Example Talk, 15 Sep 2026"

SLIDES = [
    {
        "title": "1. Example topic",
        "headline": "One clear claim the slide argues for",
        "bullets": [
            ("Who:", NAVY, "everyone, mostly non-technical", []),
            (
                "Good for:",
                GREEN,
                "talking, thinking, writing",
                ["one-off pictures, charts, mock-ups"],
            ),
            ("Limits:", RED, "no access to your files", ["output = download link or in-chat view"]),
        ],
        "visual_caption": "illustration: generate with aii-concept-fig-gen",
        "visual_image": None,  # Path to a PNG/JPEG, or None to leave the slide text-only
        "live_demo": True,
    },
    {
        "title": "2. Second example topic",
        "headline": "A second claim, one idea per slide",
        "bullets": [
            ("What:", NAVY, "full agent in a chat UI", []),
            ("Costs:", RED, "far more quota than plain chat", []),
        ],
        "visual_caption": "illustration: generate with aii-concept-fig-gen",
        "visual_image": None,
        "live_demo": False,
    },
]

# Slide is 16:9 (13.333in x 7.5in = 12192000 x 6858000 EMU) — see template/institute.pptx.
SLIDE_W = 12192000

# Body placeholder default geometry (from slideLayout2.xml / slideMaster1.xml), in EMU.
# Matches the author's own 16:9 decks (measured with python-pptx: deck-a.pptx,
# deck-b.pptx): body top≈2.0in,
# height≈4.7in — the template's placeholder geometry already agrees, unchanged.
BODY_LEFT, BODY_TOP, BODY_W = 628650, 1825626, 10934700
BODY_H_FULL = 4302042
BODY_H_WITH_DEMO = 3900000  # shrunk so a "live demo" line clears the logo row

# Body text is not fixed at 24/20pt: fit_body_pt() (see fit-up helper above)
# scales level1/level2/level3 up per-slide until the layout is full, within
# the hard caps LEVEL1_PT_RANGE=[24,34] / LEVEL2_PT_RANGE=[20,30] /
# LEVEL3_PT_RANGE=[18,26] (see
# style/STYLE.md's "text as big as possible" rule).

# Title-slide title/name/date font ranges (fit-up, see fit_title_pt): title
# stays on <=2 lines, name and date on one line each, clearly stepped down.
TITLE_PT_RANGE = (40, 54)
NAME_PT_RANGE = (26, 30)
DATE_PT_RANGE = (20, 24)

# Two-candidate bullet-slide layout: the body is one bullet list (the former
# headline is simply its first, level-1 bullet — there is no separate headline
# band any more), then either
# (A) a side picture — text column fixed at 60% of body width, picture in the
# remaining 40% (top-right, never narrower) — or (B) a picture below the text
# — text spans the full body width, picture sits bottom-right in the leftover
# space under the last bullet. COL_BOTTOM is picked per slide (see
# add_hierarchical_bullets/add_visual `live_demo`): slides without a live-demo
# line get the full body height.
# The bullet column starts where the old headline band did: that space is the
# body's now, which is why dropping the band made every slide's text bigger.
COL_TOP = 1730000
COL_BOTTOM_FULL = BODY_TOP + BODY_H_FULL
COL_BOTTOM_DEMO = BODY_TOP + BODY_H_WITH_DEMO
LEFT_COL_LEFT = BODY_LEFT
CAPTION_H = 400000

# Layout A: text column is a fixed 60% of BODY_W minus GUTTER_EMU (picture
# keeps the other 40% — never narrower; no ratio search below 60/40, the
# picture must stay big); the GUTTER_EMU sliver keeps a real >=0.3in clear
# gap between the text box's right edge and the picture's left edge.
# Layout B: text is fit against the FULL body height/width first (no picture
# reservation). Only afterwards do we check the leftover space under the last
# line, now measured down to PIC_BOTTOM_LIMIT (the footer band is fair game
# for a picture, just not for text): a picture is placed there only if that
# leftover >= MIN_PIC_LEFTOVER_B_EMU (1.6in), sized to (leftover - GUTTER_EMU)
# tall, bottom-right aligned to the body's right edge, keeping aspect ratio.
# Below that leftover threshold, B simply has no picture. This replaces an
# earlier version that reserved a fixed 1.4in for B's picture *before*
# fitting, which made width-bound slides height-bound instead and capped
# their level-1 size for no reason.
SIDE_TEXT_RATIO_A = 0.60
MIN_PIC_LEFTOVER_B_EMU = int(1.6 * EMU_PER_IN)
GUTTER_EMU = int(0.3 * EMU_PER_IN)  # min clear gap between any text box and any picture
PIC_LAYOUT_MIN_PT = 28  # A keeps its side picture down to this level-1 size
MIN_PIC_H_EMU = MIN_PIC_LEFTOVER_B_EMU - GUTTER_EMU  # 1.6in leftover minus the gutter
MAX_PIC_W_RATIO_B = 0.45  # safety cap so an extreme-aspect image never spans the full width
# Layout A's picture column may grow past its 40% share, up to this share of
# BODY_W, whenever the text still fits at the size already chosen for it —
# the picture takes every inch the text does not need, never the other way
# round (see _widened_split_a).
MAX_PIC_W_RATIO_A = 0.50

# Footer band: pictures may extend into it (down to a small margin above the
# physical slide edge, covering the right-hand footer logo/strip); text never
# does — text stays bound by COL_BOTTOM_FULL/COL_BOTTOM_DEMO as before. See
# style/STYLE.md "Pictures may use the footer band".
SLIDE_H = 6858000  # 7.5in
FOOTER_MARGIN_EMU = int(0.15 * EMU_PER_IN)
PIC_BOTTOM_LIMIT = SLIDE_H - FOOTER_MARGIN_EMU

# Slide-number footer text: small muted grey, right-aligned, on the same
# footer row as the template's bottom-left logo (top ~6.83in on this 16:9
# template). It takes the rightmost free spot on the footer row: the true
# bottom-right corner only if the template geometry leaves it free
# (TEMPLATE_CORNER_FREE — False here, since the institute template's right footer
# block/logo, see FOOTER_RIGHT_LEFT below, fills it); otherwise just left of
# that footer block. Only a picture that actually enters the footer band
# (bottom edge below LOGO_TOP) can block a footer-row slot — one that stops
# at or above LOGO_TOP never does, whatever the vertical gap. When a picture
# that does enter the band intersects that primary spot (grown by
# GUTTER_EMU on every side) the number falls back, in order, to bottom-
# centre, then a spot slid left of the picture (never left of the footer
# clear-zone start), then — if nothing is free — the primary spot anyway,
# drawn last in z-order, with a warning in the build report — see
# style/STYLE.md "Slide numbers".
SLIDE_NUM_PT = 11
SLIDE_NUM_W, SLIDE_NUM_H = (
    int(0.5 * EMU_PER_IN),
    int(0.4 * EMU_PER_IN),
)  # 2 digits at 11pt need ~0.2in
SLIDE_NUM_TOP = int(6.83 * EMU_PER_IN)
TEMPLATE_CORNER_FREE = False  # institute template's right footer block fills the true corner
SLIDE_NUM_CENTRE_LEFT = (SLIDE_W - SLIDE_NUM_W) // 2
FOOTER_CLEAR_LEFT_EMU = int(2.24 * EMU_PER_IN)  # right of the bottom-left logo
# A picture entering the footer band (bottom edge below LOGO_TOP) must keep its
# left edge at or right of this line: past the bottom-left logo
# (FOOTER_CLEAR_LEFT_EMU), the number box (SLIDE_NUM_W), and a gutter — so the
# number's slide-left fallback slot always exists and the picture never
# touches the left logo. A candidate that would go further left is narrowed
# to this line instead; when that drops it below MIN_PIC_H_EMU, the LOGO_TOP
# variant (full width allowed there) competes in the largest-picture
# selection instead. See style/STYLE.md "Slide numbers" and "Pictures anchor
# bottom-right".
FOOTER_BAND_MIN_LEFT_EMU = FOOTER_CLEAR_LEFT_EMU + SLIDE_NUM_W + GUTTER_EMU

# Title-slide big centred title box: fixed width, recentred on the (16:9) slide.
TITLE_BOX_W, TITLE_BOX_H = 7043830, 2057400
TITLE_BOX_LEFT, TITLE_BOX_TOP = (SLIDE_W - TITLE_BOX_W) // 2, 1550000
SUBTITLE_BOX_W = BODY_W  # subTitle placeholder width, unchanged/inherited


def fresh_copy() -> None:
    WORK.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TEMPLATE, WORK)


def delete_all_slides(prs: PresentationDoc) -> None:
    """Drop every slide (and, transitively, any media/notes/comments only they use)."""
    sld_id_lst = prs.slides._sldIdLst
    for sld in list(sld_id_lst):
        prs.part.rels.pop(sld.rId)
        sld_id_lst.remove(sld)


def get_body(slide):
    for shp in slide.placeholders:
        if shp.placeholder_format.idx == 1:
            return shp
    raise RuntimeError("no body placeholder (idx=1) on slide")


def _style_bullet(p, level: int) -> None:
    """Give paragraph `p` level `level`'s own hanging indent, bullet glyph and
    space-before, written into the XML rather than inherited from the master:
    the fit-up measures against LEVEL_MAR_L/SPC_BEFORE_PT, so the rendered
    paragraph has to use exactly those numbers."""
    p.level = level
    pPr = p._p.get_or_add_pPr()
    pPr.set("marL", str(LEVEL_MAR_L[level]))
    pPr.set("indent", str(-INDENT_STEP))  # hanging: the glyph sits in the step
    spc_bef = pPr.makeelement(qn("a:spcBef"), {})
    spc_bef.append(pPr.makeelement(qn("a:spcPts"), {"val": str(int(SPC_BEFORE_PT[level] * 100))}))
    pPr.insert(0, spc_bef)
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": LEVEL_BULLET_CHAR[level]}))


def add_hierarchical_bullets(
    slide, headline, rows, level1_pt, level2_pt, live_demo=False, col_w=None
):
    """The slide body: ONE bullet list, three levels deep.

    Level 1 is the section line (`headline`, bold navy) — there are no
    standalone headings inside the body, see style/STYLE.md. Level 2 is one
    `rows` entry (bold colour-coded lead phrase + plain tail), level 3 its
    sub-bullets. Each level indents 0.5in further than the one above it.

    `rows` is a list of (lead, colour, tail, subs), `subs` a list of plain
    sub-bullet strings. One bullet = one line — reword before shrinking fonts.
    Pass `live_demo=True` to match a slide that also calls add_live_demo, so the
    column doesn't run into that line. `col_w` lets a slide use the layout-A
    (side picture) text-column width or the layout-B (picture below) full body
    width (see _choose_layout); defaults to layout A's 60% of BODY_W.
    """
    if col_w is None:
        col_w = int(BODY_W * SIDE_TEXT_RATIO_A)
    col_bottom = COL_BOTTOM_DEMO if live_demo else COL_BOTTOM_FULL
    level3_pt = _level3_pt(level1_pt)
    body = get_body(slide)
    body.left, body.top = Emu(LEFT_COL_LEFT), Emu(COL_TOP)
    body.width, body.height = Emu(col_w), Emu(col_bottom - COL_TOP)
    tf = body.text_frame
    tf.clear()
    paragraphs = iter([tf.paragraphs[0]])

    def _next_p():
        return next(paragraphs, None) or tf.add_paragraph()

    if headline:
        p = _next_p()
        _style_bullet(p, 0)
        r = p.add_run()
        r.text = headline
        r.font.bold = True
        r.font.color.rgb = NAVY
        r.font.size = Pt(level1_pt)
    for lead, colour, tail, subs in rows:
        p = _next_p()
        _style_bullet(p, 1)
        r_lead = p.add_run()
        r_lead.text = lead
        r_lead.font.bold = True
        r_lead.font.color.rgb = colour
        r_lead.font.size = Pt(level2_pt)
        r_tail = p.add_run()
        r_tail.text = " " + tail
        r_tail.font.size = Pt(level2_pt)
        for sub in subs:
            sp = _next_p()
            _style_bullet(sp, 2)
            r_sub = sp.add_run()
            r_sub.text = sub
            r_sub.font.size = Pt(level3_pt)
    return body


# Flat multi-column list: one level-1 headline + a long flat list of short
# level-2 items in up to 3 newspaper-order columns. Columns are NOT forced to
# equal width: a single long label in one column would otherwise force every
# column down to that width even though the others hold only short labels.
# Instead each column is sized to its own longest item at the candidate size,
# and the fit only fails on width once the columns' own minimum widths plus
# their gutters can no longer sum to the body width — so the chosen size is
# bound by whichever actually limits it (that column-sum width, or the
# tallest column's height), never by an artificial equal share.
FLAT_LEVEL2_PT_RANGE = (16, LEVEL2_PT_RANGE[1])


def _split_flat_columns(items, n_cols):
    """Newspaper order: fill column 1 top-to-bottom, then column 2, etc."""
    if not items:
        return [[] for _ in range(n_cols)]
    rows_per_col = -(-len(items) // n_cols)  # ceil
    return [items[i * rows_per_col : (i + 1) * rows_per_col] for i in range(n_cols)]


def _flat_column_min_widths_emu(columns, level2_pt, family=BODY_FONT_FAMILY, safety=FIT_SAFETY):
    """Each column's minimum EMU width at `level2_pt`: its own longest item's
    measured text width (real font metrics), inflated back through the same
    margins/safety factor fit_body_pt's width check uses, so a short column
    never has to pay for a long label sitting in another one."""
    widths = []
    for col in columns:
        if not col:
            widths.append(0)
            continue
        max_px = max(_text_width_px(item, level2_pt, family=family) for item in col)
        widths.append(int(_px_to_emu(max_px / safety) + 2 * TEXT_INSET_EMU + LEVEL_MAR_L[1]))
    return widths


def fit_flat_columns_pt(
    items,
    headline,
    n_cols,
    avail_width_emu,
    avail_height_emu,
    gutter=GUTTER_EMU,
    family=BODY_FONT_FAMILY,
    safety=FIT_SAFETY,
    level1_range=LEVEL1_PT_RANGE,
    level2_range=FLAT_LEVEL2_PT_RANGE,
    level2_delta=LEVEL2_DELTA,
):
    """Largest level2_pt (1pt steps) at which the `n_cols` columns' own
    minimum widths (see _flat_column_min_widths_emu) plus (n_cols-1) gutters
    fit `avail_width_emu`, the headline (level1, paired by the usual fixed
    delta) fits full width, and the headline plus the tallest column's items
    fit `avail_height_emu`. Returns (level1_pt, level2_pt, fits) — `fits`
    is True when a size in range genuinely satisfies both constraints; when
    nothing in range does, falls back to the range floor with fits=False so
    the caller can tell a real fit from a forced fallback (see
    add_flat_columns_slides, which splits into two slides on fits=False)."""
    columns = _split_flat_columns(items, n_cols)
    rows_per_col = max((len(c) for c in columns), default=0)
    headline_w_px = _emu_to_px(avail_width_emu - 2 * TEXT_INSET_EMU - LEVEL_MAR_L[0]) * safety
    l1_lo, l1_hi = level1_range
    l2_lo, l2_hi = level2_range

    def _level1_for(level2_pt):
        return max(l1_lo, min(l1_hi, level2_pt + level2_delta))

    for level2_pt in range(l2_hi, l2_lo - 1, -1):
        level1_pt = _level1_for(level2_pt)
        if _text_width_px(headline, level1_pt, bold=True, family=family) > headline_w_px:
            continue
        col_widths = _flat_column_min_widths_emu(columns, level2_pt, family, safety)
        if sum(col_widths) + (n_cols - 1) * gutter > avail_width_emu:
            continue
        headline_h = _pt_to_emu(SPC_BEFORE_PT[0] + level1_pt * LINE_HEIGHT_MULT)
        rows_h = _pt_to_emu(rows_per_col * (SPC_BEFORE_PT[1] + level2_pt * LINE_HEIGHT_MULT))
        if headline_h + rows_h <= avail_height_emu:
            return level1_pt, level2_pt, True
    return _level1_for(l2_lo), l2_lo, False


def add_flat_columns_bullets(
    slide,
    headline,
    items,
    level1_pt,
    level2_pt,
    n_cols=3,
    col_gutter=GUTTER_EMU,
    family=BODY_FONT_FAMILY,
    safety=FIT_SAFETY,
):
    """The slide body: one level-1 headline line (bold navy, full body
    width), then `items` as level-2 bullets (bullet glyph/colour/font as
    elsewhere) in `n_cols` side-by-side text boxes below it, newspaper order.
    Each column is sized to its own longest item at `level2_pt` (matching
    fit_flat_columns_pt's width check), then any left-over body width is
    spread across the columns proportionally so they still span edge-to-edge
    like every other slide's body."""
    body = get_body(slide)
    body.left, body.top, body.width = Emu(BODY_LEFT), Emu(COL_TOP), Emu(BODY_W)
    headline_h = int(_pt_to_emu(SPC_BEFORE_PT[0] + level1_pt * LINE_HEIGHT_MULT))
    body.height = Emu(headline_h)
    tf = body.text_frame
    tf.clear()
    p = tf.paragraphs[0]
    _style_bullet(p, 0)
    r = p.add_run()
    r.text = headline
    r.font.bold = True
    r.font.color.rgb = NAVY
    r.font.size = Pt(level1_pt)

    columns = _split_flat_columns(items, n_cols)
    col_widths = _flat_column_min_widths_emu(columns, level2_pt, family, safety)
    min_total = sum(col_widths)
    slack = BODY_W - min_total - (n_cols - 1) * col_gutter
    if slack > 0 and min_total > 0:
        col_widths = [w + int(slack * w / min_total) if w else 0 for w in col_widths]

    cols_top = COL_TOP + headline_h
    left = BODY_LEFT
    for col_items, w in zip(columns, col_widths, strict=True):
        if col_items:
            box = slide.shapes.add_textbox(
                Emu(left), Emu(cols_top), Emu(w), Emu(COL_BOTTOM_FULL - cols_top)
            )
            tf_c = box.text_frame
            tf_c.word_wrap = True
            for j, text in enumerate(col_items):
                pc = tf_c.paragraphs[0] if j == 0 else tf_c.add_paragraph()
                _style_bullet(pc, 1)
                rc = pc.add_run()
                rc.text = text
                rc.font.size = Pt(level2_pt)
        left += w + col_gutter
    return body


def add_flat_columns_slides(
    prs,
    layout,
    headline,
    items,
    n_cols=3,
    col_gutter=GUTTER_EMU,
    family=BODY_FONT_FAMILY,
    safety=FIT_SAFETY,
):
    """Add one "flat multi-column list" slide for `headline` + `items`, or —
    when the list does not fit even at the FLAT_LEVEL2_PT_RANGE floor — two,
    titled "<headline> (1/2)" and "<headline> (2/2)" with `items` split in
    half. Adds each slide (title, slide number, body) itself, matching the
    numbering build() does for every other slide, and returns the slides
    created, in order. This is the entry point for the layout described in
    style/STYLE.md "Flat multi-column list"; fit_flat_columns_pt and
    add_flat_columns_bullets are its building blocks for callers that need a
    single slide sized/drawn separately (e.g. a caller-controlled split)."""
    body_h = COL_BOTTOM_FULL - COL_TOP
    level1_pt, level2_pt, fits = fit_flat_columns_pt(
        items, headline, n_cols, BODY_W, body_h, gutter=col_gutter, family=family, safety=safety
    )
    if fits:
        groups = [(headline, items, level1_pt, level2_pt)]
    else:
        mid = -(-len(items) // 2)  # ceil: split roughly in half
        groups = []
        for suffix, group_items in ((" (1/2)", items[:mid]), (" (2/2)", items[mid:])):
            title = f"{headline}{suffix}"
            l1, l2, group_fits = fit_flat_columns_pt(
                group_items,
                title,
                n_cols,
                BODY_W,
                body_h,
                gutter=col_gutter,
                family=family,
                safety=safety,
            )
            if not group_fits:
                raise AssertionError(
                    f"{title!r}: {len(group_items)} items do not fit at the "
                    f"{FLAT_LEVEL2_PT_RANGE[0]}pt floor even split in half - "
                    "shorten the items or drop a column"
                )
            groups.append((title, group_items, l1, l2))

    slides = []
    for title, group_items, l1, l2 in groups:
        slide = prs.slides.add_slide(layout)
        slide.shapes.title.text_frame.text = title
        add_slide_number(slide, len(prs.slides))
        add_flat_columns_bullets(
            slide,
            title,
            group_items,
            l1,
            l2,
            n_cols=n_cols,
            col_gutter=col_gutter,
            family=family,
            safety=safety,
        )
        slides.append(slide)
    return slides


_RESAMPLE_DPI = 300
_RESAMPLE_CACHE: dict[Path, tuple[int, bytes]] = {}


def _resampled_image(path: Path, width_in: float, height_in: float) -> io.BytesIO:
    """Downsample the picture at `path` to the pixel size it is actually
    displayed at (`width_in` x `height_in`), floored at 300 dpi on the long
    side and never upscaled past the source resolution, with Pillow LANCZOS.
    PNGs stay PNG (lossless, optimize=True); JPEGs stay JPEG (quality=92,
    subsampling=0). Cached per resolved source path so a picture reused at a
    smaller size elsewhere gets the bytes already produced for its largest
    placement — python-pptx dedupes identical blobs, keeping the file
    smaller. Keeps decks under the 25 MB limit without visible quality loss;
    source figures on disk are never touched."""
    path = path.resolve()
    target_long_px = ceil(max(width_in, height_in) * _RESAMPLE_DPI)
    cached = _RESAMPLE_CACHE.get(path)
    if cached is not None and cached[0] >= target_long_px:
        return io.BytesIO(cached[1])

    suffix = path.suffix.lower()
    with Image.open(path) as im:
        iw, ih = im.size
        orig_long = max(iw, ih)
        long_px = min(target_long_px, orig_long)  # never upscale
        scale = long_px / orig_long
        new_size = (max(1, round(iw * scale)), max(1, round(ih * scale)))
        resized = im.resize(new_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        try:
            if suffix == ".png":
                resized.save(buf, format="PNG", optimize=True)
            elif suffix in (".jpg", ".jpeg"):
                resized.convert("RGB").save(buf, format="JPEG", quality=92, subsampling=0)
            else:
                raise ValueError(f"unsupported image format for resampling: {path}")
        except OSError as exc:
            raise ValueError(f"failed to re-encode image {path}: {exc}") from exc

    data = buf.getvalue()
    _RESAMPLE_CACHE[path] = (long_px, data)
    return io.BytesIO(data)


def add_visual(
    slide, caption_text, image_path, left, top, max_w, max_h, valign="top", placeholder=False
):
    """Place `image_path` aspect-preserved inside the box (left, top, max_w,
    max_h) if it exists at build time — right-aligned horizontally always;
    vertically top-aligned (layout A, valign="top") or bottom-aligned
    (layout B, valign="bottom") per `valign`. A missing figure file leaves
    the slide text-only by default: no placeholder box, no caption, nothing
    drawn in the box — the figure is picked up automatically once the file
    exists. Pass `placeholder=True` to opt into the old behaviour instead: a
    light-grey placeholder box + caption using the same (left, top, max_w,
    max_h) box, useful only while deliberately iterating without the real
    image yet. See _choose_layout / _pic_geom for how the box is computed
    per slide."""
    if image_path is not None and Path(image_path).exists():
        with Image.open(image_path) as im:
            iw, ih = im.size
        aspect = iw / ih
        cand_w = max_h * aspect
        w, h = (cand_w, max_h) if cand_w <= max_w else (max_w, max_w / aspect)
        pic_left = left + max_w - w  # right-aligned
        pic_top = top if valign == "top" else top + max_h - h
        image_stream = _resampled_image(Path(image_path), w / EMU_PER_IN, h / EMU_PER_IN)
        return slide.shapes.add_picture(
            image_stream,
            Emu(int(pic_left)),
            Emu(int(pic_top)),
            width=Emu(int(w)),
            height=Emu(int(h)),
        )

    if not placeholder:
        return None

    box_h = max(max_h - CAPTION_H - 100000, 0)
    box = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Emu(int(left)), Emu(int(top)), Emu(int(max_w)), Emu(int(box_h))
    )
    box.fill.solid()
    box.fill.fore_color.rgb = RGBColor(0xEC, 0xEE, 0xF1)
    box.line.color.rgb = RGBColor(0xAA, 0xAA, 0xAA)
    box.line.width = Pt(1)
    box.shadow.inherit = False
    box.text_frame.word_wrap = True

    caption = slide.shapes.add_textbox(
        Emu(int(left)), Emu(int(top + box_h + 100000)), Emu(int(max_w)), Emu(CAPTION_H)
    )
    tf = caption.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = caption_text
    r.font.size = Pt(12)
    r.font.italic = True
    r.font.color.rgb = GREY
    r.font.name = "Calibri"
    return box, caption


def add_progress_strip(slide, stages, stage_index, left, top, col_w, col_h, *, label_pt=20):
    """Optional (style/STYLE.md rule 19): a vertical strip of `len(stages)`
    boxes in the picture column, top to bottom, the current one
    (`stage_index`) filled in TITLE_BLUE with white text, the rest outlined
    muted grey with grey text, small down-arrows in the gaps. Use in place
    of `add_visual` on a section-opener slide whose deck walks through an
    ordered sequence of stages (this replaces that slide's decorative
    picture and counts as `key_figure=True` for rule 16 — identical
    geometry on every opener, so no per-opener re-tuning). Skip it on any
    opener that already carries an information-carrying figure."""
    n = len(stages)
    gap = int(0.3 * EMU_PER_IN)
    box_h = (col_h - (n - 1) * gap) // n
    arrow_w, arrow_h = int(0.22 * EMU_PER_IN), int(0.24 * EMU_PER_IN)
    shapes = []
    for i, label in enumerate(stages):
        box_top = top + i * (box_h + gap)
        current = i == stage_index
        box = slide.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE,
            Emu(int(left)),
            Emu(int(box_top)),
            Emu(int(col_w)),
            Emu(int(box_h)),
        )
        box.shadow.inherit = False
        box.fill.solid()
        box.fill.fore_color.rgb = TITLE_BLUE if current else RGBColor(0xFF, 0xFF, 0xFF)
        box.line.color.rgb = TITLE_BLUE if current else GREY
        box.line.width = Pt(1.5)
        tf = box.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = label
        r.font.size = Pt(label_pt)
        r.font.bold = True
        r.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF) if current else GREY
        shapes.append(box)
        if i < n - 1:
            arrow = slide.shapes.add_shape(
                MSO_SHAPE.DOWN_ARROW,
                Emu(int(left + (col_w - arrow_w) // 2)),
                Emu(int(box_top + box_h + (gap - arrow_h) // 2)),
                Emu(int(arrow_w)),
                Emu(int(arrow_h)),
            )
            arrow.shadow.inherit = False
            arrow.fill.solid()
            arrow.fill.fore_color.rgb = GREY
            arrow.line.fill.background()
            shapes.append(arrow)
    return shapes


def add_live_demo(slide):
    box = slide.shapes.add_textbox(Emu(BODY_LEFT), Emu(5820000), Emu(3500000), Emu(300000))
    tf = box.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = "→ live demo"
    r.font.size = Pt(13)
    r.font.italic = True
    r.font.color.rgb = GREY
    r.font.name = "Calibri"
    return box


def _picture_rect(picture):
    """(left, top, width, height) in EMU for a shape returned by add_visual
    (a Picture, or a (box, caption) pair in placeholder mode), or None when
    add_visual drew nothing."""
    if picture is None:
        return None
    shp = picture[0] if isinstance(picture, tuple) else picture
    return shp.left, shp.top, shp.width, shp.height


def _clear_of_picture(box, pic_rect, pad):
    """True if `box` ((left, top, w, h) in EMU), grown by `pad` on every
    side, does not overlap `pic_rect` — the same >=pad gap kept between text
    and pictures elsewhere in the deck."""
    bl, bt, bw, bh = box
    pl, pt, pw, ph = pic_rect
    gl, gt, gr, gb = bl - pad, bt - pad, bl + bw + pad, bt + bh + pad
    pr, pb = pl + pw, pt + ph
    return gr <= pl or pr <= gl or gb <= pt or pb <= gt


def add_slide_number(slide, number, *, picture=None):
    """Small muted-grey slide number, right-aligned text, on the same footer
    row as the template's bottom-left logo. Takes the rightmost free spot on
    the footer row: the true bottom-right corner if TEMPLATE_CORNER_FREE,
    else right edge FOOTER_RIGHT_LEFT - GUTTER_EMU, just left of the
    template's right footer block. `picture` is whatever add_visual already
    placed on this slide, if anything — always add the number AFTER the
    picture so it is topmost in z-order. A picture only ever blocks a
    footer-row slot when it actually enters the footer band (its bottom
    edge below LOGO_TOP); one that stops at or above LOGO_TOP never blocks
    the row, whatever the vertical gap to it. When a picture that does enter
    the band intersects the primary box (grown by GUTTER_EMU on every side,
    the same gap used between text and pictures elsewhere), the number
    falls back in order to: bottom-centre (if that is clear of the picture
    too), then a spot slid left of the picture (right edge GUTTER_EMU before
    the picture's left edge, never left of FOOTER_CLEAR_LEFT_EMU), then
    finally the primary spot anyway, drawn on top of the picture, with a
    warning for the build report. See style/STYLE.md "Slide numbers".
    `number` is the slide's 1-based position in the final deck. Returns
    (shape, status) where status is "right", "centre",
    f"shifted to {left_in_inches:.2f}in", or "OVER PICTURE"."""
    primary_right = (SLIDE_W if TEMPLATE_CORNER_FREE else FOOTER_RIGHT_LEFT) - GUTTER_EMU
    primary = (primary_right - SLIDE_NUM_W, SLIDE_NUM_TOP, SLIDE_NUM_W, SLIDE_NUM_H)
    pic_rect = _picture_rect(picture)
    if pic_rect is not None and pic_rect[1] + pic_rect[3] <= LOGO_TOP:
        pic_rect = None  # picture stops above the footer row; never blocks it
    left, status = primary[0], "right"
    if pic_rect is not None and not _clear_of_picture(primary, pic_rect, GUTTER_EMU):
        centre = (SLIDE_NUM_CENTRE_LEFT, SLIDE_NUM_TOP, SLIDE_NUM_W, SLIDE_NUM_H)
        shifted_left = pic_rect[0] - GUTTER_EMU - SLIDE_NUM_W
        if _clear_of_picture(centre, pic_rect, GUTTER_EMU):
            left = centre[0]
            status = "centre"
        elif shifted_left >= FOOTER_CLEAR_LEFT_EMU:
            left = shifted_left
            status = f"shifted to {left / EMU_PER_IN:.2f}in"
        else:
            status = "OVER PICTURE"
            # left stays at the primary spot; drawn last, on top of the picture.

    box = slide.shapes.add_textbox(
        Emu(int(left)), Emu(SLIDE_NUM_TOP), Emu(SLIDE_NUM_W), Emu(SLIDE_NUM_H)
    )
    box.name = "Slide Number"
    tf = box.text_frame
    tf.word_wrap = False
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.RIGHT
    r = p.add_run()
    r.text = str(number)
    r.font.size = Pt(SLIDE_NUM_PT)
    r.font.color.rgb = GREY
    r.font.name = "Calibri"
    return box, status


def _verify_slide_numbers(pptx_path) -> None:
    """Re-open the saved .pptx and assert every content slide's "Slide
    Number" textbox reads its own 1-based index (title slide = 1, excluded).
    Raises AssertionError on any mismatch or missing box."""
    prs = Presentation(str(pptx_path))
    n = 0
    for i, slide in enumerate(prs.slides, start=1):
        n = i
        if i == 1:
            continue
        box = next((shp for shp in slide.shapes if shp.name == "Slide Number"), None)
        assert box is not None, f"slide {i}: missing Slide Number textbox"
        text = box.text_frame.text.strip()
        assert text == str(i), f"slide {i}: slide-number text is {text!r}, expected {i!r}"
    print(f"Slide-number verification passed for all {n} slides.")


def _move_logos_to_content_layout(prs, layout_content):
    """Move the institute logo pictures + text labels off the slide master
    and onto the content layout only, so the title layout never has them.

    showMasterSp="0" on the title layout's cSld does NOT work here: LibreOffice
    still paints master-level shapes regardless of that flag, verified by
    rendering. Physically relocating the shapes is the only fix that survives
    a real render, per style/STYLE.md's "no logos on the title slide" rule.
    """
    master = prs.slide_masters[0]
    spTree = master.shapes._spTree
    moved = []
    for child in list(spTree):
        if child.tag not in (qn("p:sp"), qn("p:pic")):
            continue
        nvPr = child.find(f".//{qn('p:nvPr')}")
        if nvPr is not None and nvPr.get("userDrawn") == "1":
            moved.append(child)
    for el in moved:
        new_el = copy.deepcopy(el)
        if new_el.tag == qn("p:pic"):
            blip = new_el.find(qn("p:blipFill")).find(qn("a:blip"))
            old_rId = blip.get(qn("r:embed"))
            image_part = master.part.related_part(old_rId)
            new_rId = layout_content.part.relate_to(image_part, RT.IMAGE)
            blip.set(qn("r:embed"), new_rId)
        layout_content.shapes._spTree.append(new_el)
        spTree.remove(el)


def _slide_paragraphs(s):
    """FitParagraph list for one SLIDES entry: the section line first (level
    1), then each bullet (level 2) with its sub-bullets (level 3). Every body
    line is a bullet — the old separate headline band is gone, so the section
    line is fitted and indented like everything else."""
    paragraphs = []
    if s.get("headline"):
        paragraphs.append(FitParagraph([FitRun(s["headline"], bold=True)], level=0))
    for lead, _colour, tail, subs in s["bullets"]:
        paragraphs.append(
            FitParagraph([FitRun(lead, bold=True), FitRun(" " + tail, bold=False)], level=1)
        )
        for sub in subs:
            paragraphs.append(FitParagraph([FitRun(sub, bold=False)], level=2))
    return paragraphs


def _last_line_slack_emu(paragraphs, level1_pt, level2_pt):
    """Empty leading under the last rendered line: _block_height_emu gives
    every paragraph a full line box (pt * LINE_HEIGHT_MULT), but the part of
    the last box below the glyphs is blank space, so a picture underneath may
    use it. Measured out of the leftover so the >=0.3in gutter is counted
    from the last line itself, not from the bottom of its line box."""
    if not paragraphs:
        return 0.0
    pt_size = level1_pt if paragraphs[-1].level == 0 else level2_pt
    return _pt_to_emu(pt_size * (LINE_HEIGHT_MULT - 1.0))


# Right-hand footer block (the "Department for Artificial Intelligence" label
# + its logo, measured on the content layout: label left edge 10.31in, logo
# out to the slide edge). A picture that reaches into the footer band must
# cover that block completely — a narrow picture that hides only half of the
# label looks broken, so such a picture stops above the footer instead (see
# _pic_geom) and is dropped if it no longer clears MIN_PIC_LEFTOVER_B_EMU.
# FOOTER_RIGHT_LEFT also anchors the slide number's primary spot (see
# add_slide_number above) when TEMPLATE_CORNER_FREE is False.
LOGO_TOP = 6206979  # y where the master's footer logos begin (6.79in)
FOOTER_RIGHT_LEFT = int(10.31 * EMU_PER_IN)


def _pic_width_at_height(image_path, height):
    """Width `image_path` would have at `height`, aspect preserved (None when
    there is no image to measure)."""
    if image_path is None or not Path(image_path).exists():
        return None
    with Image.open(image_path) as im:
        iw, ih = im.size
    return int(height * iw / ih)


def _widened_split_a(paragraphs, image_path, level1_pt, body_h):
    """Layout A's split point: where the text column ends and the picture
    column begins.

    The default is the 60/40 split. When the picture is WIDE-bound there —
    it would still have height to spare at PIC_BOTTOM_LIMIT — the split moves
    left in 0.05in steps for as long as the text keeps fitting at the size
    already chosen for it, never past MAX_PIC_W_RATIO_A of BODY_W. Text size
    is never traded for picture size; only text WHITESPACE is."""
    split = int(BODY_W * SIDE_TEXT_RATIO_A)
    want_w = _pic_width_at_height(image_path, PIC_BOTTOM_LIMIT - COL_TOP)
    if want_w is None:
        return split
    floor = BODY_W - int(BODY_W * MAX_PIC_W_RATIO_A)
    step = int(0.05 * EMU_PER_IN)
    while split - step >= floor and BODY_W - split < want_w:
        _, _, fits = fit_body_pt(
            paragraphs, split - step - GUTTER_EMU, body_h, level1_range=(level1_pt, level1_pt)
        )
        if not fits:
            break
        split -= step
    return split


def _level2_for(level1_pt):
    """level2 = level1 - LEVEL2_DELTA, clamped to LEVEL2_PT_RANGE — the same
    fixed ratio fit_body_pt uses, exposed so the picture-area search below
    can derive level2 for a level1 it is trying that fit_body_pt itself
    never returned."""
    lo, hi = LEVEL2_PT_RANGE
    return max(lo, min(hi, level1_pt - LEVEL2_DELTA))


def _pic_area_for_level1_a(paragraphs, image_path, level1_pt, level2_pt, body_h):
    """Layout A's split point and fitted picture area at `level1_pt`, or None
    if that size no longer fits its (possibly widened) text column unwrapped
    or within body_h — defensive; by construction a level1 at or below the
    layout's own fitted maximum always still fits, since fit_body_pt already
    found that maximum from the top of the range down."""
    split = _widened_split_a(paragraphs, image_path, level1_pt, body_h)
    text_w = split - GUTTER_EMU
    if not _fits_width(paragraphs, text_w, level1_pt, level2_pt):
        return None
    if _block_height_emu(paragraphs, level1_pt, level2_pt) > body_h:
        return None
    size = _fitted_pic_size(image_path, BODY_W - split, PIC_BOTTOM_LIMIT - COL_TOP)
    area = size[0] * size[1] if size is not None else 0
    return split, area


def _pic_area_for_level1_b(paragraphs, image_path, level1_pt, level2_pt, body_h):
    """Layout B's corner picture box and fitted area at `level1_pt`, or None
    if that size no longer fits the full-width column unwrapped or within
    body_h (see _pic_area_for_level1_a — same defensive/by-construction
    note)."""
    if not _fits_width(paragraphs, BODY_W, level1_pt, level2_pt):
        return None
    if _block_height_emu(paragraphs, level1_pt, level2_pt) > body_h:
        return None
    box = _corner_pic_box(paragraphs, level1_pt, level2_pt, image_path, COL_TOP)
    area = box["max_w"] * box["max_h"] if box is not None else 0
    return box, area


def _choose_layout(paragraphs, col_bottom, slide_label, image_path=None):
    """Pick between the two content-slide-with-picture candidates:

    A — side picture: text column = 60% of BODY_W (SIDE_TEXT_RATIO_A), fit
        against the full body height.
    B — picture below text: text column = 100% of BODY_W, fit against the
        FULL body height (no picture reservation) — a picture is only placed
        afterwards, in whatever leftover space remains under the last line,
        and only if that leftover is >= 1.6in (see _pic_geom).

    Compares the two candidates' resulting level-1 pt and keeps the larger;
    a tie keeps A — UNLESS neither candidate's size genuinely fits (both hit
    fit_body_pt's range-floor fallback): a floor size that still overflows
    its column width means a visible mid-bullet wrap, strictly worse than a
    floor size that merely runs slightly past the available height, so in
    that one edge case width-fits breaks the tie instead. Prints the
    measured body height, the computed block height, and (for B) the
    leftover height and whether it earns a picture, to the build log."""
    body_h = col_bottom - COL_TOP
    level1_range = LEVEL1_PT_RANGE

    # Layout A's actual text box is narrower than the 60% split point by
    # GUTTER_EMU, so the fitted text never reaches closer than 0.3in to the
    # picture that starts at the (unshrunk) split point — see _pic_geom.
    text_w_a_split = int(BODY_W * SIDE_TEXT_RATIO_A)
    text_w_a = text_w_a_split - GUTTER_EMU
    level1_a, level2_a, fits_a = fit_body_pt(
        paragraphs, text_w_a, body_h, level1_range=level1_range
    )
    if fits_a:
        # Hand the picture any width the text does not need at this size.
        text_w_a_split = _widened_split_a(paragraphs, image_path, level1_a, body_h)
        text_w_a = text_w_a_split - GUTTER_EMU
    block_h_a = _block_height_emu(paragraphs, level1_a, level2_a)

    level1_b, level2_b, fits_b = fit_body_pt(paragraphs, BODY_W, body_h, level1_range=level1_range)
    block_h_b = _block_height_emu(paragraphs, level1_b, level2_b)
    # Picture room (not text room) reaches PIC_BOTTOM_LIMIT: the footer band
    # is fair game for a picture even though the text block above it must
    # still stay within body_h.
    leftover_b = (
        PIC_BOTTOM_LIMIT
        - COL_TOP
        - block_h_b
        + _last_line_slack_emu(paragraphs, level1_b, level2_b)
    )
    pic_b = (image_path is not None and Path(image_path).exists()) and (
        leftover_b >= MIN_PIC_LEFTOVER_B_EMU
        or _corner_pic_box(paragraphs, level1_b, level2_b, image_path, COL_TOP) is not None
    )

    if fits_a and not fits_b:
        pick_b = False
    elif fits_b and not fits_a:
        pick_b = True
    elif not fits_a and not fits_b:
        pick_b = _fits_width(paragraphs, BODY_W, level1_b, level2_b) and not _fits_width(
            paragraphs, text_w_a, level1_a, level2_a
        )
    elif image_path is None:
        pick_b = level1_b > level1_a  # nothing to show beside the text: larger level1 wins
    else:
        # Both genuinely fit and there IS a picture. Text is fitted first,
        # but every level-1 size from each layout's own fitted maximum down
        # to PIC_LAYOUT_MIN_PT ("big enough") is a candidate too — level2/
        # level3 follow the same fixed ratios fit_body_pt already uses, and
        # each candidate is re-checked to still fit its column unwrapped and
        # within body_h. Pictures as big as the free space allows decide:
        # among ALL such candidates (either layout, any qualifying level-1),
        # the largest fitted picture area wins, ties going to the larger
        # level-1 (and A over B on a complete tie, since A's range is
        # searched first and only a strictly larger area or level-1 replaces
        # the running best). Only when no candidate reaches PIC_LAYOUT_MIN_PT
        # with an actual picture does the old rule apply — largest level-1
        # (each layout at its own fitted maximum), ties by area.
        best = None  # (layout, level1, level2, area, split_or_box)
        for level1 in range(level1_a, PIC_LAYOUT_MIN_PT - 1, -1):
            level2 = _level2_for(level1)
            result = _pic_area_for_level1_a(paragraphs, image_path, level1, level2, body_h)
            if result is None:
                continue
            split, area = result
            if area > 0 and (
                best is None or area > best[3] or (area == best[3] and level1 > best[1])
            ):
                best = ("A", level1, level2, area, split)
        for level1 in range(level1_b, PIC_LAYOUT_MIN_PT - 1, -1):
            level2 = _level2_for(level1)
            result = _pic_area_for_level1_b(paragraphs, image_path, level1, level2, body_h)
            if result is None:
                continue
            box, area = result
            if area > 0 and (
                best is None or area > best[3] or (area == best[3] and level1 > best[1])
            ):
                best = ("B", level1, level2, area, box)

        if best is not None:
            pick_b = best[0] == "B"
            if pick_b:
                level1_b, level2_b = best[1], best[2]
                block_h_b = _block_height_emu(paragraphs, level1_b, level2_b)
                leftover_b = (
                    PIC_BOTTOM_LIMIT
                    - COL_TOP
                    - block_h_b
                    + _last_line_slack_emu(paragraphs, level1_b, level2_b)
                )
                pic_b = True
            else:
                level1_a, level2_a = best[1], best[2]
                text_w_a_split = best[4]
                text_w_a = text_w_a_split - GUTTER_EMU
                block_h_a = _block_height_emu(paragraphs, level1_a, level2_a)
        else:
            size_a = _fitted_pic_size(
                image_path, BODY_W - text_w_a_split, PIC_BOTTOM_LIMIT - COL_TOP
            )
            area_a = size_a[0] * size_a[1] if size_a is not None else 0
            box_b = _corner_pic_box(paragraphs, level1_b, level2_b, image_path, COL_TOP)
            area_b = box_b["max_w"] * box_b["max_h"] if box_b is not None else 0
            if level1_a == level1_b:
                pick_b = area_b > area_a
            else:
                pick_b = level1_b > level1_a

    if pick_b:
        layout, level1_pt, level2_pt, text_w, block_h = "B", level1_b, level2_b, BODY_W, block_h_b
    else:
        layout, level1_pt, level2_pt, text_w, block_h = "A", level1_a, level2_a, text_w_a, block_h_a

    _assert_no_wrap(paragraphs, text_w, level1_pt, level2_pt, slide_label)

    print(
        f"  [{slide_label}] body_h={body_h / EMU_PER_IN:.2f}in "
        f"A(level1={level1_a}pt block_h={block_h_a / EMU_PER_IN:.2f}in fits={fits_a}) "
        f"B(level1={level1_b}pt block_h={block_h_b / EMU_PER_IN:.2f}in fits={fits_b} "
        f"leftover={leftover_b / EMU_PER_IN:.2f}in pic={pic_b}) "
        f"-> chosen {layout}: level1={level1_pt}pt block_h={block_h / EMU_PER_IN:.2f}in"
    )

    return {
        "layout": layout,
        "level1_pt": level1_pt,
        "level2_pt": level2_pt,
        "text_col_w": text_w,
        "split_a": text_w_a_split,
        "col_bottom": col_bottom,
        "body_h": body_h,
        "block_h": block_h,
        "paragraphs": paragraphs,
        "pic_b": pic_b if layout == "B" else True,
        "leftover_b": leftover_b,
    }


def _fitted_pic_size(image_path, max_w, max_h):
    """Aspect-preserving (w, h) for `image_path` inside (max_w, max_h), or
    None when the image is missing (the slide is left text-only, see
    add_visual)."""
    if image_path is None or not Path(image_path).exists():
        return None
    with Image.open(image_path) as im:
        iw, ih = im.size
    scale = min(max_w / iw, max_h / ih)
    return int(iw * scale), int(ih * scale)


def _pic_bottom_for_width(pic_w):
    """How far down a bottom-right picture of width `pic_w` may run.

    PIC_BOTTOM_LIMIT (0.15in above the slide edge, straight over the right
    footer block) when the picture is wide enough to cover that block
    ENTIRELY — half a hidden label looks broken. Otherwise it stops at
    LOGO_TOP, above the whole footer row. The slide number is never a
    constraint here: it moves out of the picture's way instead (see
    add_slide_number)."""
    left = LEFT_COL_LEFT + BODY_W - pic_w
    if left > FOOTER_RIGHT_LEFT:
        return LOGO_TOP
    return PIC_BOTTOM_LIMIT


def _text_line_boxes(paragraphs, level1_pt, level2_pt, col_top, text_left):
    """(top, bottom, right_edge) in EMU for every rendered line, using the
    same measured widths the fit-up used — so the picture packer below knows
    exactly where the text really ends, not where its box ends."""
    boxes = []
    y = col_top
    for p in paragraphs:
        pt_size = _level_pt(p.level, level1_pt, level2_pt)
        y += _pt_to_emu(SPC_BEFORE_PT.get(p.level, SPC_BEFORE_PT[2]))
        height = _pt_to_emu(pt_size * LINE_HEIGHT_MULT)
        width_px = sum(_text_width_px(r.text, pt_size, bold=r.bold) for r in p.runs)
        right = text_left + TEXT_INSET_EMU + LEVEL_MAR_L[p.level] + _px_to_emu(width_px)
        boxes.append((y, y + height, right))
        y += height
    return boxes


def _corner_pic_box(paragraphs, level1_pt, level2_pt, image_path, col_top):
    """Largest bottom-right rectangle that is free of text, for layout B.

    Bullets are short, so the space to the right of them is usually free far
    above the last line. For every candidate top edge (each line's bottom,
    plus the top of the body) the usable width is the body's right edge minus
    the 0.3in gutter minus the right edge of the widest line whose vertical
    span reaches below that top — lines that end above the picture do not
    constrain it. The pair maximising the picture's area at its own aspect
    ratio wins, subject to MIN_PIC_H_EMU and the footer cover-or-stop rule
    (the slide number is never a constraint here — it moves out of the
    picture's way instead, see add_slide_number). A candidate that enters the
    footer band is narrowed so its left edge never passes
    FOOTER_BAND_MIN_LEFT_EMU (the bottom-left logo, the number box, and a
    gutter) — the left logo is never touched and the number's slide-left slot
    always exists; if that narrowing drops it below MIN_PIC_H_EMU, the
    LOGO_TOP candidate at the same top competes in the max-area sweep
    instead. Returns an add_visual box, or None when there is no image file
    or no rectangle big enough."""
    if image_path is None or not Path(image_path).exists():
        return None
    with Image.open(image_path) as im:
        iw, ih = im.size
    aspect = iw / ih
    boxes = _text_line_boxes(paragraphs, level1_pt, level2_pt, col_top, LEFT_COL_LEFT)
    body_right = LEFT_COL_LEFT + BODY_W
    best = None
    for top in sorted({col_top} | {b[1] for b in boxes}):
        blockers = [b[2] for b in boxes if b[1] > top]
        left_limit = max(max(blockers) + GUTTER_EMU, LEFT_COL_LEFT) if blockers else LEFT_COL_LEFT
        for bottom in (PIC_BOTTOM_LIMIT, LOGO_TOP):
            limit = left_limit
            w = min(body_right - limit, (bottom - top) * aspect)
            if bottom == PIC_BOTTOM_LIMIT:
                w = min(w, body_right - FOOTER_BAND_MIN_LEFT_EMU)
            h = w / aspect
            if h < MIN_PIC_H_EMU or w <= 0:
                continue
            if bottom == PIC_BOTTOM_LIMIT and body_right - w > FOOTER_RIGHT_LEFT:
                continue  # too narrow to cover the right footer block entirely
            if best is None or w * h > best[0]:
                best = (w * h, int(w), int(h), bottom)
    if best is None:
        return None
    _, w, h, bottom = best
    return {
        "left": body_right - w,
        "top": bottom - h,
        "max_w": w,
        "max_h": h,
        "valign": "bottom",
    }


def _pic_geom(layout_info, image_path=None):
    """(left, top, max_w, max_h, valign) for add_visual, from _choose_layout()'s
    result, or None when B's leftover space is too small for a picture (below
    MIN_PIC_LEFTOVER_B_EMU) — the caller must skip add_visual in that case.

    Both layouts anchor the picture to the BOTTOM-RIGHT corner of its region
    and let it run down to PIC_BOTTOM_LIMIT, straight over the right-hand
    footer block: a picture is the slide's second message, so it gets every
    inch the text does not need.
    Layout A: the remaining ~40% column (split at the unshrunk 60% point, not
    at the narrower text box edge — see _choose_layout), COL_TOP to
    PIC_BOTTOM_LIMIT, so a landscape image reaches the FULL column width
    instead of being capped by the text column's bottom.
    Layout B: the leftover space under the text block, height = leftover -
    GUTTER_EMU, width capped to MAX_PIC_W_RATIO_B of BODY_W.
    In both, a picture too narrow to cover the right footer block entirely
    (its left edge would land right of FOOTER_RIGHT_LEFT, leaving half a
    label showing) stops at LOGO_TOP instead. And in both, a picture that
    does enter the footer band is narrowed so its left edge never passes
    FOOTER_BAND_MIN_LEFT_EMU (the left logo, the number box, and a gutter);
    if narrowing that far then makes it too narrow to cover the right footer
    block entirely, it stops at LOGO_TOP instead (full width allowed there)."""
    if layout_info["layout"] == "A":
        text_w_a_split = layout_info["split_a"]
        col_w = BODY_W - text_w_a_split
        col_left = LEFT_COL_LEFT + text_w_a_split
        body_right = LEFT_COL_LEFT + BODY_W
        bottom = PIC_BOTTOM_LIMIT
        size = _fitted_pic_size(image_path, col_w, bottom - COL_TOP)
        if size is not None:
            bottom = _pic_bottom_for_width(size[0])
            if bottom == PIC_BOTTOM_LIMIT and body_right - size[0] < FOOTER_BAND_MIN_LEFT_EMU:
                col_w = min(col_w, body_right - FOOTER_BAND_MIN_LEFT_EMU - col_left)
                size = _fitted_pic_size(image_path, col_w, bottom - COL_TOP)
                bottom = _pic_bottom_for_width(size[0]) if size is not None else bottom
        return {
            "left": col_left,
            "top": COL_TOP,
            "max_w": col_w,
            "max_h": bottom - COL_TOP,
            "valign": "bottom",
        }

    box = _corner_pic_box(
        layout_info["paragraphs"],
        layout_info["level1_pt"],
        layout_info["level2_pt"],
        image_path,
        COL_TOP,
    )
    if box is not None:
        return box

    # No image file, or no leftover space earned a picture: nothing to draw.
    if not layout_info["pic_b"]:
        return None

    leftover = layout_info["leftover_b"]
    body_right = LEFT_COL_LEFT + BODY_W
    max_w = int(BODY_W * MAX_PIC_W_RATIO_B)
    bottom = PIC_BOTTOM_LIMIT
    size = _fitted_pic_size(image_path, max_w, max(leftover - GUTTER_EMU, 0))
    if (
        size is not None
        and _pic_bottom_for_width(size[0]) == PIC_BOTTOM_LIMIT
        and body_right - size[0] < FOOTER_BAND_MIN_LEFT_EMU
    ):
        # Enters the footer band too far left (would cross the left logo /
        # the number's slide-left slot) — narrow it instead.
        max_w = min(max_w, body_right - FOOTER_BAND_MIN_LEFT_EMU)
        size = _fitted_pic_size(image_path, max_w, max(leftover - GUTTER_EMU, 0))
    if size is not None and _pic_bottom_for_width(size[0]) == LOGO_TOP:
        bottom = LOGO_TOP
        leftover -= PIC_BOTTOM_LIMIT - LOGO_TOP
        if leftover < MIN_PIC_LEFTOVER_B_EMU:
            return None

    max_h = max(leftover - GUTTER_EMU, 0)
    pic_top = bottom - max_h
    # Box itself must be right-aligned to the body's right edge; add_visual
    # right-aligns the picture *within* this box, so if the box started at
    # LEFT_COL_LEFT (spanning only the first max_w of the body) the picture
    # would land mid-slide instead of flush with the body's right edge.
    return {
        "left": LEFT_COL_LEFT + BODY_W - max_w,
        "top": pic_top,
        "max_w": max_w,
        "max_h": max_h,
        "valign": "bottom",
    }


def _repeated_picture_warnings(slides):
    """Warning lines for the build report: consecutive slides that reference
    the same `visual_image`, neither flagged `key_figure=True`. Rule 16 — a
    picture belongs on most slides but not every one, and the same
    decorative image never repeats back to back; only an actual
    information-carrying figure (a diagram/chart discussed on both slides)
    may, by passing `key_figure=True` on the slide dict to opt out of this
    check. See style/STYLE.md "Picture variety"."""
    warnings = []
    for prev, cur in itertools.pairwise(slides):
        path = cur.get("visual_image")
        if (
            path is not None
            and path == prev.get("visual_image")
            and not prev.get("key_figure")
            and not cur.get("key_figure")
        ):
            warnings.append(
                f"WARNING: {prev['title']!r} and {cur['title']!r} repeat the same "
                f"picture ({path}) - drop it from one slide (text-only layout there) "
                "or pass key_figure=True if it's an information-carrying figure "
                "discussed on both."
            )
    return warnings


def build() -> None:
    fresh_copy()
    prs = Presentation(str(WORK))
    layout_title = prs.slide_layouts[0]  # "Title Slide"
    layout_content = prs.slide_layouts[1]  # "Title and Content"
    delete_all_slides(prs)
    _move_logos_to_content_layout(prs, layout_content)  # no logos on the title slide

    # ---- Title slide ------------------------------------------------------
    slide = prs.slides.add_slide(layout_title)
    ctr_title = slide.shapes.title
    ctr_title.left, ctr_title.top = Emu(TITLE_BOX_LEFT), Emu(TITLE_BOX_TOP)
    ctr_title.width, ctr_title.height = Emu(TITLE_BOX_W), Emu(TITLE_BOX_H)
    tf = ctr_title.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    title_pt = fit_title_pt(TITLE, TITLE_BOX_W, TITLE_PT_RANGE, max_lines=2)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run()
    r.text = TITLE
    r.font.size = Pt(title_pt)
    r.font.bold = True
    r.font.color.rgb = TITLE_BLUE
    r.font.name = "Calibri Light"

    subtitle = next(shp for shp in slide.placeholders if shp.placeholder_format.idx == 1)
    name_pt = fit_title_pt(
        AUTHOR, SUBTITLE_BOX_W, NAME_PT_RANGE, max_lines=1, bold=False, family=BODY_FONT_FAMILY
    )
    date_pt = fit_title_pt(
        DATE_LINE, SUBTITLE_BOX_W, DATE_PT_RANGE, max_lines=1, bold=False, family=BODY_FONT_FAMILY
    )
    tf = subtitle.text_frame
    tf.clear()
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p0 = tf.paragraphs[0]
    p0.alignment = PP_ALIGN.CENTER
    r0 = p0.add_run()
    r0.text = AUTHOR
    r0.font.size = Pt(name_pt)
    r0.font.color.rgb = NAVY
    p1 = tf.add_paragraph()
    p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run()
    r1.text = DATE_LINE
    r1.font.size = Pt(date_pt)
    r1.font.color.rgb = DATE_GREY

    # ---- Content slides -----------------------------------------------
    report = []
    for s in SLIDES:
        slide = prs.slides.add_slide(layout_content)
        slide.shapes.title.text_frame.text = s["title"]
        live_demo = bool(s.get("live_demo"))
        col_bottom = COL_BOTTOM_DEMO if live_demo else COL_BOTTOM_FULL
        li = _choose_layout(
            _slide_paragraphs(s),
            col_bottom,
            s["title"],
            image_path=s.get("visual_image"),
        )
        add_hierarchical_bullets(
            slide,
            s["headline"],
            s["bullets"],
            li["level1_pt"],
            li["level2_pt"],
            live_demo=live_demo,
            col_w=li["text_col_w"],
        )
        pg = _pic_geom(li, s.get("visual_image"))
        pic = None
        if pg is not None:
            pic = add_visual(
                slide,
                s["visual_caption"],
                s.get("visual_image"),
                pg["left"],
                pg["top"],
                pg["max_w"],
                pg["max_h"],
                valign=pg["valign"],
                placeholder=bool(s.get("visual_placeholder")),
            )
        if live_demo:
            add_live_demo(slide)
        # Number is added last so it is always the topmost shape (see
        # add_slide_number).
        _, num_status = add_slide_number(slide, len(prs.slides), picture=pic)
        report.append((s["title"], li["level1_pt"], li["level2_pt"], li["layout"], num_status))

    print(f"{'slide':<28}{'level1':>7}{'level2':>7}{'layout':>7}  num")
    print(f"{'1. Title':<28}{title_pt:>7}{'-':>7}{'-':>7}  -")
    for title, l1, l2, layout, num_status in report:
        print(f"{title:<28}{l1:>7}{l2:>7}{layout:>7}  num: {num_status}")
    for line in _repeated_picture_warnings(SLIDES):
        print(f"  {line}")

    prs.save(str(OUT))
    print(f"Saved {OUT} ({len(prs.slides._sldIdLst)} slides)")
    _verify_slide_numbers(OUT)


if __name__ == "__main__":
    build()
