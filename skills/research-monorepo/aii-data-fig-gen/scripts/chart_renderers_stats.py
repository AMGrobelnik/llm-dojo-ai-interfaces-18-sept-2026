"""Renderers for figures that ARE a statistical claim — not a picture beside one.

A separate family from the evaluation curves because these four go one step
further than a transform. A ROC curve still shows the reader every operating
point; a critical-difference diagram shows a DECISION — "these methods are
indistinguishable at alpha = 0.05" — and there is nothing on the page left to
check it against. Same for the other three: a Kaplan-Meier step is an
estimate of a population that was never fully observed, a limit of agreement
is an interval nobody measured, and an autocorrelation stem is a statistic
about a series the figure does not draw.

That is what makes them worth putting behind one gate. The arithmetic is
done HERE, from the raw observations, and never read from the spec, for the
same reason ``render_roc`` integrates its own AUC: a critical difference
passed in alongside the ranks can disagree with them, and the disagreement is
invisible — the bar joining two methods is drawn at whatever length it was
told, and a reader who trusts the figure concludes the opposite of what the
data says. Every number annotated below is computed from the points that were
plotted.

The refusals are the other half. Each of these charts has an input that makes
it a lie rather than merely a mess, and each is easy to produce by accident:

* methods scored on DIFFERENT datasets — mean ranks are only comparable
  within one set of tasks, so a missing column silently shifts one method's
  rank and moves it under the significance bar;
* a censoring flag that is not 0/1, or a ``times``/``events`` pair of
  different lengths — the pairing is positional, so one extra entry
  reassigns every event after it to the wrong subject;
* a difference plotted against one method instead of against the mean of
  both, which builds a correlation into the picture that is not in the data;
* an autocorrelation of a series with no variance, where every lag is 0/0.

None of those raises anything in matplotlib. All of them produce a clean,
confident, publication-shaped figure, which is exactly why they raise
``SpecError`` here, naming the key and the index.

Dependencies are numpy and matplotlib, deliberately. scipy has a
studentized-range distribution, a Kaplan-Meier estimator and an
autocorrelation routine, and none of them may be used: it is not a declared
dependency of this project, so importing it would break the pipeline image
where these figures are actually produced. The one thing that genuinely
cannot be recomputed from scratch — the studentized-range quantiles — is
embedded below as a table.
"""

from __future__ import annotations

import math

import matplotlib
import numpy as np
from chart_common import (
    SpecError,
    flag,
    legend_place,
    number_option,
    readable_ink,
)
from chart_common import (
    labels_for as _labels,
)
from chart_common import (
    numbers as _numbers,
)
from chart_common import (
    series_of as _series,
)
from chart_style import (
    PALETTE,
    literal,
    number,
    place_legend,
    series_style,
)
from matplotlib.backends.backend_agg import RendererAgg
from matplotlib.font_manager import FontProperties

# Reference geometry — the limits of agreement, and anything else the data is
# measured AGAINST rather than being data itself. Grey, thin and behind the
# data, so it is visible without competing with it.
_GUIDE = {"color": "#999999", "linewidth": 1.0, "zorder": 1}

# Ink for annotations that carry a number the reader is meant to act on.
_INK = "#1A1A1A"

# The two-sided normal quantile for a 95% interval. Written out because it
# appears in three of the four charts below and each one states it on the
# figure, so the constant and the caption cannot drift apart.
_Z95 = 1.959963984540054

# A white plate under a label that sits over the plot area. Established by
# ``render_funnel``; used here for the two corner notes that state a sample
# size, which have nowhere outside the data to go.
_PLATE = {"facecolor": "white", "edgecolor": "none", "pad": 1.2, "alpha": 0.85}


# --------------------------------------------------------------------------
# shared gates
#
# ``numbers()`` already refuses NaN, Infinity, strings, None and booleans.
# What it cannot know is what the numbers MEAN, and each check below is a
# defect that reaches a rendered figure looking entirely reasonable.
# --------------------------------------------------------------------------


def _reject_empty(values: np.ndarray, what: str, *, minimum: int, why: str) -> None:
    """Too few points to be the statistic the chart claims to show.

    matplotlib accepts a zero-length line and returns a valid figure, so an
    empty series is a chart with one of its groups simply absent — the reader
    sees a two-arm comparison and counts one. The estimators here fail
    earlier and quieter than that: a standard deviation over one pair is
    ``nan``, and a mean rank over zero datasets is ``nan``, both of which
    matplotlib draws as nothing at all.
    """
    if values.size < minimum:
        entries = "entry" if values.size == 1 else "entries"
        raise SpecError(f"{what} has {values.size} {entries}; {minimum} is the minimum. {why}")


def _events(values, what: str, *, expect: int) -> np.ndarray:
    """Censoring indicators, which must be exactly 1 (event) or 0 (censored).

    A stray 2 counts as an event in every risk-set product below and pulls
    the whole curve down; a ``-1`` used as "unknown" pulls it up past 1. The
    length is pinned to ``times`` because the pairing is POSITIONAL — one
    extra entry reassigns every subject after it to somebody else's outcome,
    and the resulting curve is smooth, plausible and about nobody.
    """
    flags = _numbers(values, what, expect=expect)
    for i, v in enumerate(flags):
        if v not in (0.0, 1.0):
            raise SpecError(
                f"{what}[{i}] is {v:g} — an event flag is 1 (the event was observed) "
                "or 0 (the subject was censored, i.e. left the study still "
                "event-free). JSON true/false is not a number and is refused earlier."
            )
    return flags


def _nonnegative(values: np.ndarray, what: str, *, why: str) -> None:
    """Times, durations and lags cannot run backwards."""
    below = [(i, v) for i, v in enumerate(values) if v < 0.0]
    if below:
        i, v = below[0]
        raise SpecError(f"{what}[{i}] is {v:g}, which is negative. {why}")


def _named(s: dict, i: int, *, why: str) -> str:
    """A series' display name, required where the name IS the content.

    Most charts here can fall back to a numbered category. These cannot: a
    critical-difference diagram is a list of method names against a rank
    axis, and an at-risk table is a list of arm names against counts. An
    auto-generated "Method 3" in either would be a figure that names the
    wrong thing rather than one that names nothing.
    """
    label = s.get("label")
    if not isinstance(label, str) or not label.strip():
        raise SpecError(f"series[{i}] has no 'label'. {why}")
    return literal(label)


def _text_widths_in(texts: list[str], fig, *, size: float | None = None) -> list[float]:
    """Rendered width of each string, in inches, at this figure's font.

    Two of these charts reserve a MARGIN for text — the method names beside a
    rank axis, the arm names beside an at-risk table — and the reservation
    has to be made in data coordinates before anything is drawn. Estimating
    it from the character count is what produced the truncated labels this
    skill keeps refusing elsewhere: at the same length, "IIIl" and "WWWM"
    differ by a factor of three.

    An Agg renderer is built here rather than taken from the figure's canvas
    because the canvas is whatever the caller's backend supplied, and only
    Agg exposes text metrics without a completed draw. Constructing one costs
    about 50 microseconds and is exact: measured at the figure's own dpi it
    agrees with a laid-out ``Text`` artist to the last decimal.
    """
    renderer = RendererAgg(1, 1, fig.dpi)
    prop = FontProperties(size=size if size is not None else matplotlib.rcParams["font.size"])
    return [renderer.get_text_width_height_descent(t, prop, False)[0] / fig.dpi for t in texts]


def _text_height_in(fig, *, size: float | None = None) -> float:
    """Cap height of one line of text, in inches, at this figure's font."""
    renderer = RendererAgg(1, 1, fig.dpi)
    prop = FontProperties(size=size if size is not None else matplotlib.rcParams["font.size"])
    return renderer.get_text_width_height_descent("Ag", prop, False)[1] / fig.dpi


# What a heading costs a panel cell in height. ``panel`` wraps a sub-title to
# as many lines as the cell is narrow, so this is an allowance rather than a
# measurement — and it is deliberately generous, because under-stating it
# lets the row-spacing check below pass a figure whose rows then collide.
_HEADING_IN = 0.5


def _cell_shape(ax) -> tuple[int, int]:
    """Rows and columns of the grid this axes belongs to; (1, 1) if it is alone.

    ``panel`` composes any renderer into a subplot grid, and a cell of a two
    by two grid has half the width and half the height of the figure. Sizing
    a name column against the FIGURE there reserved twice the room the cell
    had, and the diagram came out with its rows on top of each other.
    """
    spec = ax.get_subplotspec()
    if spec is None:
        return 1, 1
    rows, cols = spec.get_gridspec().get_geometry()
    return max(1, rows), max(1, cols)


def _plot_width_in(ax, *, margin_in: float) -> float:
    """Usable width of this axes in inches, before constrained layout runs.

    The renderer is called before any layout pass, so the axes has no final
    position yet — but the FIGURE width is fixed at build time, the grid
    divides it evenly, and what layout takes off each cell is the axis
    decoration, which is known per chart. ``margin_in`` is that allowance.
    Under-stating it is the safe direction: the reserved margin then comes
    out slightly wide and the labels sit a little further out, where
    over-stating it would let them run into the plot.
    """
    _, cols = _cell_shape(ax)
    return max(1.0, float(ax.figure.get_size_inches()[0]) / cols - margin_in)


def _plot_height_in(ax, *, margin_in: float) -> float:
    """Usable height of this axes in inches, on the same reasoning as width.

    A cell of a multi-row panel also carries its own heading, which ``panel``
    wraps to as many lines as it needs, so the allowance grows there.
    """
    rows, _ = _cell_shape(ax)
    return max(
        0.6, float(ax.figure.get_size_inches()[1]) / rows - margin_in - _HEADING_IN * (rows > 1)
    )


def _figure_height_for(ax, plot_in: float, *, margin_in: float) -> float:
    """Figure height that would give this axes ``plot_in`` inches to draw in.

    The exact inverse of ``_plot_height_in``, so that a refusal which suggests
    a taller canvas suggests one that actually works — a near-miss suggestion
    is worse than none, because the caller follows it and is refused again.
    """
    rows, _ = _cell_shape(ax)
    return (plot_in + margin_in + _HEADING_IN * (rows > 1)) * rows


def _statistic_legend(ax, spec: dict, *, within: tuple[float, ...], ncols: int = 1) -> None:
    """One entry per curve, in free space inside ``within``.

    ``chart_common.draw_legend`` is built for the other shape of chart: it
    BUYS room by widening the y-range 18% and lays entries out in columns.
    Neither works here. Stretching a survival axes past 1.0 puts the "all
    subjects alive" line somewhere other than the top of the frame, and the
    columns run wider than the figure as soon as an entry carries its median.

    Its rule is kept — a legend that only restates the y-label is noise — but
    the threshold differs: every entry here carries a number the axes cannot
    show, so even a lone series earns its space.

    ``within`` is the ``(x0, y0, width, height)`` of the region, in axes
    fractions, that automatic placement is allowed to use. It exists because
    ``best`` considers lines, patches and collections only: every band of
    text these charts reserve — the at-risk table, the limits-of-agreement
    column — is invisible to it, and a legend landed squarely on top of one.
    """
    handles, _ = ax.get_legend_handles_labels()
    if not handles:
        return
    place_legend(
        ax,
        loc=legend_place(spec) or "best",
        ncols=ncols,
        bbox_to_anchor=within,
        bbox_transform=ax.transAxes,
    )


# --------------------------------------------------------------------------
# critical-difference diagram
# --------------------------------------------------------------------------

# Critical values for the two-tailed Nemenyi test, indexed by k - 2 where k is
# the number of methods. Each entry is the upper alpha quantile of the
# studentized range for infinitely many degrees of freedom, DIVIDED BY sqrt(2)
# — the form Demsar (2006, JMLR 7:1-30, Table 5) tabulates, so that
#
#     CD = q_alpha * sqrt(k(k+1) / (6N))
#
# is the critical difference in mean ranks directly.
#
# Embedded rather than computed because the studentized range has no closed
# form: its cdf is a one-dimensional integral over the normal density, which
# means either a quadrature routine written here or scipy, and scipy is not a
# declared dependency of this project. A table of 38 constants is the smaller
# and more auditable of the two. The first entry of each row is a check on
# the rest: at k = 2 the test reduces to a two-sided normal quantile, and
# 1.959964 and 1.644854 are exactly those.
#
# Every entry is the six-decimal rounding of that integral, computed by
# Gauss-Legendre quadrature. Two do NOT match the table that circulates with
# most implementations of this diagram — at alpha = 0.05 it carries 3.030879
# for k = 8 (last digit) and 3.391273 for k = 15, where the integral gives
# 3.030878 and 3.391230. The second is two digits transposed and has been
# copied from library to library. The computed values are used below.
_NEMENYI_Q: dict[float, tuple[float, ...]] = {
    0.05: (
        1.959964, 2.343701, 2.569032, 2.727774, 2.849705,  # k = 2..6
        2.948320, 3.030878, 3.101730, 3.163684, 3.218654,  # k = 7..11
        3.268004, 3.312739, 3.353618, 3.391230, 3.426041,  # k = 12..16
        3.458425, 3.488685, 3.517073, 3.543799,            # k = 17..20
    ),
    0.10: (
        1.644854, 2.052293, 2.291341, 2.459516, 2.588521,  # k = 2..6
        2.692732, 2.779884, 2.854606, 2.919889, 2.977768,  # k = 7..11
        3.029694, 3.076733, 3.119693, 3.159199, 3.195743,  # k = 12..16
        3.229723, 3.261461, 3.291224, 3.319233,            # k = 17..20
    ),
}  # fmt: skip

_MAX_METHODS = 2 + len(_NEMENYI_Q[0.05]) - 1

# The diagram's vertical layout, in units of one method row. The axis is at
# zero and everything hangs below it, which is why every constant is negative.
_CD_RULE_Y = -0.52  # the critical-difference ruler, just under the axis
_CLIQUE_TOP = -1.05  # first row of significance bars
_CLIQUE_STEP = -0.30  # each further row of bars, when they would overlap
_ROW_GAP = -0.62  # from the lowest bar to the first method row
_ROW_STEP = -1.0  # between method rows
# Below the last row: one clear row for the caption stating the CD, then a
# margin. Keeping it a whole row means the row-spacing check below covers the
# caption's clearance too, rather than leaving it as a second thing to get
# right.
_FOOT_MARGIN = 1.45
# Overhang on a significance bar, in rank units, so that the two methods it
# joins sit clearly INSIDE it rather than at its exact ends.
_BAR_OVERHANG = 0.05


def _alpha_for(spec: dict) -> float:
    """The significance level, which must be one the table covers."""
    # `number_option`, not `_numbers([x], ...)[0]`: the array validator was
    # being handed a one-element list to reuse its checks, and its message came
    # back as "'alpha'[0] is nan" — which reads as though alpha were a list and
    # sends the caller looking for an index that does not exist.
    value = number_option(spec, "alpha", 0.05)
    for known in _NEMENYI_Q:
        if abs(value - known) < 1e-9:
            return known
    # ``.12g``, not ``g``: ``g`` shows six significant digits, so 0.05000001 —
    # a value this check has just REFUSED — printed as "0.05", one of the two
    # levels the next sentence tells the caller to use. The message read
    # "'alpha' is 0.05 … use 0.05 or 0.10", which is advice they believe they
    # already followed. Twelve digits cannot round onto either level, because
    # the tolerance above is 1e-9.
    raise SpecError(
        f"'alpha' is {value:.12g}. The Nemenyi critical values are tabulated for "
        "0.05 and 0.10 only — the statistic has no closed form, so an arbitrary "
        "level cannot be computed here. Use one of those two."
    )


def _rank_row(scores: np.ndarray, *, higher_is_better: bool) -> np.ndarray:
    """Ranks of one dataset's scores, 1 = best, ties sharing their mean rank.

    Ties MUST be averaged rather than broken. Splitting them makes the
    diagram depend on the order the methods happened to be listed in — two
    methods that scored identically get ranks 3 and 4, and the one that was
    typed first moves half a rank closer to the top on every tied dataset.
    Averaging is also what keeps the ranks of each dataset summing to
    k(k+1)/2, which is the invariant everything downstream is checked against.
    """
    ordered = np.argsort(-scores if higher_is_better else scores, kind="stable")
    ranks = np.empty(scores.size, dtype=float)
    ranks[ordered] = np.arange(1, scores.size + 1, dtype=float)
    run = scores[ordered]
    start = 0
    while start < run.size:
        stop = start
        while stop + 1 < run.size and run[stop + 1] == run[start]:
            stop += 1
        if stop > start:
            # Mean of the ranks start+1 .. stop+1, assigned to every member.
            ranks[ordered[start : stop + 1]] = (start + stop + 2) / 2.0
        start = stop + 1
    return ranks


def _rank_source(series: list[dict]) -> str:
    """Whether the methods carry scores or precomputed per-dataset ranks.

    Mixing them is refused rather than resolved. The two are on different
    scales, so a figure built from three sets of scores and one set of ranks
    ranks the ranks — putting a method that came first everywhere at the
    bottom of the diagram, with nothing on the page to show it.
    """
    scored = [i for i, s in enumerate(series) if s.get("values") is not None]
    ranked = [i for i, s in enumerate(series) if s.get("ranks") is not None]
    if scored and ranked:
        raise SpecError(
            f"series{scored} carry 'values' (a score per dataset) but series{ranked} "
            "carry 'ranks' (a rank per dataset). One diagram cannot mix the two — "
            "scores are ranked here, so a series already in ranks would be ranked "
            "again. Convert them all to one form."
        )
    if not scored and not ranked:
        raise SpecError(
            "no method carries data. Each series needs either 'values' — its score "
            "on every dataset, ranked here — or 'ranks', its already-computed rank "
            "on every dataset. Every method must cover the SAME datasets, in the "
            "same order."
        )
    return "values" if scored else "ranks"


def _mean_ranks(spec: dict, series: list[dict]) -> tuple[np.ndarray, int, str]:
    """Mean rank per method, the dataset count, and what the axis means.

    The dataset count is derived from the data rather than accepted from the
    spec because it divides the critical difference: an N that is one too
    large narrows the bar and turns a tie into a claimed win.
    """
    source = _rank_source(series)
    k = len(series)
    width = len(series[0].get(source) or [])
    rows = []
    for i, s in enumerate(series):
        row = _numbers(s.get(source), f"series[{i}].{source}", expect=width)
        _reject_empty(
            row,
            f"series[{i}].{source}",
            minimum=2,
            why=(
                "A critical difference divides by the number of datasets, so a "
                "single one leaves the test with no power at all and the diagram "
                "would join every method to every other."
            ),
        )
        rows.append(row)
    table = np.vstack(rows)  # methods down, datasets across

    if source == "values":
        higher_is_better = flag(spec, "higher_is_better", True)
        ranks = np.vstack(
            [_rank_row(table[:, j], higher_is_better=higher_is_better) for j in range(width)]
        ).T
        meaning = "highest score" if higher_is_better else "lowest score"
    else:
        # `in` rather than `.get(...) is not None`: the refusal says the key
        # "was given", and an explicit null was given too. It also keeps this
        # off the list of places that read a gated option straight off the
        # spec — nothing here wants the VALUE, only whether it is present.
        if "higher_is_better" in spec:
            raise SpecError(
                "'higher_is_better' was given alongside precomputed 'ranks'. A rank "
                "is already ordered — 1 is the best — so the flag has nothing to "
                "act on, and setting it suggests these are scores rather than ranks."
            )
        ranks = table
        meaning = "best"
        # Ranks of k methods on one dataset sum to k(k+1)/2 whatever the ties.
        # A column that does not is not a ranking OF THESE METHODS: usually it
        # was computed over a larger set and a method has been dropped, which
        # shifts everyone left and moves the whole diagram.
        expected = k * (k + 1) / 2.0
        for j in range(width):
            total = float(ranks[:, j].sum())
            if abs(total - expected) > 1e-6:
                raise SpecError(
                    f"the ranks for dataset {j} sum to {total:g}, but {k} methods "
                    f"ranked against each other must sum to {expected:g} — that "
                    "holds for any pattern of ties. These ranks were computed over "
                    "a different set of methods, so they cannot be compared here."
                )

    # Dataset names are not drawn, but a list of them that disagrees with the
    # data means one of the two is stale, and the figure would be about the
    # other one.
    _labels(spec, width)
    return ranks.mean(axis=1), width, meaning


def _cliques(ranks: np.ndarray, cd: float) -> list[tuple[int, int]]:
    """Maximal runs of methods, in rank order, spanning no more than the CD.

    A bar is drawn per run, and a run is only worth drawing if it joins at
    least two methods. Runs contained in another are dropped: the containing
    bar already makes the same statement, and drawing both stacks two bars
    with the same left end, which reads as two different findings.
    """
    order = np.arange(ranks.size)
    runs = []
    for i in order:
        j = i
        # A hair of tolerance: a gap of exactly CD is not a significant one,
        # and floating-point arithmetic on a sum of thirds routinely lands a
        # ulp above it.
        while j + 1 < ranks.size and ranks[j + 1] - ranks[i] <= cd + 1e-9:
            j += 1
        if j > i:
            runs.append((int(i), int(j)))
    return [r for r in runs if not any(a <= r[0] and r[1] <= b and (a, b) != r for a, b in runs)]


def _bar_levels(runs: list[tuple[int, int]], ranks: np.ndarray) -> list[int]:
    """A row for each significance bar such that no two on a row overlap.

    Overlapping bars on one row merge into a single longer bar, which claims
    a group that was never tested. Greedy from the top: each bar takes the
    first row whose last bar ended before this one starts.
    """
    ends: list[float] = []
    levels = []
    for lo, hi in runs:
        start, stop = ranks[lo] - _BAR_OVERHANG, ranks[hi] + _BAR_OVERHANG
        for level, end in enumerate(ends):
            if start > end + 0.02:
                ends[level] = stop
                levels.append(level)
                break
        else:
            ends.append(stop)
            levels.append(len(ends) - 1)
    return levels


# Inches between a name and the end of its leader line, and between that end
# and the rank axis. Both are fixed lengths on the page rather than fractions
# of the rank range, so the diagram looks the same at any number of methods.
_NAME_GAP = 0.10
_LEADER_OVERHANG = 0.16
# Floor on a name column, so the "CD" caption on the ruler has somewhere to
# sit even when every method is called something like "SVM".
_MIN_NAME_COLUMN = 0.45


def _reserve_label_columns(ax, left: list[str], right: list[str], span: float) -> tuple[float, ...]:
    """Data-unit padding either side of the rank axis for the method names.

    The rank axis has to occupy what is left of the axes once both columns of
    names are laid out, so the mapping between inches and rank units depends
    on the padding and the padding depends on the mapping. Solved directly:
    the names take a fixed number of inches, the rank range takes the rest,
    and that fixes the scale.

    Both margins are measured to land the OUTER edge of the widest name
    exactly on the edge of the axes. Reserving less than that does not clip
    anything — the names are drawn in data coordinates and simply hang past
    the axes — but constrained layout then shrinks the axes to cover the
    overflow, at which point the reservation is paid for twice and the rank
    axis ends up squeezed into the middle third of the figure.
    """
    fig = ax.figure
    size = matplotlib.rcParams["font.size"] - 0.5
    fixed = _NAME_GAP + _LEADER_OVERHANG
    wide_left = max([*_text_widths_in(left, fig, size=size), _MIN_NAME_COLUMN]) + fixed
    wide_right = max([*_text_widths_in(right, fig, size=size), _MIN_NAME_COLUMN]) + fixed
    usable = _plot_width_in(ax, margin_in=0.45)
    if wide_left + wide_right > usable * 0.70:
        _, cols = _cell_shape(ax)
        room = (
            f"a {usable:.1f}-inch figure"
            if cols == 1
            else f"the {usable:.1f} inches this panel cell has"
        )
        raise SpecError(
            f"the method names need {wide_left + wide_right:.1f} inches of margin, "
            f"leaving under a third of {room} for the rank axis itself — the axis IS "
            "the comparison, so at that width the diagram stops making its own point. "
            + (
                "Shorten the names, or widen the figure with 'width_in'."
                if cols == 1
                else "A rank axis wants the full page width: give this one a figure "
                "of its own rather than a cell of a panel, or shorten the names."
            )
        )
    per_inch = span / (usable - wide_left - wide_right)
    return (
        wide_left * per_inch,
        wide_right * per_inch,
        _LEADER_OVERHANG * per_inch,
        _NAME_GAP * per_inch,
    )


def render_cd_diagram(ax, spec: dict) -> None:
    """Critical-difference diagram — mean ranks with Nemenyi significance bars.

    Ranks every method on every dataset (1 = best, ties sharing their mean
    rank), plots the mean rank of each on one axis, and joins with a bar any
    group whose mean ranks differ by less than the critical difference of the
    Nemenyi post-hoc test. Methods under one bar are the ones the evidence
    does NOT separate; a gap wider than a bar is the whole claim of the
    figure. The CD is computed here from the number of methods and datasets
    that were actually supplied and annotated on the axis, so the bars and
    the number can never describe different tests.

    Choose it whenever a paper compares several methods across many datasets
    or tasks and wants one figure for the headline. It is the accepted
    summary for exactly that, and it is honest about what a table of means is
    not: averaging accuracy over datasets with different difficulty and
    different scales is dominated by whichever dataset has the widest spread,
    while ranks weigh every dataset equally. Choose ``bar_sig`` instead for a
    handful of methods on ONE dataset, where the comparison is pairwise and
    the effect size matters more than the ordering; ``forest`` when the
    finding is one effect and its interval rather than an ordering; and a
    plain ``bar`` or ``heatmap`` of the score table when no test is being
    claimed — a CD diagram with three datasets is a diagram of noise, since
    the critical difference scales as 1/sqrt(N) and swallows everything.

    Each series is one method: ``label`` (required — the names are the
    figure) plus either ``values``, its score on every dataset, or ``ranks``,
    its already-computed rank on every dataset. Every method must cover the
    same datasets in the same order, which is enforced by length.
    ``higher_is_better`` (default true) says which end of ``values`` wins —
    set it false for error, loss or latency, and the axis label states which
    was assumed. ``alpha`` is 0.05 (default) or 0.10. ``categories`` may name
    the datasets; nothing is drawn from them, but a list that disagrees with
    the data is refused. Past about eight methods, give the figure a taller
    ``aspect``.
    """
    series = _series(spec)
    k = len(series)
    if k < 2:
        raise SpecError(
            "a critical-difference diagram compares methods AGAINST each other, so "
            f"one method ({series[0].get('label') or 'unnamed'}) has nothing to be "
            "ranked against. Two is the minimum."
        )
    if k > _MAX_METHODS:
        raise SpecError(
            f"{k} methods, but the Nemenyi critical values are tabulated up to "
            f"{_MAX_METHODS}. Past that the diagram is unreadable anyway — every "
            "bar spans most of the axis. Drop the methods that are not part of the "
            "claim, or split the comparison."
        )
    names = [
        _named(
            s,
            i,
            why=(
                "A critical-difference diagram is a list of method NAMES against a "
                "rank axis, so an unnamed method has nothing to draw."
            ),
        )
        for i, s in enumerate(series)
    ]

    ranks, n_datasets, meaning = _mean_ranks(spec, series)
    alpha = _alpha_for(spec)
    critical = _NEMENYI_Q[alpha][k - 2] * np.sqrt(k * (k + 1) / (6.0 * n_datasets))

    # Best first. Mean ranks are bounded by 1 and k by construction, so the
    # axis is exactly that range — no need to consult the data for it.
    order = np.argsort(ranks, kind="stable")
    sorted_ranks = ranks[order]
    lo, hi = 1.0, float(k)
    span = hi - lo

    # The better half of the methods label the left margin, the rest the
    # right, each column deepening towards the MIDDLE of the axis — the best
    # method takes the top row on the left, the worst the top row on the
    # right. That symmetry is what keeps the leader lines from crossing each
    # other however the ranks fall.
    split = (k + 1) // 2
    tail = order[split:]
    placed = [(int(m), row, True) for row, m in enumerate(order[:split])]
    placed += [(int(m), tail.size - 1 - row, False) for row, m in enumerate(tail)]
    # The name sits against the leader line and the rank at the outer edge,
    # mirrored on each side, so both columns read inward towards the axis.
    label_of = {
        m: (f"{ranks[m]:.2f}  {names[m]}" if left else f"{names[m]}  {ranks[m]:.2f}")
        for m, _, left in placed
    }
    pad_left, pad_right, overhang, gap = _reserve_label_columns(
        ax,
        [label_of[m] for m, _, left in placed if left],
        [label_of[m] for m, _, left in placed if not left],
        span,
    )
    # Where the leader lines turn out of the diagram: a fixed overhang past
    # each end of the rank axis, with the names beyond that.
    x_left, x_right = lo - overhang, hi + overhang

    runs = _cliques(sorted_ranks, float(critical))
    levels = _bar_levels(runs, sorted_ranks)
    deepest = _CLIQUE_TOP + _CLIQUE_STEP * max(levels, default=-1)
    first_row = deepest + _ROW_GAP
    rows = max(split, tail.size)
    bottom = first_row + _ROW_STEP * (rows - 1)

    # Rows closer together than the text is tall collide, and the collision is
    # one name reading across two methods. It is a canvas problem rather than
    # a data problem, so it is reported as one.
    units = abs(bottom) + _FOOT_MARGIN
    wanted = _text_height_in(ax.figure) * 1.45
    per_row = abs(_ROW_STEP) / units * _plot_height_in(ax, margin_in=0.55)
    if per_row < wanted:
        # The suggestion is the height that satisfies the same inequality —
        # and it is rounded UP to the one decimal it is printed at, not to the
        # nearest. Twenty methods on a 16:3 canvas need 3.0104 inches, which
        # prints as "3.0"; a caller who set exactly that came back one
        # hundredth of an inch short and was refused again, by a message
        # reading "leave 0.20 ... need about 0.20". A near-miss suggestion is
        # worse than none, because it costs the caller a round trip to learn
        # the advice was approximate.
        width, height = ax.figure.get_size_inches()
        needed = _figure_height_for(ax, wanted * units / abs(_ROW_STEP), margin_in=0.55)
        raise SpecError(
            f"{k} methods leave {per_row:.2f} inches per row, too little for a name at "
            f"this font size — the labels would overlap. On a {width:.1f} x {height:.1f} "
            f'inch canvas they need about {wanted:.2f}: set "aspect": "{width:.1f}:'
            f'{math.ceil(needed * 10) / 10:.1f}", '
            "or drop the methods that are not part of the claim."
        )

    for member, row, to_left in placed:
        y = first_row + _ROW_STEP * row
        end = x_left if to_left else x_right
        ax.plot(
            [ranks[member], ranks[member], end],
            [0.0, y, y],
            color=_INK,
            linewidth=1.0,
            solid_joinstyle="miter",
            zorder=3,
        )
        ax.text(
            end - gap if to_left else end + gap,
            y,
            label_of[member],
            ha="right" if to_left else "left",
            va="center",
            fontsize=matplotlib.rcParams["font.size"] - 0.5,
            color=_INK,
        )

    for (low, high), level in zip(runs, levels, strict=True):
        y = _CLIQUE_TOP + _CLIQUE_STEP * level
        ax.plot(
            [sorted_ranks[low] - _BAR_OVERHANG, sorted_ranks[high] + _BAR_OVERHANG],
            [y, y],
            color=_INK,
            linewidth=3.4,
            solid_capstyle="butt",
            zorder=4,
        )

    # The ruler: a segment exactly one critical difference long, so the reader
    # can carry it along the axis by eye. Its caption goes in the margin to
    # the LEFT of it rather than above it, where every method's leader line
    # runs — a label there has to be plated over the leaders, which reads as
    # three broken lines.
    ax.plot([lo, lo + critical], [_CD_RULE_Y, _CD_RULE_Y], color=_INK, linewidth=1.2, zorder=4)
    for end in (lo, lo + critical):
        ax.plot([end, end], [_CD_RULE_Y - 0.09, _CD_RULE_Y + 0.09], color=_INK, linewidth=1.2)
    ax.text(
        lo - overhang,
        _CD_RULE_Y,
        "CD",
        ha="right",
        va="center",
        fontsize=matplotlib.rcParams["font.size"] - 0.5,
        color=_INK,
    )
    # The number itself, and the test it came from, below every row — the one
    # band of the figure that is empty by construction, so the caption can
    # never land on the diagram. It stays SHORT on purpose: a text artist
    # anchored in data coordinates keeps its point size while constrained
    # layout shrinks the axes around it, so one that overflows starts a
    # feedback loop that ends in "axes sizes collapsed to zero".
    ax.text(
        lo - pad_left,
        bottom + _ROW_STEP,
        f"CD = {critical:.2f}   (Nemenyi, α = {alpha:g}, k = {k}, N = {n_datasets})",
        ha="left",
        va="center",
        fontsize=matplotlib.rcParams["font.size"] - 2,
        color="#555555",
    )

    # The rank axis itself: along the TOP, which is how these are read, and
    # the only place a scale can sit when every row below it is occupied.
    # The ruler can be longer than the whole rank axis — at two datasets the
    # critical difference exceeds the range of the ranks, which is the test
    # saying nothing here is separable. Widening for it keeps that visible;
    # lines, unlike text, are clipped to the axes, so otherwise the far cap
    # would simply vanish and the ruler would read as shorter than it is.
    ax.set_xlim(lo - pad_left, max(hi + pad_right, lo + critical + overhang))
    ax.set_ylim(bottom - _FOOT_MARGIN, 0.0)
    ax.set_xticks(np.arange(int(lo), int(hi) + 1))
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")
    ax.spines["top"].set_visible(True)
    ax.spines["top"].set_bounds(lo, hi)
    for side in ("left", "right", "bottom"):
        ax.spines[side].set_visible(False)
    ax.yaxis.set_visible(False)
    ax.grid(visible=False)
    # Which end is better is the one thing a rank axis cannot show, and
    # getting it backwards inverts the finding — so the axis says so, and
    # says which direction of the score it was told to believe.
    ax.set_xlabel(f"Mean rank (1 = {meaning})")


# --------------------------------------------------------------------------
# Kaplan-Meier survival
# --------------------------------------------------------------------------

# The at-risk table, in survival units below zero. Outside [0, 1] rather than
# inside it so no count can be read as a probability, and so the curve keeps
# the whole unit square it is compared against.
_RISK_TOP = -0.07
_RISK_ROW = 0.088


def _km(times: np.ndarray, events: np.ndarray) -> tuple[np.ndarray, ...]:
    """Kaplan-Meier survival and its Greenwood standard error.

    Returns arrays stepping at every observed EVENT time, starting from
    (0, 1). Censored observations never step the curve — they only shrink the
    risk set for later event times, which is exactly what makes this
    different from one minus an ECDF and why a censored study cannot be drawn
    with ``ecdf`` or ``step``.

    At equal times a subject censored at the same moment as somebody else's
    event still belongs in that event's risk set — the standard convention,
    because they were under observation when it happened. That falls out of
    ``count(time >= moment)`` rather than out of any ordering: the risk set
    and the death count are both taken by comparing VALUES, and the loop walks
    ``np.unique(time)``, which sorts on its own. The estimator is therefore
    permutation-invariant, checked over all 120 orderings of a five-subject
    sample containing a tied event and censoring.

    There used to be an ``np.lexsort((-events, times))`` here, described as
    what produced that convention. It did not — nothing downstream reads the
    order — and it survived being replaced by a plain stable sort with the
    whole suite green.

    The variance is Greenwood's:

        Var S(t) = S(t)^2 * sum_{t_i <= t} d_i / (n_i (n_i - d_i))

    When the last subjects at risk all have the event, n_i - d_i is zero and
    that term is infinite — but S(t) is zero there, so the product is taken
    as zero rather than as the ``nan`` that inf * 0 produces. A ``nan`` would
    make the band vanish silently over the tail, which reads as a tight
    interval exactly where the estimate is worst.
    """
    time, event = times, events

    step_t, step_s, step_se = [0.0], [1.0], [0.0]
    survival, greenwood = 1.0, 0.0
    for moment in np.unique(time):
        at_risk = int(np.count_nonzero(time >= moment))
        deaths = int(np.count_nonzero((time == moment) & (event == 1.0)))
        if deaths == 0:
            continue  # a censoring alone does not step the curve
        survival *= 1.0 - deaths / at_risk
        if at_risk > deaths:
            greenwood += deaths / (at_risk * (at_risk - deaths))
        step_t.append(float(moment))
        step_s.append(survival)
        step_se.append(survival * np.sqrt(greenwood))
    return np.asarray(step_t), np.asarray(step_s), np.asarray(step_se)


def _median_survival(step_t: np.ndarray, step_s: np.ndarray) -> float | None:
    """First time the curve reaches or drops below one half, if it ever does.

    "Not reached" is a real and common answer — a study that ends with most
    subjects alive has no median — and reporting the last observed time
    instead would understate survival by however long the study ran.
    """
    reached = np.nonzero(step_s <= 0.5)[0]
    return float(step_t[reached[0]]) if reached.size else None


def _at_risk_table(ax, arms: list[tuple], t_max: float) -> None:
    """Counts still under observation, in a band beneath the axis.

    A survival curve is unreadable without them. The tail of a Kaplan-Meier
    estimate is routinely drawn from a handful of subjects, and a step from
    0.4 to 0.2 looks identical whether it came from ten subjects or from the
    last two — the second is noise, and only the risk set tells them apart.

    The columns land on the x-ticks so each count sits under the time it
    belongs to, and the arm names go in a margin opened to the LEFT of zero,
    where the x-axis is bounded so no negative time is ever implied.
    """
    fig = ax.figure
    body = matplotlib.rcParams["font.size"] - 2.5
    # Falling back to the ends rather than indexing an empty list: the tick
    # locator has always put one at zero here, but a table that quietly
    # becomes a traceback is the one failure this CLI must not have.
    columns = [t for t in ax.get_xticks() if 0.0 <= t <= t_max] or [0.0, t_max]
    names = [name for name, *_ in arms]
    header = "At risk"
    widest = max(_text_widths_in([*names, header], fig, size=body))
    # The gap has to clear HALF of the leftmost count as well as the name:
    # that column is CENTRED on its tick, so at t = 0 it hangs back into the
    # margin, and a name sized to the margin alone runs into it.
    first = [f"{int(np.count_nonzero(times >= columns[0]))}" for _, times, _ in arms]
    gap = 0.12 + max(_text_widths_in(first, fig, size=body)) / 2.0
    per_inch = t_max / max(1.0, _plot_width_in(ax, margin_in=0.85) - widest - gap)
    left = -(widest + gap) * per_inch

    ax.text(
        left,
        _RISK_TOP + _RISK_ROW * 0.55,
        header,
        ha="left",
        va="center",
        fontsize=body,
        color="#555555",
    )
    for row, (name, times, colour) in enumerate(arms):
        y = _RISK_TOP - _RISK_ROW * row
        # The series colour, darkened until it is legible as TEXT. A hue
        # picked to separate 1.8 pt lines is not automatically readable at
        # 8 pt: the palette's amber measures 2.6:1 on the white page.
        ink = readable_ink(colour)
        ax.text(left, y, name, ha="left", va="center", fontsize=body, color=ink)
        for column in columns:
            ax.text(
                column,
                y,
                f"{int(np.count_nonzero(times >= column))}",
                ha="center",
                va="center",
                fontsize=body,
                color=ink,
            )
    floor = _RISK_TOP - _RISK_ROW * (len(arms) - 1)
    ax.set_xlim(left - 0.02 * t_max, ax.get_xlim()[1])
    ax.set_ylim(floor - _RISK_ROW * 0.9, 1.03)
    # Stop the frame at the data. Left running, the spines box in the table
    # as though it were part of the plot, and the x-axis grows a negative arm.
    ax.spines["left"].set_bounds(0.0, 1.0)
    ax.spines["bottom"].set_bounds(0.0, t_max)
    ax.set_xticks(columns)
    ax.yaxis.label.set_y(0.62)


def render_survival(ax, spec: dict) -> None:
    """Kaplan-Meier survival curves, with censoring ticks and Greenwood bands.

    Steps down at every observed event and holds flat between them, because
    that is all a censored study knows: between two events the estimate does
    not change, and a sloped line between them would claim a rate that was
    never observed. Censored subjects — those still event-free when
    observation stopped — are marked with a tick on the curve and leave the
    risk set without stepping it. Each curve is labelled with its median
    survival, computed from the drawn steps, or "not reached" when the curve
    never falls to one half.

    Choose it for any duration that some subjects have not finished yet: time
    to failure, time to first error, retention, session length, how long a
    pod ran before it was preempted. That last condition is the whole point —
    ``line`` and ``step`` would need a duration for every subject, so the
    unfinished ones have to be dropped (which biases every estimate towards
    the short durations that did finish) or counted as finished at the end of
    the study (which is worse). ``ecdf`` has exactly the same problem read
    from the other side. Choose ``hist`` when every duration is complete and
    the shape of their distribution is the finding, not the survival
    probability at a given time.

    Each series is one arm: ``times`` (the observation time per subject) and
    ``events`` (1 if the event happened at that time, 0 if the subject was
    censored there), paired positionally and therefore required to be the
    same length. ``"ci": true`` adds a 95% Greenwood band; ``"at_risk":
    true`` adds the risk-set counts underneath, which is what tells a reader
    whether the tail is an estimate or an anecdote.
    """
    series = _series(spec)
    show_ci = flag(spec, "ci", False)
    show_at_risk = flag(spec, "at_risk", False)
    arms, horizon = [], 0.0

    for i, s in enumerate(series):
        where = f"series[{i}]"
        if show_at_risk and len(series) > 1:
            _named(
                s,
                i,
                why=(
                    "Its row of the at-risk table needs a name — several arms of "
                    "counts with nothing but colour to tell them apart is a table "
                    "the reader has to guess at."
                ),
            )
        # No emptiness check on the line below: `_numbers` is the shared gate
        # and it refuses an empty list itself, one line up, with a message that
        # already says there is nothing to draw. `minimum=1` here means
        # `size < 1`, which is `size == 0`, which cannot get this far — the
        # reason a survival curve needs a subject to be about still holds, it
        # is simply stated where the check actually happens.
        times = _numbers(s.get("times"), f"{where}.times")
        _nonnegative(
            times,
            f"{where}.times",
            why=(
                "A survival time is measured from entry into the study, so it runs "
                "forward. A negative one usually means two dates were subtracted "
                "the wrong way round."
            ),
        )
        events = _events(s.get("events"), f"{where}.events", expect=times.size)

        step_t, step_s, step_se = _km(times, events)
        horizon = max(horizon, float(times.max()))
        # Carry the last step out to the longest follow-up. Stopping at the
        # final EVENT would hide the period after it, during which the
        # estimate is unchanged but real observation was still happening.
        if float(times.max()) > step_t[-1]:
            step_t = np.append(step_t, float(times.max()))
            step_s = np.append(step_s, step_s[-1])
            step_se = np.append(step_se, step_se[-1])

        style = series_style(i)
        median = _median_survival(step_t, step_s)
        summary = f"median {median:g}" if median is not None else "median not reached"
        name = literal(s["label"]) if s.get("label") else None
        ax.plot(
            step_t,
            step_s,
            drawstyle="steps-post",
            label=f"{name} ({summary})" if name else summary,
            **style,
        )
        if show_ci:
            # Clipped to the unit interval: a survival probability outside it
            # is not one, and a band drawn to 1.08 makes the axis lie about
            # where certainty ends.
            ax.fill_between(
                step_t,
                np.clip(step_s - _Z95 * step_se, 0.0, 1.0),
                np.clip(step_s + _Z95 * step_se, 0.0, 1.0),
                step="post",
                color=style["color"],
                alpha=0.16,
                linewidth=0,
            )
        censored = times[events == 0.0]
        if censored.size:
            # Each tick sits ON the curve, at the level the estimate holds at
            # that moment — the value of the last step at or before it.
            level = step_s[np.searchsorted(step_t, censored, side="right") - 1]
            ax.plot(
                censored,
                level,
                linestyle="none",
                marker="|",
                markersize=7,
                markeredgewidth=1.2,
                color=style["color"],
                zorder=4,
            )
        arms.append((name or "", times, style["color"]))

    if horizon <= 0.0:
        raise SpecError(
            "every observation time is 0, so there is no follow-up to draw — the "
            "curve would be a single point at the origin. Check the units: times "
            "rounded to whole days from a study measured in hours come out as zero."
        )
    ax.set_xlim(0.0, horizon * 1.02)
    ax.set_ylim(0.0, 1.03)
    ax.set_yticks(np.linspace(0.0, 1.0, 5))
    ax.set_xlabel("Time")
    ax.set_ylabel("Survival probability")
    if show_at_risk:
        _at_risk_table(ax, arms, horizon)
    # After the table, so that the region it reserved is excluded: ``best``
    # only looks at lines and patches, and would happily drop the legend on
    # top of a block of text it cannot see.
    floor, ceiling = ax.get_ylim()
    plot_floor = -floor / (ceiling - floor)
    _statistic_legend(ax, spec, within=(0.0, plot_floor, 1.0, 1.0 - plot_floor))


# --------------------------------------------------------------------------
# Bland-Altman agreement
# --------------------------------------------------------------------------


def render_bland_altman(ax, spec: dict) -> None:
    """Bland-Altman plot — the difference between two methods against their mean.

    Plots one point per subject: the difference between the two measurements
    against the average of them, with the mean difference (the bias) and the
    limits of agreement at bias ± 1.96 SD, each labelled with its value. The
    limits are the interval that contains 95% of the disagreements, which is
    the number a reader needs to decide whether the two methods can be used
    interchangeably — a bias near zero says nothing on its own if the limits
    are wider than the effect being measured. A funnel opening to the right
    means the disagreement grows with the size of the measurement.

    Choose it whenever two ways of measuring the SAME quantity are being
    compared: a cheap proxy metric against an expensive one, an automatic
    judge against human annotation, a profiler's estimate against wall clock.
    Choose it over a ``scatter`` of one method against the other, which is
    the instinctive figure and the misleading one: points cluster along the
    diagonal, the eye reads that as agreement, and a correlation coefficient
    fitted to it can sit at 0.99 while one method reads ten percent high
    throughout — correlation measures whether the two move together, not
    whether they agree. Plotting the difference against the MEAN rather than
    against either method matters for the same reason: regressing a
    difference on one of its own terms builds in a slope that is an artefact
    of the arithmetic. Choose ``residual`` when one of the two is a
    prediction rather than a measurement.

    Each series carries ``a`` and ``b``, the paired measurements, in the same
    subject order and therefore the same length; ``label`` names a subgroup
    to colour. The bias and limits are computed over ALL points, so a figure
    whose subgroups disagree with each other is showing that honestly rather
    than hiding it in one line per group. ``method_a`` and ``method_b`` name
    the two methods in the axis labels.
    """
    series = _series(spec)
    name_a = literal(spec.get("method_a", "A"))
    name_b = literal(spec.get("method_b", "B"))

    differences, averages = [], []
    for i, s in enumerate(series):
        where = f"series[{i}]"
        first = _numbers(s.get("a"), f"{where}.a")
        second = _numbers(s.get("b"), f"{where}.b", expect=first.size)
        _reject_empty(
            first,
            f"{where}.a",
            minimum=2,
            why=(
                "Limits of agreement are a standard deviation of the differences, "
                "which is undefined for a single pair — matplotlib would draw the "
                "two limits on top of the bias and the figure would claim perfect "
                "agreement."
            ),
        )
        difference, average = first - second, (first + second) / 2.0
        differences.append(difference)
        averages.append(average)
        ax.scatter(
            average,
            difference,
            s=26,
            alpha=0.7,
            color=series_style(i)["color"],
            edgecolors="none",
            label=literal(s["label"]) if s.get("label") else None,
            zorder=3,
        )

    difference = np.concatenate(differences)
    average = np.concatenate(averages)
    bias = float(difference.mean())
    # The SAMPLE standard deviation. Dividing by n instead of n-1 narrows the
    # limits of agreement, and the whole figure is an argument about how wide
    # they are.
    spread = float(difference.std(ddof=1))
    if spread == 0.0:
        raise SpecError(
            f"every pair differs by exactly {bias:g}, so both limits of agreement "
            "land on the bias line and their three labels print on top of each "
            "other. A constant offset is a calibration constant, not an agreement "
            "study — state it in the text."
        )
    upper, lower = bias + _Z95 * spread, bias - _Z95 * spread

    # Each line is labelled with its own value, in a margin opened to the
    # right of the last point and measured to fit them. Sitting them on top
    # of the data instead is the usual rendering and the usual defect: the
    # widest label is "−1.96 SD", the lower limit is where the outliers are,
    # and a plate over three of them hides the points the limit is about.
    labels = (
        (upper, f"+1.96 SD  {number(upper, '.3g')}", {"linestyle": "--", **_GUIDE}),
        (bias, f"Bias  {number(bias, '.3g')}", {"color": _INK, "linewidth": 1.2, "zorder": 2}),
        (lower, f"−1.96 SD  {number(lower, '.3g')}", {"linestyle": "--", **_GUIDE}),
    )
    note = matplotlib.rcParams["font.size"] - 1.5
    left, right = float(average.min()), float(average.max())
    widest = max(_text_widths_in([t for _, t, _ in labels], ax.figure, size=note)) + 0.14
    per_inch = max(right - left, 1e-9) / max(1.0, _plot_width_in(ax, margin_in=0.85) - widest)
    pad = max((right - left) * 0.03, 1e-9)
    ax.set_xlim(left - pad, right + widest * per_inch)
    for value, text, style in labels:
        ax.axhline(value, **style)
        # Sitting ON the line rather than centred over it: the line runs to
        # the edge of the frame underneath, so a centred label would need a
        # plate, and a plate leaves a visible break in a dashed line.
        ax.text(
            right + 0.10 * per_inch,
            value,
            text,
            ha="left",
            va="bottom",
            fontsize=note,
            color=_INK,
            zorder=5,
        )
    # Ticks only where there is data. The reserved margin is a label column,
    # and labelling it invites the reader to look for points out there.
    ax.set_xticks([t for t in ax.get_xticks() if left - pad <= t <= right])
    # Room for the three labels to sit above their lines without the topmost
    # running off the frame.
    height = max(upper - lower, abs(difference).max() * 2.0, 1e-9)
    ax.set_ylim(
        min(lower, float(difference.min())) - height * 0.10,
        max(upper, float(difference.max())) + height * 0.16,
    )
    ax.set_xlabel(f"Mean of {name_a} and {name_b}")
    ax.set_ylabel(f"Difference ({name_a} − {name_b})")
    ax.text(
        0.006,
        0.985,
        f"n = {difference.size} pairs",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=matplotlib.rcParams["font.size"] - 1.5,
        color="#555555",
        bbox=_PLATE,
    )
    # A legend only when there are subgroups to tell apart — one entry would
    # restate the y-label. It is kept out of the label column on the right,
    # which is text and therefore invisible to automatic placement.
    if len(series) > 1 and any(s.get("label") for s in series):
        first, last = ax.get_xlim()
        _statistic_legend(
            ax,
            spec,
            within=(0.0, 0.0, (right - first) / (last - first), 1.0),
            ncols=min(len(series), 3),
        )


# --------------------------------------------------------------------------
# autocorrelation
# --------------------------------------------------------------------------


def _autocorrelation(values: np.ndarray, lags: int) -> np.ndarray:
    """Sample autocorrelation at lags 0..``lags``, on the standard estimator.

    Every lag divides by the SAME total sum of squares — the whole series,
    not the n - k overlapping terms that went into the numerator. That is the
    convention R's ``acf`` and statsmodels' ``acf`` both use, and it is the
    one worth having: dividing each lag by its own overlap makes the estimate
    unbiased term by term but the resulting sequence is no longer guaranteed
    to be a valid autocorrelation function, and at long lags on a short
    series it produces correlations past 1.
    """
    centred = values - values.mean()
    total = float(np.dot(centred, centred))
    return np.array(
        [float(np.dot(centred[: centred.size - k], centred[k:])) / total for k in range(lags + 1)]
    )


def render_acf(ax, spec: dict) -> None:
    """Autocorrelation of one series against lag, with its significance band.

    A stem per lag showing how strongly the series correlates with itself k
    steps earlier, inside the band a white-noise series would stay within
    95% of the time. Lag 0 is 1 by definition and is drawn as the scale.
    What the shape says is standard: stems decaying slowly over many lags
    mean a trend the series has not been differenced out of; a stem standing
    clear of the band at a fixed period is seasonality; everything inside the
    band means the series is, as far as this test can tell, uncorrelated
    noise — which is the good outcome for a residual and the disappointing
    one for a signal.

    Choose it whenever a sequence is measured over time and the question is
    whether its points are independent: reward or loss across training steps,
    latency per request, queue depth, the residuals of any forecast. It is
    the diagnostic ``line`` cannot give — a plot of the series itself shows
    the level and hides the dependence, and the eye is unreliable about
    periodicity in a noisy trace. Choose ``line`` when the level over time is
    the finding, and ``residual`` when the question is whether errors depend
    on the FITTED VALUE rather than on the previous error.

    The single series carries ``values`` in time order — no ``x``, since a
    lag is a count of steps and an unevenly spaced series has no lags.
    ``lags`` sets how many to show, defaulting to min(40, n/2); past n/2 each
    estimate rests on fewer than half the observations. The band is
    ±1.96/sqrt(n), stated on the figure.
    """
    series = _series(spec)
    if len(series) > 1:
        raise SpecError(
            f"{len(series)} series were given, but an autocorrelation figure is about "
            "ONE sequence — two sets of stems at the same lags overlap into a single "
            "unreadable comb. Put each in its own 'panel'."
        )
    values = _numbers(series[0].get("values"), "series[0].values")
    _reject_empty(
        values,
        "series[0].values",
        minimum=4,
        why=(
            "An autocorrelation at lag k is a correlation over n - k terms, so a "
            "handful of points gives a figure of pure noise at every lag."
        ),
    )
    if float(values.std()) == 0.0:
        raise SpecError(
            f"series[0].values is constant ({values[0]:g} throughout). Autocorrelation "
            "divides by the variance of the series, so every lag would be 0/0 — "
            "matplotlib renders the resulting nan as a missing stem, which reads as "
            "a measured zero."
        )

    n = values.size
    default = min(40, n // 2)
    lags = int(_numbers([spec.get("lags", default)], "'lags'")[0])
    if lags != float(spec.get("lags", default)) or lags < 1:
        raise SpecError(f"'lags' must be a whole number of at least 1, got {spec.get('lags')!r}")
    if lags >= n:
        raise SpecError(
            f"'lags' is {lags} but the series has {n} points, so lag {lags} has no "
            "overlapping terms at all — it would draw as a stem at exactly zero, "
            f"which reads as a measured absence of correlation. Keep it near n/2 "
            f"({n // 2}), where every stem still rests on half the series."
        )

    correlation = _autocorrelation(values, lags)
    lag = np.arange(lags + 1)
    band = _Z95 / np.sqrt(n)
    colour = PALETTE[0]

    ax.axhspan(-band, band, color="#B0B0B0", alpha=0.22, linewidth=0, zorder=0)
    ax.axhline(0.0, color="#333333", linewidth=1.0, zorder=1)
    # vlines and markers rather than ``ax.stem``: stem overrides the house
    # colours with its own cycle and returns artists whose z-order puts the
    # baseline on top of the markers.
    ax.vlines(lag, 0.0, correlation, color=colour, linewidth=1.4, zorder=2)
    ax.plot(lag, correlation, linestyle="none", marker="o", markersize=4, color=colour, zorder=3)

    ax.set_xlim(-0.6, lags + 0.6)
    top = max(1.0, float(correlation.max()))
    ax.set_ylim(min(-band, float(correlation.min())) * 1.18 - 0.05, top * 1.14)
    ax.set_xlabel("Lag")
    ax.set_ylabel("Autocorrelation")
    ax.text(
        0.995,
        0.975,
        f"n = {n}, 95% band ±{band:.3f}",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=matplotlib.rcParams["font.size"] - 1.5,
        color="#555555",
        bbox=_PLATE,
    )


STATS_RENDERERS = {"cd_diagram": render_cd_diagram, "survival": render_survival,
                   "bland_altman": render_bland_altman, "acf": render_acf}  # fmt: skip
