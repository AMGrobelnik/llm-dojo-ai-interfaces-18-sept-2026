"""Seven figures that were still being hand-written because nothing covered them.

Each earns its place the same way the rest of the catalogue does: it is the
figure a paper actually draws for a question the existing types answer badly.

* ``beeswarm`` — every observation, packed so none hides another. ``strip``
  jitters at random, so at forty points per group it still stacks and the
  visible density stops matching the real one.
* ``volcano`` — effect size against significance, the standard screen when
  many comparisons were made at once. A ``bar`` of effects hides which of
  them survived correction; a table of p-values hides which effects are big.
* ``joint`` — a scatter with its two marginal distributions. The correlation
  and each variable's own shape are usually asked in the same breath, and
  splitting them across three figures loses the link.
* ``bump`` — rank over time, one line per item. ``slope`` does this for two
  time points; a leaderboard over eight releases needs the whole path, and on
  a value axis the reordering — which is the story — is invisible.
* ``splom`` — every pair of variables as its own scatter. ``corr`` gives one
  number per pair, and the same 0.81 is a straight line, two clusters, or a
  blob with an outlier.
* ``fan`` — nested quantile bands around a median. ``line`` takes one
  symmetric ± band, which assumes a symmetry a bounded or skewed quantity does
  not have: a ±std band on an accuracy near its ceiling implies scores above
  100%, and quantiles cannot.
* ``seqheat`` — a per-token quantity drawn ON the text it belongs to. A
  ``heatmap`` of the same numbers puts token indices on an axis, so the reader
  holds the sequence in their head; a ``bar`` per token loses the reading
  order the moment it wraps.
"""

from __future__ import annotations

import itertools

import numpy as np
from chart_common import (
    SpecError,
    cell_halo,
    colour_map,
    draw_legend,
    flag,
    ink_on,
    labels_for,
    number_option,
    numbers,
    require_positive,
    series_of,
    type_name,
)
from chart_style import PALETTE, literal, place_legend, place_point_label, series_style


def render_beeswarm(ax, spec: dict) -> None:
    """Every observation as a point, spread sideways in proportion to density.

    For when the reader must see the raw sample AND its density — feature
    attributions per instance, per-seed scores, latency per request. Choose
    over ``strip``, which offsets points at random and so still overlaps at
    any real n: the eye reads the resulting clumps as density and they are
    partly collision. Choose over ``violin`` when n is small enough that a
    smoothed density would invent shape the data does not support — twelve
    seeds and twelve thousand look identical once smoothed.

    Offsets are computed by binning on the value axis and spreading each
    bin's members evenly across a width proportional to how many it holds, so
    the outline traces the real histogram and the figure is reproducible
    rather than differently-random each run. The width available is fixed, so
    past roughly a hundred observations in one bin the markers do begin to
    touch; at that n the sample is large enough that ``violin`` is the better
    choice anyway, and its smoothing is no longer inventing anything.

    ``point_spread`` (default 0.34) is how wide the swarm may get in category
    units, and ``show_median`` (default true) draws the rule through each
    group.
    """
    series = series_of(spec)
    width = number_option(spec, "point_spread", 0.34, minimum=0.0)
    for i, entry in enumerate(series):
        values = numbers(entry.get("values"), f"series[{i}].values")
        # Bin height of roughly one marker, so members of a bin are the points
        # that would otherwise sit on top of each other.
        span = float(values.max() - values.min()) or 1.0
        bins = max(1, min(60, int(np.sqrt(values.size) * 3)))
        index = np.clip(((values - values.min()) / span * bins).astype(int), 0, bins - 1)
        offsets = np.zeros_like(values, dtype=float)
        # Scale against the busiest bin in THIS series, so the widest point of
        # the swarm is full width and every other is its share of that. The
        # divisor used to be a constant 8, which meant any bin past 8 members
        # drew at full width: 100 observations at one value and 8 at another
        # came out exactly the same ±0.34, reporting a 12x density difference
        # as no difference at all — in the one channel this chart type has.
        busiest = max(int(np.bincount(index, minlength=bins).max()), 2)
        for slot in range(bins):
            members = np.where(index == slot)[0]
            if members.size < 2:
                continue
            # Evenly spaced, centred: −w … +w with the widest bin at full width.
            spread = np.linspace(-1.0, 1.0, members.size)
            offsets[members] = spread * width * (members.size / busiest)
        ax.scatter(
            np.full(values.size, float(i)) + offsets,
            values,
            s=18,
            alpha=0.75,
            color=PALETTE[i % len(PALETTE)],
            edgecolors="none",
        )
        if flag(spec, "show_median", True):
            median = float(np.median(values))
            ax.plot(
                [i - width * 1.3, i + width * 1.3],
                [median, median],
                color="#333333",
                linewidth=1.6,
                solid_capstyle="butt",
            )
    labels = labels_for(spec, len(series))
    ax.set_xticks(np.arange(len(series)), labels=labels)
    ax.set_xlim(-0.6, len(series) - 0.4)


def render_volcano(ax, spec: dict) -> None:
    """Effect size against significance, with both thresholds drawn.

    The screen figure for many comparisons at once — every ablation, every
    feature, every prompt variant on one panel — where the finding is which
    ones are BOTH large and significant. Choose over a ``bar`` of effect
    sizes, which cannot show whether a difference survived multiple-testing
    correction, and over a table of p-values, which cannot show whether the
    significant ones are big enough to matter.

    Takes ``x``/``values`` like every other type, and also accepts ``effect``
    and ``p`` under their own names, which is how a spec for this figure reads
    naturally. Both spellings draw the same figure; neither was named anywhere
    until now, so the only way to find them was to read this function.

    ``p`` values are converted to −log10 here rather than accepted
    pre-transformed, so the threshold line and the points cannot disagree.

    ``max_labels`` (default 8) caps how many points are named. A volcano with
    every point labelled is unreadable, and the ones worth naming are the
    extremes — which is the order they are taken in.
    """
    series = series_of(spec)
    entry = series[0]
    effect = numbers(entry.get("x") or entry.get("effect"), "series[0].x")
    raw_p = numbers(entry.get("values") or entry.get("p"), "series[0].values", expect=effect.size)
    if np.any(raw_p <= 0) or np.any(raw_p > 1):
        bad = [float(v) for v in raw_p if v <= 0 or v > 1][:3]
        raise SpecError(
            f"'values' holds p-values and {bad} fall outside (0, 1]. Pass the "
            "p-values themselves — the figure takes −log10 of them, so a "
            "pre-transformed column would be logged twice."
        )
    # Through the shared gate, not `float(spec.get(...))`. Both of these are
    # THRESHOLDS, and every comparison against a NaN one is False: with
    # `alpha: NaN` no point is significant, nothing is highlighted, the
    # threshold line is drawn at NaN so it is not drawn at all, and the
    # annotation reads "p ≤ nan" — a volcano plot whose whole subject is which
    # points are significant, showing none, at exit 0. A string got as far as
    # `could not convert string to float` with nothing about the spec key.
    alpha = number_option(spec, "alpha", 0.05, minimum=0.0)
    if not 0.0 < alpha <= 1.0:
        raise SpecError(
            f"'alpha' is {alpha:g}. It is a p-value threshold, so it lies above 0 and at "
            "most 1 — the line is drawn at −log10 of it, which has nowhere to go at 0."
        )
    # A negative floor marks EVERYTHING significant, since `abs(effect)` clears
    # it always; that is the one value which changes the figure's claim without
    # changing anything a reader could notice.
    min_effect = number_option(spec, "min_effect", 0.0, minimum=0.0)
    significance = -np.log10(raw_p)

    strong = (np.abs(effect) >= min_effect) & (raw_p <= alpha)
    ax.scatter(
        effect[~strong], significance[~strong], s=26, color="#949494", alpha=0.7, edgecolors="none"
    )
    threshold = f"p ≤ {alpha:g}" + (f" and |effect| ≥ {min_effect:g}" if min_effect else "")
    marker = ax.scatter(
        effect[strong],
        significance[strong],
        s=34,
        color=PALETTE[0],
        edgecolors="none",
        label=f"{threshold} ({int(strong.sum())})",
    )
    ax.axhline(-np.log10(alpha), color="#333333", linewidth=1.0, linestyle="--")
    if min_effect:
        for edge in (-min_effect, min_effect):
            ax.axvline(edge, color="#333333", linewidth=1.0, linestyle="--")

    names = entry.get("labels")
    if names:
        if not isinstance(names, list) or len(names) != effect.size:
            raise SpecError(
                f"series[0].labels has {len(names) if isinstance(names, list) else '?'} "
                f"entries but there are {effect.size} points"
            )
        # Only points that cleared both thresholds, most significant first, and
        # only where the name has somewhere to sit. Labelling all 20 survivors
        # of a 60-point screen printed them over each other, which loses more
        # names than showing six does. Candidates are spaced on the normalised
        # axes so the choice is deterministic and needs no rendered geometry.
        limit = int(number_option(spec, "max_labels", 8, minimum=0, integer=True))
        span_x = float(effect.max() - effect.min()) or 1.0
        span_y = float(significance.max() - significance.min()) or 1.0
        candidates = np.where(strong)[0]
        placed: list[int] = []
        for i in candidates[np.argsort(-significance[candidates])]:
            if len(placed) >= limit:
                break
            near = any(
                abs(effect[i] - effect[j]) / span_x < 0.16
                and abs(significance[i] - significance[j]) / span_y < 0.09
                for j in placed
            )
            if not near:
                placed.append(int(i))
        for i in placed:
            place_point_label(ax, literal(names[i]), (effect[i], significance[i]), fontsize=8)
        if candidates.size > len(placed):
            # Stated, not silent: a reader must not infer that the labelled
            # points are the only significant ones. It goes in the LEGEND
            # rather than in a corner of the axes — a free-floating note lands
            # in the top right, which on a volcano is exactly where the
            # strongest points and their own labels already are.
            marker.set_label(f"{threshold} ({int(strong.sum())}, {len(placed)} labelled)")
    ax.set_xlabel(literal(spec.get("xlabel") or "Effect size"))
    ax.set_ylabel(literal(spec.get("ylabel") or "−log₁₀ p"))
    if strong.any():
        place_legend(ax, loc="lower right")


def render_joint(ax, spec: dict) -> None:
    """A scatter with the marginal distribution of each variable beside it.

    For when the relationship AND the two distributions are all part of the
    claim — a correlation that turns out to be driven by a bimodal x, a
    ceiling in y that the scatter alone hides in a band of points. Choose
    over ``scatter`` whenever "and how are they each distributed?" is the
    obvious follow-up question, which for a headline correlation it always
    is. Past a few thousand points prefer ``hexbin``: the marginals stay
    honest but the middle becomes a blob.

    The marginals are drawn in axes attached to this one, so they share its
    limits exactly — a marginal on its own scale is worse than none.
    """
    series = series_of(spec)
    entry = series[0]
    x = numbers(entry.get("x"), "series[0].x")
    y = numbers(entry.get("values") or entry.get("y"), "series[0].values", expect=x.size)
    bins = int(spec.get("bins", 30))
    if bins < 2:
        raise SpecError(f"'bins' must be at least 2, got {bins}")

    colour = series_style(0)["color"]
    ax.scatter(x, y, s=22, alpha=0.65, color=colour, edgecolors="none")

    # Attached rather than free-floating: ``inset_axes`` with ``sharex``/
    # ``sharey`` keeps the marginal aligned with the scatter under whatever
    # limits constrained layout settles on.
    top = ax.inset_axes([0, 1.02, 1, 0.20], sharex=ax)
    right = ax.inset_axes([1.02, 0, 0.20, 1], sharey=ax)
    top.hist(x, bins=bins, color=colour, alpha=0.8)
    right.hist(y, bins=bins, orientation="horizontal", color=colour, alpha=0.8)
    for margin in (top, right):
        margin.set_axis_off()
    if entry.get("label"):
        ax.scatter([], [], color=colour, label=literal(entry["label"]))
        place_legend(ax, loc="best")


def render_bump(ax, spec: dict) -> None:
    """Rank over time, one line per item — who overtook whom, and when.

    For a leaderboard's evolution across releases, or any ordering that
    changes: the crossing points ARE the finding. Choose over ``line`` on the
    underlying score, where a reordering among close values is invisible, and
    over ``slope``, which shows the same reordering for exactly two time
    points and cannot show the path between more.

    Ranks are computed here from the values, so the lines cannot disagree
    with the numbers. Rank 1 is the best and sits at the top.
    """
    series = series_of(spec)
    periods = spec.get("periods") or spec.get("categories")
    length = max(len(entry.get("values") or []) for entry in series)
    if length < 2:
        raise SpecError("a bump chart needs at least two time points per item")
    values = np.vstack(
        [
            numbers(entry.get("values"), f"series[{i}].values", expect=length)
            for i, entry in enumerate(series)
        ]
    )
    higher_is_better = flag(spec, "higher_is_better", True)
    ordered = -values if higher_is_better else values
    # A bump chart has one row per rank, so two items on the same score have
    # nowhere to both go. ``argsort`` is stable and would put whichever appears
    # first in the spec on the better row: two models level at 80.0 were drawn
    # as a permanent one-rank gap, and moving them past each other in the spec
    # — same numbers — produced a crossing that never happened. The crossings
    # are the whole finding of this chart type, so a fabricated one is fatal.
    names = [str(entry.get("label") or i + 1) for i, entry in enumerate(series)]
    for column in range(length):
        seen: dict[float, int] = {}
        for row, value in enumerate(values[:, column]):
            first = seen.setdefault(float(value), row)
            if first != row:
                where = periods[column] if periods and column < len(periods) else column + 1
                raise SpecError(
                    f"{names[first]!r} and {names[row]!r} both score {value:g} at {where!r}. "
                    "A bump chart "
                    "draws one item per rank row, so a tie can only be broken by the order "
                    "the series happen to appear in — and reordering them would show a "
                    "crossing that is not in the data. Separate the tied values, or use "
                    "'line' (or 'slope' for two periods), which draw the scores themselves "
                    "and can show a tie as a tie."
                )
    # ``argsort`` twice turns a column of values into its ranks, 1 = best.
    ranks = np.argsort(np.argsort(ordered, axis=0), axis=0) + 1

    x = np.arange(length)
    for i, entry in enumerate(series):
        style = series_style(i)
        ax.plot(
            x,
            ranks[i],
            marker="o",
            markersize=6,
            label=literal(entry["label"]) if entry.get("label") else None,
            **style,
        )
    ax.set_yticks(np.arange(1, len(series) + 1))
    ax.set_ylim(len(series) + 0.5, 0.5)  # rank 1 at the top
    ax.set_ylabel(literal(spec.get("ylabel") or "Rank"))
    labels = labels_for({"categories": periods}, length)
    ax.set_xticks(x, labels=labels)
    ax.grid(axis="y", visible=True)
    ax.grid(axis="x", visible=False)
    draw_legend(ax, spec, series, headroom=False, outside=True)


#: The most variables a pair plot can carry at the default 7-inch width.
#: Measured, not chosen: at seven the cells are 0.85 in across, which is
#: narrower than the two tick labels each one needs, and the axis names on the
#: outer edge start overlapping their neighbours. Six renders cleanly.
MAX_SPLOM_VARIABLES = 6


def render_splom(ax, spec: dict) -> None:
    """Every pair of variables as a scatter, distributions on the diagonal.

    The figure that answers what ``corr`` cannot. A correlation matrix gives
    one number per pair, and the same 0.81 is drawn by a straight line, by two
    clusters far apart, and by a round blob with one far outlier — Anscombe's
    point, and the reason a reviewer asks to see the scatter. Choose this when
    the RELATIONSHIPS are the claim; choose ``corr`` when there are more
    variables than fit here and the ranking of correlations is the claim.

    Choose ``joint`` over this for a single pair: it spends the whole canvas
    on one relationship and gives both marginals room, where here each cell is
    a sixth of the width.

    Each series is one VARIABLE — a column of the same table — so every one
    must be the same length and every one must be named, since the names label
    the rows and the columns. The diagonal is that variable's histogram, and
    every cell in a row shares its y-scale with the rest of the row (and its
    column's x-scale), because a grid of independently scaled cells invites
    exactly the cross-cell comparison it cannot support.

    Keys: ``series`` (one per variable, each ``label`` + ``values``),
    ``bins`` (diagonal histogram bins, default 12), ``point_size``
    (default 12).
    """
    # The naming check runs BEFORE ``series_of``, which is the only reason it
    # is not simply left to the shared one: that message explains itself in
    # terms of a legend, and this type draws none. A right complaint with the
    # wrong reason sends the agent to look at the wrong thing.
    raw = spec.get("series") or []
    unnamed = [
        i
        for i, entry in enumerate(raw)
        if isinstance(entry, dict) and not str(entry.get("label", "")).strip()
    ]
    if unnamed and len(raw) >= 2:
        raise SpecError(
            f"series {unnamed} have no 'label'. Every variable's name labels a "
            "row AND a column here, so an unnamed one leaves a strip of the "
            "grid that cannot be read at all."
        )
    series = series_of(spec)
    if len(series) < 2:
        raise SpecError(
            "a pair plot needs at least two variables — with one there are no "
            "pairs, and the figure is a 'hist'"
        )
    if len(series) > MAX_SPLOM_VARIABLES:
        raise SpecError(
            f"{len(series)} variables is past what a pair plot can show "
            f"(max {MAX_SPLOM_VARIABLES}): each cell would be narrower than "
            "its own tick labels. Use 'corr' for the correlations across all "
            "of them, and a pair plot for the handful worth looking at."
        )

    names = [literal(entry["label"]) for entry in series]
    first = numbers(series[0].get("values"), "series[0].values")
    columns = [first] + [
        numbers(entry.get("values"), f"series[{i}].values", expect=first.size)
        for i, entry in enumerate(series[1:], start=1)
    ]
    bins = int(number_option(spec, "bins", 12, minimum=2, integer=True))
    size = number_option(spec, "point_size", 12.0, minimum=0.1)

    n = len(columns)
    ax.set_axis_off()
    step = 1.0 / n
    # Row 0 at the TOP, which is how a matrix is read.
    cells = [
        [ax.inset_axes([c * step, 1.0 - (r + 1) * step, step, step]) for c in range(n)]
        for r in range(n)
    ]

    for row in range(n):
        for col in range(n):
            cell = cells[row][col]
            if row == col:
                cell.hist(columns[col], bins=bins, color=PALETTE[0], alpha=0.85)
            else:
                cell.scatter(
                    columns[col],
                    columns[row],
                    s=size,
                    alpha=0.6,
                    color=PALETTE[1],
                    edgecolors="none",
                )
            cell.tick_params(labelsize=6.5)

    # X is shared down each column, including the diagonal: a histogram of
    # variable c has variable c on its x-axis like every scatter above it.
    #
    # Y is shared along each row EXCEPT the diagonal, which is the mistake the
    # first version of this made. A diagonal cell's y is a COUNT and its row's
    # y is the variable, so sharing them stretched every scatter in the row to
    # the histogram's tallest bar and left the points in a strip at the top.
    for col in range(n):
        for row in range(1, n):
            cells[row][col].sharex(cells[0][col])
    for row in range(n):
        others = [c for c in range(n) if c != row]
        for col in others[1:]:
            cells[row][col].sharey(cells[row][others[0]])

    for row in range(n):
        for col in range(n):
            cell = cells[row][col]
            # ``tick_params`` rather than ``set_xticklabels([])``: blanking
            # the labels of an axes that SHARES an axis blanks them for the
            # whole group, so the first version hid every number on the
            # figure including the ones on the outer edge it meant to keep.
            #
            # Numbers go on the leftmost cell of the row that actually shows
            # the row's variable. On row 0 that is column 1, because column 0
            # is the diagonal — seaborn leaves the top row's scale unreadable
            # for exactly this reason, and one cell to the right is legible
            # and unambiguous while the row's name stays on the far left.
            leftmost = next(c for c in range(n) if c != row)
            cell.tick_params(labelbottom=(row == n - 1), labelleft=(col == leftmost and row != col))
            if row == col:
                # No count axis at all: those tick values belong to a
                # different quantity from everything else in the row, and a
                # reader scanning across would take them for the variable.
                cell.set_yticks([])
            if row == n - 1:
                cell.set_xlabel(names[col], fontsize=8)
            if col == 0:
                cell.set_ylabel(names[row], fontsize=8)


def render_fan(ax, spec: dict) -> None:
    """A median with nested quantile bands around it.

    For an uncertainty that is not symmetric. ``line`` takes one ± band, which
    is the right figure when the spread is a standard deviation of something
    unbounded — and the wrong one for a bounded or skewed quantity, where it
    implies values the measure cannot take: a ±2 std band on an accuracy of
    97% reaches past 100, and a reader has no way to know the figure invented
    that. Quantiles are read off the sample, so every edge of every band is a
    value that was actually observed.

    Choose ``line`` when one symmetric band says everything; choose this when
    the SHAPE of the spread is part of the claim, or when the intervals are
    nested (50/80/95) and their relative width is the point.

    The bands are checked for nesting. A wider level whose interval does not
    contain the narrower one cannot come from one sample, so it is refused
    rather than drawn — overlapping fills would still look like a fan, and
    nothing downstream reads the numbers back.

    Keys: ``series`` with ``x``, ``values`` (the median) and ``bands`` — a
    list of ``{"level": 80, "lower": [...], "upper": [...]}`` — plus the usual
    ``label``. ``logy`` puts the value axis on a log scale.
    """
    series = series_of(spec)
    if len(series) != 1:
        raise SpecError(
            f"a fan chart draws ONE quantity's spread, got {len(series)} series. "
            "Nested bands from two of them overlap into a single wash that "
            "belongs to neither — use a 'panel' of two fans, or 'line' with a "
            "band each."
        )
    entry = series[0]
    x = numbers(entry.get("x"), "series[0].x")
    median = numbers(entry.get("values"), "series[0].values", expect=x.size)

    raw = entry.get("bands")
    if not isinstance(raw, list) or not raw:
        raise SpecError(
            'series[0].bands must be a non-empty list of {"level": 80, '
            '"lower": [...], "upper": [...]} — without one this is a \'line\'.'
        )
    bands = []
    for i, band in enumerate(raw):
        if not isinstance(band, dict):
            raise SpecError(f"series[0].bands[{i}] must be an object, got {type_name(band)}")
        level = number_option(band, "level", 0.0, minimum=0.0)
        if not 0 < level < 100:
            raise SpecError(
                f"series[0].bands[{i}].level is {level:g}; a quantile band covers "
                "between 0 and 100 per cent of the sample."
            )
        lower = numbers(band.get("lower"), f"series[0].bands[{i}].lower", expect=x.size)
        upper = numbers(band.get("upper"), f"series[0].bands[{i}].upper", expect=x.size)
        crossed = int(np.sum(lower > upper))
        if crossed:
            raise SpecError(
                f"series[0].bands[{i}] has lower above upper at {crossed} of "
                f"{x.size} points, so the band is inside out."
            )
        outside = int(np.sum((median < lower) | (median > upper)))
        if outside:
            raise SpecError(
                f"series[0].bands[{i}] does not contain the median at {outside} of "
                f"{x.size} points. Every quantile interval straddles the median by "
                "construction, so one that does not is not from this sample."
            )
        bands.append((level, lower, upper))

    levels = [level for level, _, _ in bands]
    if len(set(levels)) != len(levels):
        raise SpecError(f"series[0].bands repeats a level: {sorted(levels)}")
    bands.sort(key=lambda b: b[0])
    for (inner_level, inner_lo, inner_hi), (outer_level, outer_lo, outer_hi) in itertools.pairwise(
        bands
    ):
        breaks = int(np.sum((outer_lo > inner_lo) | (outer_hi < inner_hi)))
        if breaks:
            raise SpecError(
                f"the {outer_level:g}% band is narrower than the {inner_level:g}% band at "
                f"{breaks} of {x.size} points. A wider quantile interval contains the "
                "narrower one at every point, so these did not come from one sample."
            )

    colour = series_style(0)["color"]
    # Widest first, so the narrower bands land on top and read darker — the
    # ramp is what tells them apart, since a fan carries no legend key per
    # level that a reader would look up.
    for level, lower, upper in reversed(bands):
        ax.fill_between(
            x,
            lower,
            upper,
            color=colour,
            alpha=0.16 + 0.5 * (1.0 - level / 100.0),
            linewidth=0,
            label=f"{level:g}%",
        )
    ax.plot(x, median, color=colour, linewidth=1.8, label=literal(entry.get("label") or "Median"))
    if flag(spec, "logy"):
        require_positive(median, "series[0].values", "y")
        ax.set_yscale("log")
    ax.grid(axis="y", visible=True)
    place_legend(ax, loc="best")


#: The most rows of text a sequence heat figure can carry. Measured at the
#: default 7-inch width: past twelve the cells are under 9 pt of height and
#: the token text inside them stops clearing the legibility gate.
MAX_SEQHEAT_ROWS = 12

#: Characters per row when the spec does not say. At the default width this
#: puts each character near 7 pt, which is the floor for text a reader is
#: expected to actually read rather than glance at.
DEFAULT_SEQHEAT_WRAP = 64


def seqheat_rows(spec: dict) -> int:
    """How many rows of text ``seqheat`` will wrap to.

    Shared with ``_default_aspect`` rather than re-derived there: the canvas
    height is decided BEFORE the renderer runs, and a canvas sized from an
    estimate of the row count is a canvas that is wrong by a whole row of
    text whenever the estimate rounds the other way.
    """
    tokens = spec.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        return 1
    try:
        wrap = int(spec.get("wrap") or DEFAULT_SEQHEAT_WRAP)
    except (TypeError, ValueError):
        wrap = DEFAULT_SEQHEAT_WRAP
    wrap = max(wrap, 8)
    rows, used = 1, 0
    for token in tokens:
        width = max(len(token) if isinstance(token, str) else 1, 1)
        if used and used + width > wrap:
            rows += 1
            used = 0
        used += width
    return rows


def render_seqheat(ax, spec: dict) -> None:
    """A per-token quantity drawn on the tokens themselves.

    The figure for anything measured PER TOKEN — attention mass, per-token
    loss, a saliency score, the log-prob the model gave each piece. Choose
    over ``heatmap``, which would put token indices on an axis and leave the
    reader reconstructing the sentence from a legend; choose over a ``bar``
    per token, which keeps the numbers precise and loses the reading order
    the moment the sequence is longer than one screen. The point of this
    figure is that the value and the word it belongs to are in the same
    place.

    Tokens are laid out in monospace and each cell is as wide as its token is
    long, so a cell's width is exactly its token's width and the text cannot
    overflow the colour it belongs to. That is also why the wrap is measured
    in CHARACTERS rather than tokens: rows of equal token count are rows of
    wildly unequal length.

    ``diverging`` is for a signed quantity — a logit difference, an
    attribution that can help or hurt — where zero is the meaningful middle.
    On data that never crosses zero it is refused, the same as everywhere
    else in the catalogue.

    Keys: ``tokens`` (the strings, in order), ``values`` (one number per
    token), ``wrap`` (characters per row, default 64), ``cbar_label``,
    ``cmap``, ``diverging``, ``vmin`` / ``vmax``.
    """
    import matplotlib.patches as mpatches
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import Normalize

    tokens = spec.get("tokens")
    if not isinstance(tokens, list) or not tokens:
        raise SpecError(
            "'tokens' must be a non-empty list of strings — the sequence this "
            'figure draws its values ON. Example: ["The", " capital", " of"].'
        )
    for i, token in enumerate(tokens):
        if not isinstance(token, str):
            raise SpecError(f"tokens[{i}] is {token!r}; every token must be a string")
    values = numbers(spec.get("values"), "'values'", expect=len(tokens))

    wrap = int(number_option(spec, "wrap", DEFAULT_SEQHEAT_WRAP, minimum=8, integer=True))
    widest = max(max(len(token), 1) for token in tokens)
    if widest > wrap:
        raise SpecError(
            f"a token is {widest} characters and 'wrap' is {wrap}, so it cannot fit "
            "on a row at all. Raise 'wrap', or split the token."
        )

    # Greedy wrap on CHARACTER width. A token is never broken across rows:
    # half a token carrying half a colour is not a reading of anything.
    rows: list[list[int]] = [[]]
    used = 0
    for i, token in enumerate(tokens):
        width = max(len(token), 1)
        if used and used + width > wrap:
            rows.append([])
            used = 0
        rows[-1].append(i)
        used += width
    assert len(rows) == seqheat_rows(spec), "the canvas was sized for a different wrap"
    if len(rows) > MAX_SEQHEAT_ROWS:
        raise SpecError(
            f"{len(tokens)} tokens wrap to {len(rows)} rows (max {MAX_SEQHEAT_ROWS}); "
            "the text would be drawn below the size a reader can follow. Show the "
            "passage that carries the finding rather than the whole sequence."
        )

    diverging = flag(spec, "diverging")
    if diverging and (values.min() >= 0 or values.max() <= 0):
        raise SpecError(
            f"'diverging' centres the colour map on zero, but the values run "
            f"{values.min():g}..{values.max():g} and never cross it — half the "
            "range would go unused and every token would land in one arm."
        )
    span = max(abs(values.min()), abs(values.max())) or 1.0
    low = number_option(spec, "vmin", -span if diverging else float(values.min()))
    high = number_option(spec, "vmax", span if diverging else float(values.max()))
    if low >= high:
        if "vmin" in spec or "vmax" in spec:
            raise SpecError(
                f"'vmin' is {low:g} and 'vmax' is {high:g}; the low must be below the high"
            )
        # Derived from data that is entirely one value — a single token, or a
        # sequence where every score came out the same. That is a real figure
        # (every cell one colour, and the colourbar says which), so widen the
        # range rather than refusing something the spec did nothing wrong to
        # produce.
        pad = abs(low) * 0.5 or 0.5
        low, high = low - pad, high + pad
    norm = Normalize(vmin=low, vmax=high)
    cmap = colour_map(spec, "RdBu_r" if diverging else "cividis")
    mappable = ScalarMappable(norm=norm, cmap=cmap)

    for row_index, row in enumerate(rows):
        x = 0.0
        top = -row_index
        for i in row:
            width = max(len(tokens[i]), 1)
            colour = mappable.to_rgba(values[i])
            ax.add_patch(
                mpatches.Rectangle((x, top - 0.82), width, 0.82, facecolor=colour, edgecolor="none")
            )
            ink = ink_on(colour)
            ax.text(
                x + width / 2.0,
                top - 0.41,
                literal(tokens[i]),
                ha="center",
                va="center",
                fontsize=7.5,
                family="monospace",
                color=ink,
                path_effects=cell_halo(ink),
            )
            x += width

    ax.set_xlim(0, wrap)
    ax.set_ylim(-len(rows), 0.18)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(visible=False)
    for spine in ax.spines.values():
        spine.set_visible(False)
    # Horizontal, under the text. This figure is wide and short by
    # construction — its height is a few lines of type — and a vertical bar
    # puts its label along that short edge: at two rows the canvas is 1.54 in
    # tall and "Attribution to ' Rome'" needs about 2.2, so the legibility
    # gate refused the figure outright. Along the bottom the label has the
    # full width, which is the one dimension this type always has.
    cbar = ax.figure.colorbar(
        mappable, ax=ax, orientation="horizontal", fraction=0.16, pad=0.06, aspect=45
    )
    cbar.outline.set_visible(False)
    if spec.get("cbar_label"):
        cbar.set_label(literal(spec["cbar_label"]))


MORE_RENDERERS = {
    "beeswarm": render_beeswarm,
    "volcano": render_volcano,
    "joint": render_joint,
    "bump": render_bump,
    "splom": render_splom,
    "fan": render_fan,
    "seqheat": render_seqheat,
}
