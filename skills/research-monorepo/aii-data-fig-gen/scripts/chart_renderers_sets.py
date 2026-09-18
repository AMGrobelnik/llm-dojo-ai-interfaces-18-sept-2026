"""Set overlap, hierarchy, parallel scaling and composite distributions.

Same contract as every other family: ``render_x(ax, spec) -> None``, drawing
onto an Axes the caller already owns. Nothing here builds a figure, saves a
file or touches ``plt`` global state. The two types that need more than one
panel — ``upset`` and ``speedup`` — derive their extra axes from the one they
were handed (``inset_axes``, ``twinx``), which is what lets ``panel`` compose
them like any other type.

These four answer questions the earlier families cannot:

* **Which items two or more sets have in common** — ``upset``. A Venn diagram
  stops being drawable to scale at three sets and stops being readable at
  four; an UpSet plot is the replacement that scales.
* **How a total divides into parts, and those parts into sub-parts** —
  ``treemap``. Area carries the value, so a hundred small parts still fit on
  a page that a bar chart would need to scroll.
* **Whether more workers actually bought more throughput** — ``speedup``,
  against the ideal linear reference every systems reviewer looks for first.
* **What a distribution looks like AND what its observations were** —
  ``raincloud``: half violin, box and the raw points, in one column per group.

Four defects specific to *these* types are worth naming, because each one
exits zero and produces a confident, plausible, wrong figure:

* an overlap figure whose intersections are INCLUSIVE while the reader
  assumes they partition the data, so the bars sum to far more than the
  union. The columns here are exclusive — each element is counted in exactly
  one — and the docstring says so;
* a treemap that reserves a header strip for each group's name, which takes
  that area out of the group's children: every child rectangle is then
  smaller than its value and the one honest property of the chart is gone;
* a speedup plot with no ideal reference line — 8x on 32 workers reads as a
  win until the diagonal is drawn next to it;
* a raincloud that lets its box draw fliers on top of the raw points, so the
  outliers — and only the outliers — appear twice and read as double.

Dependencies are matplotlib, numpy and the standard library. scipy is present
in a dev environment but is NOT a declared dependency of the pipeline image,
so the density estimate below is written out longhand rather than imported.
"""

from __future__ import annotations

import math
import textwrap

import numpy as np
from chart_common import (
    SpecError,
    flag,
    ink_on,
    legend_place,
    number_format,
    number_option,
    type_name,
)
from chart_common import (
    kde_bandwidth as _bandwidth,
)
from chart_common import (
    kernel_density as _kde,
)
from chart_common import (
    numbers as _numbers,
)
from chart_common import (
    scalar_number as _scalar,
)
from chart_common import (
    series_of as _series,
)
from chart_style import (
    PALETTE,
    literal,
    place_legend,
)
from matplotlib.colors import to_rgba
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import NullFormatter, PercentFormatter

# Past this many sets the matrix rows are thinner than their own labels and
# the number of possible intersections (2^n - 1) outruns the page.
_MAX_SETS = 12
# Past this many columns the bars are narrower than the dots beneath them.
_MAX_INTERSECTIONS = 40
# Past this many rectangles a treemap is a texture, not a figure: the median
# rectangle is too small to label and the reader is left with colour alone.
_MAX_LEAVES = 48
# Points along a raincloud's density curve. Enough that a mode is a curve
# rather than a polygon, few enough that the kernel sum stays cheap.
_KDE_GRID = 200
# Below this many observations a density curve and a quartile box both claim
# more than the data supports — ``strip`` shows the same numbers honestly.
_MIN_RAIN_SAMPLES = 5
# Markers carry a second channel beside colour, so a speedup chart stays
# readable in greyscale print. SEVEN of them against the palette's eight is
# deliberate: with eight, series 0 and series 8 came out the same colour AND
# the same marker — pixel-identical lines with two different legend entries.
# Co-prime cycles push that collision out to the 56th series.
_MARKERS = ("o", "s", "^", "D", "v", "P", "X")
# Ink for the parts of a chart that are structure rather than data.
_GUIDE_INK = "#777777"
_DOT_INK = "#333333"
_EMPTY_DOT_INK = "#DBDBDB"


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------


def _positive_int(spec: dict, key: str, default: int | None, *, maximum: int) -> int | None:
    """An integer spec key that becomes a count of things drawn."""
    value = spec.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SpecError(f"'{key}' must be a positive integer, got {value!r}")
    if value > maximum:
        raise SpecError(f"'{key}' of {value} is past what a figure can show (max {maximum})")
    return value


def _axes_inches(ax, spec: dict) -> tuple[float, float]:
    """Roughly how big this Axes will be, in inches, before layout runs.

    Needed because two charts here decide what FITS — a rectangle's label, a
    column of set names — and a fit test has to be in the same units as the
    thing being fitted. The figure's size is known exactly; the axes' share of
    it is not, because constrained layout only settles at draw time.

    ``get_position`` reports the pre-layout box, which the default subplot
    margins shrink to about 77% of its slot in each direction; constrained
    layout hands nearly all of that back to an axes carrying no ticks or
    labels. Normalising by those margins turns the pre-layout box into an
    estimate of the final one, and it stays proportionally right inside a
    ``panel``, where the slot is genuinely half the figure.

    The TITLE has to be subtracted here rather than left to layout, because
    the caller sets it AFTER the renderer returns — so no measurement taken
    inside a renderer can see it. In a full-page figure it costs one line out
    of four inches and hardly matters; in a panel cell it wraps to three lines
    and takes a third of the height, which is exactly where an unadjusted
    estimate was 54% too generous and pushed labels out of their rectangles.

    The 0.88 factors keep what is left on the LOW side deliberately. A label
    skipped because the estimate was pessimistic costs one label; a label
    drawn because it was optimistic costs the figure.
    """
    box = ax.get_position()
    fig_w, fig_h = ax.figure.get_size_inches()
    width = box.width / 0.775 * fig_w * 0.88
    height = box.height / 0.77 * fig_h * 0.88
    title = spec.get("title")
    if title:
        # Measured at the size the title will actually be drawn at, then
        # divided by the width it has to wrap into. The 0.85 is the room a
        # panel label ``(b)`` takes out of that width, and the extra line is
        # slack: the caller wraps to a CHARACTER budget and then tightens it,
        # so a title that needs two lines by width routinely comes out as
        # three, and under-reserving is the direction that costs a figure.
        title_w, line_h = _text_inches(ax, literal(title), ax.title.get_fontsize())
        lines = max(1, math.ceil(title_w / max(width * 0.85, 0.1)))
        height -= (lines + 1) * line_h + 0.08
    return width, max(height, 0.5)


def _text_inches(ax, text: str, size_pt: float) -> tuple[float, float]:
    """Measured — not estimated — size of ``text`` at ``size_pt``, in inches.

    A characters-times-average-width estimate is wrong by 30% between "IIII"
    and "MMMM", which is the difference between a label that fits its
    rectangle and one that runs over the edge of it. Asking the renderer costs
    a text layout and is exact.

    Font metrics do not depend on where the axes ends up, so this is stable
    even though it runs before constrained layout has placed anything. The
    artist is removed again: it exists only to be measured.
    """
    artist = ax.text(0.0, 0.0, text, fontsize=size_pt)
    try:
        extent = artist.get_window_extent()
    finally:
        artist.remove()
    return extent.width / ax.figure.dpi, extent.height / ax.figure.dpi


def _grouped(spec: dict) -> tuple[list[np.ndarray], list[str]]:
    """Per-group samples and their labels, every value through the gate.

    An EMPTY group is rejected rather than skipped. Skipping renumbers every
    column after it, so the label "Ours" ends up over the samples belonging to
    the next group along and the figure is wrong in a way no reader can see.
    """
    series = _series(spec)
    data = []
    for i, entry in enumerate(series):
        # `_numbers` is the shared gate, and it refuses an empty list before
        # returning ("is an empty list, so there is nothing to draw"), so the
        # local size check that used to sit here could never fire. The reason
        # an empty group must be refused rather than skipped still stands and
        # is written in the docstring above; only the duplicate check is gone.
        values = _numbers(entry.get("values"), f"series[{i}].values")
        data.append(values)
    return data, [literal(s.get("label") or str(i + 1)) for i, s in enumerate(series)]


# --------------------------------------------------------------------------
# upset — set intersections
# --------------------------------------------------------------------------


def _membership(spec: dict) -> tuple[list[str], list[set]]:
    """Set names and their member ids, from ``sets``.

    Ids are compared for equality across sets, so they have to be things that
    compare cleanly: strings or integers. A float id would make ``17`` and
    ``17.0`` two different elements in two different sets and silently split
    an intersection in half.
    """
    raw = spec.get("sets")
    if not isinstance(raw, dict) or not raw:
        raise SpecError(
            "'sets' must be a non-empty object mapping each set name to its member "
            'ids, e.g. {"MMLU": ["q1", "q2"], "GSM8K": ["q2", "q7"]}. Give '
            "'intersections' + 'set_names' instead if you already have the counts."
        )
    names: list[str] = []
    for name in raw:
        # Validated rather than coerced: a set name is drawn as a row label
        # next to the dot matrix, and str() of some other object would put a
        # repr on the figure instead of failing.
        if not isinstance(name, str):
            raise SpecError(
                f"'sets' has the non-string key {name!r}. A set name is drawn as a row "
                "label beside the matrix, so it has to be text."
            )
        names.append(name)
    members: list[set] = []
    for name in names:
        ids = raw[name]
        if not isinstance(ids, list):
            raise SpecError(f"sets[{name!r}] must be a list of member ids, got {type_name(ids)}")
        if not ids:
            raise SpecError(
                f"sets[{name!r}] is empty. A set with no members draws a bar of zero and "
                "a row of blank dots, which reads as a set that was measured and found "
                "to overlap nothing — drop it from the spec instead."
            )
        seen: set = set()
        for j, member in enumerate(ids):
            if isinstance(member, bool) or not isinstance(member, str | int):
                raise SpecError(
                    f"sets[{name!r}][{j}] is {member!r} — a member id must be a string or "
                    "an integer. Ids are matched across sets by equality, so anything "
                    "else either fails to match or matches by accident."
                )
            if member in seen:
                raise SpecError(
                    f"sets[{name!r}][{j}] repeats the id {member!r}. Membership is a set, "
                    "so the repeat cannot mean two elements — either the id is wrong or "
                    "the list is a multiset this chart cannot represent."
                )
            seen.add(member)
        members.append(seen)
    return names, members


def _explicit_combinations(spec: dict) -> tuple[list[str], dict[tuple[int, ...], int]]:
    """Set names and combination sizes, from ``intersections`` + ``set_names``."""
    names = spec.get("set_names")
    if not isinstance(names, list) or not names or not all(isinstance(n, str) and n for n in names):
        raise SpecError(
            "'set_names' must be a non-empty list of set names when 'intersections' is "
            "given — it is the list every intersection is checked against, so that a "
            "typo in a name cannot quietly become a set of its own."
        )
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise SpecError(f"'set_names' repeats {sorted(duplicates)} — each set appears once")
    index = {name: i for i, name in enumerate(names)}

    entries = spec.get("intersections")
    if not isinstance(entries, list) or not entries:
        raise SpecError(
            "'intersections' must be a non-empty list of "
            '{"sets": ["MMLU", "GSM8K"], "size": 240} entries'
        )
    counts: dict[tuple[int, ...], int] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise SpecError(f"intersections[{i}] must be an object, got {type_name(entry)}")
        combo = entry.get("sets")
        if not isinstance(combo, list) or not combo:
            raise SpecError(
                f"intersections[{i}].sets must be a non-empty list of set names — a "
                "column of the matrix is the elements in exactly those sets."
            )
        indices: list[int] = []
        for j, name in enumerate(combo):
            if name not in index:
                raise SpecError(
                    f"intersections[{i}].sets[{j}] names {name!r}, which is not one of "
                    f"'set_names' ({', '.join(names)}). A column can only mark sets the "
                    "matrix has a row for, so this one would be drawn against the wrong "
                    "sets or dropped."
                )
            if index[name] in indices:
                raise SpecError(
                    f"intersections[{i}].sets[{j}] repeats {name!r} — an element is "
                    "either in a set or not, so naming it twice cannot mean anything."
                )
            indices.append(index[name])
        key = tuple(sorted(indices))
        if key in counts:
            raise SpecError(
                f"intersections[{i}] repeats the combination "
                f"{{{', '.join(names[k] for k in key)}}}, which already has a size. Two "
                "sizes for one column cannot both be drawn — add them up in the spec."
            )
        size = _scalar(entry.get("size"), f"intersections[{i}].size")
        if size <= 0 or size != int(size):
            raise SpecError(
                f"intersections[{i}].size is {size:g}; it must be a whole number above "
                "zero. A size of zero has no bar to draw but still takes a column, and "
                "the combination simply does not occur — leave it out."
            )
        counts[key] = int(size)
    return names, counts


def _upset_data(spec: dict) -> tuple[list[str], dict[tuple[int, ...], int], list[int]]:
    """Set names, EXCLUSIVE combination sizes, and per-set totals.

    Exclusive is the definition the reader is entitled to assume from a chart
    whose bars sit side by side: every element is counted in exactly one
    column, the one naming precisely the sets it belongs to, so the columns
    partition the union and their heights add up to it. The inclusive reading
    — "at least these sets" — double-counts every element in three sets or
    more, and produces bars that sum to well over the data.
    """
    has_sets, has_explicit = spec.get("sets") is not None, spec.get("intersections") is not None
    if has_sets and has_explicit:
        raise SpecError(
            "'sets' and 'intersections' are both given, and they are two different "
            "sources of truth for the same bars — the members would be counted and the "
            "stated sizes ignored, or the reverse. Keep whichever one is the data."
        )
    if not has_sets and not has_explicit:
        raise SpecError(
            "an UpSet plot needs either 'sets' (name -> member ids, intersections are "
            "computed) or 'intersections' + 'set_names' (the counts, already computed)"
        )

    if has_sets:
        names, members = _membership(spec)
        counts: dict[tuple[int, ...], int] = {}
        for element in set().union(*members):
            key = tuple(i for i, group in enumerate(members) if element in group)
            counts[key] = counts.get(key, 0) + 1
        totals = [len(group) for group in members]
    else:
        names, counts = _explicit_combinations(spec)
        totals = [sum(size for key, size in counts.items() if i in key) for i in range(len(names))]
        for i, total in enumerate(totals):
            if total == 0:
                raise SpecError(
                    f"set_names[{i}] {names[i]!r} appears in no intersection, so its row "
                    "would be a blank line and its size bar zero. Add the intersection "
                    "it belongs to, or drop the set."
                )

    if len(names) < 2:
        raise SpecError(
            f"'{'sets' if has_sets else 'set_names'}' has {len(names)} set. An "
            "intersection plot compares the overlap BETWEEN sets, so one set has "
            'nothing to show — use "type": "bar" for a single set\'s size.'
        )
    if len(names) > _MAX_SETS:
        raise SpecError(
            f"{len(names)} sets is past what the matrix can show legibly (max "
            f"{_MAX_SETS}): the rows become thinner than their own names. Group the "
            "smaller sets together, or split the figure."
        )
    return names, counts, totals


def _upset_columns(
    spec: dict, counts: dict[tuple[int, ...], int]
) -> tuple[list[tuple[tuple[int, ...], int]], str]:
    """The columns to draw, in order, plus a note saying what was left out.

    Anything hidden is stated ON the figure. A truncated UpSet is a normal,
    honest chart — the tail of one-element intersections is genuinely not
    worth forty columns — but only while the reader can see that the columns
    shown are not all of them.
    """
    order = spec.get("sort", "size")
    if order not in {"size", "degree"}:
        raise SpecError(
            f"'sort' is {order!r} — use \"size\" (largest intersection first) or "
            '"degree" (fewest sets first, largest first within each degree)'
        )
    items = list(counts.items())
    if order == "size":
        items.sort(key=lambda kv: (-kv[1], len(kv[0]), kv[0]))
    else:
        items.sort(key=lambda kv: (len(kv[0]), -kv[1], kv[0]))

    notes = []
    total_columns = len(items)
    floor = _scalar(spec["min_size"], "min_size") if spec.get("min_size") is not None else None
    if floor is not None:
        kept = [kv for kv in items if kv[1] >= floor]
        if len(kept) < len(items):
            notes.append(f"{len(items) - len(kept)} below {floor:g} not shown")
        items = kept
    limit = _positive_int(spec, "max_intersections", None, maximum=_MAX_INTERSECTIONS)
    if limit is not None and len(items) > limit:
        items = items[:limit]

    if not items:
        raise SpecError(
            "no intersection survives 'min_size' — every column would be hidden and the "
            "figure would be an empty grid. Lower the threshold."
        )
    if len(items) > _MAX_INTERSECTIONS:
        raise SpecError(
            f"{len(items)} intersections is past what one row of bars can show (max "
            f"{_MAX_INTERSECTIONS}). Set 'max_intersections' to keep the largest, or "
            "'min_size' to drop the tail — either way the figure will say so."
        )
    if len(items) < total_columns:
        notes.insert(0, f"{len(items)} of {total_columns} intersections shown")
    return items, "; ".join(notes)


def render_upset(ax, spec: dict) -> None:
    """Set intersections as sorted bars over a dot matrix of memberships.

    Every column is one EXCLUSIVE intersection: the elements in exactly the
    sets its filled dots name and in none of the others. The bars above give
    each intersection's size, sorted largest first; the bars at the left give
    each set's own total. Because the columns partition the union, their
    heights add up to it — a bar chart of overlaps that double-counted would
    not.

    Choose it whenever more than two sets have to be compared for overlap:
    which benchmarks a model gets right, which items three annotators agreed
    on, how much two training corpora share. A Venn diagram is the reflex here
    and it fails at exactly this point — three circles cannot be drawn with
    regions in proportion, four need shapes that stop reading as sets, and
    beyond that the figure is decorative. Choose ``bar`` instead when only the
    per-set sizes matter and the overlap does not; choose ``heatmap`` when the
    question is genuinely pairwise (an overlap matrix), since that shows every
    pair at once but cannot express "in A and B but not C", which is the whole
    reason to reach for this chart.

    With ``sets`` the intersections are COMPUTED from the members, so they
    cannot disagree with the data. With ``intersections`` they are taken as
    given, and every named set is checked against ``set_names``.

    Keys: ``sets`` (name -> member ids) OR ``intersections``
    (``[{"sets": [...], "size": n}]``) + ``set_names``; ``sort`` ("size" or
    "degree"); ``min_size`` and ``max_intersections`` to trim the tail (what
    is hidden is noted on the figure); ``ylabel`` (default "Intersection
    size"); ``size_label`` (default "Set size"); ``annotate`` (counts above
    the bars, default true). Give ``aspect`` a taller ratio past about six
    sets, e.g. "16:11".
    """
    names, counts, totals = _upset_data(spec)
    columns, note = _upset_columns(spec, counts)
    n_sets, n_cols = len(names), len(columns)
    sizes = np.asarray([size for _, size in columns], dtype=float)
    axes_w, axes_h = _axes_inches(ax, spec)

    # The name column is measured, not guessed: it sits between the set-size
    # bars and the matrix, and a name wider than the gap runs over the dots.
    name_pt = 9.5
    name_w = max(_text_inches(ax, literal(name), name_pt)[0] for name in names) + 0.10
    if name_w > 0.34 * axes_w:
        # Any ``key=len`` form (max or sorted) infers the element as `Sized`,
        # which the slice below cannot subscript. Comparing lengths directly
        # keeps it a `str`.
        widest = max(len(n) for n in names)
        longest = next(n for n in names if len(n) == widest)
        raise SpecError(
            f"set name {longest[:45]!r} needs {name_w:.1f} inches beside the matrix, "
            f"more than a third of the figure. Shorten the names and explain them in "
            "the caption, or widen the figure with 'width_in'."
        )

    # Three regions inside the axes we were given, in its own fraction
    # coordinates: bars top-right, matrix bottom-right, set sizes bottom-left.
    # Insets rather than subplots because a renderer owns one Axes and never
    # the figure — and because an inset stays glued to its parent's box, so
    # constrained layout can move the whole assembly as one.
    bottom = 0.14  # room for the set-size axis and its label
    matrix_h = min(0.52, max(0.20, n_sets * 0.24 / axes_h))
    size_w = 0.15
    left = size_w + name_w / axes_w
    bars = ax.inset_axes([left, bottom + matrix_h, 1.0 - left, 1.0 - bottom - matrix_h])
    matrix = ax.inset_axes([left, bottom, 1.0 - left, matrix_h])
    set_bars = ax.inset_axes([0.0, bottom, size_w, matrix_h])
    # The parent carries the title and nothing else — its own frame would draw
    # a box around three panels that already have their own.
    ax.set_axis_off()

    # One column's width on the page, which both the count labels and the dot
    # size are sized against.
    column_w = (1.0 - left) * axes_w / n_cols

    # -- intersection sizes -------------------------------------------------
    positions = np.arange(n_cols, dtype=float)
    bars.bar(positions, sizes, width=0.62, color=PALETTE[0], zorder=3)
    bars.set_xlim(-0.5, n_cols - 0.5)
    bars.set_xticks([])
    bars.set_ylabel(literal(spec.get("ylabel") or "Intersection size"))
    # ``visible=True`` explicitly: ``grid(axis="y")`` alone TOGGLES, and the
    # house style already has the horizontal grid on, so the bare call turned
    # it off and the bars lost the scale they are read against.
    bars.grid(visible=True, axis="y")
    bars.grid(visible=False, axis="x")
    # Headroom for the counts printed on top of the bars, which otherwise sit
    # on the axes' upper edge.
    bars.set_ylim(0.0, float(sizes.max()) * 1.14)
    if flag(spec, "annotate", True):
        for x, size in zip(positions, sizes, strict=True):
            text = literal(f"{int(size):,}" if float(size).is_integer() else f"{size:.3g}")
            # Skipped rather than crammed: at twenty columns the counts touch,
            # and two numbers running together are worse than none.
            if _text_inches(bars, text, 7.5)[0] < column_w * 0.92:
                bars.text(x, size, text, ha="center", va="bottom", fontsize=7.5, zorder=4)
    if note:
        # Top RIGHT, where a size-sorted bar chart is always empty.
        bars.text(
            0.995,
            0.98,
            literal(note),
            transform=bars.transAxes,
            ha="right",
            va="top",
            fontsize=7.5,
            color="#555555",
        )

    # -- membership matrix --------------------------------------------------
    rows = np.arange(n_sets, dtype=float)
    for row in rows[::2]:
        # Banding, not a grid: the reader tracks a dot back to its name along
        # the row, and a line through the dots would compete with them.
        matrix.axhspan(row - 0.5, row + 0.5, facecolor="#F4F4F4", zorder=0)
    grid_x, grid_y = np.meshgrid(positions, rows)
    # Dot size follows the tighter of the two spacings so the dots never touch.
    row_h = matrix_h * axes_h / n_sets
    dot_pt = float(np.clip(min(row_h, column_w) * 72.0 * 0.42, 4.5, 11.0))
    matrix.scatter(grid_x, grid_y, s=dot_pt**2, color=_EMPTY_DOT_INK, zorder=2)
    for x, (combo, _size) in zip(positions, columns, strict=True):
        if len(combo) > 1:
            # The connector is what makes a column read as ONE intersection
            # rather than as several unrelated dots.
            matrix.plot([x, x], [min(combo), max(combo)], color=_DOT_INK, linewidth=1.6, zorder=3)
        matrix.scatter(np.full(len(combo), x), list(combo), s=dot_pt**2, color=_DOT_INK, zorder=4)
    matrix.set_xlim(-0.5, n_cols - 0.5)
    matrix.set_ylim(n_sets - 0.5, -0.5)  # first set at the top, as the names read
    matrix.set_xticks([])
    matrix.set_yticks([])
    matrix.grid(visible=False)
    for spine in matrix.spines.values():
        spine.set_visible(False)

    # -- set sizes ----------------------------------------------------------
    set_bars.barh(rows, totals, height=0.55, color=PALETTE[5], zorder=3)
    set_bars.set_ylim(n_sets - 0.5, -0.5)
    set_bars.invert_xaxis()  # bars grow away from the matrix, as UpSet reads
    # Names on the RIGHT of these bars, i.e. in the gap measured out above,
    # directly against the matrix row they label.
    set_bars.yaxis.tick_right()
    set_bars.set_yticks(rows, labels=[literal(name) for name in names], fontsize=name_pt)
    set_bars.tick_params(axis="y", length=0, pad=3)
    set_bars.tick_params(axis="x", labelsize=7.5)
    set_bars.set_xlabel(literal(spec.get("size_label") or "Set size"), fontsize=8.5)
    set_bars.locator_params(axis="x", nbins=2)
    set_bars.grid(visible=True, axis="x")
    set_bars.grid(visible=False, axis="y")
    # Both vertical spines go: the left one is the far end of the bars, the
    # right one would run through the names.
    for side in ("left", "right"):
        set_bars.spines[side].set_visible(False)


# --------------------------------------------------------------------------
# treemap — hierarchical composition
# --------------------------------------------------------------------------


def _worst_ratio(row: list[float], side: float) -> float:
    """Worst aspect ratio in a row of areas laid along a side of ``side``."""
    total = sum(row)
    return max(side * side * max(row) / (total * total), total * total / (side * side * min(row)))


def _squarify(areas: list[float], x: float, y: float, dx: float, dy: float) -> list[tuple]:
    """Lay out ``areas`` in the rectangle at ``(x, y)`` of size ``dx`` by ``dy``.

    The squarified treemap of Bruls, Huizing and van Wijk: take the areas in
    descending order and keep adding them to a row along the shorter side of
    what is left, for as long as doing so improves the worst aspect ratio in
    that row; then cut the row off and repeat on the remainder.

    Two properties matter and both are exact rather than approximate. Each
    rectangle's area IS its value — the height is computed as ``value /
    width``, so the multiplication that a reader performs by eye is the one
    that produced the shape. And the layout is deterministic, so a spec
    re-rendered gives the same picture.

    The alternative — slice-and-dice, which just cuts strips — is simpler and
    produces slivers: a rectangle 40 times longer than it is wide reads as a
    line, and its area cannot be judged at all.
    """
    rects: list[tuple] = []
    index = 0
    while index < len(areas):
        # Rows run along the SHORTER side; along the longer one every row
        # would be a sliver, which is the failure this algorithm exists to fix.
        side = min(dx, dy)
        row = [areas[index]]
        end = index + 1
        while end < len(areas) and _worst_ratio([*row, areas[end]], side) <= _worst_ratio(
            row, side
        ):
            row.append(areas[end])
            end += 1
        total = sum(row)
        if dy <= dx:
            width = total / dy
            offset = y
            for value in row:
                height = value / width
                rects.append((x, offset, width, height))
                offset += height
            x, dx = x + width, dx - width
        else:
            height = total / dx
            offset = x
            for value in row:
                width = value / height
                rects.append((offset, y, width, height))
                offset += width
            y, dy = y + height, dy - height
        index = end
    return rects


def _treemap_items(spec: dict) -> tuple[list[str], list[float], list[str | None]]:
    """Labels, values and optional groups, with everything unplottable refused."""
    items = spec.get("items")
    if not isinstance(items, list) or not items:
        raise SpecError(
            "'items' must be a non-empty list. Each item is "
            '{"label": "Retrieval", "value": 128}, with an optional "group" for a '
            "second level."
        )
    if len(items) > _MAX_LEAVES:
        raise SpecError(
            f"{len(items)} rectangles is past what a treemap can show (max "
            f"{_MAX_LEAVES}): most would be too small to label, leaving colour alone to "
            "carry them. Roll the tail into an 'Other' item."
        )
    labels, values, groups = [], [], []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise SpecError(f"items[{i}] must be an object, got {type_name(item)}")
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise SpecError(
                f"items[{i}].label is {label!r} — every rectangle needs a name. An area "
                "with nothing to identify it cannot be read off the figure at all."
            )
        value = _scalar(item.get("value"), f"items[{i}].value")
        if value < 0:
            raise SpecError(
                f"items[{i}].value is {value:g}. A rectangle's AREA is its value, and "
                "there is no negative area to draw — the item would either vanish or "
                'fold over its neighbour. Use "type": "diverging" or "waterfall" for a '
                "signed quantity."
            )
        if value == 0:
            raise SpecError(
                f"items[{i}].value is 0, so its rectangle has no area and the item "
                "disappears from a figure whose caption still counts it. Drop the item, "
                "or say zero in the text. (If every value is zero there is no "
                "composition to show at all.)"
            )
        group = item.get("group")
        if group is not None and (not isinstance(group, str) or not group.strip()):
            raise SpecError(f"items[{i}].group must be a non-empty string, got {group!r}")
        labels.append(label)
        values.append(value)
        groups.append(group)
    if any(g is not None for g in groups) and not all(g is not None for g in groups):
        missing = next(i for i, g in enumerate(groups) if g is None)
        raise SpecError(
            f"items[{missing}] has no 'group' while other items do. A treemap is one "
            "level or two, not both — an ungrouped item has no parent rectangle to sit "
            "in. Give every item a group, or none."
        )
    return labels, values, groups


def _wrapped(name: str, lines: int) -> str:
    """``name`` folded onto at most ``lines`` lines, never breaking a word.

    A tall narrow rectangle is the common shape in a squarified layout and it
    fits "Restart after / loss spike" comfortably while refusing the same
    words on one line. Long words are left whole: half of "Contamination" is
    not a shorter label, it is a different one.
    """
    if lines == 1:
        return name
    return "\n".join(textwrap.wrap(name, -(-len(name) // lines), break_long_words=False))


def _label_rect(ax, rect: tuple, name: str, value_text: str, face) -> bool:
    """Write a rectangle's name and value inside it, or write nothing.

    Fits are measured, and a label that does not fit is dropped. The
    alternatives are both defects: clipping cuts a name to its first
    characters, which misidentifies the rectangle it sits on, and letting it
    overflow prints it across the neighbour it does not belong to. A reader
    who cannot see a name looks at the caption; a reader who sees the wrong
    name does not know to.

    Returns whether anything was written, so the caller can SAY how many
    rectangles went unnamed. Dropping silently was the older behaviour and it
    left a reader with a blank rectangle and no way to know one existed —
    ``upset`` already prints "10 of 12 intersections shown" for exactly this.

    What is given up, in order: the size of the type, then the line breaks,
    then the value line, then everything. A rectangle labelled "Retrieval" is
    still useful; one labelled "128" is not.
    """
    x, y, width, height = rect
    pad, gap = 0.05, 0.02
    centre_x, centre_y = x + width / 2.0, y + height / 2.0
    ink = ink_on(face)

    def draw(text: str, size_pt: float, offset_in: float, *, dim: bool = False):
        # The offset is in POINTS, i.e. in the units the text itself is set
        # in, so the two lines keep their spacing whatever scale the data
        # axis ends up at. Offsetting in DATA units instead tied the gap
        # between the name and its value to the axes' aspect ratio: in a
        # panel cell, where the axes came out a third shorter than estimated,
        # the two lines closed up and printed over each other. Points are
        # also measured UP the page, which the inverted y-axis would have
        # flipped.
        ax.annotate(
            text,
            (centre_x, centre_y),
            textcoords="offset points",
            xytext=(0.0, offset_in * 72.0),
            ha="center",
            va="center",
            fontsize=size_pt,
            color=ink,
            alpha=0.85 if dim else 1.0,
            zorder=5,
            linespacing=1.15,
            annotation_clip=False,
        )

    for name_pt, value_pt in ((10.0, 8.0), (8.5, 7.0)):
        for lines in (1, 2, 3):
            text = _wrapped(name, lines)
            name_w, name_h = _text_inches(ax, text, name_pt)
            value_w, value_h = _text_inches(ax, value_text, value_pt)
            if (
                max(name_w, value_w) + 2 * pad <= width
                and name_h + value_h + gap + 2 * pad <= height
            ):
                block = name_h + value_h + gap
                draw(text, name_pt, (block - name_h) / 2.0)
                draw(value_text, value_pt, -(block - value_h) / 2.0, dim=True)
                return True
    for name_pt in (10.0, 8.5, 7.0):
        for lines in (1, 2, 3):
            text = _wrapped(name, lines)
            name_w, name_h = _text_inches(ax, text, name_pt)
            if name_w + 2 * pad <= width and name_h + 2 * pad <= height:
                draw(text, name_pt, 0.0)
                return True
    return False


def render_treemap(ax, spec: dict) -> None:
    """Nested rectangles whose AREA is proportional to their value.

    The whole figure is the total; each rectangle's share of it is that item's
    share of the total, laid out by the squarified algorithm so the shapes
    stay close to square and remain comparable. With ``group`` set on the
    items the layout is two levels: groups are placed first, each group's
    children are laid out inside its rectangle, and the group is named in the
    legend rather than in a header strip — a header would take its area out of
    the children and quietly shrink every one of them.

    Choose it when the finding is COMPOSITION with many parts: where a token
    budget went, what a corpus is made of, how a taxonomy splits. Thirty
    labelled parts fit here and would need a bar chart three times the height.
    Choose ``bar``/``barh`` instead whenever the reader has to COMPARE values
    precisely — length is judged far more accurately than area, so ranking two
    similar items off a treemap is guesswork. Choose ``stacked_pct`` when the
    same composition is compared ACROSS groups (a treemap shows one whole
    only), ``area`` when it changes over time, and ``sankey`` when parts flow
    into other parts rather than nesting inside them.

    Values must be positive: area cannot be negative, and a zero-value item
    would vanish while the caption still counts it. Labels that do not fit
    their rectangle are dropped, never clipped or overprinted.

    Keys: ``items[].label``, ``items[].value``, ``items[].group`` (optional
    second level), ``fmt`` (value format, default ",.0f" for whole numbers and
    ".3g" otherwise), ``pct`` (append each item's share of the total),
    ``values`` (set false to label with names only).
    """
    labels, values, groups = _treemap_items(spec)
    total = float(sum(values))
    width_in, height_in = _axes_inches(ax, spec)
    # Laying out in INCHES rather than in a unit square is what makes the
    # algorithm's near-square target mean near-square ON THE PAGE, and it lets
    # the label fit test compare a rectangle against measured text directly.
    canvas = width_in * height_in

    integral = all(float(v).is_integer() for v in values)
    fmt = number_format(spec, "fmt", ",.0f" if integral else ".3g")
    show_values = spec.get("values", True)

    def value_text(value: float) -> str:
        text = format(value, fmt) if show_values else ""
        if flag(spec, "pct"):
            share = f"{value / total * 100:.1f}%"
            text = f"{text} ({share})" if text else share
        return literal(text)

    leaves: list[tuple] = []  # (rect, label, value, facecolor)
    if all(g is None for g in groups):
        order = sorted(range(len(values)), key=lambda i: -values[i])
        areas = [values[i] / total * canvas for i in order]
        for rank, rect in enumerate(_squarify(areas, 0.0, 0.0, width_in, height_in)):
            i = order[rank]
            leaves.append((rect, labels[i], values[i], to_rgba(PALETTE[rank % len(PALETTE)], 0.85)))
        outlines: list[tuple] = []
        group_names: list[str] = []
    else:
        group_names = list(dict.fromkeys(groups))  # first-appearance order, for the legend
        totals = {
            g: sum(v for v, gg in zip(values, groups, strict=True) if gg == g) for g in group_names
        }
        placed = sorted(group_names, key=lambda g: -totals[g])
        outlines = _squarify(
            [totals[g] / total * canvas for g in placed], 0.0, 0.0, width_in, height_in
        )
        for name, (gx, gy, gw, gh) in zip(placed, outlines, strict=True):
            children = sorted(
                (i for i, g in enumerate(groups) if g == name), key=lambda i: -values[i]
            )
            colour = PALETTE[group_names.index(name) % len(PALETTE)]
            # One hue per group, fading with rank inside it: the group is read
            # from the colour, the ordering from the shade, and no rectangle
            # borrows area from its neighbour to say so.
            shades = np.linspace(0.92, 0.5, len(children)) if len(children) > 1 else [0.85]
            areas = [values[i] / totals[name] * gw * gh for i in children]
            for rank, rect in enumerate(_squarify(areas, gx, gy, gw, gh)):
                i = children[rank]
                leaves.append((rect, labels[i], values[i], to_rgba(colour, float(shades[rank]))))

    unnamed: list[str] = []
    for rect, name, value, face in leaves:
        x, y, width, height = rect
        ax.add_patch(
            Rectangle(
                (x, y),
                width,
                height,
                facecolor=face,
                # White gaps rather than dark rules: the border is the space
                # between two areas, and a dark line reads as part of one.
                edgecolor="white",
                linewidth=1.0,
                zorder=2,
            )
        )
        if not _label_rect(ax, rect, literal(name), value_text(value), face):
            unnamed.append(name)
    for gx, gy, gw, gh in outlines:
        # Drawn on top and unfilled: the group boundary has to survive the
        # children's own borders without covering any of their area.
        ax.add_patch(
            Rectangle((gx, gy), gw, gh, fill=False, edgecolor="white", linewidth=2.6, zorder=4)
        )

    ax.set_xlim(0.0, width_in)
    # Inverted, so the largest rectangle lands top-left where the eye starts.
    ax.set_ylim(height_in, 0.0)
    ax.set_axis_off()
    if unnamed:
        # An unnamed rectangle is not a defect — a 0.4% slice has no room for
        # its own name at any type size a reader could use — but a SILENT one
        # is: the figure showed fourteen areas and thirteen names, and nothing
        # said which one was missing or that anything was. Same contract as
        # ``upset``'s "10 of 12 intersections shown".
        shown = len(leaves) - len(unnamed)
        ax.set_title(
            f"{shown} of {len(leaves)} named; too small to label: "
            + ", ".join(literal(name) for name in unnamed[:3])
            + (f" (+{len(unnamed) - 3} more)" if len(unnamed) > 3 else ""),
            loc="right",
            fontsize=8,
            color="#666666",
        )
    if group_names:
        place_legend(
            ax,
            handles=[
                Patch(facecolor=to_rgba(PALETTE[i % len(PALETTE)], 0.85), label=literal(name))
                for i, name in enumerate(group_names)
            ],
            loc="upper center",
            # Below the axes, where constrained layout reserves real space for
            # it. Inside, it would cover the rectangles it is explaining.
            bbox_to_anchor=(0.5, 0.0),
            ncols=min(len(group_names), 5),
        )


# --------------------------------------------------------------------------
# speedup — parallel scaling
# --------------------------------------------------------------------------


def _speedup_series(spec: dict) -> list[tuple[np.ndarray, np.ndarray, dict]]:
    """Worker counts and measured speedups, one entry per series.

    ``times`` is converted here rather than in the spec: a speedup computed by
    hand and pasted in alongside the timings is free to disagree with them,
    and the figure then reports a scaling result the measurements do not
    support.
    """
    series = _series(spec)
    parsed = []
    for i, entry in enumerate(series):
        raw_x = entry.get("x") or spec.get("x")
        if not raw_x:
            raise SpecError(f"series[{i}] needs 'x' — the worker count each point was run at")
        workers = _numbers(raw_x, f"series[{i}].x")
        if workers.size < 2:
            raise SpecError(
                f"series[{i}].x has {workers.size} point. A scaling curve needs at least "
                "two worker counts — one point cannot show a trend against the ideal."
            )
        bad = [j for j, v in enumerate(workers) if v <= 0]
        if bad:
            raise SpecError(
                f"series[{i}].x[{bad[0]}] is {workers[bad[0]]:g}. A run happens on at "
                "least one worker, and speedup is measured per worker, so zero or fewer "
                "has no meaning on this axis."
            )
        drops = [j for j in range(1, workers.size) if workers[j] <= workers[j - 1]]
        if drops:
            j = drops[0]
            raise SpecError(
                f"series[{i}].x goes {workers[j - 1]:g} -> {workers[j]:g} at index {j}. "
                "The worker count has to increase along the curve: out of order, the "
                "line doubles back on itself and the ideal reference no longer lines up "
                "with the points it is drawn against."
            )

        has_times, has_values = entry.get("times") is not None, entry.get("values") is not None
        if has_times and has_values:
            raise SpecError(
                f"series[{i}] gives both 'times' and 'values', which are two sources of "
                "truth for one curve — if they disagree the figure shows one and the "
                "table shows the other. Keep the measurements ('times') and let the "
                "speedup be computed."
            )
        if has_times:
            times = _numbers(entry.get("times"), f"series[{i}].times", expect=workers.size)
            slow = [j for j, v in enumerate(times) if v <= 0]
            if slow:
                raise SpecError(
                    f"series[{i}].times[{slow[0]}] is {times[slow[0]]:g}. Speedup is a "
                    "ratio of run times, so a time of zero or less has no ratio to take."
                )
            speedup = float(times[0]) / times
        elif has_values:
            speedup = _numbers(entry.get("values"), f"series[{i}].values", expect=workers.size)
            slow = [j for j, v in enumerate(speedup) if v <= 0]
            if slow:
                raise SpecError(
                    f"series[{i}].values[{slow[0]}] is {speedup[slow[0]]:g}. A speedup is "
                    "how many times FASTER the run got, so it is above zero — a slowdown "
                    "is a value below 1, not below 0."
                )
        else:
            raise SpecError(
                f"series[{i}] needs 'values' (measured speedup) or 'times' (wall-clock "
                "time per worker count, from which the speedup is computed)"
            )
        parsed.append((workers, speedup, entry))

    baselines = {float(workers[0]) for workers, _, _ in parsed}
    if len(baselines) > 1:
        raise SpecError(
            f"the series start at different worker counts ({sorted(baselines)}). Speedup "
            "is measured against the smallest one, so curves with different baselines "
            "are different quantities plotted on one axis — and a single ideal line "
            "cannot serve both. Re-baseline them, or split the figure."
        )
    return parsed


def _log_base(ticks: list[float]) -> int:
    """Base 2 for power-of-two worker counts, base 10 otherwise.

    1/2/4/8/16 is the near-universal shape of a scaling sweep, and on a base-10
    axis those points bunch towards the left with the ticks between them
    unlabelled. The choice is presentational — the data plots identically —
    so it is made from the data rather than asked for.
    """
    powers = all(v >= 1 and float(v).is_integer() and int(v) & (int(v) - 1) == 0 for v in ticks)
    return 2 if powers else 10


def render_speedup(ax, spec: dict) -> None:
    """Measured speedup against worker count, with the ideal linear reference.

    Each series is speedup relative to the smallest worker count plotted,
    either given directly or computed here from wall-clock ``times``. The grey
    diagonal is perfect linear scaling; the gap between a curve and that
    diagonal is the finding. With ``efficiency`` set, speedup / (workers /
    baseline) is drawn on a right-hand axis as a percentage, which is the same
    information rescaled so that a flat line means scaling is holding up.

    Choose it for any parallel or distributed result — data-loader workers,
    GPUs on a training job, shards in a retrieval index. The ideal line is
    what makes it a scaling figure rather than a line chart: 8x on 32 workers
    looks like a win in isolation and is 25% efficiency next to the diagonal.
    Choose ``line`` when the y-axis is a raw measurement (throughput,
    latency) and there is no reference to compare against; ``scaling`` when
    the relationship is a power law over orders of magnitude and the fitted
    exponent is the result, which is a different question from how close to
    linear a fixed set of workers gets; ``pareto`` when the trade-off is
    against cost rather than against the ideal.

    Keys: ``series[].x`` (worker counts — increasing, above zero),
    ``series[].values`` (measured speedup) OR ``series[].times`` (wall-clock
    time per point; the speedup is derived), ``series[].label``,
    ``efficiency`` (right-hand axis), ``logx``/``logy`` (base 2 when every
    worker count is a power of two), ``legend_loc``.
    """
    parsed = _speedup_series(spec)
    baseline = float(parsed[0][0][0])
    show_efficiency = flag(spec, "efficiency")
    twin = None
    if show_efficiency:
        # A twin, not an inset: efficiency shares the x-axis exactly and only
        # needs a second scale. It is derived from the Axes we were given, so
        # ``panel`` still owns the figure.
        twin = ax.twinx()

    handles = []
    for i, (workers, speedup, entry) in enumerate(parsed):
        colour = PALETTE[i % len(PALETTE)]
        marker = _MARKERS[i % len(_MARKERS)]
        ax.plot(workers, speedup, marker=marker, color=colour, linewidth=1.8, zorder=3)
        handles.append(
            Line2D(
                [],
                [],
                color=colour,
                marker=marker,
                label=literal(entry.get("label") or f"Series {i + 1}"),
            )
        )
        if twin is not None:
            twin.plot(
                workers,
                speedup / (workers / baseline),
                linestyle=":",
                marker=marker,
                markerfacecolor="none",
                markersize=4.5,
                color=colour,
                linewidth=1.3,
                zorder=2,
            )

    low = min(float(workers.min()) for workers, _, _ in parsed)
    high = max(float(workers.max()) for workers, _, _ in parsed)
    # Sampled rather than drawn as one segment: on a semi-log x-axis the ideal
    # is a curve in display space, and two endpoints would cut the corner.
    ideal_x = np.linspace(low, high, 200)
    ax.plot(ideal_x, ideal_x / baseline, linestyle="--", color=_GUIDE_INK, linewidth=1.2, zorder=1)
    handles.append(Line2D([], [], color=_GUIDE_INK, linestyle="--", label="Ideal (linear)"))
    if twin is not None:
        handles.append(
            Line2D(
                [],
                [],
                color=_DOT_INK,
                linestyle=":",
                marker="o",
                markerfacecolor="none",
                label="Efficiency (right axis)",
            )
        )

    ax.set_xlabel("Workers")
    ax.set_ylabel("Speedup" + ("" if baseline == 1 else f" (vs {baseline:g} workers)"))
    # Scales FIRST: changing one installs a fresh locator and formatter, so
    # fixed ticks set before this came back as 2⁰, 2¹, 2² — the worker counts
    # replaced by the exponents of the axis that happens to carry them.
    ticks = sorted({float(v) for workers, _, _ in parsed for v in workers})
    if flag(spec, "logx"):
        ax.set_xscale("log", base=_log_base(ticks))
    if flag(spec, "logy"):
        ax.set_yscale("log", base=2)
        ax.yaxis.set_minor_formatter(NullFormatter())
    if len(ticks) <= 12:
        # The worker counts ARE the x values, and a locator's own 0/5/10/15
        # would put ticks where nothing was measured.
        ax.set_xticks(ticks, labels=[f"{v:g}" for v in ticks])
        ax.xaxis.set_minor_formatter(NullFormatter())
    # Room for the whole ideal line, as long as the measurements are within
    # reach of it: the comparison a reader makes is against the diagonal, and
    # half a diagonal is half the figure's point. Scaling far enough below
    # ideal that the line would flatten the data is left to run off the top
    # instead — 'efficiency' or 'logy' is the right figure for that case.
    top = max(float(speedup.max()) for _, speedup, _ in parsed)
    if not flag(spec, "logy") and high / baseline <= 3.0 * top:
        ax.set_ylim(0.0, max(top, high / baseline) * 1.05)
    ax.grid(visible=True, axis="y")
    ax.grid(visible=False, axis="x")

    if twin is not None:
        efficiencies = [
            float((speedup / (workers / baseline)).max()) for workers, speedup, _ in parsed
        ]
        twin.set_ylim(0.0, max(1.05, max(efficiencies) * 1.12))
        twin.yaxis.set_major_formatter(PercentFormatter(xmax=1.0))
        twin.set_ylabel("Parallel efficiency")
        # The house style hides the right spine on every axes; here it is the
        # one the efficiency ticks belong to, so it comes back and the others go.
        twin.spines["right"].set_visible(True)
        for side in ("left", "top", "bottom"):
            twin.spines[side].set_visible(False)
        # One grid, not two: a second set of horizontal lines at different
        # values reads as a misprint.
        twin.grid(visible=False)

    requested = legend_place(spec)
    if requested:
        place_legend(ax, handles=handles, loc=requested, ncols=1 if len(handles) <= 5 else 2)
    elif twin is not None:
        # With efficiency on, the upper left is NOT free: efficiency starts at
        # 100% and runs along the top of the axes, and an inside legend landed
        # on it. Outside, constrained layout reserves real space and the
        # overlap becomes impossible rather than merely unlikely.
        #
        # A FIGURE legend at "outside lower center", not an axes legend at a
        # fraction of the axes height. That fraction is fewer pixels the
        # shorter the axes gets, while the tick labels and x-label keep their
        # size — at 21:9 the old anchor put the legend 17 px over "GPUs", and
        # the text gate missed it because the boxes overlapped and the ink did
        # not quite. Constrained layout reserves the strip instead, so the
        # distance is not a guess.
        place_legend(
            ax.figure,
            handles,
            [h.get_label() for h in handles],
            loc="outside lower center",
            ncols=min(len(handles), 4),
        )
    else:
        # A speedup chart's data climbs to the right, so the corner above the
        # ideal line is the one that is always empty.
        place_legend(ax, handles=handles, loc="upper left", ncols=1 if len(handles) <= 5 else 2)


# --------------------------------------------------------------------------
# raincloud — distribution, summary and observations at once
# --------------------------------------------------------------------------


def render_raincloud(ax, spec: dict) -> None:
    """Half violin, box and jittered raw points, one column per group.

    Three views of the same samples, side by side and to the same y-scale: the
    cloud is a kernel density (normalised to its own peak, so the columns
    compare SHAPE), the box gives median, quartiles and 1.5-IQR whiskers, and
    the rain is every observation, jittered horizontally so equal values do
    not stack. n is printed above each group. The jitter is seeded, so
    re-rendering a spec gives the same picture.

    Choose it over ``violin`` whenever the reader has to see the observations
    as well as the shape — which is most of the time in a results section,
    because a density curve drawn through twelve seeds looks exactly as smooth
    and confident as one drawn through twelve thousand samples, and only the
    points can tell them apart. Choose ``box`` when space is tight and the
    quartiles are genuinely all that is claimed; ``strip`` when n is small
    enough that the density and the box would both be over-claiming (below
    about five observations this refuses to draw for that reason);
    ``ridgeline`` past about six groups, where columns run out of width and
    rows do not; ``ecdf`` when the comparison is specifically about tails or a
    threshold.

    The box deliberately draws no fliers: the rain already shows every
    outlier, and a second marker on top of the same observation reads as two.

    Keys: ``series[].values``, ``series[].label``, ``jitter`` (half-width in
    column units, default 0.09), ``seed`` (jitter RNG, default 0),
    ``bandwidth`` (override Silverman's rule), ``counts`` (the "n = " labels,
    default true).
    """
    data, labels = _grouped(spec)
    for i, values in enumerate(data):
        if values.size < _MIN_RAIN_SAMPLES:
            raise SpecError(
                f"series[{i}].values has {values.size} observations, fewer than the "
                f"{_MIN_RAIN_SAMPLES} a density curve and a quartile box need. The curve "
                "would imply a shape the data cannot support and the box would draw "
                'quartiles from single values. Use "type": "strip", which shows the same '
                "observations without the smoothing."
            )
    jitter = number_option(spec, "jitter", 0.09, minimum=0.0)
    if not 0.0 <= jitter < 0.2:
        raise SpecError(
            f"'jitter' is {jitter:g}; it must be at least 0 and under 0.2. Wider than "
            "that the rain spreads under the neighbouring column and a point can no "
            "longer be attributed to the group it belongs to."
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

    # Offsets within a column, in column units. The cloud sits to the right of
    # the tick, the box just left of it, the rain further left again — the
    # three never overlap, so nothing hides anything else.
    cloud_gap, cloud_width, box_offset, box_width, rain_offset = 0.05, 0.38, 0.03, 0.12, 0.24
    for i, values in enumerate(data):
        position = float(i + 1)
        colour = PALETTE[i % len(PALETTE)]
        bandwidth = _bandwidth(values, f"series[{i}].values", spec.get("bandwidth"))
        # Evaluated between the smallest and largest observation only. Running
        # the grid past them draws density where nothing was measured, which
        # on a bounded metric puts mass beyond 100% or below zero.
        grid = np.linspace(float(values.min()), float(values.max()), _KDE_GRID)
        density = _kde(values, grid, bandwidth)
        density = density / density.max() * cloud_width
        edge = position + cloud_gap + density
        ax.fill_betweenx(
            grid, position + cloud_gap, edge, facecolor=colour, alpha=0.5, linewidth=0, zorder=2
        )
        ax.plot(edge, grid, color=colour, linewidth=1.1, zorder=3)

        box = ax.boxplot(
            [values],
            positions=[position - box_offset],
            widths=box_width,
            patch_artist=True,
            # The rain IS the outliers, drawn once. Left on, every extreme
            # observation would carry a flier on top of its own point.
            showfliers=False,
            # Without this, boxplot takes over the x ticks and limits — set
            # once per group, the last group would win and the labels would
            # come out one column wide.
            manage_ticks=False,
            medianprops={"color": "#1a1a1a", "linewidth": 1.5},
            boxprops={"facecolor": "white", "edgecolor": colour, "linewidth": 1.0},
            whiskerprops={"color": _DOT_INK, "linewidth": 1.0},
            capprops={"color": _DOT_INK, "linewidth": 1.0},
        )
        for group in box.values():
            for artist in group:
                artist.set_zorder(5)

        ax.scatter(
            position - rain_offset + rng.uniform(-jitter, jitter, values.size),
            values,
            s=17,
            facecolor=to_rgba(colour, 0.6),
            # An opaque white rim survives the face alpha, so two coincident
            # observations still read as two points rather than one dark one.
            edgecolor="white",
            linewidths=0.4,
            zorder=4,
        )

    ax.set_xticks(np.arange(1, len(data) + 1, dtype=float), labels=labels)
    ax.set_xlim(0.5, len(data) + 0.5)
    # Six groups of long names ran together into one unreadable line inside a
    # panel cell; this wraps them, or rotates them once wrapping stops helping.
    ax.grid(visible=True, axis="y")
    ax.grid(visible=False, axis="x")
    if flag(spec, "counts", True):
        # Above the data, in the axes' own top margin: n belongs to the group
        # and has to sit where no cloud can grow into it.
        ax.margins(y=0.10)
        for i, values in enumerate(data):
            ax.text(
                i + 1.0,
                0.99,
                literal(f"n = {values.size}"),
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=8,
                color="#555555",
            )


SETS_RENDERERS = {
    "upset": render_upset,
    "treemap": render_treemap,
    "speedup": render_speedup,
    "raincloud": render_raincloud,
}
