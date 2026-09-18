"""Renderers for model-evaluation figures — ROC, PR, calibration, learning, Q-Q.

A separate family from the core charts because these share an input problem
the core charts do not have: none of them plots the numbers it is given.
A ROC point is a threshold, a PR point is a threshold, a calibration marker
is a bin, a Q-Q point is an order statistic. Every one is a TRANSFORM of the
raw evaluation output, so the transform lives here, next to the drawing.

That placement is the whole design. Each figure's headline number — AUC,
average precision, expected calibration error — is computed from the very
points that were plotted, never read from the spec, for the same reason
``render_scatter`` fits its own regression line: a number passed in beside a
curve can disagree with it, and the disagreement is invisible. A legend
reading "AUC = 0.94" over a curve worth 0.78 looks exactly like a correct
figure, survives review, and is only caught by someone re-deriving it from
the data — which is nobody.

The curves also refuse a second failure the core charts cannot have. A rate
outside [0, 1] is not a rate; a false-positive rate that steps backwards did
not come from a threshold sweep; labels that are all one class leave a ROC
curve dividing by zero. Each of those renders as a plausible picture, so
each raises ``SpecError`` naming the key and the index instead.
"""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
from chart_common import (
    SpecError,
    flag,
    legend_place,
    number_option,
    readable_ink,
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
    require_positive as _require_positive,
)
from chart_common import (
    series_of as _series,
)
from chart_style import (
    PALETTE,
    fix_log_ticks,
    literal,
    place_legend,
    place_point_label,
    series_style,
)

# Reference geometry — the chance diagonal, the perfect-calibration line, the
# positive-rate baseline. Grey, thin and BEHIND the data: these lines are the
# yardstick the curve is read against, so they have to be visible without
# competing with it for the reader's attention.
_GUIDE = {"color": "#999999", "linewidth": 1.0, "zorder": 1}


# --------------------------------------------------------------------------
# shared gates
#
# ``numbers()`` already refuses NaN, Infinity, strings and None. What it
# cannot know is what the numbers MEAN, and every check below is a defect
# that reached a rendered figure looking entirely reasonable.
# --------------------------------------------------------------------------


def _unit_interval(values: np.ndarray, what: str, *, meaning: str) -> None:
    """Rates and probabilities live in [0, 1]; anything else is a unit error.

    The overwhelmingly common cause is percentages: 0..100 plotted on a unit
    axis draws a curve that leaves the frame entirely, so the figure comes
    out empty-looking with a legend and an axis that both still read as if
    everything worked.
    """
    outside = [(i, v) for i, v in enumerate(values) if v < 0.0 or v > 1.0]
    if outside:
        i, v = outside[0]
        raise SpecError(
            f"{what}[{i}] is {v:g}, outside [0, 1]. {meaning} are fractions, not "
            "percentages — divide by 100 if these came from a table in percent."
        )


def _non_decreasing(values: np.ndarray, what: str, *, why: str) -> None:
    """A curve traced by a threshold sweep can never step backwards.

    Out-of-order points draw a zigzag whose enclosed area is partly negative,
    so the trapezoid summary silently under-reports — and the picture reads
    as a noisy model rather than as a sorting mistake.
    """
    for i in range(1, values.size):
        if values[i] < values[i - 1]:
            raise SpecError(
                f"{what} steps back at index {i} ({values[i - 1]:g} → {values[i]:g}). "
                f"{why} Sort every array of this series together, by {what}."
            )


def _binary(values, what: str, *, expect: int | None = None) -> np.ndarray:
    """Class labels, which must be exactly 0 or 1.

    A stray 2 (a three-class column pasted in by mistake) counts as a
    positive in every cumulative sum below and shifts the whole curve up.
    """
    labels = _numbers(values, what, expect=expect)
    for i, v in enumerate(labels):
        if v not in (0.0, 1.0):
            raise SpecError(
                f"{what}[{i}] is {v:g} — labels must be 0 (negative) or 1 (positive). "
                "Write the two classes as 0 and 1; JSON true/false is not a number "
                "and is refused earlier."
            )
    return labels


def _fraction(spec: dict, key: str) -> float | None:
    """A single spec-level number that has to be a fraction, or nothing."""
    if spec.get(key) is None:
        return None
    # `number_option` and a scalar message, not `_numbers([x])` + the array
    # formatter: the array form indexes into what it was given, so a single
    # number came back as "'positive_rate'[0] is 1.5" — an index into a value
    # that is not a list, sending the reader looking for an entry [0].
    value = number_option(spec, key, 0.0)
    if not 0.0 <= value <= 1.0:
        raise SpecError(
            f"'{key}' is {value:g}, outside [0, 1]. Class rates are fractions, not "
            "percentages — divide by 100 if this came from a table in percent."
        )
    return value


def _area_under(x: np.ndarray, y: np.ndarray) -> float:
    """Trapezoid area under the polyline that was actually drawn.

    Written out rather than taken from numpy because the name moved
    (``np.trapz`` was removed in numpy 2.0 in favour of ``np.trapezoid``),
    and a summary number that disappears on a version bump is worse than
    three lines of arithmetic.
    """
    return float(np.sum(np.diff(x) * (y[:-1] + y[1:]) / 2.0))


def _sweep(labels: np.ndarray, scores: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Cumulative true/false positives at every DISTINCT score, highest first.

    Ties are collapsed to one point rather than expanded into a staircase.
    Splitting a tie group makes the curve depend on the order the rows
    happened to arrive in — the same model on the same data draws a different
    figure per run — and the optimistic ordering inflates the area under it.
    """
    order = np.argsort(-scores, kind="stable")
    ranked, hits = scores[order], labels[order]
    true_pos, false_pos = np.cumsum(hits), np.cumsum(1.0 - hits)
    # The last index of each run of equal scores: one operating point per
    # threshold a user could actually set.
    last = np.concatenate((np.nonzero(np.diff(ranked))[0], [ranked.size - 1]))
    return true_pos[last], false_pos[last]


def _one_source(s: dict, curve_keys: tuple[str, str], where: str) -> bool:
    """Decide whether a series is a precomputed curve or raw predictions.

    Carrying both is refused rather than silently preferring one: the two
    describe the same model, so if they disagree the figure shows one number
    while the caller believes it shows the other.
    """
    curve = any(s.get(k) is not None for k in curve_keys)
    raw = s.get("labels") is not None or s.get("scores") is not None
    if curve and raw:
        raise SpecError(
            f"{where} carries both a precomputed curve "
            f"('{curve_keys[0]}'/'{curve_keys[1]}') and raw 'labels'/'scores'. "
            "Only one can be drawn — keep the source the numbers came from."
        )
    if not curve and not raw:
        raise SpecError(
            f"{where} needs either '{curve_keys[0]}' + '{curve_keys[1]}' "
            "(a precomputed curve) or 'labels' + 'scores' (the raw evaluation "
            "output, swept into a curve here)"
        )
    return curve


def _named_points(s: dict, x: np.ndarray, y: np.ndarray) -> tuple | None:
    """Optional per-point names — the thresholds of a hand-authored curve.

    Length-checked by ``labels_for``, so five names against four points is an
    error rather than four labelled points and one silently dropped name.
    """
    if not s.get("categories"):
        return None
    return x, y, _labels(s, x.size)


def _reject_named_points(s: dict, where: str) -> None:
    """``categories`` names points of a curve, and raw predictions have none."""
    if s.get("categories"):
        raise SpecError(
            f"{where} has 'categories' alongside raw 'labels'/'scores'. The curve is "
            "swept here, so its points are thresholds discovered in the data rather "
            "than the rows you passed, and there is nothing for the names to attach "
            "to — name the points of a precomputed curve instead."
        )


def _mark_points(ax, marks: tuple | None, colour: str) -> None:
    if marks is None:
        return
    x, y, names = marks
    ax.plot(x, y, linestyle="none", marker="o", markersize=4, color=colour, zorder=3)
    for xi, yi, name in zip(x, y, names, strict=False):
        # Darkened until it is legible as text; the hue still ties the name to
        # its curve. See ``readable_ink``.
        place_point_label(ax, name, (xi, yi), fontsize=8, color=readable_ink(colour))


def _entry(s: dict, statistic: str) -> str:
    """Legend text: the series name plus the number this figure is about.

    The statistic is never optional. It is the finding — a ROC curve without
    its AUC asks every reader to integrate by eye — and it is computed from
    the plotted points, so an unlabelled series still gets an entry.
    """
    name = literal(s["label"]) if s.get("label") else None
    return f"{name} ({statistic})" if name else statistic


def _curve_legend(ax, spec: dict, *, loc: str) -> None:
    """One entry per line, in the corner a diagonal chart leaves empty.

    ``draw_legend`` is built for the other shape of chart: it BUYS room by
    widening the y-range 18% and lays the entries out in COLUMNS across the
    top. Neither move works on these. Stretching a ROC axes to 1.2 puts the
    chance diagonal somewhere other than the corner, and the columns are what
    actually breaks: three entries of "Ridge baseline (n = 60)" side by side
    measured wider than the whole figure, at which point constrained layout
    gave up with "axes sizes collapsed to zero" and emitted a figure whose
    plot area had been squeezed off the canvas.

    One column in a corner is also simply how these are drawn — the data of
    every chart here runs along a diagonal, so what is free is a corner and
    never a strip.

    ``draw_legend``'s rule is kept: a legend that only restates the axis
    label is noise. Here every entry carries a number the axes cannot show —
    AUC, average precision, ECE, the sample size — so even a single entry
    earns its space. ``legend_loc`` overrides the corner.
    """
    handles, _ = ax.get_legend_handles_labels()
    if not handles:
        return
    place_legend(ax, loc=legend_place(spec) or loc, ncols=1)


# --------------------------------------------------------------------------
# ROC
# --------------------------------------------------------------------------


def _close_roc(fpr: np.ndarray, tpr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Add the two endpoints every threshold sweep passes through.

    Above the highest score nothing is predicted positive, which is (0, 0);
    below the lowest everything is, which is (1, 1). A curve that omits them
    is not a shorter curve, it is the same curve with its ends unstated — and
    integrating only the stated part reports a PARTIAL area as the AUC, so a
    curve worth 0.86 is labelled 0.71. Neither point is invented: both are
    forced by the definition, which is why they can be supplied here.
    """
    if fpr[0] > 0.0 or tpr[0] > 0.0:
        fpr, tpr = np.concatenate(([0.0], fpr)), np.concatenate(([0.0], tpr))
    if fpr[-1] < 1.0 or tpr[-1] < 1.0:
        fpr, tpr = np.concatenate((fpr, [1.0])), np.concatenate((tpr, [1.0]))
    return fpr, tpr


def _roc_points(s: dict, i: int) -> tuple[np.ndarray, np.ndarray, tuple | None]:
    where = f"series[{i}]"
    if _one_source(s, ("fpr", "tpr"), where):
        fpr = _numbers(s.get("fpr"), f"{where}.fpr")
        tpr = _numbers(s.get("tpr"), f"{where}.tpr", expect=fpr.size)
        _unit_interval(fpr, f"{where}.fpr", meaning="False-positive rates")
        _unit_interval(tpr, f"{where}.tpr", meaning="True-positive rates")
        # BOTH are monotone in a real sweep: lowering the threshold can only
        # add positives, never take one back. A dip means the arrays were
        # sorted apart from each other, or transposed.
        _non_decreasing(fpr, f"{where}.fpr", why="A ROC curve sweeps the threshold downward.")
        _non_decreasing(tpr, f"{where}.tpr", why="A ROC curve sweeps the threshold downward.")
        marks = _named_points(s, fpr, tpr)
        return (*_close_roc(fpr, tpr), marks)

    _reject_named_points(s, where)
    labels = _binary(s.get("labels"), f"{where}.labels")
    scores = _numbers(s.get("scores"), f"{where}.scores", expect=labels.size)
    positives = float(labels.sum())
    negatives = float(labels.size - positives)
    if positives == 0.0 or negatives == 0.0:
        raise SpecError(
            f"{where}.labels is one class only ({int(positives)} of {labels.size} are 1). "
            "A ROC curve divides by the size of each class, so an empty class leaves "
            "every point undefined — evaluate on a set containing both."
        )
    true_pos, false_pos = _sweep(labels, scores)
    return (
        np.concatenate(([0.0], false_pos / negatives)),
        np.concatenate(([0.0], true_pos / positives)),
        None,
    )


def render_roc(ax, spec: dict) -> None:
    """ROC curves, each labelled with an AUC integrated from its drawn points.

    Sweeps the decision threshold and plots true-positive rate against
    false-positive rate, with the chance diagonal for scale. What it measures
    is RANKING — whether the score puts positives above negatives — separately
    from where the threshold ends up and from how common the positive class
    is.

    Choose it when the classes are roughly balanced, or when the claim is
    that one score separates the classes better than another. Choose ``pr``
    instead when positives are rare: the false-positive rate divides by a
    huge negative count, so at 2% positives a ROC curve looks excellent while
    precision at every usable threshold is hopeless. Choose ``calibration``
    when the question is whether the scores work as PROBABILITIES rather than
    as a ranking — ROC is unchanged by any monotone rescaling, so a wildly
    overconfident model still draws a perfect curve.

    Each series is either a precomputed curve (``fpr`` + ``tpr``) or the raw
    evaluation output (``labels`` of 0/1 + ``scores``, swept here). A
    precomputed curve is closed to (0,0) and (1,1) so its AUC is the whole
    area. Set ``"chance": false`` to drop the diagonal, ``"aspect": "1:1"``
    to read the curve as a square — which is how a ROC is read.
    """
    series = _series(spec)
    for i, s in enumerate(series):
        fpr, tpr, marks = _roc_points(s, i)
        style = series_style(i)
        ax.plot(fpr, tpr, label=_entry(s, f"AUC = {_area_under(fpr, tpr):.3f}"), **style)
        _mark_points(ax, marks, style["color"])

    if spec.get("chance", True):
        ax.plot([0.0, 1.0], [0.0, 1.0], linestyle="--", label="Chance (AUC = 0.500)", **_GUIDE)

    # A hair of margin: a curve running along tpr = 1 sits exactly on the
    # spine otherwise, where it reads as part of the frame.
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    # Defaults, not overrides — ``chart_gen`` applies the spec's own labels
    # after this, so these only fill in an axis that would otherwise be bare.
    # A ROC's axes always mean the same two things, so there is no reason for
    # a figure to ship without them.
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    _curve_legend(ax, spec, loc="lower right")


# --------------------------------------------------------------------------
# precision-recall
# --------------------------------------------------------------------------


def _pr_points(s: dict, i: int) -> tuple[np.ndarray, np.ndarray, float | None, tuple | None]:
    where = f"series[{i}]"
    if _one_source(s, ("recall", "precision"), where):
        recall = _numbers(s.get("recall"), f"{where}.recall")
        precision = _numbers(s.get("precision"), f"{where}.precision", expect=recall.size)
        _unit_interval(recall, f"{where}.recall", meaning="Recalls")
        _unit_interval(precision, f"{where}.precision", meaning="Precisions")
        # Only recall is monotone. Precision genuinely zigzags as the
        # threshold drops — that sawtooth is the shape of a real PR curve,
        # not noise to be smoothed away.
        _non_decreasing(recall, f"{where}.recall", why="A PR curve sweeps the threshold downward.")
        marks = _named_points(s, recall, precision)
        rate = None
    else:
        _reject_named_points(s, where)
        labels = _binary(s.get("labels"), f"{where}.labels")
        scores = _numbers(s.get("scores"), f"{where}.scores", expect=labels.size)
        positives = float(labels.sum())
        if positives == 0.0:
            raise SpecError(
                f"{where}.labels contains no positives (all {labels.size} are 0). "
                "Recall divides by the positive count, so there is no curve to draw."
            )
        true_pos, false_pos = _sweep(labels, scores)
        precision = true_pos / (true_pos + false_pos)
        recall = true_pos / positives
        rate = positives / labels.size
        marks = None

    if recall[0] > 0.0:
        # The stretch from recall 0 to the first operating point is held at
        # that point's precision — the standard closure, and the one that
        # makes the annotated average precision the area of what is drawn.
        recall = np.concatenate(([0.0], recall))
        precision = np.concatenate(([precision[0]], precision))
    return recall, precision, rate, marks


def render_pr(ax, spec: dict) -> None:
    """Precision-recall curves, each labelled with its average precision.

    Sweeps the decision threshold and plots precision against recall, drawn
    as steps because that is what the average precision sums: the annotated
    AP is exactly the area under the staircase on the page. The dashed
    baseline is the positive rate, which is what precision a coin flip gets.

    Choose it over ``roc`` whenever positives are rare or the cost of a false
    positive is what the paper is about — a retrieval, detection, flagging or
    triage task. Neither precision nor recall involves the true-negative
    count, so a PR curve keeps discriminating exactly where a ROC curve
    saturates: at 1% positives a model can hold a 0.99 AUC and still be
    wrong four times in five at any threshold anyone would deploy. The cost
    of that sensitivity is that AP and the baseline both move with the class
    balance, so PR curves are only comparable within one evaluation set.

    Each series is either a precomputed curve (``recall`` + ``precision``) or
    the raw evaluation output (``labels`` of 0/1 + ``scores``, swept here).
    ``positive_rate`` places the baseline for an all-precomputed figure; with
    raw labels it is derived, and a spec that states a different one is an
    error rather than a quietly redrawn line.
    """
    series = _series(spec)
    rates: list[tuple[int, float]] = []
    for i, s in enumerate(series):
        recall, precision, rate, marks = _pr_points(s, i)
        if rate is not None:
            rates.append((i, rate))
        # Steps, and steps that lean BACKWARDS: the interval before each
        # operating point is held at that point's precision, which is the
        # term average precision sums over it. Drawn the other way round the
        # picture and the number in the legend describe different areas.
        average_precision = float(np.sum(np.diff(recall) * precision[1:]))
        reached = float(recall[-1])
        summary = (
            f"AP = {average_precision:.3f}"
            if reached >= 0.999
            else f"AP = {average_precision:.3f} up to recall {reached:.2f}"
        )
        style = series_style(i)
        ax.plot(recall, precision, drawstyle="steps-pre", label=_entry(s, summary), **style)
        _mark_points(ax, marks, style["color"])

    # One baseline for the figure: the class balance of the evaluation set.
    # A stated 'positive_rate' wins, otherwise the first swept series sets it.
    baseline = _fraction(spec, "positive_rate")
    if baseline is None and rates:
        baseline = rates[0][1]
    for i, rate in rates:
        if abs(rate - baseline) > 0.005:
            raise SpecError(
                f"series[{i}] has a positive rate of {rate:.3f} but the figure's baseline "
                f"is {baseline:.3f}. Precision and average precision both move with the "
                "class balance, so curves measured on differently balanced sets cannot "
                "share one baseline and cannot be compared on one axes — give them a "
                "panel each, or state the shared 'positive_rate' explicitly."
            )
    if baseline is not None:
        ax.axhline(baseline, linestyle="--", label=f"Chance ({baseline:.3f})", **_GUIDE)

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("Recall")
    ax.set_ylabel("Precision")
    _curve_legend(ax, spec, loc="lower left")


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------


def _bin_count(spec: dict) -> int:
    value = float(_numbers([spec.get("bins", 10)], "'bins'")[0])
    if value != int(value) or not 2 <= value <= 100:
        raise SpecError(
            f"'bins' is {value:g} — a reliability diagram needs a whole number of bins "
            "between 2 and 100. Past that most bins hold no samples and the curve is "
            "mostly gaps."
        )
    return int(value)


def _reliability(
    probs: np.ndarray, labels: np.ndarray, n_bins: int, strategy: str
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Bin edges, count, observed positive frequency, and mean confidence.

    Empty bins come back with a count of zero and are dropped by the caller
    rather than plotted. A bin nobody predicted into has no observed
    frequency, and drawing it at zero puts a point on the floor of the chart
    that reads as a confidently wrong prediction nobody ever made.

    Bins are half-open ``[lo, hi)`` with the last one closed — numpy's
    histogram convention, and therefore the one the count strip underneath is
    drawn with. (sklearn's ``calibration_curve`` closes the other end, so a
    probability landing EXACTLY on a bin edge — common when confidences are
    rounded to two decimals — lands one bin lower there. The marker and the
    bar under it have to agree; agreeing with a library nobody here imports
    matters less.)
    """
    if strategy == "quantile":
        # Equal-COUNT bins: with predictions massed near 0 and 1 — the usual
        # shape — equal-width bins leave the middle empty and put most of the
        # data in two bins, so the diagram has four markers and no resolution
        # where it matters.
        edges = np.quantile(probs, np.linspace(0.0, 1.0, n_bins + 1))
    else:
        edges = np.linspace(0.0, 1.0, n_bins + 1)
    index = np.clip(np.digitize(probs, edges[1:-1], right=False), 0, n_bins - 1)
    counts = np.bincount(index, minlength=n_bins).astype(float)
    hits = np.bincount(index, weights=labels, minlength=n_bins)
    observed = np.divide(hits, counts, out=np.zeros_like(counts), where=counts > 0)
    # Mean predicted probability per bin, NOT the bin's midpoint. The midpoint
    # is where the bin is; this is where its predictions actually are, and the
    # two are not the same thing — under ``quantile`` bins, which exist for
    # exactly the skewed case, they were up to 0.07 apart here. It is also the
    # confidence term in the standard definition of ECE, so plotting the
    # marker here keeps "the number matches the drawn points" AND agrees with
    # the number a reader computes from the same data.
    confidence = np.divide(
        np.bincount(index, weights=probs, minlength=n_bins),
        counts,
        out=np.zeros_like(counts),
        where=counts > 0,
    )
    return edges, counts, observed, confidence


# The strip reserved for the counts, in the data coordinates of the
# probability axis. BELOW zero rather than inside [0, 1] so that no count bar
# can ever be read as an observed frequency, and so the curve keeps the whole
# unit square it is compared against.
_HIST_FLOOR = -0.36
_HIST_HEIGHT = 0.30


def _count_inset(ax, histograms: list[tuple]) -> None:
    """The bin counts, in a strip that shares the x-axis below the diagram.

    A reliability diagram is unreadable without them. The rightmost bin
    routinely holds a handful of samples, and three samples land the marker
    at exactly 0, 1/3, 2/3 or 1 — a point that swings a third of the axis on
    one extra example, drawn identically to a bin summarising two thousand.

    The strip is an inset in DATA coordinates below y = 0, with the main
    y-axis' ticks and spine stopped at 0, so the reserved band cannot be
    mistaken for part of the probability axis. It has to be an inset rather
    than a second subplot: a renderer gets one Axes and never touches the
    figure, which is what lets ``panel`` compose it like any other type.
    """
    # Spanning the AXES' x-range, not [0, 1]: an inset narrower than the axes
    # carries its own x scale, and the bar for the 0.9 bin then sits over the
    # 0.88 tick of the diagram above it.
    left, right = ax.get_xlim()
    strip = ax.inset_axes([left, _HIST_FLOOR, right - left, _HIST_HEIGHT], transform=ax.transData)
    for counts, edges, colour in histograms:
        strip.stairs(
            counts,
            edges,
            color=colour,
            fill=len(histograms) == 1,
            alpha=0.55 if len(histograms) == 1 else 1.0,
            linewidth=1.2,
        )
    strip.set_xlim(left, right)
    # Headroom for the caption below. Without it the tallest bar reaches the
    # top of the strip and the words sit on top of the bar — and with
    # equal-count bins EVERY bar is the tallest, so there is no corner left.
    strip.set_ylim(0.0, max(float(c.max()) for c, _, _ in histograms) * 1.45)
    strip.set_xticks([])  # the diagram's own x-axis, directly below, is shared
    strip.grid(visible=False)
    strip.tick_params(axis="y", labelsize=7, pad=1.5)
    # Two ticks, whole numbers: this is a count, and the margin here belongs
    # to the main y-axis' labels — a third tick starts colliding with them.
    strip.locator_params(axis="y", nbins=2, integer=True)
    # Inside the strip: an axis label out here would sit in the margin
    # constrained layout reserved for the MAIN y-label and collide with it.
    strip.text(
        0.99,
        0.96,
        "samples per bin",
        transform=strip.transAxes,
        ha="right",
        va="top",
        fontsize=7,
        color="#555555",
    )


def render_calibration(ax, spec: dict) -> None:
    """Reliability diagram — observed frequency against predicted probability.

    Bins the predicted probabilities, plots the fraction of positives in each
    bin at the MEAN PREDICTED PROBABILITY of that bin, and draws the
    perfect-calibration diagonal. Below the diagonal is overconfidence (the
    model claims 0.9 and is right 0.6 of the time), above it is
    underconfidence. Each series is labelled with its expected calibration
    error: the count-weighted mean distance from the diagonal, summed over
    exactly the markers drawn.

    The mean rather than the bin's midpoint, which is what this drew for a
    while. They are not the same thing — the midpoint is where the bin is,
    the mean is where its predictions are — and under ``quantile`` bins,
    which exist for exactly the skewed case where they diverge most, they
    were 0.07 apart on the shipped example and the reported ECE was 0.126
    against a standard 0.155. Plotting the marker at the confidence the
    error is measured against keeps the number matching the picture AND
    matching the number a reader computes from the same data. A strip of bin
    counts sits underneath, because a marker from four samples and a marker
    from four thousand are otherwise drawn identically.

    Choose it when the probabilities themselves are the product — routing on
    a confidence threshold, abstention, selective prediction, risk scores,
    anything where 0.9 has to mean nine times in ten. ``roc`` and ``pr``
    cannot answer that: both depend only on the ORDER of the scores, so a
    model whose every probability is inflated by 30 points scores exactly as
    it did before. The reverse also holds — recalibration cannot change a
    ROC curve — so a calibration figure complements one of those rather than
    replacing it.

    Each series carries ``probabilities`` (in [0, 1]) and ``labels`` (0/1) of
    the same length. ``bins`` (default 10) sets the resolution; empty bins
    are dropped rather than drawn at zero. ``"strategy": "quantile"`` bins by
    equal count instead of equal width, for predictions massed at the ends.
    ``"histogram": false`` drops the count strip in a tight panel.
    """
    series = _series(spec)
    n_bins = _bin_count(spec)
    strategy = spec.get("strategy", "uniform")
    if strategy not in {"uniform", "quantile"}:
        raise SpecError(
            f"'strategy' is {strategy!r} — use \"uniform\" (equal-width bins) or "
            '"quantile" (equal-count bins)'
        )

    histograms = []
    for i, s in enumerate(series):
        where = f"series[{i}]"
        probs = _numbers(s.get("probabilities"), f"{where}.probabilities")
        labels = _binary(s.get("labels"), f"{where}.labels", expect=probs.size)
        _unit_interval(probs, f"{where}.probabilities", meaning="Predicted probabilities")

        edges, counts, observed, confidence = _reliability(probs, labels, n_bins, strategy)
        filled = counts > 0
        centres = confidence[filled]
        frequency, weight = observed[filled], counts[filled]
        error = float(np.sum(weight * np.abs(frequency - centres)) / weight.sum())

        style = series_style(i)
        ax.plot(
            centres,
            frequency,
            marker="o",
            markersize=5,
            label=_entry(s, f"ECE = {error:.3f}"),
            **style,
        )
        histograms.append((counts, edges, style["color"]))

    ax.plot([0.0, 1.0], [0.0, 1.0], linestyle="--", label="Perfect calibration", **_GUIDE)
    ax.set_xlim(-0.02, 1.02)

    if flag(spec, "histogram", True):
        ax.set_ylim(_HIST_FLOOR - 0.02, 1.02)
        ax.set_yticks(np.linspace(0.0, 1.0, 6))
        # Stop the frame and the label at the data. Left running, the spine
        # continues past the last tick into the strip's territory and the
        # y-label centres itself on empty space.
        ax.spines["left"].set_bounds(0.0, 1.0)
        ax.yaxis.label.set_y(0.72)
        _count_inset(ax, histograms)
    else:
        ax.set_ylim(-0.02, 1.02)

    ax.set_xlabel("Predicted probability")
    ax.set_ylabel("Observed frequency")
    _curve_legend(ax, spec, loc="upper left")


# --------------------------------------------------------------------------
# learning curve
# --------------------------------------------------------------------------


def render_learning_curve(ax, spec: dict) -> None:
    """Score against training-set size, with ±1 std bands over the repeats.

    One series per split — training and validation — measured at each size
    and shaded by the spread across folds or seeds. The two lines together
    are what makes it diagnostic: a wide gap that is not closing is variance
    and more data will help; both lines flat, low and touching is bias and
    more data will not; a validation line still climbing at the largest size
    says the experiment stopped too early.

    Choose it when the question is about DATA — how much is enough, whether
    to keep labelling, whether the gap is over- or under-fitting. Choose
    ``line`` for score against training STEP, which is a different question
    about one run's optimisation, and ``scaling`` for score against compute
    or parameters on log-log axes with a fitted exponent.

    ``train_sizes`` holds the x values (a series may override with its own
    ``x``); each series carries ``values`` and optionally ``std``, either a
    per-point list or one number for a constant band. Sizes are usually
    geometric, so ``"logx": true`` is the common case — it spaces the
    measured points evenly instead of crushing every small size against the
    axis.
    """
    series = _series(spec)
    sizes: list[np.ndarray] = []
    for i, s in enumerate(series):
        where = f"series[{i}]"
        values = _numbers(s.get("values"), f"{where}.values")
        raw_x = s.get("x") or spec.get("train_sizes")
        if not raw_x:
            raise SpecError(
                "'train_sizes' is missing — a learning curve is score against the "
                "NUMBER OF TRAINING EXAMPLES, so plotting it against an index would "
                "hide the sizes the experiment actually ran at"
            )
        x = _numbers(raw_x, f"{where}.x" if s.get("x") else "'train_sizes'", expect=values.size)
        _non_decreasing(
            x,
            f"{where}.x" if s.get("x") else "'train_sizes'",
            why="A learning curve is read left to right, from least data to most.",
        )
        sizes.append(x)

        style = series_style(i)
        ax.plot(
            x,
            values,
            marker="o",
            markersize=4.5,
            label=literal(s["label"]) if s.get("label") else None,
            **style,
        )
        std = s.get("std")
        if std is not None:
            band = _numbers(
                std if isinstance(std, list) else [std] * values.size,
                f"{where}.std",
                expect=values.size,
            )
            if np.any(band < 0.0):
                raise SpecError(
                    f"{where}.std has a negative entry. A ±band of negative width draws "
                    "inside out — the upper edge falls below the lower one and the "
                    "shading reads as a band a third of its real size. Pass the "
                    "standard deviation, not a signed residual."
                )
            ax.fill_between(
                x, values - band, values + band, color=style["color"], alpha=0.18, linewidth=0
            )

    if flag(spec, "logx"):
        for i, x in enumerate(sizes):
            _require_positive(x, f"series[{i}] training sizes", "x")
        ax.set_xscale("log")
        marks = np.unique(np.concatenate(sizes))
        if marks.size <= 10:
            # Tick AT the sizes the experiment actually ran. The default log
            # locator labels powers of ten and nothing else, so a sweep from
            # 250 to 16000 arrives with exactly two labelled ticks — neither
            # of them a size anybody trained on — and the reader cannot say
            # which point is 4k and which is 8k.
            ax.set_xticks(marks, labels=[f"{v:g}" for v in marks])
            ax.tick_params(axis="x", which="minor", labelbottom=False)
        else:
            # Too many to label one by one; fall back to the house rule,
            # which restores labels when the range is under a decade.
            fix_log_ticks(ax, "x")

    ax.set_xlabel("Training-set size (examples)")
    ax.set_ylabel("Score")
    _legend(ax, spec, series)


# --------------------------------------------------------------------------
# Q-Q
# --------------------------------------------------------------------------


def _plotting_positions(n: int) -> np.ndarray:
    """Where in the theoretical distribution the i-th of n order statistics sits.

    ``i/n`` would put the largest observation at probability 1, whose normal
    quantile is infinite. The offset rule below is the standard fix and the
    one R's ``ppoints`` uses: Blom's 3/8 for small samples, where the choice
    visibly tilts the tails, and 1/2 beyond ten points, where it does not.
    """
    a = 3.0 / 8.0 if n <= 10 else 0.5
    return (np.arange(1, n + 1) - a) / (n + 1.0 - 2.0 * a)


def render_qq(ax, spec: dict) -> None:
    """Normal Q-Q plot — sample quantiles against theoretical normal quantiles.

    Sorts the sample, pairs each value with the standard-normal quantile of
    its plotting position, and draws the reference line through the first and
    third quartiles of both — R's ``qqline``, chosen over a least-squares fit
    because outliers are the point of the plot and must not be allowed to
    tilt the line they are measured against. Points on the line are normal;
    ends bending up on the right and down on the left are heavy tails; a
    single point far off one end is an outlier, not a distributional shape.

    Choose it whenever a method ASSUMES normality — the residuals of a
    regression, a t-test or an ANOVA, the errors of a forecast — because it
    answers that question far more sharply than a histogram, which hides in
    its bin width exactly the tail behaviour that breaks those tests. Choose
    ``hist`` when the shape of one distribution is the finding itself, and
    ``ecdf`` to compare two empirical distributions to each other rather than
    one against a theoretical model.

    Each series carries ``values`` — the raw sample, in any order; it is
    sorted here. The theoretical quantiles come from the standard library's
    ``NormalDist``, so this needs nothing beyond numpy and matplotlib.
    """
    series = _series(spec)
    normal = NormalDist()
    lower, upper = normal.inv_cdf(0.25), normal.inv_cdf(0.75)

    for i, s in enumerate(series):
        sample = np.sort(_numbers(s.get("values"), f"series[{i}].values"))
        if sample.size < 3:
            raise SpecError(
                f"series[{i}].values has {sample.size} points. A Q-Q plot compares the "
                "SHAPE of a sample against the normal, and below three order statistics "
                "there is no shape — the reference line would be fitted to the two "
                "points it is meant to judge."
            )
        theoretical = np.array([normal.inv_cdf(p) for p in _plotting_positions(sample.size)])
        colour = PALETTE[i % len(PALETTE)]
        ax.plot(
            theoretical,
            sample,
            linestyle="none",
            marker="o",
            markersize=4,
            alpha=0.75,
            color=colour,
            label=_entry(s, f"n = {sample.size}"),
        )
        # Through the quartile pair, extended across the plotted range. One
        # line per series: two samples on different scales need different
        # lines, and a single shared one would declare one of them non-normal
        # for no reason but its variance. Grey while there is only one series,
        # which keeps reference geometry the same colour it is on every other
        # chart in this family; coloured once there are several, where the
        # line has to be attributable to its points.
        low, high = (float(q) for q in np.quantile(sample, [0.25, 0.75]))
        slope = (high - low) / (upper - lower)
        ends = np.array([theoretical[0], theoretical[-1]])
        ax.plot(
            ends,
            low + slope * (ends - lower),
            linestyle="--",
            **(_GUIDE if len(series) == 1 else {"color": colour, "linewidth": 1.2, "zorder": 1}),
        )

    ax.set_xlabel("Theoretical quantiles (standard normal)")
    ax.set_ylabel("Sample quantiles")
    _curve_legend(ax, spec, loc="upper left")


EVAL_RENDERERS = {
    "roc": render_roc,
    "pr": render_pr,
    "calibration": render_calibration,
    "learning_curve": render_learning_curve,
    "qq": render_qq,
}
