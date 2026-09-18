"""What the figure actually put where — the gates that read the drawn pixels.

Two post-render gates already existed, and each retired a whole class of
silent defect the day it was written: ``assert_layout_applied`` for collapsed
axes, ``assert_all_glyphs_rendered`` for hollow boxes. Both work by reading
matplotlib's warnings. The two here work by reading GEOMETRY, and they cover
the two remaining ways a figure loses text without anyone being told:

* **collision** — a label printed over another label. A legend on a data
  point, an annotation through a tick, two category names in the same pixels.
* **clipping** — a label running off the canvas. A 300-character x-label
  rendered with 30% of itself visible, cut off mid-word at both ends, at exit
  0 with no warning. The figure looks fine until someone reads the axis.

Nothing here estimates. Once the figure is drawn, every ``Text`` reports the
box it occupies, so both questions are arithmetic on those boxes.

Three corrections were needed before the answers could be trusted, and each
was a false positive that made an earlier version useless:

* **Undrawn ticks.** A locator places ticks across the whole data range and
  keeps a ``Text`` for every one, then paints only those inside the view. The
  rest still report an extent — usually off the side of the canvas — which
  read as labels running off the edge on 13 of the 47 catalogue figures.
  Charts that draw their own geometry (``radar``, ``treemap``, ``upset``,
  ``sankey``) call ``set_axis_off()``, which likewise leaves every tick
  artist in place and merely stops painting it.

* **Child axes.** ``upset`` builds its three panels with ``inset_axes``,
  which land in ``ax.child_axes`` and never appear in ``fig.axes``. Walking
  only ``fig.axes`` missed them, so their undrawn ticks came back as
  collisions with the title.

* **Rotation.** ``get_window_extent`` returns the axis-aligned box AROUND
  rotated glyphs, which for a 35-degree label is far larger than its ink. Two
  adjacent tick labels on a ``corr`` matrix overlap 90% by that measure and
  not at all to the eye, so the ORIENTED box is what gets compared.
"""

from __future__ import annotations

import itertools
import math

import matplotlib.text

# Text extents include the font's leading and side bearings — reserved space
# that is never inked. Two lines of a wrapped title touch by that margin
# without a reader seeing anything, so boxes are trimmed to approximate ink
# before being compared. Height carries most of the slack (ascender and
# descender space); width carries very little.
_INK_HEIGHT = 0.74
_INK_WIDTH = 0.94

# How much of the smaller label must be covered before it counts as a
# collision. Measured, not chosen: across the 47 catalogue examples and the
# stress corpus the largest genuine-looking overlap is under 0.02 once boxes
# are trimmed to ink, while a deliberately collided pair scores 0.89.
_OVERLAP_TOL = 0.12

# Below this an intersection is the rounding of two boxes that merely touch.
# At 200 dpi one character is roughly 15x20 px.
_MIN_OVERLAP_PX = 6.0

# ...and above THIS the overlap is real overprint however large the labels
# are. The fraction test alone is blind to it: two long labels crossing by
# 758 px² — some two-and-a-half characters of solid ink — score 6% of the
# bigger box and pass. Measured the same way as the tolerance above: across
# the 55 catalogue examples in six layouts each, every pair over 150 px² is
# in a figure with text printed through text (a ``sankey`` reading
# "Answeredfied answers", a ``parallel`` whose axis names run through its
# legend, a ``corr`` panel whose title and panel label sit on each other),
# and no figure that reads correctly has a pair anywhere near it — the
# largest in a clean figure is under 100.
_OVERLAP_PX_FATAL = 150.0

# A label may lose this much of itself to the canvas edge before it counts as
# clipped. Every well-formed figure in the corpus keeps 100% of every label,
# so the slack exists only for antialiasing, not for real overhang.
#
# Both tolerances below are UNTESTED, and deliberately so — the band they
# describe cannot be reached through the CLI. Every figure is built with
# ``layout="constrained"`` (chart_gen: single + panel, chart_style: the
# re-layout), and nothing ever turns it off, so the engine shrinks the axes
# until the decorations fit: a label either fits whole or the layout collapses
# and fails big. Sweeping title lengths, the least-visible fraction steps
# straight from 1.00 to 0.84 with nothing in between; raising ``_MIN_VISIBLE``
# to 1.0 (refuse ANY clipping) passes the entire suite for the same reason.
# A test would have to bypass the layout engine to land in 0.97..1.00, and
# would then be pinning an arrangement this tool cannot produce.
#
# One avenue that looks like it escapes all of the above, tried and measured so
# nobody spends the afternoon on it twice: POINT NAMES. They are placed by
# ``fit_point_labels`` with ``ax.annotate`` at a pixel offset, and constrained
# layout reserves nothing for an annotation offset — so a name on the extreme
# data point ought to be free to hang off the canvas by a few pixels, which is
# precisely this band. It cannot. Sweeping a ``bubble``'s corner name from 2 to
# 68 characters, every figure keeps 100% of every label, and past 68 the spec
# validator refuses the name outright. The reason is geometric rather than
# fortunate: this check measures against the FIGURE canvas, while point names
# are drawn INSIDE the axes, and constrained layout insets the axes from the
# canvas to make room for the axis labels and ticks. Measured on that figure,
# the nearest text to the canvas edge is the x-axis label at 15.8 px, and no
# point name comes close to it. The margin that makes the layout legible is
# also what puts this band out of reach.
_MIN_VISIBLE = 0.97

# Same story, measured the same way: nothing the CLI draws loses between 0 and
# 12 px² of a label, so setting this to 0 also passes the suite.
_MIN_CLIPPED_PX = 12.0

#: Labels along one axis past which "shorten them" stops being the remedy.
#: Measured: a 7-inch canvas refuses a ``bar`` at 90 categories and a ``barh``
#: at 60, and by 40 the column is under 0.1 in wide whatever the text says.
_CROWDED_AXIS = 40


def all_axes(fig) -> list:
    """Every axes in the figure, including insets, which ``fig.axes`` omits."""
    seen, out, queue = set(), [], list(fig.axes)
    while queue:
        ax = queue.pop()
        if id(ax) in seen:
            continue
        seen.add(id(ax))
        out.append(ax)
        queue.extend(ax.child_axes)
    return out


def _undrawn_tick_labels(fig) -> set[int]:
    """Axis text matplotlib created but does not paint.

    Ticks outside the view, and — on an axes that called ``set_axis_off()`` —
    the AXIS LABEL as well. ``set_axis_off`` clears ``axison`` rather than
    hiding each artist, so ``xaxis.label`` still reports itself visible and
    still reports an extent, off at the origin. Charts that draw their own
    geometry (``radar``, ``treemap``, ``sankey``, ``parallel``) all turn the
    axis off, so passing one of them ``xlabel`` was refused with "'x' is only
    0% visible" — a clipping report about text nobody would ever have seen.
    """
    skip: set[int] = set()
    for ax in all_axes(fig):
        for axis in (ax.xaxis, ax.yaxis):
            hidden = not ax.axison or not axis.get_visible()
            if hidden and axis.label is not None:
                skip.add(id(axis.label))
            lo, hi = sorted(axis.get_view_interval())
            for tick in axis.get_major_ticks() + axis.get_minor_ticks():
                if not hidden and lo <= tick.get_loc() <= hi:
                    continue
                skip.update(id(t) for t in (tick.label1, tick.label2) if t is not None)
    return skip


def _oriented_box(
    artist, renderer, pad: float = 0.0, trim: bool = True
) -> tuple[list[tuple[float, float]], float]:
    """The artist's ink as an oriented box (four corners), plus its area.

    ``pad`` grows the box on every side. Used to ask for CLEARANCE rather
    than mere non-overlap: two tick labels that merely fail to intersect
    still read as one word — ``waterfall`` shipped "− reranking− self-
    consistency" with no space between the two labels at all.

    ``trim`` shrinks the reported extent towards the ink inside it. Right for
    the gate, which must not refuse a figure over reserved whitespace; wrong
    for the fitter, where trimming 6% off the width was enough to hide that
    exact ``waterfall`` collision.

    The axis-aligned extent of a rotated rectangle is centred on that
    rectangle's own centre, so the centre comes straight from the reported
    extent and only the side lengths need an unrotated measurement. Measuring
    at rotation 0 rather than inverting the projection avoids the singularity
    at 45 degrees, where width and height cannot be recovered from the extent
    alone.
    """
    box = artist.get_window_extent(renderer=renderer)
    centre_x, centre_y = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    angle = float(artist.get_rotation())
    if angle % 180.0 == 0.0:
        width, height = box.width, box.height
    else:
        artist.set_rotation(0)
        try:
            upright = artist.get_window_extent(renderer=renderer)
            width, height = upright.width, upright.height
        finally:
            artist.set_rotation(angle)
    width = width * (_INK_WIDTH if trim else 1.0) + 2 * pad
    height = height * (_INK_HEIGHT if trim else 1.0) + 2 * pad
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    corners = []
    for dx, dy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):  # counter-clockwise
        x, y = dx * width / 2, dy * height / 2
        corners.append((centre_x + x * cos - y * sin, centre_y + x * sin + y * cos))
    return corners, width * height


def _clip_polygon(subject: list, clipper: list) -> list:
    """Sutherland-Hodgman: the part of ``subject`` inside convex ``clipper``."""
    output = subject
    for i in range(len(clipper)):
        if not output:
            return []
        ax, ay = clipper[i]
        bx, by = clipper[(i + 1) % len(clipper)]

        def side(point, ax=ax, ay=ay, bx=bx, by=by):
            """Positive to the left of a->b; both quads are wound CCW."""
            return (bx - ax) * (point[1] - ay) - (by - ay) * (point[0] - ax)

        current, output = output, []
        previous = current[-1]
        previous_side = side(previous)
        for point in current:
            this_side = side(point)
            if this_side >= 0:
                if previous_side < 0:
                    output.append(_line_crossing(previous, point, (ax, ay), (bx, by)))
                output.append(point)
            elif previous_side >= 0:
                output.append(_line_crossing(previous, point, (ax, ay), (bx, by)))
            previous, previous_side = point, this_side
    return output


def _line_crossing(p1, p2, a, b):
    (x1, y1), (x2, y2), (x3, y3), (x4, y4) = p1, p2, a, b
    denominator = (x1 - x2) * (y3 - y4) - (y1 - y2) * (x3 - x4)
    if denominator == 0:
        return p2
    t = ((x1 - x3) * (y3 - y4) - (y1 - y3) * (x3 - x4)) / denominator
    return (x1 + t * (x2 - x1), y1 + t * (y2 - y1))


def _polygon_area(polygon: list) -> float:
    total = 0.0
    for i in range(len(polygon)):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def _bounds(corners):
    xs = [point[0] for point in corners]
    ys = [point[1] for point in corners]
    return min(xs), min(ys), max(xs), max(ys)


def drawn_texts(fig) -> list[tuple]:
    """Every text artist actually painted: ``(bounds, corners, area, text)``.

    An artist whose extent the renderer refuses to compute is dropped rather
    than raised on. This gate exists to REFUSE figures, so an unmeasurable
    artist must not become a refusal on its own — that would fail a figure
    for a matplotlib internal rather than for anything a reader would see.
    The cost is a label this pass cannot judge; the alternative is a whole
    catalogue that cannot be rendered.
    """
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    skip = _undrawn_tick_labels(fig)
    out = []
    for artist in fig.findobj(matplotlib.text.Text):
        if id(artist) in skip or not artist.get_visible():
            continue
        if not artist.get_text().strip():
            continue
        try:
            corners, area = _oriented_box(artist, renderer)
        except (RuntimeError, ValueError):
            continue
        if area > 0:
            out.append((_bounds(corners), corners, area, artist.get_text()))
    return out


def any_overlap(artists, renderer, *, clearance: float = 0.0) -> bool:
    """Does the ink of any two of these text artists come within ``clearance``?

    The same measurement ``text_collisions`` makes, over a caller-chosen set
    rather than the whole figure — so the tick-label fitter can ask "do these
    collide *yet*?" after each attempt, instead of estimating from a
    characters-per-inch rule that cannot see how wide the axes ended up.

    ``clearance`` in pixels asks for a GAP rather than mere separation. Two
    labels whose boxes stop exactly against each other do not overlap and
    still read as one word.
    """
    boxes = []
    for artist in artists:
        if not artist.get_text().strip():
            continue
        try:
            corners, _ = _oriented_box(artist, renderer, pad=clearance / 2, trim=False)
        except (RuntimeError, ValueError):
            continue
        boxes.append((_bounds(corners), corners))
    boxes.sort(key=lambda entry: entry[0][0])
    for i, (bounds_a, quad_a) in enumerate(boxes):
        for bounds_b, quad_b in boxes[i + 1 :]:
            if bounds_b[0] >= bounds_a[2]:
                break
            if bounds_b[1] >= bounds_a[3] or bounds_b[3] <= bounds_a[1]:
                continue
            if _polygon_area(_clip_polygon(quad_a, quad_b)) > 0:
                return True
    return False


def text_collisions(fig) -> list[dict]:
    """Pairs of painted labels whose ink overlaps, worst first."""
    entries = sorted(drawn_texts(fig), key=lambda entry: entry[0][0])
    hits = []
    # Sweep on x so a heatmap's few hundred cell annotations do not become a
    # quadratic scan: a pair is only measured while their x-ranges still meet.
    for i, (bounds_a, quad_a, area_a, text_a) in enumerate(entries):
        for bounds_b, quad_b, area_b, text_b in entries[i + 1 :]:
            if bounds_b[0] >= bounds_a[2]:
                break
            if bounds_b[1] >= bounds_a[3] or bounds_b[3] <= bounds_a[1]:
                continue
            overlap = _polygon_area(_clip_polygon(quad_a, quad_b))
            smaller = min(area_a, area_b)
            fraction = overlap / smaller if smaller else 0.0
            if overlap >= _MIN_OVERLAP_PX and (
                fraction > _OVERLAP_TOL or overlap >= _OVERLAP_PX_FATAL
            ):
                hits.append({"a": text_a, "b": text_b, "fraction": fraction, "px": overlap})
    hits.sort(key=lambda hit: -hit["fraction"])
    return hits


def clipped_texts(fig) -> list[dict]:
    """Painted labels that run off the canvas, worst first."""
    fig.canvas.draw()
    canvas = fig.get_window_extent(fig.canvas.get_renderer())
    frame = [
        (canvas.x0, canvas.y0),
        (canvas.x1, canvas.y0),
        (canvas.x1, canvas.y1),
        (canvas.x0, canvas.y1),
    ]
    hits = []
    for _, corners, area, text in drawn_texts(fig):
        visible = _polygon_area(_clip_polygon(corners, frame))
        fraction = visible / area if area else 1.0
        if fraction < _MIN_VISIBLE and (area - visible) >= _MIN_CLIPPED_PX:
            hits.append({"text": text, "visible": fraction})
    hits.sort(key=lambda hit: hit["visible"])
    return hits


# Where a point's name may sit, in points, tried in this order: the near ring
# first, then the same eight directions one step further out. Up-and-right
# leads because that is the corner a reader looks in, and every alternative is
# a reflection of it, so a name only ever moves somewhere a reader would still
# read as belonging to the same point.
_LABEL_RING = ((5, 4), (-5, 4), (5, -9), (-5, -9), (0, 8), (0, -13), (9, -3), (-9, -3))
_LABEL_CORNERS = (*_LABEL_RING, *((x * 2, y * 2) for x, y in _LABEL_RING))

# A hair of slack beyond the ink itself, so a name that merely grazes a point
# still counts as landing on it. The ink's own extent is measured, not assumed:
# a marker centre 5 px outside a label still painted 99 pixels INSIDE it,
# because ``scatter`` sizes in points-squared and a 34 pt² marker is 9 px
# across at 200 dpi. Testing centres alone is what let that ship.
_MARKER_CLEARANCE = 2.0

# How finely a drawn line is sampled when asking whether a label lands on it.
# A step function's horizontal run is two vertices and hundreds of pixels, so
# testing the vertices alone let "XL" sit squarely on the Pareto frontier.
_LINE_SAMPLE_PX = 4.0


def _drawn_data(ax) -> tuple[list[tuple[float, float]], list[float]]:
    """Where this axes painted data, as points, and how wide that ink is.

    ``scatter`` produces a ``PathCollection`` whose offsets are the points;
    ``plot`` produces a ``Line2D``, whose segments are sampled so that a label
    cannot be placed in the middle of a long straight run. Anything else — a
    filled band, a bar, a contour — is area rather than a curve, and a label
    over area is a different question with a different answer.

    The second return value is one radius PER POINT, in pixels — the width of
    the ink drawn at that point — so the caller can ask about the ink rather
    than about its centre. Per point rather than per axes because a bubble
    chart's markers differ by orders of magnitude; see the ``sizes`` comment
    below for what a single radius did to it.
    """
    import matplotlib.collections
    import numpy as np

    out: list[tuple[float, float]] = []
    radii_pt: list[float] = []
    for collection in ax.collections:
        if not isinstance(collection, matplotlib.collections.PathCollection):
            continue
        offsets = collection.get_offsets()
        if len(offsets) == 0:
            continue
        pixels = collection.get_offset_transform().transform(offsets)
        out.extend(map(tuple, pixels))
        sizes = collection.get_sizes()
        # ``s`` is an AREA in points squared, which is why a "34" marker is
        # not 34 points across. Kept PER POINT: a ``bubble`` chart runs from a
        # 4 px marker to an 88 px one, and one radius for the whole axes meant
        # every name was held 88 px clear of every centre — no candidate
        # position ever measured clean, so the nudger kept the first guess and
        # a small bubble's name sat on a large neighbour's face.
        if len(sizes):
            per = np.sqrt(np.asarray(sizes, dtype=float) / np.pi)
            if per.size == 1:
                radii_pt.extend([float(per[0])] * len(pixels))
            else:
                radii_pt.extend(float(r) for r in np.resize(per, len(pixels)))
        else:
            radii_pt.extend([0.0] * len(pixels))
    # Each line carries its OWN half-width (or marker radius, whichever is
    # wider) so its samples are cleared by the ink actually drawn there.
    segments: list[tuple[object, object, float]] = []
    for line in ax.lines:
        if not len(line.get_xydata()):
            continue
        marker_r = (
            float(line.get_markersize()) / 2.0
            if line.get_marker() not in ("", " ", "None", None)
            else 0.0
        )
        segments.append(
            (
                line.get_xydata(),
                line.get_transform(),
                max(marker_r, float(line.get_linewidth()) / 2.0),
            )
        )
    # An arrow drawn with ``annotate("", xy=…, xytext=…)`` is a FancyArrowPatch
    # hanging off the Annotation — not in ``ax.patches``, and ``findobj`` does
    # not reach it either. ``network``'s directed edges are all of these, so
    # without this every one of them was invisible and a node's name was
    # placed straight through the arrow arriving at it.
    for artist in ax.texts:
        if getattr(artist, "arrow_patch", None) is None:
            continue
        segments.append((np.asarray([artist.xyann, artist.xy], dtype=float), ax.transData, 0.0))
    for data, transform, seg_radius in segments:
        pixels = transform.transform(np.asarray(data, dtype=float))
        before = len(out)
        out.extend(map(tuple, pixels))
        for (x0, y0), (x1, y1) in itertools.pairwise(pixels):
            steps = int(np.hypot(x1 - x0, y1 - y0) / _LINE_SAMPLE_PX)
            if steps < 2 or steps > 4000:
                continue
            fractions = np.linspace(0.0, 1.0, steps, endpoint=False)[1:]
            out.extend((float(x0 + (x1 - x0) * t), float(y0 + (y1 - y0) * t)) for t in fractions)
        # Every sample of one line carries that line's own half-width.
        radii_pt.extend([seg_radius] * (len(out) - before))
    scale = ax.figure.dpi / 72.0
    return out, [r * scale for r in radii_pt]


def fit_point_labels(fig) -> None:
    """Move a point's name off whatever it landed on, measured after layout.

    A renderer picks the offset before the axes has its final size, so "up and
    to the right by five points" can put a name straight through a neighbouring
    marker, through a curve, or through another name. All three are invisible
    to the renderer, and the first two are invisible to the text gate as well,
    because neither a marker nor a line is text.

    Each recorded label is tried at each position in turn and keeps the first
    that is clear of the data and of every other painted label. If none is
    clear the original is kept: a figure that says what the renderer meant, and
    which the gate can then refuse on the evidence, beats one silently shuffled
    somewhere no better.
    """
    labels = getattr(fig, "aii_point_labels", [])
    if not labels:
        return
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    painted = {id(ax): _drawn_data(ax) for ax, _ in labels}
    ours = {id(annotation) for _, annotation in labels}
    skip = _undrawn_tick_labels(fig)
    # Everything already on the page that a name must not land on. Collected
    # once: it does not change while the labels move, and re-walking the figure
    # for every label at every corner turned a 60-point volcano into minutes.
    fixed: list[list[tuple[float, float]]] = []
    for artist in fig.findobj(matplotlib.text.Text):
        if id(artist) in ours or id(artist) in skip:
            continue
        if not artist.get_visible() or not artist.get_text().strip():
            continue
        try:
            fixed.append(_oriented_box(artist, renderer)[0])
        except (RuntimeError, ValueError):
            continue
    import numpy as np

    grids = {
        key: (
            np.asarray(points or [(np.inf, np.inf)], dtype=float),
            np.asarray(radii if points else [0.0], dtype=float),
        )
        for key, (points, radii) in painted.items()
    }
    placed: list[list[tuple[float, float]]] = []
    for ax, annotation in labels:
        grid, radii = grids[id(ax)]
        best, chosen = None, _LABEL_CORNERS[0]
        for corner in _LABEL_CORNERS:
            annotation.set_position(corner)
            try:
                quad, _ = _oriented_box(annotation, renderer, pad=_MARKER_CLEARANCE, trim=True)
            except (RuntimeError, ValueError):
                break
            x0, y0, x1, y1 = _bounds(quad)
            # Measure each marker against ITS OWN radius instead of inflating
            # the box by the largest one on the axes. The old form asked "is
            # this centre inside a box grown by the biggest marker" — on a
            # ``bubble`` chart, where radii run 4 px to 88 px, that swallowed
            # every candidate position and the nudger kept its first guess.
            # Distance-to-box against the per-point radius is both narrower
            # and what the question actually is: does the name touch the ink.
            dx = np.maximum(np.maximum(x0 - grid[:, 0], grid[:, 0] - x1), 0.0)
            dy = np.maximum(np.maximum(y0 - grid[:, 1], grid[:, 1] - y1), 0.0)
            inside = (dx * dx + dy * dy) <= radii * radii
            # Scored rather than accepted or rejected. On a dense scatter every
            # position touches something, and "the first one that is perfect,
            # else the one you started with" then always kept the start —
            # ``pareto`` ended up back on its own frontier line. Least bad is a
            # real answer; first-or-nothing is not.
            penalty = float(inside.sum()) + sum(
                _polygon_area(_clip_polygon(quad, other)) for other in fixed + placed
            )
            if best is None or penalty < best:
                best, chosen = penalty, corner
            if penalty == 0:
                break
        annotation.set_position(chosen)
        placed.append(_oriented_box(annotation, renderer, trim=True)[0])
    fig.canvas.draw()


def assert_text_is_legible(fig) -> None:
    """Refuse a figure that has lost text to a collision or to the canvas edge.

    Same contract as the layout and glyph gates: nothing is written, and the
    message names the labels involved so the spec can be corrected rather
    than re-rolled.
    """
    clipped = clipped_texts(fig)
    if clipped:
        worst = clipped[0]
        raise RuntimeError(
            f"{len(clipped)} label(s) run off the edge of the figure — "
            f"{worst['text'][:48]!r} is only {worst['visible']:.0%} visible, so the "
            "rest of it is cut off with no indication. Shorten the text, raise "
            "'width_in', or choose an 'aspect' that gives that side more room."
        )
    collisions = text_collisions(fig)
    if collisions:
        shown = "; ".join(f"{hit['a'][:32]!r} over {hit['b'][:32]!r}" for hit in collisions[:3])
        # "Split it into a panel" is the usual advice and exactly the wrong
        # advice when the figure ALREADY is one — a 7x7 matrix in a half-width
        # cell has 17 px per cell and would need 2 pt text, which no amount of
        # further subdivision fixes. Give the panel case its own way out.
        # Count PLACES, the same way ``content_places`` does: a twin shares
        # its host's rectangle and a colorbar is not a chart, so counting axes
        # objects called a ``speedup`` with an efficiency axis a two-panel
        # figure. An INSET does not share its host's rectangle — it is a
        # different one by construction — so walking ``all_axes`` here counted
        # a lone ``upset``, which builds three of them, as a four-panel figure
        # and told the caller to "use fewer panels" on a spec with no panels
        # in it. ``fig.axes`` omits insets, which is exactly what is wanted.
        charts = len(
            {
                tuple(round(v, 4) for v in ax.get_position().bounds)
                for ax in fig.axes
                if ax.get_label() != "<colorbar>" and ax.get_visible()
            }
        )
        # How many labels are competing for the SAME axis. When the answer is
        # "dozens", shortening them is the wrong advice — the column is a few
        # pixels wide whatever the text says, and the figure needs a shape that
        # gives every name its own row instead.
        crowded = max(
            (
                len([t for t in ax.get_xticklabels() if t.get_text() and t.get_visible()])
                for ax in all_axes(fig)
                if ax.get_label() != "<colorbar>"
            ),
            default=0,
        )
        if charts > 1:
            remedy = (
                "Each cell of a panel gets a fraction of the width, and a matrix or "
                "a dense axis may not fit in one at all — give that chart its own "
                "figure, use fewer panels, or shorten its labels."
            )
        elif crowded >= _CROWDED_AXIS:
            remedy = (
                f"There are {crowded} labels along one axis, so each has a few pixels of "
                "column whatever it says — shortening them will not help. Turn the chart on "
                'its side, where every name gets its own row ("type": "barh", or "lollipop" '
                'past ~20), group the tail into an "Other" row, or split the categories '
                "across a 'panel'."
            )
        else:
            remedy = (
                "Give them room: shorten the labels, raise 'width_in', or change "
                "'aspect' towards the side that is short — a matrix squashed to 21:9 "
                "has no width per cell, a chart with many categories has none per "
                "column. Splitting into a 'panel' also works."
            )
        raise RuntimeError(
            f"{len(collisions)} pair(s) of labels print over each other: {shown}"
            + (f" (+{len(collisions) - 3} more)" if len(collisions) > 3 else "")
            + ". "
            + remedy
        )
