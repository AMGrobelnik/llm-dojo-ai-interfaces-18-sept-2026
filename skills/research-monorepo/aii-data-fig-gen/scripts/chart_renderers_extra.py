"""Schedules, joint distributions, diagnostics, composition, attrition,
nominal grids and vector fields.

The types here fill gaps the other families leave: figures that are common
in a methods or appendix section rather than in the results table, but that
get hand-rolled every time because no generator covers them.
"""

from __future__ import annotations

import numpy as np
from chart_common import (
    SpecError,
    colour_map,
    draw_legend,
    flag,
    ink_on,
    labels_for,
    number_option,
    numbers,
    require_annotations_fit,
    require_positive,
    series_of,
)
from chart_style import (
    PALETTE,
    SEQUENTIAL_CMAP,
    content_places,
    literal,
    place_legend,
    series_style,
)
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch


def render_step(ax, spec: dict) -> None:
    """A piecewise-constant series — the value holds, then jumps.

    For anything that changes at discrete moments and is CONSTANT between
    them: a learning-rate schedule, a batch-size ramp, a policy or config
    that switched at a known step. Choose over ``line``, which draws a
    sloped segment between points and so implies the value passed through
    every intermediate level — for a schedule that is simply false, and a
    reader will take the slope literally. ``where`` may be ``post`` (the
    default, value holds forward from each x), ``pre`` (it holds backward
    into each x), or ``mid`` (it changes halfway between them).

    ``markers`` puts a dot at each actual sample, which separates the measured
    points from the held value between them.
    """
    series = series_of(spec)
    where = spec.get("where", "post")
    if where not in ("post", "pre", "mid"):
        raise SpecError(f"'where' must be post, pre or mid, got {where!r}")
    # Read BEFORE the loop: the axis was switched to log after every series had
    # been drawn, so nothing was in a position to refuse a zero. `line`,
    # `scatter`, `scaling` and `pareto` all call `require_positive` and `step`
    # did not — measured, a step series containing 0.0 with `logy: true` drew
    # at exit 0 with matplotlib masking the point, which is the exact silent
    # data loss SKILL.md says this check exists to stop.
    log_y = flag(spec, "logy")
    for i, s in enumerate(series):
        y = numbers(s.get("values"), f"series[{i}].values")
        if log_y:
            require_positive(y, f"series[{i}].values", "y")
        raw_x = s.get("x") or spec.get("x")
        x = numbers(raw_x, f"series[{i}].x", expect=y.size) if raw_x else np.arange(y.size)
        style = series_style(i)
        label = literal(s["label"]) if s.get("label") else None
        ax.step(x, y, where=where, label=label, **style)
        if flag(spec, "markers"):
            ax.plot(x, y, "o", color=style["color"], markersize=4)
    if log_y:
        ax.set_yscale("log")
    draw_legend(ax, spec, series)


def render_hist2d(ax, spec: dict) -> None:
    """A joint distribution of two variables as a binned density grid.

    For the SHAPE of a relationship when there are enough points that a
    scatter is a solid blob — correlation structure, ridges, multiple
    clusters. Choose over ``scatter`` past roughly two thousand points, and
    over ``hexbin`` when the axes are naturally rectangular (integer counts,
    binned scores) so square cells align with the data rather than cutting
    across it. Both axes are binned, so unlike a scatter no point can hide
    another.

    ``cmap`` overrides the sequential default; the rainbow family is refused,
    because density is the only thing this figure encodes.
    """
    series = series_of(spec)
    s = series[0]
    x = numbers(s.get("x"), "series[0].x")
    y = numbers(s.get("values") or s.get("y"), "series[0].values", expect=x.size)
    bins = spec.get("bins", 40)
    # Only the minimum is checked here. The shared `bins` gate in chart_validate
    # already refuses non-integers, bools and anything below 1, and it runs
    # first — so a bool or a float never reaches this line, and 1 is the single
    # value this adds. A 1x1 hist2d is one box holding every point, which is a
    # colourbar and no information.
    if bins < 2:
        raise SpecError(f"'bins' must be an integer of at least 2, got {bins!r}")
    *_, mesh = ax.hist2d(x, y, bins=bins, cmap=colour_map(spec, SEQUENTIAL_CMAP))
    bar = ax.figure.colorbar(mesh, ax=ax, fraction=0.046, pad=0.03)
    bar.set_label(literal(spec.get("cbar_label", "Count")))


def render_residual(ax, spec: dict) -> None:
    """Residuals against fitted values, with the zero line.

    The standard regression diagnostic, and the figure that shows whether a
    model's errors are structured. A healthy plot is a formless band around
    zero; a funnel means the variance grows with the prediction, and a curve
    means the model is missing a term. Choose over ``scatter`` of predicted
    against actual, where both of those failures hide along the diagonal —
    the eye is far better at spotting a pattern against a horizontal line
    than a departure from a 45-degree one.

    Takes ``x``/``values`` like every other type, and also accepts ``fitted``
    and ``residuals`` under their own names, which read better in a spec
    written for this chart. Those two were reachable and named nowhere — not
    here, not in the example, not in SKILL.md — so the only way to find them
    was to read the renderer.
    """
    series = series_of(spec)
    for i, s in enumerate(series):
        fitted = numbers(s.get("x") or s.get("fitted"), f"series[{i}].x")
        resid = numbers(
            s.get("values") or s.get("residuals"), f"series[{i}].values", expect=fitted.size
        )
        colour = series_style(i)["color"]
        label = literal(s["label"]) if s.get("label") else None
        ax.scatter(fitted, resid, s=24, alpha=0.6, color=colour, edgecolors="none", label=label)
    ax.axhline(0.0, color="#333333", linewidth=1.0)
    if spec.get("band"):
        # A ±k·sigma envelope, so "inside the band" is a judgement the figure
        # makes rather than one the reader has to eyeball.
        sigma = float(
            np.std(
                np.concatenate(
                    [numbers(s.get("values") or s.get("residuals"), "residuals") for s in series]
                )
            )
        )
        k = float(spec.get("band"))
        ax.axhspan(-k * sigma, k * sigma, color="#999999", alpha=0.15, zorder=0)
    draw_legend(ax, spec, series)


def render_stacked_pct(ax, spec: dict) -> None:
    """Composition as percentages — every bar fills the full height.

    For how a whole DIVIDES when the total is not the point: what share of
    tokens each stage consumed, what fraction of errors each class
    contributed. Choose over stacked ``bar`` when the categories have very
    different totals and you want to compare their makeup rather than their
    size — a raw stack makes a small category's composition unreadable next
    to a large one. Never use it when the totals matter; normalising throws
    them away and nothing on the figure hints that it happened.
    """
    series = series_of(spec)
    n = max(len(s.get("values") or []) for s in series)
    cats = labels_for(spec, n)
    stacks = [
        numbers(s.get("values"), f"series[{i}].values", expect=n) for i, s in enumerate(series)
    ]
    for i, col in enumerate(stacks):
        if np.any(col < 0):
            raise SpecError(
                f"series[{i}].values has a negative. A percentage stack has no "
                "honest rendering of one — the share would exceed the whole."
            )
    total = np.sum(stacks, axis=0)
    if np.any(total <= 0):
        bad = [cats[j] for j in np.where(total <= 0)[0]]
        raise SpecError(f"categories {bad} total zero, so they have no composition to show")

    x = np.arange(n)
    bottom = np.zeros(n)
    for i, (s, col) in enumerate(zip(series, stacks, strict=True)):
        share = 100.0 * col / total
        ax.bar(
            x,
            share,
            0.68,
            bottom=bottom,
            label=literal(s["label"]) if s.get("label") else None,
            color=PALETTE[i % len(PALETTE)],
        )
        if flag(spec, "annotate"):
            for xi, base, height in zip(x, bottom, share, strict=True):
                if height >= 6:  # below this the number does not fit in the band
                    ax.text(
                        xi,
                        base + height / 2,
                        f"{height:.0f}%",
                        ha="center",
                        va="center",
                        fontsize=8,
                        # NOT a fixed white: the palette runs from a dark
                        # blue to a pale yellow, and white on the amber band
                        # measured 2.6:1 against a 4.5:1 minimum.
                        color=ink_on(PALETTE[i % len(PALETTE)]),
                    )
        bottom += share
    ax.set_xticks(x, labels=cats)
    ax.set_ylim(0, 100)
    ax.set_ylabel(literal(spec.get("ylabel") or "Share (%)"))
    # The stack fills the axes to 100% by construction, so there is never
    # room inside for a legend.
    draw_legend(ax, spec, series, headroom=False, outside=True)


def render_funnel(ax, spec: dict) -> None:
    """Stage-by-stage attrition, each stage a bar with what survived it.

    For a pipeline that loses volume at every step — candidates generated,
    passing a filter, reaching evaluation, published — where the DROP is the
    finding. Each stage is annotated with its absolute count and its
    retention against both the previous stage and the original intake, which
    is the pair of numbers a reader always wants and usually has to compute
    themselves. Choose over a plain ``barh`` when the stages are sequential
    and the losses compound; a bar chart shows the same heights but not that
    each stage is drawn FROM the one above it.
    """
    series = series_of(spec)
    values = numbers(series[0].get("values"), "series[0].values")
    if values.size < 2:
        raise SpecError("a funnel needs at least two stages")
    if np.any(np.diff(values) > 0):
        rising = [i for i in range(1, values.size) if values[i] > values[i - 1]]
        raise SpecError(
            f"stage(s) {rising} are LARGER than the stage above. A funnel shows "
            "attrition, so a rising stage means the stages are out of order or "
            "this is not a funnel — use 'bar'."
        )
    stages = labels_for(spec, values.size)
    y = np.arange(values.size)
    top = float(values[0])
    for i, value in enumerate(values):
        ax.barh(y[i], value, 0.62, color=PALETTE[i % len(PALETTE)])
        overall = 100.0 * value / top if top else 0.0
        note = f"{value:,.0f}  ({overall:.0f}% of intake"
        if i:
            prev = float(values[i - 1])
            note += f", {100.0 * value / prev:.0f}% of previous" if prev else ""
        ax.text(
            value,
            y[i],
            note + ")",
            va="center",
            ha="left",
            fontsize=8.5,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 1.0},
        )
    ax.set_yticks(y, labels=stages)
    ax.invert_yaxis()
    ax.grid(axis="x", visible=True)
    ax.grid(axis="y", visible=False)
    # Headroom on the right so the widest annotation is not clipped.
    ax.set_xlim(0, top * 1.42)


# A discrete legend is a lookup table, and past this many entries the reader
# is matching swatches rather than reading the grid. It is also where the
# palette runs out: beyond eight the colours repeat exactly, so two different
# levels would be drawn identically and the figure would be wrong, not merely
# crowded.
MAX_CATMAP_LEVELS = len(PALETTE)


def render_catmap(ax, spec: dict) -> None:
    """A grid whose cells hold a CATEGORY, not a magnitude.

    For which-one-was-it across two axes: the expert each token was routed to
    per layer, the outcome of every task under every config (pass / fail /
    timeout), which variant won each seed. Choose over ``heatmap``, which is
    not a plainer version of this but the wrong figure for a nominal value: a
    sequential ramp asserts that expert 4 is more than expert 1 and that 2
    lies between them, so a reader takes an ordering out of what is only an
    identifier. Here each level gets a palette colour and a legend entry, and
    nothing about the colours implies a rank.

    Keys: ``matrix`` (rows of category names), ``levels`` to pin the legend
    order and which colour each level gets — worth setting whenever two
    figures share a vocabulary, since otherwise colours follow first
    appearance and the same level differs between them — plus ``row_labels``,
    ``col_labels`` and ``annotate``.
    """
    raw = spec.get("matrix")
    if not isinstance(raw, list) or not raw or not all(isinstance(row, list) for row in raw):
        raise SpecError("'matrix' must be a non-empty list of equal-length rows")
    widths = {len(row) for row in raw}
    if len(widths) != 1 or widths == {0}:
        raise SpecError(f"'matrix' rows have differing or empty lengths {sorted(widths)}")
    for r, row in enumerate(raw):
        for c, cell in enumerate(row):
            if isinstance(cell, float) or not isinstance(cell, str | int):
                raise SpecError(
                    f"matrix[{r}][{c}] is {cell!r}. A catmap cell names a category, "
                    "so it must be a string or an integer code. A measured "
                    "quantity belongs in 'heatmap', which draws it on a scale."
                )
    cells = [[str(cell) for cell in row] for row in raw]
    blank = [
        (r, c) for r, row in enumerate(cells) for c, cell in enumerate(row) if not cell.strip()
    ]
    if blank:
        r, c = blank[0]
        raise SpecError(
            f"matrix[{r}][{c}] is blank, and {len(blank)} cell(s) are. A level's "
            "colour only means anything through its legend entry, so a level "
            "with no name draws a swatch nothing on the figure identifies — "
            "half the grid was amber with nothing saying what amber was. Spell "
            "the level ('none', 'dropped'), which is also what the caption has "
            "to say anyway."
        )

    seen = list(dict.fromkeys(cell for row in cells for cell in row))
    raw_levels = spec.get("levels")
    if raw_levels is None:
        levels = seen
    else:
        if not isinstance(raw_levels, list) or not raw_levels:
            raise SpecError("'levels' must be a non-empty list of category names")
        levels = [str(level) for level in raw_levels]
        repeated = sorted({level for level in levels if levels.count(level) > 1})
        if repeated:
            raise SpecError(
                f"'levels' repeats {repeated}. Each level takes the next palette "
                "colour, so a repeat silently shifts every level after it."
            )
        unknown = sorted(set(seen) - set(levels))
        if unknown:
            raise SpecError(
                f"the matrix uses {unknown}, which 'levels' does not list. "
                "'levels' pins the legend order and the colours, so a level "
                "missing from it has no colour to draw."
            )
    if len(levels) > MAX_CATMAP_LEVELS:
        raise SpecError(
            f"{len(levels)} distinct levels, and the palette holds "
            f"{MAX_CATMAP_LEVELS} — past that two levels would be drawn in the "
            "same colour. Group the rare levels into an 'other', or if the "
            "values are really measurements use 'heatmap'."
        )

    index = {level: i for i, level in enumerate(levels)}
    codes = np.array([[index[cell] for cell in row] for row in cells])
    colours = [PALETTE[i] for i in range(len(levels))]
    # ``vmin``/``vmax`` on the half-integers, so every code lands in the middle
    # of its own band rather than on a boundary between two.
    ax.imshow(
        codes,
        cmap=ListedColormap(colours),
        vmin=-0.5,
        vmax=len(levels) - 0.5,
        aspect="auto",
        interpolation="nearest",
    )
    ax.set_xticks(
        np.arange(codes.shape[1]),
        labels=labels_for({"categories": spec.get("col_labels")}, codes.shape[1]),
    )
    ax.set_yticks(
        np.arange(codes.shape[0]),
        labels=labels_for({"categories": spec.get("row_labels")}, codes.shape[0]),
    )
    ax.grid(visible=False)
    if flag(spec, "annotate"):
        # The same gate ``heatmap`` and ``clustermap`` carry, and this type
        # needs it MORE than they do: their cell text is a formatted number,
        # this one draws a category NAME. Without it, "copy suppression" was
        # drawn 15 px wider than its own 166 px cell, overhanging into both
        # neighbours, and two adjacent labels closed to 2.6 px — narrower than
        # a word space — so they printed as "retrieval headcopy suppression".
        # The collision gate downstream did not catch it: it fires on boxes
        # that INTERSECT, and these merely touch.
        require_annotations_fit(spec, codes.shape[1], max(levels, key=len))
        for r in range(codes.shape[0]):
            for c in range(codes.shape[1]):
                ax.text(
                    c,
                    r,
                    literal(cells[r][c]),
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    # Same rule as every other annotated cell in the skill: the
                    # ink follows the luminance of the patch it sits on, since
                    # the palette spans a dark blue and a pale yellow and no
                    # single fixed colour is legible on both.
                    color=ink_on(colours[codes[r, c]]),
                )
    # The grid fills its plot area by construction, so an inside legend has
    # nowhere free to sit and would cover cells. Out it goes — and on a single
    # chart it goes out through constrained layout, which RESERVES the strip
    # rather than anchoring at a fixed fraction of the axes height. The fixed
    # anchor is what printed the legend straight through "Token position";
    # ``draw_legend`` records the same failure for the same reason.
    handles = [
        Patch(facecolor=colour, label=literal(level))
        for colour, level in zip(colours, levels, strict=True)
    ]
    ncols = min(len(levels), 4)
    if content_places(ax.figure) == 1:
        place_legend(ax.figure, handles=handles, loc="outside lower center", ncols=ncols)
    else:
        # The same anchor and padding ``draw_legend`` uses for a panel, which
        # measurably clears the panel's xlabel where -0.12 without
        # ``borderaxespad`` did not.
        place_legend(
            ax,
            handles=handles,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.14),
            ncols=ncols,
            borderaxespad=0.0,
        )


# Past this the arrowheads touch on a print-width figure and the field reads
# as a texture rather than as a set of directions. Measured on a 7-inch
# canvas: a 20x20 grid is still legible, 30x30 is a smear.
MAX_QUIVER_ARROWS = 400

# An arrow shorter than this fraction of the data's diagonal is a dot with a
# head on it — the direction it encodes cannot be read off the page.
_MIN_ARROW_SPAN = 0.01


def render_quiver(ax, spec: dict) -> None:
    """A field of arrows — where each sample is, and where it went.

    For DISPLACEMENT sampled over a plane: how embeddings moved between two
    checkpoints, a gradient or force field, drift between two runs. Choose
    over a ``scatter`` of the before and after positions, which carries the
    same numbers but leaves the reader pairing points up by eye — the arrow
    states which went where, and a direction is readable at a glance where
    two overlaid clouds of dots are not.

    ``series[0]`` carries ``x`` and ``y`` (the tails) and ``u`` and ``v`` (the
    components). Arrows are drawn in DATA units, so a length is literally the
    displacement and the field can be measured against the axes; ``scale``
    overrides that with matplotlib's convention, where a LARGER number draws
    SHORTER arrows. ``color_by_magnitude`` shades each arrow by its length and
    adds a colourbar, for when the speed matters as much as the heading;
    ``cmap`` overrides the sequential default there, and the rainbow family is
    refused because magnitude is the only thing the colour encodes.

    The two axes are always drawn to the same scale, so a 45-degree
    displacement reads as 45 degrees on the page. That is why the canvas
    defaults to 1:1; pinning a wide ``aspect`` still keeps the angles true,
    it just leaves margins either side of the plot.
    """
    series = series_of(spec)
    s = series[0]
    x = numbers(s.get("x"), "series[0].x")
    y = numbers(s.get("y"), "series[0].y", expect=x.size)
    u = numbers(s.get("u"), "series[0].u", expect=x.size)
    v = numbers(s.get("v"), "series[0].v", expect=x.size)
    if x.size > MAX_QUIVER_ARROWS:
        raise SpecError(
            f"{x.size} arrows, and past {MAX_QUIVER_ARROWS} they overlap into a "
            "texture. Sample the field onto a coarser grid, or if the density "
            "itself is the finding use 'hist2d'."
        )
    magnitude = np.hypot(u, v)
    if not np.any(magnitude > 0):
        raise SpecError(
            "every vector is zero, so the figure would be an empty axes with "
            "tick marks. A field that did not move is a sentence, not a figure."
        )

    span = float(np.hypot(np.ptp(x), np.ptp(y)))
    scale = number_option(spec, "scale", 1.0, minimum=0.0)
    if scale == 0:
        raise SpecError(
            "'scale' is 0. Arrow length is displacement DIVIDED by scale, so "
            "zero is not 'no scaling' — it drew every arrow the same apparent "
            "length, about 262 times the width of the axes, which says nothing "
            "about the data. Use 1 for true displacement, or a smaller number "
            "to exaggerate."
        )
    # Keyed on the length that is actually DRAWN, not on whether the spec
    # mentioned 'scale'. The presence test let 'scale': 1.0 — a provable no-op —
    # switch the gate off, and let any scale above about 8 ship a blank field
    # at exit 0. Dividing here is what the renderer itself does below.
    drawn = float(magnitude.max()) / scale
    if span > 0 and drawn < _MIN_ARROW_SPAN * span:
        raise SpecError(
            f"the longest arrow draws {drawn:.4g} against a data span of "
            f"{span:.4g}, so every arrow is shorter than its own head. Lower "
            "'scale' to lengthen them (matplotlib's convention: SMALLER draws "
            "LONGER), and say in the caption that the arrows are exaggerated."
        )

    common = {"angles": "xy", "scale_units": "xy", "scale": scale, "width": 0.004}
    if flag(spec, "color_by_magnitude"):
        arrows = ax.quiver(x, y, u, v, magnitude, cmap=colour_map(spec, SEQUENTIAL_CMAP), **common)
        bar = ax.figure.colorbar(arrows, ax=ax, fraction=0.046, pad=0.03)
        bar.set_label(literal(spec.get("cbar_label", "Magnitude")))
    else:
        ax.quiver(x, y, u, v, color=PALETTE[0], **common)
    # The tails sit at the data limits, so autoscaling clips every arrowhead
    # on the outside of the field. Pad by the longest arrow.
    # Register the TIPS, not just the tails. ``quiver`` reports only its
    # offsets to the data limits, so ``ax.dataLim`` held the tail grid alone —
    # and the shared crop gate, which asks whether the limits a spec pinned
    # still cover the data, could not see an arrow it had cut in half. With
    # the tips in, an 'xlim' that drops an arrow is caught like any other.
    tips = np.column_stack([x + u / scale, y + v / scale])
    ax.update_datalim(np.vstack([np.column_stack([x, y]), tips]))
    reach = float(magnitude.max()) / scale
    ax.set_xlim(float(x.min()) - reach, float(x.max()) + reach)
    ax.set_ylim(float(y.min()) - reach, float(y.max()) + reach)
    # One data unit must be the same length on both axes, or the drawn angle
    # is not the angle in the data — and the angle is the whole content of
    # this figure. Measured on the house 16:9 canvas with IDENTICAL x and y
    # ranges, a 45-degree vector drew at 26.9 degrees. ``angles="xy"`` keeps
    # the arrow consistent with the axes, so the figure could still be
    # measured; it is the direction a reader takes at a glance that was wrong.
    ax.set_aspect("equal")


EXTRA_RENDERERS = {
    "step": render_step,
    "hist2d": render_hist2d,
    "residual": render_residual,
    "stacked_pct": render_stacked_pct,
    "funnel": render_funnel,
    "catmap": render_catmap,
    "quiver": render_quiver,
}
