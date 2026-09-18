"""Primitives every chart family shares.

Extracted so the renderer families — core, evaluation curves, comparison,
distribution, flow — can all build on one definition of what a valid series
is, how a legend is placed, and above all what counts as a number.

That last one is the point. ``numbers()`` is the gate that stops a figure
disagreeing with its data: NaN rendered as a silent gap that reads as a
measured zero, a short series zero-filled into measurements nobody made, a
length mismatch quietly dropping categories. Every family goes through it,
so a new chart type cannot reintroduce a defect an old one already fixed.
"""

from __future__ import annotations

import math

import numpy as np
from chart_style import content_places, literal, place_legend

__all__ = [
    "SpecError",
    "ink_for",
    "ink_on",
    "cell_halo",
    "MIN_TEXT_CONTRAST",
    "readable_ink",
    "labels_for",
    "draw_legend",
    "numbers",
    "require_consistent_labels",
    "require_fittable",
    "reject_pointless_diverging",
    "reject_unrenderable_categories",
    "require_positive",
    "series_of",
    "colour_map",
    "legend_place",
    "number_format",
    "number_option",
    "flag",
]


class SpecError(ValueError):
    """A spec that cannot be rendered, with a message naming the problem."""


def series_of(spec: dict) -> list[dict]:
    """The spec's series, checked for the two things every type needs.

    Every renderer funnels through here, so this is where a rule that holds
    for all of them belongs — rather than in fifty renderers, forty of which
    would forget it.
    """
    series = spec.get("series") or []
    if not series:
        raise SpecError("'series' is empty — a chart needs at least one data series")
    require_consistent_labels(series)
    return series


def labels_for(spec: dict, n: int) -> list[str]:
    """Category labels for ``n`` data points.

    Absent categories are numbered — that is a chart without category names,
    which is fine. But categories that are PRESENT and the wrong length are
    an error, not something to trim or pad. Silently truncating produced a
    confident figure with two of its five categories missing, which is worse
    than no figure: nothing downstream can tell it happened.
    """
    raw = spec.get("categories")
    if not raw:
        return [str(i + 1) for i in range(n)]
    if not isinstance(raw, list):
        raise SpecError(f"'categories' must be a list, got {type_name(raw)}")
    if len(raw) != n:
        raise SpecError(
            f"'categories' has {len(raw)} {'entry' if len(raw) == 1 else 'entries'} "
            f"but the data has {n} {'point' if n == 1 else 'points'}. "
            "Every category needs a value and every value needs a category — "
            "pad the shorter one explicitly rather than leaving it to be guessed."
        )
    return [literal(c) for c in raw]


def require_positive(values: np.ndarray, what: str, axis: str) -> None:
    """A log axis silently DELETES non-positive points.

    matplotlib masks them, so four points in becomes two drawn, and in
    ``scaling`` the fitted exponent disappears with them because the fit is
    gated on positivity — a figure quietly missing both data and its headline
    number.
    """
    bad = [float(v) for v in values if v <= 0]
    if bad:
        raise SpecError(
            f"{what} contains {bad[:3]}{'…' if len(bad) > 3 else ''} on a "
            f"logarithmic {axis} axis. A log scale cannot show zero or negative "
            "values — matplotlib drops them silently, leaving a figure with "
            "fewer points than the data. Use a linear axis."
        )


def numbers(values, what: str, *, expect: int | None = None) -> np.ndarray:
    """Coerce ``values`` to a float array, rejecting anything unplottable.

    NaN and Infinity are the dangerous ones: matplotlib draws NaN as *nothing
    at all*, so a bar quietly vanishes and the gap reads as a measured zero.
    A figure that misreports its own data is the exact failure this renderer
    exists to prevent, so these stop the render instead.
    """
    if values is None:
        raise SpecError(f"{what} is missing")
    if not isinstance(values, list | tuple):
        raise SpecError(f"{what} must be a list of numbers, got {type_name(values)}")
    if len(values) == 0:
        # An empty list drew an EMPTY CHART at exit 0 — axes, title, legend
        # and no data — which downstream cannot distinguish from a figure that
        # rendered correctly, so it reaches the paper as a blank panel.
        raise SpecError(
            f"{what} is an empty list, so there is nothing to draw. Drop the "
            "series entirely rather than passing it with no values."
        )
    out = []
    for i, v in enumerate(values):
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise SpecError(f"{what}[{i}] is {v!r} — every value must be a number")
        if not np.isfinite(v):
            raise SpecError(
                f"{what}[{i}] is {v!r}. NaN and Infinity render as a silent gap "
                "that reads as zero — drop the point or state it explicitly."
            )
        out.append(float(v))
    if expect is not None and len(out) != expect:
        raise SpecError(
            f"{what} has {len(out)} {'entry' if len(out) == 1 else 'entries'} "
            f"but {expect} {'was' if expect == 1 else 'were'} expected"
        )
    return np.asarray(out, dtype=float)


def require_consistent_labels(series: list[dict]) -> None:
    """Every drawn series is named, or none of them is.

    A legend is drawn as soon as ANY series carries a label, and the ones
    without simply do not appear in it. Three series, two labelled: the
    figure shows blue, amber and green bars and names two colours, so the
    tallest bar in every group is a quantity the reader cannot identify.
    Nothing about the picture looks wrong, which is what makes it worth
    refusing rather than leaving to the eye.

    Naming none of them is fine — that is a chart with one meaning and no
    legend, and the y-label carries it.
    """
    if len(series) < 2:
        return
    named = [bool(str(s.get("label", "")).strip()) for s in series]
    if all(named) or not any(named):
        return
    missing = [i for i, has in enumerate(named) if not has]
    raise SpecError(
        f"series {missing} have no 'label' while the others do. The legend names only the "
        "series that have one, so these are drawn and left unidentified — a reader sees the "
        "colour and has nothing to match it to. Name every series, or none of them if the "
        "chart has one meaning and does not need a legend."
    )


def draw_legend(
    ax, spec: dict, series: list[dict], *, headroom: bool = True, outside: bool = False
) -> None:
    """Draw a legend only when it carries information, with room to sit in.

    A one-series legend restates the y-label and steals space; venues call
    it out in review.

    ``headroom`` widens the top of the y-range before placing the legend.
    ``loc="best"`` only avoids the data when somewhere free exists — on a
    chart whose tallest bar reaches the top of the axes it has nowhere to
    go and lands on top of the bars. Skip it for horizontal charts, where
    the free space is on the x-axis instead.
    """
    # Read BEFORE the early return, on purpose. ``legend_loc`` is documented as
    # a key every type takes, and a one-series chart gets no legend at all — so
    # asking for a legend position there is a request that has nothing to
    # apply to, not a typo. Looking at it here is what tells the ignored-key
    # reporter the difference, which otherwise refused a spec written straight
    # from the documented list.
    requested_loc = legend_place(spec)
    if len(series) < 2 or not any(s.get("label") for s in series):
        return
    # Past a handful of entries an inside legend needs more of the axes than
    # headroom can buy — at twelve series it sat on top of the data and hid a
    # tick label. Above the threshold, move it OUT: constrained layout then
    # reserves real space for it and overlap becomes impossible rather than
    # merely unlikely.
    # ``outside`` is for charts whose plot area is full BY CONSTRUCTION — a
    # 100% stack reaches the top of every bar, so "find some free space" has
    # no answer and ``loc="best"`` drops the legend onto the data.
    if (outside or len(series) > 6) and not requested_loc:
        # Few entries read best as one horizontal row; many need wrapping to
        # about three rows so the legend does not eat the figure.
        ncol = len(series) if len(series) <= 4 else min(5, (len(series) + 2) // 3)
        handles, labels = ax.get_legend_handles_labels()
        if content_places(ax.figure) == 1:
            # ``loc="outside lower center"`` is laid out BY constrained layout,
            # which reserves the strip and then places the legend in it. The
            # hand-rolled anchor below is a fixed fraction of the AXES height,
            # so on a short canvas (a 21:9 stacked bar) 14% of the height was
            # less than the tick labels and x-label already occupied and the
            # legend printed straight through "Pipeline phase". Only available
            # for a figure-level legend, hence the single-axes test.
            place_legend(ax.figure, handles, labels, loc="outside lower center", ncols=ncol)
            return
        place_legend(
            ax, loc="upper center", bbox_to_anchor=(0.5, -0.14), ncols=ncol, borderaxespad=0.0
        )
        return
    if headroom:
        lo, hi = ax.get_ylim()
        ax.set_ylim(lo, lo + (hi - lo) * 1.18)
    ncol = len(series) if len(series) <= 4 else (len(series) + 1) // 2
    place_legend(ax, loc=requested_loc or "best", ncols=ncol)


# Beyond this, a category name cannot be rendered under a vertical bar at
# print width by any combination of wrapping and rotation — 76-character
# names came out as "ency" and "ples", fragments that misidentify the bar
# they label.
_MAX_VERTICAL_CATEGORY_CHARS = 40


def reject_unrenderable_categories(cats: list[str]) -> None:
    """Send long category names to ``barh`` instead of clipping them.

    A horizontal bar puts its label on the y-axis, where the full figure
    width is available, so the same names fit comfortably. Refusing with
    that pointer beats emitting a figure whose labels are truncated to
    their last four characters.
    """
    longest = max((len(c) for c in cats), default=0)
    if longest > _MAX_VERTICAL_CATEGORY_CHARS:
        # Reuses ``longest`` rather than ``max(cats, key=len)``: that form infers
        # the element type as `Sized`, which the slice below cannot subscript.
        worst = next(c for c in cats if len(c) == longest)
        raise SpecError(
            f"category {worst[:45]!r}… is {longest} characters, too long to sit "
            'under a vertical bar without being cut off. Use "type": "barh" — '
            "a horizontal bar puts the label on the y-axis where the full width "
            "is available — or shorten the names and explain them in the caption. "
            "Note the axes swap on barh: the values go on x, the categories on y, "
            "so xlabel and ylabel trade places."
        )


def reject_pointless_diverging(values, *, key: str = "diverging") -> None:
    """Refuse ``diverging`` on data that never crosses zero.

    A diverging map is centred on zero and spends half its range either side.
    On all-positive data that half is never used, the mid-tone the eye reads
    as "the middle" sits at a value nothing has, and every cell lands in one
    arm — a ``clustermap`` of scores from 38 to 93 came out uniformly red with
    a colourbar running −93 to +93. The figure is unreadable and exits 0,
    which is the shape of defect this renderer exists to refuse.

    Only for the EXPLICIT key. ``corr`` chooses a diverging map itself and is
    right to: zero means "no correlation" whether or not any cell is negative,
    so its centre is meaningful even on all-positive data.
    """
    import numpy as np

    low, high = float(np.min(values)), float(np.max(values))
    if low < 0 < high:
        return
    side = "positive" if low >= 0 else "negative"
    raise SpecError(
        f"'{key}' centres the colour map on zero and spends half its range "
        f"either side, but every value here is {side} ({low:g} to {high:g}). "
        "Half the map would go unused and every cell would land in one arm, "
        f"all much the same colour. Drop '{key}' for the sequential map, which "
        "scales to the data, or set 'vmin'/'vmax' if a fixed centre is meant."
    )


def error_bars(values, what: str, *, expect: int | None = None):
    """``errors`` as a float array, refusing a negative magnitude.

    An error bar is a DISTANCE either side of the value, so a negative one
    means nothing. matplotlib says as much — "'yerr' must not contain
    negative values" — but it says it about the whole array, with no series,
    no index and no idea which of forty numbers is wrong, where every other
    refusal here names the exact key. Zero is allowed: a measurement with no
    spread is a real result.
    """
    import numpy as np

    array = numbers(values, what, expect=expect)
    bad = np.flatnonzero(array < 0)
    if bad.size:
        first = int(bad[0])
        raise SpecError(
            f"{what}[{first}] is {array[first]:g}. An error bar is a distance either "
            f"side of the value, so it cannot be negative — {bad.size} of "
            f"{array.size} here are. Use the magnitude of the interval."
        )
    return array


#: Roughly how wide one character is, as a fraction of the font size. DejaVu
#: Sans digits sit near 0.55 em; measured against the drawn extents rather
#: than taken from the font tables.
_DIGIT_EM = 0.55

#: The axes ends up narrower than the figure — tick labels, the y-label and a
#: colourbar all take width. Measured across widths 5, 7 and 12 in: the axes
#: was 77-82% of the figure, so 0.8 is the conservative middle.
_AXES_SHARE_OF_FIGURE = 0.8


def require_annotations_fit(spec: dict, columns: int, longest: str, font_pt: float = 7.5) -> None:
    """Refuse per-cell annotation the cells are too small to hold.

    A matrix wide enough that its numbers overlap is refused anyway — by the
    collision gate, AFTER laying out every one of them. That is the slow way
    round: a 200x200 annotated heatmap took 182 seconds to arrive at "514,943
    pairs of labels print over each other", where the same matrix without
    annotation is refused in under 4. The answer was knowable from the spec
    the whole time: 40,000 numbers do not fit in twelve inches.

    Measured rather than guessed, at three figure widths: the last cell size
    whose annotations survived was 0.24 in and the first that collided was
    0.19 in, at every width — a physical limit, as it should be. Asking
    whether the WIDEST annotation fits its own cell lands in that gap and
    adapts to ``fmt`` and the font size, which a fixed column count could not.
    """
    if columns < 1:
        return
    width_in = float(spec.get("width_in", 7.0))
    cell_in = width_in * _AXES_SHARE_OF_FIGURE / columns
    needed_in = len(longest) * font_pt * _DIGIT_EM / 72.0
    if cell_in >= needed_in:
        return
    raise SpecError(
        f"{columns} columns across {width_in:g} inches leaves {cell_in:.2f} in per cell, and "
        f"{longest!r} needs {needed_in:.2f} in — the numbers would print over each other. "
        'Drop "annotate" and let the colour carry the reading (the colourbar states the '
        "scale), show fewer columns, or raise 'width_in'."
    )


#: Colour maps that undo what the rest of the house style guarantees, and the
#: one to use instead. The rainbow family is not perceptually uniform: equal
#: steps in the data are unequal steps in apparent lightness, so the eye reads
#: boundaries where the numbers have none and reads a smooth run where they
#: have a jump. It is also the family that fails hardest for the ~8% of male
#: readers with a red-green deficiency — the same pairing ``--style neurips``
#: warns image models away from. The cyclic ones say the two ends of the scale
#: meet, which is true of a phase and false of an accuracy.
_UNSAFE_CMAPS = {
    "jet": "cividis",
    "rainbow": "cividis",
    "gist_rainbow": "cividis",
    "nipy_spectral": "cividis",
    "gist_ncar": "cividis",
    "brg": "cividis",
    "flag": "cividis",
    "prism": "cividis",
    "hsv": "twilight",
}


def flag(spec: dict, key: str, default: bool = False) -> bool:
    """A yes/no option, refusing anything that only LOOKS like one.

    JSON has a boolean and a model writing a spec does not always use it.
    ``bool("false")`` is ``True`` in Python, and so are ``"no"``, ``"off"``
    and the string ``"0"`` — measured across all ten of these options, every
    one of those five spellings turned the option ON. ``"density": "false"``
    drew a density plot, and the spec says the opposite of the figure.

    Refused rather than translated: ``"0"`` could be read as false, but
    ``"no"`` and ``"off"`` are guesses about intent, and a spec that means
    ``false`` can simply say ``false``.
    """
    value = spec.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise SpecError(
            f"'{key}' must be true or false, got {value!r}. A string is not a "
            f'boolean — every non-empty one, including "false" and "0", reads '
            f"as TRUE, so the figure would say the opposite of the spec."
        )
    return value


def number_option(
    spec: dict,
    key: str,
    default: float,
    *,
    minimum: float | None = None,
    integer: bool = False,
) -> float:
    """A numeric renderer option, held to the same bar as the data.

    ``numbers()`` refuses NaN because matplotlib draws it as nothing at all,
    and a point that vanishes reads as a measurement nobody made. An option
    that POSITIONS the data does exactly the same thing and was not being
    checked: ``point_spread: NaN`` on a beeswarm put 112 of its 126 points at
    a NaN coordinate, so the figure showed 14 and exited 0.

    ``minimum`` is for the options where a value below it cannot mean
    anything rather than merely looking odd — a sankey drawn at a negative
    scale is not a smaller diagram, it is the wrong one.
    """
    value = spec.get(key)
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise SpecError(f"'{key}' must be a number, got {value!r}. Leave it out for {default!r}.")
    if not math.isfinite(value):
        raise SpecError(
            f"'{key}' is {value!r}. It positions the data, so a non-finite value "
            "puts points at a coordinate matplotlib draws as nothing at all — "
            "the figure comes back with fewer points than the data and no error."
        )
    if integer and value != int(value):
        raise SpecError(f"'{key}' must be a whole number, got {value!r}")
    if minimum is not None and value < minimum:
        raise SpecError(f"'{key}' must be at least {minimum}, got {value!r}")
    return float(value)


def scalar_number(value, what: str) -> float:
    """One number from the spec, through the gate every series goes through.

    ``numbers`` takes a list, but a lone spec value — a bandwidth, an overlap
    fraction, an intersection size, a jitter width — arrives from the same
    JSON and is exactly as able to be ``None``, ``"0.7"`` or a NaN. Routing it
    through the same check keeps the invariant whole instead of leaving
    scalars as the one unguarded way a NaN reaches an axis.

    The index is stripped back out of the message: ``overlap[0]`` names a
    position in a list the spec author never wrote.

    This is ``number_option``'s sibling, not its rival: that one reads a KEY
    out of a spec and has a default to fall back to, this one is handed a
    value that has already been dug out — often from inside a series entry,
    where ``what`` is something like ``items[3].value``.

    Lived in ``chart_renderers_dist`` and ``chart_renderers_sets`` as the same
    eight lines twice, with a note in the second copy saying this module was
    where it belonged.
    """
    try:
        return float(numbers([value], what)[0])
    except SpecError as exc:
        raise SpecError(str(exc).replace(f"{what}[0]", f"'{what}'")) from exc


def kernel_density(samples: np.ndarray, grid: np.ndarray, bandwidth: float) -> np.ndarray:
    """Gaussian kernel density of ``samples`` evaluated on ``grid``.

    Written out rather than imported: scipy is present in the dev venv but is
    NOT a declared dependency of the pipeline image, so a ``scipy.stats``
    import here would work on a laptop and fail on deploy. It is five lines
    of arithmetic — one Gaussian per sample, averaged.

    The sum is chunked over samples so peak memory is bounded by the chunk
    rather than by ``len(grid) x len(samples)``, which for a 50k-sample group
    would be a 100 MB temporary for a curve 256 points wide.
    """
    density = np.zeros(grid.size, dtype=float)
    for start in range(0, samples.size, 4096):
        offsets = (grid[:, None] - samples[None, start : start + 4096]) / bandwidth
        density += np.exp(-0.5 * offsets * offsets).sum(axis=1)
    return density / (samples.size * bandwidth * np.sqrt(2.0 * np.pi))


def kde_bandwidth(samples: np.ndarray, what: str, override) -> float:
    """Silverman's rule of thumb, or the spec's own bandwidth.

    The IQR term is what keeps one outlier from setting the bandwidth for the
    whole group: a single 10x sample inflates the standard deviation, the
    kernel widens to match, and every real mode is smoothed flat.

    A group with no spread at all has no density to draw — a point mass is
    infinitely tall and zero wide — so it is refused with a pointer to the
    chart that CAN show it.
    """
    if override is not None:
        width = scalar_number(override, "bandwidth")
        if width <= 0:
            raise SpecError(f"'bandwidth' must be positive, got {width:g}")
        return width
    spread = float(np.std(samples))
    q25, q75 = (float(v) for v in np.percentile(samples, [25, 75]))
    if q75 > q25:
        spread = min(spread, (q75 - q25) / 1.349)
    if spread <= 0:
        raise SpecError(
            f"{what} has no spread — all {samples.size} observations are "
            f"{float(samples[0]):g}. A density curve of a single repeated value has "
            'no width to draw. Use "type": "strip", which shows the observations '
            "themselves, or a bar of the value."
        )
    return 0.9 * spread * samples.size ** (-0.2)


def number_format(spec: dict, key: str, default: str) -> str:
    """A format spec from ``spec[key]``, checked by using it.

    ``fmt`` reaches ``format(value, fmt)``, so a wrong one — `.2` with no
    type, a stray `%`, a word — came back as ``ValueError: Invalid format
    specifier`` from inside the annotation loop, naming neither the key nor
    the chart. Trying it once on a known number here is the whole check, and
    it cannot go stale the way a pattern for "what a format spec looks like"
    would.
    """
    fmt = spec.get(key)
    if fmt is None:
        return default
    if not isinstance(fmt, str) or not fmt.strip():
        raise SpecError(
            f"'{key}' must be a Python format spec such as '.2f' or ',.0f', "
            f"got {fmt!r}. Leave it out for {default!r}."
        )
    try:
        format(1.0, fmt)
    except (ValueError, TypeError):
        raise SpecError(
            f"'{key}' is {fmt!r}, which Python cannot format a number with, so "
            f"every annotated value would fail. Use format-spec syntax, not "
            f"printf — '.2f' for two decimals, ',.0f' for thousands separators, "
            f"'.1%' for a percentage, never '%.2f'. Leave it out for {default!r}."
        ) from None
    return fmt


def legend_place(spec: dict) -> str | None:
    """``spec['legend_loc']``, checked against matplotlib's own table.

    The third key in this skill whose value is a bare string handed to
    matplotlib, after ``font_family`` and ``cmap``, and it failed the same way:
    ``'northeast'`` came back as a ``ValueError`` listing every valid location
    with no mention that the spec key was ``legend_loc``. The module docstring
    of ``chart_validate`` names that exact case as the kind of thing this skill
    refuses; it just never checked this one.

    ``outside …`` gets its own message because it is the plausible wrong guess
    rather than a typo: matplotlib accepts it only on a FIGURE legend, and it
    is what the layout pass already uses on its own when a legend has too many
    entries to sit inside the axes. Asking for it here is asking for something
    that happens without being asked.

    Placements are read from ``Legend.codes`` rather than copied, so a location
    matplotlib adds or removes cannot leave this list quietly wrong.
    """
    loc = spec.get("legend_loc")
    if loc is None:
        return None
    from matplotlib.legend import Legend

    valid = sorted(Legend.codes)
    if isinstance(loc, str) and loc.strip() in valid:
        return loc.strip()
    if isinstance(loc, str) and loc.strip().startswith("outside"):
        raise SpecError(
            f"'legend_loc' is {loc!r}. Only a figure-level legend takes an "
            "'outside …' placement, and you do not need to ask for one: the "
            "layout pass moves the legend out by itself when it has more "
            f"entries than fit inside the axes. Use one of {', '.join(valid)}."
        )
    if isinstance(loc, int) and not isinstance(loc, bool):
        raise SpecError(
            f"'legend_loc' is {loc!r}. matplotlib's numeric location codes are "
            f"not part of this spec — name the placement: {', '.join(valid)}."
        )
    import difflib

    text = loc.strip() if isinstance(loc, str) else ""
    close = difflib.get_close_matches(text.lower(), valid, n=2, cutoff=0.5)
    suggestion = f" Closest: {', '.join(repr(c) for c in close)}." if close else ""
    raise SpecError(
        f"'legend_loc' is {loc!r}, which is not a legend placement, so the "
        f"figure cannot be drawn at all.{suggestion} Valid: {', '.join(valid)}."
    )


def colour_map(spec: dict, default: str) -> str:
    """``spec['cmap']``, or ``default``, refusing one that is not a reading.

    The twin of ``colour_limit`` above, for the same reason: a name matplotlib
    does not know reaches ``imshow`` and comes back as a bare ``ValueError``
    listing all 166 registered maps, with nothing to say the spec key was
    ``cmap`` — while every other bad value in this skill names its key and what
    to change.

    It also refuses the rainbow and cyclic families outright. Colour is the
    only encoding a heatmap has, so the map is not decoration: ``jet`` puts a
    bright yellow band in the middle of a run that is monotonic in the data,
    and a reader takes that band for a boundary in the result. Nothing
    downstream can detect it, because the figure is exactly what was asked for.
    """
    name = spec.get("cmap")
    if name is None:
        return default
    # Presence checked rather than truthiness, the way ``colour_limit`` does
    # it: ``"cmap": ""`` under an ``or default`` is a key that was written,
    # accepted, and did nothing, with no word to say the default was used.
    if not isinstance(name, str) or not name.strip():
        raise SpecError(
            f"'cmap' must be the name of a matplotlib colour map, got {name!r}. "
            f"Leave it out for the house default ({default!r})."
        )
    instead = _UNSAFE_CMAPS.get(name.removesuffix("_r"))
    if instead is not None:
        raise SpecError(
            f"'cmap' is {name!r}, which is not perceptually uniform — equal steps "
            f"in the data are unequal steps in lightness, so it draws boundaries "
            f"the numbers do not have, and it is unreadable with a red-green "
            f"deficiency. Use {instead!r}, or leave 'cmap' out for {default!r}."
        )
    from matplotlib import colormaps

    if name not in colormaps:
        import difflib

        close = difflib.get_close_matches(name, sorted(colormaps), n=3, cutoff=0.6)
        suggestion = f" Closest registered: {', '.join(repr(c) for c in close)}." if close else ""
        raise SpecError(
            f"'cmap' is {name!r}, which matplotlib does not know, so the figure "
            f"cannot be drawn at all.{suggestion} Leave it out for {default!r}."
        )
    return name


def require_colour_limits_cover(values, vmin: float, vmax: float, *, stated, what="matrix") -> None:
    """Refuse colour limits that crop the data they are drawn over.

    The colour-axis twin of ``_limits_must_cover_data``. Everything past a
    limit is clamped to the end colour, so cells that differ are painted
    identically and the colourbar states a range the data does not have:
    ``vmax: 0.3`` on a matrix running 0.10..0.95 gave four of six cells the
    same yellow, a 0.30 result and a 0.95 result indistinguishable, under a
    bar labelled 0.100..0.300. Colour is the only encoding a heatmap has —
    with ``annotate`` off (the ``clustermap`` default) nothing else carries
    the number — so a clamped cell is not a zoom, it is a wrong reading.

    Takes the RESOLVED limits and the keys that were stated, because under
    ``diverging`` a stated ``vmax`` also sets ``vmin`` at ``-vmax``: checking
    the spec keys alone would miss the low end it silently cropped.
    """
    import numpy as np

    if not stated:
        return
    array = np.asarray(values, dtype=float)
    low, high = float(array.min()), float(array.max())
    slack = max(high - low, 1e-9) * 1e-6
    counts = [
        (int((array < vmin - slack).sum()), f"below {vmin:g}"),
        (int((array > vmax + slack).sum()), f"above {vmax:g}"),
    ]
    outside = [f"{n} {where}" for n, where in counts if n]
    if not outside:
        return
    keys = " and ".join(repr(key) for key in stated)
    raise SpecError(
        f"the colour limits set by {keys} run {vmin:g}..{vmax:g}, but the {what} runs "
        f"{low:g}..{high:g} — of its {array.size} cells, {' and '.join(outside)}. Those "
        "would all be drawn in one end colour as if they were equal, under a colourbar "
        "stating a range the data does not have. Widen the limits, or drop them and let "
        "the colour map fit the data."
    )


# The two inks every annotation-on-a-fill chooses between: the page white and
# a near-black that is softer than pure black at small sizes.
_INK_LIGHT = "white"
_INK_DARK = "#1a1a1a"


def _relative_luminance(colour) -> float:
    """WCAG relative luminance, with any transparency composited over white."""
    from matplotlib.colors import to_rgba

    red, green, blue, alpha = to_rgba(colour)
    channels = [alpha * c + (1.0 - alpha) for c in (red, green, blue)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(ink, background) -> float:
    """WCAG contrast ratio between two colours, 1.0 (same) to 21.0 (max)."""
    a, b = _relative_luminance(ink), _relative_luminance(background)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def require_fittable(x, y, what: str) -> None:
    """Refuse a least-squares fit that has nothing to solve.

    ``np.polyfit`` on points that all share one x — or on all-zero data —
    raises ``LinAlgError: SVD did not converge``, which is a ``ValueError``
    subclass and so reached the caller as "matplotlib rejected this figure",
    blaming the library for a fit that cannot exist. A vertical column of
    points has no slope, and two points define the line exactly with nothing
    left to estimate.
    """
    import numpy as np

    if x.size < 2 or y.size < 2:
        raise SpecError(
            f"{what} has {x.size} point, and a least-squares fit needs at least "
            "two. Drop 'fit' — the points alone are the figure."
        )
    if np.ptp(x) == 0:
        raise SpecError(
            f"{what} has the same x for every point ({float(x[0]):g}), so the fitted "
            "line would be vertical and has no slope to report. Drop 'fit', or plot "
            "the spread of y at that x with 'box'/'strip' instead."
        )


def readable_ink(colour, background="white", minimum: float = 4.5) -> tuple:
    """``colour``, darkened just enough to be READABLE as text on ``background``.

    A series colour identifies which curve a label belongs to, which is worth
    keeping — but a colour chosen to be distinguishable as a 1.8 pt line is
    not automatically legible as 8 pt text. The palette's amber on the white
    page measures 2.6:1 against a 4.5:1 minimum, which is what ``survival``
    drew its at-risk counts in.

    Darkened towards black in small steps and stopped at the first that
    clears, so the hue survives and the tie to the curve with it. Returns the
    colour unchanged when it already passes.
    """
    from matplotlib.colors import to_rgba

    red, green, blue, alpha = to_rgba(colour)
    for step in range(21):
        scale = 1.0 - step * 0.05
        candidate = (red * scale, green * scale, blue * scale, alpha)
        if _contrast(candidate, background) >= minimum:
            return candidate
    return (0.0, 0.0, 0.0, alpha)


def ink_on(colour) -> str:
    """Text colour that stays legible on a patch of ``colour``.

    The same question ``ink_for`` answers for a colormapped cell, for a flat
    fill. ``stacked_pct`` wrote white on every band regardless: white on the
    palette's amber measures 2.6:1 against a 4.5:1 minimum, and on its green
    3.4:1 — the exact defect ``ink_for`` exists to prevent one renderer over.

    A translucent patch is composited over the white page first, because the
    colour a reader sees is the composite; judging the fill alone puts dark
    text on what renders as a dark tile.

    Chosen by CONTRAST RATIO, not by a luminance threshold. "Is this fill
    darker than half?" is the wrong question: the palette's amber sits just
    under the halfway mark and took white at 2.2:1 when the same ink in near
    black would have given 7.6:1. Maximising the ratio is both simpler and
    what the accessibility standard is actually stated in.
    """
    return (
        _INK_LIGHT if _contrast(_INK_LIGHT, colour) >= _contrast(_INK_DARK, colour) else _INK_DARK
    )


#: The contrast ratio WCAG asks of small text. Enforced directly wherever the
#: background is a flat colour the renderer chose; over a COLORMAP it cannot
#: always be reached, which is what ``cell_halo`` exists for.
MIN_TEXT_CONTRAST = 4.5


def cell_halo(ink):
    """A hairline outline in the opposite ink, for text over a colormap.

    ``ink_on`` picks the better of near-black and near-white, which is the
    best that can be done — and over a continuous map the best is not always
    enough. Both maps this style ships have a mid-tone where neither ink
    clears the bar: cividis bottoms out at 4.18:1 and RdBu_r at 4.19:1
    against a stated minimum of 4.5, and those are the cells in the MIDDLE of
    a matrix, which is most of them when there is no strong block structure.

    Changing the colormap is the wrong fix. cividis is the one that is
    perceptually uniform AND colourblind-safe; RdBu_r is the one whose sign
    reads from hue direction. An outline keeps both and separates the glyph
    from whatever is behind it — the standard answer for text over a
    continuous field, and what ``radar`` already does for its radial labels.

    Applied to EVERY annotation, not only the ones below the bar. Haloing one
    cell in a matrix and not its neighbours makes that cell look singled out
    for a reason the reader cannot infer; at 0.8 pt the outline is invisible
    as an effect and does its work at the glyph edge.
    """
    from matplotlib.patheffects import withStroke

    opposite = _INK_DARK if ink == _INK_LIGHT else _INK_LIGHT
    return [withStroke(linewidth=0.8, foreground=opposite)]


def ink_for(image, value: float) -> str:
    """Text colour for a heatmap cell, from the cell's ACTUAL rendered colour.

    Deriving it from the value's position in the range assumes the colormap
    runs dark-to-bright. Reverse the map — ``cividis_r``, or any ``*_r`` — and
    the rule inverts: the lowest value lands on the BRIGHTEST cell and gets
    white text on yellow, while the highest gets near-black on navy. Both
    annotations become invisible while the figure still looks fine at a
    glance.

    Asking the colormap what it actually painted is correct for any map,
    reversed or not. Luminance uses the Rec. 709 weights, which track
    perceived brightness rather than treating the channels as equal.
    """
    return ink_on(image.cmap(image.norm(value)))


def type_name(value) -> str:
    """The JSON name for a value's type, for use in refusal messages.

    Specs are parsed with ``object_hook=RecordingDict`` so unused keys can be
    reported, which means every JSON object in a spec is a RecordingDict and
    ``type_name(value)`` put that class name in front of the user: a spec
    with an object where a list belongs said "got RecordingDict", naming an
    implementation detail the caller has no way to know about. These messages
    talk about JSON, so they now say what JSON calls it.
    """
    if isinstance(value, bool):
        return "boolean"  # before int: bool IS an int, and "integer" would mislead
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, int | float):
        return "number"
    if value is None:
        return "null"
    # Not a JSON type at all. This line used to read ``return type_name(value)``
    # — a self-call with the SAME argument, so anything reaching it recursed
    # until RecursionError rather than producing a name. It IS reachable:
    # ``_require_numbers`` calls this precisely when the value is not a
    # list/tuple, and this module computes with numpy, where ``np.int64`` is
    # not a subclass of ``int`` — so a refusal ABOUT a numpy scalar crashed
    # instead of being raised, turning a clear SpecError into a stack overflow.
    #
    # Deliberately NOT ``type(value).__name__``: that is the exact form this
    # function exists to replace, and it is forbidden across the skill. A spec
    # author writes JSON and has no more use for "int64" than for
    # "RecordingDict". Reaching here means a value that never came from their
    # spec, so name the category, not the class.
    return "an unsupported value"
