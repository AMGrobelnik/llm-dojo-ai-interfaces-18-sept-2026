"""Spec validation for the presentation keys, before anything is drawn.

Separate from ``chart_renderers`` on purpose. The renderers police the DATA —
that the bars equal their numbers. This module polices the SPEC ITSELF: the
cosmetic keys that reach matplotlib as raw arguments, where a wrong type or
an out-of-range value produces a stack trace rather than a message, or worse
an enormous file.

Stress-testing found 21 distinct raw tracebacks reaching the caller, almost
all from this class: ``width_in: "wide"``, ``font_pt: 0``, ``bins: -1``,
``ylim: [0, 1, 2]``, ``legend_loc: "northeast"``, ``cmap: "nope"``. A model
authoring a spec cannot act on ``ValueError: could not convert string to
float``; it can act on "width_in must be a positive number, got 'wide'".

It also holds the TEXT BUDGETS — how long a title or an axis label may be.
Same reasoning, one step earlier: an over-long label produces a figure with
its text cut off rather than a traceback, and the cheapest place to say so is
before anything is drawn. The budgets are coarse by construction, since they
cannot know the figure's final width; ``chart_geometry`` measures the drawn
result and catches what they cannot.
"""

from __future__ import annotations

import math

from chart_common import type_name
from chart_renderers import SpecError

# Guard rails on anything that becomes an allocation. ``aspect: "1:100"``
# produced a 196-megapixel PNG that Pillow then refused to reopen, which
# breaks the skill's own read-the-figure-back verification loop.
MAX_WIDTH_IN = 40.0
MAX_PIXELS = 40_000_000
MAX_BINS = 5_000
MAX_PANELS = 16  # PANEL_LABELS has 16 letters

# ---------------------------------------------------------------------------
# How long a piece of text may be
# ---------------------------------------------------------------------------
# Every one of these was measured by growing that slot until the figure broke,
# then set below the break. The point is to refuse a spec BEFORE it renders,
# with a message that says what to do, rather than after — where the geometry
# gate can only report that something collided.
#
# Measured on the default 7-inch figure at 11 pt:
#
#   title    never refused and never collided; it just ate the canvas. At 600
#            characters the chart was 38% of its own figure and the heading was
#            the other 62%. 120 wraps to at most two lines.
#   x/ylabel silently CLIPPED, which is the worst outcome here: an x-label ran
#            off both edges from ~90 characters and a y-label from ~50, cut
#            mid-word, at exit 0. A label is a name with a unit, not a
#            sentence.
#   label    legend entries collided at 80 characters and collapsed the layout
#            at 100.
#   category already had its own 40-character gate for vertical bars, with a
#            pointer to barh; barh itself collapsed at 100.
#
# These are the coarse, teachable budgets. They cannot know the figure's real
# width — a 3.5-inch column fits half as much — so ``chart_geometry`` measures
# the drawn result as well and refuses anything that still does not fit.
MAX_TITLE_CHARS = 120
MAX_AXIS_LABEL_CHARS = 80
MAX_SERIES_LABEL_CHARS = 60
MAX_LABEL_CHARS = 80

# Keys whose string values are settings rather than text drawn on the figure —
# a colormap name, a format string, an aspect ratio. Capping them would be
# harmless (they are all short) but the error message would be nonsense, and
# more importantly a future long-but-legitimate setting must not be refused
# for being long.
_NOT_DRAWN = frozenset(
    {
        "type",
        "aspect",
        "cmap",
        "fmt",
        "value_format",
        "legend_loc",
        "font_family",
        "sort",
        "orientation",
        "kind",
        "scale",
        "method",
        "color",
        "colour",
    }
)

_LIMITS = {
    "title": MAX_TITLE_CHARS,
    "xlabel": MAX_AXIS_LABEL_CHARS,
    "ylabel": MAX_AXIS_LABEL_CHARS,
    "cbar_label": MAX_AXIS_LABEL_CHARS,
    "size_label": MAX_AXIS_LABEL_CHARS,
    "label": MAX_SERIES_LABEL_CHARS,
}

_ADVICE = {
    "title": (
        "A title is a heading, not a caption — one line that names what the "
        "figure shows. Move the detail into the figure's caption, which has "
        "the whole column width and as many lines as it needs."
    ),
    "xlabel": "An axis label is a quantity and its unit, e.g. 'Latency (ms)'.",
    "ylabel": "An axis label is a quantity and its unit, e.g. 'Accuracy (%)'.",
    "cbar_label": "A colourbar label is a quantity and its unit, e.g. 'Pearson r'.",
    "size_label": "A size-key label is a quantity and its unit, e.g. 'Parameters (B)'.",
    "label": (
        "A legend entry names one series in a few words; every extra "
        "character is taken from the plot area."
    ),
}


def _check_text_lengths(spec: dict, path: str = "") -> None:
    """Refuse text too long for the slot it will be drawn in.

    Walks the WHOLE spec rather than a list of known keys, so a renderer
    added later gets the same protection without anyone remembering to
    register its text fields. Values under keys that are settings rather
    than drawn text are skipped by name.
    """
    for key, value in spec.items():
        if key in _NOT_DRAWN:
            continue
        where = f"{path}{key}"
        if isinstance(value, str):
            limit = _LIMITS.get(key, MAX_LABEL_CHARS)
            if len(value) > limit:
                advice = _ADVICE.get(key, "Shorten it, and explain it in the caption.")
                raise SpecError(
                    f"'{where}' is {len(value)} characters, past the {limit} that "
                    f"fits. {advice} It starts: {value[:60]!r}…"
                )
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, str) and len(item) > MAX_LABEL_CHARS:
                    raise SpecError(
                        f"'{where}[{i}]' is {len(item)} characters, past the "
                        f"{MAX_LABEL_CHARS} that fits on a figure. Shorten it and "
                        f"explain it in the caption. It starts: {item[:60]!r}…"
                    )
                if isinstance(item, dict):
                    _check_text_lengths(item, f"{where}[{i}].")
        elif isinstance(value, dict):
            _check_text_lengths(value, f"{where}.")


def _number(spec: dict, key: str, *, minimum: float | None = None) -> float | None:
    value = spec.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise SpecError(f"'{key}' must be a number, got {value!r}")
    if minimum is not None and value < minimum:
        raise SpecError(f"'{key}' must be at least {minimum}, got {value!r}")
    return float(value)


def _limits(spec: dict, key: str) -> tuple[float, float] | None:
    value = spec.get(key)
    if value is None:
        return None
    if not isinstance(value, list | tuple) or len(value) != 2:
        raise SpecError(f"'{key}' must be a two-element list [low, high], got {value!r}")
    lo, hi = value
    for v in (lo, hi):
        if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(v):
            raise SpecError(f"'{key}' bounds must be finite numbers, got {value!r}")
    if lo >= hi:
        raise SpecError(
            f"'{key}' is [{lo}, {hi}] — low must be below high. A reversed range "
            "flips the axis and hangs the bars downward."
        )
    return float(lo), float(hi)


def validate_spec(spec: object) -> dict:
    """Check a whole spec tree. Returns it unchanged, or raises ``SpecError``."""
    if not isinstance(spec, dict):
        raise SpecError(
            f"a spec must be a JSON object, got {type_name(spec)}. "
            'Example: {"type": "bar", "series": [{"values": [1, 2, 3]}]}'
        )

    _check_text_lengths(spec)
    check_font_family(spec)
    _number(spec, "font_pt", minimum=1)
    _number(spec, "width_in", minimum=0.5)
    _limits(spec, "ylim")
    _limits(spec, "xlim")

    width = spec.get("width_in")
    if isinstance(width, int | float) and width > MAX_WIDTH_IN:
        raise SpecError(f"'width_in' of {width} inches is far past print size (max {MAX_WIDTH_IN})")

    aspect = spec.get("aspect")
    if aspect is not None and not isinstance(aspect, str):
        raise SpecError(f"'aspect' must be a \"W:H\" string, got {aspect!r}")
    if isinstance(aspect, str):
        # ``figsize_for`` falls back to 16:9 on anything it cannot parse, and
        # says nothing. So ``"16x9"`` drew the shape that was wanted by luck
        # while ``"4x3"`` drew a 16:9 figure — the wrong shape, at exit 0,
        # under a caption written for the other one. Nothing downstream
        # compares the shape it asked for against the shape it got.
        # No length check before the unpack: unpacking a generator of the
        # wrong length raises ValueError itself, into this same handler, with
        # this same refusal coming out. Checked against "16", "16:9:3", ":",
        # "" and "16:" among others — every one produced the identical message
        # with the guard and without it, so it was only ever a second spelling
        # of the line below.
        try:
            width_ratio, height_ratio = (float(part) for part in aspect.split(":"))
        except ValueError:
            raise SpecError(
                f"'aspect' is {aspect!r}; it must be two positive numbers "
                'separated by a colon, like "16:9" or "4:3".'
            ) from None
        if width_ratio <= 0 or height_ratio <= 0:
            raise SpecError(
                f"'aspect' is {aspect!r}. Both sides must be above zero — a "
                "zero or negative side has no shape to draw."
            )

    bins = spec.get("bins")
    if bins is not None:
        if isinstance(bins, bool) or not isinstance(bins, int) or bins < 1:
            raise SpecError(f"'bins' must be a positive integer, got {bins!r}")
        if bins > MAX_BINS:
            raise SpecError(f"'bins' of {bins} is past any readable histogram (max {MAX_BINS})")

    series = spec.get("series")
    if series is not None:
        if not isinstance(series, list):
            raise SpecError(f"'series' must be a list, got {type_name(series)}")
        for i, entry in enumerate(series):
            if not isinstance(entry, dict):
                raise SpecError(
                    f"series[{i}] must be an object, got {type_name(entry)}. "
                    'Each entry looks like {"label": "Ours", "values": [1, 2, 3]}'
                )
            label = entry.get("label")
            if label is not None and not isinstance(label, str):
                raise SpecError(f"series[{i}].label must be a string, got {label!r}")

    if spec.get("type") == "panel":
        panels = spec.get("panels")
        if panels is not None:
            if not isinstance(panels, list):
                raise SpecError(f"'panels' must be a list, got {type_name(panels)}")
            if len(panels) > MAX_PANELS:
                raise SpecError(
                    f"{len(panels)} panels is past what one figure can carry "
                    f"(max {MAX_PANELS}) — split it into several figures"
                )
            for i, panel in enumerate(panels):
                if not isinstance(panel, dict):
                    raise SpecError(f"panels[{i}] must be an object, got {type_name(panel)}")
                if panel.get("type") == "panel":
                    raise SpecError(f"panels[{i}] is itself a panel — panels do not nest")
                validate_spec(panel)
        ncols = spec.get("ncols")
        if ncols is not None and (
            isinstance(ncols, bool) or not isinstance(ncols, int) or ncols < 1
        ):
            raise SpecError(f"'ncols' must be a positive integer, got {ncols!r}")
    elif spec.get("panels") is not None:
        raise SpecError('\'panels\' only applies to a spec with "type": "panel"')

    return spec


def check_canvas(figsize: tuple[float, float], dpi: int) -> None:
    """Refuse a canvas too large to be a figure.

    ``aspect: "1:100"`` produced 1400x140000 px — 196 megapixels. It exited 0,
    so nothing flagged it, and Pillow then refused to reopen the result, which
    silently breaks the read-it-back verification step this skill asks for.
    """
    pixels = figsize[0] * dpi * figsize[1] * dpi
    if pixels > MAX_PIXELS:
        raise SpecError(
            f"this aspect and width give a {pixels / 1e6:.0f} megapixel canvas "
            f"(max {MAX_PIXELS / 1e6:.0f}). Use a less extreme 'aspect', or split "
            "the figure into a 'panel'."
        )


# ---------------------------------------------------------------------------
# Keys nothing ever looked at
# ---------------------------------------------------------------------------
# A spec key that no renderer reads is silently dropped, and the figure comes
# back missing whatever it asked for. ``x_label``/``y_label`` instead of
# ``xlabel``/``ylabel`` is the live example: a natural guess, accepted without
# complaint, and the figure arrives with no axis labels at all — failing the
# first item on the verification checklist the caller was handed, in a way
# that only shows up if they look closely at the picture.
#
# Rather than police against a hand-written list of ~100 valid keys across 55
# renderers — which would be wrong the day a renderer adds one, and wrong in
# the direction that REJECTS a good spec — every dict in the spec records what
# was looked up while the figure was drawn. Whatever nothing asked for is what
# gets reported.


class RecordingDict(dict):
    """A spec node that remembers which of its keys were read.

    Installed as ``json.loads(..., object_hook=...)``, so it wraps every
    object in the spec — panels and series included — at parse time.
    """

    __slots__ = ("read",)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read = set()

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)

    def __contains__(self, key) -> bool:
        self.read.add(key)
        return super().__contains__(key)


def ignored_keys(node, path: str = "spec") -> list[tuple[str, str]]:
    """``(path, key)`` for every key the render never looked at."""
    found: list[tuple[str, str]] = []
    if isinstance(node, RecordingDict):
        found += [(path, key) for key in node if key not in node.read]
    if isinstance(node, dict):
        for key, value in node.items():
            found += ignored_keys(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += ignored_keys(value, f"{path}[{index}]")
    return found


def assert_nothing_was_ignored(spec, example: dict | None = None) -> None:
    """Refuse a spec carrying keys the figure was not built from.

    ``example`` is the catalogue entry for this chart type; its keys are what
    the near-miss suggestion is drawn from, so the hint is the real spelling
    for THIS type rather than a global list.
    """
    ignored = ignored_keys(spec)
    if not ignored:
        return
    import difflib

    known = set()
    if isinstance(example, dict):

        def collect(node) -> None:
            if isinstance(node, dict):
                known.update(node.keys())
                for value in node.values():
                    collect(value)
            elif isinstance(node, list):
                for value in node:
                    collect(value)

        collect(example)

    lines = []
    for path, key in ignored:
        close = difflib.get_close_matches(key, sorted(known - {key}), n=1, cutoff=0.7)
        did_you_mean = f" — did you mean {close[0]!r}?" if close else ""
        lines.append(f"{path}.{key}{did_you_mean}")
    raise SpecError(
        "nothing read "
        + ("these keys: " if len(lines) > 1 else "this key: ")
        + "; ".join(lines)
        + ". A key no renderer looks at is dropped, and the figure comes back "
        "without whatever it asked for. Remove it or fix the spelling — "
        "'chart_gen.py --example <type>' prints every key this type accepts."
    )


def check_font_family(spec: dict) -> None:
    """Refuse a ``font_family`` this machine cannot resolve.

    The key exists for one reason: DejaVu covers Latin, Greek, Cyrillic and
    Hebrew, and a script it lacks needs a covering font put FIRST. matplotlib
    silently falls back to the default when the name does not resolve, so the
    request did nothing — and for the case the key exists for, the figure then
    fails the glyph gate instead, blaming the script rather than the font name
    that was never found.
    """
    family = spec.get("font_family")
    if family is None:
        return
    if not isinstance(family, str) or not family.strip():
        raise SpecError(
            f"'font_family' must be the name of an installed font, got {family!r}. "
            "It exists to put a font covering your script FIRST — e.g. "
            "'Noto Sans CJK JP' for Japanese."
        )
    from matplotlib import font_manager

    try:
        font_manager.findfont(family, fallback_to_default=False)
    except ValueError:
        import difflib

        installed = sorted({f.name for f in font_manager.fontManager.ttflist})
        close = difflib.get_close_matches(family, installed, n=3, cutoff=0.6)
        suggestion = f" Closest installed: {', '.join(repr(c) for c in close)}." if close else ""
        raise SpecError(
            f"font_family {family!r} is not installed here, so matplotlib would fall back to "
            f"the default and your script would still be drawn in a font that may not cover "
            f"it.{suggestion} {len(installed)} families are available."
        ) from None
