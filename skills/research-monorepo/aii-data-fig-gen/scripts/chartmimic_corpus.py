"""The ChartMimic exemplar corpus — the second half of ``--search``.

Our 61 generator types answer "what should I plot?" only when one of them
fits. ChartMimic (arXiv:2406.09961) is 4,800 human-curated figures lifted out
of real STEM papers, each with the matplotlib code that draws it, over 22
categories. It is what a model should reach for in the two cases the catalogue
cannot serve:

* **no generator fits** — a pie chart, a plot-in-plot inset, a 3-D surface, a
  bar-and-line combination. The audit below measures exactly which those are.
* **a reference is wanted** — how a published figure sets up a twin axis, or
  labels a contour, in working code rather than in prose.

An exemplar is NEVER a spec. It is somebody else's matplotlib, in somebody
else's style, with no data-integrity guard and no house palette; adapting it is
a hand-written figure, with everything the skill says about hand-written
figures still applying. ``chart_search`` labels it as such and prints where the
code lives, because a ranked list that does not say which half of it is
runnable invites the model to pass an exemplar id to ``--example``.

The corpus itself is ~450 MB and gitignored (``aii_data/chartmimic/``). What is
tracked is ``chartmimic_index.json``, one compact record per exemplar, written
by ``chartmimic_index_build.py``. This module reads that index and scores it
with the same tokenizer, synonyms, stems and stopwords ``chart_search`` uses on
our own types — one vocabulary across both corpora, or a query that reaches a
generator would silently miss the exemplar that answers it better.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Iterable

INDEX_PATH = Path(__file__).resolve().parent / "chartmimic_index.json"

# Which of OUR types answers each ChartMimic category. Curated, like INTENTS,
# and for the same reason: no derivation gets from "ChartMimic calls this
# category Tree" to "it is a squarify treemap, so our `treemap` covers it and
# our `tree` does not". Every entry below was checked against the category's
# own code — Tree imports squarify in 160 of 160 files, Graph imports networkx
# in 160 of 160.
#
# An EMPTY tuple is the point of this table: it names a question our catalogue
# cannot answer with a generator, so a future generator author knows what to
# add and a model knows to hand-write instead of forcing a near-miss type.
COVERAGE: dict[str, tuple[str, ...]] = {
    "3d": (),
    "CB": (),
    "HR": (),
    "PIP": (),
    "area": ("area", "stacked_pct", "fan"),
    "bar": ("bar", "barh", "bar_sig", "lollipop", "diverging", "waterfall", "stacked_pct"),
    "box": ("box", "raincloud", "strip", "beeswarm"),
    "contour": ("contour", "hist2d"),
    "density": ("ridgeline", "hist", "fan", "hexbin", "contour"),
    "errorbar": ("bar", "line", "forest", "fan"),
    "errorpoint": ("forest", "scatter", "cd_diagram"),
    "graph": ("network", "sankey", "tree"),
    "heatmap": ("heatmap", "catmap", "corr", "clustermap"),
    "hist": ("hist", "ecdf", "qq"),
    "line": ("line", "step", "bump", "slope", "scaling", "learning_curve", "speedup", "acf"),
    "multidiff": ("panel",),
    "pie": (),
    "quiver": ("quiver",),
    "radar": ("radar",),
    "scatter": ("scatter", "bubble", "joint", "splom", "pareto", "hexbin", "hist2d"),
    "tree": ("treemap",),
    "violin": ("violin", "raincloud", "ridgeline"),
}

# What to do instead, for each category with no generator. A gap without a
# next step is a complaint; with one it is a decision.
GAPS: dict[str, str] = {
    "pie": "no pie renderer, deliberately — a pie is read worse than the "
    "`barh`, `stacked_pct` or `treemap` that answer the same question. "
    "Hand-write one only when a venue demands it.",
    "3d": "no 3-D renderer — a projected surface hides data behind data. "
    "Prefer `heatmap` or `contour` for a scalar field over two axes.",
    "PIP": "no inset. `panel` places axes SIDE BY SIDE, which is not the "
    "same figure. Hand-write `ax.inset_axes` when a zoom must overlay.",
    "CB": "no dual-axis / mixed-mark type — bars and a line on one axes, "
    "usually with `twinx`. The single most common real gap.",
    "HR": "ChartMimic's own catch-all for figures that fit no category; "
    "by construction nothing covers it. Hand-write.",
}


class Exemplar(NamedTuple):
    """One ChartMimic figure, as the index records it."""

    id: str
    task: str
    category: str
    subtype: str
    intent: str
    features: tuple[str, ...]

    @property
    def key(self) -> str:
        """``task/id`` — the identifier that is actually unique.

        ChartMimic numbers each task folder from 1, so ``pie_16`` names TWO
        different files: ``direct_600/pie_16.py`` (reproduce this figure) and
        ``customized_600/pie_16.py`` (the same design redrawn from different
        data). Measured on the pinned release: 2,400 distinct ids across 4,800
        exemplars, every one of them used exactly twice. Ranking on the bare id
        would print the same name for two different results and make the order
        between them undefined, which is the one thing this search promises not
        to do.
        """
        return f"{self.task}/{self.id}"


_CACHE: tuple[dict, tuple[Exemplar, ...]] | None = None


def load(path: Path = INDEX_PATH) -> tuple[dict, tuple[Exemplar, ...]]:
    """``(provenance, exemplars)`` from the tracked index, read once per process.

    Returns an EMPTY corpus when the index is missing rather than raising: the
    index is a build artifact of a gitignored 450 MB store, and ``--search``
    over our own 61 types has to keep working in a checkout that never fetched
    it. A missing optional corpus degrades; it does not break the tool.
    """
    global _CACHE
    if _CACHE is None:
        if not path.exists():
            _CACHE = ({}, ())
        else:
            raw = json.loads(path.read_text(encoding="utf-8"))
            _CACHE = (
                raw.get("provenance", {}),
                tuple(
                    Exemplar(
                        e["id"],
                        e["task"],
                        e["category"],
                        e["subtype"],
                        e["intent"],
                        tuple(e.get("features", ())),
                    )
                    for e in raw.get("exemplars", ())
                ),
            )
    return _CACHE


def paths(exemplar: Exemplar, provenance: dict) -> tuple[str, str]:
    """``(code, image)`` inside the gitignored store, as the index's provenance
    describes the layout. The pattern is stored once rather than two literal
    strings per entry — 9,600 paths would add ~470 KB to a file with a 2 MB cap.
    """
    store = provenance.get("store", "aii_data/chartmimic").split(" ")[0]
    fields = {"task": exemplar.task, "id": exemplar.id}
    code = provenance.get("code_path", "iclr/{task}/{id}.py").format(**fields)
    image = provenance.get("image_path", "iclr/{task}/{id}.png").format(**fields)
    return f"{store}/{code}", f"{store}/{image}"


def category_name(category: str, provenance: dict) -> str:
    """ChartMimic's own name for a category — ``CB`` alone tells a reader nothing."""
    return provenance.get("category_names", {}).get(category, category)


def audit(provenance: dict, exemplars: Iterable[Exemplar], known: Iterable[str]) -> list[tuple]:
    """One row per ChartMimic category: ``(key, name, n, covered, missing)``.

    ``missing`` is the curated types that are NOT registered renderers, so a
    coverage claim that has gone stale — a renderer renamed or removed —
    surfaces as a row rather than as a quietly wrong table.
    """
    registered = set(known)
    counts: dict[str, int] = {}
    for exemplar in exemplars:
        counts[exemplar.category] = counts.get(exemplar.category, 0) + 1
    rows = []
    for key in sorted(COVERAGE, key=lambda k: (-counts.get(k, 0), k)):
        ours = COVERAGE[key]
        rows.append(
            (
                key,
                category_name(key, provenance),
                counts.get(key, 0),
                tuple(t for t in ours if t in registered),
                tuple(t for t in ours if t not in registered),
            )
        )
    return rows


def audit_table(provenance: dict, exemplars: Iterable[Exemplar], known: Iterable[str]) -> str:
    """The audit as a terminal table, gaps called out under it."""
    rows = audit(provenance, exemplars, known)
    out = [
        f"ChartMimic coverage — {provenance.get('count', 0)} exemplars, "
        f"{provenance.get('dataset', '?')} @ {provenance.get('revision', '?')[:12]}\n",
        f"  {'category':<20}{'n':>5}  our types",
        f"  {'-' * 20}{'-' * 5}  {'-' * 40}",
    ]
    for _key, name, count, covered, missing in rows:
        types = ", ".join(covered) if covered else "— none —"
        if missing:
            types += f"   [STALE: {', '.join(missing)}]"
        out.append(f"  {name:<20}{count:>5}  {types}")
    out.append("\nWhat ChartMimic has that we do not:\n")
    for key in sorted(GAPS):
        note = f"{category_name(key, provenance)}: {GAPS[key]}"
        out.append(textwrap.fill(note, width=76, initial_indent="  ", subsequent_indent="    "))
    return "\n".join(out)


__all__ = [
    "COVERAGE",
    "GAPS",
    "INDEX_PATH",
    "Exemplar",
    "audit",
    "audit_table",
    "category_name",
    "load",
    "paths",
]
