"""Comparison and ranking figures — the family that answers "which one is better?".

The core family (``chart_renderers``) plots quantities. This one plots the
*relationship between* quantities, which is a different job: the reader's
question is not "how big is each" but which item won, by how much, and
whether the ordering moved. Grouped bars answer that badly past three or
four categories — the eye has to compare lengths that do not share a
baseline — so every renderer here draws the comparison itself: the gap
(``dumbbell``), the re-ranking (``slope``), the running total
(``waterfall``), the sign (``diverging``), the whole profile (``radar``,
``parallel``).

Same contract as every other family: ``render_x(ax, spec) -> None``, never
create or save a figure, never touch ``plt`` global state, and every number
from the spec goes through ``numbers()`` so the picture cannot disagree with
its data. ``waterfall`` takes that one step further and checks the
arithmetic: a waterfall whose final bar does not equal its start plus its
steps is a wrong figure that still looks right, so it is refused.

Wire the table at the bottom into the CLI with
``RENDERERS.update(COMPARE_RENDERERS)``.
"""

from __future__ import annotations

import math
import textwrap

import matplotlib
import numpy as np
from chart_common import (
    SpecError,
    error_bars,
    flag,
    legend_place,
    number_format,
    number_option,
    type_name,
)
from chart_common import (
    draw_legend as _legend,
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
    place_legend,
    series_style,
)

# One vocabulary of colour for DIRECTION, shared by every chart in this file.
# A rise is the same green in a slope chart, a waterfall step and a diverging
# bar, so a reader who learns it on one figure reads all three. Red/green is
# the obvious pairing and the wrong one — deuteranopia collapses it to a
# single hue — so a fall is amber, which also separates from the green under
# greyscale print (Rec. 709 luminance 0.59 against 0.48).
_RISE = PALETTE[2]  # green: went up
_FALL = PALETTE[1]  # amber: went down
_FLAT = "#9A9A9A"  # grey: did not move
_TOTAL = PALETTE[0]  # blue: an absolute total, not a step
_RULE = "#8C8C8C"  # connectors, brackets, the line joining a dumbbell

# Average advance width of DejaVu Sans over mixed-case text, as a fraction of
# the point size. Used to reserve room for labels that live OUTSIDE the data
# area (slope end-labels, radar spoke names) before anything is drawn —
# measuring properly would need a rendered canvas, which a renderer must not
# force.
_EM_RATIO = 0.55


def _signed_colour(delta: float) -> str:
    """Rise / fall / flat, from the sign of a change."""
    if delta > 0:
        return _RISE
    if delta < 0:
        return _FALL
    return _FLAT


def _only_series(spec: dict, kind: str, instead: str) -> dict:
    """The single series these one-row-per-category charts take.

    Raising with a pointer to the chart that DOES take two beats silently
    drawing the first series and dropping the second, which is the same
    class of quiet omission as truncating a category list.
    """
    series = _series(spec)
    if len(series) != 1:
        raise SpecError(
            f"'series' has {len(series)} entries but a {kind} draws exactly one value "
            f"per category. For two values per category use {instead}."
        )
    return series[0]


def _two_series(spec: dict, kind: str, instead: str) -> tuple[dict, dict]:
    """The before/after pair these two-column charts take."""
    series = _series(spec)
    if len(series) != 2:
        raise SpecError(
            f"'series' has {len(series)} entries but a {kind} compares exactly two — "
            f"series[0] is the first value and series[1] the second. {instead}"
        )
    return series[0], series[1]


def _num(value: float, fmt: str) -> str:
    """A formatted number carrying a real minus sign, not a hyphen.

    ``format(-8.4, "+.1f")`` produces U+002D, while the house style sets
    ``axes.unicode_minus`` so every TICK on the same figure uses U+2212. Left
    alone, a waterfall printed "−5" on its axis and "-5.7" on the bar right
    next to it: two different glyph widths for the same sign, which a reader
    registers as a rendering fault even without naming it.
    """
    text = format(float(value), fmt)
    return "−" + text[1:] if text.startswith("-") else text


def _sort_order(spec: dict, values: np.ndarray, *, default: str) -> np.ndarray:
    """Row order for a ranked chart. Stable, so ties keep the author's order."""
    how = spec.get("sort", default)
    if how in (None, False, "none"):
        return np.arange(values.size)
    if how is True or how == "desc":
        return np.argsort(-values, kind="stable")
    if how == "asc":
        return np.argsort(values, kind="stable")
    raise SpecError(f'\'sort\' must be "desc", "asc" or "none", got {how!r}')


def _nice_ceiling(value: float) -> float:
    """Round an auto-chosen upper bound up to a number a reader can hold.

    Scaling a radar to ``max × 1.05`` is correct and unreadable: it put the
    rings at 22.05 / 44.1 / 66.15 / 88.2. Rounding UP to a 1/2/2.5/5 × 10ⁿ
    step keeps every point inside the outer ring — nothing is cropped, which
    is the part that would matter — while giving round ring labels. An
    explicit ``rlim`` is never touched.
    """
    if value <= 0:
        return 1.0
    scale = 10.0 ** math.floor(math.log10(value))
    for step in (1.0, 2.0, 2.5, 5.0):
        if value <= step * scale * (1.0 + 1e-12):
            return step * scale
    return 10.0 * scale


def _text_width_in(chars: int, points: float) -> float:
    """Rough width in inches of ``chars`` characters set at ``points``."""
    return chars * points * _EM_RATIO / 72.0


def _axes_size_in(ax) -> tuple[float, float]:
    """Pre-draw estimate of THIS axes' box in inches, width and height.

    Sizing a label reserve off the FIGURE is right exactly once — when the
    figure holds one axes. Inside a ``panel`` grid the same renderer gets a
    third of the width, and a reserve computed from the whole figure is three
    times too small: the slope chart's end-labels went straight through the
    y-axis ticks of the panel beside it.

    ``get_position()`` is the subplot's share of the figure BEFORE
    constrained layout runs, so it reads 0.775 for a lone axes and 0.23 for a
    3-column cell — the distinction that matters. Layout then reclaims the
    margins and hands back roughly 15% more, hence the correction; it stays
    deliberately on the low side, because over-reserving costs whitespace
    while under-reserving costs clipped text.
    """
    fig_w, fig_h = ax.figure.get_size_inches()
    box = ax.get_position()
    return max(1.0, box.width * fig_w * 1.15), max(0.8, box.height * fig_h * 1.15)


def _outside_pad(
    longest_chars: int, points: float, axes_in: float, inner: float, key: str
) -> float:
    """Extra data-range to reserve on BOTH sides for labels drawn outside it.

    The circular bit: the pad is measured in data units, but how many data
    units an inch is worth depends on the pad. Solving the fixed point
    (``pad = width_in / axes_in * (inner + 2 * pad)``) is exact, where
    guessing a constant was not — a 0.3-unit guess clipped 20-character
    method names off the left edge of a slope chart at 7 inches wide.

    Past a ratio of 0.3 the labels would take more of the figure than the
    data, so the chart is refused rather than shipped as two columns of text
    with a thin strip of graphics between them.
    """
    ratio = (_text_width_in(longest_chars, points) + 0.10) / axes_in
    if ratio > 0.3:
        raise SpecError(
            f"the longest {key} is {longest_chars} characters, which needs more of "
            "the figure than the data would get. Shorten the names (explain them in "
            "the caption), or widen the figure with a bigger 'width_in'."
        )
    return inner * ratio / (1.0 - 2.0 * ratio)


def _legend_below(ax, spec: dict, series: list[dict], *, clear_in: float) -> None:
    """Legend under the axes, for the charts whose data leaves no free corner.

    ``draw_legend`` leans on ``loc="best"``, which needs somewhere free to
    put the box — and these two have nowhere. A parallel-coordinates polyline
    crosses the full width AND the full height by construction, and a radar
    fills the middle and rings its rim with spoke names. "Best" duly dropped
    a six-entry legend straight on top of six lines, and covered the first
    spoke's name on the radar.

    BELOW, not above: a legend anchored above the axes lands in the same band
    as ``ax.set_title``, which the CLI applies after the renderer returns, and
    the two overprint — the title struck through the legend's bottom row.
    Below, constrained layout reserves real space and nothing can reach it.
    ``clear_in`` is how many inches of tick label it has to clear first.
    """
    if len(series) < 2 or not any(s.get("label") for s in series):
        return
    # Wide and short. Below the axes the constraint is vertical space, so a
    # three-entry legend belongs on one row — stacking it into one column cost
    # more figure height than the legend was worth.
    ncol = len(series) if len(series) <= 4 else min(4, (len(series) + 1) // 2)
    requested = legend_place(spec)
    if requested:
        place_legend(ax, loc=requested, ncols=ncol)
        return
    axes_h_in = _axes_size_in(ax)[1]
    place_legend(
        ax, loc="upper center", bbox_to_anchor=(0.5, -(0.04 + clear_in / axes_h_in)), ncols=ncol
    )


def _spread(values: np.ndarray, gap: float, lo: float, hi: float) -> np.ndarray:
    """Nudge label positions apart, keeping their order, inside ``[lo, hi]``.

    Two items a tenth of a point apart put their end-labels on top of each
    other: the text overprints and neither number is readable, while the
    figure still looks fine in a thumbnail. Pushing them apart moves the TEXT
    only — the lines and markers stay on the real values, so nothing about
    the data is restated wrongly.

    When even an even spread cannot honour the gap (more rows than the axis
    has line-heights) the labels are distributed evenly instead of being
    piled at the top, which is the least-wrong arrangement available.
    """
    n = values.size
    if n < 2:
        return values.astype(float)
    order = np.argsort(values, kind="stable")
    if gap * (n - 1) > (hi - lo):
        out = np.empty(n, dtype=float)
        out[order] = np.linspace(lo, hi, n)
        return out
    out = values.astype(float).copy()
    for k in range(1, n):  # push up from the bottom
        below, here = order[k - 1], order[k]
        out[here] = max(out[here], out[below] + gap)
    if out[order[-1]] > hi:  # the stack overshot the top: settle it back down
        out[order[-1]] = hi
        for k in range(n - 2, -1, -1):
            here, above = order[k], order[k + 1]
            out[here] = min(out[here], out[above] - gap)
    return out


def render_slope(ax, spec: dict) -> None:
    """Before/after slope chart — one line per item, showing which items changed rank.

    Two columns, an item's value on each, joined by a line that is green if
    it rose and amber-dashed if it fell. Both ends carry the item's name and
    its number, so the figure reads without a legend.

    Choose it over paired bars whenever the ORDERING is the finding: crossing
    lines make a re-ranking visible at a glance, while eight pairs of bars
    force the reader to track two lengths per item and compute the change
    themselves. Choose paired bars instead when the absolute magnitudes
    matter more than the movement, ``dumbbell`` when the gap matters more
    than the direction, and ``parallel`` when there are three or more stages
    rather than two.

    Spec: ``categories`` (item names), exactly two ``series`` whose ``label``
    becomes each column's heading and whose ``values`` are the before and
    after numbers. Optional ``fmt`` (default ``".1f"``) formats the printed
    values.
    """
    left, right = _two_series(
        spec,
        "slope chart",
        'For three or more columns use "type": "parallel", which gives every axis its own scale.',
    )
    before = _numbers(left.get("values"), "series[0].values")
    after = _numbers(right.get("values"), "series[1].values", expect=before.size)
    cats = _labels(spec, before.size)
    fmt = number_format(spec, "fmt", ".1f")

    label_pt = matplotlib.rcParams["font.size"] - 1
    left_text = [f"{c}  {_num(v, fmt)}" for c, v in zip(cats, before, strict=True)]
    right_text = [f"{_num(v, fmt)}  {c}" for c, v in zip(cats, after, strict=True)]

    lo = float(min(before.min(), after.min()))
    hi = float(max(before.max(), after.max()))
    # A flat chart (every item identical) has no range to pad; give it one so
    # the single row of markers does not land on the axis spine.
    inner = max(hi - lo, abs(hi) * 0.02, 1e-9)
    lo, hi = lo - 0.07 * inner, hi + 0.07 * inner
    ax.set_ylim(lo, hi)

    for b, a in zip(before, after, strict=True):
        rose = a >= b
        ax.plot(
            [0.0, 1.0],
            [b, a],
            color=_signed_colour(a - b),
            linewidth=1.7,
            linestyle="-" if rose else (0, (5, 2)),
            marker="o",
            markersize=4.5,
            zorder=3,
        )

    # Labels get their own y positions so near-equal items stay readable; the
    # markers stay on the true values.
    axes_w_in, axes_h_in = _axes_size_in(ax)
    gap = (label_pt * 1.35 / 72.0) / axes_h_in * (hi - lo)
    # Half a line of inset on the clamp: the labels are vertically CENTRED on
    # these positions, so spreading them right up to the limit hangs the top
    # and bottom ones half outside the axes.
    top, bottom = hi - gap / 2, lo + gap / 2
    ink = {"fontsize": label_pt, "color": "#1A1A1A", "va": "center"}
    for i, (yl, yr) in enumerate(
        zip(_spread(before, gap, bottom, top), _spread(after, gap, bottom, top), strict=True)
    ):
        ax.text(-0.025, yl, left_text[i], ha="right", **ink)
        ax.text(1.025, yr, right_text[i], ha="left", **ink)

    pad = _outside_pad(
        max(len(t) for t in left_text + right_text),
        label_pt,
        axes_w_in,
        1.0,
        "item label",
    )
    ax.set_xlim(-pad, 1.0 + pad)
    ax.axvline(0.0, color="#DDDDDD", linewidth=0.9, zorder=1)
    ax.axvline(1.0, color="#DDDDDD", linewidth=0.9, zorder=1)
    ax.set_xticks(
        [0.0, 1.0],
        labels=[literal(left.get("label") or "Before"), literal(right.get("label") or "After")],
    )
    ax.tick_params(axis="x", length=0)
    # No gridlines: they run straight through the end-labels, and the values
    # are printed next to every marker anyway.
    ax.grid(visible=False)


def render_dumbbell(ax, spec: dict) -> None:
    """Two markers per row joined by a line — for when the GAP is the story.

    One row per category, a dot for each of the two conditions, and a rule
    between them whose length IS the difference. Optionally the delta is
    printed at the end of each row.

    Choose it over paired bars when the reader's question is "how far apart
    are they?": bars encode the two values as lengths from a shared baseline
    and leave the difference to be estimated, whereas here the difference is
    drawn directly and the rows can be scanned for the longest one. Choose
    ``slope`` instead when the ordering changed and you want that visible,
    ``bar_sig`` when the point is whether the gap is significant, and
    ``lollipop`` when there is only one value per category.

    Spec: ``categories``, exactly two ``series`` (each ``label`` +
    ``values``). Optional ``annotate`` prints the second-minus-first delta,
    ``fmt`` (default ``"+.1f"``) formats it.
    """
    first, second = _two_series(
        spec,
        "dumbbell chart",
        'For one value per category use "type": "lollipop"; for three or more use '
        '"type": "parallel".',
    )
    a = _numbers(first.get("values"), "series[0].values")
    b = _numbers(second.get("values"), "series[1].values", expect=a.size)
    cats = _labels(spec, a.size)
    y = np.arange(a.size, dtype=float)

    for yi, va, vb in zip(y, a, b, strict=True):
        ax.plot([va, vb], [yi, yi], color=_RULE, linewidth=2.0, solid_capstyle="round", zorder=2)
    for i, (values, entry) in enumerate(((a, first), (b, second))):
        ax.scatter(
            values,
            y,
            s=58,
            color=PALETTE[i % len(PALETTE)],
            edgecolors="white",
            linewidths=0.8,
            zorder=3,
            label=literal(entry.get("label")) if entry.get("label") else None,
        )

    lo = float(min(a.min(), b.min()))
    hi = float(max(a.max(), b.max()))
    span = max(hi - lo, abs(hi) * 0.02, 1e-9)
    annotate = flag(spec, "annotate")
    if annotate:
        fmt = number_format(spec, "fmt", "+.1f")
        outer = np.maximum(a, b)
        for yi, edge, delta in zip(y, outer, b - a, strict=True):
            ax.text(
                edge + 0.02 * span,
                yi,
                _num(delta, fmt),
                ha="left",
                va="center",
                fontsize=matplotlib.rcParams["font.size"] - 2,
                color="#333333",
            )
    ax.set_xlim(lo - 0.07 * span, hi + (0.22 if annotate else 0.07) * span)
    ax.set_yticks(y, labels=cats)
    # Half a row of margin top and bottom: matplotlib's default scatter
    # margins put the first and last dots hard against the axes edge, where
    # the marker is clipped in half by the spine.
    ax.set_ylim(a.size - 0.5, -0.5)
    ax.grid(visible=True, axis="x")
    ax.grid(visible=False, axis="y")
    _legend(ax, spec, [first, second], headroom=False)


def render_lollipop(ax, spec: dict) -> None:
    """A stem and a dot per category — a bar chart that survives many categories.

    Same encoding as a bar (position along an axis) with almost none of the
    ink. Horizontal by default, which puts the category names on the y-axis
    where the full figure width is available.

    Choose it over ``bar``/``barh`` past roughly a dozen categories, where
    bars become a picket fence: the filled rectangles start to read as a
    texture rather than as values, and adjacent bars visually merge. The dot
    keeps the endpoint sharp however many rows there are. Choose ``bar``
    instead for three or four categories, where the extra ink helps, and
    ``dumbbell`` or ``bar`` when a category carries more than one value —
    this renderer deliberately takes exactly one.

    Spec: ``categories``, one ``series`` with ``values``. Optional
    ``orient`` (``"h"`` default, or ``"v"``), ``sort``
    (``"desc"``/``"asc"``/``"none"``, default ``"none"``), ``baseline``
    (stem origin, default 0), ``annotate``, ``fmt``.
    """
    entry = _only_series(spec, "lollipop", '"type": "dumbbell" (two markers joined by a rule)')
    values = _numbers(entry.get("values"), "series[0].values")
    cats = _labels(spec, values.size)
    orient = spec.get("orient", "h")
    if orient not in ("h", "v"):
        raise SpecError(f'\'orient\' must be "h" or "v", got {orient!r}')
    baseline = number_option(spec, "baseline", 0.0)
    order = _sort_order(spec, values, default="none")
    values = values[order]
    cats = [cats[k] for k in order]
    slots = np.arange(values.size, dtype=float)
    colour = PALETTE[0]

    lo = float(min(values.min(), baseline))
    hi = float(max(values.max(), baseline))
    span = max(hi - lo, abs(hi) * 0.02, 1e-9)
    annotate = flag(spec, "annotate")
    fmt = number_format(spec, "fmt", ".1f")
    # A value label goes on the far side of its own dot, so a stem pointing
    # DOWN needs its label below. Placing every label on the same side put a
    # negative one back across the baseline, printed on top of the zero rule.
    below = values < baseline
    pad_lo = 0.18 * span if (annotate and below.any()) else 0.07 * span
    pad_hi = 0.18 * span if (annotate and (~below).any()) else 0.07 * span
    offsets = np.where(below, -0.02 * span, 0.02 * span)
    label_pt = matplotlib.rcParams["font.size"] - 2

    if orient == "h":
        ax.hlines(slots, baseline, values, color=colour, linewidth=1.6, zorder=2)
        ax.scatter(values, slots, s=58, color=colour, zorder=3)
        ax.set_yticks(slots, labels=cats)
        ax.set_ylim(values.size - 0.5, -0.5)
        ax.set_xlim(lo - pad_lo, hi + pad_hi)
        ax.grid(visible=True, axis="x")
        ax.grid(visible=False, axis="y")
        if baseline != 0.0 or lo < 0.0:
            ax.axvline(baseline, color="#333333", linewidth=0.9, zorder=1)
        if annotate:
            for s, v, off, left in zip(slots, values, offsets, below, strict=True):
                ax.text(
                    v + off,
                    s,
                    _num(v, fmt),
                    ha="right" if left else "left",
                    va="center",
                    fontsize=label_pt,
                    color="#333333",
                )
    else:
        ax.vlines(slots, baseline, values, color=colour, linewidth=1.6, zorder=2)
        ax.scatter(slots, values, s=58, color=colour, zorder=3)
        ax.set_xticks(slots, labels=cats)
        ax.set_xlim(-0.6, values.size - 0.4)
        ax.set_ylim(lo - pad_lo, hi + pad_hi)
        if baseline != 0.0 or lo < 0.0:
            ax.axhline(baseline, color="#333333", linewidth=0.9, zorder=1)
        if annotate:
            for s, v, off, under in zip(slots, values, offsets, below, strict=True):
                ax.text(
                    s,
                    v + off,
                    _num(v, fmt),
                    ha="center",
                    va="top" if under else "bottom",
                    fontsize=label_pt,
                    color="#333333",
                )


def render_waterfall(ax, spec: dict) -> None:
    """Steps from a starting total to a final total — the standard ablation figure.

    Bars named in ``totals`` are absolute and drawn from zero; every other
    bar is a signed contribution floating on the running sum, green up and
    amber down, joined by a thin connector so the path is continuous.

    Choose it over a bar chart of deltas whenever the deltas ADD UP to
    something: it shows both each component's contribution and where the
    total ended, which two separate charts otherwise have to say. Choose
    ``diverging`` instead when the components are independent and do not
    compose into a total, and ``forest`` when the uncertainty on each
    contribution is part of the claim.

    The arithmetic is checked. A total that does not equal the running sum
    of the steps before it is refused, because a waterfall that does not
    balance is wrong in the way that survives review — every bar looks
    plausible and only the addition is broken.

    Spec: ``categories``, one ``series`` with ``values`` (absolute for total
    rows, signed deltas for step rows). Optional ``totals`` (indices of the
    absolute rows, default first and last), ``tolerance`` (default 0.1,
    absorbing rounding in the quoted steps), ``annotate`` (default true),
    ``fmt``.
    """
    entry = _only_series(spec, "waterfall", '"type": "bar" with several series')
    values = _numbers(entry.get("values"), "series[0].values")
    n = values.size
    if n < 2:
        raise SpecError(
            "series[0].values needs at least two entries — a waterfall is a starting "
            "level and at least one step"
        )
    cats = _labels(spec, n)
    fmt = number_format(spec, "fmt", ".1f")
    delta_fmt = fmt if fmt[:1] in "+- " else "+" + fmt
    tolerance = number_option(spec, "tolerance", 0.1)
    if tolerance < 0:
        raise SpecError(f"'tolerance' must not be negative, got {tolerance!r}")

    raw_totals = spec.get("totals", [0, n - 1])
    if not isinstance(raw_totals, list):
        raise SpecError(f"'totals' must be a list of row indices, got {type_name(raw_totals)}")
    totals = set()
    for i, index in enumerate(raw_totals):
        if isinstance(index, bool) or not isinstance(index, int):
            raise SpecError(f"totals[{i}] must be an integer row index, got {index!r}")
        if not 0 <= index < n:
            raise SpecError(f"totals[{i}] is {index} but there are only {n} rows (0..{n - 1})")
        totals.add(index)

    running = 0.0
    bottoms, heights, colours, levels = [], [], [], []
    for i, value in enumerate(values):
        if i in totals:
            if i > 0 and abs(value - running) > tolerance:
                raise SpecError(
                    f"series[0].values[{i}] is the total {value:g}, but the rows before "
                    f"it sum to {running:g} — off by {value - running:+.4g}. A waterfall "
                    "whose total does not equal its steps is exactly the figure that "
                    "passes review while being wrong. Fix the number, drop row "
                    f"{i} from 'totals' to draw it as a step, or raise 'tolerance' "
                    f"(currently {tolerance:g}) if the difference is only rounding."
                )
            bottom, top = min(0.0, float(value)), max(0.0, float(value))
            colours.append(_TOTAL)
            running = float(value)
        else:
            bottom = min(running, running + float(value))
            top = max(running, running + float(value))
            colours.append(_signed_colour(float(value)))
            running += float(value)
        bottoms.append(bottom)
        heights.append(top - bottom)
        levels.append(running)

    x = np.arange(n, dtype=float)
    width = 0.62
    ax.bar(x, heights, width, bottom=bottoms, color=colours, zorder=2)
    for i in range(n - 1):
        ax.plot(
            [x[i] + width / 2, x[i + 1] - width / 2],
            [levels[i], levels[i]],
            color=_RULE,
            linewidth=0.9,
            zorder=3,
        )

    # A bar's length only means anything measured from zero, so the axis has
    # to contain zero even when the interesting range is 50..70. Cropping it
    # would turn an 8-point drop into a bar half the height of the total.
    low = min(0.0, float(min(bottoms)))
    high = max(0.0, float(max(np.asarray(bottoms) + np.asarray(heights))))
    span = max(high - low, 1e-9)
    y_lo = low - (0.05 * span if low < 0 else 0.0)
    y_hi = high + 0.13 * span
    if low < 0:
        ax.axhline(0.0, color="#333333", linewidth=0.8, zorder=1)

    if flag(spec, "annotate", True):
        offset = 0.02 * span
        label_pt = matplotlib.rcParams["font.size"] - 2
        # A step label sits OUTSIDE its floating bar, so it can hang below the
        # lowest bar rather than above the tallest — a descent that lands near
        # zero pushed its label under the axis, where it was silently cut off
        # at the canvas edge. Reserve for whichever direction actually needs it.
        line = (label_pt * 1.6 / 72.0) / _axes_size_in(ax)[1] * span
        for i, value in enumerate(values):
            is_total = i in totals
            text = _num(value, fmt if is_total else delta_fmt)
            top = bottoms[i] + heights[i]
            above = is_total or value >= 0
            anchor = (top + offset) if above else (bottoms[i] - offset)
            y_lo = min(y_lo, anchor - line) if not above else y_lo
            y_hi = max(y_hi, anchor + line) if above else y_hi
            ax.text(
                x[i],
                anchor,
                text,
                ha="center",
                va="bottom" if above else "top",
                fontsize=label_pt,
                color="#1A1A1A",
            )
    ax.set_ylim(y_lo, y_hi)

    ax.set_xticks(x, labels=cats)
    ax.set_xlim(-0.6, n - 0.4)


def render_diverging(ax, spec: dict) -> None:
    """Signed bars either side of zero, sorted — who gained and who lost.

    One horizontal bar per category running left or right from a zero rule,
    green for positive and amber for negative, ordered by value so the
    ranking is the shape of the chart.

    Choose it over ``barh`` whenever the values are SIGNED: a plain bar chart
    of deltas puts the zero line somewhere in the middle without marking it,
    and the reader has to check each label for a minus sign. Choose
    ``waterfall`` instead when the contributions sum to a meaningful total,
    ``forest`` when each value carries a confidence interval and the question
    is whether it crosses zero, and ``lollipop`` when everything has the same
    sign.

    Spec: ``categories``, one ``series`` with ``values``. Optional ``sort``
    (default ``"desc"``), ``annotate``, ``fmt``.
    """
    entry = _only_series(spec, "diverging bar chart", '"type": "dumbbell" or "type": "bar"')
    values = _numbers(entry.get("values"), "series[0].values")
    cats = _labels(spec, values.size)
    order = _sort_order(spec, values, default="desc")
    values = values[order]
    cats = [cats[k] for k in order]
    y = np.arange(values.size, dtype=float)

    ax.barh(y, values, 0.66, color=[_signed_colour(float(v)) for v in values], zorder=2)
    ax.axvline(0.0, color="#333333", linewidth=1.0, zorder=3)

    low = min(0.0, float(values.min()))
    high = max(0.0, float(values.max()))
    span = max(high - low, 1e-9)
    annotate = flag(spec, "annotate")
    fmt = number_format(spec, "fmt", "+.1f")
    edge = 0.16 if annotate else 0.06
    ax.set_xlim(low - edge * span, high + edge * span)
    if annotate:
        offset = 0.015 * span
        for yi, value in zip(y, values, strict=True):
            positive = value >= 0
            ax.text(
                value + (offset if positive else -offset),
                yi,
                _num(value, fmt),
                ha="left" if positive else "right",
                va="center",
                fontsize=matplotlib.rcParams["font.size"] - 2,
                color="#333333",
            )

    ax.set_yticks(y, labels=cats)
    ax.set_ylim(values.size - 0.5, -0.5)
    ax.grid(visible=True, axis="x")
    ax.grid(visible=False, axis="y")


def _stack_brackets(
    spans: list[tuple[float, float]], floors: list[float], step: float, margin: float
) -> list[float]:
    """Give every significance bracket a height that clears the bars and its neighbours.

    Placing each bracket just above the tallest bar it spans is the obvious
    rule and it overprints as soon as two comparisons overlap — three
    brackets over the same group came out as one thick smear with the stars
    on top of each other. Narrow brackets are placed first so they sit low
    and the wide ones arch over them, which is the arrangement a reader
    expects; each bracket then rises from ITS OWN floor to clear every
    already-placed bracket whose x-range it touches, so overlap is
    impossible rather than unlikely.

    The per-bracket floor is why this cannot be done as "level times step":
    levelling first and adding the bar heights afterwards put a
    second-level bracket over short bars BELOW a first-level bracket over
    tall ones, reintroducing exactly the collision the stacking exists to
    remove.
    """
    heights = [0.0] * len(spans)
    placed: list[tuple[float, float, float]] = []
    for k in sorted(range(len(spans)), key=lambda j: (spans[j][1] - spans[j][0], spans[j][0])):
        x0, x1 = spans[k]
        y = floors[k]
        for px0, px1, py in placed:
            if x0 <= px1 + margin and px0 <= x1 + margin:
                y = max(y, py + step)
        heights[k] = y
        placed.append((x0, x1, y))
    return heights


def render_bar_sig(ax, spec: dict) -> None:
    """Grouped bars with significance brackets and stars over the named pairs.

    Ordinary grouped bars, plus a ``⊓`` bracket carrying a label between any
    two categories the spec names. Brackets are stacked so they never
    overlap each other or the bars, and the y-range is widened to fit them.

    Choose it over ``bar`` whenever the claim is a statistical one: putting
    the stars on the figure is what lets a reader check the claim against the
    picture instead of against a table three pages away. Choose ``forest``
    instead when the effect size and its interval matter more than the
    threshold, and plain ``bar`` when nothing is being tested.

    Spec: ``categories``, one or more ``series`` (``values``, optional
    ``errors``), and ``comparisons``: a list of
    ``{"a": 0, "b": 1, "label": "**"}`` where ``a`` and ``b`` are CATEGORY
    indices. An optional ``"series": k`` on a comparison anchors the bracket
    on one series' bars instead of the group centres.
    """
    series = _series(spec)
    n_groups = max(len(s.get("values") or []) for s in series)
    cats = _labels(spec, n_groups)
    x = np.arange(n_groups, dtype=float)
    width = 0.8 / len(series)

    tops = np.full(n_groups, -np.inf)
    bottoms = np.zeros(n_groups)
    offsets = []
    for i, s in enumerate(series):
        values = _numbers(s.get("values"), f"series[{i}].values", expect=n_groups)
        errors = (
            error_bars(s.get("errors"), f"series[{i}].errors", expect=n_groups)
            if s.get("errors")
            else np.zeros(n_groups)
        )
        offset = (i - (len(series) - 1) / 2) * width
        offsets.append(offset)
        ax.bar(
            x + offset,
            values,
            width * 0.92,
            label=literal(s.get("label")) if s.get("label") else None,
            color=PALETTE[i % len(PALETTE)],
            yerr=errors if s.get("errors") else None,
            capsize=2.5,
            error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
            zorder=2,
        )
        tops = np.maximum(tops, values + errors)
        bottoms = np.minimum(bottoms, values - errors)

    raw = spec.get("comparisons") or []
    if not isinstance(raw, list):
        raise SpecError(f"'comparisons' must be a list, got {type_name(raw)}")
    spans, labels, ends = [], [], []
    for i, comparison in enumerate(raw):
        if not isinstance(comparison, dict):
            raise SpecError(
                f"comparisons[{i}] must be an object, got {type_name(comparison)}. "
                'Each looks like {"a": 0, "b": 1, "label": "**"}'
            )
        pair = []
        for key in ("a", "b"):
            index = comparison.get(key)
            if isinstance(index, bool) or not isinstance(index, int):
                raise SpecError(
                    f"comparisons[{i}].{key} must be an integer category index, got {index!r}"
                )
            if not 0 <= index < n_groups:
                raise SpecError(
                    f"comparisons[{i}].{key} is {index} but there are only {n_groups} "
                    f"categories (0..{n_groups - 1})"
                )
            pair.append(index)
        if pair[0] == pair[1]:
            raise SpecError(f"comparisons[{i}] compares category {pair[0]} with itself")
        label = comparison.get("label")
        if not isinstance(label, str) or not label.strip():
            raise SpecError(
                f"comparisons[{i}].label must be a non-empty string — the star or "
                'p-value IS the message a bracket carries (e.g. "**", "n.s.", "p<0.01")'
            )
        which = comparison.get("series")
        if which is not None:
            if isinstance(which, bool) or not isinstance(which, int):
                raise SpecError(
                    f"comparisons[{i}].series must be an integer series index, got {which!r}"
                )
            if not 0 <= which < len(series):
                raise SpecError(
                    f"comparisons[{i}].series is {which} but there are only "
                    f"{len(series)} series (0..{len(series) - 1})"
                )
        shift = offsets[which] if which is not None else 0.0
        low, high = min(pair), max(pair)
        spans.append((low + shift, high + shift))
        ends.append((low, high))
        labels.append(literal(label))

    low_y = float(min(0.0, bottoms.min()))
    high_y = float(tops.max())
    span = max(high_y - low_y, 1e-9)
    if spans:
        # Every bracket must clear the tallest bar it arches over, not merely
        # the tallest bar in the figure — otherwise a short comparison at the
        # left floats far above its own bars for no reason.
        step = 0.085 * span
        floors = [float(tops[a : b + 1].max()) + 0.05 * span for a, b in ends]
        heights = _stack_brackets(spans, floors, step, 0.06)
        tick = 0.018 * span
        for (x0, x1), y, text in zip(spans, heights, labels, strict=True):
            ax.plot(
                [x0, x0, x1, x1],
                [y - tick, y, y, y - tick],
                color=_RULE,
                linewidth=1.0,
                solid_joinstyle="miter",
                zorder=4,
            )
            ax.text(
                (x0 + x1) / 2,
                y + tick * 0.4,
                text,
                ha="center",
                va="bottom",
                fontsize=matplotlib.rcParams["font.size"] - 1,
                color="#1A1A1A",
                zorder=4,
            )
        high_y = max(high_y, max(heights) + 0.075 * span)
    ax.set_ylim(low_y - (0.04 * span if low_y < 0 else 0.0), high_y + 0.04 * span)

    ax.set_xticks(x, labels=cats)
    ax.set_xlim(-0.6, n_groups - 0.4)
    _legend(ax, spec, series)


def render_radar(ax, spec: dict) -> None:
    """A closed polygon per method over three or more metrics on one circular axis.

    Each metric gets a spoke, each method a polygon through its values, drawn
    with explicit trigonometry on the ordinary Cartesian axes the caller
    supplied — a polar axes would mean creating one, which no renderer may
    do. Rings are labelled with the values they stand for, so the radial
    scale is readable rather than decorative.

    Choose it when the finding is a PROFILE — "ours trades a little accuracy
    for much better latency and cost" — across four to eight comparable
    metrics. It is the only chart here that shows the shape of a trade-off in
    one glance. Choose grouped ``bar`` instead when the reader needs to
    compare exact values (area on a radar exaggerates differences and depends
    on the arbitrary order of the spokes), and ``parallel`` when the metrics
    have wildly different units or there are more than about eight.

    Spec: ``categories`` (metric names, 3 or more), one ``series`` per method
    (``label`` + ``values``). Optional ``normalize``: ``"none"`` (default,
    one shared radial scale) or ``"axis"`` (each metric scaled to its own
    min/max across the methods, printed under the spoke name). Optional
    ``rlim`` ``[low, high]`` pins the shared scale; ``fmt`` formats the ring
    labels.
    """
    series = _series(spec)
    n = max(len(s.get("values") or []) for s in series)
    if n < 3:
        raise SpecError(
            f"a radar needs at least 3 metrics, got {n} — with two the polygon "
            'collapses to a line. Use "type": "bar" or "type": "dumbbell".'
        )
    cats = _labels(spec, n)
    data = np.vstack(
        [_numbers(s.get("values"), f"series[{i}].values", expect=n) for i, s in enumerate(series)]
    )
    fmt = number_format(spec, "fmt", "g")
    normalize = spec.get("normalize", "none")
    if normalize not in ("none", "axis"):
        raise SpecError(f'\'normalize\' must be "none" or "axis", got {normalize!r}')

    tips: list[str] = list(cats)
    if normalize == "axis":
        # Per-axis normalisation over two methods pins one to the rim and the
        # other to the centre on EVERY metric, whatever the real gap: a
        # 0.2-point difference and a 40-point difference draw identically.
        # That is a figure that misreports its data, which is the one thing
        # this family refuses to do.
        if len(series) < 3:
            raise SpecError(
                f"'normalize' is \"axis\" with only {len(series)} methods. Scaling each "
                "metric to its own min/max across two series puts one at the rim and "
                "the other at the centre on every spoke regardless of how close they "
                'are. Use "normalize": "none" with a shared radial scale, or "type": '
                '"dumbbell" if the per-metric gap is the finding.'
            )
        lows, highs = data.min(axis=0), data.max(axis=0)
        # A metric every method scores identically has no range to normalise
        # against; dividing by it would be a NaN drawn as a missing vertex.
        flat = highs - lows == 0
        scaled = np.where(flat, 0.5, (data - lows) / np.where(flat, 1.0, highs - lows))
        tips = [
            f"{c}\n{_num(lo, fmt)}–{_num(hi, fmt)}"
            for c, lo, hi in zip(cats, lows, highs, strict=True)
        ]
        rings, ring_text = np.array([0.25, 0.5, 0.75, 1.0]), None
    else:
        if spec.get("rlim") is not None:
            bounds = _numbers(spec.get("rlim"), "rlim", expect=2)
            r_lo, r_hi = float(bounds[0]), float(bounds[1])
            if r_hi <= r_lo:
                raise SpecError(f"'rlim' is [{r_lo:g}, {r_hi:g}] — low must be below high")
            if data.min() < r_lo or data.max() > r_hi:
                raise SpecError(
                    f"'rlim' is [{r_lo:g}, {r_hi:g}] but the values run "
                    f"{data.min():g}..{data.max():g}, so points would fall outside the "
                    "outer ring and be drawn as if they were on it. Widen it or drop it."
                )
        else:
            r_lo = min(0.0, float(data.min()))
            r_hi = r_lo + _nice_ceiling(float(data.max()) - r_lo)
        scaled = (data - r_lo) / (r_hi - r_lo)
        rings = np.array([0.25, 0.5, 0.75, 1.0])
        ring_text = [_num(r_lo + f * (r_hi - r_lo), fmt) for f in rings]

    # Clockwise from the top, which is how a reader scans a dial.
    angles = np.pi / 2 - 2 * np.pi * np.arange(n) / n
    cos, sin = np.cos(angles), np.sin(angles)
    closed = np.append(np.arange(n), 0)

    for radius in rings:  # the web, behind everything
        ax.plot(
            radius * cos[closed],
            radius * sin[closed],
            color="#D6D6D6",
            linewidth=0.7,
            zorder=1,
        )
    for c, s in zip(cos, sin, strict=True):
        ax.plot([0.0, c], [0.0, s], color="#D6D6D6", linewidth=0.7, zorder=1)

    for i, entry in enumerate(series):
        radii = scaled[i][closed]
        style = series_style(i)
        ax.plot(
            radii * cos[closed],
            radii * sin[closed],
            marker="o",
            markersize=4,
            linewidth=1.8,
            zorder=3,
            label=literal(entry.get("label")) if entry.get("label") else None,
            **style,
        )
        ax.fill(
            radii * cos[closed], radii * sin[closed], color=style["color"], alpha=0.13, zorder=2
        )

    tip_r = 1.13
    label_pt = matplotlib.rcParams["font.size"] - 1
    for c, s, name in zip(cos, sin, tips, strict=True):
        ax.text(
            tip_r * c,
            tip_r * s,
            name,
            ha="center" if abs(c) < 0.2 else ("left" if c > 0 else "right"),
            va="center" if abs(s) < 0.2 else ("bottom" if s > 0 else "top"),
            fontsize=label_pt,
            color="#1A1A1A",
        )
    if ring_text is not None:
        # On the bisector between the first and last spoke, which is the one
        # direction guaranteed to have no spoke, no polygon vertex and no
        # metric name on it.
        bisector = np.pi / 2 + np.pi / n
        for radius, text in zip(rings, ring_text, strict=True):
            ax.text(
                radius * np.cos(bisector),
                radius * np.sin(bisector),
                text,
                ha="center",
                va="center",
                fontsize=label_pt - 1,
                color="#666666",
                bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.0, "alpha": 0.85},
                zorder=4,
            )

    # Reserve for the spoke names in X ONLY. Reserving the same amount in Y is
    # the obvious move and it wastes half the canvas: with an equal aspect the
    # axes BOX takes the shape of the limits, so a square limit on a chart
    # whose names stick out sideways drew a hexagon a fifth of the figure wide,
    # floating in a band of whitespace. Sideways is where the names go, so
    # sideways is where the room goes.
    axes_in = _axes_size_in(ax)[0]
    x_limit = tip_r + _outside_pad(
        max(len(line) for tip in tips for line in tip.split("\n")),
        label_pt,
        axes_in,
        2 * tip_r,
        "metric name",
    )
    lines = max(tip.count("\n") + 1 for tip in tips)
    y_limit = tip_r + lines * (label_pt * 1.45 / 72.0) * (2 * x_limit / axes_in)
    ax.set_xlim(-x_limit, x_limit)
    ax.set_ylim(-y_limit, y_limit)
    ax.set_aspect("equal", adjustable="box")
    ax.grid(visible=False)
    ax.axis("off")
    _legend_below(ax, spec, series, clear_in=0.0)


def render_parallel(ax, spec: dict) -> None:
    """Parallel coordinates — one polyline per configuration across independently scaled axes.

    Every axis is a vertical line scaled to its OWN min and max, both printed
    at the ends, so quantities in different units (learning rate, batch size,
    accuracy) sit side by side without one flattening the others. A
    configuration is one polyline crossing all of them.

    Choose it for a hyperparameter sweep or any multi-column results table
    where the question is which settings travel together: a line that runs
    high on the objective axis can be traced back across every setting that
    produced it, which no arrangement of bars will show. Choose ``radar``
    instead for a small number of comparable metrics where the profile shape
    is the point, ``scatter`` for exactly two variables, and ``heatmap`` when
    the sweep is a full grid over two settings.

    Note the two things this chart cannot do: adjacent axes only reveal
    relationships between NEIGHBOURS, so the column order is part of the
    argument, and past roughly thirty lines it saturates into a solid band.

    Spec: ``categories`` (axis names, 2 or more), one ``series`` per
    configuration (``label`` + one ``values`` entry per axis). Optional
    ``fmt`` (default ``"g"``) formats the printed min/max.
    """
    series = _series(spec)
    k = max(len(s.get("values") or []) for s in series)
    if k < 2:
        raise SpecError(
            f"parallel coordinates need at least 2 axes, got {k} — with one there is "
            'nothing to connect. Use "type": "bar" or "type": "lollipop".'
        )
    names = _labels(spec, k)
    data = np.vstack(
        [_numbers(s.get("values"), f"series[{i}].values", expect=k) for i, s in enumerate(series)]
    )
    fmt = number_format(spec, "fmt", "g")

    lows, highs = data.min(axis=0), data.max(axis=0)
    # An axis on which every configuration scored the same has no range: put
    # the lines through its midpoint and print the one value, rather than
    # dividing by zero and drawing a polyline with a hole in it.
    flat = highs - lows == 0
    scaled = np.where(flat, 0.5, (data - lows) / np.where(flat, 1.0, highs - lows))

    x = np.arange(k, dtype=float)
    for j in x:
        ax.plot([j, j], [0.0, 1.0], color="#BBBBBB", linewidth=1.0, zorder=1)
    for i, entry in enumerate(series):
        ax.plot(
            x,
            scaled[i],
            marker="o",
            markersize=3.5,
            linewidth=1.6,
            alpha=0.9,
            zorder=2,
            label=literal(entry.get("label")) if entry.get("label") else None,
            **series_style(i),
        )

    tick_pt = matplotlib.rcParams["xtick.labelsize"]
    for j, lo, hi, is_flat in zip(x, lows, highs, flat, strict=True):
        ax.text(
            j,
            1.025,
            _num(hi, fmt),
            ha="center",
            va="bottom",
            fontsize=tick_pt - 1,
            color="#555555",
        )
        if not is_flat:
            ax.text(
                j,
                -0.025,
                _num(lo, fmt),
                ha="center",
                va="top",
                fontsize=tick_pt - 1,
                color="#555555",
            )

    # Wrap the axis names to their own column width. Rotating them instead
    # would tilt them into the min-value text sitting directly above.
    slot_chars = max(6, int(_axes_size_in(ax)[0] * 72 / (k * tick_pt * _EM_RATIO)))
    wrapped = [textwrap.fill(name, slot_chars, break_long_words=False) for name in names]
    ax.set_xticks(x, labels=wrapped)
    # Push the names clear of the min-value text drawn just under each axis.
    ax.tick_params(axis="x", length=0, pad=14)
    ax.set_xlim(-0.35, k - 0.65)
    ax.set_ylim(-0.09, 1.13)
    ax.yaxis.set_visible(False)
    # No frame at all: the vertical rules ARE the axes here, and a y-axis or a
    # baseline spine would be a scale the chart does not have.
    for side in ("left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.grid(visible=False)
    name_lines = max(name.count("\n") + 1 for name in wrapped)
    _legend_below(ax, spec, series, clear_in=(14 + name_lines * 1.35 * tick_pt) / 72.0)


COMPARE_RENDERERS = {
    "slope": render_slope,
    "dumbbell": render_dumbbell,
    "lollipop": render_lollipop,
    "waterfall": render_waterfall,
    "diverging": render_diverging,
    "bar_sig": render_bar_sig,
    "radar": render_radar,
    "parallel": render_parallel,
}
