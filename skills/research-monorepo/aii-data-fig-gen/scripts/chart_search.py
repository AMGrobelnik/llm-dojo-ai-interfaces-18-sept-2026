"""Search two chart corpora by the QUESTION a figure has to answer.

``--list-types`` prints all 61 entries indexed by NAME, which is the right
surface once you know the name and the wrong one when you do not. An agent
picking a figure does not think "I want a dumbbell"; it thinks "I need to show
that the GAP between two conditions is the story". A name index cannot answer
that, and neither can grep: "gap" occurs on exactly one line of
``--list-types``, so a literal search finds `dumbbell` and misses `slope`,
`forest` and `diverging`, which answer the same question.

So this module adds the layer the docstrings cannot carry on their own: an
INTENT index mapping the handful of things a figure is ever FOR onto the types
that serve each one. The docstrings stay the single source of truth for what a
type DOES -- they are read live from ``RENDERERS``, never copied here, so a
renderer whose docstring changes cannot drift out of sync with its blurb.

Scoring is deliberately boring and explainable, because an agent has to be able
to act on the ranking rather than trust it:

    3 x  the query names the type outright ("roc curve" -> roc)
    2 x  the query hits an INTENT tag the type is indexed under
    1 x  plain token overlap with the type's live docstring

Ties break alphabetically so the output is deterministic -- two runs of the
same query produce the same ranking, which matters when the caller is a model
whose prompt cache keys on exact text.

`panel` is deliberately absent from the intent index: it composes other types
rather than answering a question of its own, so surfacing it as an answer to
"how do I show a distribution" would be noise. It is still reachable by name.

TWO CORPORA
-----------

Our 61 types are the preferred answer and are not the only one. The second
corpus is ChartMimic (``chartmimic_corpus``): 4,800 human-curated figures out
of real STEM papers, each with the matplotlib code that draws it. It answers
the question our catalogue cannot -- "what do I do when NOTHING fits?" -- for
the five categories the audit measures as uncovered (pie, 3-D, plot-in-plot,
bar-and-line combinations, and ChartMimic's own catch-all), and it is a
working-code reference for everything else.

Every result is labelled by the corpus it came from, because the two are used
differently and confusing them wastes a whole render cycle:

    ours: <type>              runnable -- `--example <type>` prints a spec
    chartmimic: <id>          a REFERENCE -- read the .py and adapt it

An exemplar is scored on the same scale with the same tokenizer, so one
vocabulary reaches both corpora:

    3 x  the query names the exemplar's CATEGORY ("pie chart" -> pie_7)
    2 x  the fraction of the QUERY its intent line covers
    2 x  the feature keywords the query names, capped at one tag's worth

Coverage rather than raw token count, because an exemplar's intent line is a
paper's chart title plus its axis names -- 15-25 words against a renderer's
one-sentence docstring. Counting raw overlap would let LENGTH buy rank, and the
wordiest exemplar would beat the type that answers the question. Coverage asks
the question that matters instead: how much of what was ASKED does this answer?

On a tie, a generator outranks an exemplar. That is the whole preference
ordering, encoded once in the sort key: a generator is runnable, house-styled
and guarded, so when the two are equally good the runnable one wins.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

import chartmimic_corpus

if TYPE_CHECKING:
    from collections.abc import Iterable

# The analytic intents a figure can serve. Keys are the vocabulary a caller
# actually types; values are the types that genuinely answer it.
#
# Curated rather than derived, and that is the whole point of the module: the
# mapping from "I need to show X" to a type name is exactly the knowledge the
# docstrings do NOT contain. Membership is deliberately generous -- a type
# earns a tag if it is a REASONABLE answer, not only if it is the best one,
# because a caller who sees three candidates picks better than one handed a
# single verdict.
INTENTS: dict[str, tuple[str, ...]] = {
    "compare groups": (
        "bar",
        "barh",
        "bar_sig",
        "box",
        "violin",
        "raincloud",
        "strip",
        "beeswarm",
        "dumbbell",
        "lollipop",
        "radar",
        "forest",
    ),
    "rank": ("barh", "lollipop", "bump", "slope", "diverging", "cd_diagram", "dumbbell"),
    "change over time": ("line", "area", "step", "bump", "slope", "fan", "timeline", "acf"),
    "before and after": ("slope", "dumbbell", "waterfall", "diverging", "bar"),
    "distribution": (
        "hist",
        "box",
        "violin",
        "raincloud",
        "beeswarm",
        "strip",
        "ecdf",
        "ridgeline",
        "qq",
        "fan",
    ),
    "compare distributions": ("ecdf", "ridgeline", "violin", "box", "raincloud", "hist"),
    "relationship": ("scatter", "bubble", "joint", "hexbin", "hist2d", "splom", "corr", "contour"),
    "correlation": ("corr", "scatter", "splom", "joint", "clustermap"),
    "part of a whole": ("stacked_pct", "area", "treemap", "waterfall", "funnel", "bar"),
    "composition": ("stacked_pct", "treemap", "area", "sankey", "upset"),
    "flow": ("sankey", "funnel", "quiver", "network"),
    "hierarchy": ("tree", "treemap", "dendrogram", "clustermap"),
    "structure": ("network", "tree", "dendrogram", "splom", "parallel"),
    "uncertainty": ("forest", "fan", "line", "bar", "learning_curve", "survival", "box"),
    "significance": ("bar_sig", "volcano", "forest", "cd_diagram", "acf"),
    "effect size": ("forest", "volcano", "diverging", "dumbbell"),
    "classifier performance": ("roc", "pr", "calibration", "heatmap", "catmap"),
    "confusion matrix": ("heatmap", "catmap"),
    "model agreement": ("bland_altman", "calibration", "scatter", "residual", "qq"),
    "model fit": ("residual", "qq", "calibration", "scatter", "learning_curve"),
    "scaling": ("scaling", "learning_curve", "speedup", "line"),
    "ablation": ("waterfall", "heatmap", "bar", "diverging", "forest"),
    "matrix": ("heatmap", "corr", "catmap", "clustermap", "contour", "hist2d"),
    "many categories": ("lollipop", "barh", "ridgeline", "treemap", "heatmap"),
    "many variables": ("splom", "parallel", "radar", "corr", "clustermap"),
    "density": ("hexbin", "hist2d", "contour", "beeswarm", "ridgeline"),
    "trade-off": ("pareto", "roc", "pr", "scatter", "radar"),
    "survival": ("survival",),
    "sequence": ("seqheat", "step", "line", "acf"),
    "schedule": ("timeline",),
    "set overlap": ("upset",),
}

# Query words that mean the same thing as a word already in an intent key or a
# docstring. Kept small on purpose: every entry is a word a caller plausibly
# types that would otherwise score zero, not a thesaurus dump.
SYNONYMS: dict[str, str] = {
    "versus": "compare",
    "vs": "compare",
    "against": "compare",
    "difference": "compare",
    "differ": "compare",
    "gap": "compare",
    "spread": "distribution",
    "variance": "distribution",
    "variability": "distribution",
    "outlier": "distribution",
    "quartile": "distribution",
    "percentile": "distribution",
    "trend": "time",
    "temporal": "time",
    "longitudinal": "time",
    "series": "time",
    "proportion": "composition",
    "percentage": "composition",
    "share": "composition",
    "breakdown": "composition",
    "whole": "composition",
    "accuracy": "classifier",
    "auc": "classifier",
    "precision": "classifier",
    "recall": "classifier",
    "roc": "classifier",
    "cluster": "hierarchy",
    "tree": "hierarchy",
    "nested": "hierarchy",
    "graph": "network",
    "node": "network",
    "edge": "network",
    "error": "uncertainty",
    "confidence": "uncertainty",
    "interval": "uncertainty",
    "ci": "uncertainty",
    "band": "uncertainty",
    "speedup": "scaling",
    "throughput": "scaling",
    "parallel": "scaling",
    "pareto": "trade-off",
    "frontier": "trade-off",
    "correlate": "correlation",
    "association": "correlation",
    "rank": "rank",
    "ordering": "rank",
    "leaderboard": "rank",
}

_WORD = re.compile(r"[a-z0-9_]+")

# Suffixes stripped so a query verb meets the noun an intent key is named
# with. Without this, "how does accuracy SCALE" misses the "scaling" intent
# entirely -- the single worst failure found while testing, because the query
# then fell through to classifier-performance types on the word "accuracy"
# alone and ranked calibration above scaling. Applied to BOTH sides, so the
# stem only has to be consistent, never linguistically correct.
_SUFFIXES = ("ising", "izing", "ing", "ed", "es", "s", "e")


def _stem(word: str) -> str:
    """Crude suffix strip; consistency matters, correctness does not."""
    for suf in _SUFFIXES:
        if len(word) > len(suf) + 3 and word.endswith(suf):
            return word[: -len(suf)]
    return word


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens, synonym-folded then stemmed."""
    raw = _WORD.findall(text.lower())
    return {_stem(SYNONYMS.get(w, w)) for w in raw}


def _blurb(renderers: dict, name: str) -> str:
    """First docstring line of a renderer -- the live source of truth."""
    if name == "panel":
        return "Compose any of the above into a labelled grid."
    return (renderers[name].__doc__ or "").strip().split("\n")[0]


# Words that carry no analytic intent. Without these, "show me a MODEL" grants
# an intent hit on both "model agreement" and "model fit", and a type indexed
# under several such intents out-scores the type that actually answers the
# question -- measured: "how does accuracy scale with model size" ranked
# calibration first (3 intents x 2.0) and scaling nowhere.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "do",
        "does",
        "for",
        "from",
        "how",
        "i",
        "in",
        "is",
        "it",
        "its",
        "me",
        "my",
        "of",
        "on",
        "or",
        "over",
        "show",
        "the",
        "their",
        "to",
        "two",
        "want",
        "we",
        "what",
        "when",
        "which",
        "with",
        "you",
        "your",
        "plot",
        "chart",
        "figure",
        "graph",
        "draw",
        "need",
        "use",
        "best",
        "good",
        "model",
    ]
)


def _intent_hits(query_tokens: set[str], name: str) -> list[tuple[str, float]]:
    """Intent keys this type is under, each weighted by how much the query covers.

    An intent scores in proportion to the fraction of ITS OWN words the query
    supplies, so "scaling" fully matched by "scale" beats "model fit" matched
    on the generic half of its name. A flat per-intent score cannot make that
    distinction and is what let a 3-intent type win on one common word.
    """
    hits: list[tuple[str, float]] = []
    for intent, members in INTENTS.items():
        if name not in members:
            continue
        words = _tokens(intent) - _STOPWORDS
        if not words:
            continue
        covered = words & query_tokens
        if covered:
            hits.append((intent, len(covered) / len(words)))
    return hits


class Hit(NamedTuple):
    """One ranked result, from either corpus.

    The first four fields are the tuple ``rank`` has always returned, in
    the same order, so a caller that unpacks ``(name, score, blurb, why)`` or
    reads ``row[0]`` keeps working. ``corpus`` and ``where`` are additive.
    """

    name: str
    score: float
    blurb: str
    why: list[str]
    corpus: str = "ours"
    where: str = ""


# Sort tier per corpus. Second key in the ranking, after the score itself:
# equal scores resolve to the RUNNABLE answer, never to whichever string sorts
# first. A generator carries the house style, the layout passes and the
# data-integrity guards; an exemplar carries none of them.
_CORPUS_ORDER = {"ours": 0, "chartmimic": 1}
CORPORA = ("ours", "chartmimic", "all")

# The exemplar feature term's ceiling, in units of one fully-covered intent
# tag. Six keywords could otherwise stack to 12 and let a feature list
# out-argue every curated intent in the catalogue; a keyword is a hint about
# what the code DEMONSTRATES, not a claim about what the figure is FOR.
_FEATURE_CAP = 2.0


def _rank_ours(q: set[str], query: str, renderers: dict, limit: int) -> list[Hit]:
    """Our own catalogue, scored name 3x / covered intent 2x / docstring 1x."""
    scored: list[Hit] = []
    for name in (*renderers, "panel"):
        blurb = _blurb(renderers, name)
        hits = _intent_hits(q, name)
        score = 0.0
        if _stem(name) in q or name.replace("_", " ") in query.lower():
            score += 3.0
        score += 2.0 * sum(weight for _intent, weight in hits)
        score += len(q & (_tokens(blurb) - _STOPWORDS))
        if score > 0:
            scored.append(Hit(name, score, blurb, [i for i, _w in hits], "ours"))
    scored.sort(key=lambda row: (-row.score, row.name))
    return scored[:limit]


def _rank_chartmimic(q: set[str], query: str, limit: int) -> list[Hit]:
    """ChartMimic exemplars, scored category 3x / query coverage 2x / features 2x.

    Returns an empty list when the index is absent, which is the state of any
    checkout that has not fetched the gitignored corpus -- searching our own
    types must not depend on a 450 MB download being present.
    """
    provenance, exemplars = chartmimic_corpus.load()
    scored: list[tuple[str, Hit]] = []
    for item in exemplars:
        name = chartmimic_corpus.category_name(item.category, provenance)
        # The category's own words, so the intent line cannot re-earn evidence
        # the 3.0 already paid for. Without this an exemplar with NO usable
        # title still scored full marks on "pie", because its placeholder text
        # ("an unlabelled Pie figure") names the category it was placed under.
        own = _tokens(f"{item.category} {name}")
        score = 0.0
        if _stem(item.category) in q or name.lower() in query.lower():
            score += 3.0
        intent_tokens = (_tokens(item.intent) - _STOPWORDS) - own
        if q and intent_tokens:
            score += 2.0 * len(q & intent_tokens) / len(q)
        feature_score = 0.0
        matched: list[str] = []
        for feature in item.features:
            words = _tokens(feature) - _STOPWORDS
            covered = words & q
            if covered:
                feature_score += len(covered) / len(words)
                matched.append(feature)
        score += min(_FEATURE_CAP, 2.0 * feature_score)
        if score > 0:
            code, _image = chartmimic_corpus.paths(item, provenance)
            why = [f"{name} / {item.subtype}", *matched]
            scored.append((item.id, Hit(item.key, score, item.intent, why, "chartmimic", code)))
    scored.sort(key=lambda row: (-row[1].score, row[1].name))
    # One row per FIGURE. Each id names two files -- the same design drawn from
    # different data -- and they score within a hair of each other, so without
    # this the four exemplar slots are routinely two figures shown twice.
    seen: set[str] = set()
    out: list[Hit] = []
    for ident, hit in scored:
        if ident in seen:
            continue
        seen.add(ident)
        out.append(hit)
        if len(out) == limit:
            break
    return out


def rank(
    query: str,
    renderers: dict,
    *,
    limit: int = 8,
    exemplars: int = 4,
    corpus: str = "all",
) -> list[Hit]:
    """Rank both corpora against a natural-language question.

    ``limit`` caps OUR types and ``exemplars`` caps ChartMimic hits, applied
    before the merge rather than after: one shared cap would let 4,800
    exemplars crowd the 61 runnable answers out of the list on any query with
    broad vocabulary, which is the opposite of the preference this module
    encodes. Anything scoring zero is dropped, so an unmatched query returns
    EMPTY rather than a confidently-ordered list of irrelevant results.
    """
    if corpus not in CORPORA:
        # Not a guard for the CLI, which argparse already constrains — a guard
        # for a library caller, whose typo would otherwise fall through both
        # branches below and return an EMPTY list indistinguishable from "no
        # chart type matched", which is the search's honest answer for a query
        # nothing serves.
        raise ValueError(f"corpus must be one of {CORPORA}, not {corpus!r}")
    q = _tokens(query) - _STOPWORDS
    rows: list[Hit] = []
    if corpus in ("ours", "all"):
        rows += _rank_ours(q, query, renderers, limit)
    if corpus in ("chartmimic", "all"):
        rows += _rank_chartmimic(q, query, exemplars)
    rows.sort(key=lambda row: (-row.score, _CORPUS_ORDER[row.corpus], row.name))
    return rows


def format_results(query: str, results: Iterable[Hit]) -> str:
    """Render the ranking for a terminal, ending in the command to run next."""
    rows = list(results)
    if not rows:
        return (
            f"no chart type matched {query!r}.\n\n"
            "  chart_gen.py --list-types    # the full catalogue\n"
            f"  known intents: {', '.join(sorted(INTENTS))}"
        )
    labels = [f"{row.corpus}: {row.name}" for row in rows]
    width = max(len(label) for label in labels)
    out = [f"chart types for {query!r}, best first:\n"]
    for label, row in zip(labels, rows, strict=True):
        out.append(f"  {label:<{width}}  {row.blurb}")
        if row.why:
            out.append(f"  {'':<{width}}  ↳ {', '.join(row.why)}")
        if row.where:
            out.append(f"  {'':<{width}}  ↳ reference code, not a spec: {row.where}")
    runnable = next((row for row in rows if row.corpus == "ours"), None)
    if runnable is not None:
        out.append(f"\n  chart_gen.py --example {runnable.name}   # a complete spec to copy")
    else:
        out.append(
            "\n  no generator covers this — read the exemplar's .py and hand-write it,"
            "\n  keeping the house style (see the skill's hand-written figure recipe)."
        )
    return "\n".join(out)


def audit(renderers: dict) -> str:
    """The ChartMimic coverage table: which categories our 61 types answer."""
    provenance, exemplars = chartmimic_corpus.load()
    if not exemplars:
        return (
            f"no ChartMimic index at {chartmimic_corpus.INDEX_PATH}.\n"
            "  chartmimic_index_build.py --fetch && chartmimic_index_build.py"
        )
    return chartmimic_corpus.audit_table(provenance, exemplars, [*renderers, "panel"])


__all__ = ["CORPORA", "INTENTS", "SYNONYMS", "Hit", "audit", "format_results", "rank"]
