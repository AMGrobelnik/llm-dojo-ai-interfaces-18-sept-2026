"""Distribution, relationship and flow renderers — one per chart type.

Same contract as ``chart_renderers``: ``render_x(ax, spec) -> None``, drawing
onto an Axes the caller already owns. Nothing here builds a figure, saves a
file or touches ``plt`` global state, which is what lets ``panel`` compose
any of them into a subplot grid without a special case per type.

This is the family a results section reaches for once the headline bar chart
exists:

* **How a metric is distributed**, not just what its mean was — ``ridgeline``
  across many groups, ``strip`` when n is small enough to show every run.
* **How two measured quantities relate** at a density a plain scatter cannot
  carry — ``bubble`` (a third variable on marker area), ``hexbin`` (tens of
  thousands of points), ``contour`` (a sampled 2-D field), ``corr`` (every
  pairwise correlation at once).
* **Where a budget or a schedule goes** — ``sankey``, ``timeline``.

Tolerant about presentation, strict about data, exactly as the core family
is: a missing colour or title falls back, but every number still enters
through ``chart_common.numbers`` and anything that would make the picture
disagree with its numbers raises ``SpecError`` naming the key and index.

Three defects specific to *these* types are worth naming, because each one
exits zero and produces a confident, plausible, wrong figure:

* a Sankey whose flows do not balance — matplotlib logs that at INFO level
  and draws it anyway, so the arrow widths silently stop adding up;
* a bubble chart that encodes its third variable on marker RADIUS — the
  reader judges area, so a 2x value reads as 4x;
* a correlation matrix on a sequential colour map, where the eye reads
  "large" instead of "positive" and the sign of every cell is lost.

Dependencies are matplotlib, numpy and the standard library. scipy is not a
declared dependency of the deployed image, so the density estimate below is
written out longhand rather than imported.
"""

from __future__ import annotations

import numpy as np
from chart_common import (
    SpecError,
    colour_map,
    flag,
    legend_place,
    number_format,
    number_option,
    type_name,
)
from chart_common import (
    cell_halo as _cell_halo,
)
from chart_common import (
    draw_legend as _legend,
)
from chart_common import (
    ink_for as _ink_for,
)
from chart_common import (
    kde_bandwidth as _bandwidth,
)
from chart_common import (
    kernel_density as _kde,
)
from chart_common import (
    labels_for as _labels,
)
from chart_common import (
    numbers as _numbers,
)
from chart_common import (
    require_positive as _require_positive,
)
from chart_common import (
    scalar_number as _scalar,
)
from chart_common import (
    series_of as _series,
)
from chart_style import (
    DIVERGING_CMAP,
    PALETTE,
    SEQUENTIAL_CMAP,
    fix_log_ticks,
    literal,
    number,
    place_legend,
    place_point_label,
    series_style,
)
from matplotlib.colors import LogNorm, to_rgba
from matplotlib.lines import Line2D
from matplotlib.patheffects import withStroke
from matplotlib.sankey import Sankey

# Points across the shared x-range of a ridgeline. Enough that a mode is a
# curve rather than a polygon, few enough that the kernel sum stays cheap.
_KDE_GRID = 256
# Kernel support: past three bandwidths a Gaussian contributes under 0.5% of
# its mass, so this is where the curve can be cut without visibly clipping it.
_KDE_TAILS = 3.0
# Hexbin cells across the width. Past this the hexagons are sub-pixel at print
# size and the plot degrades into noise that looks like structure.
_MAX_GRIDSIZE = 200
# Contour levels. Past this the labels collide and the fill bands are thinner
# than the lines separating them.
_MAX_LEVELS = 60
# Sankey flow balance, as a fraction of the total input. Loose enough to
# forgive inputs rounded to three significant figures, tight enough that a
# genuinely unbalanced diagram — one whose widths do not add up — is refused.
_SANKEY_REL_TOL = 1e-3


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def _positive_int(spec: dict, key: str, default: int, *, maximum: int) -> int:
    """An integer spec key that becomes an allocation or a label count."""
    value = spec.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpecError(f"'{key}' must be a positive integer, got {value!r}")
    if value > maximum:
        raise SpecError(
            f"'{key}' of {value} is past what a figure can show legibly (max {maximum})"
        )
    return value


def _grouped(spec: dict) -> tuple[list[np.ndarray], list[str]]:
    """Per-group samples and their labels — the shape of a group-wise chart.

    An EMPTY group is rejected rather than skipped. Skipping renumbers every
    row after it, so the label "Ours" ends up against the samples belonging
    to the next group along and the figure is wrong in a way no reader can
    see.
    """
    series = _series(spec)
    data = []
    for i, s in enumerate(series):
        values = _numbers(s.get("values"), f"series[{i}].values")
        data.append(values)
    labels = [literal(s.get("label") or str(i + 1)) for i, s in enumerate(series)]
    return data, labels


def _xy_of(series_entry: dict, index: int) -> tuple[np.ndarray, np.ndarray]:
    """The ``x``/``values`` pair of one series, both gated and length-matched."""
    raw_y = series_entry.get("values") or series_entry.get("y")
    if not raw_y or not series_entry.get("x"):
        raise SpecError(f"series[{index}] needs both 'x' and 'values'")
    y = _numbers(raw_y, f"series[{index}].values")
    x = _numbers(series_entry.get("x"), f"series[{index}].x", expect=y.size)
    return x, y


def _axis_fraction(value: float, axis: np.ndarray, *, log: bool) -> float:
    """Where ``value`` sits along ``axis`` — 0 at the low end, 1 at the high.

    Measured in the axis's OWN scale. On a log axis a fixed fraction of the
    linear range is a sliver at one end and most of the plot at the other, so
    a margin expressed linearly is no margin at all exactly where it matters.
    """
    low, high = float(axis.min()), float(axis.max())
    if log and low > 0:
        low, high, value = (float(np.log10(v)) for v in (low, high, max(value, 1e-300)))
    return (value - low) / (high - low) if high > low else 0.5


# --------------------------------------------------------------------------
# distributions
# --------------------------------------------------------------------------


def render_ridgeline(ax, spec: dict) -> None:
    """Stacked density curves, one row per group, overlapping slightly.

    Each group's distribution is drawn as a filled Gaussian-KDE curve on its
    own baseline, with the rows spaced closer than the curves are tall so a
    tall neighbour rises into the row above. Every row shares one x-axis, so
    a shifted mode or a second bump is read off directly.

    Choose it over ``violin`` or ``box`` once there are more than about six
    groups. A violin grid spends the figure's WIDTH on one strip per group
    and runs out of it; a ridgeline spends the page's height, which is free,
    and stays readable at twenty rows. Choose ``violin``/``box`` instead when
    the groups are few and the quartiles are the finding, ``ecdf`` when the
    comparison is about tails or a threshold, and ``strip`` when n per group
    is small — a density curve drawn through eight points implies a
    smoothness the data does not support.

    Rows are normalised to their own peak, so they compare SHAPE rather than
    frequency. Put n in the group's label when it varies between groups.

    Keys: ``series[].values``, ``series[].label``, ``overlap`` (0 = rows just
    touch, default 0.7), ``bandwidth`` (override Silverman's rule),
    ``medians`` (mark each row's median).
    """
    data, labels = _grouped(spec)
    overlap = _scalar(spec.get("overlap", 0.7), "overlap")
    if not 0.0 <= overlap <= 3.0:
        raise SpecError(
            f"'overlap' is {overlap:g}; it must be between 0 and 3. Past that a "
            "curve reaches over three rows and hides the groups it is drawn on top of."
        )
    widths = [
        _bandwidth(values, f"series[{i}].values", spec.get("bandwidth"))
        for i, values in enumerate(data)
    ]

    # One grid for every row: the whole point of a ridgeline is that the rows
    # share an x-axis, so each curve has to be evaluated on the same points.
    pad = _KDE_TAILS * max(widths)
    grid = np.linspace(
        min(float(v.min()) for v in data) - pad,
        max(float(v.max()) for v in data) + pad,
        _KDE_GRID,
    )
    height = 1.0 + overlap  # peak height in row units

    for i, (values, width) in enumerate(zip(data, widths, strict=True)):
        # Row 0 sits at the TOP and every later row is drawn in front of it,
        # so a peak occludes the tail of the row above — the overlap reads as
        # depth rather than as two curves crossing.
        base = float(len(data) - 1 - i)
        curve = _kde(values, grid, width)
        curve = curve / curve.max() * height
        style = series_style(i)
        z = 2 + 2 * i
        # An opaque backing fill first: at 0.75 alpha alone the row behind
        # shows through and two overlapping colours read as a third one.
        ax.fill_between(grid, base, base + curve, facecolor="white", linewidth=0, zorder=z)
        ax.fill_between(
            grid, base, base + curve, facecolor=style["color"], alpha=0.75, linewidth=0, zorder=z
        )
        ax.plot(grid, base + curve, linewidth=1.2, zorder=z + 1, **style)
        ax.plot(grid, np.full_like(grid, base), color="#B0B0B0", linewidth=0.7, zorder=z + 1)
        if flag(spec, "medians"):
            median = float(np.median(values))
            ax.vlines(
                median,
                base,
                base + float(np.interp(median, grid, curve)),
                color="#1a1a1a",
                linewidth=1.0,
                zorder=z + 1,
            )

    ax.set_yticks(np.arange(len(data))[::-1], labels=labels)
    ax.set_ylim(-0.25, len(data) - 1 + height + 0.15)
    ax.margins(x=0)
    # The rows ARE the y-axis, so a horizontal grid would draw a line through
    # every baseline. The comparison here runs along x instead.
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", visible=True)


def render_strip(ax, spec: dict) -> None:
    """Every raw observation as a jittered point, one column per group.

    Points are spread horizontally by a small random offset so equal values
    do not land on top of each other, and the group mean is drawn as a heavy
    horizontal rule through them. The jitter is seeded, so re-rendering a
    spec gives the same picture.

    Choose it over ``box`` or ``violin`` whenever n per group is small — say
    under about thirty. A box plot of eight seeds draws quartiles estimated
    from two points each and a "distribution" the reader cannot audit; a
    strip shows the eight numbers, so a bimodal split or one dominant
    outlier is visible instead of being smoothed into a summary. Above about
    a hundred points per group the columns saturate into a solid bar and
    ``violin`` or ``ridgeline`` become the honest choice.

    n per group is not annotated: the column IS n, one mark per observation,
    which is the whole reason to reach for this over a box.

    Keys: ``series[].values``, ``series[].label``, ``jitter`` (half-width in
    column units, default 0.16), ``seed`` (jitter RNG, default 0), ``mean``
    (default true).
    """
    data, labels = _grouped(spec)
    jitter = number_option(spec, "jitter", 0.16, minimum=0.0)
    if not 0.0 <= jitter < 0.5:
        raise SpecError(
            f"'jitter' is {jitter:g}; it must be at least 0 and under 0.5. At 0.5 the "
            "columns are half a slot wide and neighbouring groups overlap, so a point "
            "can no longer be attributed to the group it belongs to."
        )
    seed = int(number_option(spec, "seed", 0, integer=True))
    # Only ``seed < 0`` can still fire: ``number_option(..., integer=True)``
    # already refuses floats, bools and strings, but it ACCEPTS negatives and
    # returns a float, so the ``int()`` above is the real cast and the two
    # isinstance arms are unreachable. Do not delete the whole line as dead
    # code — that is the tempting reading and it is wrong: a negative seed
    # would then reach ``np.random.default_rng(-1)``, which raises a bare
    # ValueError("expected non-negative integer") instead of this SpecError
    # naming the key the caller actually wrote.
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise SpecError(f"'seed' must be a non-negative integer, got {seed!r}")
    # Seeded, not global: two renders of one spec must give the same figure,
    # and a jitter drawn from unseeded global state makes them differ.
    rng = np.random.default_rng(seed)
    show_mean = flag(spec, "mean", True)
    positions = np.arange(1, len(data) + 1, dtype=float)

    for i, values in enumerate(data):
        colour = PALETTE[i % len(PALETTE)]
        offsets = rng.uniform(-jitter, jitter, values.size)
        ax.scatter(
            positions[i] + offsets,
            values,
            s=30,
            facecolor=to_rgba(colour, 0.62),
            # An opaque white rim survives the face alpha, so two coincident
            # observations still read as two points rather than one dark one.
            edgecolor="white",
            linewidths=0.5,
            zorder=3,
        )
        if show_mean:
            ax.hlines(
                float(values.mean()),
                positions[i] - 0.3,
                positions[i] + 0.3,
                color="#1a1a1a",
                linewidth=2.0,
                zorder=4,
                # Labelled once: the rule is one glyph with one meaning, and a
                # legend entry per group would restate the x-axis.
                label="Mean" if i == 0 else None,
            )

    ax.set_xticks(positions, labels=labels)
    ax.set_xlim(0.5, len(data) + 0.5)
    if show_mean:
        # Headroom before the legend, for the same reason ``draw_legend`` buys
        # it: ``loc="best"`` only avoids the data when somewhere is free.
        low, high = ax.get_ylim()
        ax.set_ylim(low, low + (high - low) * 1.14)
        place_legend(ax, loc=legend_place(spec) or "best")


# --------------------------------------------------------------------------
# relationships
# --------------------------------------------------------------------------


def render_bubble(ax, spec: dict) -> None:
    """Scatter with a third variable encoded as marker AREA, plus a size key.

    Area is proportional to the value and anchored at zero — twice the value
    is twice the ink. The alternative, scaling the radius, is the standard
    way this chart lies: area grows as the square, so a 2x value draws 4x the
    marker and the reader, who judges area, reads a difference that is not
    there. The scale is shared across every series, so bubbles are comparable
    between them, and the size legend prints real values from the data.

    Choose it when a scatter is already the right figure and there is a third
    per-point quantity worth showing — cost against accuracy with model size
    on the marker, say. Prefer a colour scale (``hexbin``, ``contour``) when
    the third variable is the FINDING rather than context: area is read to
    perhaps 20% accuracy, so a bubble chart is a qualifier, not a
    measurement. Prefer a panel of two scatters when the size variable spans
    more than about two orders of magnitude — at 1% of the maximum a bubble
    is a dot, and honest as that is, nobody can read it.

    Keys: ``series[].x``, ``series[].values``, ``series[].sizes``,
    ``series[].categories`` (per-point annotations), ``size_label`` (the size
    legend's heading), ``max_area`` (points² for the largest bubble, default
    620), ``size_legend_loc``.
    """
    series = _series(spec)
    max_area = _scalar(spec.get("max_area", 620), "max_area")
    if not 20.0 <= max_area <= 4000.0:
        raise SpecError(f"'max_area' is {max_area:g} points²; use something in 20..4000")

    parsed = []
    for i, entry in enumerate(series):
        x, y = _xy_of(entry, i)
        sizes = _numbers(entry.get("sizes"), f"series[{i}].sizes", expect=y.size)
        # Zero area is an invisible marker and a negative one is meaningless;
        # both would drop a point from a figure that still claims to show it.
        bad = [j for j, v in enumerate(sizes) if v <= 0]
        if bad:
            raise SpecError(
                f"series[{i}].sizes[{bad[0]}] is {sizes[bad[0]]:g}. Marker area encodes "
                "magnitude, so a value of zero or less has no bubble to draw and the "
                "point silently disappears. Shift the variable so it is positive, or "
                'plot it on an axis instead with "type": "scatter".'
            )
        parsed.append((x, y, sizes, entry))

    # One scale across every series. Normalising per series would draw two
    # different values at the same size, which is the whole failure this
    # chart type has to avoid.
    largest = max(float(sizes.max()) for _, _, sizes, _ in parsed)

    for i, (x, y, sizes, entry) in enumerate(parsed):
        colour = PALETTE[i % len(PALETTE)]
        areas = max_area * sizes / largest
        ax.scatter(
            x,
            y,
            s=areas,
            # A translucent face with an OPAQUE rim: passing ``alpha`` would
            # fade the rim too, and overlapping bubbles then merge into one
            # shape with no visible boundary.
            facecolor=to_rgba(colour, 0.42),
            edgecolor=colour,
            linewidths=1.1,
            zorder=3,
            label=literal(entry.get("label")) if entry.get("label") else None,
        )
        if entry.get("categories"):
            for xi, yi, area, name in zip(x, y, areas, _labels(entry, x.size), strict=True):
                # Inside the bubble when it is wide enough to hold the name,
                # otherwise just above it. Centred unconditionally, a name on a
                # small bubble covers the mark it identifies.
                diameter = float(np.sqrt(area))
                fits = diameter > 4.7 * len(name) + 4.0
                if fits:
                    # Centred INSIDE its own disc, which is where it belongs and
                    # where no nudge could improve it — so it is not registered.
                    ax.annotate(
                        name,
                        (xi, yi),
                        textcoords="offset points",
                        xytext=(0, 0),
                        ha="center",
                        va="center",
                        fontsize=7.5,
                        zorder=4,
                    )
                else:
                    # Too small to hold the name, so the name goes above the
                    # disc — and THAT is the one that lands on a neighbour.
                    # Registered so ``fit_point_labels`` can move it; that only
                    # became useful once the clearance test measured each marker
                    # against its own radius (a bubble field runs 4 px to 88 px,
                    # and one radius for the axes left no position measuring
                    # clean, so the nudger kept every first guess).
                    place_point_label(
                        ax,
                        name,
                        (xi, yi),
                        offset=(0, diameter / 2 + 2.5),
                        ha="center",
                        va="bottom",
                        fontsize=7.5,
                        zorder=4,
                    )

    # Colour legend first, then re-parent it: a second ``ax.legend`` call
    # REPLACES the first, so without ``add_artist`` the series names vanish
    # the moment the size key is drawn.
    _legend(ax, spec, series)
    existing = ax.get_legend()
    if existing is not None:
        # One fixed swatch size for the colour key. Left alone it inherits a
        # size from the data, so the colour legend looks like part of the size
        # scale and reads as a value it does not have.
        for handle in existing.legend_handles:
            handle.set_sizes([70])
        ax.add_artist(existing)

    smallest = min(float(sizes.min()) for _, _, sizes, _ in parsed)
    # Round the midpoint to two significant figures — it is a scale marker,
    # not a measurement, and "154" reads as a data point while "150" reads as
    # a ruler. The endpoints stay exact: they ARE in the data.
    midpoint = float(f"{(largest + smallest) / 2.0:.2g}")
    keys = {largest, smallest}
    if smallest < midpoint < largest:
        keys.add(midpoint)
    keys = sorted(keys, reverse=True)
    handles = [
        Line2D(
            [],
            [],
            linestyle="none",
            marker="o",
            # ``scatter`` sizes markers by AREA in points² and ``Line2D`` by
            # diameter in points, so the square root is what makes the key
            # the same size as the bubbles it explains.
            markersize=np.sqrt(max_area * value / largest),
            markerfacecolor=to_rgba(PALETTE[0], 0.42),
            markeredgecolor=PALETTE[0],
            markeredgewidth=1.1,
            label=f"{value:.3g}",
        )
        for value in keys
    ]
    place_legend(
        ax,
        handles=handles,
        title=literal(spec.get("size_label") or "Size"),
        # Outside the axes by default. Inside, a key whose largest entry is a
        # 25-point circle covers a corner of the data, and constrained layout
        # reserves real space for it out here.
        loc=spec.get("size_legend_loc") or "center left",
        bbox_to_anchor=None if spec.get("size_legend_loc") else (1.02, 0.5),
        labelspacing=max(1.0, float(np.sqrt(max_area)) / 16.0),
        handletextpad=1.1,
        borderpad=0.8,
        alignment="left",
    )


def render_hexbin(ax, spec: dict) -> None:
    """Hexagonal density bins with a labelled colourbar.

    Counts points into a hexagonal grid and colours each cell by how many
    landed in it. Hexagons rather than squares because each has six equidistant
    neighbours instead of four plus four diagonals, so a diagonal ridge in the
    data does not come out as a staircase.

    Choose it once a scatter has become a solid blob — past roughly two
    thousand points, overplotting hides the mode and the reader cannot tell a
    dense core from a saturated one. It also fixes the quieter failure of a
    big scatter: with alpha low enough to see structure, genuine outliers
    fade to invisible, while here a lone point is a cell of count 1 and
    stays on the map. Below that prefer ``scatter``, which keeps individual
    points identifiable, or ``contour`` when the field is sampled on a grid
    rather than observed.

    Keys: ``series[0].x``, ``series[0].values``, ``gridsize`` (cells across,
    default 40), ``cbar_label``, ``log_counts`` (log colour scale for a
    heavy-tailed density), ``mincnt`` (cells below this stay blank, default 1), ``cmap``.
    """
    series = _series(spec)
    if len(series) > 1:
        raise SpecError(
            f"'series' has {len(series)} entries but a hexbin can only show one. Two "
            "density maps drawn over each other are opaque — the top one hides the "
            'bottom one and neither count can be read. Use "type": "panel" with one '
            "hexbin per panel, sharing 'xlim' and 'ylim' so they compare."
        )
    x, y = _xy_of(series[0], 0)
    gridsize = _positive_int(spec, "gridsize", 40, maximum=_MAX_GRIDSIZE)
    mincnt = _positive_int(spec, "mincnt", 1, maximum=1_000_000)

    image = ax.hexbin(
        x,
        y,
        gridsize=gridsize,
        cmap=colour_map(spec, SEQUENTIAL_CMAP),
        # Cells with nothing in them are left BLANK rather than painted at the
        # bottom of the colour map. Painted, an empty region is the same dark
        # navy as a genuine count of one and the plot claims coverage it does
        # not have.
        mincnt=mincnt,
        # A hairline between cells; without it adjacent hexagons of similar
        # count merge into a single blob and the binning is invisible.
        linewidths=0.2,
        edgecolors="face",
        # LogNorm rather than hexbin's ``bins="log"``: the colourbar then
        # carries real counts instead of log10 units nobody can convert back.
        norm=LogNorm() if spec.get("log_counts") else None,
    )
    bar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    # Always labelled. An unlabelled colourbar is a legend with no key: the
    # reader can see that one region is darker without knowing by how much.
    bar.set_label(literal(spec.get("cbar_label") or "Count"))
    ax.grid(visible=False)


def render_contour(ax, spec: dict) -> None:
    """Filled contours of a 2-D field, with the levels labelled on the lines.

    Takes a ``z`` matrix sampled over the ``x`` and ``y`` axes and draws it as
    bands of constant value, with thin lines between the bands carrying their
    numeric level. The labels are what make this a measurement rather than a
    picture: from the fill alone a reader can see where the minimum is but
    not what it is worth.

    Choose it for a loss surface or a hyperparameter landscape — anything
    evaluated on a grid, where the question is where the optimum sits and how
    sharp it is. A ``heatmap`` of the same matrix shows the values as cells and
    is better when the grid is coarse and each cell is a distinct experiment;
    contours are better when the grid is fine enough to interpolate and the
    shape of the surface — a long flat valley versus a narrow basin — is the
    finding. Use ``hexbin`` instead when the field is not sampled but
    observed, i.e. you have points rather than a matrix.

    Keys: ``x``, ``y``, ``z`` (rows indexed by ``y``, columns by ``x``),
    ``levels`` (a count, default 12, or an explicit increasing list),
    ``cbar_label``, ``cmap``, ``labels`` (inline level labels, default true),
    ``logx``/``logy`` for a swept axis spanning decades.
    """
    x = _numbers(spec.get("x"), "x")
    y = _numbers(spec.get("y"), "y")
    raw = spec.get("z")
    if not isinstance(raw, list) or not raw or not all(isinstance(row, list) for row in raw):
        raise SpecError("'z' must be a non-empty list of equal-length rows")
    if len(raw) != y.size:
        raise SpecError(
            f"'z' has {len(raw)} rows but 'y' has {y.size} entries. Each row of z is "
            "one value of y, so they have to match — otherwise the field is drawn "
            "against coordinates it was not measured at."
        )
    field = np.vstack([_numbers(row, f"z[{r}]", expect=x.size) for r, row in enumerate(raw)])
    # contourf reads x and y as coordinates and does not check them. Handed a
    # descending or repeated axis it still draws something, with the cells
    # folded back over each other.
    for name, axis in (("x", x), ("y", y)):
        if axis.size < 2 or np.any(np.diff(axis) <= 0):
            raise SpecError(
                f"'{name}' must be at least two values in strictly increasing order — "
                "a contour grid has no meaning if its coordinates repeat or go backwards."
            )

    raw_levels = spec.get("levels", 12)
    if isinstance(raw_levels, list):
        levels = _numbers(raw_levels, "levels")
        if levels.size < 2 or np.any(np.diff(levels) <= 0):
            raise SpecError("'levels' must be at least two values in strictly increasing order")
        # contourf fills only BETWEEN the levels it is given (extend="neither"
        # by default), so everything outside them is left as bare page —
        # indistinguishable from no data. Levels of 2.6..3.2 over a field
        # running 2.3..4.6 blanked 70% of the plot area, the basin holding the
        # optimum included, under a colourbar that read 2.6..3.2.
        outside = int(((field < levels[0]) | (field > levels[-1])).sum())
        if outside:
            raise SpecError(
                f"'levels' runs {levels[0]:g}..{levels[-1]:g} but 'z' runs "
                f"{field.min():g}..{field.max():g}, so {outside} of {field.size} grid points "
                "fall outside them and would be left unfilled — bare page a reader cannot "
                "tell from missing data, under a colourbar stating a range the field does "
                "not have. Widen the levels to span z, or give a count instead of a list."
            )
    else:
        levels = _positive_int(spec, "levels", 12, maximum=_MAX_LEVELS)

    filled = ax.contourf(x, y, field, levels=levels, cmap=colour_map(spec, SEQUENTIAL_CMAP))
    bar = ax.figure.colorbar(filled, ax=ax, fraction=0.046, pad=0.03)
    bar.set_label(literal(spec.get("cbar_label") or "Value"))

    lines = ax.contour(x, y, field, levels=filled.levels, colors="#1a1a1a", linewidths=0.6)
    if spec.get("labels", True):
        texts = ax.clabel(lines, inline=True, fontsize=8, fmt="%.3g")
        for text in texts:
            # A white halo, because the labels sit on the fill and the fill runs
            # from near-black to bright yellow. Any single ink colour is
            # illegible at one end of that range; an outline is legible at both.
            text.set_path_effects([withStroke(linewidth=2.2, foreground="white")])
            # clabel places a label wherever its contour has room, edges
            # included, and the axes then clips it — the figure came out with
            # "3." and half a digit hanging off the right-hand side. A label
            # that close to the boundary is dropped instead; the colourbar
            # still carries its value.
            at_x, at_y = text.get_position()
            near_edge = not (
                0.05 <= _axis_fraction(at_x, x, log=flag(spec, "logx")) <= 0.95
                and 0.05 <= _axis_fraction(at_y, y, log=flag(spec, "logy")) <= 0.95
            )
            if near_edge:
                text.remove()

    if flag(spec, "logx"):
        _require_positive(x, "x", "x")
        ax.set_xscale("log")
        fix_log_ticks(ax, "x")
    if flag(spec, "logy"):
        _require_positive(y, "y", "y")
        ax.set_yscale("log")
        fix_log_ticks(ax, "y")
    ax.grid(visible=False)


def render_corr(ax, spec: dict) -> None:
    """Correlation matrix on a diverging colour map centred at zero.

    Variable names run along both axes and the colour map is symmetric about
    zero on a fixed −1..1 range, so the midpoint of the scale is r = 0, one
    hue means positive and the other negative, and the same colour means the
    same correlation in every figure of the paper. A sequential map here —
    the matplotlib default — reads as "large" rather than "positive", which
    loses the sign of every cell, and a map auto-scaled to the data makes
    r = 0.15 look strong in one figure and weak in the next.

    Choose it as the survey step before a modelling claim: which of these
    measurements move together, across all pairs at once. Choose ``scatter``
    with ``fit`` when the claim is about ONE pair — a correlation coefficient
    hides the shape it came from, and Anscombe's quartet is four different
    scatters with the same r. Choose ``heatmap`` for any matrix that is not a
    correlation: an ablation grid, a confusion matrix, a cost table.

    Keys: ``matrix`` (square), ``labels`` (variable names, used on both
    axes), ``lower_only`` (hide the redundant upper triangle), ``annotate``
    (default true), ``fmt`` (default ".2f"), ``cbar_label``.

    ``cmap`` overrides the map, though the diverging default is already
    centred on zero, which is what a correlation matrix wants.
    """
    raw = spec.get("matrix")
    if not isinstance(raw, list) or not raw or not all(isinstance(row, list) for row in raw):
        raise SpecError("'matrix' must be a non-empty list of equal-length rows")
    size = len(raw)
    matrix = np.vstack([_numbers(row, f"matrix[{r}]", expect=size) for r, row in enumerate(raw)])
    out_of_range = np.argwhere(np.abs(matrix) > 1.0)
    if out_of_range.size:
        r, c = (int(v) for v in out_of_range[0])
        # ``.12g``, not ``g``: six significant digits rounded 1.0000001 — a
        # value this check has just REFUSED — to "1", so the message read
        # "matrix[0][1] is 1, outside −1..1" and named a number that is inside
        # the range it quotes. The cell that is wrong then looks fine.
        raise SpecError(
            f"matrix[{r}][{c}] is {matrix[r, c]:.12g}, outside −1..1, so it is not a "
            'correlation. If this is a covariance or a delta matrix, use "type": '
            '"heatmap" with "diverging": true, which scales the colour map to the data.'
        )

    lower_only = flag(spec, "lower_only")
    if lower_only and not np.allclose(matrix, matrix.T, atol=1e-6):
        r, c = (int(v) for v in np.argwhere(~np.isclose(matrix, matrix.T, atol=1e-6))[0])
        raise SpecError(
            f"'lower_only' hides the upper triangle, but matrix[{r}][{c}] is "
            f"{matrix[r, c]:g} while matrix[{c}][{r}] is {matrix[c, r]:g} — the halves "
            "differ, so hiding one would drop numbers the reader has no way to know "
            "existed. Drop 'lower_only', or make the matrix symmetric."
        )
    shown = matrix
    if lower_only:
        # The diagonal stays: it is where a reader's eye tracks a variable from
        # the row label to the column label.
        shown = np.ma.masked_where(np.triu(np.ones_like(matrix, dtype=bool), k=1), matrix)

    image = ax.imshow(shown, cmap=colour_map(spec, DIVERGING_CMAP), vmin=-1.0, vmax=1.0)
    bar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    bar.set_label(literal(spec.get("cbar_label") or "Correlation (r)"))
    bar.set_ticks([-1.0, -0.5, 0.0, 0.5, 1.0])

    names = _labels({"categories": spec.get("labels")}, size)
    ax.set_xticks(np.arange(size), labels=names)
    ax.set_yticks(np.arange(size), labels=names)
    if sum(len(n) for n in names) > 40:
        ax.tick_params(axis="x", labelrotation=35)
        for label in ax.get_xticklabels():
            label.set_ha("right")
    ax.grid(visible=False)

    if flag(spec, "annotate", True):
        fmt = number_format(spec, "fmt", ".2f")
        for r in range(size):
            for c in range(size):
                if lower_only and c > r:
                    continue
                ax.text(
                    c,
                    r,
                    number(matrix[r, c], fmt),
                    ha="center",
                    va="center",
                    fontsize=8,
                    # Asked of the colour map rather than of the value: on a
                    # diverging map both ENDS are dark and the middle is pale,
                    # so a rule based on the value alone is wrong at one end.
                    color=_ink_for(image, matrix[r, c]),
                    path_effects=_cell_halo(_ink_for(image, matrix[r, c])),
                )


# --------------------------------------------------------------------------
# flows
# --------------------------------------------------------------------------


def render_sankey(ax, spec: dict) -> None:
    """Flows between stages, drawn at widths proportional to their magnitude.

        Each stage is a set of flows: positive into the stage, negative out of
        it. Stages chain by naming an earlier one and the pair of flow indices
        that join, so the output of one becomes the input of the next and the
        band keeps its width across the join.

        Choose it when the finding is where a total GOES — a token or dollar
        budget split across pipeline phases, a corpus shrinking through
        filtering stages, a cohort of tasks ending in success, timeout or refusal.
        A stacked ``bar`` shows the same split but not the routing, so it cannot
        say which part of stage one became which part of stage two. Prefer
        ``bar``/``area`` when there is only one split to show: a one-stage Sankey
        is a costly way to draw three numbers.

        The flows are checked to balance before anything is drawn. matplotlib
        logs an unbalanced system at INFO level and renders it anyway, which
        yields a diagram whose widths do not add up and whose arrows still look
        convincing.

        Keys: ``stages[].flows`` (+ in, − out), ``stages[].labels`` (one per
        flow), ``stages[].orientations`` (0 straight, 1 up, −1 down),
        ``stages[].label`` (the stage's name, shown in the legend),
        ``stages[].prior`` and ``stages[].connect`` ([flow of that prior stage,
        flow of this one]), ``unit`` (appended to every quantity),
        ``value_format`` (default "%g"), ``trunklength``, and ``scale`` (flow
    units per drawn unit; derived from the totals when absent, which is what
    makes any unit work — set it only to match two sankeys to each other).
    """
    stages = spec.get("stages")
    if not isinstance(stages, list) or not stages:
        raise SpecError(
            "'stages' must be a non-empty list. Each stage is "
            '{"flows": [+in, -out, ...], "labels": [...], "orientations": [...]}'
        )

    # ``literal(None)`` is the string "None", so a null unit would print every
    # quantity as "120None" — a falsy unit is no unit, not the word.
    unit = literal(spec.get("unit") or "")
    value_format = spec.get("value_format", "%g")
    if not isinstance(value_format, str):
        raise SpecError(f"'value_format' must be a format string, got {value_format!r}")
    try:
        value_format % 1.0
    except (TypeError, ValueError) as exc:
        raise SpecError(
            f"'value_format' {value_format!r} is not a number format — {exc}. Use "
            'something like "%g" or "%.1f".'
        ) from exc

    parsed = []
    for i, stage in enumerate(stages):
        if not isinstance(stage, dict):
            raise SpecError(f"stages[{i}] must be an object, got {type_name(stage)}")
        flows = _numbers(stage.get("flows"), f"stages[{i}].flows")
        if flows.size < 2:
            raise SpecError(f"stages[{i}].flows needs at least one input and one output")
        # In must equal out. Unbalanced, the widths on one side of the body do
        # not sum to the widths on the other and the diagram misstates the very
        # thing it exists to show.
        inflow = float(flows[flows > 0].sum())
        if inflow <= 0:
            raise SpecError(
                f"stages[{i}].flows has no positive value. Flows into a stage are "
                "positive and flows out are negative, so a stage with no input has "
                "nothing to route."
            )
        imbalance = float(flows.sum())
        if abs(imbalance) > _SANKEY_REL_TOL * inflow:
            raise SpecError(
                f"stages[{i}].flows sums to {imbalance:g}: {inflow:g} in against "
                f"{-float(flows[flows < 0].sum()):g} out. A Sankey's widths only add up "
                "when a stage conserves what enters it — add the missing flow (losses, "
                "rounding, an 'other' bucket) explicitly rather than leaving the "
                "difference implied."
            )
        # ``labels_for`` escapes as it goes; escaping again would print the
        # backslash it added.
        names = _labels({"categories": stage.get("labels")}, flows.size)

        # Read without a default: the two-arg ``dict.get`` does not type-check
        # here (no overload matches a list default against this mapping), and
        # the explicit None branch says the same thing more plainly.
        orientations = stage.get("orientations")
        if orientations is None:
            orientations = [0] * flows.size
        if not isinstance(orientations, list) or len(orientations) != flows.size:
            raise SpecError(
                f"stages[{i}].orientations must be a list of {flows.size} values, one "
                f"per flow, got {orientations!r}"
            )
        for j, orient in enumerate(orientations):
            if isinstance(orient, bool) or orient not in (-1, 0, 1):
                raise SpecError(
                    f"stages[{i}].orientations[{j}] is {orient!r}; it must be 0 "
                    "(straight through), 1 (up) or −1 (down)."
                )
        parsed.append((flows, names, list(orientations), stage))

    total = float(parsed[0][0][parsed[0][0] > 0].sum())
    # Sankey's default scale of 1.0 assumes the inputs sum to about 1. Left at
    # the default, flows measured in millions of tokens draw a body a million
    # units wide inside an axes 2 units across — the diagram is simply not on
    # the canvas. Deriving it from the data is what makes any unit work.
    scale = number_option(spec, "scale", 1.0 / total, minimum=1e-12)
    tolerance = total * 1e-6

    joins: list[tuple[int, tuple[int, int]] | None] = [None] * len(parsed)
    for i, (flows, _names, _orientations, stage) in enumerate(parsed):
        # A flow far smaller than the total is dropped by matplotlib without
        # an error — its label is placed, its band is not — so the figure
        # names a stream that is not drawn.
        tiny = [j for j, v in enumerate(flows) if abs(v) <= tolerance]
        if tiny:
            raise SpecError(
                f"stages[{i}].flows[{tiny[0]}] is {flows[tiny[0]]:g}, negligible against "
                f"the {total:g} flowing through the diagram. matplotlib drops a band that "
                "small but still writes its label, leaving a name pointing at nothing. "
                "Merge it into a neighbouring flow."
            )
        if i == 0:
            continue  # the first stage has nothing to join to
        connect = stage.get("connect")
        prior = stage.get("prior", i - 1)
        # Whatever survives the checks below is what gets drawn — re-reading
        # the spec at draw time is how a validated value and a used value come
        # to differ.
        if connect is None:
            raise SpecError(
                f"stages[{i}] needs 'connect': [flow of the prior stage, flow of this "
                "stage] — the pair of flows that are the same stream, so the band can "
                "carry its width across the join."
            )
        if (
            not isinstance(connect, list)
            or len(connect) != 2
            or any(isinstance(v, bool) or not isinstance(v, int) for v in connect)
        ):
            raise SpecError(
                f"stages[{i}].connect must be two integer flow indices, got {connect!r}"
            )
        if not isinstance(prior, int) or isinstance(prior, bool) or not 0 <= prior < i:
            raise SpecError(
                f"stages[{i}].prior is {prior!r}; it must index a stage already drawn (0..{i - 1})"
            )
        out_index, in_index = connect
        if not 0 <= out_index < parsed[prior][0].size:
            raise SpecError(
                f"stages[{i}].connect[0] is {out_index}, but stages[{prior}] has "
                f"{parsed[prior][0].size} flows"
            )
        if not 0 <= in_index < flows.size:
            raise SpecError(
                f"stages[{i}].connect[1] is {in_index}, but this stage has {flows.size} flows"
            )
        joined = float(parsed[prior][0][out_index] + flows[in_index])
        if abs(joined) > tolerance:
            raise SpecError(
                f"stages[{i}] joins stages[{prior}] flow {out_index} "
                f"({parsed[prior][0][out_index]:g}) to its own flow {in_index} "
                f"({flows[in_index]:g}). The two are the same stream seen from either "
                "side, so they must be equal and opposite — as given, the band would "
                f"change width by {abs(joined):g} across the join."
            )
        joins[i] = (prior, (out_index, in_index))

    diagram = Sankey(
        ax=ax,
        scale=scale,
        unit=unit,
        format=value_format,
        gap=0.28,
        radius=0.08,
        shoulder=0.02,
        offset=0.22,
        tolerance=tolerance,
    )
    trunklength = _scalar(spec.get("trunklength", 1.2), "trunklength")
    for i, (flows, names, orientations, stage) in enumerate(parsed):
        colour = PALETTE[i % len(PALETTE)]
        join = joins[i]
        if join is not None:
            # The joined pair is ONE band. Labelled from both sides it prints
            # its magnitude twice, overlapping, at the seam — so the incoming
            # side is silenced here rather than trusted to the spec. ``None``
            # and not "": an empty label still prints the quantity.
            names = list(names)
            names[join[1][1]] = None
        diagram.add(
            flows=list(flows),
            labels=names,
            orientations=orientations,
            prior=join[0] if join else None,
            connect=join[1] if join else (0, 0),
            trunklength=trunklength,
            facecolor=to_rgba(colour, 0.55),
            edgecolor=colour,
            linewidth=1.0,
            # The stage's name goes in the LEGEND, not inside the body.
            # ``patchlabel`` writes it at the centre of the patch, where the
            # trunk's own flow labels already are: "Retrieval" landed on top of
            # "Corpus ingested 120 M" and neither could be read.
            label=literal(stage["label"]) if stage.get("label") else None,
        )
    diagram.finish()
    # ``finish`` fits the axes to the flow paths and the label ANCHORS, not to
    # the labels themselves, so a long name at a left- or right-hand tip runs
    # off the canvas. Widening the view is what keeps it on the page — but the
    # widening only sticks after the aspect is made adjustable by BOX. Left on
    # ``finish``'s datalim setting, matplotlib restores whatever limits the
    # aspect wants and discards these ("Ignoring fixed x limits…"), which is
    # how "Verified answers" ended up cut off at the right-hand edge.
    ax.set_aspect("equal", adjustable="box")
    low, high = ax.get_xlim()
    ax.set_xlim(low - 0.18 * (high - low), high + 0.18 * (high - low))
    # No axes: a Sankey's coordinates are layout, not data, so ticks on them
    # would invite a reading that means nothing.
    ax.set_axis_off()
    _legend(ax, spec, [{"label": stage.get("label")} for *_, stage in parsed], headroom=False)


def render_timeline(ax, spec: dict) -> None:
    """Gantt-style horizontal spans, one row per task.

    Each task is a bar from its start to its end on a shared numeric axis,
    rows in the order given, top to bottom. Tasks sharing a ``group`` share a
    colour and the groups are named in a legend.

    Choose it for a schedule — the phases of an experiment, the stages of a
    run, what overlapped with what and what was blocking. The reading it
    supports and a bar chart of durations does not is CONCURRENCY: two bars
    at the same x-range ran together, a gap is idle time, and the critical
    path is the chain with no slack. Use ``barh`` instead when only the
    durations matter and nothing overlaps, and ``area`` when the question is
    how much of a resource was in use over time rather than which task held it.

    The axis is numeric — hours, days, steps from the start — so put the unit
    in ``xlabel``. Calendar dates are not parsed; convert them to an offset
    first, which is what makes the spans comparable anyway.

    Keys: ``tasks[].label``, ``tasks[].start``, ``tasks[].end``,
    ``tasks[].group``, ``marker`` (a reference line — a deadline, a release),
    ``marker_label``.
    """
    tasks = spec.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        raise SpecError(
            "'tasks' must be a non-empty list. Each task is "
            '{"label": "Pretraining", "start": 0, "end": 14}'
        )

    groups: list[str] = []
    for i, task in enumerate(tasks):
        if not isinstance(task, dict):
            raise SpecError(f"tasks[{i}] must be an object, got {type_name(task)}")
        group = task.get("group")
        if group is not None and not isinstance(group, str):
            raise SpecError(f"tasks[{i}].group must be a string, got {group!r}")
        if isinstance(group, str) and group not in groups:
            groups.append(group)

    seen_groups: set[str] = set()
    for i, task in enumerate(tasks):
        start, end = _numbers([task.get("start"), task.get("end")], f"tasks[{i}] span", expect=2)
        # A zero-width bar draws nothing at all, so the row keeps its label and
        # loses its data — the schedule then shows a task that never ran.
        if end <= start:
            raise SpecError(
                f"tasks[{i}] runs from {start:g} to {end:g}, so it has no duration to "
                "draw and the row would come out blank. 'end' must be after 'start'; "
                "give a milestone a short nominal duration instead."
            )
        group = task.get("group")
        colour = PALETTE[groups.index(group) % len(PALETTE)] if group else PALETTE[0]
        # Label the FIRST bar of each group only: one legend entry per group,
        # not one per row, which would just restate the y-axis.
        label = None
        if group and group not in seen_groups:
            seen_groups.add(group)
            label = literal(group)
        ax.barh(
            i,
            end - start,
            left=start,
            height=0.62,
            facecolor=to_rgba(colour, 0.85),
            edgecolor=colour,
            linewidth=0.8,
            label=label,
            zorder=3,
        )

    if spec.get("marker") is not None:
        ax.axvline(
            _scalar(spec["marker"], "marker"),
            color="#333333",
            linestyle="--",
            linewidth=1.2,
            zorder=4,
            label=literal(spec["marker_label"]) if spec.get("marker_label") else None,
        )

    names = [literal(task.get("label") or str(i + 1)) for i, task in enumerate(tasks)]
    ax.set_yticks(np.arange(len(tasks)), labels=names)
    ax.set_ylim(len(tasks) - 0.4, -0.6)  # first task at the top, as a schedule reads
    ax.margins(x=0.02)
    # Time runs along x, so that is the axis a reader measures against.
    ax.grid(axis="x", visible=True)
    ax.grid(axis="y", visible=False)

    entries = [{"label": g} for g in groups]
    if spec.get("marker_label"):
        entries.append({"label": spec["marker_label"]})
    if len(entries) == 1 and not groups:
        # ``draw_legend`` skips a single entry because it usually restates the
        # y-label. A lone reference line is the exception: nothing else on the
        # figure says what the dashed rule means.
        place_legend(ax, loc=legend_place(spec) or "best")
    else:
        _legend(ax, spec, entries, headroom=False)


DIST_RENDERERS = {
    "ridgeline": render_ridgeline,
    "strip": render_strip,
    "bubble": render_bubble,
    "hexbin": render_hexbin,
    "contour": render_contour,
    "corr": render_corr,
    "sankey": render_sankey,
    "timeline": render_timeline,
}
