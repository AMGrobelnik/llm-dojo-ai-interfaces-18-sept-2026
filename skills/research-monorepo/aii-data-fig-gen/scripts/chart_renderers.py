"""One renderer per chart type. Each draws a spec onto a single Axes.

Renderers never create or save figures and never call ``plt.*`` global
state — that is the caller's job. Keeping them ``(ax, spec) -> None`` is
what lets ``panel`` compose any of them into a subplot grid without a
special case per type.

Tolerant about PRESENTATION, strict about DATA. A missing title, colour or
aspect falls back to a sane default — these specs are authored by a model,
and losing a whole figure over one absent cosmetic field is a bad trade.

But anything that would make the picture disagree with its numbers raises
``SpecError``, which the CLI turns into a message naming the offending key.
That line matters because the failures on the wrong side of it are silent:
five categories against three values used to render three bars and drop two
categories, and a NaN used to render as an empty slot that reads as a
measured zero. Both produced a confident, plausible, wrong figure that
nothing downstream could detect — strictly worse than no figure at all.
"""

from __future__ import annotations

import numpy as np
from chart_common import (
    SpecError,
    colour_map,
    flag,
    number_format,
    number_option,
)
from chart_common import (
    cell_halo as _cell_halo,
)
from chart_common import (
    draw_legend as _legend,
)
from chart_common import (
    error_bars as _error_bars,
)
from chart_common import (
    ink_for as _ink_for,
)
from chart_common import (
    labels_for as _labels,
)
from chart_common import (
    numbers as _numbers,
)
from chart_common import (
    reject_pointless_diverging as _reject_pointless_diverging,
)
from chart_common import (
    reject_unrenderable_categories as _reject_unrenderable_categories,
)
from chart_common import (
    require_annotations_fit as _require_annotations_fit,
)
from chart_common import (
    require_colour_limits_cover as _require_colour_limits_cover,
)
from chart_common import (
    require_fittable as _require_fittable,
)
from chart_common import (
    require_positive as _require_positive,
)
from chart_common import (
    series_of as _series,
)
from chart_renderers_cluster import CLUSTER_RENDERERS
from chart_renderers_compare import COMPARE_RENDERERS
from chart_renderers_dist import DIST_RENDERERS
from chart_renderers_eval import EVAL_RENDERERS
from chart_renderers_extra import EXTRA_RENDERERS
from chart_renderers_more import MORE_RENDERERS
from chart_renderers_sets import SETS_RENDERERS
from chart_renderers_stats import STATS_RENDERERS
from chart_style import (
    DIVERGING_CMAP,
    PALETTE,
    SEQUENTIAL_CMAP,
    fix_log_ticks,
    literal,
    number,
    place_point_label,
    series_style,
)


def render_bar(ax, spec: dict) -> None:
    """Grouped or stacked bars, with optional error bars.

    Grouped is the default: stacking hides the individual series values,
    which is usually the thing a results table is trying to show.

    ``stacked`` turns stacking on when the total is the point rather than the
    parts. ``annotate`` prints each bar's value above it — worth it when the
    figure carries a results table's numbers, and not when there are enough
    bars that the labels become the chart.
    """
    series = _series(spec)
    n_groups = max(len(s.get("values") or []) for s in series)
    cats = _labels(spec, n_groups)
    x = np.arange(n_groups)
    stacked = flag(spec, "stacked")

    if stacked:
        bottom = np.zeros(n_groups)
        for i, s in enumerate(series):
            vals = _numbers(s.get("values"), f"series[{i}].values", expect=n_groups)
            # A stack running through zero cannot be read: segments overlap,
            # every visible height differs from its value and the sign is
            # gone. Observed rendering [10,20,30]/[-5,-25,-10] as 5/20/20
            # with one bar missing entirely.
            if np.any(vals < 0):
                raise SpecError(
                    f"series[{i}].values has a negative in a STACKED bar. Stacked "
                    "segments are drawn end to end, so a negative overlaps the "
                    "one below and every height stops matching its value. Use "
                    'grouped bars (drop "stacked") or a "forest" chart for signed '
                    "quantities."
                )
            ax.bar(
                x,
                vals,
                0.62,
                bottom=bottom,
                label=literal(s.get("label")) if s.get("label") else None,
                color=PALETTE[i % len(PALETTE)],
            )
            bottom += vals
    else:
        width = 0.8 / len(series)
        for i, s in enumerate(series):
            vals = _numbers(s.get("values"), f"series[{i}].values", expect=n_groups)
            errs = s.get("errors")
            offset = (i - (len(series) - 1) / 2) * width
            ax.bar(
                x + offset,
                vals,
                width * 0.92,
                label=literal(s.get("label")) if s.get("label") else None,
                color=PALETTE[i % len(PALETTE)],
                yerr=_error_bars(errs, f"series[{i}].errors", expect=n_groups) if errs else None,
                capsize=2.5,
                error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
            )
            if flag(spec, "annotate"):
                for xi, v in zip(x + offset, vals, strict=False):
                    ax.text(xi, v, f"{v:.1f}", ha="center", va="bottom", fontsize=8)

    _reject_unrenderable_categories(cats)
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    _legend(ax, spec, series)


def render_barh(ax, spec: dict) -> None:
    """Horizontal bars, one per category.

    Choose over ``bar`` whenever the category names are long — they sit on
    the y-axis with the full figure width to run into, instead of being
    rotated or truncated under a vertical bar. Also the natural form for a
    ranking, since the eye reads top-to-bottom. For a signed quantity use
    ``diverging``; when the gap between two values is the story use
    ``dumbbell``; past ~20 categories ``lollipop`` stays cleaner.
    """
    series = _series(spec)
    n = max(len(s.get("values") or []) for s in series)
    cats = _labels(spec, n)
    y = np.arange(n)
    height = 0.8 / len(series)
    for i, s in enumerate(series):
        vals = _numbers(s.get("values"), f"series[{i}].values", expect=n)
        errs = s.get("errors")
        offset = (i - (len(series) - 1) / 2) * height
        ax.barh(
            y + offset,
            vals,
            height * 0.92,
            label=literal(s.get("label")) if s.get("label") else None,
            color=PALETTE[i % len(PALETTE)],
            xerr=_error_bars(errs, f"series[{i}].errors", expect=n) if errs else None,
            capsize=2.5,
            error_kw={"elinewidth": 1.0, "ecolor": "#333333"},
        )
    ax.set_yticks(y)
    ax.set_yticklabels(cats)
    ax.invert_yaxis()  # first category at the top, as a ranking reads
    ax.grid(axis="x", visible=True)
    ax.grid(axis="y", visible=False)
    _legend(ax, spec, series, headroom=False)


def render_line(ax, spec: dict) -> None:
    """Multi-series lines with optional shaded uncertainty bands.

    ``band`` may be a scalar (constant ±) or a per-point list; either way it
    is drawn at low alpha behind the line so overlapping bands stay readable.

    ``logx`` / ``logy`` put either axis on a log scale, for a quantity that
    spans decades. Non-positive values are refused rather than dropped: a log
    axis deletes them silently, leaving a curve missing points nobody counted.
    """
    series = _series(spec)
    for i, s in enumerate(series):
        y = _numbers(s.get("values"), f"series[{i}].values")
        raw_x = s.get("x") or spec.get("x")
        x = _numbers(raw_x, f"series[{i}].x", expect=y.size) if raw_x else np.arange(y.size)
        style = series_style(i)
        colour = style["color"]
        ax.plot(x, y, label=literal(s.get("label")) if s.get("label") else None, **style)
        band = s.get("band")
        if band is not None:
            b = (
                _numbers(band, f"series[{i}].band", expect=y.size)
                if isinstance(band, list)
                else _numbers([band] * y.size, f"series[{i}].band")
            )
            ax.fill_between(x, y - b, y + b, color=colour, alpha=0.18, linewidth=0)
    if flag(spec, "logx"):
        for i, s in enumerate(series):
            _require_positive(
                _numbers(s.get("x") or spec.get("x") or [], f"series[{i}].x"), f"series[{i}].x", "x"
            )
        ax.set_xscale("log")
        fix_log_ticks(ax, "x")
    if flag(spec, "logy"):
        for i, s in enumerate(series):
            _require_positive(
                _numbers(s.get("values"), f"series[{i}].values"), f"series[{i}].values", "y"
            )
        ax.set_yscale("log")
        fix_log_ticks(ax, "y")
    _legend(ax, spec, series)


def render_scatter(ax, spec: dict) -> None:
    """Scatter with an optional least-squares fit and its equation.

    The fit is computed here rather than accepted from the spec so the line
    always matches the plotted points — a fit passed in alongside the data
    can silently disagree with it.

    ``logx`` / ``logy`` put either axis on a log scale. Reach for them when a
    quantity spans decades — parameters, tokens, cost — rather than letting
    the top decade swallow everything below it.
    """
    series = _series(spec)
    for i, s in enumerate(series):
        if not s.get("x") or not (s.get("values") or s.get("y")):
            raise SpecError(f"series[{i}] needs both 'x' and 'values'")
        y = _numbers(s.get("values") or s.get("y"), f"series[{i}].values")
        x = _numbers(s.get("x"), f"series[{i}].x", expect=y.size)
        colour = PALETTE[i % len(PALETTE)]
        ax.scatter(
            x,
            y,
            s=26,
            alpha=0.65,
            color=colour,
            edgecolors="none",
            label=literal(s.get("label")) if s.get("label") else None,
        )
        if flag(spec, "fit"):
            _require_fittable(x, y, f"series[{i}]")
            slope, intercept = np.polyfit(x, y, 1)
            xs = np.linspace(x.min(), x.max(), 100)
            ax.plot(xs, slope * xs + intercept, color=PALETTE[(i + 1) % len(PALETTE)], linewidth=2)
            r = float(np.corrcoef(x, y)[0, 1])
            ax.text(
                0.03,
                0.96,
                # The sign is the OPERATOR, not part of the number: a
                # negative intercept printed "y = 0.762x + -4.05", which
                # nobody writes — and the two signs in it were different
                # glyphs, because an f-string gives an ASCII hyphen while the
                # axis ticks an inch away carry U+2212. Both numbers go
                # through ``number`` for the same reason.
                f"y = {number(slope, '.3g')}x "
                f"{'\N{MINUS SIGN}' if intercept < 0 else '+'} "
                f"{number(abs(intercept), '.3g')}   (R² = {r * r:.3f})",
                transform=ax.transAxes,
                va="top",
                fontsize=9,
            )
    # Gated exactly as ``line`` and ``scaling`` gate theirs. Without it a log
    # axis MASKS every non-positive point instead of refusing: five points
    # were drawn trending up while the fit annotation above them read
    # "y = -1.75x + 53.2", because the slope was still computed over the two
    # at x = 0 that the reader cannot see. The figure disagreed with itself.
    if flag(spec, "logx"):
        for i, s in enumerate(series):
            _require_positive(
                _numbers(s.get("x") or spec.get("x") or [], f"series[{i}].x"), f"series[{i}].x", "x"
            )
        ax.set_xscale("log")
        fix_log_ticks(ax, "x")
    if flag(spec, "logy"):
        for i, s in enumerate(series):
            _require_positive(
                _numbers(s.get("values"), f"series[{i}].values"), f"series[{i}].values", "y"
            )
        ax.set_yscale("log")
        fix_log_ticks(ax, "y")
    _legend(ax, spec, series)


#: Past this many rows or columns a heatmap stops labelling every one of them.
#: Measured at the default 7-inch width by drawing each size and asking the
#: legibility gate: every tick is still readable at 36, and at 40 there are 39
#: colliding pairs. By 512 there are 11,123, which is why a matrix that size
#: could not be drawn at all before. The gate still has the last word — this
#: only stops the figure being built in a shape it is going to refuse.
MAX_LABELLED_CELLS = 36


def _index_ticks(count: int) -> tuple[list[int], list[str]]:
    """Positions and labels for an axis that is an INDEX, not a set of names.

    Every row of a 512x512 attention map got a tick before this. The labels
    were auto-generated 1..N — position markers, not names anyone chose — and
    all 512 were drawn, so the figure was refused for label collisions and a
    large matrix could not be plotted at all. Turning annotations off did not
    help, because the ticks are numbered whether or not the cells are.

    Thinned to about ten, on round-ish steps, so the axis still says where you
    are. Only ever applied to generated indices: labels the SPEC supplied are
    names someone chose, and hiding those silently is the failure this
    catalogue refuses everywhere else.
    """

    step = max(1, round(count / 10))
    for nice in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        if nice >= step:
            step = nice
            break
    positions = list(range(0, count, step))
    return positions, [str(i + 1) for i in positions]


def render_heatmap(ax, spec: dict) -> None:
    """Annotated matrix — confusion matrices, correlation, ablation grids.

    Cell text switches between black and white on the luminance of its own
    cell, so annotations stay legible at both ends of the colour map. A
    fixed text colour is unreadable at one end, which is the usual defect.

    Keys: ``matrix``, ``row_labels``, ``col_labels``, ``cbar_label``,
    ``annotate`` (default true), ``fmt`` (default ".2f"), ``cmap``,
    ``vmin``/``vmax``, and ``diverging`` — a red-blue map centred on zero, for
    SIGNED quantities only. On data that never crosses zero it is refused:
    half the range would go unused and every cell would land in one arm.
    """
    raw = spec.get("matrix")
    if not isinstance(raw, list) or not raw or not all(isinstance(row, list) for row in raw):
        raise SpecError("'matrix' must be a non-empty list of equal-length rows")
    widths = {len(row) for row in raw}
    if len(widths) != 1:
        raise SpecError(f"'matrix' rows have differing lengths {sorted(widths)}")
    # Same numeric gate as every series: a NaN here made vmin/vmax NaN, which
    # collapsed the colourbar to -0.1..0.1 and saturated every real cell.
    matrix = np.vstack([_numbers(row, f"matrix[{r}]") for r, row in enumerate(raw)])
    diverging = flag(spec, "diverging")
    if diverging:
        _reject_pointless_diverging(matrix)
    cmap = colour_map(spec, DIVERGING_CMAP if diverging else SEQUENTIAL_CMAP)
    vmax = number_option(
        spec, "vmax", float(np.abs(matrix).max()) if diverging else float(matrix.max())
    )
    vmin = number_option(spec, "vmin", -vmax if diverging else float(matrix.min()))
    _require_colour_limits_cover(
        matrix, vmin, vmax, stated=[k for k in ("vmin", "vmax") if k in spec]
    )

    im = ax.imshow(matrix, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")
    cbar = ax.figure.colorbar(im, ax=ax, fraction=0.046, pad=0.03)
    if spec.get("cbar_label"):
        cbar.set_label(literal(spec["cbar_label"]))

    rows = _labels({"categories": spec.get("row_labels")}, matrix.shape[0])
    cols = _labels({"categories": spec.get("col_labels")}, matrix.shape[1])
    # Named axes keep every tick; generated indices get thinned once there are
    # more of them than fit. See ``_index_ticks``.
    if spec.get("col_labels") or matrix.shape[1] <= MAX_LABELLED_CELLS:
        ax.set_xticks(np.arange(matrix.shape[1]), labels=cols)
    else:
        ax.set_xticks(*_index_ticks(matrix.shape[1]))
    if spec.get("row_labels") or matrix.shape[0] <= MAX_LABELLED_CELLS:
        ax.set_yticks(np.arange(matrix.shape[0]), labels=rows)
    else:
        ax.set_yticks(*_index_ticks(matrix.shape[0]))
    if sum(len(c) for c in cols) > 40:
        ax.tick_params(axis="x", labelrotation=35)
        for label in ax.get_xticklabels():
            label.set_ha("right")
    ax.grid(visible=False)

    if flag(spec, "annotate", True):
        fmt = number_format(spec, "fmt", ".2f")
        _require_annotations_fit(
            spec,
            matrix.shape[1],
            max((number(v, fmt) for v in matrix.ravel()), key=len, default=""),
        )
        for r in range(matrix.shape[0]):
            for c in range(matrix.shape[1]):
                ax.text(
                    c,
                    r,
                    number(matrix[r, c], fmt),
                    ha="center",
                    va="center",
                    fontsize=8,
                    color=_ink_for(im, matrix[r, c]),
                    path_effects=_cell_halo(_ink_for(im, matrix[r, c])),
                )


def render_box(ax, spec: dict) -> None:
    """Box plots over raw samples — median, quartiles, whiskers, outliers.

    The compact default for comparing a handful of distributions. Choose
    ``violin`` instead when a distribution may be multi-modal, which a box
    hides completely; ``strip`` when n is small enough that every
    observation should be visible; ``ridgeline`` past about six groups.
    """
    _distribution(ax, spec, kind="box")


def render_violin(ax, spec: dict) -> None:
    """Violin plots — the full density of each distribution, mirrored.

    Choose over ``box`` when the shape matters: a bimodal distribution and a
    wide unimodal one produce the same box and obviously different violins.
    Costs more width per group, so past about six groups prefer
    ``ridgeline``, and below ~20 samples per group prefer ``strip``, where
    a density estimate is more confident than the data warrants.
    """
    _distribution(ax, spec, kind="violin")


def _distribution(ax, spec: dict, *, kind: str) -> None:
    series = _series(spec)
    data = [_numbers(s.get("values"), f"series[{i}].values") for i, s in enumerate(series)]
    labels = [literal(s.get("label") or str(i + 1)) for i, s in enumerate(series)]
    positions = np.arange(1, len(data) + 1)

    if kind == "box":
        bp = ax.boxplot(
            data,
            positions=positions,
            widths=0.55,
            patch_artist=True,
            medianprops={"color": "#1a1a1a", "linewidth": 1.4},
            flierprops={"marker": "o", "markersize": 3, "alpha": 0.4},
        )
        for i, patch in enumerate(bp["boxes"]):
            patch.set_facecolor(PALETTE[i % len(PALETTE)])
            patch.set_alpha(0.75)
    else:
        vp = ax.violinplot(data, positions=positions, widths=0.7, showmedians=True)
        for i, body in enumerate(vp["bodies"]):
            body.set_facecolor(PALETTE[i % len(PALETTE)])
            body.set_alpha(0.7)
        for key in ("cmedians", "cbars", "cmins", "cmaxes"):
            if key in vp:
                vp[key].set_color("#333333")

    ax.set_xticks(positions)
    ax.set_xticklabels(labels)


def render_hist(ax, spec: dict) -> None:
    """Histogram of one or more samples, binned into counts or density.

    Right when the SHAPE of a single distribution is the point — where the
    mass sits, whether it is skewed, where it cuts off. For comparing
    distributions prefer ``ecdf``, which needs no bin-width choice and so
    cannot be tuned into telling a different story. Above two or three
    overlaid series a histogram turns to mud; use ``ridgeline``.
    """
    series = _series(spec)
    bins = spec.get("bins", 30)
    data = [_numbers(s.get("values"), f"series[{i}].values") for i, s in enumerate(series)]
    # One set of edges for every series. Each ax.hist call computes its own
    # edges from the range of the sample it is given, so two overlaid series
    # got different bin WIDTHS while sharing one "Count" axis: 400 points plus
    # a single far outlier binned 3.6x wider than the same 400 points alone,
    # and its bars came out 2.9x taller. The reader compares bar heights; they
    # are only comparable when the bars measure equal intervals. ``bins`` is a
    # positive int by the time it gets here — ``validate_spec`` owns that, for
    # panels too — so the count is simply re-read over the pooled sample.
    if len(data) > 1:
        bins = np.histogram_bin_edges(np.concatenate(data), bins=bins)
    for i, s in enumerate(series):
        vals = data[i]
        ax.hist(
            vals,
            bins=bins,
            label=literal(s.get("label")) if s.get("label") else None,
            color=PALETTE[i % len(PALETTE)],
            alpha=0.55 if len(series) > 1 else 0.85,
            histtype="stepfilled" if len(series) > 1 else "bar",
            density=flag(spec, "density"),
        )
    if flag(spec, "density"):
        ax.set_ylabel(literal(spec.get("ylabel") or "Density"))
    else:
        # A count axis has no half-observations on it. matplotlib's default
        # locator happily labels a small sample 0.00, 0.25, 0.50 ..., which
        # says the bin holding one item holds a quarter of one.
        from matplotlib.ticker import MaxNLocator

        ax.yaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_ylabel(literal(spec.get("ylabel") or "Count"))
    _legend(ax, spec, series)


def render_ecdf(ax, spec: dict) -> None:
    """Empirical CDFs — compares whole distributions without binning choices.

    Preferred over a histogram when the comparison is between distributions
    rather than about the shape of one: no bin width to argue about.
    """
    series = _series(spec)
    for i, s in enumerate(series):
        # No empty check: `numbers` refuses an empty list on the line above,
        # with a message that names the series. A `continue` here could only
        # ever be reached by a value that got past it, and there is none.
        vals = np.sort(_numbers(s.get("values"), f"series[{i}].values"))
        y = np.arange(1, vals.size + 1) / vals.size
        ax.step(
            vals,
            y,
            where="post",
            label=literal(s.get("label")) if s.get("label") else None,
            color=PALETTE[i % len(PALETTE)],
        )
    ax.set_ylim(0, 1.02)
    _legend(ax, spec, series)


def render_scaling(ax, spec: dict) -> None:
    """Log-log scaling curve with a fitted power law.

    The fitted exponent is the finding in a scaling figure, so it is
    computed from the plotted points and annotated rather than left for the
    reader to eyeball off a log axis.

    ``fit`` turns that off, and defaults to true. It went unnamed here for
    long enough that the only way to learn the fit was optional was to read
    the renderer — while the exponent it draws is the claim the figure makes,
    which is exactly the sort of key a caller has to be able to find.
    """
    series = _series(spec)
    for i, s in enumerate(series):
        y = _numbers(s.get("values"), f"series[{i}].values")
        x = _numbers(s.get("x") or spec.get("x"), f"series[{i}].x", expect=y.size)
        _require_positive(x, f"series[{i}].x", "x")
        _require_positive(y, f"series[{i}].values", "y")
        colour = PALETTE[i % len(PALETTE)]
        ax.plot(
            x,
            y,
            "o-",
            color=colour,
            label=literal(s.get("label")) if s.get("label") else None,
            markersize=5,
        )
        if flag(spec, "fit", True) and np.all(x > 0) and np.all(y > 0):
            _require_fittable(np.log(x), np.log(y), f"series[{i}]")
            exponent, log_c = np.polyfit(np.log(x), np.log(y), 1)
            xs = np.logspace(np.log10(x.min()), np.log10(x.max()), 100)
            ax.plot(xs, np.exp(log_c) * xs**exponent, "--", color=colour, alpha=0.6, linewidth=1.2)
            ax.text(
                0.03,
                0.06 + 0.07 * i,
                f"{s.get('label', 'fit')}: exponent = {number(exponent, '.3f')}",
                transform=ax.transAxes,
                fontsize=9,
                color=colour,
            )
    ax.set_xscale("log")
    ax.set_yscale("log")
    # A loss axis typically spans well under a decade — without this the
    # y-axis renders with no labels at all.
    fix_log_ticks(ax, "x")
    fix_log_ticks(ax, "y")
    _legend(ax, spec, series)


def render_area(ax, spec: dict) -> None:
    """Stacked areas — how a total divides into parts across a continuous axis.

    Use when the TOTAL and its composition both matter, e.g. token spend by
    pipeline stage over time. The top edge is the total; each band is a
    part. Only the bottom band has a flat baseline, so comparing the middle
    bands against each other is unreliable — if that comparison is the
    point, use ``line`` with one line per part. Requires non-negative
    values, since a negative band would overlap the one beneath it.
    """
    series = _series(spec)
    n = max(len(s.get("values") or []) for s in series)
    x = _numbers(spec.get("x"), "x", expect=n) if spec.get("x") else np.arange(n)
    stack = [
        _numbers(s.get("values"), f"series[{i}].values", expect=n) for i, s in enumerate(series)
    ]
    # The docstring above has always said non-negative; nothing enforced it.
    # ``stackplot`` runs a cumulative sum, so a negative band folds back over
    # the one beneath and the later series is painted on top: bands of 10/−8/5
    # drew as 10/8/5 with the reader seeing 2/5/3 and a top edge of 10 where
    # the total is 7. Every number on the figure is wrong. Refused the way
    # stacked ``bar`` and ``stacked_pct`` already refuse it.
    for i, vals in enumerate(stack):
        if np.any(vals < 0):
            raise SpecError(
                f"series[{i}].values has a negative in a STACKED area. Bands are drawn "
                "end to end, so a negative one overlaps the band beneath it and every "
                "height — including the top edge the reader takes for the total — stops "
                "matching its value. Use 'line' with one line per part for signed "
                "quantities."
            )
    ax.stackplot(
        x,
        *stack,
        labels=[literal(s.get("label") or "") for s in series],
        colors=[PALETTE[i % len(PALETTE)] for i in range(len(series))],
        alpha=0.85,
    )
    ax.margins(x=0)
    _legend(ax, spec, series)


def render_forest(ax, spec: dict) -> None:
    """Effect sizes with confidence intervals, one row per item.

    The right figure for an ablation or a per-benchmark delta: it shows
    whether an interval crosses zero, which a bar chart obscures.
    """
    series = _series(spec)
    s = series[0]
    values = _numbers(s.get("values"), "series[0].values")
    errs = (
        _error_bars(s.get("errors"), "series[0].errors", expect=values.size)
        if s.get("errors")
        else np.zeros(values.size)
    )
    labels = _labels(spec, values.size)
    y = np.arange(values.size)

    ax.errorbar(
        values,
        y,
        xerr=errs,
        fmt="o",
        color=PALETTE[0],
        ecolor="#333333",
        elinewidth=1.2,
        capsize=3,
        markersize=6,
    )
    ax.axvline(spec.get("null_line", 0.0), color="#999999", linestyle="--", linewidth=1)
    ax.set_yticks(y, labels=labels)
    ax.invert_yaxis()
    ax.grid(axis="x", visible=True)
    ax.grid(axis="y", visible=False)


def render_pareto(ax, spec: dict) -> None:
    """Scatter with the non-dominated frontier drawn through it.

    Standard for cost/quality trade-offs. The frontier is computed, so it
    cannot disagree with the points.

    ``logx`` puts cost on a log scale, which is usually what a cost axis
    wants: the cheap end is where the trade-offs are, and a linear axis
    crushes them against zero. ``frontier`` (default true) draws the line.
    """
    series = _series(spec)
    for i, s in enumerate(series):
        y = _numbers(s.get("values"), f"series[{i}].values")
        x = _numbers(s.get("x"), f"series[{i}].x", expect=y.size)
        colour = PALETTE[i % len(PALETTE)]
        ax.scatter(
            x,
            y,
            s=46,
            color=colour,
            label=literal(s.get("label")) if s.get("label") else None,
            zorder=3,
        )
        for xi, yi, name in zip(x, y, _labels(s, x.size), strict=False):
            place_point_label(ax, name, (xi, yi), fontsize=8)
        if flag(spec, "frontier", True) and x.size:
            # Sort by x ascending, and within one x by y DESCENDING. Sorting on
            # x alone left equal-x points in spec order, so the walk below took
            # whichever came first: with (1, 2) listed before (1, 5) the
            # staircase ran through (1, 2), a point another point beats on the
            # same cost. The same four points in the other order gave a
            # different frontier, which a computed frontier must never do.
            order = np.lexsort((-y, x))
            fx, fy, best = [], [], -np.inf
            for xi, yi in zip(x[order], y[order], strict=False):
                if yi > best:
                    best = yi
                    fx.append(xi)
                    fy.append(yi)
            ax.step(fx, fy, where="post", color=colour, alpha=0.5, linewidth=1.4, zorder=2)
    # As in ``scatter``: a masked point is one the FRONTIER was computed from
    # and the reader cannot see, so the staircase would claim a corner that
    # nothing on the canvas supports.
    if flag(spec, "logx"):
        for i, s in enumerate(series):
            _require_positive(_numbers(s.get("x"), f"series[{i}].x"), f"series[{i}].x", "x")
        ax.set_xscale("log")
        fix_log_ticks(ax, "x")
    _legend(ax, spec, series)


_CORE_RENDERERS = {
    "bar": render_bar,
    "barh": render_barh,
    "line": render_line,
    "scatter": render_scatter,
    "heatmap": render_heatmap,
    "box": render_box,
    "violin": render_violin,
    "hist": render_hist,
    "ecdf": render_ecdf,
    "scaling": render_scaling,
    "area": render_area,
    "forest": render_forest,
    "pareto": render_pareto,
}


# The catalogue, assembled from every family. Each family module owns one
# kind of figure and registers itself here, so adding a chart type is a new
# function plus one dict entry — never an edit to the CLI or the dispatcher.
#
# A duplicate name would silently shadow whichever family imported first, so
# it is caught here rather than discovered when the wrong chart appears.
_FAMILIES = (
    ("core", _CORE_RENDERERS),
    ("compare", COMPARE_RENDERERS),
    ("eval", EVAL_RENDERERS),
    ("dist", DIST_RENDERERS),
    ("extra", EXTRA_RENDERERS),
    ("more", MORE_RENDERERS),
    ("sets", SETS_RENDERERS),
    ("stats", STATS_RENDERERS),
    ("cluster", CLUSTER_RENDERERS),
)

RENDERERS: dict = {}
_OWNER: dict[str, str] = {}
for _family, _members in _FAMILIES:
    for _name, _fn in _members.items():
        if _name in RENDERERS:
            raise RuntimeError(
                f"chart type {_name!r} is registered by both {_OWNER[_name]!r} "
                f"and {_family!r} — one would silently shadow the other"
            )
        RENDERERS[_name] = _fn
        _OWNER[_name] = _family
