#!/usr/bin/env python
"""Build ``chartmimic_index.json`` — the searchable half of the ChartMimic corpus.

ChartMimic (arXiv:2406.09961) is 4,800 human-curated ``(figure, instruction,
matplotlib code)`` triplets over 22 chart categories, taken from real STEM
papers. It is ~450 MB of tarballs, images and code, so it CANNOT live in git:
``rule-big-blob-public-only`` bans any newly added tracked file over 2 MB, and
the public-export allowlist excludes data outright.

So the raw corpus lands in the gitignored store (``aii_data/chartmimic/``) and
this script distils it into ONE compact JSON index that is tracked — id,
category, subtype, a one-line intent, the matplotlib features the exemplar
demonstrates, and where its code and image sit in the store. That index is what
``chart_search`` ranks; the store is what a model reads once the search has
pointed at an exemplar.

Two commands, in order::

    chartmimic_index_build.py --fetch     # populate aii_data/chartmimic/
    chartmimic_index_build.py             # rewrite chartmimic_index.json

``--fetch`` pins the dataset REVISION rather than tracking ``main``, so a
rebuild months from now produces the same index from the same bytes; the
revision is recorded in the index's ``provenance`` block along with the count
and the build date, because an index whose source cannot be named is an index
nobody can check.

Where the intent line comes from, and why it is not one thing:

* The 2,400 ``customized_*`` exemplars carry a REAL description in their
  instruction — "a set of data about the importance of various factors …" — so
  the subject clause of that sentence is lifted verbatim.
* The 2,400 ``direct_*`` exemplars carry a BOILERPLATE instruction ("I found a
  very nice picture in a STEM paper …"), identical for every one of them apart
  from the figsize. Indexing that would give 2,400 identical intent lines, so
  the intent is read out of the code instead: the chart's own title and axis
  names, which is exactly the text a searcher's question rhymes with.

Both are recorded per entry in ``intent_from``, so a reader can tell which.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import sys
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

# The pinned release. ``dataset-iclr.tar.gz`` is the v2 (ICLR 2025) corpus:
# four task folders, 4,800 ``<id>.py`` / ``<id>.png`` / ``<id>.pdf`` triples.
DATASET = "ChartMimic/ChartMimic"
REVISION = "0c46ca5103b03fea520fb6e5b2d87c8a0372aaf1"
TARBALL = "dataset-iclr.tar.gz"
TASKS = ("direct_600", "direct_1800", "customized_600", "customized_1800")

REPO = Path(__file__).resolve().parents[4]
STORE = REPO / "aii_data" / "chartmimic"
INDEX = Path(__file__).resolve().parent / "chartmimic_index.json"

# Layout inside the store, recorded in provenance so a reader can resolve an
# entry to a file without this script. Kept as a pattern rather than repeated
# 9,600 times: two literal paths per entry would add ~50 bytes each and the
# index has a 2 MB ceiling to stay under.
CODE_PATH = "iclr/{task}/{id}.py"
IMAGE_PATH = "iclr/{task}/{id}.png"

# ChartMimic's own taxonomy: 18 regular types plus 4 advanced ones, named as
# the paper names them (Appendix D). The keys are the filename prefixes the
# release actually uses; several are abbreviations that mean nothing on sight.
CATEGORY_NAMES: dict[str, str] = {
    "3d": "3D",
    "CB": "Combination",
    "HR": "Hard-to-Recognize",
    "PIP": "Plot-in-Plot",
    "area": "Area",
    "bar": "Bar",
    "box": "Box",
    "contour": "Contour",
    "density": "Density",
    "errorbar": "Errorbar",
    "errorpoint": "Errorpoint",
    "graph": "Graph",
    "heatmap": "Heatmap",
    "hist": "Histogram",
    "line": "Line",
    "multidiff": "Multidiff",
    "pie": "Pie",
    "quiver": "Quiver",
    "radar": "Radar",
    "scatter": "Scatter",
    "tree": "Tree",
    "violin": "Violin",
}

# matplotlib call -> the capability it demonstrates, in the words a searcher
# would use. Ordered: the first six that fire are what an entry carries, so
# two exemplars with the same calls always get the same keyword list.
FEATURES: tuple[tuple[str, str], ...] = (
    ("nx.draw_networkx_edges", "node-link graph"),
    ("nx.draw_networkx_nodes", "node-link graph"),
    ("nx.draw", "node-link graph"),
    ("squarify.plot", "treemap rectangles"),
    ("venn2", "venn diagram"),
    ("venn3", "venn diagram"),
    ("plot_surface", "3d surface"),
    ("plot_wireframe", "3d wireframe"),
    ("plot_trisurf", "3d surface"),
    ("bar3d", "3d bars"),
    ("voxels", "3d voxels"),
    ("projection=3d", "3d axes"),
    ("inset_axes", "inset axes"),
    ("twinx", "twin y-axis"),
    ("twiny", "twin x-axis"),
    ("errorbar", "error bars"),
    ("fill_between", "shaded band"),
    ("fill_betweenx", "shaded band"),
    ("stackplot", "stacked areas"),
    ("boxplot", "box and whisker"),
    ("violinplot", "violin density"),
    ("pie", "pie wedges"),
    ("barh", "horizontal bars"),
    ("bar_label", "bar value labels"),
    ("hexbin", "hex density"),
    ("hist2d", "2d histogram"),
    ("imshow", "image grid"),
    ("pcolormesh", "mesh grid"),
    ("matshow", "matrix grid"),
    ("contourf", "filled contours"),
    ("clabel", "contour labels"),
    ("quiver", "arrow field"),
    ("streamplot", "stream lines"),
    ("broken_barh", "gantt spans"),
    ("eventplot", "event raster"),
    ("stem", "stems"),
    ("step", "step line"),
    ("table", "embedded table"),
    ("colorbar", "colourbar"),
    ("annotate", "annotations"),
    ("axhline", "reference line"),
    ("axvline", "reference line"),
    ("axhspan", "shaded region"),
    ("axvspan", "shaded region"),
    ("add_patch", "custom patches"),
    ("scatter", "scatter points"),
    ("semilogy", "log scale"),
    ("semilogx", "log scale"),
    ("loglog", "log scale"),
    ("set_theta_offset", "polar axes"),
    ("legend", "legend"),
    ("grid", "grid lines"),
)
MAX_FEATURES = 6

# Structural qualifiers, first match wins. ChartMimic ships no subtype LABELS
# — the paper's "201 subcategories" are not in the release — so the subtype is
# DERIVED from the code and says so in the provenance block. It still earns its
# place: "bar / stacked" and "bar / horizontal" are different figures and a
# searcher asking for one does not want the other.
SUBTYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "3d",
        (
            "plot_surface",
            "plot_wireframe",
            "plot_trisurf",
            "bar3d",
            "voxels",
            "set_zlabel",
            "set_zticks",
            "set_zlim",
            "view_init",
            "scatter3D",
            "plot3D",
            "projection=3d",
        ),
    ),
    ("polar", ("set_theta_offset", "set_thetagrids", "set_rlabel_position")),
    ("inset", ("inset_axes",)),
    ("twin-axis", ("twinx", "twiny")),
    ("stacked", ("stackplot",)),
    ("horizontal", ("barh",)),
    ("annotated", ("annotate", "bar_label")),
)

_TITLE_CALLS = frozenset({"title", "set_title", "suptitle"})
_X_CALLS = frozenset({"xlabel", "set_xlabel"})
_Y_CALLS = frozenset({"ylabel", "set_ylabel", "set_zlabel"})

# The subject clause of a customized instruction. The sentence is templated —
# "I also have a set of data about X. Please refer to …" — so X is liftable
# without a model, and lifting it beats paraphrasing it.
_SUBJECT = re.compile(r"a set of data (?:about|on|regarding) (.+?)(?:\.\s|\.$|\n)", re.S)
_WS = re.compile(r"\s+")
INTENT_CHARS = 130


def _fetch(store: Path) -> None:
    """Download the pinned tarball and extract it into the gitignored store."""
    from huggingface_hub import hf_hub_download

    store.mkdir(parents=True, exist_ok=True)
    path = hf_hub_download(
        DATASET, TARBALL, repo_type="dataset", revision=REVISION, local_dir=str(store / "_hf")
    )
    out = store / "iclr"
    out.mkdir(exist_ok=True)
    with tarfile.open(path) as tar:
        tar.extractall(out, filter="data")
    print(f"extracted {TARBALL} -> {out}")


def _instructions(store: Path) -> dict[str, str]:
    """The cached instruction text, keyed ``task/id``; empty when absent.

    Optional on purpose. The instruction column lives in the dataset's parquet
    preview, not in the tarball, so an index built without it is still complete
    — every entry simply falls back to its code-derived intent. A missing
    optional input must degrade, not fail: this script is the only way to
    regenerate the index, and refusing to run because a 590 MB parquet fetch
    was skipped would make the index unregenerable in exactly the situation
    where regenerating it matters.
    """
    path = store / "instructions.jsonl"
    if not path.exists():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        out[f"{row['Task']}/{row['ExampleID']}"] = row["Instruction"]
    return out


def _one_line(text: str, limit: int = INTENT_CHARS) -> str:
    """Collapse to a single line and cut at a word boundary."""
    flat = _WS.sub(" ", text).strip().strip('"').strip()
    if len(flat) <= limit:
        return flat
    return flat[:limit].rsplit(" ", 1)[0] + "…"


def _string_env(tree: ast.AST) -> dict[str, str]:
    """Module-level ``name = "literal"`` bindings.

    ChartMimic's code is templated into a "Plot Configuration" block that binds
    every label to a variable first (``ylabel_value = "Scores"``), so reading
    only the literal passed to ``set_ylabel`` finds a title in 133 of 4,800
    files. Resolving one level of variable takes that to 3,900.
    """
    env: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        env[target.id] = node.value.value
    return env


def _text_arg(node: ast.expr, env: dict[str, str]) -> str | None:
    """The string an argument denotes, resolving a plain name through ``env``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value or None
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.JoinedStr):
        parts = [
            v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str)
        ]
        return " ".join(p.strip() for p in parts if p.strip()) or None
    return None


def _read_code(source: str) -> tuple[str | None, str | None, str | None, list[str]]:
    """``(title, xlabel, ylabel, calls)`` from one exemplar's matplotlib code.

    ``calls`` carries the bare attribute AND, where the receiver is a plain
    name, the dotted form — because ``nx.draw_networkx_edges`` and
    ``squarify.plot`` are the whole signal for the Graph and Tree categories
    and the bare attribute (``plot``) says nothing. ``projection="3d"`` is
    folded in as a pseudo-call for the same reason: a third of the 3D
    exemplars set the projection and never touch a ``z`` API.
    """
    tree = ast.parse(source)
    env = _string_env(tree)
    title = xlab = ylab = None
    calls: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "projection":
            if isinstance(node.value, ast.Constant) and node.value.value == "3d":
                calls.append("projection=3d")
            continue
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            # A bare call — ``venn2(...)``. Harmless noise otherwise: features
            # are matched against a curated list, never against everything.
            calls.append(node.func.id)
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        name = node.func.attr
        calls.append(name)
        if isinstance(node.func.value, ast.Name):
            calls.append(f"{node.func.value.id}.{name}")
        arg = _text_arg(node.args[0], env) if node.args else None
        if arg is None:
            continue
        if name in _TITLE_CALLS and title is None:
            title = arg
        elif name in _X_CALLS and xlab is None:
            xlab = arg
        elif name in _Y_CALLS and ylab is None:
            ylab = arg
    return title, xlab, ylab, calls


def _code_intent(title: str | None, xlab: str | None, ylab: str | None, category: str) -> str:
    """A sentence a searcher's question can rhyme with, from the chart's own words."""
    axes = ""
    if ylab and xlab:
        axes = f"{ylab} against {xlab}"
    elif ylab or xlab:
        axes = ylab or xlab or ""
    if title and axes:
        return _one_line(f"{title} — {axes}")
    if title or axes:
        return _one_line(title or axes)
    return f"an unlabelled {CATEGORY_NAMES.get(category, category)} figure"


def _features(calls: list[str]) -> list[str]:
    """Up to six capability keywords, in FEATURES order so the list is stable."""
    seen = set(calls)
    out: list[str] = []
    for call, word in FEATURES:
        if call in seen and word not in out:
            out.append(word)
            if len(out) == MAX_FEATURES:
                break
    return out


def _subtype(calls: list[str]) -> str:
    """A structural qualifier, or ``plain`` when the figure is the plain form."""
    seen = set(calls)
    for name, triggers in SUBTYPES:
        if seen & set(triggers):
            return name
    return "plain"


def _walk(store: Path) -> Iterator[tuple[str, str, Path]]:
    """``(task, id, code path)`` over the whole extracted corpus, in a fixed order."""
    for task in TASKS:
        folder = store / "iclr" / task
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.py"), key=lambda p: _sort_key(p.stem)):
            yield task, path.stem, path


def _sort_key(stem: str) -> tuple[str, int]:
    """Sort ``bar_9`` before ``bar_10`` — a string sort would not, and the index
    is committed, so a rebuild that only reorders it is a diff nobody can read.
    """
    category, _, index = stem.rpartition("_")
    return category, int(index) if index.isdigit() else 0


def build(store: Path) -> dict:
    """The whole index, ready to serialise."""
    instructions = _instructions(store)
    entries = []
    for task, ident, path in _walk(store):
        category = ident.rpartition("_")[0]
        try:
            title, xlab, ylab, calls = _read_code(
                path.read_text(encoding="utf-8", errors="replace")
            )
        except SyntaxError:
            title = xlab = ylab = None
            calls = []
        subject = _SUBJECT.search(instructions.get(f"{task}/{ident}", ""))
        if subject:
            intent, source = _one_line(subject.group(1)), "instruction"
        else:
            intent, source = _code_intent(title, xlab, ylab, category), "code"
        entries.append(
            {
                "id": ident,
                "task": task,
                "category": category,
                "subtype": _subtype(calls),
                "intent": intent,
                "intent_from": source,
                "features": _features(calls),
            }
        )
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["category"]] = counts.get(entry["category"], 0) + 1
    return {
        "provenance": {
            "dataset": DATASET,
            "revision": REVISION,
            "source": TARBALL,
            "paper": "arXiv:2406.09961",
            "built": dt.datetime.now(tz=dt.UTC).date().isoformat(),
            "builder": Path(__file__).name,
            "store": "aii_data/chartmimic (gitignored)",
            "code_path": CODE_PATH,
            "image_path": IMAGE_PATH,
            "count": len(entries),
            "per_category": dict(sorted(counts.items())),
            "category_names": CATEGORY_NAMES,
            "subtype": "derived from the code by this builder, not a ChartMimic label",
        },
        "exemplars": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--fetch", action="store_true", help="download + extract the corpus into the store first"
    )
    parser.add_argument("--store", default=str(STORE), help=f"raw corpus root (default: {STORE})")
    parser.add_argument("--out", default=str(INDEX), help=f"index to write (default: {INDEX})")
    args = parser.parse_args()

    store = Path(args.store)
    if args.fetch:
        _fetch(store)
    if not (store / "iclr").is_dir():
        print(
            f"no corpus at {store / 'iclr'} — run with --fetch first.",
            file=sys.stderr,
        )
        return 2
    index = build(store)
    out = Path(args.out)
    out.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")) + "\n", "utf-8")
    size = out.stat().st_size
    print(f"{out}: {index['provenance']['count']} exemplars, {size / 1024:.0f} KiB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
