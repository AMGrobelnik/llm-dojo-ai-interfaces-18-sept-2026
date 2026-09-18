#!/usr/bin/env python
"""Render a publication-quality data figure from a JSON spec.

    python chart_gen.py --spec fig.json --out figures/fig1
    cat fig.json | python chart_gen.py --spec - --out figures/fig1

Writes ``<out>.pdf`` (the deliverable — vector, so LaTeX renders the text at
page resolution) and ``<out>.png`` (raster, for reading the figure back to
check it). ``--format`` narrows that if only one is wanted.

**Why a spec instead of generated plotting code:** the figure is then a
function of the data. A model that writes matplotlib by hand can produce a
chart whose bars do not match the numbers it was given, and nothing catches
it — the code runs, the picture looks plausible. Here the numbers ARE the
input, the axes are computed from them, and fits (regression, power law) are
derived from the plotted points rather than accepted alongside them, so a
figure cannot disagree with its own data.

Every chart type in ``chart_renderers.RENDERERS`` is available, plus
``panel`` which composes any of them into a labelled grid.

Run ``--list-types`` for the catalogue, ``--example TYPE`` for a complete
runnable spec of that type.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import math
import sys
import warnings
from pathlib import Path

# Sibling modules import by bare name: running this as a script already puts
# its own directory at the front of sys.path, so no path manipulation is needed.
import matplotlib.pyplot as plt
from chart_examples import EXAMPLES
from chart_geometry import assert_text_is_legible, fit_point_labels
from chart_renderers import RENDERERS, SpecError
from chart_search import CORPORA, audit, format_results, rank
from chart_style import (
    add_panel_label,
    apply_house_style,
    assert_all_glyphs_rendered,
    assert_axis_names_are_unique,
    assert_layout_applied,
    assert_legends_clear_of_data,
    assert_series_are_distinguishable,
    assert_series_can_be_told_apart,
    clear_legends_of_data,
    figsize_for,
    fit_legends,
    fit_tick_labels,
    fit_titles,
    literal,
    rasterize_dense_clouds,
    share_panel_legends,
)
from chart_validate import (
    RecordingDict,
    assert_nothing_was_ignored,
    check_canvas,
    validate_spec,
)

PANEL_LABELS = "abcdefghijklmnop"


def _limits_must_cover_data(ax, axis: str, bounds) -> None:
    """Refuse an explicit limit that would hide plotted values.

    ``ylim: [0, 1]`` on values 40/55/62 rendered three identical full-height
    bars — a chart whose every bar is wrong, at exit 0. Cropping outliers is
    a legitimate wish, but it has to be a stated one: silently flattening the
    comparison the figure exists to show is not a zoom, it is a lie.
    """
    lo, hi = float(bounds[0]), float(bounds[1])
    interval = ax.dataLim.intervaly if axis == "y" else ax.dataLim.intervalx
    d_lo, d_hi = float(interval[0]), float(interval[1])
    if not (math.isfinite(d_lo) and math.isfinite(d_hi)):
        return
    # A hair of tolerance so a limit set exactly at the data edge is fine.
    span = max(abs(d_hi - d_lo), 1e-9)
    if d_lo < lo - span * 1e-6 or d_hi > hi + span * 1e-6:
        raise SpecError(
            f"'{axis}lim' is [{lo:g}, {hi:g}] but the data runs {d_lo:g}..{d_hi:g}, "
            "so part of it would be cropped out of the figure without any "
            "indication. Widen the limit, or drop it and let the axis fit the data."
        )


def _draw(ax, spec: dict) -> None:
    """Render one spec onto ``ax`` and apply its shared cosmetic keys."""
    kind = spec.get("type")
    renderer = RENDERERS.get(kind)
    if renderer is None:
        raise SpecError(
            f"unknown chart type {kind!r}. Available: {', '.join(sorted(RENDERERS))}, panel"
        )
    renderer(ax, spec)
    if spec.get("title"):
        ax.set_title(literal(spec["title"]))
    if spec.get("xlabel"):
        ax.set_xlabel(literal(spec["xlabel"]))
    if spec.get("ylabel"):
        ax.set_ylabel(literal(spec["ylabel"]))
    if spec.get("ylim"):
        _limits_must_cover_data(ax, "y", spec["ylim"])
        ax.set_ylim(*spec["ylim"])
    if spec.get("xlim"):
        _limits_must_cover_data(ax, "x", spec["xlim"])
        ax.set_xlim(*spec["xlim"])


# Charts whose rows run down the page: their natural height is a function of
# how many rows there are, not a fixed ratio.
_ROW_ORIENTED = {
    "barh",
    "forest",
    "dumbbell",
    "lollipop",
    "diverging",
    "funnel",
    "timeline",
}

# Charts that are geometrically square. On a 16:9 canvas a radar shrinks to
# the middle third with dead margins either side, because the plot cannot use
# width it has no radius for.
_SQUARE = {"radar", "corr", "qq", "roc", "pr", "calibration", "splom", "quiver"}


# The most columns a panel grid can carry at the default 7-inch text width.
# Measured, not chosen: at four columns each cell is 1.75 in wide, which is
# less than a labelled chart needs, and constrained layout collapses the axes
# to zero. Three columns render at every panel count up to the maximum.
_MAX_DEFAULT_PANEL_COLS = 3


def _default_ncols(count: int) -> int:
    """Columns for a panel grid the spec did not pin.

    A fixed two columns turned nine panels into a 2x5 tower that constrained
    layout could not place at all, so nine, twelve and sixteen panels simply
    could not be produced. Squaring the grid keeps cells close to a chart's
    natural shape, capped where the cells get too narrow to label.
    """
    return max(1, min(_MAX_DEFAULT_PANEL_COLS, math.ceil(math.sqrt(max(1, count)))))


def _default_aspect(spec: dict) -> str:
    """Aspect to use when the spec doesn't pin one.

    A four-row forest plot on a 4:3 canvas strands each row in its own band
    of whitespace. Sizing height to the row count keeps the spacing even
    whether there are three rows or fifteen.
    """
    kind = spec.get("type")
    if kind in _SQUARE:
        return "1:1"
    if kind == "panel":
        # One 16:9 canvas for every grid shape letterboxed the cells: a 3x3
        # grid gave each panel a 5:1 strip. Deriving the canvas from the grid
        # keeps every cell about 4:3 whatever the panel count.
        panels = spec.get("panels") or []
        ncols = int(spec.get("ncols") or _default_ncols(len(panels)))
        nrows = max(1, -(-len(panels) // max(1, ncols)))
        return f"{ncols * 4}:{nrows * 3}"
    if kind == "seqheat":
        # Each row is a line of TEXT, so its height is set by the font rather
        # than by how much canvas is going spare. At 16:9 two rows of tokens
        # were 1.5 in tall each, which is a colour block with a word floating
        # in the middle of it.
        from chart_renderers_more import seqheat_rows

        # The constant is the title plus the horizontal colourbar and its
        # label; the per-row term is one line of type with its padding.
        return f"7:{1.15 + 0.46 * seqheat_rows(spec):.2f}"
    if kind not in _ROW_ORIENTED:
        return "16:9"
    rows = max((len(s.get("values") or []) for s in spec.get("series") or []), default=4)
    return f"7:{max(2.4, rows * 0.62 + 1.3):.2f}"


@contextlib.contextmanager
def _closed_on_failure(fig):
    """Close ``fig`` if the block raises, leave it open if it returns.

    ``plt.subplots`` registers the figure with pyplot, so dropping the local
    name does not free it — only ``plt.close`` does.
    """
    try:
        yield
    except BaseException:
        plt.close(fig)
        raise


def _run_layout_passes(fig) -> None:
    """Fit the figure's furniture, in the order that was worked out.

    Order matters: the legend decides how much room the axes has, tick labels
    change the axes height, titles are measured against the axes they end up
    sitting on, and a point's name can only be placed once nothing above it
    will move the point again.

    ``clear_legends_of_data`` runs TWICE, and the second run is the one that
    counts. It decides whether a legend sits on the data by measuring, and the
    two passes after it shrink the axes: a wrapped title took a lone chart's
    axes from 179 px of height to 141, and the legend — a fixed size, already
    placed — went from covering nothing to covering half a curve. The mover had
    already had its turn, so the figure was refused instead of fixed. Once
    first, because the room the legend needs is an input to the passes below.

    One copy, called by both the lone-chart and the panel paths. It was two,
    identical apart from the panel path's ``share_panel_legends`` ahead of it,
    and the panel copy was held by nothing at all: reordering it, dropping its
    second ``clear_legends_of_data``, and deleting its ``rasterize_dense_clouds``
    outright each left the layout and catalogue suites green. The last of those
    ships a panel of dense scatter as a vector PDF of every point.
    """
    fit_legends(fig)
    clear_legends_of_data(fig)
    fit_tick_labels(fig)
    fit_titles(fig)
    clear_legends_of_data(fig)
    fit_point_labels(fig)
    rasterize_dense_clouds(fig)


def build_figure(spec: dict):
    """Build and return the matplotlib Figure for ``spec``."""
    validate_spec(spec)
    apply_house_style(spec.get("font_pt", 11), spec.get("font_family"))
    aspect = spec.get("aspect") or _default_aspect(spec)
    width = float(spec.get("width_in", 7.0))

    if spec.get("type") != "panel":
        size = figsize_for(aspect, width)
        check_canvas(size, int(plt.rcParams["savefig.dpi"]))
        fig, ax = plt.subplots(figsize=size, layout="constrained")
        # Every gate below this line raises on a bad spec, and pyplot keeps a
        # global reference to a figure whether or not anyone returns it — so a
        # refusal used to leak one. The CLI never noticed (it exits), but this
        # is also a library function: SKILL.md invites calling it directly, and
        # a suite that exercises the refusals opened enough of them to trip
        # matplotlib's own "more than 20 figures" warning.
        with _closed_on_failure(fig):
            _draw(ax, spec)
            _run_layout_passes(fig)
        return fig

    panels = spec.get("panels") or []
    if not panels:
        raise SpecError("'panels' is empty — a panel figure needs sub-specs")
    ncols = int(spec.get("ncols") or _default_ncols(len(panels)))
    nrows = -(-len(panels) // ncols)  # ceiling division
    size = figsize_for(aspect, width)
    check_canvas(size, int(plt.rcParams["savefig.dpi"]))
    fig, axes = plt.subplots(
        nrows,
        ncols,
        figsize=size,
        layout="constrained",
        squeeze=False,
    )
    flat = [a for row in axes for a in row]
    with _closed_on_failure(fig):
        return _draw_panels(fig, flat, spec, panels)


def _draw_panels(fig, flat, spec: dict, panels: list):
    """The panel body, split out so the whole of it sits under one guard."""
    for i, (ax, panel) in enumerate(zip(flat, panels, strict=False)):
        _draw(ax, panel)
        if spec.get("panel_labels", True):
            add_panel_label(ax, f"({PANEL_LABELS[i]})")
    # A grid wider than the panel count leaves empty axes drawing their own
    # spines and ticks — visible as a blank framed box in the corner.
    for ax in flat[len(panels) :]:
        ax.set_visible(False)
    if spec.get("title"):
        fig.suptitle(literal(spec["title"]))
    # Panels that all show the same series get ONE legend: nine copies of
    # the same two entries is nine chances to land on the bars.
    share_panel_legends(fig)
    _run_layout_passes(fig)
    return fig


def _example_hint(spec: object, message: str = "") -> str:
    """Point a rejected spec at a working one of its own type.

    Every renderer names the key it is missing, which is the right message when
    The author knows the shape. It is the wrong one when they guessed it: a
    ``waterfall`` written with invented ``start``/``steps``/``end_label`` keys
    is told "'series' is empty", which is true, unhelpful, and sends the author
    to the wrong place. One line, appended once here rather than to fifty
    messages, turns any of them into an instruction.
    """
    kind = spec.get("type") if isinstance(spec, dict) else None
    if not isinstance(kind, str) or kind not in EXAMPLES:
        return ""
    # Most renderers end their sentence; seven of them do not, and the hint
    # then ran straight on from it — "…but 1 was expected Run `chart_gen.py`".
    # Terminated here, once, rather than in each of those seven.
    stop = "" if message.rstrip().endswith((".", "!", "?", ":")) else "."
    return f"{stop} Run `chart_gen.py --example {kind}` for a complete {kind} spec to copy."


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--spec", "-s", help="path to the JSON spec, or '-' for stdin")
    parser.add_argument("--out", "-o", help="output path WITHOUT extension")
    parser.add_argument(
        "--format",
        "-f",
        default="pdf,png",
        help="comma-separated: pdf,png,svg (default: pdf,png)",
    )
    parser.add_argument("--list-types", action="store_true", help="print the chart catalogue")
    parser.add_argument("--example", metavar="TYPE", help="print a complete runnable spec of TYPE")
    parser.add_argument(
        "--search",
        metavar="QUESTION",
        help="find chart types by the question a figure must answer, e.g. 'compare two groups'",
    )
    parser.add_argument(
        "--corpus",
        default="all",
        choices=CORPORA,
        help="which corpus --search draws from: our generators, the ChartMimic "
        "exemplars, or both (default: all)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="print which ChartMimic categories our generators cover, and which they do not",
    )
    args = parser.parse_args()

    if args.audit:
        print(audit(RENDERERS))
        return 0

    if args.search:
        print(format_results(args.search, rank(args.search, RENDERERS, corpus=args.corpus)))
        return 0

    if args.list_types:
        print("chart types (use as the spec's 'type'):\n")
        width = max(len("panel"), *(len(n) for n in RENDERERS))
        for name in sorted(RENDERERS):
            doc = (RENDERERS[name].__doc__ or "").strip().split("\n")[0]
            print(f"  {name:<{width}} {doc}")
        print(f"  {'panel':<{width}} Compose any of the above into a labelled grid.")
        print("\n  chart_gen.py --example bar   # a complete spec to copy")
        return 0

    if args.example:
        example = EXAMPLES.get(args.example)
        if example is None:
            print(
                f"no example for {args.example!r}. Available: {', '.join(sorted(EXAMPLES))}",
                file=sys.stderr,
            )
            return 2
        print(json.dumps(example, indent=2))
        return 0

    if not args.spec or not args.out:
        parser.error(
            "--spec and --out are required (or use --list-types / --example / --search / --audit)"
        )

    if args.spec == "-":
        raw = sys.stdin.read()
    else:
        try:
            # ``utf-8-sig`` rather than ``utf-8``: a byte-order mark is what
            # several editors and Windows tools put at the front of a JSON
            # file, and ``json.loads`` rejects it as a syntax error at column
            # 1 — a spec that is correct in every visible way, refused.
            raw = Path(args.spec).read_text(encoding="utf-8-sig")
        except OSError as e:
            print(f"cannot read spec {args.spec!r}: {e.strerror}", file=sys.stderr)
            return 2
    raw = raw.lstrip("﻿")
    # Said separately from the parse error below. Empty input reaches
    # ``json.loads`` as "Expecting value: line 1 column 1", which reads as a
    # typo in the spec and sends the caller to re-read JSON that is not the
    # problem — the file is empty, or the command feeding the pipe wrote
    # nothing because it failed.
    if not raw.strip():
        source = "nothing arrived on stdin" if args.spec == "-" else f"{args.spec} is empty"
        print(
            f"{source} — the spec is the figure, so there is nothing to draw. "
            "chart_gen.py --example <type> prints a complete one to start from.",
            file=sys.stderr,
        )
        return 2
    try:
        # ``object_hook`` wraps every object in the spec — panels and series
        # included — so each one records which of its keys the render actually
        # looked at. What nothing looked at is reported below.
        spec = json.loads(raw, object_hook=RecordingDict)
    except json.JSONDecodeError as e:
        print(f"spec is not valid JSON: {e}", file=sys.stderr)
        return 2

    # Recorded, not just raised: constrained layout reports a collapse as a
    # WARNING from inside ``build_figure`` (via ``fit_titles``' draw), so
    # trapping only the save phase let a badly laid-out figure exit 0.
    with warnings.catch_warnings(record=True) as built:
        warnings.simplefilter("always")
        try:
            fig = build_figure(spec)
        except SpecError as e:
            print(f"bad spec: {e}{_example_hint(spec, str(e))}", file=sys.stderr)
            return 2
        except (ValueError, TypeError, KeyError) as e:
            # matplotlib rejecting a cosmetic key (legend_loc, cmap, fmt).
            # Validation above covers the common ones; this keeps the rest a
            # message rather than a traceback the caller cannot act on.
            print(
                f"bad spec: matplotlib rejected this figure — {e}{_example_hint(spec, str(e))}",
                file=sys.stderr,
            )
            return 2
        # After the draw, not before: the reads happen inside the renderers,
        # and only a figure that built successfully proves which keys had a
        # chance to be read.
        try:
            assert_nothing_was_ignored(spec, EXAMPLES.get(spec.get("type")))
        except SpecError as e:
            plt.close(fig)
            print(f"bad spec: {e}", file=sys.stderr)
            return 2

    # NOT ``with_suffix("")``: it strips everything after the last dot, so
    # ``--out fig_v1.2`` silently wrote ``fig_v1.pdf`` — the figure landing at
    # a path the caller never named, which downstream then reports as missing.
    # Only a known image extension is treated as one.
    # Strip only a real image extension, then APPEND the format rather than
    # using ``with_suffix``. Both halves matter: ``with_suffix("")`` ate the
    # ".2" from ``--out fig_v1.2``, and ``with_suffix(".png")`` ate it again
    # on the way out — so a versioned filename silently became ``fig_v1.png``,
    # a path the caller never named and downstream reports as missing.
    out = Path(args.out)
    if out.suffix.lower().lstrip(".") in {"pdf", "png", "svg", "eps", "jpg", "jpeg"}:
        out = out.with_suffix("")
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        # The WRITE below was already guarded; the directory that has to exist
        # first was not, so an --out under a path the process cannot create
        # ended in a pathlib traceback instead of a message.
        print(f"cannot create {out.parent}: {e.strerror}", file=sys.stderr)
        return 2
    # De-duplicated, order kept: "png,png" wrote one file and reported it
    # TWICE in ``written``, so anything counting that list saw two figures
    # where one exists. A format list is a set of formats.
    formats = list(dict.fromkeys(f.strip().lower() for f in args.format.split(",") if f.strip()))
    if not formats:
        print("bad spec: --format listed no formats, so nothing would be written", file=sys.stderr)
        return 2
    # No EPS. The PostScript backend cannot draw transparency and flattens it
    # to opaque with only a warning — measured, that is 9 of 10 catalogue
    # types, because the house style uses alpha for stacked areas, scatter
    # points, violins and treemap fills alike. The EPS would then differ
    # visibly from the PNG the caller checked, which is the one thing this
    # renderer refuses to let happen, and the format was accepted but never
    # documented or asked for. PDF is the vector deliverable; SVG is the
    # editable one.
    unknown = [f for f in formats if f not in {"pdf", "png", "svg"}]
    if unknown:
        print(f"bad spec: unsupported --format {unknown} (use pdf, png or svg)", file=sys.stderr)
        return 2

    # Render everything under a warning trap first. Glyph coverage is only
    # known once text is actually laid out, and a figure with boxes where its
    # labels should be must not reach disk — so nothing is committed until
    # every format has drawn cleanly.
    staged = []
    with warnings.catch_warnings(record=True) as warned:
        warnings.simplefilter("always")
        try:
            for fmt in formats:
                buf = io.BytesIO()
                fig.savefig(buf, format=fmt)
                staged.append((out.with_name(f"{out.name}.{fmt}"), buf.getvalue()))
            # Geometry is only knowable once everything has been drawn, and
            # only while the figure is still alive — so it goes here, between
            # rendering and the close, and still ahead of any write.
            legibility = None
            try:
                assert_text_is_legible(fig)
                assert_series_are_distinguishable(fig)
                assert_series_can_be_told_apart(fig, spec)
                assert_axis_names_are_unique(fig)
                assert_legends_clear_of_data(fig)
            except RuntimeError as e:
                legibility = e
        finally:
            plt.close(fig)
        try:
            assert_layout_applied(list(built) + list(warned), fig)
            assert_all_glyphs_rendered(list(built) + list(warned))
            if legibility is not None:
                raise legibility
        except RuntimeError as e:
            print(f"bad spec: {e}", file=sys.stderr)
            return 2

    # Every byte to a ``.part`` file FIRST, then rename them into place. The
    # rendering above is already staged in memory for the same reason — but
    # the writes were not, so a spec asking for pdf,png whose PNG write failed
    # left the PDF on disk and exited 2. Measured: 6845 bytes of fig.pdf beside
    # a missing fig.png. SKILL.md promises "Nothing partial is ever written — a
    # half-file would pass the downstream existence check", and the downstream
    # check is exactly `does fig.pdf exist`, so it read that failure as success.
    #
    # Rename rather than delete-on-failure: re-rendering over an existing
    # figure must not destroy the previous one when the new render cannot be
    # written. A failed run now leaves whatever was there before, untouched.
    # The renames are not atomic AS A GROUP, so every target is checked before
    # the first one happens. Writing the parts and renaming as we went still
    # left fig.pdf behind when fig.png's rename failed — the first rename had
    # already succeeded. Checking first moves every foreseeable failure into
    # the .part phase, where nothing real has been touched yet.
    written: list[str] = []
    parts: list[tuple[Path, Path]] = []
    try:
        for path, payload in staged:
            if path.is_dir():
                raise IsADirectoryError(21, "Is a directory", str(path))
            part = path.with_name(f"{path.name}.part")
            part.write_bytes(payload)
            parts.append((part, path))
        for part, path in parts:
            part.replace(path)
            written.append(str(path))
    except OSError as e:
        for part, _ in parts:
            part.unlink(missing_ok=True)
        target = getattr(e, "filename", None) or "the output"
        print(f"cannot write {target}: {e.strerror}", file=sys.stderr)
        return 2

    print(json.dumps({"ok": True, "written": written}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
