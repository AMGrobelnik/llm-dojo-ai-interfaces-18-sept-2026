"""House style for generated paper figures.

One place decides what every chart looks like, so a paper's figures are a set
rather than a collection. The choices here are the ones that a bake-off
across matplotlib, seaborn, plotly, altair, bokeh, Lets-Plot, pygal,
PGFPlots and ultraplot showed actually separate publication-ready output
from almost-ready output:

* **Constrained layout, always.** The single most common defect in the
  bake-off was a clipped axis label — the y-label sheared off at the left
  edge because the figure was sized before the label was measured. It
  happened to seaborn and plotly renders that were otherwise flawless.
  ``layout="constrained"`` measures first, so it cannot happen.

* **Colourblind-safe by default.** Deuteranopia affects ~8% of men; a
  red/green series pair is unreadable to a chunk of any audience. The
  palette below is seaborn's ``colorblind`` set. Measured under the standard
  dichromacy simulation, the closest pair is ΔE*ab 14.0 under protanopia and
  10.3 under deuteranopia — comfortably apart, against a just-noticeable
  difference of ~1. Two limits, both measured rather than assumed, and both
  left alone deliberately:

  - Violet and tan (4th and 5th) sit ΔE 3.3 apart under TRITANOPIA, which
    is ~1 in 10,000 and blue-yellow. Re-picking them would cost separation
    under the two common forms.
  - GREYSCALE separates the first THREE series (ΔL* ≥ 8.1) and no more:
    past that the lightnesses cluster in a 57-70 band, and violet against
    grey is ΔL* 0.3 — the same shade in print. No reordering fixes that,
    and spreading the lightnesses out would cost the CVD separations above.
    Four or more series that must survive B&W reproduction need a second
    channel (line style, markers, hatching), which the style adds
    automatically only past eight, where the colour itself repeats.

  ``test_data_fig_palette`` measures all of this rather than trusting the
  palette's name.

* **Sans-serif.** Matches the venue templates (NeurIPS/ICML/ACL) and stays
  legible when a reviewer shrinks a figure to a column width.

* **No chartjunk.** No 3D, no gradients, no shadows, no coloured plot
  background, no heavy gridlines. A faint horizontal grid only, behind the
  data.

Vector output is the deliverable: LaTeX embeds PDF at the resolution of the
page, so text in the figure stays sharp and selectable. A PNG is written
alongside for quick review only.
"""

from __future__ import annotations

import textwrap

import matplotlib

# Must precede pyplot: figure generation runs headless in the pipeline, and
# the default interactive backend fails without a display.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

# seaborn's ``colorblind`` palette, minus vermilion and light pink. Ordered so
# the first three — the most common series count — are maximally separated:
# ΔE*ab 52-69 apart across normal, protanopia and deuteranopia.
PALETTE: tuple[str, ...] = (
    "#0173B2",  # blue
    "#DE8F05",  # amber
    "#029E73",  # green
    "#CC78BC",  # violet
    "#CA9161",  # tan
    "#949494",  # grey
    "#ECE133",  # yellow
    "#56B4E9",  # sky
)

# Dash patterns for when the palette wraps. Past eight series the colour
# repeats exactly — series 1 and 9 were pixel-identical, which makes a legend
# unusable — so the line style becomes the second channel that tells them
# apart. It is also the only channel that survives greyscale print past the
# third series, where the palette's lightnesses start to cluster.
LINE_STYLES: tuple[str, ...] = ("-", "--", "-.", ":")


def series_style(index: int) -> dict:
    """Colour, and past the palette's length a dash pattern too."""
    style = {"color": PALETTE[index % len(PALETTE)]}
    if index >= len(PALETTE):
        style["linestyle"] = LINE_STYLES[(index // len(PALETTE)) % len(LINE_STYLES)]
    return style


# Sequential map for heatmaps: perceptually uniform AND colourblind-safe,
# unlike the jet/rainbow maps that still show up in papers.
SEQUENTIAL_CMAP = "cividis"
# Diverging map for signed quantities (deltas, correlations).
DIVERGING_CMAP = "RdBu_r"

# Base font size in points. Figures are drawn at their final print size, so
# this is what the reader actually sees — not a value scaled later.
BASE_FONT_PT = 11


def _sans_stack(family: str | None) -> list[str]:
    """Preference list, with an explicit ``family`` taking priority.

    matplotlib uses the first entry it can resolve and never consults the
    rest per-glyph, so overriding means going to the FRONT.
    """
    base = ["DejaVu Sans", "Helvetica", "Arial", "Liberation Sans"]
    return [family, *base] if family else base


def apply_house_style(base_font_pt: int = BASE_FONT_PT, family: str | None = None) -> None:
    """Install the house style into matplotlib's global rcParams.

    ``family`` puts one font ahead of the default stack — the escape hatch
    for a script DejaVu does not cover (CJK, Devanagari, Thai). Without it
    those figures cannot be produced at all, because the glyph gate refuses
    to write a figure full of hollow boxes.

    Call once before building a figure. Idempotent.
    """
    plt.rcParams.update(
        {
            # -- typography ---------------------------------------------------
            "font.family": "sans-serif",
            # matplotlib picks the FIRST available family and uses only it —
            # there is no per-glyph fallback across this list, so appending a
            # CJK font would be inert. DejaVu covers Latin, Greek, Cyrillic
            # and Hebrew; a script it lacks needs ``font_family`` on the spec
            # to put a covering font first.
            "font.sans-serif": _sans_stack(family),
            "font.size": base_font_pt,
            "axes.titlesize": base_font_pt + 1,
            "axes.labelsize": base_font_pt,
            "xtick.labelsize": base_font_pt - 1,
            "ytick.labelsize": base_font_pt - 1,
            "legend.fontsize": base_font_pt - 1,
            "figure.titlesize": base_font_pt + 3,
            # Real minus signs, not hyphens, on negative ticks.
            "axes.unicode_minus": True,
            # Numbers are formatted the same way wherever the figure is drawn.
            # matplotlib only consults the locale when this is True, and it
            # defaults to False — so the skill was relying on a default it does
            # not own. Measured: under a comma-decimal locale (en_DK) with this
            # flipped on, `line`, `heatmap` and `corr` all render differently,
            # and a tick reading "0,5" in an English paper is wrong in a way the
            # figure looks entirely fine about.
            "axes.formatter.use_locale": False,
            # -- the frame ----------------------------------------------------
            # Top and right spines carry no information and box the data in.
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.linewidth": 0.8,
            "axes.edgecolor": "#333333",
            # -- grid ---------------------------------------------------------
            # Faint, horizontal, and BEHIND the data. A grid drawn over the bars
            # reads as a defect.
            "axes.grid": True,
            "axes.grid.axis": "y",
            "grid.color": "#CCCCCC",
            "grid.linewidth": 0.6,
            "grid.alpha": 0.6,
            "axes.axisbelow": True,
            # -- data ---------------------------------------------------------
            "axes.prop_cycle": plt.cycler(color=list(PALETTE)),
            "lines.linewidth": 1.8,
            "lines.markersize": 5,
            "patch.linewidth": 0,
            "image.cmap": SEQUENTIAL_CMAP,
            # -- legend -------------------------------------------------------
            # No visible box — a frame competes with the axes for attention —
            # but an OPAQUE one. Frameless meant the grid rule ran straight
            # through the legend text: on ``bubble`` the y=80 gridline crossed
            # "Open weights" and "API models" at mid-x-height. ``loc="best"``
            # steers a legend clear of the DATA and knows nothing about the
            # grid, so the only fix that generalises is to let the legend mask
            # whatever it lands on.
            "legend.frameon": True,
            "legend.framealpha": 1.0,
            "legend.facecolor": "white",
            "legend.edgecolor": "none",
            "legend.borderaxespad": 0.4,
            "legend.handlelength": 1.4,
            "legend.columnspacing": 1.2,
            # -- figure -------------------------------------------------------
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            # Measure text, THEN size the figure. Prevents the clipped-label
            # defect that constrained layout exists to solve.
            "figure.constrained_layout.use": True,
            "figure.constrained_layout.h_pad": 0.06,
            "figure.constrained_layout.w_pad": 0.06,
            "figure.dpi": 200,
            "savefig.dpi": 200,
            # TrueType (42), never matplotlib's default Type 3 (3). Not a
            # preference: IEEE and ACM submission systems REJECT PDFs containing
            # Type 3 fonts outright, and matplotlib emits them by default, so
            # every figure it produces is non-compliant until this is set. It
            # also cuts PDF size by roughly a third. ``ps.fonttype`` needs the
            # same treatment — an EPS export would otherwise reintroduce Type 3.
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
            "svg.fonttype": "none",
        }
    )


def figsize_for(aspect: str, width_in: float = 7.0) -> tuple[float, float]:
    """Figure size in inches for an ``W:H`` aspect string.

    Width defaults to 7 inches — a full text-width figure at close to 100%
    scale, which is the size the reader sees.

    The generated size is deliberately NOT capped by height here. Capping it
    to the paper's float limit was tried and is worse: a 1:1 figure comes out
    3.6 x 3.6 in, a 2x2 panel gets 2.4 in per cell, and the legibility gates
    then refuse figures that used to draw — 18 checks and two catalogue
    examples went red. The shrink that motivated it belongs to the LaTeX
    include, and is fixed there.
    """
    # No fallback here. `validate_spec` refuses a malformed or non-positive
    # aspect before this runs — measured against ten spellings ("16x9", "1:0",
    # "-16:9", ":", "" and the rest) down every route in: top-level, on a
    # panel, on a panel's child, absent, and explicitly null. Not one reached
    # this function; the only value that arrives is a parsed, positive pair.
    #
    # What used to sit here caught the parse failure and returned 16:9, which
    # is the defect `test_an_aspect_that_cannot_be_parsed_is_refused_not_
    # quietly_replaced` was written for: "16x9" drew the shape that was wanted
    # by luck and "4x3" drew a 16:9 figure at exit 0, under a caption written
    # for the other shape. A second copy of that fallback below the gate would
    # restore exactly that behaviour on any path that ever skipped the gate,
    # which is the last place it should come back.
    w, h = (float(part) for part in aspect.split(":"))
    return (width_in, width_in * h / w)


def literal(text) -> str:
    """User text, with ``$`` neutralised so matplotlib prints it verbatim.

    A MATCHED PAIR of dollar signs is mathtext to matplotlib, so a title like
    "Cost $5 to $9 per run" silently renders as "Cost 5to9 per run" with the
    currency gone and the middle word italicised. A cost figure losing its
    currency symbols is precisely the kind of quiet corruption this renderer
    is built to refuse, and unlike a bad number it survives review because
    the sentence still reads.

    Escaping rather than rejecting: a literal dollar is what a spec author
    means essentially every time. The cost is that mathtext is unavailable —
    use Unicode for superscripts (``R²``, ``10⁻³``), which the rest of this
    module already does.

    RIGHT-TO-LEFT text is refused here instead. matplotlib applies no bidi
    reordering and no Arabic joining: it draws the code points left to right
    in their isolated forms, so a Hebrew or Arabic label comes out reversed
    and unjoined. The glyphs are all in DejaVu, so the missing-glyph gate —
    the one that catches CJK — sees nothing wrong and the figure ships. This
    is the single funnel every piece of user text in the catalogue passes
    through, which is why the check lives here.
    """
    text = str(text)
    _reject_bidi(text)
    return text.replace("$", r"\$")


def _reject_bidi(text: str) -> None:
    """Refuse text matplotlib would draw in the wrong ORDER.

    Unicode gives each character a bidirectional class; ``R`` (Hebrew and
    friends) and ``AL`` (Arabic) are the two that mean "runs right to left".
    Detected by that property rather than by code-point ranges, so it holds
    for every RTL script without a list to keep up to date.
    """
    import unicodedata

    # Imported here, not at module scope: ``chart_common`` imports FROM this
    # module, so a top-level import would close the cycle.
    from chart_common import SpecError

    offenders = sorted({ch for ch in text if unicodedata.bidirectional(ch) in ("R", "AL")})
    if not offenders:
        return
    names = ", ".join(f"{ch!r} ({unicodedata.name(ch, 'unnamed')})" for ch in offenders[:3])
    raise SpecError(
        f"{text[:40]!r} is written right to left ({names}). matplotlib does no "
        "bidi reordering and no Arabic joining — it draws the characters left to "
        "right in isolated forms, so the label comes out reversed and unjoined, "
        "and every glyph exists so nothing else notices. Transliterate the label, "
        "or write it in the paper's own script."
    )


def number(value: float, spec: str = "g") -> str:
    """A number as DRAWN text, with the same minus sign the axes use.

    ``axes.unicode_minus`` gives every tick label a real minus (U+2212); an
    f-string gives an ASCII hyphen, and the two are visibly different glyphs
    at print size. ``bland_altman`` labelled its limits "−1.96 SD  -8.11" —
    both operators in one label, written two ways — and ``corr`` annotated
    "-0.62" in a cell beside a colourbar tick reading "−0.5".

    Applies to the exponent marker too (``1e-05``), which is the same
    operator and was already being drawn the same wrong way.
    """
    return format(value, spec).replace("-", "\N{MINUS SIGN}")


def content_axes(fig) -> list:
    """The axes that hold a chart, excluding colorbars.

    ``fig.axes`` counts a colorbar as an axes, so a single heatmap reports
    two and every "is this a lone chart?" test silently took the multi-panel
    branch. matplotlib labels the strip it creates ``<colorbar>``, which is
    the one public marker that survives both classic and constrained layout.
    """
    return [ax for ax in fig.axes if ax.get_label() != "<colorbar>"]


def content_places(fig) -> int:
    """How many CHARTS the figure holds — places, not axes objects.

    A twin axes shares its host's rectangle exactly; so does an inset. Counting
    objects called ``speedup``'s efficiency axis a second chart, which sent its
    legend down the multi-panel path — a hand-rolled anchor at a fixed fraction
    of the AXES height. At 21:9 that fraction is fewer pixels than the tick
    labels and x-label already occupy, and the legend printed over "GPUs".
    """
    return len(
        {
            tuple(round(v, 4) for v in ax.get_position().bounds)
            for ax in content_axes(fig)
            if ax.get_visible()
        }
    )


#: Points in ONE artist above which its cloud is drawn as a bitmap inside the
#: vector file. Measured on this house style at 6x4in, three-decimal marker
#: coordinates, PDF out:
#:
#:     points    vector    raster
#:      2,000    0.04 MB   0.07 MB
#:     20,000    0.33 MB   0.38 MB
#:     50,000    0.80 MB   0.50 MB
#:    120,000    1.91 MB   0.33 MB
#:
#: Below ~25k the bitmap is the LARGER of the two, so rasterizing there would
#: cost both size and crispness. The threshold sits at the crossover.
_RASTER_POINTS = 25_000


def rasterize_dense_clouds(fig) -> None:
    """Draw very dense point clouds as a bitmap, keeping everything else vector.

    A scatter of 360,000 points writes every marker as its own path: 5.7 MB
    for one figure, and a six-figure paper then does not fit inside a venue's
    upload limit. Rasterizing the cloud alone is the standard answer — the
    axes, ticks, labels and legend stay vector, so the text is still selectable
    and sharp at any zoom, which is the whole reason the deliverable is a PDF.

    Only ``Collection``s are touched. A dense LINE is already handled by
    matplotlib's path simplification (120,000 points is 0.09 MB), so
    rasterizing one would trade crispness for nothing.
    """
    for ax in fig.axes:
        for collection in ax.collections:
            offsets = collection.get_offsets()
            if offsets is not None and len(offsets) > _RASTER_POINTS:
                collection.set_rasterized(True)


def panel_label_text(ax):
    """The ``Text`` holding a panel label, i.e. the axes' LEFT title slot.

    ``get_title(loc="left")`` returns the string but matplotlib exposes no
    public accessor for the artist, and both measuring the label and re-laying
    it need the artist itself. Kept in one place so that stays a single
    documented dependency rather than a habit.
    """
    return ax._left_title


def fit_titles(fig) -> None:
    """Wrap any title wider than the axes it sits on, after layout.

    Constrained layout reflows axes to fit their labels but cannot wrap a
    single line, so a long title runs off the edge and loses its last words.

    This has to run POST-LAYOUT and measure against the AXES, not the
    figure. Two earlier attempts got that wrong and silently under-wrapped:
    a characters-per-inch estimate (titles render a point larger than the
    base size, and the average glyph is wider than half an em), then a
    measurement against the figure width — but ``ax.set_title`` centres on
    the axes, which is narrower than the figure by the y-label and tick
    margins. A 6.0in title fits a 7in figure and still overflows a 5.6in
    axes.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    fig_width = fig.get_window_extent(renderer=renderer).width
    panels = content_axes(fig)

    # A single axes squeezed into a strip — a horizontal bar chart whose
    # category names eat most of the width — cannot host a centred title:
    # ``set_title`` centres on the AXES, so the heading starts near the right
    # edge and runs off it. Promote it to a figure title, which is centred on
    # the page and is what a reader expects of a heading anyway.
    if len(panels) == 1 and fig._suptitle is None:
        only = panels[0]
        if only.get_title() and only.get_window_extent(renderer=renderer).width < fig_width * 0.7:
            fig.suptitle(only.get_title())
            only.set_title("")
            fig.canvas.draw()

    rewrapped = False
    for ax in panels:
        axes_width = max(1.0, ax.get_window_extent(renderer=renderer).width)
        label = panel_label_text(ax)
        label_width = label.get_window_extent(renderer=renderer).width if label.get_text() else 0.0
        # The right slot is the other half of the same line, and nothing used
        # to account for it: ``treemap``'s "13 of 14 named" note landed there
        # and its heading printed straight over it, 54% covered.
        note = ax._right_title
        note_width = note.get_window_extent(renderer=renderer).width if note.get_text() else 0.0
        if label_width or note_width:
            # Centre the heading in the space BETWEEN whatever occupies the two
            # side slots, rather than on the axes. Left at the axes midpoint,
            # staying clear of a side label costs twice its width — once on the
            # side it is on and once again on the far side to hold the centring
            # — which wrapped a two-line heading to four. Re-centring costs each
            # width exactly once, and the arithmetic then guarantees the
            # heading lands between the two.
            ax.title.set_x((label_width + axes_width - note_width) / 2 / axes_width)
        text = ax.get_title()
        if not text or "\n" in text:
            continue
        # The floor exists for ONE narrow axes — a barh whose category names
        # eat the width, where wrapping into the leftover strip gives a
        # five-line column in the corner. In a PANEL every axes is legitimately
        # narrow, and a floor of 70% of the figure exceeds a half-width cell,
        # so no panel title ever wrapped and titles ran into their neighbours.
        usable = max(axes_width, fig_width * 0.7) if len(panels) == 1 else axes_width
        usable -= label_width + note_width
        drawn = ax.title.get_window_extent(renderer=renderer).width
        if drawn <= usable:
            continue
        # ``textwrap`` splits on a CHARACTER budget, so the widest resulting
        # line can still render over the limit — a title wrapped to two lines
        # came back flush against its panel label. Scale the budget by how far
        # over the title is, then measure what was actually produced and
        # tighten until it fits. The Text reports its own extent from the
        # renderer, so the check costs no extra layout pass.
        # ``break_long_words`` defaults to TRUE, which splits a word rather
        # than let a line run over: an ordinary panel title came out as
        # "Generalisati / on to unseen / distribution / s", and shipped at
        # exit 0 because nothing downstream compares the drawn text to the
        # spec. A word that will not fit is left to overflow instead, where
        # the clipping gate can see it. The tick-label fitter has passed
        # ``break_long_words=False`` for exactly this reason all along.
        budget = max(12, int(len(text) * usable / drawn))
        for _ in range(4):
            ax.set_title(textwrap.fill(text, budget, break_long_words=False))
            if ax.title.get_window_extent(renderer=renderer).width <= usable or budget <= 12:
                break
            budget = max(12, budget - 2)
        # All three title slots share one baseline, and a wrapped heading grows
        # upward from it — so a panel label stayed level with the LAST line and
        # hung off the bottom of a three-line title. Padding the label to the
        # same line count lifts it to sit beside the first line. Set the text
        # on the artist rather than through ``set_title``, which re-applies
        # rcParams and so silently un-bolded the label.
        if label_width:
            label.set_text(label.get_text() + "\n" * ax.get_title().count("\n"))
        rewrapped = True

    # The figure title needs the same treatment and never got it. Every path
    # that produces one — a ``panel``'s own heading, and the promotion above —
    # left it as a single line, so on a narrow figure it ran off BOTH edges:
    # "Correlations between run-level metrics" came out as "ons between
    # run-level metrics (n = 4". Measured against the figure, since a
    # suptitle is centred on the page rather than on any axes.
    if fig._suptitle is not None and "\n" not in fig._suptitle.get_text():
        text = fig._suptitle.get_text()
        usable = fig_width * 0.96
        drawn = fig._suptitle.get_window_extent(renderer=renderer).width
        if text and drawn > usable:
            budget = max(12, int(len(text) * usable / drawn))
            for _ in range(4):
                fig.suptitle(textwrap.fill(text, budget, break_long_words=False))
                if (
                    fig._suptitle.get_window_extent(renderer=renderer).width <= usable
                    or budget <= 12
                ):
                    break
                budget = max(12, budget - 2)
            rewrapped = True

    if rewrapped:
        # The extra line changes every axes' height; let layout settle again.
        fig.canvas.draw()


def add_panel_label(ax, label: str) -> None:
    """Put a bold ``(a)``-style label above a subplot's top-left corner.

    This uses matplotlib's own LEFT title slot rather than a free-floating
    text artist. Two placements were tried first and both overprinted the
    heading: prefixing it onto the title gave ``(d)Row-normalised confusion
    matrix``, and a separate artist at the axes' top-left corner gave
    ``Accurac(a)y by benchmark`` as soon as ``fit_titles`` grew the centred
    title out to the full width of the cell.

    An axes owns three independent title slots — left, centre and right —
    laid out on one line by the same code that positions the heading. Giving
    the label the left slot means the two are placed against each other by
    matplotlib instead of by arithmetic here, so the ordering of these calls
    stops mattering: the label may be attached before or after the title.
    ``fit_titles`` reads this slot's width back and wraps the heading clear
    of it.
    """
    ax.set_title(label, loc="left", fontweight="bold")


def fix_log_ticks(ax, which: str) -> None:
    """Restore tick labels on a log axis that spans less than a decade.

    matplotlib's default ``LogLocator`` only places major ticks at powers of
    ten. An axis running 1.7–2.9 contains none, so it renders **completely
    unlabelled** — no error, no warning, just a figure with a bare axis. It
    is easy to miss in review and it hits the most common scaling-law range.
    Below roughly one decade, switch to labelling the minor subdivisions
    with plain numbers.
    """
    from matplotlib.ticker import LogLocator, NullFormatter, ScalarFormatter

    axis = ax.xaxis if which == "x" else ax.yaxis
    lo, hi = ax.get_xlim() if which == "x" else ax.get_ylim()
    lo, hi = min(lo, hi), max(lo, hi)
    if lo <= 0 or hi <= 0 or (hi / lo) >= 10:
        return  # a full decade or more: the default powers-of-ten are right
    axis.set_major_locator(LogLocator(subs="all", numticks=12))
    formatter = ScalarFormatter()
    formatter.set_scientific(False)
    axis.set_major_formatter(formatter)
    axis.set_minor_formatter(NullFormatter())


# Clearance demanded between neighbouring tick labels, in ems of their own
# size. A word space is about 0.25 em, so this is "at least a space apart" —
# the point below which two labels read as one word.
_WORD_GAP_EM = 0.30


def _drawn_x_labels(ax) -> list:
    """The x tick labels this axes actually paints, left to right.

    ``label1`` is the bottom label and ``label2`` the top one. An axes whose
    ticks were moved to the top paints label2 and leaves label1 hidden AT THE
    ORIGIN — every one of them reporting the same 1-pixel box, which reads as
    a pile of collisions that is not there. ``cd_diagram`` puts its rank axis
    on top, so its six labels "1".."6" were stood up at 90 degrees to resolve
    a crowd of six invisible artists stacked at (0, 0), across an axis with
    inches of room.
    """
    return [label for _, label in _drawn_x_label_slots(ax)]


def _drawn_x_label_slots(ax) -> list[tuple[int, object]]:
    """``(tick index, Text)`` for every x tick label actually painted.

    The index is what lets a caller put a rewritten label back. Blank
    categories are legitimate — a spacer between two groups of bars — and
    they are skipped here because an empty box measures nothing, so the
    painted list is SHORTER than the locator's. Feeding it straight back to
    ``set_xticklabels`` raised "The number of FixedLocator locations (9) ...
    does not match the number of labels (8)", surfaced to the caller as a bad
    spec naming a ``set_ticks`` call they never made.
    """
    lo, hi = sorted(ax.xaxis.get_view_interval())
    return [
        (index, label)
        for index, tick in enumerate(ax.xaxis.get_major_ticks())
        if lo <= tick.get_loc() <= hi
        for label in (tick.label1, tick.label2)
        if label is not None and label.get_visible() and label.get_text().strip()
    ]


def _relabelled(ax, slots, replacements: list[str]) -> list[str]:
    """One label per tick, with the painted ones replaced by ``replacements``.

    ``set_xticklabels`` demands exactly one entry per FixedLocator position,
    so anything it is not told about has to be carried through unchanged.
    Both ``label1`` and ``label2`` take their text from the same formatter,
    so reading label1 gives the right current value either way.
    """
    full = [tick.label1.get_text() for tick in ax.xaxis.get_major_ticks()]
    for (index, _), text in zip(slots, replacements, strict=True):
        full[index] = text
    return full


def share_panel_legends(fig) -> None:
    """One legend for a grid whose panels all show the same series.

    Nine cells each carrying the same two-entry legend is nine copies of one
    piece of information, and in a cell that small ``loc="best"`` has nowhere
    free to put it — "Baseline" and "Ours" printed across the bars in every
    single panel. A shared figure legend is both the standard small-multiples
    design and the only one that fits.

    Only when the panels genuinely agree: a grid whose cells show different
    series keeps its own legends, because merging them would attach a label
    to a colour that means something else two cells over.
    """
    panels = [ax for ax in content_axes(fig) if ax.get_visible()]
    if len(panels) < 2:
        return
    legends = [ax.get_legend() for ax in panels]
    if not all(legends):
        return
    labelling = {tuple(text.get_text() for text in legend.get_texts()) for legend in legends}
    if len(labelling) != 1 or not next(iter(labelling)):
        return
    handles, labels = panels[0].get_legend_handles_labels()
    if not handles:
        # A legend built from explicit ``handles=`` is invisible here: a
        # catmap's level swatches are Patches that were never added to the
        # axes as labelled artists, so this returns empty and every panel
        # kept its own copy — which then printed through the panel's xlabel,
        # the one failure this function exists to prevent. Read the handles
        # off the drawn legend instead.
        handles = list(legends[0].legend_handles)
        labels = [text.get_text() for text in legends[0].get_texts()]
    if not handles:
        return
    for legend in legends:
        legend.remove()
    place_legend(fig, handles, labels, loc="outside lower center", ncols=min(len(labels), 5))


#: Point names on ONE figure, past which they are refused rather than placed.
#: Measured: the catalogue's own busiest example names 9 points, and the
#: legibility gate starts refusing a ``pareto`` for overprinted names at 54 —
#: so anything reaching this is far past readable. The cap exists because
#: ``fit_point_labels`` tries every name against every name already placed:
#: 144 names take 2.5 s, 180 take 9, and a 500-series spec never returned at
#: all, so the gate that would have refused it never got to run.
_MAX_POINT_LABELS = 120


def place_point_label(ax, text: str, xy, *, offset: tuple[float, float] = (5, 4), **kwargs):
    """Name a single plotted point, beside it, and record it for nudging.

    Every renderer that writes a name next to a marker goes through here. The
    offset it is given is a FIRST GUESS: whether the name lands on a
    neighbouring point is a question about the drawn figure, and
    ``fit_point_labels`` answers it after layout by trying the other corners.

    ``volcano`` is why. It chooses which points to label by spacing the
    LABELLED ones apart, which says nothing about the sixty it did not label —
    so "few-shot 3" was printed with a data marker through the middle of the
    word, at exit 0, and the text gate never saw it because a marker is not
    text.
    """
    figure = ax.figure
    recorded = getattr(figure, "aii_point_labels", [])
    if len(recorded) >= _MAX_POINT_LABELS:
        from chart_common import SpecError

        raise SpecError(
            f"more than {_MAX_POINT_LABELS} points are asking for a name on one figure. "
            "Names that many cannot be told apart — the legibility gate already refuses "
            "a scatter at 54 of them — and placing each one clear of the others is work "
            "that grows with the square of the count, so a spec with thousands never "
            "finishes rather than being refused. Label only the points the caption "
            "talks about, or drop the names and let the axes carry the reading."
        )
    # ``offset`` is the caller's FIRST GUESS, not a decision: ``fit_point_labels``
    # re-places the annotation after layout. ``bubble`` needs its own — a name
    # sits above the marker it belongs to, by that marker's radius — where the
    # default 5,4 would start it inside the disc.
    annotation = ax.annotate(text, xy, textcoords="offset points", xytext=offset, **kwargs)
    figure.aii_point_labels = [*recorded, (ax, annotation)]
    return annotation


def place_legend(parent, *args, **kwargs):
    """Draw a legend and record the call, so ``fit_legends`` can reflow it.

    Every legend in the catalogue goes through here, whether its parent is an
    axes or the figure. The recording is what makes a reflow possible at all:
    ``Legend.set_ncols`` stores the new column count and does NOT re-pack the
    legend box, so calling it changes nothing a reader would ever see — a
    four-entry legend measured 700 px before and 700 px after. Narrowing means
    building the legend again, and that needs the arguments it was built with.
    """
    legend = parent.legend(*args, **kwargs)
    figure = parent if isinstance(parent, plt.Figure) else parent.figure
    figure.aii_legends = [*getattr(figure, "aii_legends", []), (parent, args, kwargs, legend)]
    return legend


def _room_for(legend, parent, fig, renderer) -> float:
    """How wide this legend is allowed to be, in pixels.

    A legend sitting INSIDE its axes has the axes' width and no more. One
    anchored below or beside the axes is centred on it but spills freely into
    the figure margins, so the page is its limit — measuring that one against
    the axes made ``speedup`` shed a column it did not need to at 21:9, which
    turned a one-row legend into two and dropped the second row onto the
    x-axis label. Which case applies is read off the drawn figure rather than
    from the arguments, because ``loc`` and ``bbox_to_anchor`` together have
    too many spellings of "outside" to enumerate.
    """
    page = fig.get_window_extent(renderer=renderer).width
    if parent is fig:
        return page
    axes_box = parent.get_window_extent(renderer=renderer)
    legend_box = legend.get_window_extent(renderer=renderer)
    inside = legend_box.y0 >= axes_box.y0 - 1.0 and legend_box.y1 <= axes_box.y1 + 1.0
    return axes_box.width if inside else page


def fit_legends(fig) -> None:
    """Reflow any legend that is wider than the space it has to sit in.

    The column count is chosen before layout runs and whether it fits is only
    knowable after. Three entries in one row measured 695 px on a 700 px
    canvas, and constrained layout answers a legend wider than its axes by
    shrinking the axes — on EVERY draw, without converging, so the figure
    collapsed to nothing and was refused outright. Dropping a column at a time
    until it fits leaves the axes stable instead.

    A legend that has been re-parented with ``add_artist`` is left alone:
    replaying ``ax.legend`` would overwrite whichever legend is currently the
    axes' own, and ``bubble`` deliberately carries two — a colour key and a
    size key. It keeps its columns; if it genuinely does not fit, the layout
    gate refuses the figure with a message rather than shipping it.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    recorded = getattr(fig, "aii_legends", [])
    changed = False
    for index, (parent, args, kwargs, legend) in enumerate(list(recorded)):
        still_attached = legend in fig.legends if parent is fig else legend is parent.get_legend()
        if not still_attached:
            continue
        ncols = kwargs.get("ncols", 1)
        while ncols > 1:
            # Re-read each pass: shedding a column lets the axes grow back, so
            # the space available is a moving target while this converges.
            available = _room_for(legend, parent, fig, renderer)
            if legend.get_window_extent(renderer=renderer).width <= available:
                break
            ncols -= 1
            legend.remove()
            kwargs = {**kwargs, "ncols": ncols}
            legend = parent.legend(*args, **kwargs)
            recorded[index] = (parent, args, kwargs, legend)
            changed = True
            fig.canvas.draw()
    if changed:
        fig.canvas.draw()


#: How much of a single shape the legend may cover before that shape counts as
#: hidden. A FRACTION of the shape, not an absolute area: the question is
#: whether a reader can still see where the bar ends, and a legend corner
#: clipping 6% of one bar's top-left corner is invisible while 40% is the
#: value itself. Measured across the catalogue put through a two-column panel:
#: the harmless overlaps run 1.3-12.6%, the ones that lose the value 37-100%.
_LEGEND_HIDES = 0.05
#: Where REFUSING is warranted, which costs the whole figure rather than a
#: legend's position. Sits above every harmless overlap measured and below
#: every damaging one.
_LEGEND_HIDES_FATAL = 0.25


def _data_hidden(ax, legend, renderer) -> tuple[float, int]:
    """``(worst fraction of any one shape covered, how many are covered)``.

    Patches always count: a bar or a band is area by construction, and a
    legend over one hides where it ends. Lines count only when they carry a
    real label — a threshold guide (``volcano``'s significance cutoff, a
    chance line) spans the whole axes on purpose, so counting it would move or
    refuse every legend on every such chart for nothing.

    A fraction rather than an area, because the same 200 square pixels is a
    corner of one bar or the whole of another.
    """
    box = legend.get_window_extent(renderer=renderer)
    fractions = []
    for patch in ax.patches:
        patch_box = patch.get_window_extent(renderer=renderer)
        if patch_box.width <= 0 or patch_box.height <= 0:
            continue
        width = max(0.0, min(box.x1, patch_box.x1) - max(box.x0, patch_box.x0))
        height = max(0.0, min(box.y1, patch_box.y1) - max(box.y0, patch_box.y0))
        if width * height > 0:
            fractions.append(width * height / (patch_box.width * patch_box.height))
    for line in ax.lines:
        if str(line.get_label()).startswith("_"):
            continue
        xdata, ydata = line.get_data()
        if len(xdata) == 0:
            continue
        import numpy as np

        points = ax.transData.transform(np.column_stack([xdata, ydata]))
        under = sum(1 for x, y in points if box.x0 <= x <= box.x1 and box.y0 <= y <= box.y1)
        if under:
            fractions.append(under / len(points))
    if not fractions:
        return 0.0, 0
    return max(fractions), sum(1 for f in fractions if f >= _LEGEND_HIDES_FATAL)


def clear_legends_of_data(fig) -> None:
    """Move an inside legend that landed on the data out of the axes.

    ``loc="best"`` avoids the data only where free space exists. A horizontal
    chart has none to buy: the y-headroom trick that clears a bar chart's
    legend does nothing for a Gantt, whose rows are fixed and whose bars start
    wherever the schedule says. ``timeline``'s legend covered 1,674 px of the
    "Paper writing" bar — its LEFT END, so a reader could not see when the
    task began — in the shipped catalogue example.

    ``draw_legend`` already moves a legend out past six entries, or when the
    plot area is full by construction. That is a guess made before layout; this
    is the measurement after it, and it catches the cases the guess does not.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    recorded = getattr(fig, "aii_legends", [])
    changed = False
    for index, (parent, _args, kwargs, legend) in enumerate(list(recorded)):
        if parent is fig or legend is not parent.get_legend():
            continue  # already outside, or replaced by a later pass
        if _data_hidden(parent, legend, renderer)[0] < _LEGEND_HIDES:
            continue
        handles, labels = legend.legend_handles, [t.get_text() for t in legend.get_texts()]
        if not handles or content_places(fig) != 1:
            # A panel cell has no figure-level strip of its own to move into;
            # the layout gate refuses it instead of shipping a covered bar.
            continue
        legend.remove()
        moved = place_legend(
            fig, handles, labels, loc="outside lower center", ncols=kwargs.get("ncols", len(labels))
        )
        recorded[index] = (fig, (handles, labels), {"loc": "outside lower center"}, moved)
        changed = True
        fig.canvas.draw()
    if changed:
        fig.canvas.draw()


def assert_legends_clear_of_data(fig) -> None:
    """Refuse a figure whose legend is hiding the data it explains.

    ``clear_legends_of_data`` moves a lone chart's legend below the axes, so
    by the time this runs the only cases left are the ones nothing can move: a
    PANEL cell has no strip of its own to move into, and its neighbours' cells
    are not free space either.

    That case was silent and it is not small. A ``timeline`` in a two-column
    grid drew its five-entry legend over EIGHT OF ITS NINE BARS and exited 0,
    and the ``bar`` cell beside it had its bar TOPS masked — GSM8K reading as
    ~40 where the spec said 55.8.

    The bar for refusing is deliberately higher than the bar for moving: a
    legend clipping the corner of one bar costs a reader nothing, and refusing
    the figure over it would cost them the whole thing.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    from chart_geometry import all_axes

    covered = []
    for ax in all_axes(fig):
        legend = ax.get_legend()
        if legend is None:
            continue
        worst, count = _data_hidden(ax, legend, renderer)
        if worst < _LEGEND_HIDES_FATAL:
            continue
        name = (panel_label_text(ax).get_text() or ax.get_title() or "the chart").strip()
        covered.append((" ".join(name.split()), count, worst))
    if not covered:
        return
    covered.sort()
    where = "; ".join(
        f"{name} has {count} of its shapes {worst:.0%} behind its legend"
        if count
        else f"{name}'s legend covers {worst:.0%} of a mark"
        for name, count, worst in covered
    )
    raise RuntimeError(
        f"a legend is drawn over the data it explains: {where}. The legend is opaque by "
        "design — it has to mask the gridline it lands on — so whatever is under it is "
        "gone, not merely faint. A lone chart's legend is moved below the axes "
        "automatically; a panel cell has nowhere to move it, so give that chart its own "
        "figure, use fewer columns so each cell has room, or drop the series that need "
        "naming."
    )


def _thin_numeric_ticks(ax, renderer, clearance: float) -> bool:
    """Drop x ticks until the numbers on a CONTINUOUS axis have a gap.

    The wrapping fitter beside this one only handles a ``FixedLocator`` — a
    categorical axis, whose labels are the caller's own strings. A numeric
    axis is laid out by ``AutoLocator``, and the docstring's claim that it
    "already spaces them to fit" is not true: it picks a count from the axis
    length in INCHES, without knowing how wide the numbers will render. At
    4.6 in the ``line`` example printed "10000" and "15000" 1.5 px apart —
    closer than the space between two words, so they read as one number.

    Rotating is the wrong remedy here (the axis carries no names to read at
    an angle) and so is wrapping, so the tick COUNT comes down instead. The
    target is computed from the widest label rather than searched for, which
    costs one relayout instead of one per candidate count.
    """
    from chart_geometry import any_overlap
    from matplotlib.ticker import MaxNLocator

    if ax.get_xscale() != "linear":
        return False  # a log axis has fix_log_ticks, which knows about decades
    labels = _drawn_x_labels(ax)
    if len(labels) < 3 or not any_overlap(labels, renderer, clearance=clearance):
        return False
    widest = max(label.get_window_extent(renderer=renderer).width for label in labels)
    span = ax.get_window_extent(renderer=renderer).width
    ax.xaxis.set_major_locator(MaxNLocator(nbins=max(2, int(span // (widest + clearance)))))
    return True


def fit_tick_labels(fig) -> None:
    """Wrap, then tilt, then stand up any x tick labels that would collide.

    This has to run POST-LAYOUT and measure the AXES. The rule it replaces
    estimated a characters-per-slot budget from the FIGURE width, which is
    right for a lone chart and wrong by the column count for every panel: in
    a three-column grid each axes gets a third of the width, the estimate
    said the labels fit, and "GSM8K HumanEval MMLU" printed on top of itself
    as ``GSM8kmanEvalMLU``. Unreadable, and at exit 0.

    A numeric axis is handled separately, by ``_thin_numeric_ticks``: its
    labels are the locator's own numbers rather than the caller's names, so
    wrapping them is meaningless and rotating them costs the reader for
    nothing. Fewer ticks is the fix there.

    Three regimes for a CATEGORICAL axis, escalating only as far as needed,
    each verified by measuring the result rather than assuming it worked:

    * they already fit — leave them horizontal, since rotation costs the
      reader;
    * WRAP to the measured slot width. Long names (``retrieval efficiency``)
      need more vertical space at 90 degrees than layout will surrender, and
      the overflow is cut at the canvas edge: the labels came out as "ency"
      and "ples" — fragments that misidentify the bar they sit under;
    * TILT to 30 degrees, then stand them up at 90, where neighbours cannot
      collide however long they get.
    """
    from chart_geometry import all_axes, any_overlap
    from matplotlib.ticker import FixedLocator

    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    changed = False
    for ax in all_axes(fig):
        if not ax.axison:
            continue
        gap = _WORD_GAP_EM * plt.rcParams["xtick.labelsize"] * fig.dpi / 72.0
        if not isinstance(ax.xaxis.get_major_locator(), FixedLocator):
            changed |= _thin_numeric_ticks(ax, renderer, gap)
            continue
        slots = _drawn_x_label_slots(ax)
        labels = [label for _, label in slots]
        if len(labels) < 2:
            continue
        # A gap, not merely no overlap: ``waterfall`` shipped "− reranking−
        # self-consistency" because two labels stopped exactly against each
        # other, which passes an intersection test and reads as one word.
        if not any_overlap(labels, renderer, clearance=gap):
            continue

        texts = [label.get_text() for label in labels]
        width = ax.get_window_extent(renderer=renderer).width
        # Character budget per slot, measured from a label that is already
        # drawn rather than from the point size — the average glyph is not
        # half an em, and the error compounds across a row of categories.
        widest = max(labels, key=lambda label: label.get_window_extent(renderer=renderer).width)
        per_char = widest.get_window_extent(renderer=renderer).width / max(
            1, len(widest.get_text())
        )
        budget = max(4, int(width / len(labels) / max(1.0, per_char)))

        wrapped = [textwrap.fill(text, budget, break_long_words=False) for text in texts]
        if max(text.count("\n") for text in wrapped) < 3:
            ax.set_xticklabels(_relabelled(ax, slots, wrapped))
            plt.setp(_drawn_x_labels(ax), rotation=0, ha="center")
            if not any_overlap(_drawn_x_labels(ax), renderer, clearance=gap):
                changed = True
                continue
        # Wrapping was not enough, or produced a column of fragments. Undo it
        # before tilting: a rotated multi-line label is unreadable twice over.
        ax.set_xticklabels(_relabelled(ax, slots, texts))
        plt.setp(_drawn_x_labels(ax), rotation=30, ha="right", rotation_mode="anchor")
        if any_overlap(_drawn_x_labels(ax), renderer, clearance=gap):
            plt.setp(_drawn_x_labels(ax), rotation=90, ha="center", rotation_mode="default")
        changed = True
    if changed:
        # Taller or tilted labels change every axes' height; let layout settle.
        fig.canvas.draw()


def _swatch(handle) -> tuple:
    """Everything a reader can use to tell one legend entry from another.

    Colour, dash pattern and marker — read off the drawn handle rather than
    from whatever the renderer intended, so a patch and a line are compared on
    the same terms and a renderer that sets the colour twice cannot disagree
    with itself.
    """
    import matplotlib.colors

    def rgba(getter):
        try:
            value = getter()
        except (AttributeError, TypeError):
            return None
        if isinstance(value, list | tuple) and value and not isinstance(value[0], int | float):
            value = value[0]
        try:
            return tuple(round(c, 4) for c in matplotlib.colors.to_rgba(value))
        except (ValueError, TypeError):
            return None

    face = rgba(getattr(handle, "get_facecolor", None)) or rgba(getattr(handle, "get_color", None))
    edge = rgba(getattr(handle, "get_edgecolor", None))
    style = getattr(handle, "get_linestyle", lambda: None)()
    marker = getattr(handle, "get_marker", lambda: None)()
    # SIZE is a channel too, and the one ``bubble``'s size key runs on: its
    # three entries share a colour and a marker on purpose and differ only in
    # how big they are drawn. Rounded, because a size key computed from the
    # data lands on values that are equal to the eye but not to a float.
    size = getattr(handle, "get_markersize", lambda: None)()
    if size is None:
        sizes = getattr(handle, "get_sizes", lambda: None)()
        size = float(sizes[0]) if sizes is not None and len(sizes) else None
    return (face, edge, str(style), str(marker), None if size is None else round(float(size), 1))


def assert_axis_names_are_unique(fig) -> None:
    """Refuse an axis that gives two different positions the same name.

    A categorical axis IS the key to the figure: the bar over "ARC" is the
    ARC bar. Two positions called "ARC" and the key stops working — the
    reader cannot say which is which, and nothing about the picture looks
    wrong. It arrives by three different routes, which is why this reads the
    DRAWN ticks rather than the spec: from ``categories`` on a bar, from the
    series labels on a ``box``/``violin``/``strip``, and from the two column
    headings on a ``slope``.

    Blanks are exempt — an empty category is a spacer between two groups of
    bars, and a figure may have several. Numeric axes never repeat a value,
    so this only ever fires on names.
    """
    from chart_geometry import all_axes

    for ax in all_axes(fig):
        if not ax.axison or ax.get_label() == "<colorbar>":
            continue
        for which, ticks in (("x", ax.get_xticklabels()), ("y", ax.get_yticklabels())):
            seen: set[str] = set()
            for tick in ticks:
                name = tick.get_text().strip()
                if not name or not tick.get_visible():
                    continue
                if name in seen:
                    raise RuntimeError(
                        f"the {which} axis names {name!r} twice, at two different "
                        "positions, so the label stops identifying which one it means. "
                        "Give them names that tell them apart, or combine them if they "
                        "really are one thing. An EMPTY name is fine and is how a spacer "
                        "between two groups is written."
                    )
                seen.add(name)


def assert_series_can_be_told_apart(fig, spec: dict) -> None:
    """A multi-series figure that draws no legend at all names nothing.

    ``assert_series_are_distinguishable`` reads the LEGEND, so it is blind to
    the spec that gives no series a label: no labels, no legend, nothing for it
    to inspect. Measured on a twelve-series bar — exits 2 with labels ("the
    legend gives 's0' and 's8' the same colour"), exits 0 without them, having
    drawn series 8..11 in exactly the fills of 0..3. SKILL.md lists that figure
    among the failures the skill catches; it caught the labelled half.

    Placed HERE, after the draw, rather than in ``chart_validate``. Several
    renderers already refuse an unnamed series with a message that says what
    the name is FOR — a survival arm in the at-risk table, a method on the
    critical-difference axis, a splom variable that labels a row and a column.
    A rule in the validator runs before all of them and replaces three good
    messages with one generic one; the suite caught exactly that, three times.
    By the time this runs, every renderer has had its say.

    ``categories`` naming the series one-for-one is the other way a spec can
    identify them — ``beeswarm`` puts one group per category on the axis and
    wants no legend — so that counts and is not refused.
    """
    from matplotlib.legend import Legend

    series = spec.get("series")
    if not isinstance(series, list):
        return
    entries = [entry for entry in series if isinstance(entry, dict)]
    if len(entries) < 2:
        return
    if any(str(entry.get("label") or "").strip() for entry in entries):
        return
    groups = spec.get("categories")
    if isinstance(groups, list) and len(groups) == len(entries):
        return
    if any(
        text.get_text().strip() for legend in fig.findobj(Legend) for text in legend.get_texts()
    ):
        return
    raise RuntimeError(
        f"{len(entries)} series and not one carries a 'label', so the figure draws no "
        f"legend and nothing on it says which series is which — past {len(PALETTE)} "
        "the colours repeat outright as well. Name every series, or use 'categories' "
        "with one entry per series when the axis names them."
    )


def assert_series_are_distinguishable(fig) -> None:
    """Refuse a legend in which two entries look exactly alike.

    The palette holds eight colours and wraps, which is why the dash pattern
    became a second channel — "series 1 and 9 were pixel-identical, which
    makes a legend unusable". The same failure returns further out and in the
    renderers that have no second channel: a twelve-series ``bar`` shipped
    four PAIRS of identical swatches, and a fifty-series ``line`` wrapped both
    channels at series 32. Both at exit 0, and a reader cannot tell which line
    is which.

    Measured on the drawn handles rather than counted, so it holds for bars,
    lines, patches and markers alike, and a renderer that adds a third channel
    later needs no change here.
    """
    from matplotlib.legend import Legend

    for legend in fig.findobj(Legend):
        labels = [text.get_text() for text in legend.get_texts()]
        # The mirror of the check below, and the same conclusion by the other
        # route: two entries carrying ONE name, in different colours. The
        # swatch test cannot see it — the swatches differ, which is the whole
        # point — and the reader is left with "Baseline" twice and no way to
        # say which curve either of them is.
        named: dict[str, int] = {}
        for position, label in enumerate(labels):
            if not label.strip() or label.startswith("_"):
                continue
            if label in named:
                raise RuntimeError(
                    f"the legend names {label!r} twice, in two different styles, so a "
                    "reader cannot tell which mark it refers to. Two series may not "
                    "share a name — give them the names that tell them apart, or "
                    "combine them if they really are one series."
                )
            named[label] = position
        seen: dict[tuple, str] = {}
        for handle, label in zip(legend.legend_handles, labels, strict=False):
            key = _swatch(handle)
            if key in seen and seen[key] != label:
                raise RuntimeError(
                    f"the legend gives {seen[key]!r} and {label!r} the same colour, dash "
                    "pattern and marker, so a reader cannot tell them apart. The palette "
                    f"holds {len(PALETTE)} colours and the dash patterns multiply that to "
                    f"{len(PALETTE) * len(LINE_STYLES)} for line charts; past that, and past "
                    f"{len(PALETTE)} for anything drawn as a solid shape, the styles repeat. "
                    "Show fewer series — aggregate them, split them across panels, or draw "
                    "the spread with 'box'/'violin'/'ridgeline' instead of one line each."
                )
            seen[key] = label


def _grid_shape(fig) -> tuple[int, int] | None:
    """``(nrows, ncols)`` of the subplot grid, if this figure has one."""
    for ax in content_axes(fig):
        spec = ax.get_subplotspec()
        if spec is not None:
            rows, cols = spec.get_gridspec().get_geometry()
            return int(rows), int(cols)
    return None


def assert_layout_applied(warned: list, fig=None) -> None:
    """Fail if constrained layout gave up on this figure.

    When the axes are squeezed to nothing — too many panels, a legend wider
    than the figure, reserved margins that leave no room — matplotlib skips
    the layout pass and only *warns*. What lands on disk is a figure with
    overlapping or zero-size axes, drawn without complaint.

    Same reasoning as the glyph gate below: the CLI reported ``{"ok": true}``
    and exit 0 for a figure that was visibly badly laid out, which is the one
    outcome this renderer exists to make impossible.

    ``fig`` supplies the MEASUREMENTS. This is the most common refusal the
    generator issues, and it used to splice matplotlib's own sentence — "Try
    making figure larger or Axes decorations smaller" — which says nothing
    about how much larger, or how much smaller, or what the figure is now.
    A caller cannot act on that without guessing. It may be a closed figure:
    only geometry is read, which survives ``plt.close``.
    """
    if not any("constrained_layout not applied" in str(w.message) for w in warned):
        return

    measured = ""
    remedy = "Widen it with 'width_in' or a wider 'aspect', or shorten the title and labels."
    if fig is not None:
        width, height = (float(v) for v in fig.get_size_inches())
        shape = _grid_shape(fig)
        panels = len(content_axes(fig))
        if shape and shape != (1, 1):
            rows, cols = shape
            measured = (
                f" {panels} panel(s) in a {rows}x{cols} grid across {width:.3g} in "
                f"leaves {width / cols:.2g} in per cell, and the labels need more than that."
            )
            remedy = (
                "Widen it with 'width_in' or a wider 'aspect', cut 'ncols' so each cell gets "
                "more of the width, show fewer panels, or shorten the labels."
            )
        else:
            measured = (
                f" The canvas is {width:.3g} x {height:.3g} in, and its labels, legend and "
                "tick marks need more than that leaves for the data."
            )

    raise RuntimeError(
        "constrained layout could not place this figure, so the axes would be drawn "
        "overlapping or at zero size." + measured + " " + remedy
    )


def assert_all_glyphs_rendered(warned: list) -> None:
    """Fail if any character had no glyph in the resolved font.

    matplotlib draws a missing glyph as a hollow box and only *warns*. A
    figure whose axis labels are boxes is wrong in exactly the way this
    renderer exists to prevent — and it is the worst kind of wrong, because
    it depends on which fonts the machine happens to have. CJK renders fine
    on a developer laptop and as boxes inside the pipeline image, so the
    defect never shows up where it is introduced.
    """
    missing = sorted(
        {
            str(w.message).split("missing from font")[0].strip()
            for w in warned
            if "missing from font" in str(w.message)
        }
    )
    if missing:
        raise RuntimeError(
            "the figure's font has no glyph for: "
            + "; ".join(missing[:5])
            + (f" (+{len(missing) - 5} more)" if len(missing) > 5 else "")
            + ". These render as hollow boxes, not text. Install a font "
            "covering this script, or label the figure in Latin script."
        )
