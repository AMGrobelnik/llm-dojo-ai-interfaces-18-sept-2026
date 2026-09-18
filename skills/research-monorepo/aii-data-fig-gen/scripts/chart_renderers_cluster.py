"""Structure figures: what groups with what, and what connects to what.

The two gaps the catalogue documented and did not cover. Both are ordinary
DATA figures — the clustering is computed from the numbers and the graph is
drawn from an edge list — so both belong here rather than with an image model,
which would invent a tree that does not match the distances it claims to show.

* ``dendrogram`` — hierarchical clustering of observations. The linkage is
  computed here from the raw matrix, so the tree cannot disagree with the
  data, and the merge heights are the real cophenetic distances rather than
  a drawing.
* ``clustermap`` — the same clustering applied to a heatmap, with rows and
  columns reordered into their clusters and the trees drawn beside them.
  This is the figure a plain ``heatmap`` cannot be: block structure that is
  obvious once reordered is invisible in input order.
* ``network`` — a node-link diagram of a graph whose edges are data
  (citations, co-occurrence, message passing). Laid out by a deterministic
  force simulation seeded from a fixed circle, so the same edges always give
  the same picture — an image model gives a different graph every call, and a
  random seed gives a different one every run.

``scipy`` carries the linkage. It is not listed in ``aii_pipeline``'s
dependencies directly, but ``scikit-learn`` is, and scipy is a hard
requirement of scikit-learn — so it is present wherever this skill runs. The
import is still guarded, because a missing dependency should be a sentence
rather than a traceback.
"""

from __future__ import annotations

import numpy as np
from chart_common import (
    SpecError,
    cell_halo,
    colour_map,
    flag,
    ink_for,
    number_format,
    number_option,
    numbers,
    reject_pointless_diverging,
    require_annotations_fit,
    require_colour_limits_cover,
    type_name,
)
from chart_style import PALETTE, SEQUENTIAL_CMAP, literal, number, place_point_label

# Past this the leaves are thinner than their own labels, and a tree nobody
# can read the leaves of says nothing a summary table would not say better.
_MAX_LEAVES = 60

# Past this a force layout is a hairball: every node touches every other and
# the reader cannot follow a single edge. Measured on the drawn figure — at
# 40 nodes the labels alone cover a third of the canvas.
_MAX_NODES = 40

_LINKAGE_METHODS = ("average", "ward", "complete", "single", "centroid", "median", "weighted")


def _import_scipy_hierarchy():
    """The real collaborator: scipy's clustering module. Its own function so a
    test can inject a fake that raises ``ImportError`` without reaching for
    scipy itself or patching ``builtins.__import__``."""
    from scipy.cluster import hierarchy

    return hierarchy


def _hierarchy(*, import_hierarchy=_import_scipy_hierarchy):
    """scipy's clustering module, or a message saying it is missing."""
    try:
        hierarchy = import_hierarchy()
    except ImportError as exc:  # pragma: no cover - present wherever sklearn is
        raise SpecError(
            "hierarchical clustering needs scipy, which is not importable here "
            f"({exc}). It ships with scikit-learn, which this pipeline depends "
            "on — install it, or use 'heatmap', which needs no clustering."
        ) from exc
    return hierarchy


def _matrix_of(spec: dict, key: str = "matrix") -> np.ndarray:
    """The observations, as a rectangular float array, or a message."""
    raw = spec.get(key)
    if not isinstance(raw, list) or not raw or not all(isinstance(row, list) for row in raw):
        raise SpecError(f"'{key}' must be a non-empty list of equal-length rows of numbers")
    widths = {len(row) for row in raw}
    if len(widths) != 1:
        raise SpecError(
            f"'{key}' rows have differing lengths {sorted(widths)}. A ragged matrix "
            "cannot be clustered — every observation needs the same features."
        )
    if next(iter(widths)) == 0:
        raise SpecError(f"'{key}' rows are empty, so there is nothing to cluster on")
    return np.vstack([numbers(row, f"{key}[{r}]") for r, row in enumerate(raw)])


def _method_of(spec: dict) -> str:
    method = str(spec.get("method") or "average")
    if method not in _LINKAGE_METHODS:
        raise SpecError(
            f"'method' is {method!r}; the linkages available are "
            f"{', '.join(_LINKAGE_METHODS)}. 'average' is the safe default and "
            "'ward' the usual choice when the features are on one scale."
        )
    return method


def _names_for(spec: dict, key: str, count: int, what: str) -> list[str]:
    raw = spec.get(key)
    if not raw:
        return [str(i + 1) for i in range(count)]
    if not isinstance(raw, list):
        raise SpecError(f"'{key}' must be a list, got {type_name(raw)}")
    if len(raw) != count:
        raise SpecError(
            f"'{key}' has {len(raw)} entries but there are {count} {what}. "
            "A name attached to the wrong row is worse than no name at all, so "
            "this is refused rather than padded."
        )
    return [literal(name) for name in raw]


def _linkage(matrix: np.ndarray, method: str, what: str):
    if matrix.shape[0] < 2:
        raise SpecError(
            f"clustering needs at least two {what}, got {matrix.shape[0]}. "
            "One observation has nothing to be close to."
        )
    if matrix.shape[0] > _MAX_LEAVES:
        raise SpecError(
            f"{matrix.shape[0]} {what} is past what a readable tree carries "
            f"(max {_MAX_LEAVES}) — the leaves come out thinner than their own "
            "labels. Aggregate first, or show the matrix as a 'heatmap'."
        )
    hierarchy = _hierarchy()
    # ``ward``/``centroid``/``median`` are only defined on Euclidean distances,
    # which is exactly what ``linkage`` computes from a raw observation matrix.
    return hierarchy.linkage(matrix, method=method)


def render_dendrogram(ax, spec: dict) -> None:
    """Hierarchical clustering of the rows, drawn as a tree with merge heights.

    For "which of these group together, and how strongly" — models by their
    per-task profile, prompts by their error pattern, datasets by their
    statistics. The linkage is computed from ``matrix`` here rather than
    accepted pre-computed, so the branch heights ARE the distances at which
    the clusters merged and cannot drift from the data beside them.

    Choose over ``corr``, which shows every pairwise relationship and no
    grouping, and over ``clustermap`` when the tree is the finding and the
    values behind it are not. Choose ``clustermap`` when the reader needs both.

    Keys: ``matrix`` (rows are observations, columns their features),
    ``labels`` (one per row), ``method`` (linkage, default "average"),
    ``orientation`` ("top" or "left", default "left" so long names have room),
    ``color_threshold`` (distance below which branches are coloured by
    cluster; default colours nothing, so the tree makes no cluster claim the
    caption has not made).
    """
    matrix = _matrix_of(spec)
    labels = _names_for(spec, "labels", matrix.shape[0], "rows")
    linkage = _linkage(matrix, _method_of(spec), "rows")
    orientation = str(spec.get("orientation") or "left")
    if orientation not in ("top", "left"):
        raise SpecError(
            f"'orientation' is {orientation!r}; a dendrogram here is drawn 'left' "
            "(leaves down the y-axis, where a long name has the figure's width) "
            "or 'top' (leaves along the x-axis)."
        )
    # No type check on what comes back: `number_option` is the shared gate for
    # this key — GATED_KEYS pins it, and a source scan stops any renderer
    # reading it directly — so it has already refused a string, a bool, a list
    # and an object by the time it returns, each with a better message than the
    # duplicate here managed ("... Leave it out for 0.0."). Whatever reaches
    # this line is a number or None, and the local check could not fire.
    threshold = number_option(spec, "color_threshold", 0.0) or None

    hierarchy = _hierarchy()
    # A fixed palette rather than scipy's default, so a dendrogram matches
    # every other figure in the paper and stays colourblind-safe.
    hierarchy.set_link_color_palette(list(PALETTE[:6]))
    hierarchy.dendrogram(
        linkage,
        ax=ax,
        labels=labels,
        orientation=orientation,
        color_threshold=float(threshold) if threshold is not None else 0.0,
        above_threshold_color="#555555",
        leaf_font_size=9,
    )
    hierarchy.set_link_color_palette(None)
    ax.grid(visible=False)
    if orientation == "left":
        ax.set_xlabel(literal(spec.get("xlabel") or "Merge distance"))
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
    else:
        ax.set_ylabel(literal(spec.get("ylabel") or "Merge distance"))
        ax.spines["bottom"].set_visible(False)
        ax.tick_params(axis="x", length=0)


def render_clustermap(ax, spec: dict) -> None:
    """A heatmap whose rows and columns are reordered into their clusters.

    Block structure that is obvious once reordered is invisible in input
    order, and input order is almost always alphabetical or whatever the log
    happened to emit. The row tree is drawn beside the matrix and the column
    tree above it, so the reader can see WHY the order is what it is rather
    than being asked to trust it.

    The reordering is applied to the labels at the same time as to the values
    — they are permuted together, from one permutation — so a row can never
    end up under someone else's name, which is the defect this figure would
    otherwise be uniquely good at hiding.

    Choose over ``heatmap`` whenever the grouping matters and the row order is
    arbitrary. Choose ``heatmap`` when the order is meaningful (a confusion
    matrix's classes, a time axis), because reordering destroys it.

    Keys: ``matrix``, ``row_labels``, ``col_labels``, ``method`` (linkage),
    ``cluster_cols`` (default true), ``cmap``, ``cbar_label``, ``annotate``
    (default false — a clustermap is usually too large for cell text), and
    ``diverging`` — a red-blue map centred on zero, for SIGNED quantities
    only. On data that never crosses zero it is refused: half the range would
    go unused and every cell would land in one arm.

    ``fmt`` (default ".2f") formats the cell text when ``annotate`` is on, and
    ``vmin`` / ``vmax`` pin the colour range — which is what to use when two
    clustermaps have to be read against each other. Limits that would crop
    the data are refused: a clamped cell is not a zoom, it is a wrong reading.
    """
    matrix = _matrix_of(spec)
    rows = _names_for(spec, "row_labels", matrix.shape[0], "rows")
    cols = _names_for(spec, "col_labels", matrix.shape[1], "columns")
    method = _method_of(spec)

    hierarchy = _hierarchy()
    # Keep the REORDERED linkage, not the plain one. optimal_leaf_ordering
    # rotates branches to put similar leaves side by side; it returns a new
    # linkage, and only that one's leaves_list matches the rows the heatmap
    # ends up drawing. Handing the plain linkage to dendrogram below drew a
    # tree whose leaves were in a different order from the matrix beside it —
    # on the shipped example, 8 of 10 rows and all 6 columns pointed at a row
    # they did not belong to, so every branch height was read against the
    # wrong names.
    row_link = hierarchy.optimal_leaf_ordering(_linkage(matrix, method, "rows"), matrix)
    row_order = hierarchy.leaves_list(row_link)
    if flag(spec, "cluster_cols", True) and matrix.shape[1] >= 2:
        col_link = hierarchy.optimal_leaf_ordering(_linkage(matrix.T, method, "columns"), matrix.T)
        col_order = hierarchy.leaves_list(col_link)
    else:
        col_link, col_order = None, np.arange(matrix.shape[1])

    ordered = matrix[np.ix_(row_order, col_order)]
    rows = [rows[i] for i in row_order]
    cols = [cols[i] for i in col_order]

    diverging = flag(spec, "diverging")
    if diverging:
        reject_pointless_diverging(ordered)
    cmap = colour_map(spec, "RdBu_r" if diverging else SEQUENTIAL_CMAP)
    vmax = number_option(
        spec, "vmax", float(np.abs(ordered).max()) if diverging else float(ordered.max())
    )
    vmin = number_option(spec, "vmin", -vmax if diverging else float(ordered.min()))
    require_colour_limits_cover(
        ordered, vmin, vmax, stated=[k for k in ("vmin", "vmax") if k in spec]
    )
    image = ax.imshow(ordered, cmap=cmap, vmin=vmin, vmax=vmax, aspect="auto")

    # The trees live in insets attached to the heatmap, so they share its
    # extent exactly however constrained layout resizes the axes. A separate
    # subplot would drift out of register with the rows it describes.
    #
    # Row names go on the RIGHT. Left of the matrix is where both the tick
    # labels and the row tree want to be, and they have no way to negotiate:
    # the tree's width is a fixed fraction of the axes and the labels' is
    # whatever the names happen to measure, so the tree was drawn straight
    # through "Coder B" and "Reasoner A". Names right, tree left, nothing to
    # negotiate. It is also what every other clustermap does.
    ax.yaxis.tick_right()
    ax.yaxis.set_label_position("right")
    side = ax.inset_axes([-0.22, 0, 0.20, 1])
    hierarchy.dendrogram(
        row_link,
        ax=side,
        orientation="left",
        no_labels=True,
        color_threshold=0.0,
        above_threshold_color="#555555",
    )
    side.set_axis_off()
    side.invert_yaxis()
    if col_link is not None:
        top = ax.inset_axes([0, 1.02, 1, 0.18])
        hierarchy.dendrogram(
            col_link,
            ax=top,
            orientation="top",
            no_labels=True,
            color_threshold=0.0,
            above_threshold_color="#555555",
        )
        top.set_axis_off()

    colourbar = ax.figure.colorbar(image, ax=ax, fraction=0.046, pad=0.03)
    if spec.get("cbar_label"):
        colourbar.set_label(literal(spec["cbar_label"]))
    ax.set_xticks(np.arange(ordered.shape[1]), labels=cols)
    ax.set_yticks(np.arange(ordered.shape[0]), labels=rows)
    ax.grid(visible=False)
    if flag(spec, "annotate", False):
        fmt = number_format(spec, "fmt", ".2f")
        require_annotations_fit(
            spec,
            ordered.shape[1],
            max((number(v, fmt) for v in ordered.ravel()), key=len, default=""),
        )
        for r in range(ordered.shape[0]):
            for c in range(ordered.shape[1]):
                ax.text(
                    c,
                    r,
                    # ``number``, not ``format``: the standalone heatmap has
                    # used it since it was written, and this copy did not — so
                    # a clustermap of negative values drew "-38.80" in its
                    # cells beside a colourbar tick reading "−38.80".
                    number(ordered[r, c], fmt),
                    ha="center",
                    va="center",
                    fontsize=7.5,
                    color=ink_for(image, ordered[r, c]),
                    path_effects=cell_halo(ink_for(image, ordered[r, c])),
                )


def _spring_layout(count: int, edges: list[tuple[int, int]], iterations: int = 220) -> np.ndarray:
    """Fruchterman-Reingold, seeded from a circle so it is reproducible.

    Deterministic on purpose. The usual implementation seeds from a random
    number generator, which gives a different picture every run — so a figure
    regenerated after a caption is written no longer matches the caption, and
    a diff of two runs is meaningless. A circle seed costs nothing and makes
    the layout a function of the edges.
    """
    angles = np.linspace(0.0, 2.0 * np.pi, count, endpoint=False)
    # The tiny radial ripple breaks the exact symmetry of a regular polygon,
    # which otherwise has zero net force and never separates.
    radius = 1.0 + 0.06 * np.cos(3.0 * angles)
    position = np.column_stack([radius * np.cos(angles), radius * np.sin(angles)])
    optimal = 1.0 / np.sqrt(count)
    temperature = 0.12
    for step in range(iterations):
        delta = position[:, None, :] - position[None, :, :]
        distance = np.linalg.norm(delta, axis=-1)
        np.fill_diagonal(distance, np.inf)
        repulsion = (delta / distance[..., None] ** 2 * optimal**2).sum(axis=1)
        attraction = np.zeros_like(position)
        for a, b in edges:
            offset = position[a] - position[b]
            length = max(float(np.linalg.norm(offset)), 1e-9)
            pull = offset / length * (length**2 / optimal)
            attraction[a] -= pull
            attraction[b] += pull
        force = repulsion + attraction
        magnitude = np.maximum(np.linalg.norm(force, axis=1, keepdims=True), 1e-9)
        position += force / magnitude * np.minimum(magnitude, temperature)
        temperature *= 1.0 - step / iterations * 0.02
    span = position.max(axis=0) - position.min(axis=0)
    return (position - position.min(axis=0)) / np.maximum(span, 1e-9)


def render_network(ax, spec: dict) -> None:
    """A graph as nodes and links, laid out by a deterministic force model.

    For a graph whose edges are DATA — who cites whom, which agents exchanged
    messages, which concepts co-occur. Node area encodes ``nodes[].value``
    when given and edge width encodes ``edges[].weight``, so both channels
    come from numbers rather than from emphasis.

    Deliberately capped at a size a reader can follow. Past forty nodes a
    force layout is a hairball in which no individual edge can be traced, and
    the honest figure is an adjacency ``heatmap`` or an aggregated graph.

    Choose over a concept figure for anything with real edges: an image model
    draws a plausible graph, not yours. Choose ``sankey`` when the edges are
    flows between ordered stages, and ``heatmap`` when the graph is dense.

    Keys: ``nodes`` (list of names, or of objects with ``label``/``value``/
    ``group``), ``edges`` (list of ``[source, target]`` or objects with
    ``source``/``target``/``weight``; endpoints name a node or index it),
    ``directed`` (draw arrowheads, default false).
    """
    raw_nodes = spec.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise SpecError("'nodes' must be a non-empty list of names or objects")
    names, values, groups = [], [], []
    for i, node in enumerate(raw_nodes):
        if isinstance(node, str):
            names.append(node)
            values.append(1.0)
            groups.append(None)
            continue
        if not isinstance(node, dict) or not node.get("label"):
            raise SpecError(f"nodes[{i}] must be a name or an object with a 'label'")
        names.append(str(node["label"]))
        value = node.get("value")
        if value is None:
            value = 1.0
        if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
            raise SpecError(
                f"nodes[{i}].value is {value!r}; node area encodes it, and an area "
                "cannot be zero or negative — leave it out for an unweighted node."
            )
        values.append(float(value))
        groups.append(node.get("group"))
    if len(names) > _MAX_NODES:
        raise SpecError(
            f"{len(names)} nodes is past what a node-link diagram can show "
            f"(max {_MAX_NODES}) — the layout becomes a hairball in which no "
            "single edge can be followed. Aggregate the graph, or show the "
            "adjacency matrix as a 'heatmap'."
        )
    if len(set(names)) != len(names):
        duplicate = next(n for n in names if names.count(n) > 1)
        raise SpecError(
            f"two nodes are both called {duplicate!r}. Edges name their endpoints, "
            "so a repeated name silently attaches an edge to the wrong one."
        )
    index = {name: i for i, name in enumerate(names)}

    def endpoint(value, where: str) -> int:
        if isinstance(value, str):
            if value not in index:
                raise SpecError(
                    f"{where} names {value!r}, which is not in 'nodes'. Every edge "
                    "has to join two nodes the figure actually draws."
                )
            return index[value]
        if isinstance(value, bool) or not isinstance(value, int):
            raise SpecError(f"{where} must be a node name or an index, got {value!r}")
        if not 0 <= value < len(names):
            raise SpecError(f"{where} is index {value}, outside 0..{len(names) - 1}")
        return value

    raw_edges = spec.get("edges")
    if not isinstance(raw_edges, list) or not raw_edges:
        raise SpecError("'edges' must be a non-empty list — a graph with no edges is a scatter")
    edges, weights = [], []
    for i, edge in enumerate(raw_edges):
        if isinstance(edge, list | tuple):
            if len(edge) != 2:
                raise SpecError(f"edges[{i}] must be [source, target], got {len(edge)} entries")
            a, b, weight = edge[0], edge[1], 1.0
        elif isinstance(edge, dict):
            a, b = edge.get("source"), edge.get("target")
            weight = edge.get("weight")
            if weight is None:
                weight = 1.0
            if isinstance(weight, bool) or not isinstance(weight, int | float) or weight <= 0:
                raise SpecError(
                    f"edges[{i}].weight is {weight!r}; line width encodes it, so it "
                    "has to be above zero — leave it out for an unweighted edge."
                )
        else:
            raise SpecError(f"edges[{i}] must be [source, target] or an object")
        source, target = endpoint(a, f"edges[{i}].source"), endpoint(b, f"edges[{i}].target")
        if source == target:
            raise SpecError(
                f"edges[{i}] joins {names[source]!r} to itself. A self-loop has no "
                "readable rendering here — state it in the caption instead."
            )
        edges.append((source, target))
        weights.append(float(weight))

    position = _spring_layout(len(names), edges)
    widest = max(weights)
    for (a, b), weight in zip(edges, weights, strict=True):
        (x0, y0), (x1, y1) = position[a], position[b]
        style = {
            "color": "#9a9a9a",
            "linewidth": 0.8 + 2.2 * weight / widest,
            "zorder": 1,
            "alpha": 0.85,
        }
        if flag(spec, "directed"):
            ax.annotate(
                "",
                xy=(x1, y1),
                xytext=(x0, y0),
                arrowprops={"arrowstyle": "-|>", "shrinkA": 9, "shrinkB": 9, **style},
            )
        else:
            ax.plot([x0, x1], [y0, y1], **style)

    palette_of = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(dict.fromkeys(groups))}
    largest = max(values)
    ax.scatter(
        position[:, 0],
        position[:, 1],
        s=[160.0 * value / largest + 90.0 for value in values],
        color=[palette_of[group] for group in groups],
        edgecolors="white",
        linewidths=1.2,
        zorder=2,
    )
    # Through the nudger, not straight below the node: an edge arriving at a
    # node comes in at whatever angle the layout gave it, and the Writer ->
    # Planner arrow ran through the middle of the word "Planner".
    for (x, y), name in zip(position, names, strict=True):
        place_point_label(ax, literal(name), (float(x), float(y)), fontsize=8, zorder=3)
    # Room for the labels, which hang below their node and would otherwise be
    # cut off at the bottom row of the layout.
    ax.set_xlim(-0.12, 1.12)
    ax.set_ylim(-0.16, 1.10)
    ax.set_axis_off()
    if any(group is not None for group in groups):
        from chart_style import place_legend
        from matplotlib.lines import Line2D

        handles = [
            Line2D(
                [], [], linestyle="none", marker="o", markersize=8, color=colour, label=str(name)
            )
            for name, colour in palette_of.items()
            if name is not None
        ]
        place_legend(
            ax,
            handles=handles,
            loc="upper center",
            bbox_to_anchor=(0.5, 0.0),
            ncols=min(len(handles), 5),
        )


#: The most nodes a tree can carry and still be read at the default width.
#: Measured the same way the rest of this file measures: past this the leaf
#: labels collide and the legibility gate refuses the figure anyway.
MAX_TREE_NODES = 60


def render_tree(ax, spec: dict) -> None:
    """A rooted tree from a structure you already have.

    For a search or derivation whose SHAPE is the finding — a Tree-of-Thoughts
    or MCTS rollout with nodes sized by visit count and the accepted path
    picked out, a proof tree, an error taxonomy with counts at the leaves.

    Choose over ``dendrogram``, which cannot take a tree at all: it computes
    its own linkage from an observation matrix, and its branch heights are
    merge distances rather than depth. Choose over ``network``, which is
    force-directed — a tree under a force layout comes out a blob, the root
    ends up wherever the solver put it, and depth stops reading, which is the
    one thing the figure is for. ``treemap`` keeps the hierarchy and discards
    the branching.

    Depth is the y axis, so the root is at the top and every child sits one
    row below its parent. Leaves are spread evenly across x and each parent is
    centred over its children, which is what keeps the subtrees from
    overlapping without a full tidy-layout pass.

    Keys: ``nodes`` — a list of ``{"id": "a", "parent": "root", "label": …,
    "value": …}``, the root being the one with no ``parent`` — plus
    ``highlight`` (ids to draw as the emphasised path), ``value_label`` (what
    ``value`` measures, for the legend), and ``cmap``.
    """
    raw = spec.get("nodes")
    if not isinstance(raw, list) or not raw:
        raise SpecError(
            '\'nodes\' must be a non-empty list of {"id": …, "parent": …} objects. '
            "The root is the one with no 'parent'."
        )
    if len(raw) > MAX_TREE_NODES:
        raise SpecError(
            f"{len(raw)} nodes is past what a tree can show (max {MAX_TREE_NODES}); "
            "the leaf labels collide before that. Show the subtree that carries "
            "the finding, or aggregate the tail."
        )
    nodes: dict[str, dict] = {}
    order: list[str] = []
    for i, node in enumerate(raw):
        if not isinstance(node, dict):
            raise SpecError(f"nodes[{i}] must be an object, got {type_name(node)}")
        node_id = node.get("id")
        if not isinstance(node_id, str) or not node_id.strip():
            raise SpecError(f"nodes[{i}].id must be a non-empty string, got {node_id!r}")
        if node_id in nodes:
            raise SpecError(
                f"nodes[{i}].id repeats {node_id!r}. Every node needs its own id — "
                "two nodes sharing one silently merges their subtrees."
            )
        nodes[node_id] = node
        order.append(node_id)

    roots = [n for n in order if not str(nodes[n].get("parent") or "").strip()]
    if len(roots) != 1:
        raise SpecError(
            f"a tree has exactly one root, found {len(roots)} ({sorted(roots)[:4]}). "
            "The root is the node with no 'parent'."
        )
    root = roots[0]
    children: dict[str, list[str]] = {n: [] for n in order}
    for node_id in order:
        parent = str(nodes[node_id].get("parent") or "").strip()
        if not parent:
            continue
        if parent not in nodes:
            raise SpecError(
                f"node {node_id!r} names parent {parent!r}, which is not in 'nodes'. "
                "A dangling parent leaves the node unreachable from the root."
            )
        children[parent].append(node_id)

    # Reachability doubles as the cycle check: anything a walk from the root
    # never touches is either detached or part of a cycle, and both are the
    # same problem for the reader — a node that is drawn nowhere.
    depth: dict[str, int] = {}
    stack = [(root, 0)]
    while stack:
        node_id, d = stack.pop()
        depth[node_id] = d
        stack.extend((child, d + 1) for child in reversed(children[node_id]))
    missed = [n for n in order if n not in depth]
    if missed:
        raise SpecError(
            f"{len(missed)} node(s) are not reachable from the root ({missed[:4]}) — "
            "a detached branch or a cycle. Every node must hang off the root."
        )

    # x by leaf order, parents centred over their children.
    x: dict[str, float] = {}
    counter = [0.0]

    def place(node_id: str) -> float:
        kids = children[node_id]
        if not kids:
            x[node_id] = counter[0]
            counter[0] += 1.0
            return x[node_id]
        spans = [place(child) for child in kids]
        x[node_id] = (min(spans) + max(spans)) / 2.0
        return x[node_id]

    place(root)

    highlight = {str(h) for h in (spec.get("highlight") or [])}
    unknown = sorted(highlight - set(nodes))
    if unknown:
        raise SpecError(f"'highlight' names {unknown}, which are not in 'nodes'")

    # Marker areas resolved up front, so the drawing loop reads one list and
    # nothing is conditionally bound. ``value`` is optional per node; a tree
    # with none is drawn at a uniform size.
    given = [node.get("value") for node in raw]
    if any(v is not None for v in given):
        sized = numbers([v if v is not None else 0 for v in given], "'nodes[].value'")
        top = float(sized.max()) or 1.0
        areas = [40.0 + 260.0 * (float(v) / top) for v in sized]
    else:
        areas = [90.0] * len(raw)
    ink = PALETTE[0]
    accent = PALETTE[1]

    for node_id in order:
        parent = str(nodes[node_id].get("parent") or "").strip()
        if not parent:
            continue
        on_path = node_id in highlight and parent in highlight
        ax.plot(
            [x[parent], x[node_id]],
            [-depth[parent], -depth[node_id]],
            color=accent if on_path else "#b0b0b0",
            linewidth=2.2 if on_path else 1.0,
            zorder=2 if on_path else 1,
            solid_capstyle="round",
        )
    for i, node_id in enumerate(order):
        ax.scatter(
            [x[node_id]],
            [-depth[node_id]],
            s=areas[i],
            color=accent if node_id in highlight else ink,
            zorder=3,
            edgecolors="white",
            linewidths=0.8,
        )
        text = nodes[node_id].get("label")
        if text:
            place_point_label(ax, literal(text), (x[node_id], -depth[node_id]), fontsize=7.5)

    ax.set_xticks([])
    # Positions and labels have to correspond. Sorting them independently put
    # "4" on the root and "0" on the leaves — the axis said the opposite of
    # the tree, which the picture makes obvious and the code does not.
    rows = sorted({-d for d in depth.values()})
    ax.set_yticks(rows, labels=[str(-y) for y in rows])
    ax.set_ylabel(literal(spec.get("ylabel") or "Depth"))
    ax.grid(visible=False)
    for side in ("top", "right", "bottom"):
        ax.spines[side].set_visible(False)


CLUSTER_RENDERERS = {
    "tree": render_tree,
    "dendrogram": render_dendrogram,
    "clustermap": render_clustermap,
    "network": render_network,
}
