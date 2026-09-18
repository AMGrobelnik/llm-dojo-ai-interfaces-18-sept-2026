#!/usr/bin/env python3
"""Rank agentic LLMs on list price, cost per task and raw capability.

Reads the four YAML files in ``data/`` and recomputes the whole ranking:

* **list price** — blended ``(input + w*output)/(1+w)`` $/M at the assumed
  output weight in ``price_blend:``, relative to the
  reference model. A ``:free`` listing is not a price: it is rate-limited
  and temporary, so a free listing is priced by the same model's paid
  listing and a model that has no paid listing anywhere leaves the paid
  ranking entirely. Nothing is ever scored at a price of zero;
* **cost per task** — relative, solved from same-source pairwise ratios
  only. Every ratio relates two models measured on the same tasks in the
  same run; the chaining across runs happens here, in log space, by a
  least-squares fit anchored at the reference. A model no ratio reaches
  is price-only and is flagged;
* **effective cost** — the geometric mean of those two, the chart's x;
* **raw capability** — per task group, an agentic composite blended with that
  group's domain benchmarks at the group's own weight. Every board is
  put on 0-100 by its own median and inter-quartile range over every
  plotted variant;
* **gaps stay gaps** — the evidence is never complete, and nothing
  here fills it in. A variant is scored on the boards it was itself
  measured on and on no others: no score is copied or scaled across
  reasoning efforts or across models, and a model no same-source ratio
  reaches has no cost per task at all rather than a guessed one;
* **an additive fit over the measured cells** — per group,
  ``score(variant, board) = board_offset + variant_ability`` is solved
  by weighted least squares over exactly the cells that exist, so any
  two variants are compared through the boards they share, whichever
  those turn out to be. The ability is the group's raw capability and
  the fit's standard error is the band printed beside it; a variant
  measured on fewer than ``MIN_MEASURED_BOARDS`` of a group's boards is
  left out of that group rather than given a number for it;
* **capability per cost** — raw capability calibrated by list price and
  cost per task: the mean of three equal thirds, each min-max scaled
  over the plotted variants.

Writes ``results/ranking.md``, ``results/frontiers.html`` and
``results/evidence.md`` and prints the markdown to stdout. Every weight
lives in ``data/task_groups.yaml``; every number on the page and in the
evidence report is recomputed from the YAML, none is written by hand.
"""

import argparse
import html
import itertools
import math
import textwrap
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from statistics import fmean, stdev
from typing import Any, NamedTuple

import numpy as np
import yaml
from loguru import logger

GREEN, CYAN, END = "\033[92m", "\033[96m", "\033[0m"
LOG_FORMAT = f"{GREEN}{{time:HH:mm:ss}}{END}|{{level:<7}}|{CYAN}{{function}}{END}| {{message}}"
SKILL_DIR = Path(__file__).resolve().parent.parent
#: How this skill spells its own files in prose: paths in a generated doc
#: are checked from the repo root, and `results/` is not that root.
SKILL_REL = ".claude/skills/amg-llm-bench"
MAX_TABLE_WIDTH = 69

#: How many excluded rows a group's requirement table names before it
#: stops. The count in the sentence above it is the whole truth
#: either way, and a table of 60 near-identical rows is not a finding.
REQUIREMENT_ROWS = 12
OVERALL = "overall"
FREE_SUFFIX = ":free"
#: Names are plotted, not read aloud; these keep a label under ~14 chars
#: so twenty-odd of them fit one chart without colliding.
SHORT_NAME = {
    "DeepSeek": "DS",
    "Claude ": "",
    "MiniMax ": "MiniMax-",
}
#: Short codes for the group columns of the per-model drilldown table in
#: results/evidence.md, where a full group name would push the row past
#: the 70-character limit. The page itself always spells the group out.
GROUP_CODE = {
    "coding-experiments": "code",
    "scientific-writing": "write",
    "research-reasoning": "resrch",
    "review-judging": "judge",
    OVERALL: "all",
}
#: Said once, in one wording, and reused by the page, ranking.md and
#: evidence.md as (term, meaning) pairs. Spelling a column out three
#: different ways is how a reader ends up believing there are three
#: different columns.
COLUMN_TERMS: list[tuple[str, str]] = [
    (
        "capability per cost",
        "how good the model is, set against what it costs: the mean "
        "of three equal thirds, each min-max scaled over the plotted "
        "variants.",
    ),
    (
        "raw capability (0-100)",
        "how well the model suits this group's work, from the group's own benchmark weights.",
    ),
    (
        "preference",
        "the same fit run over this group's Arena boards alone — blind "
        "human votes; `-` where the row carries no Arena board here at "
        "all. The raw capability is the mean of the pillar columns.",
    ),
    (
        "capability",
        "the same fit over the group's Artificial Analysis boards "
        "alone. A wide gap between the two pillar columns is a finding "
        "about the model, not an error.",
    ),
    (
        "effective cost (x reference)",
        "the geometric mean of relative list price and relative cost per "
        "task, as a multiple of the reference model.",
    ),
    (
        "evidence coverage",
        "the share of the group's benchmark weight this variant was "
        "measured on, at its own reasoning effort. Nothing else is "
        "behind the row: an unmeasured board is left out, not filled in.",
    ),
    (
        "measured boards",
        "how many of the group's boards this variant has a measured row "
        "on, out of how many the group weighs.",
    ),
    (
        "ability band",
        "the standard error of this row's ability in the least-squares "
        "fit: how far the raw capability could move on the evidence "
        "behind it. It narrows with boards measured, never with boards "
        "borrowed.",
    ),
]
#: Every status a row can carry, in the words the tables print.
STATUS_TERMS: list[tuple[str, str]] = [
    ("on frontier", "nothing is both cheaper and a better fit."),
    ("off frontier", "something else is cheaper and fits better at once."),
    (
        "too thin for the frontier",
        "this row was not itself measured on enough of the group to be "
        "allowed on the frontier, and the status says which bar it fell "
        "under: the boards of its own it was run on, the share of the "
        "group's weight behind it, or both. Nothing is inherited — an "
        "effort placed against a better-measured sibling is judged on "
        "what was run at its own effort. It is still scored, ranked, "
        "plotted and listed among the least-measured models; a row "
        "nobody has really measured simply cannot set the line the rest "
        "of the page is read against.",
    ),
    (
        "price-only, no cost-per-task data",
        "no same-source ratio reaches this model, so it has no cost per "
        "task at all. Nothing is invented for it: its capability per "
        "cost is the list-price and raw-capability thirds alone, and its "
        "effective cost on the chart is its list price.",
    ),
    (
        "no cost-per-task data at this reasoning effort",
        "the model is priced per task but nobody published a cost "
        "multiplier for this effort, and the default effort's cost is "
        "not this effort's cost. The row is treated as having none.",
    ),
    (
        "pillar missing",
        "nobody measured this row on any board of that pillar, so the "
        "column is blank and the raw capability is the pillar that "
        "remains — which means a different thing from a mean over "
        "both, and says so. A row missing a pillar is not ranked at "
        "all unless another effort of the same model carries it.",
    ),
    (
        "effort cost measured",
        "a published run priced this model at this reasoning effort "
        "against another effort of itself, so the cost on this row is "
        "the effort's own cost.",
    ),
    (
        "placed relative to",
        "this row is an effort variant of a model whose best-measured "
        "variant sits on more boards, so each of its pillars is that "
        "variant's pillar plus the weighted mean gap between the two on "
        "the boards of that pillar both were measured on. A pillar they "
        "share no board in keeps the anchor's value: a lead on Arena is "
        "a statement about preference and about nothing else. A global "
        "fit has no model-by-board term, so a family-wide weakness on "
        "the boards only one variant was run on would otherwise be "
        "charged to that variant alone.",
    ),
    (
        "no board shared with",
        "this effort variant and its family's best-measured variant "
        "were never run on the same board, so there is no distance "
        "between the two to read. It keeps whatever the group's own fit "
        "gave it, and gets no number at all if the fit never reached "
        "it.",
    ),
    (
        "free listing exists",
        "the same model also has a free listing on the same id, with "
        "a :free suffix. That lane is "
        "throttled and temporary, so the ranking still prices the model "
        "at its paid list price.",
    ),
]


@dataclass(slots=True)
class Model:
    """One catalogue entry, plus everything the ranker derives for it."""

    id: str
    name: str
    scores: dict[str, float]
    #: benchmark key -> the `sources:` key the score was read from, so
    #: every raw number on the evidence page can be clicked back to a page.
    srcs: dict[str, str] = field(default_factory=dict)
    #: Boards a source publishes per MODEL rather than per reasoning
    #: effort — a board file marks them `per_effort: false`. They are
    #: merged into every effort variant of the model, because the number
    #: really does describe all of them, and they are excluded from the
    #: two places where that would be a lie: the count of boards a
    #: variant was measured on *at its own effort*, and the shared-board
    #: reading that places one effort against another.
    shared: dict[str, float] = field(default_factory=dict)
    #: The reasoning effort this row was run at. Empty where no source
    #: names one, and the row then reads `(default)`.
    effort: str = ""
    #: The effort the model's untagged rows were captured at, empty when
    #: unknown. A variant at any other effort inherits those rows.
    base_effort: str = ""
    #: The catalogue name, without the `(effort)` the variant carries.
    base_name: str = ""
    #: Cost-per-task multiplier for this effort, 1.0 at `base_effort`.
    #: Effort is a cost dial only: it never touches the list price.
    #: `None` where nobody published a multiplier for this effort: the
    #: variant then has no cost per task at all, because the default
    #: effort's cost is not this effort's cost.
    effort_cost: float | None = 1.0
    #: True where this model has more than one effort variant, so the
    #: effort-cost question arises at all.
    effort_split: bool = False
    #: effort -> board -> {value, src}, straight out of models.yaml.
    #: Consumed by `expand_efforts` and empty on every variant it makes.
    ladder: dict[str, dict[str, Any]] = field(default_factory=dict)
    #: Why this row has no cost per task, where it has none: `model`
    #: when no same-source ratio reaches the model at all, `effort` when
    #: the model is priced but nobody priced this reasoning effort.
    #: Empty where the cost per task is solved from measured ratios.
    cost_gap: str = ""
    rung: str | None = None
    agentic: bool = True
    free: bool = False
    free_only: bool = False
    free_twin: bool = False
    paid_listing: str | None = None
    free_rationale: str = ""
    rejected: str | None = None
    rejected_short: str = ""
    #: `evidence: none` in models.yaml AND no score to contradict it —
    #: priced by the catalogue but on no board this skill carries. Out of
    #: every ranking table, every chart and every scale; listed once in
    #: the no-evidence appendix.
    no_evidence: bool = False
    #: `alias_of:` in models.yaml — a moving id that currently resolves
    #: to a pinned dated snapshot in the same file. Its scores are folded
    #: into that snapshot and the alias itself leaves every table.
    alias_of: str = ""
    created: str = ""
    price_in: float = 0.0
    price_out: float = 0.0
    price_src: str = ""
    discount: dict[str, Any] | None = None
    blended: float = 0.0
    rel_price: float = 0.0
    #: group -> the same two numbers at that group's own measured
    #: output:input blend. A group weighs output differently because its
    #: steps do, and a cost axis that ignores that is pricing a workload
    #: nobody runs. Empty for a row with no price of its own.
    blended_by: dict[str, float] = field(default_factory=dict)
    rel_price_by: dict[str, float] = field(default_factory=dict)
    rel_cost: float | None = None
    price_only: bool = False
    #: group -> raw capability: the ability the group's additive fit
    #: solved for this variant, over the cells it was measured on and no
    #: others. What every table prints.
    fit: dict[str, float] = field(default_factory=dict)
    #: group -> the standard error of that ability in the same fit. It
    #: is the band the row's own evidence supports, not a spread over
    #: numbers somebody else was measured on.
    band: dict[str, float] = field(default_factory=dict)
    #: group -> the share of the group's benchmark weight this variant
    #: was measured on. Every board behind it is the variant's own.
    cover: dict[str, float] = field(default_factory=dict)
    #: group -> whether enough of the group's weight was measured on
    #: this row for it to be allowed to define that group's frontier. A
    #: row below the line is still scored, ranked and plotted; it just
    #: cannot anchor the line a reader traces on three boards.
    frontier_ok: dict[str, bool] = field(default_factory=dict)
    #: group -> the key of the effort sibling this row's ability was
    #: placed against, where it was placed against one at all. The
    #: number then rests on that row's boards as much as on its own.
    anchored: dict[str, str] = field(default_factory=dict)
    #: group -> which frontier bar a barred row fell under, in words.
    #: Printed in place of "on frontier", because "too thin" without the
    #: number it was thin on is a verdict with no evidence.
    frontier_bar: dict[str, str] = field(default_factory=dict)
    #: group -> how many of that group's boards this variant measured,
    #: and how many boards the group weighs in all.
    boards: dict[str, int] = field(default_factory=dict)
    board_pool: dict[str, int] = field(default_factory=dict)
    calibrated_intelligence: dict[str, float] = field(default_factory=dict)
    #: group -> evidence family -> that family's own composite, on the
    #: same 0-100 scale as `fit`. Printed beside the blended raw capability so
    #: a disagreement between human preference and static boards is
    #: visible instead of averaged away.
    pillar_fit: dict[str, dict[str, float]] = field(default_factory=dict)
    #: group -> the families the model has too little of that family's
    #: weight to be scored on at all. Printed as a status word, because
    #: a missing family changes what the raw capability means.
    pillars_missing: dict[str, list[str]] = field(default_factory=dict)
    #: group -> how this row was placed against its effort siblings,
    #: where it was placed against one at all. Printed in the status.
    placement: dict[str, str] = field(default_factory=dict)
    #: The hard capability record, straight out of models.yaml. `None`
    #: on a field the capability catalogue does not publish for this id:
    #: unknown is not a failure, so a `None` never excludes the row.
    context_window: int | None = None
    max_output_tokens: int | None = None
    tool_calling: bool | None = None
    #: `id_truncated:` in models.yaml — the catalogue's id for this row
    #: is a shortened label, not the id a backend would dial, so the row
    #: ranks but is never cut into a preset.
    id_truncated: bool = False
    #: group -> the requirement fields this row is known to fall under,
    #: in words. A non-empty list keeps the row in the group's table with
    #: a flag and takes it out of that group's frontier and cuts.
    requirement_gaps: dict[str, list[str]] = field(default_factory=dict)
    #: group -> benchmark key -> the 0-100 robust-scaled value used.
    #: Kept per group because a group weighs its own boards, so one raw
    #: score appears under every group that asked for that board.
    normed: dict[str, dict[str, float]] = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Pool identity: one row per (model, effort), not per model.

        Reasoning effort is a point on the frontier, not a footnote, so
        every scale, guard and frontier test keys on this and not on
        ``id``. ``id`` stays the catalogue identity, which is what the
        price list and the cost-ratio graph are keyed by.
        """
        return f"{self.id}@{self.effort}" if self.effort else self.id

    @property
    def eff_cost(self) -> float:
        """Geometric mean of relative price and relative cost per task.

        A row with no measured cost per task has no geometric mean to
        take, so its effective cost is its list price alone and says so
        in its status. That is a coarser reading of the same axis, not a
        cost per task invented for it.

        This is the pool-wide reading, on the pool-wide blend. Anything
        scored inside a task group asks `eff_cost_in` instead.
        """
        if self.rel_cost is None:
            return self.rel_price
        return math.sqrt(self.rel_price * self.rel_cost)

    def eff_cost_in(self, group: str) -> float:
        """The same axis, priced on one group's measured blend."""
        rel = self.rel_price_by.get(group, self.rel_price)
        if self.rel_cost is None:
            return rel
        return math.sqrt(rel * self.rel_cost)

    @property
    def short(self) -> str:
        """Chart label: shortened name plus the effort it was run at."""
        text = (self.base_name or self.name).split(" (")[0].strip()
        for long, small in SHORT_NAME.items():
            text = text.replace(long, small)
        return f"{text.strip()} ({self.effort or 'default'})"

    def status(self, group: str, *, on_frontier: bool = False) -> list[str]:
        """Plain-words status for one group row — no symbols to decode.

        The page used to carry ``*``, ``a`` and ``~`` and a legend to
        look them up in. A reader who has to hold a symbol table in their
        head to read a table is being charged for the author's brevity,
        so every marker is spelled out instead, in the order that matters
        to a decision: where the row sits, then what is thin about it.
        """
        gaps = self.requirement_gaps.get(group) or []
        if gaps:
            words = ["below the group's " + and_list(gaps) + " requirement"]
        elif not self.frontier_ok.get(group, True):
            words = [self.frontier_bar.get(group) or "too thin for the frontier"]
        else:
            words = ["on frontier" if on_frontier else "off frontier"]
        measured = self.boards.get(group)
        if measured is not None:
            words.append(f"{measured} of {self.board_pool.get(group, 0)} boards measured")
        words += [f"{pillar} pillar missing" for pillar in self.pillars_missing.get(group, [])]
        placed = self.placement.get(group, "")
        if placed:
            words.append(placed)
        if self.cost_gap == "effort":
            words.append("no cost-per-task data at this reasoning effort")
        elif self.price_only:
            words.append("price-only, no cost-per-task data")
        if self.effort_split and not self.price_only:
            words.append("effort cost measured")
        if self.free_twin:
            words.append("free listing exists")
        return words


def load_yaml(path: Path) -> dict[str, Any]:
    """Parse one YAML file, failing loudly with the path that broke."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cannot read {path}: {exc}") from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise SystemExit(f"malformed YAML in {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise SystemExit(f"{path} must hold a mapping at the top level")
    return loaded


#: The pillars every task group stands on, in the order the page prints
#: them. They are the answer to "who says so": people choosing between
#: two answers, and a fixed task set with a scoring key. Neither can be
#: trusted alone and neither is the other's measurement, so each carries
#: half of every group and a variant is scored on the pillars it has.
PILLARS: tuple[str, ...] = ("preference", "capability")

#: The directory under `data/` holding one YAML per captured source.
BOARDS_DIR = "boards"

#: A board file may say a board is published per MODEL rather than per
#: reasoning effort, with `per_effort: false` — a count of what a whole
#: model did is not a measurement of any one of its efforts. The default
#: is per-effort, which is what every leaderboard row is unless the file
#: says otherwise, and a file that needs its column read in log space
#: says that too, with `transform: log10`.
DEFAULT_PER_EFFORT = True


@dataclass(slots=True)
class Board:
    """One captured leaderboard column, as a board file declares it."""

    key: str
    title: str
    unit: str
    higher_is_better: bool
    #: True where the source publishes one number per model rather than
    #: one per reasoning effort.
    per_effort: bool
    #: `log10` where the raw unit is read in log space, else empty.
    transform: str
    #: The synthetic `sources:` key this board's cells cite, so every
    #: number traces back to the file, page and capture date it came from.
    source_key: str


def board_source(block: dict[str, Any], board: dict[str, Any], key: str) -> dict[str, Any]:
    """The `sources:` entry one board's cells cite, from its file's header.

    The capture is the evidence, so the entry carries the whole header —
    title, url, date, how it was captured — plus the one thing that is a
    property of the board rather than the file: whether Arena's style
    control was on for it.

    A board that carries the key as ``null`` has no such toggle — it is
    not an Arena category table — and that is not the same statement as
    the toggle being off. The ``null`` is kept as a ``None``, and the
    reader of this entry drops it rather than reading it as a setting.
    """
    entry = {
        "title": f"{block.get('title') or 'board capture'} - {board.get('title') or key}",
        "url": str(block.get("url") or ""),
        "date": str(block.get("captured") or ""),
        "method": str(block.get("method") or ""),
    }
    if "style_control" in board:
        setting = board["style_control"]
        entry["style_control"] = None if setting is None else bool(setting)
    return entry


def load_boards(data_dir: Path) -> tuple[dict[str, Board], dict[str, dict[str, float]], dict]:
    """Read every `data/boards/*.yaml` into boards, cells and sources.

    One file per captured source, each one reproducible by rerunning its
    capture script, which is why a board file wins over the same cell in
    `models.yaml`: the hand-maintained catalogue is where a number goes
    when nobody has automated pulling it, not a second opinion on a
    number somebody has.

    A cell key is a `models.yaml` id, optionally suffixed `@effort`. The
    values are raw — Elo, dollars, fractions — and the only thing done to
    them here is the log of a unit that has to be read in logs.
    """
    folder = data_dir / BOARDS_DIR
    if not folder.is_dir():
        logger.warning(f"no {BOARDS_DIR}/ directory under {data_dir}; no captured board is loaded")
        return {}, {}, {}
    boards: dict[str, Board] = {}
    cells: dict[str, dict[str, float]] = {}
    sources: dict[str, Any] = {}
    for path in sorted(folder.glob("*.yaml")):
        raw = load_yaml(path)
        block = dict(raw.get("source") or {})
        stem = path.stem
        for key, spec in sorted((raw.get("boards") or {}).items()):
            spec = dict(spec or {})
            if key in boards:
                raise SystemExit(
                    f"board `{key}` is declared in two board files under "
                    f"{SKILL_REL}/data/{BOARDS_DIR}/; one board, one capture"
                )
            source_key = f"board:{stem}:{key}"
            sources[source_key] = board_source(block, spec, key)
            unit = str(spec.get("unit", ""))
            boards[key] = Board(
                key=key,
                title=str(spec.get("title") or key),
                unit=unit,
                higher_is_better=bool(spec.get("higher_is_better", True)),
                per_effort=bool(spec.get("per_effort", DEFAULT_PER_EFFORT)),
                transform=str(spec.get("transform", "")),
                source_key=source_key,
            )
            column: dict[str, float] = {}
            for cell, value in (spec.get("values") or {}).items():
                number = float(value)
                if boards[key].transform == "log10":
                    if number <= 0.0:
                        logger.warning(f"{key}: {cell} is {number:g}, which has no log; dropped")
                        continue
                    number = math.log10(number)
                if not boards[key].higher_is_better:
                    # Every fit in this file reads a bigger number as
                    # better, so a board where small is good is negated
                    # once here rather than special-cased everywhere.
                    number = -number
                column[str(cell)] = number
            cells[key] = column
        logger.info(
            f"{path.name}: {len(raw.get('boards') or {})} boards, captured {block.get('captured', 'undated')}"
        )
    return boards, cells, sources


def declared_efforts(raw: dict[str, Any], ratios: dict[str, Any]) -> dict[str, set[str]]:
    """Model id -> every reasoning effort the catalogue declares for it.

    The same union the variant expansion is built on: the model's own
    `default_effort:`, every effort with a row under `scores_by_effort:`,
    every effort a published cost multiplier touches, and an `efforts:`
    list for a level a provider sells that nothing here has scored yet.
    An `alias_of:` pair shares one set, because the alias's boards are
    folded into the snapshot it points at and an effort either model
    declares is an effort of that one purchasable endpoint.
    """
    entries = {str(entry["id"]): entry for entry in raw.get("models") or []}
    out: dict[str, set[str]] = {}
    for model_id, entry in entries.items():
        out[model_id] = (
            {str(entry.get("default_effort", ""))}
            | {str(key) for key in entry.get("scores_by_effort") or {}}
            | {str(key) for key in entry.get("efforts") or []}
        )
    for row in ratios.get("effort_ratios") or []:
        model_id = str(row.get("model", ""))
        if model_id in out:
            out[model_id] |= {str(row.get("effort_a", "")), str(row.get("effort_b", ""))}
    for model_id, entry in entries.items():
        target = str(entry.get("alias_of", ""))
        if target in out:
            shared = out[model_id] | out[target]
            out[model_id] = shared
            out[target] = shared
    return out


def apply_boards(
    raw: dict[str, Any],
    boards: dict[str, Board],
    cells: dict[str, dict[str, float]],
    efforts: Mapping[str, set[str]] | None = None,
) -> list[str]:
    """Write every board-file cell into the catalogue it was keyed against.

    A board file is the fresher, reproducible capture, so wherever it
    carries a board for a model it *replaces* whatever `models.yaml` held
    for that pair — untagged row and effort rows alike — rather than
    landing beside a stale number and letting the two average. Boards no
    file carries are left exactly as the catalogue has them.

    A board marked `per_effort: false` is one number for the whole model.
    It goes to a separate shelf, `model_scores`, because merging it into
    the untagged row would hand it to the default-effort variant alone
    and merging it into every effort row would let it masquerade as a
    measurement of an effort nobody ran.

    A cell is attached only where the catalogue knows what it names. An
    id `models.yaml` does not carry, and an `@effort` that model does not
    declare, are both dropped and returned for the report: a source
    naming a level the catalogue has never heard of would otherwise
    conjure a whole ranked row out of one board, priced and placed with
    nothing else behind it. The fix is to declare the effort, not to let
    the capture declare it.
    """
    by_id = {str(entry["id"]): entry for entry in raw.get("models") or []}
    known = dict(efforts or {})
    missing: set[str] = set()
    undeclared: set[str] = set()
    for key, column in sorted(cells.items()):
        board = boards[key]
        touched = {cell.split("@", 1)[0] for cell in column}
        for model_id in sorted(touched & set(by_id)):
            entry = by_id[model_id]
            (entry.get("scores") or {}).pop(key, None)
            for rows in (entry.get("scores_by_effort") or {}).values():
                (rows or {}).pop(key, None)
        for cell, value in sorted(column.items()):
            model_id, _, effort = cell.partition("@")
            entry = by_id.get(model_id)
            if entry is None:
                missing.add(cell)
                continue
            if effort and effort not in known.get(model_id, {effort}):
                undeclared.add(cell)
                continue
            written = {"value": value, "src": board.source_key}
            if not board.per_effort:
                entry.setdefault("model_scores", {})[key] = written
            elif effort:
                entry.setdefault("scores_by_effort", {}).setdefault(effort, {})[key] = written
            else:
                entry.setdefault("scores", {})[key] = written
    if missing:
        logger.warning(
            f"{len(missing)} board cells name an id that is not in models.yaml, so "
            "there is nothing to attach them to and they are dropped: " + ", ".join(sorted(missing))
        )
    if undeclared:
        logger.warning(
            f"{len(undeclared)} board cells name a reasoning effort models.yaml does "
            "not declare for that model, so they would each invent a ranked row on "
            "one board; declare the effort in the catalogue or leave them out: "
            + ", ".join(sorted(undeclared))
        )
    return sorted(missing | undeclared)


#: Fallback output weight when `price_blend:` is absent from the YAML.
#: It is an assumption either way — see `price_blend` in
#: data/task_groups.yaml for what would replace it with a measurement.
DEFAULT_OUTPUT_WEIGHT = 3.0


def price_blend(groups: dict[str, Any]) -> tuple[float, str]:
    """The pool-wide output:input price weight, and where it came from.

    This is the fallback: the weight used where there is no task group
    to measure one for, which is the overall pool and nothing else. It
    is an assumption and says so.
    """
    block = groups.get("price_blend") or {}
    return (
        float(block.get("output_weight", DEFAULT_OUTPUT_WEIGHT)),
        str(block.get("basis", "assumed")),
    )


def group_blends(groups: dict[str, Any]) -> dict[str, tuple[float, str]]:
    """group -> (output weight, basis), measured per group where it is.

    A group is a set of pipeline steps and those steps have measured
    token medians, so the output:input ratio the cost axis blends on is
    that group's own ratio and not one number for the whole page. A
    group with no measurement falls back to the pool-wide assumption,
    labelled as one, because a blend printed without its basis is a
    number a reader cannot weigh.
    """
    block = groups.get("price_blend") or {}
    fallback, fallback_basis = price_blend(groups)
    measured = block.get("by_group") or {}
    basis = str(block.get("by_group_basis", "measured"))
    out: dict[str, tuple[float, str]] = {}
    for name in groups["groups"]:
        if name in measured:
            out[name] = (float(measured[name]), basis)
        else:
            out[name] = (fallback, fallback_basis)
    out[OVERALL] = (fallback, fallback_basis)
    return out


def blended_price(price: dict[str, Any], output_weight: float = DEFAULT_OUTPUT_WEIGHT) -> float:
    """Blend a listing into one $/M number at the given output weight."""
    inputs = float(price.get("input", 0.0))
    return (inputs + output_weight * float(price.get("output", 0.0))) / (1.0 + output_weight)


def source_citations(raw: dict[str, Any]) -> set[str]:
    """Every `sources:` key the catalogue actually cites, from anywhere.

    A score, a ladder row, a list price, a capability record and a
    rejection can each name a source, so all five are read. An entry
    nothing cites is dead weight that reads like evidence — the page
    counts sources — and a `src:` naming nothing is a broken link.
    """
    cited: set[str] = set()
    for entry in raw.get("models") or []:
        for cell in (entry.get("scores") or {}).values():
            cited.add(str(cell.get("src", "")))
        for cell in (entry.get("model_scores") or {}).values():
            cited.add(str(cell.get("src", "")))
        for rows in (entry.get("scores_by_effort") or {}).values():
            for cell in (rows or {}).values():
                cited.add(str(cell.get("src", "")))
        cited.add(str((entry.get("list_price") or {}).get("src", "")))
        cited.add(str(entry.get("capabilities_src", "")))
        cited.update(str(key) for key in (entry.get("rejected_src") or []))
    cited.discard("")
    return cited


def check_sources(raw: dict[str, Any]) -> None:
    """Stop on a `src:` that names nothing; warn on a source nothing cites."""
    declared = set(raw.get("sources") or {})
    cited = source_citations(raw)
    dangling = sorted(cited - declared)
    if dangling:
        raise SystemExit(
            "these `src:` keys name no entry under `sources:` in "
            f"{SKILL_REL}/data/models.yaml, so the number behind them cannot be "
            f"traced to a page: {', '.join(dangling)}"
        )
    unused = sorted(declared - cited)
    if unused:
        logger.warning(
            f"{len(unused)} sources are declared and cited by nothing. A source "
            "list that is longer than the evidence reads like more evidence than "
            f"there is: delete them from {SKILL_REL}/data/models.yaml or cite "
            f"them: {', '.join(unused)}"
        )


def merge_aliases(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold every ``alias_of:`` row's evidence into the row it points at.

    ``deepseek/deepseek-v4-pro`` is the string a run actually sends, and
    today it serves ``deepseek-v4-pro-0813``. Ranked apart they are two
    competing answers to one purchase, with the evidence split between
    them and both eligible for the same frontier corner. So the alias's
    boards are folded into the snapshot — the snapshot's own value wins
    wherever both carry a board, because it is the dated capture of the
    weights being sold — and the alias keeps its row for the routing note
    and leaves every table. The snapshot's price stands untouched: it is
    the listing the id resolves to.
    """
    by_id = {entry["id"]: entry for entry in entries}
    for entry in entries:
        target_id = str(entry.get("alias_of", ""))
        if not target_id:
            continue
        target = by_id.get(target_id)
        if target is None:
            raise SystemExit(f"{entry['id']} is alias_of {target_id}, which is not in models.yaml")
        gained = 0
        target_scores = target.setdefault("scores", {}) or {}
        target["scores"] = target_scores
        for key, value in (entry.get("scores") or {}).items():
            if key not in target_scores:
                target_scores[key] = value
                gained += 1
        target_model = target.setdefault("model_scores", {}) or {}
        target["model_scores"] = target_model
        for key, value in (entry.get("model_scores") or {}).items():
            target_model.setdefault(key, value)
        if not target_model:
            target.pop("model_scores", None)
        target_ladder = target.setdefault("scores_by_effort", {}) or {}
        target["scores_by_effort"] = target_ladder
        for effort, rows in (entry.get("scores_by_effort") or {}).items():
            merged = dict(rows)
            merged.update(target_ladder.get(effort) or {})
            target_ladder[effort] = merged
        if not target_ladder:
            target.pop("scores_by_effort", None)
        logger.info(
            f"{entry['id']} is an alias of {target_id}: {gained} board"
            f"{'s' if gained != 1 else ''} folded in, the alias leaves the ranking"
        )
    return entries


def build_models(
    raw: dict[str, Any],
    output_weight: float = DEFAULT_OUTPUT_WEIGHT,
    blends: Mapping[str, float] | None = None,
) -> tuple[list[Model], str]:
    """Turn models.yaml into Model objects and find the reference id.

    A ``:free`` listing is a rate-limited, temporary lane, never a price.
    Each one is resolved to the same model's base row — ``free_of:``
    where the slug does not simply strip to it — and that row is where
    both its price and its evidence come from. A free slug is the same
    weights behind a different endpoint, so ranking it on nothing while
    the identical paid row sits three lines up is a gap in the reading,
    not caution. What does not transfer is the endpoint: the free row
    keeps its own context window, response ceiling and tool-calling
    flag, because those are properties of the lane it routes through.

    A free slug with no base row at all is ``free_only``: it cannot be
    priced and it inherits no evidence, so it stays at no evidence. No
    zero ever reaches capability per cost — a paid row whose blended
    price is not positive is a data error, not a bargain.
    """
    entries = merge_aliases(list(raw.get("models", [])))
    per_group = dict(blends or {})
    paid_blend = {
        entry["id"]: blended_price(entry.get("list_price") or {}, output_weight)
        for entry in entries
        if not entry["id"].endswith(FREE_SUFFIX)
    }
    paid_blend_by = {
        name: {
            entry["id"]: blended_price(entry.get("list_price") or {}, weight)
            for entry in entries
            if not entry["id"].endswith(FREE_SUFFIX)
        }
        for name, weight in per_group.items()
    }
    by_id = {str(entry["id"]): entry for entry in entries}

    def base_of(entry: dict[str, Any]) -> str:
        """The paid row a free listing is a listing of, or ""."""
        named = str(entry.get("free_of", "")).strip()
        if named:
            return named
        return str(entry["id"]).removesuffix(FREE_SUFFIX)

    free_bases = {base_of(entry) for entry in entries if str(entry["id"]).endswith(FREE_SUFFIX)}
    models: list[Model] = []
    mislabelled: list[str] = []
    reference = ""
    for entry in entries:
        identifier = str(entry["id"])
        is_free_row = identifier.endswith(FREE_SUFFIX) or bool(entry.get("free", False))
        inherited = by_id.get(base_of(entry)) if is_free_row else None
        if inherited is entry:
            inherited = None
        raw_scores = entry.get("scores") or {}
        model_scores = entry.get("model_scores") or {}
        ladder_rows = entry.get("scores_by_effort") or {}
        default_effort = str(entry.get("default_effort", ""))
        if inherited is not None:
            # The base row's evidence is this model's evidence; the free
            # row's own cells stay where it has one the base lacks.
            raw_scores = {**(inherited.get("scores") or {}), **raw_scores}
            model_scores = {**(inherited.get("model_scores") or {}), **model_scores}
            ladder_rows = ladder_rows or (inherited.get("scores_by_effort") or {})
            default_effort = default_effort or str(inherited.get("default_effort", ""))
        # A model-level board describes the model, so the base row
        # carries it from the start and every effort variant expanded
        # off that row carries it too. It is kept in `shared` as well,
        # which is how the fit knows not to count it as a board measured
        # at one particular reasoning effort.
        scores = {key: float(val["value"]) for key, val in {**raw_scores, **model_scores}.items()}
        is_free = is_free_row
        price = entry.get("list_price") or {}
        model = Model(
            id=identifier,
            name=entry.get("name", identifier),
            scores=scores,
            srcs={
                key: str(val.get("src", "")) for key, val in {**raw_scores, **model_scores}.items()
            },
            shared={key: float(val["value"]) for key, val in model_scores.items()},
            effort=default_effort,
            base_effort=default_effort,
            base_name=entry.get("name", identifier),
            ladder={str(effort): dict(rows) for effort, rows in ladder_rows.items()},
            rung=entry.get("rung"),
            agentic=bool(entry.get("agentic", True)),
            free=is_free,
            free_twin=not is_free and identifier in free_bases,
            free_rationale=entry.get("free_rank_rationale", ""),
            rejected=entry.get("rejected"),
            rejected_short=entry.get("rejected_short", ""),
            no_evidence=str(entry.get("evidence", "")) == "none"
            and not scores
            and not model_scores,
            alias_of=str(entry.get("alias_of", "")),
            created=str(entry.get("created", "")),
            price_in=float(price.get("input", 0.0)),
            price_out=float(price.get("output", 0.0)),
            price_src=str(price.get("src", "")),
            discount=entry.get("discount_route"),
            context_window=none_or_int(entry.get("context_window")),
            max_output_tokens=none_or_int(entry.get("max_output_tokens")),
            tool_calling=none_or_bool(entry.get("tool_calling")),
            id_truncated=bool(entry.get("id_truncated", False)),
        )
        base = base_of(entry)
        if is_free:
            model.paid_listing = base if base in paid_blend and paid_blend[base] > 0.0 else None
            model.free_only = model.paid_listing is None
            model.blended = paid_blend.get(base, 0.0)
            model.blended_by = {name: table.get(base, 0.0) for name, table in paid_blend_by.items()}
        else:
            model.blended = blended_price(entry.get("list_price") or {}, output_weight)
            model.blended_by = {
                name: blended_price(price, weight) for name, weight in per_group.items()
            }
            if not model.rejected and model.blended <= 0.0:
                raise SystemExit(
                    f"{identifier} has no positive list price; a free listing is not a "
                    "price, so mark it `:free` or give it its paid list price"
                )
        if str(entry.get("evidence", "")) == "none" and entry.get("scores"):
            mislabelled.append(identifier)
        models.append(model)
        if entry.get("reference"):
            reference = model.id
    if mislabelled:
        logger.warning(
            f"{len(mislabelled)} rows are tagged `evidence: none` and carry scores "
            "anyway; the scores win and the rows are ranked. Clear the tag in "
            f"models.yaml: {', '.join(sorted(mislabelled))}"
        )
    if not reference:
        raise SystemExit("no model in models.yaml carries `reference: true`")
    return models, reference


def solve_relative_cost(
    ratios: list[dict[str, Any]],
    reference: str,
    *,
    iterations: int = 20000,
    tolerance: float = 1e-13,
) -> dict[str, float]:
    """Least-squares fit of log cost per task over the ratio graph.

    Each row is one same-source observation ``cost(a)/cost(b) = ratio``,
    i.e. ``x_a - x_b = log(ratio)`` in log space. Relaxing every node to
    the mean of what its neighbours imply converges on the least-squares
    solution of that over-determined system, with the reference pinned
    at zero. Nodes the reference cannot reach are left out entirely.
    """
    edges: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for row in ratios:
        ratio = float(row["ratio"])
        if ratio <= 0.0:
            logger.warning(f"skipping non-positive ratio in {row}")
            continue
        a, b, log_ratio = row["model_a"], row["model_b"], math.log(ratio)
        edges[a].append((b, log_ratio))
        edges[b].append((a, -log_ratio))

    reachable: set[str] = {reference}
    frontier = [reference]
    while frontier:
        node = frontier.pop()
        for neighbour, _ in edges[node]:
            if neighbour not in reachable:
                reachable.add(neighbour)
                frontier.append(neighbour)

    solution = dict.fromkeys(reachable, 0.0)
    for step in range(iterations):
        shift = 0.0
        updated = dict(solution)
        for node in reachable:
            if node == reference:
                continue
            implied = [
                solution[other] + delta for other, delta in edges[node] if other in reachable
            ]
            updated[node] = sum(implied) / len(implied)
            shift = max(shift, abs(updated[node] - solution[node]))
        solution = updated
        if shift < tolerance:
            logger.info(f"cost-ratio fit converged after {step + 1} passes")
            break
    else:
        logger.warning("cost-ratio fit hit the iteration cap")
    return {node: math.exp(value) for node, value in solution.items()}


def effort_multipliers(
    rows: list[dict[str, Any]], model_id: str, base_effort: str
) -> dict[str, float]:
    """Cost-per-task multiplier per effort for one model, base at 1.0.

    The effort ladder is the same least-squares fit as the cross-model
    one, run on one model's own graph with its untagged effort pinned:
    the published ratios are same-source pairs, so they compose the same
    way. An empty map means nothing anchors the ladder to the rows the
    scores came from, and every variant then costs what the base does.
    """
    edges = [
        {
            "model_a": str(row["effort_a"]),
            "model_b": str(row["effort_b"]),
            "ratio": row["ratio"],
        }
        for row in rows
        if str(row.get("model", "")) == model_id
    ]
    if not edges:
        return {}
    nodes = {edge["model_a"] for edge in edges} | {edge["model_b"] for edge in edges}
    if base_effort not in nodes:
        logger.warning(
            f"{model_id} has effort ratios but none touch its default effort "
            f"{base_effort or '(none)'}; its variants keep the base cost"
        )
        return {}
    return solve_relative_cost(edges, base_effort)


#: How far a ladder row taken at the model's own default effort may sit
#: from the untagged row for the same board before the two captures are
#: treated as disagreeing. Two per cent: rounding and a re-run of the
#: same harness land inside it, a differently-scaled capture does not.
LADDER_AGREEMENT = 0.02

#: Reasoning efforts in the order the providers sell them, cheapest
#: first. Used only to ask whether a dearer effort actually scored
#: higher; an effort no provider here publishes falls to the end.
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")

#: A dearer effort has to score this far below the one under it, in task
#: fit points, before it is called a step backwards. Under it the two are
#: the same reading twice.
MONOTONE_SLACK = 0.5


def check_ladder_agreement(model: Model) -> list[str]:
    """Warn where a ladder row contradicts the untagged row it belongs to.

    ``scores:`` is whatever a board published with no effort tag, and the
    rule for ingesting ``scores_by_effort:`` is that its row at the
    model's own ``default_effort`` restates that untagged number. When it
    does not, the two captures are of different things — a differently
    scaled harness, or a ladder pulled from a page that ran the model at
    another effort — and averaging them is how that gets buried. The rule
    was documented and never enforced; this is the enforcement, as a
    warning naming the board and both numbers.
    """
    rows = model.ladder.get(model.base_effort) or {}
    clashes: list[str] = []
    for key, row in rows.items():
        untagged = model.scores.get(key)
        if untagged is None:
            continue
        tagged = float(row["value"])
        scale = max(abs(untagged), abs(tagged))
        if scale > 0.0 and abs(tagged - untagged) / scale > LADDER_AGREEMENT:
            clashes.append(f"{key} {tagged:g} vs untagged {untagged:g}")
    if clashes:
        logger.warning(
            f"{model.id}: its {model.base_effort or '(default)'}-effort ladder row "
            "disagrees with the untagged row it is supposed to restate, so the two "
            "captures are not of the same thing. Re-capture or drop the ladder: "
            + "; ".join(clashes)
        )
    return clashes


@dataclass(slots=True)
class DataNotes:
    """What the data itself flagged during a run, kept for the report.

    These are findings about the catalogue rather than about any model's
    standing, and they belong in `results/findings.md` as much as in the
    log: a warning nobody reads is a warning that outlives its cause.
    """

    #: model id -> the boards whose ladder row contradicts the untagged row.
    ladder_clashes: dict[str, list[str]] = field(default_factory=dict)
    #: models split by effort that nobody published a cost multiplier for.
    effort_unpriced: list[str] = field(default_factory=list)
    #: captured cells naming an id or an effort the catalogue does not
    #: declare, which are dropped rather than turned into a ranked row.
    board_unmatched: list[str] = field(default_factory=list)


def collect_notes(models: list[Model], ratios: dict[str, Any]) -> DataNotes:
    """Run the data checks over the catalogue, before it is expanded."""
    effort_rows = list(ratios.get("effort_ratios") or [])
    notes = DataNotes()
    for model in models:
        if model.rejected or model.free or model.no_evidence or model.alias_of:
            continue
        clashes = check_ladder_agreement(model)
        if clashes:
            notes.ladder_clashes[model.id] = clashes
        multipliers = effort_multipliers(effort_rows, model.id, model.base_effort)
        efforts = set(model.ladder) | set(multipliers) | {model.base_effort}
        if len(efforts) > 1 and not multipliers:
            notes.effort_unpriced.append(model.base_name)
    notes.effort_unpriced.sort()
    if notes.effort_unpriced:
        logger.warning(
            f"{len(notes.effort_unpriced)} models are split by reasoning effort with "
            "no published cost ratio between their efforts, so no effort of them "
            "but the default has a cost per task at all and those rows are priced "
            f"on the list price alone: {', '.join(notes.effort_unpriced)}"
        )
    return notes


def expand_efforts(models: list[Model], ratios: dict[str, Any]) -> list[Model]:
    """One row per (model, effort), because effort is a frontier axis.

    Running a model at low effort is a different cost/ability trade-off
    from running it at max, not a footnote on one point, so each effort
    a source actually measured — a board row tagged with it, or a
    published cost multiplier for it — becomes its own candidate. A
    model no source splits keeps its single row, labelled with the
    effort it was run at where that is known and ``(default)`` where it
    is not.

    The untagged rows belong to the default-effort variant: that is the
    effort a source runs a model at unless it says otherwise. So the
    default variant is the untagged rows merged with its own effort rows
    (the tagged row wins, being the more specific measurement), and every
    other variant carries only what was measured at that effort — full
    stop. The gaps stay gaps: a board nobody ran at this effort is a
    board this variant is not scored on, because a value moved over from
    another effort is a number the model was never measured on, and it
    lands on a different row's price. A variant no board was run at is
    not created at all.
    """
    effort_rows = list(ratios.get("effort_ratios") or [])
    out: list[Model] = []
    dropped: list[str] = []
    for model in models:
        if model.rejected or model.free or model.no_evidence or model.alias_of:
            out.append(model)
            continue
        multipliers = effort_multipliers(effort_rows, model.id, model.base_effort)
        efforts = sorted(set(model.ladder) | set(multipliers) | {model.base_effort})
        for effort in efforts:
            rows = model.ladder.get(effort) or {}
            base = effort == model.base_effort
            scores = dict(model.scores) if base else {}
            srcs = dict(model.srcs) if base else {}
            for key, value in rows.items():
                scores[key] = float(value["value"])
                srcs[key] = str(value.get("src", ""))
            if not scores:
                dropped.append(f"{model.id} ({effort or 'default'})")
                continue
            # A model-level board describes every effort of the model, so
            # every variant carries it. It is still not a measurement OF
            # this effort, which is why it cannot create a variant above
            # and cannot place one below.
            scores.update(model.shared)
            out.append(
                replace(
                    model,
                    effort=effort,
                    name=f"{model.base_name} ({effort or 'default'})",
                    scores=scores,
                    srcs=srcs,
                    effort_cost=1.0 if base else multipliers.get(effort),
                    effort_split=len(efforts) > 1,
                    ladder={},
                    fit={},
                    band={},
                    cover={},
                    frontier_ok={},
                    boards={},
                    board_pool={},
                    calibrated_intelligence={},
                    pillar_fit={},
                    pillars_missing={},
                    placement={},
                    anchored={},
                    frontier_bar={},
                    requirement_gaps={},
                    normed={},
                )
            )
    if dropped:
        logger.info(
            f"{len(dropped)} effort variants exist only as a published cost "
            "multiplier, with no board run at that effort, so there is nothing to "
            f"score them on and they are dropped rather than filled in: "
            f"{', '.join(dropped)}"
        )
    logger.info(f"expanded {len(models)} catalogue rows into {len(out)} variants")
    return out


def apply_prices(models: list[Model], reference: str) -> None:
    """Every model's blended list price relative to the reference model.

    Once per blend: the pool-wide one, and each group's own. The
    reference is the same model throughout, so a group's axis is still
    read against the same listing — it is the mix of input and output
    that its steps measured that changes, not the yardstick.
    """
    ref = next(m for m in models if m.id == reference)
    for model in models:
        model.rel_price = model.blended / ref.blended
        model.rel_price_by = {
            name: model.blended_by[name] / value
            for name, value in ref.blended_by.items()
            if value > 0.0 and name in model.blended_by
        }


def apply_costs(models: list[Model], rel_costs: dict[str, float]) -> None:
    """Attach the solved cost per task, scaled by the variant's effort.

    Effort is a cost dial and nothing else here: the list price of a
    model does not change with how hard it thinks, so only the
    cost-per-task third — and through it the effective cost — moves.

    A model no same-source ratio reaches has **no** cost per task. It
    used to be given one — its list price times the median cost-to-price
    ratio of the models that have both — and that number then rode the
    chart, the frontier and the ranking key as though somebody had
    measured it. Two variants of one model could differ by a whole rung
    on it. A ratio nobody published is missing evidence, so the row is
    marked price-only, its capability per cost is the thirds it does
    have, and its effective cost is its list price.

    The same rule runs down the effort ladder: a variant whose effort
    nobody priced has no cost per task either, because the default
    effort's cost is not this effort's cost.
    """
    for model in models:
        base = rel_costs.get(model.id)
        if base is None:
            model.cost_gap = "model"
        elif model.effort_cost is None:
            model.cost_gap = "effort"
        else:
            model.cost_gap = ""
        model.rel_cost = None if model.cost_gap else base * float(model.effort_cost or 1.0)
        model.price_only = model.rel_cost is None


def base_variant(models: list[Model]) -> list[Model]:
    """One row per catalogue id: the variant at the model's own effort.

    Price and cost-per-task evidence is per model, not per effort, so
    the evidence tables list each model once instead of repeating one
    listing under every effort it can be run at.
    """
    seen: set[str] = set()
    out: list[Model] = []
    for model in models:
        if model.id in seen or model.effort != model.base_effort:
            continue
        seen.add(model.id)
        out.append(model)
    return out


#: A declared weight map may sit this far from 1.0 before the run stops.
#: Wide enough for a rounded third, narrow enough that a weight someone
#: forgot to take back out cannot hide in it.
WEIGHT_TOLERANCE = 0.001


def check_weight_sum(label: str, total: float) -> None:
    """Stop on a weight map that does not declare what it adds up to.

    These used to be renormalised in silence, which kept every score
    right and every *declared* share wrong: a group summing to 1.05 still
    ranks correctly and still misreports its own family split, and there
    is no way to tell which weight was meant to be lower. So it is an
    error, named, with the number.
    """
    if abs(total - 1.0) > WEIGHT_TOLERANCE:
        raise SystemExit(
            f"{label} weights sum to {total:.4f}, not 1. They are shares, so they "
            "have to add up: fix the weight that is wrong in "
            f"{SKILL_REL}/data/task_groups.yaml rather than leaving it to be "
            "renormalised, which would silently change the family split the page prints"
        )


#: The three weight-hygiene bounds, when `weight_guards:` in
#: `data/task_groups.yaml` names none. A file that declares no
#: `weight_guards:` block at all is not checked: the toy fixtures in
#: tests/ are deliberately lopsided, and a guard that fires on them
#: would be testing the fixture rather than the ranking.
DEFAULT_WEIGHT_GUARDS = {
    "max_family_share": 0.40,
    "max_board_weight": 0.25,
    "coverage_leverage": 3.0,
}


def weight_guards(groups: dict[str, Any]) -> dict[str, float] | None:
    """The declared weight bounds, or ``None`` where none are declared."""
    declared = groups.get("weight_guards")
    if not declared:
        return None
    return {key: float(declared.get(key, value)) for key, value in DEFAULT_WEIGHT_GUARDS.items()}


def eval_families(groups: dict[str, Any]) -> dict[str, str]:
    """Board -> the evaluation family it belongs to, from the YAML.

    An evaluation family is one benchmark under however many names it
    was published under: Terminal-Bench 4.0, Terminal-Bench 2.1,
    KiloBench and Artificial Analysis' three re-runs of the same suite
    are six boards and one family. A board named nowhere in
    `eval_families:` is its own family, so the map only has to carry the
    collisions.
    """
    out: dict[str, str] = {}
    for family, boards in (groups.get("eval_families") or {}).items():
        for board in boards or []:
            out[str(board)] = str(family)
    return out


def family_totals(weights: Mapping[str, float], families: Mapping[str, str]) -> dict[str, float]:
    """What each evaluation family carries in one flattened weight map."""
    out: dict[str, float] = defaultdict(float)
    for key, weight in weights.items():
        out[families.get(key, key)] += weight
    return dict(out)


def check_weight_guards(label: str, weights: dict[str, float], groups: dict[str, Any]) -> None:
    """Stop on a group one benchmark family, or one board, decides.

    Coding-experiments was 0.710 Terminal-Bench under three names — the
    whole agentic block plus Artificial Analysis' re-runs of the same
    suite — which makes it a Terminal-Bench ranking with a group name on
    it, and made Terminal-Bench 4.0 the third-heaviest input into a
    paper-writing score as well. Weights are argued about in the YAML,
    so the bound belongs there too; this is the enforcement.
    """
    guards = weight_guards(groups)
    if guards is None:
        return
    families = eval_families(groups)
    where = f"{SKILL_REL}/data/task_groups.yaml"
    for family, share in sorted(family_totals(weights, families).items()):
        if share > guards["max_family_share"] + WEIGHT_TOLERANCE:
            members = sorted(k for k in weights if families.get(k, k) == family)
            raise SystemExit(
                f"{label}: the `{family}` evaluation family carries {share:.3f} of the "
                f"group, over the {guards['max_family_share']:.2f} `max_family_share` in "
                f"{where}. One benchmark under several names is still one benchmark: "
                f"{', '.join(members)}. Spread the weight or raise the bound and say why"
            )
    for board, share in sorted(weights.items()):
        if share > guards["max_board_weight"] + WEIGHT_TOLERANCE:
            raise SystemExit(
                f"{label}: `{board}` carries {share:.3f} of the group, over the "
                f"{guards['max_board_weight']:.2f} `max_board_weight` in {where}"
            )


def check_coverage_leverage(
    label: str, weights: dict[str, float], measured: Mapping[str, float], groups: dict[str, Any]
) -> None:
    """Stop where a heavy board is one most of the pool was never run on.

    A board carrying weight ``w`` that only a share ``c`` of the ranked
    pool holds does not decide ``w`` of the ranking: for the ``1 - c``
    who lack it the weight is renormalised away, so what it really does
    is re-order the measured rows against each other and leave everyone
    else standing on whatever thin evidence remains. Terminal-Bench 4.0
    at 0.448 of coding-experiments, on a ninth of the variants, was the
    case that named this guard.
    """
    guards = weight_guards(groups)
    if guards is None:
        return
    leverage = guards["coverage_leverage"]
    for board, share in sorted(weights.items()):
        cover = measured.get(board, 0.0)
        if share > leverage * cover + WEIGHT_TOLERANCE:
            raise SystemExit(
                f"{label}: `{board}` carries {share:.3f} of the group but only "
                f"{cover:.3f} of the ranked pool was measured on it, over the "
                f"{leverage:g}x `coverage_leverage` in "
                f"{SKILL_REL}/data/task_groups.yaml. Cut the weight, or find the "
                "rows the board is missing"
            )


def group_pillars(groups: dict[str, Any], name: str) -> dict[str, dict[str, float]]:
    """One group's pillars, each as its boards renormalised over itself.

    A pillar is declared either as a list of boards — equal weight, which
    is the default and the honest one where nothing argues for a split —
    or as a mapping of board to weight. Either way the members are
    renormalised over their own total here, so a pillar always carries
    exactly its share of the group and the numbers inside it are only
    ever read against each other.
    """
    spec = groups["groups"][name]
    declared = spec.get("pillars")
    if not declared:
        raise SystemExit(
            f"group `{name}` declares no `pillars:` block in "
            f"{SKILL_REL}/data/task_groups.yaml. A group stands on the three "
            f"pillars ({', '.join(PILLARS)}) or it is not a group"
        )
    out: dict[str, dict[str, float]] = {}
    for pillar, members in declared.items():
        if str(pillar) not in PILLARS:
            raise SystemExit(
                f"group `{name}` declares a pillar `{pillar}`, which is not one of "
                f"{', '.join(PILLARS)}"
            )
        raw = (
            {str(board): 1.0 for board in members}
            if isinstance(members, list)
            else {str(board): float(weight) for board, weight in (members or {}).items()}
        )
        if not raw:
            raise SystemExit(f"group `{name}` declares pillar `{pillar}` with no board in it")
        total = sum(raw.values())
        out[str(pillar)] = {board: weight / total for board, weight in raw.items()}
    return {pillar: out[pillar] for pillar in PILLARS if pillar in out}


def group_weights(groups: dict[str, Any], name: str) -> dict[str, float]:
    """Flatten one group's pillars into per-board weights summing to 1.

    Equal shares, by the author's rule: the pillars answer to different
    people — voters and a scoring key — and neither of them is allowed
    to be the ranking on its own. So each carries the same share of
    every group whatever it holds, and what a group argues about is
    which boards belong in which pillar, never how much a pillar is
    worth.

    A group declaring one pillar hands it the lot; that is a data error
    the YAML's own comment calls out, not a licence, and only the toy
    fixtures in tests/ use it.
    """
    pillars = group_pillars(groups, name)
    share = 1.0 / len(pillars)
    out: dict[str, float] = defaultdict(float)
    for members in pillars.values():
        for board, weight in members.items():
            out[board] += share * weight
    flat = dict(out)
    check_weight_sum(f"group {name}", sum(flat.values()))
    check_weight_guards(f"group {name}", flat, groups)
    return flat


def board_pillars(groups: dict[str, Any]) -> dict[str, str]:
    """Board -> the pillar it sits in, read off every group's declaration.

    A board is evidence of one kind wherever it is used: an Arena column
    is a preference measurement in a coding group and in a writing group
    alike. So the map is global, and a board filed under two pillars is a
    contradiction the run stops on rather than resolves.
    """
    out: dict[str, str] = {}
    for name in groups.get("groups") or {}:
        for pillar, members in group_pillars(groups, name).items():
            for board in members:
                if out.setdefault(board, pillar) != pillar:
                    raise SystemExit(
                        f"board `{board}` is in the `{out[board]}` pillar of one group "
                        f"and the `{pillar}` pillar of `{name}`. A board measures one "
                        "kind of thing; pick the pillar it belongs to"
                    )
    return out


def pillar_weights(
    weights: dict[str, float], pillars: dict[str, str]
) -> dict[str, dict[str, float]]:
    """Split one group's flattened weight map into one map per pillar."""
    out: dict[str, dict[str, float]] = defaultdict(dict)
    for key, weight in weights.items():
        out[pillars.get(key, PILLARS[-1])][key] = weight
    return dict(out)


def pillar_shares(groups: dict[str, Any], name: str) -> dict[str, float]:
    """What share of a group's weight each pillar carries — half each.

    Read off the flattened map rather than asserted, because a share the
    page prints and a share the fit uses have to be the same number.
    """
    weights = group_weights(groups, name)
    pillars = board_pillars(groups)
    return {
        pillar: sum(subset.values())
        for pillar, subset in sorted(pillar_weights(weights, pillars).items())
    }


def pillar_share_text(groups: dict[str, Any], name: str) -> str:
    """One line naming each pillar's share of a group's total weight."""
    shares = pillar_shares(groups, name)
    return ", ".join(f"{pillar} {share:.0%}" for pillar, share in shares.items())


def pillars_present(
    scores: dict[str, float], weights: dict[str, float], pillars: dict[str, str]
) -> tuple[list[str], list[str]]:
    """Which of a group's pillars this row has evidence in, and which not.

    One measured board is enough. A pillar is not a composite to be
    renormalised over what the row happens to hold — it is a question
    ("do people prefer it", "do people pay for it", "does it get the
    answer right") and one board answering it is an answer. What is not
    an answer is silence: a pillar the row has no board in is left out of
    the mean rather than filled in at the middle, and the row's status
    says which pillar is missing, because a raw capability over two
    pillars means something different from one over three.
    """
    present: list[str] = []
    missing: list[str] = []
    for pillar, subset in sorted(pillar_weights(weights, pillars).items()):
        if any(key in scores for key in subset):
            present.append(pillar)
        else:
            missing.append(pillar)
    return present, missing


#: Fewest pillars a variant needs a measured board in before a group
#: scores it. Two: one pillar alone is one kind of witness, and this
#: whole ranking is the claim that no one kind of witness is enough.
MIN_MEASURED_PILLARS = 2


def coverage(scores: dict[str, float], weights: dict[str, float]) -> tuple[float, int]:
    """One group's benchmark weight behind a row, and its board count.

    Group weights sum to 1, so the weight is already a share. Every board
    counted is one this variant was itself measured on at its own
    reasoning effort: there is nothing else to count, because nothing is
    filled in from anywhere else.
    """
    have = {k: w for k, w in weights.items() if k in scores}
    return sum(have.values()), len(have)


def scale_unit(values: dict[str, float], *, invert: bool) -> dict[str, float]:
    """Min-max each value onto 0-1; ``invert`` makes small values good.

    Every plotted variant sets the ends. Nothing has to be held back
    from the scale any more: a variant reaches a column at all only once
    it is measured on ``MIN_MEASURED_BOARDS`` of the group's boards, so
    an end of a scale is always somebody's measurement.

    This is the capability-per-cost axis alone: the two cost thirds and
    the raw-capability third are min-max scaled against each other, which
    is what makes them three comparable thirds. A benchmark board is
    scaled by ``scale_robust`` instead, for the reason written there.
    """
    if len(values) < 2:
        return dict.fromkeys(values, 0.5)
    low, high = min(values.values()), max(values.values())
    if math.isclose(low, high):
        return dict.fromkeys(values, 0.5)
    span = high - low
    return {
        key: min(1.0, max(0.0, (high - val) / span if invert else (val - low) / span))
        for key, val in values.items()
    }


#: How many inter-quartile ranges either side of a board's median still
#: land inside 0-100. Three is the distance a well-spread board's ends
#: actually reach — for a normal column three sigma is 2.2 IQR — so a
#: board that discriminates uses most of the scale, while a near-flat
#: one, whose ends sit about one IQR out, uses about a third of it.
ROBUST_CLIP = 3.0


def scale_robust(values: dict[str, float]) -> dict[str, float]:
    """Put one board on 0-100 by its own median and inter-quartile range.

    Min-max put every board's ends at 0 and 100 whatever the board did,
    which is the same as declaring every board equally discriminating
    before any weight is applied. A near-flat column — AA-LCR runs 0.803
    to 0.887 over this pool — was stretched to the full scale, so noise
    on it counted as much as a real 40-point spread on Terminal-Bench,
    and a single runaway capture could set an end of a board's scale on
    its own.

    So the middle half of the plotted variants sets the unit instead:
    the median lands on 50 and one IQR is worth ``50 / ROBUST_CLIP``
    points, clipped at ``±ROBUST_CLIP`` IQR. A board whose pool is
    near-flat has ends about one IQR from its median and so spans about
    33-67, contributing proportionally less to the fit than a board
    whose ends are three IQR out and span the whole 0-100. Both the
    clip and the median are robust: one extreme reading moves neither.

    Determinism where the middle half is a single value: the IQR is 0,
    so half the full range stands in for it, and where that is 0 too —
    every variant on the same number — the board says nothing about
    anybody and everyone lands on 50.
    """
    if len(values) < 2:
        return dict.fromkeys(values, 50.0)
    numbers = np.array(sorted(values.values()), dtype=float)
    low_q, middle, high_q = (float(x) for x in np.percentile(numbers, (25.0, 50.0, 75.0)))
    spread = high_q - low_q
    if spread <= 0.0:
        spread = (float(numbers[-1]) - float(numbers[0])) / 2.0
    if spread <= 0.0:
        return dict.fromkeys(values, 50.0)
    unit = 50.0 / ROBUST_CLIP
    return {
        key: 50.0 + unit * min(ROBUST_CLIP, max(-ROBUST_CLIP, (value - middle) / spread))
        for key, value in values.items()
    }


#: Fewest of a group's boards a variant must have been measured on
#: before that group scores, ranks or plots it. Two readings cannot tell
#: a real ability from one lucky board and leave the fit no residual to
#: read a band off; three is the fewest that does both. A variant under
#: it is named in the group's *models not scored in this group* note and
#: given no number at all, because the alternative — a number filled in
#: from another effort, another model or a pool-wide ratio — is the
#: thing this ranking is not allowed to do.
MIN_MEASURED_BOARDS = 3

#: A board carries this much weight in the fit at the very least, so a
#: board weighted near zero still contributes a row rather than a
#: division by zero.
MIN_CELL_WEIGHT = 1e-6


def cell_weight(weights: Mapping[str, float], board: str) -> float:
    """What one board weighs in the fit, never zero."""
    return max(float(weights.get(board, 0.0)), MIN_CELL_WEIGHT)


def cell_weight_total(weights: Mapping[str, float], boards: Iterable[str]) -> float:
    """What a set of boards weighs in the fit, never zero."""
    return max(sum(cell_weight(weights, board) for board in boards), MIN_CELL_WEIGHT)


#: How much of a group's benchmark weight a row has to have been
#: measured on before it may define a frontier, when
#: `data/task_groups.yaml` names no figure.
DEFAULT_FRONTIER_MIN_WEIGHT = 0.5


def frontier_min_weight(groups: dict[str, Any]) -> float:
    """The least measured weight a row needs to hold a frontier.

    Three boards are enough to be scored and ranked, and they are not
    enough to anchor the one line a reader traces: a cheap listing
    measured on a tenth of a group arrives at the cheap corner of the
    chart on evidence nobody would bet the ladder on. So a row also has
    to have been measured on ``frontier_min_weight`` of the group's
    benchmark weight before it can sit on the line.

    It is a share, so anything outside 0 to 1 is a typo rather than a
    setting, and the run stops instead of silently barring every row or
    none.
    """
    value = float(
        (groups.get("shrinkage") or {}).get("frontier_min_weight", DEFAULT_FRONTIER_MIN_WEIGHT)
    )
    if not 0.0 <= value <= 1.0:
        raise SystemExit(
            f"shrinkage.frontier_min_weight is {value:g}, and it is the share of a "
            "group's benchmark weight a row has to have been measured on before "
            "that row may sit on a frontier — a share, so it has to be between 0 and 1"
        )
    return value


#: How many of a group's boards a row has to have been measured on
#: itself before it may define a frontier, when `data/task_groups.yaml`
#: names no figure.
DEFAULT_FRONTIER_MIN_BOARDS = 2


def frontier_min_boards(groups: dict[str, Any]) -> int:
    """The fewest boards of its own a row needs to hold a frontier.

    A share of the weight is not the whole question: a group whose
    weight sits on a handful of wide boards can put a row over the
    weight bar on one of them, and one board is a reading, not a
    position. Two boards that agree are the least that is not.

    It is a count, so anything under one is a typo rather than a
    setting, and the run stops rather than quietly barring every row.
    """
    value = (groups.get("shrinkage") or {}).get("frontier_min_boards", DEFAULT_FRONTIER_MIN_BOARDS)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise SystemExit(
            f"shrinkage.frontier_min_boards is {value!r}, and it is how many of a "
            "group's boards a row has to have been measured on before that row may "
            "sit on a frontier — a count of boards, so it has to be a whole number "
            "of at least 1"
        )
    return value


def board_columns(models: list[Model]) -> dict[str, dict[str, float]]:
    """Transpose a set of models into one column per benchmark."""
    columns: dict[str, dict[str, float]] = defaultdict(dict)
    for model in models:
        for key, value in model.scores.items():
            columns[key][model.key] = value
    return columns


#: Two weighted terms of one group correlating above this, over the
#: variants carrying both, are one measurement wearing two names. The
#: line is drawn from the catalogue itself: the arena category boards
#: sit at 0.98-0.99 against each other and really are slices of one
#: voting pool, while arena_creative_elo (0.964) and the Terminal-Bench
#: pair (0.96) are separate evidence that happens to agree.
DUPLICATE_R = 0.98

#: A correlation is not read at all below this many shared variants:
#: three models agreeing proves nothing, and the catalogue has boards
#: that overlap on four.
DUPLICATE_MIN_SHARED = 20


def group_terms(groups: dict[str, Any], name: str) -> dict[str, dict[str, float]]:
    """One group's weighted terms: its pillars, as boards.

    The duplicate check below reads pillars rather than boards, because
    the boards inside a pillar are meant to agree — four Arena columns
    are four slices of one voting pool, and the pillar is the fix for
    counting them four times, not the problem. What must not agree is
    two pillars: if what people prefer and what a scoring key says rank
    the catalogue identically, then one of them is decoration and the
    group is standing on one leg.
    """
    return group_pillars(groups, name)


def term_column(scaled: dict[str, dict[str, float]], members: dict[str, float]) -> dict[str, float]:
    """One term as a column: each variant's weighted mean of what it has."""
    out: dict[str, float] = {}
    for key, row in scaled.items():
        held = {k: w for k, w in members.items() if k in row}
        if held:
            out[key] = sum(w * row[k] for k, w in held.items()) / sum(held.values())
    return out


def correlation(left: Mapping[str, float], right: Mapping[str, float]) -> tuple[float, int]:
    """Pearson r over the keys both columns hold, and how many that was."""
    shared = sorted(set(left) & set(right))
    if len(shared) < 2:
        return 0.0, len(shared)
    first = np.array([left[key] for key in shared])
    second = np.array([right[key] for key in shared])
    if not first.std() or not second.std():
        return 0.0, len(shared)
    return float(np.corrcoef(first, second)[0, 1]), len(shared)


def duplicate_terms(
    models: list[Model], groups: dict[str, Any]
) -> list[tuple[str, str, str, float, int]]:
    """Weighted terms of one group that are the same measurement twice.

    Two boards agreeing cell for cell is the easy case and the old check
    caught it. The expensive case is the one that was live: four arena
    category boards, none identical, all ranking the catalogue the same
    way, carrying 0.44 of scientific-writing between them for what is
    one opinion poll. Correlation catches both.
    """
    columns = board_columns(models)
    scaled: dict[str, dict[str, float]] = defaultdict(dict)
    for key, column in columns.items():
        for model_key, unit in scale_robust(column).items():
            scaled[model_key][key] = unit
    out: list[tuple[str, str, str, float, int]] = []
    for name in groups["groups"]:
        terms = {
            term: term_column(scaled, members)
            for term, members in group_terms(groups, name).items()
        }
        for left, right in itertools.combinations(sorted(terms), 2):
            value, shared = correlation(terms[left], terms[right])
            if shared >= DUPLICATE_MIN_SHARED and value > DUPLICATE_R:
                out.append((name, left, right, value, shared))
    return out


@dataclass(slots=True)
class Ability:
    """One group's additive fit, solved over the measured cells alone."""

    #: variant key -> its ability, on the boards' own 0-100 scale.
    score: dict[str, float] = field(default_factory=dict)
    #: variant key -> the standard error of that ability in the fit.
    band: dict[str, float] = field(default_factory=dict)
    #: board -> the level the fit put that board at, shared by everyone.
    offset: dict[str, float] = field(default_factory=dict)
    #: variant key -> its ability before the group's 0-100 squeeze, on
    #: the boards' own scaled units. Sibling placement works here,
    #: because a gap read off two rows' shared boards is in these units
    #: and not in the squeezed ones.
    raw: dict[str, float] = field(default_factory=dict)
    #: variant key -> the standard error of that unsqueezed ability.
    raw_band: dict[str, float] = field(default_factory=dict)


def _components(cells: dict[str, dict[str, float]]) -> list[tuple[set[str], set[str]]]:
    """The connected pieces of the variant-board graph the cells form.

    Two variants that share no board, directly or through a chain of
    other variants, are not comparable on this evidence at all: the fit
    has one free constant per piece. Each piece is anchored on its own
    below, which is the honest reading — a piece is scored against the
    boards inside it and nothing else.
    """
    seen: set[str] = set()
    out: list[tuple[set[str], set[str]]] = []
    boards_of = {key: set(row) for key, row in cells.items()}
    holders: dict[str, set[str]] = defaultdict(set)
    for key, row in cells.items():
        for board in row:
            holders[board].add(key)
    for start in cells:
        if start in seen:
            continue
        keys, boards, queue = {start}, set(), [start]
        seen.add(start)
        while queue:
            key = queue.pop()
            for board in boards_of[key]:
                if board in boards:
                    continue
                boards.add(board)
                for other in holders[board]:
                    if other not in seen:
                        seen.add(other)
                        keys.add(other)
                        queue.append(other)
        out.append((keys, boards))
    return out


def squeeze_abilities(raw: Mapping[str, float]) -> tuple[float, float]:
    """The one affine map that pulls a group's abilities back into 0-100.

    Where the fit runs past either end of the boards' own scale the
    whole group is squeezed by a single shared map, which keeps every
    distance and every ordering rather than flattening the top rows into
    a tie at 100 the way a clip would. Returns the shift and the scale,
    so a caller that re-places rows before the squeeze applies the same
    map to what it changed.
    """
    if not raw:
        return 0.0, 1.0
    low = min(0.0, *raw.values())
    high = max(100.0, *raw.values())
    return low, 100.0 / (high - low)


def solve_ability(cells: dict[str, dict[str, float]], weights: dict[str, float]) -> Ability:
    """Fit ``value(variant, board) = board_level + ability`` on what exists.

    The evidence is a sparse matrix: every variant sits on a different
    handful of boards, and which boards two variants share differs per
    pair. Averaging each row over the boards it happens to hold compares
    a model measured on the hard boards with one measured on the easy
    ones and calls the second better; filling the gaps in from another
    effort or another model invents the numbers the comparison then
    turns on.

    So this solves, by weighted least squares over exactly the cells
    that exist,

        value(variant, board) = board_level[board] + ability[variant]

    with each cell weighted by its board's weight in the group. The
    board level absorbs how hard or how generous a board is; the ability
    is what is left, which is the group score. Two variants that share
    boards are compared directly through them, and two that do not are
    compared through the chain of variants that connects them — exactly
    the overlap structure the data has, with nothing added to it.

    A Bradley-Terry style pairwise model would answer the same question,
    but it needs the per-pair outcomes recast as wins and loses the size
    of the gap in doing it, and the sizes are the interesting part here:
    the distance between two variants on a board is the finding. So the
    additive fit, which keeps the scale.

    ``numpy.linalg.lstsq`` returns the minimum-norm solution, so the one
    free constant per connected piece does not blow the fit up; each
    piece is then anchored so that its board levels sit where those
    boards' own measured means sit, which ties the pieces to one scale
    without inventing a cell. The band is the standard error of the
    ability from the same fit's residuals.
    """
    keys = sorted(cells)
    boards = sorted({board for row in cells.values() for board in row})
    if not keys or not boards:
        return Ability()
    index = {key: number for number, key in enumerate(keys)}
    board_index = {board: len(keys) + number for number, board in enumerate(boards)}
    design = np.zeros((sum(len(row) for row in cells.values()), len(keys) + len(boards)))
    target = np.zeros(design.shape[0])
    row_number = 0
    for key in keys:
        for board, value in sorted(cells[key].items()):
            root = math.sqrt(cell_weight(weights, board))
            design[row_number, index[key]] = root
            design[row_number, board_index[board]] = root
            target[row_number] = value * root
            row_number += 1
    solution, _, rank, _ = np.linalg.lstsq(design, target, rcond=None)
    ability = {key: float(solution[index[key]]) for key in keys}
    level = {board: float(solution[board_index[board]]) for board in boards}

    # One free constant per connected piece: shift each piece so its
    # board levels agree with those boards' own measured means.
    means = {
        board: fmean([row[board] for row in cells.values() if board in row]) for board in boards
    }
    for piece_keys, piece_boards in _components(cells):
        total = cell_weight_total(weights, piece_boards)
        shift = sum(cell_weight(weights, b) * (means[b] - level[b]) for b in piece_boards) / total
        for board in piece_boards:
            level[board] += shift
        for key in piece_keys:
            ability[key] -= shift

    # The ability is read off as the score on a weight-average board, so
    # it lands on the same 0-100 scale the boards are already on. Where
    # the fit runs past either end of that scale it is squeezed back in
    # by one affine map shared by the whole group, which keeps every
    # distance and every ordering rather than flattening the top rows
    # into a tie at 100 the way a clip would.
    weight_total = cell_weight_total(weights, boards)
    middle = sum(cell_weight(weights, b) * level[b] for b in boards) / weight_total
    residual = design @ solution - target
    spare = max(design.shape[0] - rank, 1)
    variance = float(residual @ residual) / spare
    try:
        covariance = variance * np.linalg.pinv(design.T @ design)
    except np.linalg.LinAlgError:
        logger.warning("the ability fit's covariance did not converge; bands are left at zero")
        covariance = np.zeros((design.shape[1], design.shape[1]))
    raw = {key: value + middle for key, value in ability.items()}
    raw_band = {key: math.sqrt(max(float(covariance[index[key], index[key]]), 0.0)) for key in keys}
    low, scale = squeeze_abilities(raw)
    return Ability(
        score={key: (value - low) * scale for key, value in raw.items()},
        band={key: scale * value for key, value in raw_band.items()},
        offset=level,
        raw=raw,
        raw_band=raw_band,
    )


def pillar_fits(
    cells: dict[str, dict[str, float]], weights: dict[str, float], pillars: dict[str, str]
) -> tuple[dict[str, float], dict[str, float], dict[str, Ability]]:
    """One additive fit per pillar, and the mean of the pillars each row has.

    The pillars hold disjoint boards, so each fit is a self-contained
    reading of one kind of evidence and the three can be averaged without
    double-counting anything. A row with no board in a pillar is simply
    not in that fit, and its mean is over the pillars it does have — the
    alternative, a middling score standing in for the missing pillar, is
    an opinion nobody measured.

    The band is the pillars' bands combined in quadrature over the count,
    which is the standard error of their mean.
    """
    by_pillar = pillar_weights(weights, pillars)
    parts: dict[str, Ability] = {}
    for pillar, members in sorted(by_pillar.items()):
        rows = {key: {k: v for k, v in row.items() if k in members} for key, row in cells.items()}
        rows = {key: row for key, row in rows.items() if row}
        if rows:
            parts[pillar] = solve_ability(rows, weights)
    raw: dict[str, float] = {}
    raw_band: dict[str, float] = {}
    for key in cells:
        held = [part for part in parts.values() if key in part.raw]
        if not held:
            continue
        raw[key] = fmean([part.raw[key] for part in held])
        raw_band[key] = math.sqrt(sum(part.raw_band[key] ** 2 for part in held)) / len(held)
    return raw, raw_band, parts


#: Fewest boards an effort variant has to share with its family's
#: best-measured variant before it may be placed against it. One,
#: because a placed row is not being scored on that board: it is being
#: put at a distance from a row the group's fit already pinned down on
#: everything that row was run on. One shared board is a thin reading
#: of the distance, which the row's band says out loud; no shared board
#: is no reading at all, and such a row is left where it was.
MIN_SIBLING_SHARED = 1


def sibling_anchor(
    family: list[Model],
    cells: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    *,
    model_level: frozenset[str] | set[str] = frozenset(),
) -> Model:
    """The variant of one model the rest of its efforts are placed against.

    The most measured boards, because that is the variant whose ability
    the group's fit actually pinned down; ties go to the one whose
    boards carry the most of the group's weight, and a tie there to the
    variant key, so the answer never depends on catalogue order.
    """
    return max(
        family,
        key=lambda model: (
            len(set(cells.get(model.key, {})) - set(model_level)),
            cell_weight_total(weights, set(cells.get(model.key, {})) - set(model_level)),
            model.key,
        ),
    )


def shared_gap(
    sibling: Mapping[str, float],
    anchor: Mapping[str, float],
    weights: Mapping[str, float],
    shared: list[str],
    *,
    fallback: float = 0.0,
) -> tuple[float, float]:
    """Weighted mean of (sibling - anchor) over shared boards, and its error.

    Board weights, because the boards two efforts share are not equally
    interesting either. The error is the standard error of that weighted
    mean over the boards, so a pair that disagrees board to board is
    placed with a wider band than one that agrees on all of them.

    One shared board has no spread of its own to read, and calling that
    error zero would print the most confident band on the page under
    the thinnest evidence on it. So ``fallback`` stands in: the caller
    passes the anchor's own residual scatter — how far that model's own
    boards disagree about it — widened by ``math.sqrt(2)`` because a
    one-board gap carries the noise of both rows' readings on that
    board and the anchor's scatter is the only estimate of per-board
    noise the fit has.
    """
    cells = [cell_weight(weights, board) for board in shared]
    gaps = [sibling[board] - anchor[board] for board in shared]
    total = sum(cells)
    mean = sum(w * gap for w, gap in zip(cells, gaps, strict=True)) / total
    square = sum(w * w for w in cells)
    spare = total - square / total
    if spare <= 0.0:
        return mean, fallback
    spread = sum(w * (gap - mean) ** 2 for w, gap in zip(cells, gaps, strict=True)) / spare
    return mean, math.sqrt(max(spread, 0.0) * square) / total


def residual_scatter(
    row: Mapping[str, float], offset: Mapping[str, float], ability: float
) -> float:
    """How far one row's own boards disagree about its ability.

    The fit says every cell is a board level plus an ability; what is
    left over on each of this row's boards is what the model did that
    the fit cannot explain. The spread of those leftovers is the band a
    single board deserves, and it is zero only for a row whose boards
    agree exactly or a row with one board, where there is nothing left
    to read.
    """
    gaps = [value - offset.get(board, 0.0) - ability for board, value in row.items()]
    return float(stdev(gaps)) if len(gaps) > 1 else 0.0


def and_list(words: Iterable[str]) -> str:
    """`a`, `a and b`, `a, b and c` — a list a person reads aloud."""
    items = list(words)
    if len(items) < 2:
        return items[0] if items else ""
    return f"{', '.join(items[:-1])} and {items[-1]}"


class PillarGap(NamedTuple):
    """One pillar's distance between an effort variant and its anchor.

    A gap is read off boards, and a board answers one pillar's question,
    so the distance it measures belongs to that pillar and to no other.
    """

    pillar: str
    #: How many of that pillar's boards the two rows share.
    shared: int
    #: The weighted mean of (this row - anchor) over those boards, after
    #: the reliability shrink, and that mean's standard error.
    gap: float
    error: float
    #: How much of the measured gap survived the shrink.
    weight: float = 1.0


class Placement(NamedTuple):
    """Where one effort variant sits relative to its family's anchor."""

    #: The variant being placed, and the variant it is placed against.
    key: str
    anchor_key: str
    #: The anchor's printed name, for the status line.
    anchor: str
    #: How many boards the two were both measured on.
    shared: int
    #: The mean of the pillar gaps below, after the shrink, and the
    #: standard error of that mean. ``None`` where no pillar had a board
    #: to read a gap off at all, and the row is left where it was. It is
    #: a summary for the reader: what moves the row is ``parts``, pillar
    #: by pillar, because a gap measured on preference boards is a
    #: statement about preference and about nothing else.
    gap: float | None
    error: float
    #: How much of the measured gap survived the shrink: 1.0 where the
    #: shared boards agree tightly, falling toward 0 as their own scatter
    #: swamps the distance being read. Printed wherever it bites.
    weight: float = 1.0
    #: The gap in each pillar the two rows share a board in.
    parts: tuple[PillarGap, ...] = ()

    @property
    def note(self) -> str:
        """The status words this placement puts on the row."""
        boards = "board" if self.shared == 1 else "boards"
        if self.gap is None:
            if not self.shared:
                return f"no board shared with {self.anchor}"
            return f"too few boards shared with {self.anchor}: {self.shared}"
        held = "" if self.weight > SHRINK_QUIET else f", at {self.weight:.0%} of the measured gap"
        moved = and_list([part.pillar for part in self.parts])
        pillars = "pillar" if len(self.parts) == 1 else "pillars"
        return (
            f"placed relative to {self.anchor} on {self.shared} shared {boards} "
            f"in the {moved} {pillars}{held}"
        )


#: A shrink at or above this is not worth a reader's attention: the
#: boards agreed, the gap stands, and the status line stays short.
SHRINK_QUIET = 0.95


def shrink_placements(found: list[Placement], raw: Mapping[str, float]) -> list[Placement]:
    """Charge every placed gap for how well the shared boards agree.

    A placement reads one number — the distance between two efforts of
    one model — off however many boards both were run on. Read off one
    board it is one board's noise as much as it is a distance, and on a
    board the pool is near-flat on, noise is most of what there is: a
    rounding difference lands a whole inter-quartile range up the scale.
    That is how a medium-effort row once arrived at the top of a coding
    group on a single shared board nobody would have bet on.

    So the gap is shrunk toward zero by its own reliability. Treat the
    true sibling gaps as spread by ``tau`` — estimated from the
    placements that stand on more than one board, which are the ones
    with a scatter of their own to read — and each measured gap as that
    true gap plus noise of size ``error``. The posterior mean is

        gap * tau^2 / (tau^2 + error^2)

    which is 1.0 when the boards agree tightly, a half when the noise is
    the size of a typical real gap, and near zero when it swamps it. It
    is not a clamp: nothing is bounded, the direction is never flipped,
    and a well-measured placement moves exactly as far as it did before.
    A family whose siblings really do differ widens ``tau`` and so keeps
    more of its gaps.

    The band is left un-shrunk, at the full reading error, because the
    thing a reader must not be sold is a thin placement wearing a
    confident band.
    """
    spread = [part.gap for spot in found for part in spot.parts if part.shared > 1]
    if len(spread) > 1:
        tau = math.sqrt(fmean([gap * gap for gap in spread]))
    else:
        numbers = sorted(raw.values())
        tau = float(stdev(numbers)) if len(numbers) > 1 else 0.0
    out: list[Placement] = []
    for spot in found:
        if spot.gap is None or tau <= 0.0:
            out.append(spot)
            continue
        parts = tuple(
            part._replace(
                gap=part.gap * (tau * tau / (tau * tau + part.error * part.error)),
                weight=tau * tau / (tau * tau + part.error * part.error),
            )
            for part in spot.parts
        )
        gap, error, weight = summarise(parts)
        out.append(spot._replace(gap=gap, error=error, weight=weight, parts=parts))
    return out


def summarise(parts: tuple[PillarGap, ...]) -> tuple[float, float, float]:
    """The one-line reading of a set of pillar gaps, for the status row.

    The mean of the pillar gaps, the standard error of that mean, and
    the mean of what survived the shrink in each. What actually moves
    the row is each pillar's own gap, applied to that pillar alone.
    """
    return (
        fmean([part.gap for part in parts]),
        math.sqrt(sum(part.error**2 for part in parts)) / len(parts),
        fmean([part.weight for part in parts]),
    )


def sibling_placements(
    models: list[Model],
    cells: Mapping[str, Mapping[str, float]],
    weights: Mapping[str, float],
    *,
    pillars: Mapping[str, str],
    fits: Mapping[str, Ability] | None = None,
    extra: Mapping[str, Mapping[str, float]] | None = None,
    raw: Mapping[str, float] | None = None,
    model_level: frozenset[str] | set[str] = frozenset(),
) -> list[Placement]:
    """Place each effort variant against the sibling that measured most.

    The additive fit has a board level and a row ability and no term for
    the two together, so a weakness the whole model family shares on the
    boards only one of its efforts was run on is charged to that effort
    alone. Measured, that is not a small effect: GPT-6 Astra at max sits
    on 27 of coding-experiments' 40 boards including several near the
    pool's floor, its high and xhigh rows sit on 6 easy ones, and the
    global fit put max 19 points under two rows it beats 4-1 on the
    boards all three were run on.

    So within a family — the variants of one catalogue id, which differ
    only in reasoning effort — the best-measured variant keeps its
    global-fit ability, and every other variant is placed at that
    ability plus the weighted mean gap between the two on the boards
    both were measured on. It is direction-free: a sibling that beats
    the anchor on their shared boards lands above it, by exactly what it
    beat it by. The band is the anchor's band and the gap's own standard
    error combined, because a placed row inherits both uncertainties.

    **One gap per pillar, and it moves that pillar alone.** A board
    answers one pillar's question, so two efforts sharing only Arena
    boards have measured their distance in human preference and have
    measured nothing about whether either gets the answer right. Read as
    one number over the whole ability, that preference gap would be
    charged to the capability pillar too: a row on three of a group's
    boards, none of them a capability board, once reached the top of a
    coding frontier that way, on an Arena lead over its own default
    effort. So each pillar moves by the gap its own shared boards
    measured, a pillar with no shared board keeps the anchor's value,
    and the row's raw capability stays the mean of its pillars.

    ``extra`` carries the variants the group's fit would not touch at
    all: under ``MIN_MEASURED_BOARDS`` boards of their own, they cannot
    be told from one lucky reading *on their own boards*, which is why
    they are unranked today. Measured against a sibling that the fit did
    pin down, they can: the thing being read is a distance, not an
    ability, and a distance needs one board at both ends. So such a row
    is placed too, and it is the only way it gets a number at all.

    With no shared board there is no distance to read and the row is
    left exactly as the group found it — placed nowhere, ranked on its
    own boards if it has enough of them and unranked if it has not.

    It reads ``cells`` rather than the rows' stored scores, and returns
    the placements rather than applying them, so that the same rule runs
    over the leave-one-board-out refits: a top five compared against one
    computed by a different method would report moves nobody made.
    """
    pool: dict[str, Mapping[str, float]] = {**(extra or {}), **cells}
    by_id: dict[str, list[Model]] = defaultdict(list)
    for model in models:
        if pool.get(model.key):
            by_id[model.id].append(model)
    found: list[Placement] = []
    for _, family in sorted(by_id.items()):
        # The anchor keeps its group-fit ability, so it has to be a row
        # the group's fit reached: a family nobody measured enough has
        # nothing to be placed against and stays as it is.
        fitted = [model for model in family if cells.get(model.key)]
        if not fitted or len(family) < 2:
            continue
        anchor = sibling_anchor(fitted, cells, weights, model_level=model_level)
        theirs = cells[anchor.key]
        fallback = pillar_fallbacks(theirs, anchor.key, pillars, fits or {})
        for sibling in family:
            if sibling.key == anchor.key:
                continue
            mine = pool[sibling.key]
            # A model-level board carries the same number on every effort
            # of the model, so it says nothing about the distance between
            # two of them: counted as shared it would drag every gap
            # toward zero and look like agreement while doing it.
            shared = sorted((set(mine) & set(theirs)) - set(model_level))
            here: dict[str, list[str]] = defaultdict(list)
            for board in shared:
                here[pillars.get(board, PILLARS[-1])].append(board)
            parts = tuple(
                PillarGap(
                    pillar,
                    len(here[pillar]),
                    *shared_gap(
                        mine, theirs, weights, here[pillar], fallback=fallback.get(pillar, 0.0)
                    ),
                )
                for pillar in PILLARS
                if len(here[pillar]) >= MIN_SIBLING_SHARED
            )
            if not parts:
                found.append(
                    Placement(sibling.key, anchor.key, anchor.name, len(shared), None, 0.0, 1.0)
                )
                continue
            gap, error, weight = summarise(parts)
            found.append(
                Placement(
                    sibling.key, anchor.key, anchor.name, len(shared), gap, error, weight, parts
                )
            )
    return shrink_placements(found, raw or {})


def pillar_fallbacks(
    row: Mapping[str, float],
    key: str,
    pillars: Mapping[str, str],
    fits: Mapping[str, Ability],
) -> dict[str, float]:
    """The band a one-board gap deserves, per pillar, from the anchor.

    One shared board has no spread of its own, so ``shared_gap`` is
    handed the anchor's own residual scatter instead — how far that
    row's boards disagree about it *inside that pillar*, which is the
    only per-board noise estimate that pillar's fit has. Widened by
    ``sqrt(2)`` because a one-board gap carries both rows' noise on it.
    """
    out: dict[str, float] = {}
    for pillar, fit in fits.items():
        if key not in fit.raw:
            continue
        mine = {k: v for k, v in row.items() if pillars.get(k, PILLARS[-1]) == pillar}
        out[pillar] = math.sqrt(2.0) * residual_scatter(mine, fit.offset, fit.raw[key])
    return out


def apply_placements(
    placements: list[Placement],
    raw: dict[str, float],
    raw_band: dict[str, float],
    fits: Mapping[str, Ability],
) -> None:
    """Move each placed row onto its anchor's pillars, in place.

    Pillar by pillar, before the group's 0-100 squeeze, so every gap is
    added in the boards' own units. A pillar the two rows share no board
    in keeps the anchor's value: the distance there was never measured,
    and the anchor is the best-measured row of that family. A pillar the
    placed row was fitted in but the anchor was not keeps its own
    number, because that one it did measure itself.

    The row's raw capability is then the mean of its pillars, exactly as
    ``pillar_fits`` computes it for everybody else. A row with no shared
    board anywhere is left where the group's fit put it, and a row the
    fit never reached gets its only number here.
    """
    for spot in placements:
        if spot.gap is None:
            continue
        moved = {part.pillar: part for part in spot.parts}
        values: list[float] = []
        bands: list[float] = []
        for pillar, fit in sorted(fits.items()):
            part = moved.get(pillar)
            if spot.anchor_key in fit.raw:
                value = fit.raw[spot.anchor_key] + (part.gap if part else 0.0)
                band = math.hypot(fit.raw_band[spot.anchor_key], part.error if part else 0.0)
            elif spot.key in fit.raw:
                value, band = fit.raw[spot.key], fit.raw_band[spot.key]
            else:
                continue
            fit.raw[spot.key], fit.raw_band[spot.key] = value, band
            values.append(value)
            bands.append(band)
        if not values:
            continue
        raw[spot.key] = fmean(values)
        raw_band[spot.key] = math.sqrt(sum(band * band for band in bands)) / len(bands)


def overlap_pairs(
    models: list[Model], group: str, *, shared: int = MIN_MEASURED_BOARDS
) -> Iterator[tuple[Model, Model, int, float, float]]:
    """Every pair of scored variants with enough boards in common.

    Yields the two rows, how many boards they share, the gap the fit put
    between them and their mean gap on those shared boards. A pair where
    either gap is zero is left out: a tie orders nothing, so there is
    nothing for the fit to agree or disagree with.
    """
    scored = [m for m in models if group in m.fit and m.normed.get(group)]
    for left, right in itertools.combinations(scored, 2):
        common = set(left.normed[group]) & set(right.normed[group])
        if len(common) < shared:
            continue
        gap = fmean([left.normed[group][key] - right.normed[group][key] for key in common])
        apart = left.fit[group] - right.fit[group]
        if math.isclose(gap, 0.0, abs_tol=1e-9) or math.isclose(apart, 0.0, abs_tol=1e-9):
            continue
        yield left, right, len(common), apart, gap


class Disagreement(NamedTuple):
    """One pair the fit ordered against the boards the two rows share."""

    left: str
    right: str
    #: How many boards both rows were measured on.
    shared: int
    #: The gap the group's fit put between them, left minus right.
    fitted: float
    #: Their mean gap on the shared boards, the same way round.
    measured: float


def overlap_disagreements(
    models: list[Model], group: str, *, shared: int = MIN_MEASURED_BOARDS
) -> list[Disagreement]:
    """Every pair the fit ordered against its own overlap, worst first.

    The aggregate count says how often the fit reads the overlap; it
    cannot say which reading to distrust. So every pair that came out
    the other way is named, with both gaps, ordered by the smaller of
    the two — a pair that is 8 points apart in the fit and 6 the other
    way on its shared boards is a real contradiction, one that is 0.1
    either way is two rows that are level.
    """
    found = [
        Disagreement(left.name, right.name, count, apart, gap)
        for left, right, count, apart, gap in overlap_pairs(models, group, shared=shared)
        if (gap > 0.0) != (apart > 0.0)
    ]
    return sorted(found, key=lambda d: (-min(abs(d.fitted), abs(d.measured)), d.left, d.right))


def overlap_agreement(
    models: list[Model], group: str, *, shared: int = MIN_MEASURED_BOARDS
) -> tuple[int, int]:
    """How often the fitted ordering agrees with the shared boards.

    The check the additive fit has to pass: take every pair of scored
    variants with at least ``shared`` boards in common, and compare the
    sign of the gap between their abilities with the sign of the mean
    gap between them on the boards they actually share. A fit that
    reorders pairs against their own overlap is not reading the overlap,
    and that is the one thing this method is for. Returns how many pairs
    agreed and how many were compared.
    """
    agree = compared = 0
    for _, _, _, apart, gap in overlap_pairs(models, group, shared=shared):
        compared += 1
        agree += (gap > 0.0) == (apart > 0.0)
    return agree, compared


#: How deep into a group's table the leave-one-board-out check looks.
#: A reader picking a model reads the top of the table, so that is where
#: an unstable ordering matters; a board that only reshuffles rows 80
#: and 90 has not changed anyone's decision.
LOBO_TOP = 10

#: And how deep the *set* is read: which rows are in the top five at all
#: is a coarser question than what order they sit in, and it is the one
#: a reader who wants a shortlist is asking.
LOBO_SET = 5


class Lobo(NamedTuple):
    """What dropping one board did to the top of one group's table."""

    board: str
    #: The furthest any top-`LOBO_TOP` row moved, in places.
    moved: int
    #: The row that moved that far, and where it went.
    model: str
    was: int
    now: int
    #: Rows that entered or left the top `LOBO_SET` altogether.
    churn: int


def lobo_shifts(
    models: list[Model], name: str, weights: dict[str, float], pillars: dict[str, str]
) -> list[Lobo]:
    """Refit the group without each board in turn and see what moves.

    The fit is least squares over sparse evidence, and least squares
    does not say how much of its answer rests on any one input. This
    does, the only way sparse evidence allows: drop a board, solve
    again, and measure how far the top of the table travels. A board
    whose removal reorders the rows a reader actually chooses between is
    load-bearing, whatever weight the YAML gives it; one whose removal
    changes nothing is decorative.

    Rows that fall under `MIN_MEASURED_BOARDS` once the board is gone
    leave both orderings rather than counting as a move — they are not
    reordered, they are unranked, which the coverage table already says.

    Returns one row per board that moves anything, worst first.
    """
    cells = {m.key: dict(m.normed.get(name, {})) for m in models if name in m.fit}
    cells = {k: v for k, v in cells.items() if v}
    if not cells:
        return []
    model_level = {key for m in models for key in m.shared}
    names = {m.key: m.name for m in models}
    base = sorted(cells, key=lambda k: -next(m for m in models if m.key == k).fit[name])
    out: list[Lobo] = []
    for board in sorted(weights):
        kept = {k: v for k, v in weights.items() if k != board}
        if not kept or not any(board in row for row in cells.values()):
            continue
        left = {key: {k: v for k, v in row.items() if k != board} for key, row in cells.items()}
        own = {k: set(v) - model_level for k, v in left.items()}
        fitted = {k: v for k, v in left.items() if len(own[k]) >= MIN_MEASURED_BOARDS}
        spare = {k: v for k, v in left.items() if 0 < len(own[k]) < MIN_MEASURED_BOARDS}
        after, after_band, parts = pillar_fits(fitted, kept, pillars)
        apply_placements(
            sibling_placements(
                models,
                fitted,
                kept,
                pillars=pillars,
                fits=parts,
                extra=spare,
                raw=after,
                model_level=model_level,
            ),
            after,
            after_band,
            parts,
        )
        common = [k for k in base if k in after]
        was = {k: i for i, k in enumerate(common)}
        now = {k: i for i, k in enumerate(sorted(common, key=lambda k: -after[k]))}
        top = common[:LOBO_TOP]
        if not top:
            continue
        worst = max(top, key=lambda k: abs(now[k] - was[k]))
        moved = abs(now[worst] - was[worst])
        churn = len(set(common[:LOBO_SET]) ^ {k for k in common if now[k] < LOBO_SET})
        out.append(Lobo(board, moved, names[worst], was[worst] + 1, now[worst] + 1, churn // 2))
    out.sort(key=lambda row: (-row.moved, -row.churn, row.board))
    return out


def fit_abilities(
    models: list[Model],
    weight_maps: dict[str, dict[str, float]],
    pillars: dict[str, str],
    core: list[str],
) -> None:
    """Score every variant in every group, from its own measured cells.

    Each board is put on 0-100 by its own median and inter-quartile
    range over every plotted variant that carries it — an Elo, a dollar
    figure and a percentage cannot share a fit, and a board whose pool is
    near-flat should not be stretched to the full scale on the strength
    of its two end readings.

    Then one additive fit **per pillar**, over the cells that exist, and
    the group's raw capability is the mean of the pillar abilities the
    variant has. That is what equal halves means when the evidence is
    sparse: a single fit over both pillars' boards at half the weight
    each gives a variant sitting on twelve Arena columns and one
    Artificial Analysis row a score that is mostly Arena, whatever the
    declared share says, because the weights only bind where the cells
    exist. Per pillar, then averaged, they bind everywhere.

    A pillar the variant has no board in is left out of that mean rather
    than filled in, and the row's status names it. A variant needs a
    board in ``MIN_MEASURED_PILLARS`` pillars and ``MIN_MEASURED_BOARDS``
    boards measured at its own reasoning effort before a group scores it
    at all: a board marked `per_effort: false` describes the model and
    not the effort, so it buys a pillar but not the board count.

    The result is read once more per model family: an effort variant
    measured on a handful of its family's boards is placed against the
    variant that was measured on the most of them, by the gap between the
    two on the per-effort boards they share. See ``sibling_placements``
    for why an additive fit cannot do that on its own.
    """
    columns = board_columns(models)
    scaled: dict[str, dict[str, float]] = defaultdict(dict)
    for key, column in columns.items():
        for model_key, unit in scale_robust(column).items():
            scaled[model_key][key] = unit
    by_key = {model.key: model for model in models}
    model_level = {key for model in models for key in model.shared}
    for name, weights in weight_maps.items():
        cells: dict[str, dict[str, float]] = {}
        spare: dict[str, dict[str, float]] = {}
        for model in models:
            mine = {k: v for k, v in scaled.get(model.key, {}).items() if k in weights}
            model.normed[name] = mine
            if not mine:
                continue
            present, missing = pillars_present(mine, weights, pillars)
            if missing:
                model.pillars_missing[name] = missing
            own = {k for k in mine if k not in model_level}
            if len(own) < MIN_MEASURED_BOARDS or len(present) < MIN_MEASURED_PILLARS:
                spare[model.key] = dict(mine)
                continue
            cells[model.key] = dict(mine)
        raw, raw_band, parts = pillar_fits(cells, weights, pillars)
        placements = sibling_placements(
            models,
            cells,
            weights,
            pillars=pillars,
            fits=parts,
            extra=spare,
            raw=raw,
            model_level=model_level,
        )
        apply_placements(placements, raw, raw_band, parts)
        for spot in placements:
            by_key[spot.key].placement[name] = spot.note
            if spot.gap is not None:
                by_key[spot.key].anchored[name] = spot.anchor_key
        low, scale = squeeze_abilities(raw)
        for key, value in raw.items():
            by_key[key].fit[name] = (value - low) * scale
            by_key[key].band[name] = scale * raw_band[key]
        # The pillar columns carry the same affine map as the blended
        # number, so a reader can see the halves average to the raw
        # capability beside them on every row, placed rows included:
        # placement moves a pillar, so the mean still holds.
        for pillar, part in parts.items():
            for key, value in part.raw.items():
                if key in raw:
                    by_key[key].pillar_fit.setdefault(name, {})[pillar] = (value - low) * scale
    for model in models:
        scored = [name for name in core if name in model.fit]
        # Overall is a mean of the groups, so a row placed against the
        # same sibling in every group it is scored in is placed against
        # it here too, and rests on the same evidence.
        anchors = {model.anchored.get(name) for name in scored}
        if scored and len(anchors) == 1 and None not in anchors:
            model.anchored[OVERALL] = anchors.pop() or ""
            model.placement[OVERALL] = (
                model.placement[scored[0]].split(" on ")[0] + " in every group"
            )
        if scored:
            model.fit[OVERALL] = fmean([model.fit[name] for name in scored])
            model.band[OVERALL] = fmean([model.band[name] for name in scored])
            model.cover[OVERALL] = fmean([model.cover.get(name, 0.0) for name in scored])
        overall: dict[str, list[float]] = defaultdict(list)
        for name in scored:
            for pillar, part_value in model.pillar_fit.get(name, {}).items():
                overall[pillar].append(part_value)
        if overall:
            model.pillar_fit[OVERALL] = {f: fmean(v) for f, v in sorted(overall.items())}
        # Overall, a pillar is missing only where it is missing
        # everywhere the model was scored: one group carrying it is
        # evidence enough for the column that averages the groups.
        gone = sorted({f for n in scored for f in model.pillars_missing.get(n, [])} - set(overall))
        if gone:
            model.pillars_missing[OVERALL] = gone


def mark_frontier_eligible(
    models: list[Model], group_names: list[str], min_weight: float, min_boards: int
) -> None:
    """Record which rows are measured on enough of a group to hold its line.

    Two bars, both read off the row's own measurements at its own
    reasoning effort: the share of the group's benchmark weight behind
    it, and how many of the group's boards it was run on. Nothing is
    inherited. A placed effort variant carries its anchor's ability, and
    that is exactly why it cannot borrow its anchor's standing: the one
    line a reader traces should be drawn by rows somebody measured, not
    by a row whose position is one shared board's distance from a row
    somebody measured. So an anchor can hold the line while the siblings
    placed against it do not, which is the honest picture of what was
    run.

    A barred row is still scored, ranked, plotted and labelled — it is
    drawn hollow and its status says which bar it fell under.
    """
    for model in models:
        for name in [*group_names, OVERALL]:
            if name not in model.fit:
                continue
            cover = model.cover.get(name, 0.0)
            boards = model.boards.get(name, 0)
            failed: list[str] = []
            if boards < min_boards:
                plural = "" if boards == 1 else "s"
                failed.append(f"{boards} board{plural} of its own, under {min_boards}")
            if cover < min_weight:
                failed.append(f"{cover:.0%} of the group's weight, under {min_weight:.0%}")
            model.frontier_ok[name] = not failed
            if failed:
                model.frontier_bar[name] = "too thin for the frontier: " + and_list(failed)


def none_or_int(value: Any) -> int | None:
    """An int, or ``None`` where the catalogue publishes no number."""
    return None if value is None else int(value)


def none_or_bool(value: Any) -> bool | None:
    """A bool, or ``None`` where the catalogue publishes no flag."""
    return None if value is None else bool(value)


def group_requirements(groups: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """group -> the hard floor a row must clear to run that group's steps.

    Derived in `data/task_groups.yaml` from the step medians, not chosen
    here; this only reads it.
    """
    return {name: dict(spec.get("requirements") or {}) for name, spec in groups["groups"].items()}


def mark_requirements(models: list[Model], groups: dict[str, Any]) -> None:
    """Record, per group, which hard requirements a row is known to fail.

    The three fields are a hard yes or no: a model whose context window
    cannot hold one request of a step, or that cannot call a tool, does
    not do that step badly — it does not do it at all, and a ranking
    that puts it on a frontier is recommending something unbuyable. So a
    failing row keeps its place in the group's table, with the failing
    field named in its status, and leaves the frontier and the cuts.

    A field the capability catalogue does not publish is ``None`` and
    never fails: the ranker reports what it read, and silence is not a
    measurement.
    """
    for name, spec in group_requirements(groups).items():
        min_ctx = spec.get("min_context_tokens")
        min_out = spec.get("min_max_output_tokens")
        needs_tools = bool(spec.get("tool_calling"))
        for model in models:
            gaps: list[str] = []
            if min_ctx is not None and model.context_window is not None:
                if model.context_window < int(min_ctx):
                    gaps.append("context window")
            if min_out is not None and model.max_output_tokens is not None:
                if model.max_output_tokens < int(min_out):
                    gaps.append("max output")
            if needs_tools and model.tool_calling is False:
                gaps.append("tool calling")
            if gaps:
                model.requirement_gaps[name] = gaps


def step_groups(groups: dict[str, Any]) -> dict[str, str]:
    """Pipeline step -> the task group whose weights it uses.

    Every step is scored by its group and nothing overrides that any
    more. The split a step used to be able to override was the agentic
    one, and there is no agentic half now: a group is two pillars at a
    half each, and a step that wanted a different mix of preference and
    capability evidence would be claiming its own group.
    """
    out: dict[str, str] = {}
    for name, spec in groups["groups"].items():
        for step in spec.get("steps") or []:
            out[str(step)] = name
    return out


def score_models(models: list[Model], groups: dict[str, Any]) -> list[str]:
    """Fill in coverage, the ability fit and capability per cost.

    Returns the group names, the last of them ``OVERALL``. Every pipeline
    step is scored by its group, so a per-step best pick is the same
    computation as that group's frontier rather than a second one that
    could drift from it.
    """
    group_defs = groups["groups"]
    min_weight = frontier_min_weight(groups)
    min_boards = frontier_min_boards(groups)
    core = list(group_defs)
    weight_maps = {name: group_weights(groups, name) for name in group_defs}
    every_board = {key for weights in weight_maps.values() for key in weights}

    # Coverage comes first and needs no scaling at all: it is read
    # straight off which of the group's boards the row was measured on.
    for model in models:
        if model.rejected:
            continue
        for name, weights in weight_maps.items():
            model.board_pool[name] = len(weights)
            share, boards = coverage(model.scores, weights)
            if boards == 0:
                continue
            model.cover[name] = share
            model.boards[name] = boards
        model.board_pool[OVERALL] = len(every_board)
        if not [n for n in core if n in model.cover]:
            continue
        model.boards[OVERALL] = len(every_board & set(model.scores))

    pillars = board_pillars(groups)
    paid = rankable(models)
    free = [m for m in models if not m.rejected and m.free]
    if paid:
        measured = {
            board: sum(board in m.scores for m in paid) / len(paid) for board in every_board
        }
        for name, weights in weight_maps.items():
            check_coverage_leverage(f"group {name}", weights, measured, groups)
    fit_abilities(paid, weight_maps, pillars, core)
    mark_frontier_eligible(paid, list(weight_maps), min_weight, min_boards)
    # A `:free` slug is the same weights behind a different endpoint, so
    # it takes the paid row's score rather than being refitted. Fitting
    # the free lane inside itself was the old answer and it produced
    # nothing: nine rows sharing almost no board give every column a
    # sample of one, which no robust scale can read, and every free row
    # came out unscored. The paid scale is also the comparable one.
    inherit_free_scores(free, paid)
    mark_requirements(models, groups)

    cost_cheap = scale_unit(
        {m.key: math.log(m.rel_cost) for m in paid if m.rel_cost is not None},
        invert=True,
    )
    weights = groups["calibrated_intelligence_weights"]
    names = [*core, OVERALL]
    for name in [*weight_maps, OVERALL]:
        # Price cheapness is scaled inside the group, on the group's own
        # measured output:input blend. One pool-wide blend would price
        # every group's listings for a workload only some of them run.
        price_cheap = scale_unit(
            {m.key: math.log(m.blended_by.get(name, m.blended)) for m in paid},
            invert=True,
        )
        fits = scale_unit({m.key: m.fit[name] for m in paid if name in m.fit}, invert=False)
        for model in paid:
            if model.key not in fits:
                continue
            # The thirds a row has, renormalised over themselves. A model
            # no same-source ratio reaches has no cost per task, and the
            # old code handed it its list-price third a second time —
            # which is the claim that its cost per task is exactly
            # average. Two thirds it was measured on beat three with one
            # invented.
            parts = [
                (float(weights["price_cheapness"]), price_cheap[model.key]),
                (float(weights["task_fit"]), fits[model.key]),
            ]
            if model.key in cost_cheap:
                parts.append((float(weights["cost_per_task_cheapness"]), cost_cheap[model.key]))
            model.calibrated_intelligence[name] = sum(w * v for w, v in parts) / sum(
                w for w, _ in parts
            )
    return names


def inherit_free_scores(free: list[Model], paid: list[Model]) -> None:
    """Give each `:free` listing the score of the paid row it is one of.

    The free endpoint serves the same weights as the paid one, so the
    evidence for the paid row is the evidence for the slug. What it does
    not inherit is standing: a free slug is not a purchasable point and
    never defines a frontier, so `frontier_ok` stays False for it with
    the reason spelled out.

    Effort is not selectable through a `:free` slug — the router asks for
    the id and takes what the lane gives it — so the row inherits the
    base-effort variant where the catalogue names one, and otherwise the
    best-covered variant of that id.
    """
    by_id: dict[str, list[Model]] = defaultdict(list)
    for model in paid:
        by_id[model.id].append(model)
    for slug in free:
        twins = by_id.get(slug.paid_listing or "", [])
        if not twins:
            continue
        default = [m for m in twins if m.effort == m.base_effort]
        source = max(default or twins, key=lambda m: m.cover.get(OVERALL, 0.0))
        slug.fit = dict(source.fit)
        slug.band = dict(source.band)
        slug.cover = dict(source.cover)
        slug.boards = dict(source.boards)
        slug.board_pool = dict(source.board_pool)
        slug.pillar_fit = {k: dict(v) for k, v in source.pillar_fit.items()}
        slug.pillars_missing = {k: list(v) for k, v in source.pillars_missing.items()}
        slug.normed = {k: dict(v) for k, v in source.normed.items()}
        slug.effort = source.effort
        slug.frontier_ok = dict.fromkeys(source.fit, False)
        slug.frontier_bar = dict.fromkeys(
            source.fit, "free listing, not a purchasable point on the frontier"
        )


def rankable(models: list[Model]) -> list[Model]:
    """The paid pool the ranking is computed over.

    Rejected rows are out because they are not candidates, `:free`
    listings because they have no price of their own, `evidence: none`
    rows because a price with no board behind it can be reported but
    cannot be ranked — including them would also stretch the price scale
    that every other model is measured on — and `alias_of:` rows because
    their evidence has been folded into the snapshot their id resolves
    to, and one purchasable endpoint is one point.
    """
    return [
        m for m in models if not m.rejected and not m.free and not m.no_evidence and not m.alias_of
    ]


def no_evidence_pool(models: list[Model]) -> list[Model]:
    """Priced candidates on no board, cheapest first."""
    return sorted((m for m in models if m.no_evidence and not m.rejected), key=lambda m: m.blended)


def pareto_front(points: list[Model], group: str) -> list[Model]:
    """Paid models no other paid model beats on both cost and fit.

    Rejected rows and `:free` listings are out by construction: the
    first are not candidates and the second have no price of their own.
    So are the rows measured on too little of the group's benchmark
    weight: their score is their own boards and nothing else, but a
    cheap listing measured on a tenth of a group would still hold the
    cheap end of the line, and the frontier is the one thing on the page
    a reader takes at face value. Those rows keep their place in the
    table, the chart and the least-measured fold — they simply do not
    define the line. `shrinkage.frontier_min_weight` in
    `data/task_groups.yaml` is where that bar is set.

    Out too are the rows that fail the group's hard requirements in
    `data/task_groups.yaml` `requirements:`. A model that cannot hold
    the step's request is not a cheap point on the line; it is not a
    point on the line.
    """
    usable = [
        m
        for m in points
        if not m.rejected
        and not m.free
        and group in m.fit
        and m.frontier_ok.get(group, True)
        and not m.requirement_gaps.get(group)
    ]
    front: list[Model] = []
    for candidate in usable:
        dominated = any(
            other is not candidate
            and other.eff_cost_in(group) <= candidate.eff_cost_in(group)
            and other.fit[group] >= candidate.fit[group]
            and (
                other.eff_cost_in(group) < candidate.eff_cost_in(group)
                or other.fit[group] > candidate.fit[group]
            )
            for other in usable
        )
        if not dominated:
            front.append(candidate)
    front.sort(key=lambda m: (m.eff_cost_in(group), -m.fit[group], m.key))
    # Two efforts of one model can land on the same cost and the same
    # fit, when no board splits them and no ratio prices them apart.
    # They are one point, so the frontier carries one of them.
    seen: set[tuple[str, float, float]] = set()
    out: list[Model] = []
    for model in front:
        tie = (model.id, round(model.eff_cost_in(group), 12), round(model.fit[group], 12))
        if tie in seen:
            continue
        seen.add(tie)
        out.append(model)
    return out


def clip_words(text: str, budget: int) -> str:
    """Drop trailing whole words until the text fits, marking the cut.

    A name cut mid-word reads as a misspelling — and the spell-check
    hook agrees — so whole words go first and only a single word longer
    than the budget is cut through.
    """
    words = text.split()
    while len(words) > 1 and len(" ".join(words)) + 1 > budget:
        words.pop()
    out = " ".join(words)
    if len(out) + 1 <= budget:
        return out + "…"
    return out[: max(budget - 1, 1)] + "…"


def trim_name(text: str, budget: int) -> str:
    """Trim a `Model (effort)` name, keeping the effort tag whole.

    The effort tag is the half of the name a reader is scanning for, so
    the model half gives way first; a name that is all tag falls back to
    trimming the whole string.
    """
    if len(text) <= budget:
        return text
    head, sep, tail = text.rpartition(" (")
    keep = budget - len(sep) - len(tail)
    if sep and tail.endswith(")") and keep >= 4:
        return clip_words(head, keep) + sep + tail
    return clip_words(text, budget)


def md_table(header: list[str], rows: list[list[str]]) -> list[str]:
    """Render a markdown table, trimming one column to stay under 70 chars.

    Column 0 is trimmed unless it holds identifiers, then column 1. The budget is what the other columns do not use, and
    those are measured over the data as well as the header: a column
    headed `raw` holding `100.0` is five characters wide, not three.
    """
    # An identifier column (step ids such as `execute.experiment`) has
    # no word boundary to cut at, and a cut mid-word is a misspelling to
    # the reader and to the spell-check hook alike, so when column 0 is
    # one of those the trimming moves to the next column.
    cut = 0 if any(" " in row[0] for row in rows) or len(header) == 1 else 1
    spans = [
        max(len(row[index]) for row in [header, *rows])
        for index in range(len(header))
        if index != cut
    ]
    budget = MAX_TABLE_WIDTH - sum(span + 3 for span in spans) - 4
    widest = max((len(r[cut]) for r in rows), default=0)
    budget = max(budget, 1)
    out = []
    for original in [header, *rows]:
        cells = [*original]
        cells[cut] = trim_name(cells[cut], budget)
        line = "| " + " | ".join(cells) + " |"
        if len(line) > MAX_TABLE_WIDTH:
            logger.warning(f"table row is {len(line)} chars: {line}")
        out.append(line)
        if original is header:
            out.append("|" + "|".join(["---"] * len(header)) + "|")
    logger.debug(f"table column {cut} budget {budget}, widest name {widest}")
    return out


def by_calibrated_intelligence(models: list[Model], group: str) -> list[Model]:
    """The models scored in one group, best capability per cost first."""
    return sorted(
        (m for m in models if group in m.calibrated_intelligence),
        key=lambda m: m.calibrated_intelligence[group],
        reverse=True,
    )


def pillar_cell(model: Model, group: str, family: str) -> str:
    """One family's own composite, or `-` where the family is absent.

    Absent means either no board of that family at all, or too little of
    its weight to be scored on it — the same rule, read the same way.
    """
    part = model.pillar_fit.get(group, {}).get(family)
    return "-" if part is None else f"{part:.1f}"


def group_order(models: list[Model], group: str, front_ids: set[str]) -> list[Model]:
    """One group's rows: the frontier first, then everything else by fit.

    Sorting on capability per cost alone put a two-board model at the
    top of every table, above the frontier it is not on. It no longer
    can — a row measured on fewer than three of the group's boards is
    not in the table at all — but capability per cost still crossed the
    remainder over itself: it is a mean of three min-max thirds, one of
    which a price-only row simply does not have, so it could rank a row
    above another that is both cheaper and more capable. The frontier is
    what a reader came for and stays on top; the rest follow by raw
    capability, which is the axis the frontier itself is drawn on, so no
    row that can hold a frontier sits above one that beats it on both. A
    row under the coverage floor still can — it is barred from the
    frontier however good it looks, and its status column says so.
    """
    scored = by_calibrated_intelligence(models, group)
    scored.sort(key=lambda m: (m.key not in front_ids, -m.fit[group], m.key))
    return scored


def least_measured(models: list[Model], group: str, count: int = 20) -> list[Model]:
    """The rows in this group with the least evidence behind them.

    Every row here is measured on at least ``MIN_MEASURED_BOARDS`` of
    the group's boards — that is the price of being in the table at all
    — so the fold answers a narrower question than it used to: of the
    rows that are ranked, which rest on the least of the group's
    weight, and how wide is the band on each. Every row too thin to hold
    a frontier is in here whatever the count says, because the page has
    just taken those rows off the line and this is where it says which
    ones and why.
    """
    scored = [m for m in models if group in m.fit]
    scored.sort(key=lambda m: (m.cover.get(group, 0.0), m.key))
    barred = sum(1 for m in scored if not m.frontier_ok.get(group, True))
    return scored[: max(count, barred)]


def rows_for(models: list[Model], group: str, front_ids: set[str]) -> list[list[str]]:
    """Render already-ordered models as table rows, every column spelled out.

    One column per pillar, from column 6 on: the same raw capability
    solved over the preference boards alone and over the capability
    boards alone. Their mean in column 2 is what the ranking uses; the
    split is how a reader sees that the two kinds of evidence disagreed
    before they were averaged. Column 4 and the last two columns are
    what stands behind column 2 — the share of the group's weight
    measured on this row, how many of its boards that was, and the band
    the fit puts on the ability. Every one of them is this row's own.
    """
    return [
        [
            model.name,
            f"{model.calibrated_intelligence[group]:.2f}",
            f"{model.fit[group]:.1f}",
            f"{model.eff_cost_in(group):.2f}",
            f"{model.cover.get(group, 0.0):.2f}",
            "; ".join(model.status(group, on_frontier=model.key in front_ids)),
            *(pillar_cell(model, group, pillar) for pillar in PILLARS),
            f"{model.boards.get(group, 0)} of {model.board_pool.get(group, 0)}",
            f"+/-{model.band.get(group, 0.0):.1f}",
        ]
        for model in models
    ]


def unranked_reason(model: Model, group: str) -> str:
    """Why a variant that carries boards here is still not scored.

    Two bars send a row to this list, and the row is entitled to know
    which: too few measured boards to tell an ability from one lucky
    reading, or boards in only one pillar, which is one kind of witness
    and not the disagreement this ranking is made of.
    """
    boards = model.boards.get(group, 0)
    if boards < MIN_MEASURED_BOARDS:
        return f"under {MIN_MEASURED_BOARDS} measured boards"
    missing = sorted(model.pillars_missing.get(group) or [])
    if missing:
        return f"no {and_list(missing)} board"
    return "not scored here"


def not_enough_boards(models: list[Model], group: str) -> list[Model]:
    """Variants this group carries a board for but cannot rank.

    Fewer than ``MIN_MEASURED_BOARDS`` measured boards is not enough to
    tell an ability from one lucky reading, and a board in fewer than
    ``MIN_MEASURED_PILLARS`` pillars is one source's opinion; the
    alternative to both — a score filled in from another effort, another
    model or a pool-wide ratio — is the thing this ranking does not do.
    What is left here is the rows that failed a bar *and* had no sibling
    effort to be placed against: a variant sharing a board with a
    well-measured effort of the same model is read as a distance from
    that effort instead, and is ranked. So the row is named here, with
    the boards it does have and the bar it missed, and given no number.
    """
    listed = [m for m in models if group not in m.fit and m.boards.get(group, 0) > 0]
    return sorted(listed, key=lambda m: (-m.boards.get(group, 0), m.key))


def group_rows(models: list[Model], group: str, front_ids: set[str]) -> list[list[str]]:
    """Every row of one group, frontier first, then by ranking score."""
    return rows_for(group_order(models, group, front_ids), group, front_ids)


def free_pool(models: list[Model]) -> list[Model]:
    """Free listings, best raw capability first, no-evidence rows last."""
    return sorted(
        (m for m in models if m.free and not m.rejected),
        key=lambda m: (OVERALL in m.fit, m.fit.get(OVERALL, 0.0)),
        reverse=True,
    )


def free_rows(models: list[Model]) -> list[list[str]]:
    """Free-pool rows, ordered by raw capability — the only axis they differ on.

    The number is the paid row's, on the paid scale, because the slug is
    that model. A slug whose base row is on no board has nothing to
    inherit and says so rather than printing a 0.0 that reads like a
    measurement.
    """
    return [
        [
            m.name,
            f"{m.fit[OVERALL]:.1f}" if OVERALL in m.fit else "none",
            f"{m.cover.get(OVERALL, 0.0):.2f}",
            "none" if m.free_only else "paid",
        ]
        for m in free_pool(models)
    ]


def alias_md(models: list[Model]) -> list[str]:
    """Which undated aliases were folded into which dated snapshot.

    An alias and the snapshot it points at are one thing to buy, and
    listing both put the same model on the chart twice — once with the
    boards that named the alias and once with the boards that named the
    date, each looking thinner than the model really is. So the alias's
    scores are merged into the snapshot row and the alias stops being a
    point. This says which ids that happened to, because a reader looking
    for `deepseek-v4-pro` needs to know where it went.
    """
    aliases = sorted((m for m in models if m.alias_of), key=lambda m: m.id)
    if not aliases:
        return []
    out = [
        "## Aliases folded into their snapshots",
        "",
        "An undated alias and the dated snapshot it resolves to are one",
        "endpoint, so they are one row: the alias's boards are merged",
        "into the snapshot, the dated row's list price wins, and the",
        "alias is not plotted. Where to look instead:",
        "",
    ]
    out += md_table(
        ["alias", "scored as"],
        [[m.id, m.alias_of] for m in aliases],
    )
    return out


#: Effective-cost bands a per-step best pick is chosen inside, as
#: multiples of the reference model. One frontier row is not an answer
#: to "what should this step run?" — the frontier spans two orders of
#: magnitude of cost — so the pick is made three times, once per band.
COST_BANDS: tuple[tuple[str, float], ...] = (
    ("at or under the reference", 1.0),
    ("up to 5x the reference", 5.0),
    ("above 5x the reference", math.inf),
)


class BandPick(NamedTuple):
    """One band's pick and whether the frontier actually reaches it."""

    model: Model
    on_frontier: bool


def best_by_band(models: list[Model], key: str) -> dict[str, BandPick]:
    """The best row inside each cost band, by band label.

    The frontier is preferred: a row it does not reach is beaten on both
    cost and fit by something cheaper, so naming it as a pick without
    saying so would be naming a worse buy. But a band the frontier skips
    is not an empty band — on this catalogue the middle band, 1x to 5x
    the reference, holds no frontier row in any group, because the
    frontier jumps from the cheap open models straight to the
    expensive closed ones. Printing "none" there told a reader with a 5x
    budget nothing at all. So the band falls back to the best-fitting
    ranked row inside it, flagged ``on_frontier=False`` for the caller
    to mark: something cheaper and better exists outside the band, and
    the row is the best that band itself can do.
    """
    front = {m.key for m in pareto_front(models, key)}
    out: dict[str, BandPick] = {}
    low = 0.0
    for label, high in COST_BANDS:
        pool = [m for m in models if key in m.fit and low < m.eff_cost_in(key) <= high]
        low = high
        if not pool:
            continue
        reached = [m for m in pool if m.key in front]
        out[label] = BandPick(max(reached or pool, key=lambda m: m.fit[key]), bool(reached))
    return out


def step_picks_md(models: list[Model], groups: dict[str, Any]) -> list[str]:
    """Per pipeline step, the best frontier row in each cost band.

    A step is scored by its group, on the same computation the group
    tables run, so a step's pick cannot drift from its group's frontier.
    """
    mapping = step_groups(groups)
    if not mapping:
        return []
    ordered = sorted(mapping.items(), key=lambda kv: (kv[1], kv[0]))
    out = [
        "## Best pick per pipeline step",
        "",
        "One row per step of the pipeline, picked off that step's own",
        "frontier: the best raw capability inside each band of effective cost.",
        "Three picks rather than one, because the frontier spans two",
        "orders of magnitude of cost and the cheapest frontier row and",
        "the best one are rarely the same buy.",
        "",
        f"Every step is scored by its group, so the {len(ordered)} steps",
        f"below share {len({g for _, g in ordered})} scorings and rows",
        "repeat: look your step up rather than reading down.",
        "",
    ]
    low = 0.0
    for label, high in COST_BANDS:
        rows = []
        for step, group in ordered:
            pick = best_by_band(models, group).get(label)
            name = "none" if pick is None else pick.model.name + ("" if pick.on_frontier else " +")
            rows.append(
                [step, name] + (["-"] if pick is None else [f"{pick.model.fit[group]:.1f}"])
            )
        bounds = f"over {low:g}x" if math.isinf(high) else f"over {low:g}x up to {high:g}x"
        out += [f"**Effective cost {label}** ({bounds}):", ""]
        out += md_table(["step", "best pick", "raw capability"], rows)
        out += [""]
        if any(row[1].endswith(" +") for row in rows):
            out += [
                "`+` marks a band the frontier does not reach: the row named is "
                "the best this band can do, and something outside the band beats "
                "it on cost and capability at once.",
                "",
            ]
        low = high
    return out


def rung_legend(models: list[Model]) -> list[str]:
    """Explain the two `rung:` naming schemes over the rungs in the data.

    `rung:` carries two ladders at once and the label does not say which.
    `r1`..`rN` is the price ladder: one model per rung, ordered by
    blended list price, and it is the ladder a preset walks. The named
    rungs — `claude-easy`, `claude-medium` — are the Claude-only preset's
    three difficulty tiers, which exist because that preset is pinned to
    one provider and its tiers are not price-ordered against everyone
    else's. A reader who sees both in one column needs telling.
    """
    rungs = sorted({str(m.rung) for m in models if m.rung})
    if not rungs:
        return []
    numbered = sorted(
        (r for r in rungs if r.startswith("r") and r[1:].isdigit()),
        key=lambda r: int(r[1:]),
    )
    named = [r for r in rungs if r not in set(numbered)]
    by_rung = {str(m.rung): m for m in models if m.rung}

    def row(rung: str) -> list[str]:
        model = by_rung[rung]
        mark = " (rejected)" if model.rejected else ""
        return [model.base_name + mark, rung, f"{model.blended:.3f}"]

    out = [
        "**The `rung:` labels are two ladders, not one.**",
        "",
        f"- `r1`-`r{len(numbered)}` — the ladder the presets walk, one",
        "  model per rung. It is placed by hand in `models.yaml` and runs",
        "  in roughly ascending list price, so it is a slot rather than a",
        "  computed rank: read the blended price beside it, not the",
        "  number. A rung held by a rejected model records where that",
        "  model would sit; the ranking still excludes it.",
    ]
    if named:
        out += [
            "- " + ", ".join(f"`{r}`" for r in named) + " — the Claude-only",
            "  preset's difficulty tiers, which are not positions on the",
            "  ladder above. That preset is pinned to one provider, so its",
            "  tiers are named rather than numbered.",
        ]
    out += ["", "The ladder as the data has it:", ""]
    out += md_table(["model", "rung", "blended $/M"], [row(r) for r in numbered])
    if named:
        out += ["", "The Claude-only tiers:", ""]
        out += md_table(["model", "Claude rung", "blended $/M"], [row(r) for r in named])
    out += [""]
    return out


#: The three agent backends a preset can run on, and what each will
#: route. `terminal_claude_agent` takes native `claude-*` ids and
#: nothing else; the two OpenRouter backends take `vendor/model` ids,
#: the free one only the `:free` slugs the router's pool declares.
CLAUDE_BACKEND = "terminal_claude_agent"
PAID_BACKEND = "sdk_openhands_agent"
FREE_BACKEND = "sdk_openhands_free"
BACKENDS = (CLAUDE_BACKEND, PAID_BACKEND, FREE_BACKEND)
OPENROUTER_BACKENDS = frozenset({PAID_BACKEND, FREE_BACKEND})

#: The presets, weakest first. A preset's own cut is its level 3, and
#: the two levels below it are the cuts of the presets below it.
PRESETS = ("lite", "pro", "max", "ultra")

#: One rung per preset, plus one above the top preset for its
#: orchestrator to sit on.
LADDER_RUNGS = len(PRESETS) + 1

#: The subagent tier each difficulty level drives, hardest last.
TIER_LEVELS = (("easy", 1), ("medium", 2), ("hard", 3))

#: How many alternates a free-backend role carries. The free pool
#: exhausts, so a role with one id is a role that stops working.
FREE_FALLBACKS = 2

#: Where the runtime keeps the two lists that decide what is routable.
#: They are repo files rather than skill data on purpose: a cut this
#: skill prints that the runtime would refuse is worse than no cut.
REPO_ROOT = SKILL_DIR.parents[2]
ROSTER_PATH = REPO_ROOT / "aii_server/dashboard/api/run_config/_roster/model_discovery.yaml"
FREE_POOL_PATH = REPO_ROOT / "aii_lib/src/aii_lib/free_router/providers.yaml"


def tier_id_routable_on(backend: str, model_id: str) -> bool:
    """Mirror of `_tier_id_routable_on` in the agent harness.

    The harness decides at run time whether an id can be dialled on a
    backend, and a cut it would refuse is not a cut. Kept as the same
    three lines rather than imported, because this script runs from a
    skill directory and importing the server package to ask one question
    would make the ranking depend on the server booting.
    """
    if backend not in OPENROUTER_BACKENDS:
        return True
    model_id = model_id.strip()
    if model_id.startswith("openrouter/"):
        return True
    return "/" in model_id and not model_id.startswith(("claude-", "claude_"))


def roster_id(model_id: str) -> str:
    """The catalogue's `anthropic/claude-fable-5.1` as the CLI's id."""
    return model_id.split("/", 1)[-1].replace(".", "-")


def claude_roster(path: Path) -> dict[str, list[str]]:
    """Native Claude id -> the reasoning efforts the roster ships for it.

    An empty list is not "any effort": Haiku rejects the parameter with
    a 400, and the roster records that by shipping it with no efforts at
    all. So an id with an empty list may only be cut with no effort.
    """
    if not path.is_file():
        logger.warning(
            f"no Claude roster at {path}, so no Claude cut can be checked "
            "for routability and the Claude backend is left out of cuts.yaml"
        )
        return {}
    block = (load_yaml(path).get(CLAUDE_BACKEND) or {}).get("shipped") or []
    return {str(row["model"]): [str(e) for e in (row.get("efforts") or [])] for row in block}


def free_pool_slugs(path: Path) -> list[str]:
    """The `:free` slugs the free router declares on its OpenRouter lane.

    Only that lane: the pool also carries provider-native ids with no
    vendor prefix, and the free backend cannot dial those — the harness
    routability test rejects them before the pool is ever consulted.
    """
    if not path.is_file():
        logger.warning(
            f"no free-router pool at {path}, so the free backend is left out of cuts.yaml"
        )
        return []
    out: list[str] = []
    for provider in load_yaml(path).get("providers") or []:
        if "openrouter.ai" not in str(provider.get("base_url", "")):
            continue
        for entry in provider.get("models") or []:
            slug = entry if isinstance(entry, str) else str(entry.get("id", ""))
            if slug.endswith(FREE_SUFFIX):
                out.append(slug)
    return sorted(dict.fromkeys(out))


def routable_variants(
    models: list[Model], backend: str, roster: Mapping[str, list[str]], slugs: Sequence[str]
) -> list[Model]:
    """Every scored variant this backend could actually dial.

    Three different questions, one per backend, and all three are the
    runtime's own: the Claude CLI takes the ids its roster shipped at
    the efforts that roster names, the paid OpenRouter backend takes any
    `vendor/model` id, and the free backend takes only the slugs the
    free router's pool declares. A truncated catalogue id is dropped
    everywhere — it is a label for a row, not something to dial.
    """
    out: list[Model] = []
    for model in models:
        if model.rejected or model.alias_of or model.id_truncated:
            continue
        if backend == CLAUDE_BACKEND:
            if model.free:
                continue
            efforts = roster.get(roster_id(model.id))
            if efforts is None:
                continue
            if (model.effort or "") not in (efforts or [""]):
                continue
        elif backend == FREE_BACKEND:
            if model.id not in set(slugs):
                continue
        elif model.free or not tier_id_routable_on(backend, model.id):
            continue
        out.append(model)
    return out


def ladder_for(models: list[Model], backend: str, group: str, roster, slugs) -> list[Model]:
    """The rungs one backend's cut for one task group is taken from.

    The spine is the group's own frontier, restricted to what this
    backend can dial and to rows that clear the group's hard
    requirements, read weakest first, and thinned to one rung per
    id-and-effort so every step up the ladder is a real step. Five rungs
    is what the four presets and the top preset's orchestrator need; a
    shorter ladder is returned short and the presets clamp onto its top
    rung rather than repeat a rung and hand two tiers the same model.

    The free lane has no frontier — a free listing is not a price — so
    it is ordered by the evidence it has and then, for the rows with
    none, by the widest window, which is the only published fact about
    them that a step's requirements care about.
    """
    pool = [
        m
        for m in routable_variants(models, backend, roster, slugs)
        if not m.requirement_gaps.get(group)
    ]
    if backend == FREE_BACKEND:
        rungs = sorted(
            pool,
            key=lambda m: (group in m.fit, m.fit.get(group, 0.0), m.context_window or 0, m.id),
        )
    else:
        front = pareto_front([m for m in pool if group in m.fit], group)
        rungs = sorted(front, key=lambda m: (m.fit[group], -m.eff_cost_in(group)))
    seen: dict[tuple[str, str], Model] = {}
    for model in rungs:
        seen.setdefault((rung_id(model, backend), model.effort or ""), model)
    rungs = list(seen.values())
    if len(rungs) <= LADDER_RUNGS:
        return rungs
    step = (len(rungs) - 1) / (LADDER_RUNGS - 1)
    return [rungs[round(i * step)] for i in range(LADDER_RUNGS)]


def role_pick(rung: Model, ladder: Sequence[Model], group: str, backend: str) -> dict[str, Any]:
    """One role's entry: the id to dial, its effort and why it is there."""
    pick: dict[str, Any] = {"model": rung_id(rung, backend)}
    if backend == CLAUDE_BACKEND and not (rung.effort or ""):
        pick["effort"] = None
    else:
        pick["effort"] = rung.effort or None
    if group in rung.fit:
        pick["capability"] = round(rung.fit[group], 1)
        pick["basis"] = "measured"
    else:
        pick["basis"] = "no evidence"
    if backend == FREE_BACKEND:
        rest = [rung_id(m, backend) for m in reversed(ladder) if m.id != rung.id]
        pick["fallbacks"] = list(dict.fromkeys(rest))[:FREE_FALLBACKS]
    return pick


def rung_id(model: Model, backend: str) -> str:
    """The id this backend dials for a rung."""
    return roster_id(model.id) if backend == CLAUDE_BACKEND else model.id


def cut_for(ladder: Sequence[Model], preset: str, group: str, backend: str) -> dict[str, Any]:
    """One preset's four roles on one backend for one task group.

    Level 3 is the preset's own rung, level 2 the rung below it and
    level 1 two below, so a rung is the hard tier of one preset and the
    easy tier of another and the ladder stays single. Lite has nothing
    below it and clamps. The orchestrator sits one rung above level 3,
    or on it where the ladder has run out, which is recorded.
    """
    if not ladder:
        return {}
    index = PRESETS.index(preset)
    top = len(ladder) - 1
    hard = min(index, top)
    cut: dict[str, Any] = {}
    for tier, level in TIER_LEVELS:
        cut[tier] = role_pick(ladder[max(0, hard - (3 - level))], ladder, group, backend)
    lead = min(hard + 1, top)
    cut["orchestrator"] = role_pick(ladder[lead], ladder, group, backend)
    if lead == hard:
        cut["orchestrator"]["note"] = "ladder has nothing above the hard tier"
    return cut


def build_cuts(models: list[Model], core: list[str]) -> dict[str, Any]:
    """preset -> backend -> task group -> the four roles to run it with."""
    roster = claude_roster(ROSTER_PATH)
    slugs = free_pool_slugs(FREE_POOL_PATH)
    pool = [m for m in models if not m.rejected and not m.alias_of]
    ladders = {
        backend: {group: ladder_for(pool, backend, group, roster, slugs) for group in core}
        for backend in BACKENDS
    }
    out: dict[str, Any] = {}
    for preset in PRESETS:
        out[preset] = {}
        for backend in BACKENDS:
            block = {
                group: cut_for(ladder, preset, group, backend)
                for group, ladder in ladders[backend].items()
                if ladder
            }
            if block:
                out[preset][backend] = block
    return {
        "ladders": {
            backend: {
                group: [
                    {
                        "rung": i + 1,
                        "model": rung_id(m, backend),
                        "effort": m.effort or None,
                        "capability": round(m.fit[group], 1) if group in m.fit else None,
                    }
                    for i, m in enumerate(ladder)
                ]
                for group, ladder in by_group.items()
                if ladder
            }
            for backend, by_group in ladders.items()
        },
        "presets": out,
    }


CUTS_HEADER = """\
# Preset cuts, generated by scripts/rank_llms.py. Do not edit.
#
# For each preset, each agent backend and each task group: the model and
# reasoning effort to run the orchestrator and the three subagent tiers
# on. Nothing here is chosen by hand.
#
# `ladders:` is what the cuts are cut from — one ladder per backend per
# task group, weakest rung first, taken from that group's Pareto
# frontier restricted to what the backend can route and to the rows that
# clear the group's hard requirements. There is one rung per preset plus
# one above the top preset for its orchestrator.
#
# `presets:` walks that ladder by the rule in SKILL.md section 6: the
# hard tier is the preset's own rung, medium is one rung down, easy is
# two, the orchestrator is one rung up, and a preset with nothing below
# or above it clamps. Efforts are the efforts the scored rows carry, and
# an effort of `null` means the id takes no effort parameter.
#
# On the free backend every role carries fallbacks, because the free
# pool exhausts. `basis: no evidence` marks a pick this skill has no
# board for at all: it clears the group's hard requirements and nothing
# more is known about it.
"""


def render_cuts(cuts: dict[str, Any]) -> str:
    """cuts.yaml, header comment and all."""
    body = yaml.safe_dump(cuts, sort_keys=False, default_flow_style=False, width=72)
    return CUTS_HEADER + "\n" + body


def cuts_md(cuts: dict[str, Any]) -> list[str]:
    """The preset-cut section of ranking.md.

    The ladders are the substance — the cut itself is one rule applied
    to them, so the rule is printed once as rung numbers rather than
    four near-identical tables of the same ids. The roles with their
    efforts, the free lane's fallbacks and the clamp notes are all in
    `results/cuts.yaml`, which is what the runtime would read.
    """
    out = [
        "## Preset cuts",
        "",
        "One ladder per agent backend per task group, cut four ways.",
        "The rungs are that group's Pareto frontier, weakest first,",
        "restricted to the ids the backend can actually route and to",
        "the rows that clear the group's hard requirements; the free",
        "lane has no frontier, so it is ordered by evidence and then",
        "by context window. A ladder with fewer than five rungs is",
        "left short and the presets clamp onto its top, so no two",
        "tiers are ever handed the same model by padding. Rung",
        "numbers below are for a full ladder. The cuts themselves,",
        "with efforts, free-lane fallbacks and clamp notes, are in",
        "`results/cuts.yaml`.",
        "",
        "Every preset reads the same ladder at these rungs:",
        "",
    ]
    rows = []
    for index, preset in enumerate(PRESETS):
        hard = min(index, LADDER_RUNGS - 1)
        cells = [str(max(0, hard - (3 - level)) + 1) for _, level in TIER_LEVELS]
        rows.append([preset, *cells, str(min(hard + 1, LADDER_RUNGS - 1) + 1)])
    out += md_table(["preset", "easy", "medium", "hard", "lead"], rows)
    for backend, by_group in (cuts.get("ladders") or {}).items():
        out += ["", f"### {backend}", ""]
        if not by_group:
            out += [
                "No id on this backend clears a group's",
                "requirements, so it gets no cut.",
                "",
            ]
            continue
        for group, ladder in by_group.items():
            out += [f"**{group}**", ""]
            out += md_table(
                ["rung", "model", "effort", "raw"],
                [
                    [
                        str(rung["rung"]),
                        rung["model"],
                        rung.get("effort") or "-",
                        "-" if rung.get("capability") is None else f"{rung['capability']:.1f}",
                    ]
                    for rung in ladder
                ],
            )
            out.append("")
    return out


def render_markdown(
    models: list[Model],
    names: list[str],
    groups: dict[str, Any],
    reference: str,
    steps: dict[str, Any],
    *,
    cuts: dict[str, Any],
) -> str:
    """Build the whole of results/ranking.md."""
    ranked = rankable(models)
    output_weight, blend_basis = price_blend(groups)
    split_variants = sum(1 for m in ranked if m.effort_split)
    measured_variants = sum(1 for m in ranked if m.effort_split and not m.price_only)
    lines = [
        "# Agentic LLM ranking",
        "",
        f"Generated by `{SKILL_REL}/scripts/rank_llms.py`.",
        f"Reference model: `{reference}`",
        "(relative price and relative cost per task are 1.00 there).",
        "",
        *glossary_md("Columns, in plain words:", COLUMN_TERMS),
        "**Nothing here is copied, scaled or filled in.** A variant is",
        "scored on the boards it was itself measured on, at its own",
        "reasoning effort, and on no others. No score moves across",
        "efforts or across models, and a model no same-source ratio",
        "reaches has no cost per task at all rather than a guessed one.",
        "",
        "**The boards are sparse, so the scores are solved, not",
        "averaged.** Per group,",
        "`value(variant, board) = board level + ability` is fitted by",
        "weighted least squares over exactly the cells that exist, each",
        "cell weighted by its board's weight in the group. The board",
        "level absorbs how hard or how generous a board is; the ability",
        "is what is left, and that is the raw capability printed here.",
        "Two variants are compared through the boards they share —",
        "which boards those are differs per pair, and the fit uses",
        "whichever they turn out to be.",
        "",
        "**Evidence coverage** is the share of the group's benchmark",
        "weight measured on a row, and the **ability band** is the",
        "standard error the fit puts on it: a row on three boards is",
        "printed with a wide band, not with somebody else's number. A",
        f"row measured on fewer than {MIN_MEASURED_BOARDS} of a group's",
        "boards is not scored in that group on its own boards; it is",
        "scored only if another reasoning effort of the same model was",
        "measured on enough of the group and the two share a board, and",
        "otherwise it is named in the *not scored in this group* list",
        "under the group. A row also has to have been measured itself,",
        "at its own effort, on enough of the group's boards and enough",
        "of its weight before it may sit on a frontier; one that has",
        "not says *too thin for the frontier* and names the bar it fell",
        "under. Nothing is inherited there, so an anchor can hold a",
        "line its placed siblings do not.",
        "",
        "Prices are paid list prices. A `:free` listing is rate-limited",
        "and temporary, so it is never a price: free listings are priced",
        "by the same model's paid listing, and a model with no paid",
        "listing anywhere is out of the paid ranking altogether.",
        "",
        "**Every row is a model at one reasoning effort**, named",
        "`Model (effort)`, because low effort and max effort are two",
        f"different buys. {len(ranked)} variants over",
        f"{len({m.id for m in ranked})} models: an effort gets its own row",
        "where a board published a row for it or a run published its cost",
        "multiplier, and `(default)` means no source named an effort at",
        "all. Effort multiplies the cost per task and never the list",
        "price. A board with no row at that effort is simply a board",
        "this variant is not scored on.",
        "",
        "**Effort is only priced where somebody published the",
        f"multiplier.** {measured_variants} of those {split_variants} variants",
        "sit on a measured multiplier. The rest have no cost per task at",
        "this effort — the default effort's cost is not this effort's",
        "cost, and running a model at max almost certainly burns more",
        "tokens than running it at low — so their capability per cost is",
        "the list-price and raw-capability thirds alone and their",
        "effective cost on the charts is the list price.",
        "",
        *glossary_md("Status words:", STATUS_TERMS),
        "Every number behind these tables — each benchmark, its weight,",
        "its raw and normalised scores, every cost ratio and every list",
        f"price — is in `{SKILL_REL}/results/evidence.md`",
        "and on the frontier page.",
        "",
        "## Cost basis",
        "",
        "List price is one blended number per model: the price of a",
        "million input tokens and the price of a million output tokens,",
        f"averaged with output counted {output_weight:g} times as heavily as",
        "input.",
        "",
        f"That output weighting is **{blend_basis}**. Agentic traffic is",
        "output-dominated once prompt caching works, but nothing in this",
        "skill measures the ratio: no pipeline step records an output-token",
        "median. It is a single number to change, `price_blend:` in",
        f"`{SKILL_REL}/data/task_groups.yaml`, and every price here moves",
        "with it.",
        "",
        "Relative price and relative cost per task are both multiples of",
        f"`{reference}`; effective cost is their geometric mean.",
        "",
        *rung_legend(models),
    ]
    cost_rows = [
        [
            m.name,
            f"{m.blended:.3f}",
            f"{m.rel_price:.2f}",
            "none" if m.rel_cost is None else f"{m.rel_cost:.2f}",
            f"{m.eff_cost:.2f}",
        ]
        for m in sorted(ranked, key=lambda m: m.eff_cost)
    ]
    lines += md_table(
        ["model", "blended $/M", "relative price"],
        [[r[0], r[1], r[2]] for r in cost_rows],
    )
    lines += [
        "",
        "Relative cost per task is `none` where no same-source",
        "ratio reaches the model.",
        "",
    ]
    lines += md_table(
        ["model", "cost per task", "effective cost"],
        [[r[0], r[3], r[4]] for r in cost_rows],
    )

    for name in names:
        spec = groups["groups"].get(name)
        lines += ["", f"## {name}", ""]
        if spec:
            lines.append("Steps: " + ", ".join(f"`{s}`" for s in spec["steps"]))
            lines += [
                "",
                "Two pillars at " + pillar_share_text(groups, name) + " of",
                "the group's weight. The raw capability is the mean of the",
                "pillar scores this row has, so a row missing a pillar is",
                "scored over the one it carries and its status says which",
                "one is gone.",
            ]
            if spec.get("pending"):
                lines += ["", "Pending: " + " ".join(spec["pending"].split())]
        else:
            lines.append("Mean of every group's raw-capability score.")
        lines.append("")
        front = pareto_front(ranked, name)
        front_ids = {m.key for m in front}
        ordered = group_order(ranked, name, front_ids)
        rows = rows_for(ordered, name, front_ids)
        thin_rows = rows_for(least_measured(ranked, name), name, front_ids)
        lines += [
            "Frontier rows first, then the rest by raw capability --",
            "the axis the frontier is drawn on, so no row here sits above",
            "one that beats it on both cost and capability. Capability",
            "per cost is a column to read, not the order. Read the band",
            "beside every raw capability too: it is the standard error of",
            "the ability in this group's fit, so a row measured on three",
            "boards carries a wide one.",
            "",
        ]
        # Two tables rather than one: six spelled-out columns cannot fit
        # inside 70 characters, and abbreviating them back to `cov` is
        # exactly what this report stopped doing.
        lines += md_table(
            ["model", "capability per cost", "raw capability"],
            [[r[0], r[1], r[2]] for r in rows],
        )
        lines += ["", f"Effective cost is a multiple of `{reference}`.", ""]
        lines += md_table(
            ["model", "effective cost", "evidence coverage"],
            [[r[0], r[3], r[4]] for r in rows],
        )
        lines += [
            "",
            "**What stands behind that number.** How many of the",
            "group's boards the row was measured on, and the band the",
            "fit puts on its ability.",
            "",
        ]
        lines += md_table(
            ["model", "measured boards", "ability band"],
            [[r[0], r[-2], r[-1]] for r in rows],
        )
        lines += [
            "",
            "**Pillar split**: the same raw capability recomputed over",
            "the preference boards alone and over the capability boards",
            "alone. A pillar is blank where the row carries no board of",
            "it at all — silence, left out of the mean rather than",
            "filled in at the middle. A row blank in a pillar is not",
            "ranked here.",
            "",
        ]
        lines += md_table(
            ["model", *PILLARS],
            [[r[0], *r[6:-2]] for r in rows],
        )
        lines += ["", "Status of each row:", ""]
        lines += [f"- **{r[0]}** — {r[5]}" for r in rows]
        lines += [
            "",
            "Pareto frontier, cheapest first: "
            + (" -> ".join(m.name for m in front) if front else "no row carries a fit here"),
        ]
        if thin_rows:
            lines += [
                "",
                f"### {len(thin_rows)} least-measured models ({name})",
                "",
                "The ranked rows with the least of this group's benchmark",
                "weight behind them. They are ranked and plotted like any",
                "other, on their own boards — or, where the status says",
                "*placed relative to*, at a distance from another effort",
                "of the same model — and their bands are the widest here.",
                "The ones whose status reads *too thin for the frontier*",
                "were kept off the frontier for that reason.",
                "",
            ]
            lines += md_table(
                ["model", "raw capability", "evidence coverage"],
                [[r[0], r[2], r[4]] for r in thin_rows],
            )
            lines.append("")
            lines += md_table(
                ["model", "measured boards", "ability band"],
                [[r[0], r[-2], r[-1]] for r in thin_rows],
            )
        unranked = not_enough_boards(ranked, name)
        if unranked:
            lines += [
                "",
                f"### {len(unranked)} models not scored in this group ({name})",
                "",
                "These carry a board here and still cannot be read on",
                f"their own: fewer than {MIN_MEASURED_BOARDS} of the",
                "group's boards at their own reasoning effort, or boards",
                "in only one of the two pillars. No effort of the same",
                "model shares a board with them either, so there is",
                "nothing to place them against. They are not scored,",
                "ranked or plotted here, and no number is invented for",
                "them. The boards they do have are on the evidence page.",
                "",
            ]
            lines += md_table(
                ["model", "measured boards", "why"],
                [
                    [
                        m.name,
                        f"{m.boards.get(name, 0)} of {m.board_pool.get(name, 0)}",
                        unranked_reason(m, name),
                    ]
                    for m in unranked
                ],
            )

    lines += ["", "## Free pool", "", *free_pool_prose(models)]
    free_table = free_rows(models)
    lines += md_table(
        ["model", "raw capability", "evidence coverage"],
        [[r[0], r[1], r[2]] for r in free_table],
    )
    lines.append("")
    lines += md_table(
        ["model", "paid listing"],
        [[r[0], r[3]] for r in free_table],
    )
    lines.append("")
    for model in sorted(
        (m for m in models if m.free and not m.rejected),
        key=lambda m: m.fit.get(OVERALL, 0.0),
        reverse=True,
    ):
        if model.free_rationale:
            lines.append(f"- **{model.name}** — " + " ".join(model.free_rationale.split()))

    lines += ["", "## Priced, no evidence", "", *no_evidence_md(models)]

    lines += ["", "## Rejected", ""]
    lines.append("In the data, out of every ranking table and frontier.")
    lines.append("")
    rejected = [m for m in models if m.rejected]
    lines += md_table(
        ["model", "disqualifier"],
        [[m.name, m.rejected_short or "see below"] for m in rejected],
    )
    lines.append("")
    for model in rejected:
        lines.append(f"- **{model.name}** — " + " ".join(model.rejected.split()))

    lines += ["", *alias_md(models), "", *cuts_md(cuts)]

    lines += ["", *step_picks_md(ranked, groups)]

    lines += ["", "## Pipeline steps by measured difficulty", ""]
    step_rows = [
        [
            entry["step"],
            str(entry["level"]),
            str(entry.get("tool_calls_median", "-")),
            f"{entry['cost_usd_median']:.2f}" if entry.get("cost_usd_median") is not None else "-",
        ]
        for entry in sorted(
            steps.get("steps", []),
            key=lambda e: (-e["level"], -(e.get("cost_usd_median") or 0.0)),
        )
    ]
    lines += md_table(["step", "level", "tool calls", "$ median"], step_rows)
    return "\n".join(lines) + "\n"


def no_evidence_md(models: list[Model]) -> list[str]:
    """The count, then the collapsed table, of priced candidates on no board.

    The candidate rule is every text-only tool-capable model published
    in the last three years, so most of the catalogue arrives here: it
    has a price and nothing else. Counting them is the honest coverage
    number — it says how much of the market the boards do not reach —
    and collapsing them keeps a ranking report a ranking report.
    """
    pool = no_evidence_pool(models)
    if not pool:
        return ["Every priced candidate carries at least one board score."]
    lines = [
        f"**{len(pool)}** priced candidates appear on no board this skill",
        "carries, so they have a list price and no raw capability. They are",
        "ranked nowhere, drawn nowhere, and they do not anchor any",
        "scale — a price with no evidence behind it is not a bargain,",
        "it is an unknown. They are listed so the next run can see what",
        "was already screened and what is still waiting for a board.",
        "",
        "<details>",
        f"<summary>{len(pool)} priced candidates with no board evidence</summary>",
        "",
    ]
    lines += md_table(
        ["model", "blended $/M", "created"],
        [[m.name, f"{m.blended:.3f}", m.created or "-"] for m in pool],
    )
    lines += ["", "</details>"]
    return lines


def free_pool_prose(models: list[Model]) -> list[str]:
    """The standing caveat on the free lane, plus who has no paid route."""
    pool = [m for m in models if m.free and not m.rejected]
    orphans = [m.name for m in pool if m.free_only]
    blind = [m.name for m in pool if not m.free_only and OVERALL not in m.fit]
    lines = [
        "The free backend needs an ordering of `:free` listings, and",
        "that is all this table is. A `:free` listing is not a price: it",
        "is a shared rate-limit pool that throttles, queues and lapses,",
        "so **free availability is unreliable** and these rows are",
        "ordered by raw capability alone, never by cost.",
        "",
        "A slug takes its raw capability straight from the paid row it",
        "is a free listing of, on the paid scale, because the weights",
        "behind the two endpoints are the same model. The endpoint is",
        "not: each row keeps the free lane's own context window,",
        "response ceiling and tool-calling flag, and those are what a",
        "task group's hard floors are checked against.",
        "",
        "**Paid listing** says whether the same model has one. A model",
        "marked `none` is free-only with no list price, so it cannot be",
        "priced, has no base row to inherit from and never enters the",
        "paid ranking or a frontier.",
        "",
    ]
    if blind:
        lines += [
            "Paid row exists but is not scored anywhere — too few of",
            "the group's boards, or tagged as carrying no evidence — so",
            "there is nothing for the slug to inherit: " + ", ".join(blind) + ".",
            "",
        ]
    if orphans:
        lines += ["Free-only, no list price: " + ", ".join(orphans) + ".", ""]
    return lines


def label_boxes(text: str, x: float, y: float, anchor: str) -> tuple[float, float, float, float]:
    """Bounding box of one chart label, in SVG user units."""
    width = len(text) * 5.85
    left = {"start": x, "middle": x - width / 2.0, "end": x - width}[anchor]
    return left, y - 8.5, left + width, y + 3.0


def overlaps(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    """Overlapping area of two boxes; zero when they are clear."""
    wide = min(a[2], b[2]) - max(a[0], b[0])
    tall = min(a[3], b[3]) - max(a[1], b[1])
    return wide * tall if wide > 0 and tall > 0 else 0.0


#: Offsets tried in order: right of the dot, then above, below, left, and
#: the diagonals, then further out. The first clear one wins, so a lone
#: point gets the tidy right-hand label and a crowded one steps aside.
LABEL_SLOTS = (
    (9.0, 3.5, "start"),
    (0.0, -10.0, "middle"),
    (0.0, 15.5, "middle"),
    (-9.0, 3.5, "end"),
    (8.0, -8.0, "start"),
    (8.0, 14.0, "start"),
    (-8.0, -8.0, "end"),
    (-8.0, 14.0, "end"),
    (0.0, -21.0, "middle"),
    (0.0, 26.0, "middle"),
)


def ring_slots(radius: float) -> list[tuple[float, float, str]]:
    """Twelve label positions evenly around a dot at one radius."""
    out = []
    for step in range(12):
        angle = math.radians(step * 30.0)
        dx, dy = radius * math.cos(angle), radius * math.sin(angle)
        anchor = "start" if dx > 3.0 else "end" if dx < -3.0 else "middle"
        out.append((round(dx, 1), round(dy + 3.5, 1), anchor))
    return out


#: Tried only for a frontier label that cannot sit clear of everything
#: near its own dot, which is what happens where an effort ladder packs
#: five variants of one model into a few pixels. Rings step outwards, so
#: the nearest clear seat wins, and the label is drawn with a leader line
#: back to the point it names.
FAR_SLOTS = tuple(slot for radius in (30.0, 44.0, 62.0, 84.0) for slot in ring_slots(radius))


@dataclass(slots=True)
class Placed:
    """One label that survived placement, and the dot it belongs to."""

    text: str
    x: float
    y: float
    anchor: str
    solid: bool
    dot_x: float
    dot_y: float

    @property
    def far(self) -> bool:
        """Whether the label sits far enough out to need a leader line."""
        return math.hypot(self.x - self.dot_x, self.y - 3.5 - self.dot_y) > 22.0


def place_labels(
    points: list[tuple[Model, float, float]],
    group: str,
    bounds: tuple[float, float, float, float],
    blocked: list[tuple[float, float, float, float]],
    *,
    must: set[str],
) -> list[Placed]:
    """Greedily place labels, keeping every one of them collision-free.

    Frontier models are placed first because their labels are the ones a
    reader is looking for, and they alone may step out to a far ring and
    take a leader line when nothing close to their dot is clear; every
    other label is placed only where it collides with nothing at all —
    no other label, no dot, no axis, no legend — and is dropped
    otherwise. The rest follow by fit, so a crowded cheap corner gives
    way to the models above it.
    """
    taken = list(blocked)
    for _, x, y in points:
        taken.append((x - 6.0, y - 6.0, x + 6.0, y + 6.0))
    ordered = sorted(
        points,
        key=lambda item: (item[0].key not in must, -item[0].fit.get(group, 0.0)),
    )
    placed: list[Placed] = []
    left, top, right, bottom = bounds
    for model, x, y in ordered:
        text, best, best_cost = model.short, None, math.inf
        slots = LABEL_SLOTS + FAR_SLOTS if model.key in must else LABEL_SLOTS
        for dx, dy, anchor in slots:
            lx, ly = x + dx, y + dy
            box = label_boxes(text, lx, ly, anchor)
            outside = max(0.0, left - box[0]) + max(0.0, box[2] - right)
            outside += max(0.0, top - box[1]) + max(0.0, box[3] - bottom)
            cost = sum(overlaps(box, other) for other in taken) + outside * 40.0
            if cost < best_cost:
                best, best_cost = (lx, ly, anchor, box), cost
            if cost <= 0.0:
                break
        if best is None or (best_cost > 0.0 and model.key not in must):
            continue
        lx, ly, anchor, box = best
        taken.append(box)
        solid = model.frontier_ok.get(group, False)
        placed.append(Placed(text, lx, ly, anchor, solid, x, y))
    return placed


def label_pool(points: list[Model], front_ids: set[str], group: str) -> list[Model]:
    """Which points may carry a text label: the frontier, then the rest.

    The frontier is the line a reader traces, so those labels are
    written whatever it costs. Every other point is a candidate and wins
    a label only where one fits with no overlap at all, which is how the
    chart ends up with as many names as it can read cleanly. Thin points
    used to be barred from a label because a hollow dot's number was not
    evidence; now a thin point is drawn with a ring and its label greyed,
    which says the same thing without hiding which model it is.
    Everything unlabelled keeps its hover card and its table row.
    """
    del front_ids, group
    return list(points)


#: Vendor logo slugs, keyed by the id prefix the catalogue publishes.
#: Each names a file in ``data/logos/``, vendored once from simple-icons
#: (CC0); a vendor with no entry, or whose file is missing, keeps the
#: plain circle, which is why this table is written out rather than
#: guessed from the name.
VENDOR_LOGOS = {
    "amazon": "amazon",
    "anthropic": "anthropic",
    "baidu": "baidu",
    "bytedance-seed": "bytedance",
    "deepseek": "deepseek",
    "google": "googlegemini",
    "ibm-granite": "ibm",
    "kwaipilot": "kuaishou",
    "meituan": "meituan",
    "meta": "meta",
    "minimax": "minimax",
    "mistralai": "mistralai",
    "moonshotai": "moonshotai",
    "nvidia": "nvidia",
    "openai": "openai",
    "qwen": "qwen",
    "tencent": "tencenthy",
    "x-ai": "x",
    "xiaomi": "xiaomi",
    "z-ai": "zdotai",
}

#: Where the vendored logos live, and which of them are actually on disk.
#: They are skill assets rather than catalogue data, so they are read
#: from the skill directory and not from ``--data-dir``.
LOGO_DIR = SKILL_DIR / "data" / "logos"
LOGO_FILES = frozenset(p.stem for p in LOGO_DIR.glob("*.svg")) if LOGO_DIR.is_dir() else frozenset()

#: Marker geometry. The dot is a shade wider than a bare scatter point
#: needs because it now carries the maker's mark, and the logo is
#: squeezed into the square that fits inside that circle.
DOT_R = 6.5
LOGO_SIDE = 8.6


def vendor_logo(model: Model) -> str:
    """The logo slug for one model's maker, or `''` where none is vendored."""
    slug = VENDOR_LOGOS.get(model.id.split("/", 1)[0], "")
    return slug if slug in LOGO_FILES else ""


def logo_sprite(models: list[Model]) -> str:
    """Every logo the charts use, inlined once as one hidden SVG sprite.

    The charts reference the symbols with `<use>`, so a maker's mark is
    in the file once however many of its models are plotted — which is
    what keeps a page with four charts and a thousand markers the same
    size it was with plain dots.
    """
    slugs = sorted({slug for slug in (vendor_logo(m) for m in models) if slug})
    if not slugs:
        return ""
    symbols = []
    for slug in slugs:
        raw = (LOGO_DIR / f"{slug}.svg").read_text(encoding="utf-8")
        inner = raw.split(">", 1)[1].rsplit("</svg>", 1)[0]
        if "</title>" in inner:
            inner = inner.split("</title>", 1)[1]
        symbols.append(f'<symbol id="lg-{slug}" viewBox="0 0 24 24">{inner.strip()}</symbol>')
    return (
        '<svg class="sprite" aria-hidden="true" focusable="false"><defs>'
        + "".join(symbols)
        + "</defs></svg>"
    )


def chart_controls(ident: str) -> str:
    """The filter bar above one chart: marker toggles, name box, reset."""
    boxes = "".join(
        f'<label><input type="checkbox" data-k="{key}" checked> {text}</label>'
        for key, text in (
            ("front", "on frontier"),
            ("off", "off frontier"),
            ("thin", "too thin"),
        )
    )
    return (
        f"<div class=cbar>{boxes}"
        f'<input type="search" class="nf" placeholder="filter by model name" '
        f'aria-label="filter points by model name" id="nf-{ident}">'
        '<button type="button" class="rst">reset view</button>'
        "<span class=chint>wheel to zoom &middot; drag to pan &middot; "
        "double-click to reset &middot; click a point to pin its card</span></div>"
    )


def svg_chart(models: list[Model], group: str, title: str) -> str:
    """One inline SVG scatter: log effective cost against raw capability.

    The panel is live. The page's script zooms and pans the marks layer
    and redraws the two axis layers from `data-geom`, so a decade label
    is recomputed on zoom rather than stretched, and every marker and
    label keeps the size it was drawn at. Nothing is written twice for
    that: a dot moves by its own `cx`/`cy`, and a label, a leader line
    or a logo moves by the `data-a` dot it hangs off.
    """
    points = [m for m in models if group in m.fit and m.eff_cost_in(group) > 0.0]
    if not points:
        return f"<p>No data for {html.escape(group)}.</p>"
    width, height = 1180, 560
    left, right, top, bottom = 66, 26, 44, 58
    ident = slug(group)
    xs = [math.log10(m.eff_cost_in(group)) for m in points]
    ys = [m.fit[group] for m in points]
    x_lo, x_hi = min(xs) - 0.12, max(xs) + 0.12
    y_lo, y_hi = min(ys) - 5, max(ys) + 7

    def px(value: float) -> float:
        return left + (value - x_lo) / (x_hi - x_lo) * (width - left - right)

    def py(value: float) -> float:
        return height - bottom - (value - y_lo) / (y_hi - y_lo) * (height - bottom - top)

    geom = ",".join(
        f"{v:g}" for v in (left, right, top, bottom, width, height, x_lo, x_hi, y_lo, y_hi)
    )
    parts = [
        f'<svg viewBox="0 0 {width} {height}" data-geom="{geom}" '
        f'role="img" aria-label="{html.escape(title)}">',
        f'<defs><clipPath id="clip-{ident}"><rect x="4" y="{top - 22}" '
        f'width="{width - 8}" height="{height - bottom + 4 - (top - 22)}"/></clipPath></defs>',
    ]
    # Two axis layers, gridlines and tick text, written here for a reader
    # with scripting off and rebuilt by the script on every zoom.
    grid: list[str] = []
    ticks: list[str] = []
    decade = math.floor(x_lo)
    while decade <= x_hi:
        x = px(decade)
        # A decade whose gridline falls left of the axis has its tick text
        # clipped by the panel edge, which reads as a stray character.
        if x < left:
            decade += 1
            continue
        grid.append(
            f'<line class="grid" x1="{x:.1f}" y1="{top - 10}" x2="{x:.1f}" y2="{height - bottom}"/>'
        )
        ticks.append(
            f'<text class="tick" x="{x:.1f}" y="{height - bottom + 18}" '
            f'text-anchor="middle">{10**decade:g}x</text>'
        )
        decade += 1
    # Raw capability is a 0-100 scale, so the gridlines are the round numbers of
    # that scale, not five even slices of whatever range this group spans.
    for value in range(0, 101, 20):
        if not y_lo <= value <= y_hi:
            continue
        y = py(value)
        grid.append(
            f'<line class="grid" x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}"/>'
        )
        ticks.append(
            f'<text class="tick" x="{left - 9}" y="{y + 4:.1f}" text-anchor="end">{value}</text>'
        )
    parts.append('<g class="gl">' + "".join(grid) + "</g>")
    tick_layer = '<g class="tk">' + "".join(ticks) + "</g>"

    # The legend spells every marker out; a reader should never have to
    # look up what a ring meant. Its width is measured from the words so
    # a longer wording cannot overflow the panel.
    entries = (
        ("dot front-dot", False, "on frontier"),
        ("dot", False, "off frontier"),
        ("dot thin-dot", False, "too thin for the frontier"),
        ("dot", True, "ring: the thinner the evidence, the heavier"),
    )
    slots = [14.0]
    for _, _, text in entries[:-1]:
        slots.append(slots[-1] + 24.0 + len(text) * 5.85)
    legend_w = slots[-1] + 24.0 + len(entries[-1][2]) * 5.85
    legend_x, legend_y = width - right - legend_w, top - 24
    legend = [
        f'<rect class="legend" x="{legend_x:.1f}" y="{legend_y}" '
        f'width="{legend_w:.1f}" height="22" rx="6"/>'
    ]
    for (klass, ringed, text), offset in zip(entries, slots, strict=True):
        cx = legend_x + offset
        if ringed:
            legend.append(
                f'<circle class="ring" cx="{cx:.1f}" cy="{legend_y + 11}" r="8.5" opacity="0.75"/>'
            )
        legend.append(f'<circle class="{klass}" cx="{cx:.1f}" cy="{legend_y + 11}" r="4.5"/>')
        legend.append(f'<text class="tick" x="{cx + 11:.1f}" y="{legend_y + 15}">{text}</text>')
    blocked = [(legend_x - 4.0, float(legend_y), float(width - right), legend_y + 26.0)]

    # Everything from here to the closing </g> is the layer the script
    # moves, and it is clipped so a panned point cannot escape the panel.
    marks = [f'<g class="mk" clip-path="url(#clip-{ident})">']
    front = pareto_front(points, group)
    if len(front) > 1:
        seats = [(px(math.log10(m.eff_cost_in(group))), py(m.fit[group])) for m in front]
        marks.append(
            '<polyline class="front" points="'
            + " ".join(f"{x:.1f},{y:.1f}" for x, y in seats)
            + '"/>'
        )
        # The frontier line is the thing a reader traces, so no label may
        # sit on it: block it as a chain of small boxes along each segment.
        for (x1, y1), (x2, y2) in itertools.pairwise(seats):
            span = max(abs(x2 - x1), abs(y2 - y1))
            for step in range(int(span // 7) + 1):
                share = step / max(span // 7, 1)
                cx, cy = x1 + (x2 - x1) * share, y1 + (y2 - y1) * share
                blocked.append((cx - 4.0, cy - 4.0, cx + 4.0, cy + 4.0))
    on_front = {m.key for m in front}
    placed_input = [
        (model, px(math.log10(model.eff_cost_in(group))), py(model.fit[group])) for model in points
    ]
    # Rings first, so a heavy ring never sits on top of a neighbour's dot.
    # The ring is how much of the group went unmeasured on that point:
    # it grows and darkens as the evidence coverage falls, and a
    # well-measured point has none at all, so the eye reads evidence as
    # weight. Nothing behind a dot is borrowed, so the ring is a width,
    # not a share of somebody else's number.
    for model, x, y in placed_input:
        unmeasured = 1.0 - model.cover.get(group, 0.0)
        if unmeasured <= 0.08:
            continue
        marks.append(
            f'<circle class="ring" cx="{x:.1f}" cy="{y:.1f}" '
            f'r="{DOT_R + 1.6 + 5.0 * unmeasured:.1f}" '
            f'opacity="{0.18 + 0.62 * unmeasured:.2f}"/>'
        )
    for model, x, y in placed_input:
        if model.key in on_front:
            klass = "dot front-dot"
        elif not model.frontier_ok.get(group, True):
            # Hollow and dashed: a row the frontier was not allowed to
            # run through, so the eye does not read it as a corner the
            # line simply missed.
            klass = "dot thin-dot"
        else:
            klass = "dot"
        value = model.calibrated_intelligence.get(group)
        shown_value = f"{value:.3f}" if value is not None else "-"
        state = ", ".join(model.status(group, on_frontier=model.key in on_front))
        band = model.band.get(group, 0.0)
        counted = f"{model.boards.get(group, 0)} of {model.board_pool.get(group, 0)}"
        cost_note = (
            "solved from same-source ratios"
            if not model.price_only
            else "none published; the effective cost here is the list price"
        )
        tip = (
            f"{model.name} — effective cost {model.eff_cost_in(group):.2f}x reference, "
            f"raw capability {model.fit[group]:.1f} +/-{band:.1f}, "
            f"measured on {counted} boards, "
            f"evidence coverage {model.cover.get(group, 0.0):.2f}"
            + (f", capability per cost {value:.2f}" if value is not None else "")
        )
        # The data attributes are what the hover card reads: every point
        # carries its own numbers, labelled or not, so the card never has
        # to be looked up in the table. The `<title>` stays for a reader
        # with scripting off.
        marks.append(
            f'<circle class="{klass}" cx="{x:.1f}" cy="{y:.1f}" r="{DOT_R:g}" '
            f'data-name="{html.escape(model.name, quote=True)}" '
            f'data-ci="{shown_value}" data-fit="{model.fit[group]:.1f}" '
            f'data-cost="{model.eff_cost_in(group):.2f}x" '
            f'data-measured="{model.cover.get(group, 0.0):.2f} of the group weight" '
            f'data-band="+/-{band:.1f} (standard error of the ability)" '
            f'data-boards="{counted} boards measured at this effort" '
            f'data-costbasis="{html.escape(cost_note, quote=True)}" '
            f'data-state="{html.escape(state, quote=True)}">'
            f"<title>{html.escape(tip)}</title></circle>"
        )
        # The maker's mark, squeezed into the dot and painted to contrast
        # with it. It never takes the mouse, so the circle under it keeps
        # the hover card and the click that pins it.
        logo = vendor_logo(model)
        if logo:
            light = "lg thin-lg" if klass.endswith("thin-dot") else "lg"
            marks.append(
                f'<use class="{light}" href="#lg-{logo}" data-a="{x:.1f},{y:.1f}" '
                f'x="{x - LOGO_SIDE / 2:.1f}" y="{y - LOGO_SIDE / 2:.1f}" '
                f'width="{LOGO_SIDE:g}" height="{LOGO_SIDE:g}"/>'
            )
    bounds = (4.0, float(top - 22), float(width - 4), float(height - bottom + 2))
    # Every dot blocks, labelled or not, so a surviving label never lands
    # on the marker of a model whose own label was dropped.
    blocked += [
        (x - DOT_R - 1.0, y - DOT_R - 1.0, x + DOT_R + 1.0, y + DOT_R + 1.0)
        for _, x, y in placed_input
    ]
    shown = {m.key for m in label_pool(points, on_front, group)}
    eligible_for_label = [item for item in placed_input if item[0].key in shown]
    # The note is written last, once the placement is known, but its box
    # has to block before anything is placed — so the space reserved is
    # the widest the sentence can get, which is when every point is
    # labelled. Above the plot, beside the title: the axis tick row
    # already holds the decade labels and a second line collides there.
    note = (
        "{count} of " + str(len(placed_input)) + " points are labelled; "
        "hover any dot, labelled or not, for its full card"
    )
    blocked.append(
        (left - 4.0, float(top - 20), left + len(note.format(count=len(placed_input))) * 5.4, top)
    )
    placed = place_labels(eligible_for_label, group, bounds, blocked, must=on_front)
    for item in placed:
        # A label pushed out to a far ring is drawn joined to its dot, so
        # a ladder of effort variants stays readable instead of piling
        # five names on one pixel.
        if item.far:
            tip_x = item.x + {"start": -2.0, "end": 2.0, "middle": 0.0}[item.anchor]
            tip_y = item.y - 3.0
            reach = math.hypot(tip_x - item.dot_x, tip_y - item.dot_y)
            share = min(7.0 / reach, 1.0)
            marks.append(
                f'<line class="lead" data-a="{item.dot_x:.1f},{item.dot_y:.1f}" '
                f'x1="{item.dot_x + (tip_x - item.dot_x) * share:.1f}" '
                f'y1="{item.dot_y + (tip_y - item.dot_y) * share:.1f}" '
                f'x2="{tip_x:.1f}" y2="{tip_y:.1f}"/>'
            )
        klass = "lbl" if item.solid else "lbl thin-lbl"
        marks.append(
            f'<text class="{klass}" data-a="{item.dot_x:.1f},{item.dot_y:.1f}" '
            f'x="{item.x:.1f}" y="{item.y:.1f}" '
            f'text-anchor="{item.anchor}">{html.escape(item.text)}</text>'
        )
    marks.append("</g>")
    # Order is the whole trick of a panned chart: gridlines under the
    # marks, and the tick text, the legend, the title and the axis names
    # over them, so a point dragged to the edge slides under the writing
    # rather than through it.
    parts += marks
    parts.append(tick_layer)
    parts += legend
    parts.append(f'<text class="ttl" x="{left}" y="22">{html.escape(title)}</text>')
    if len(placed) < len(placed_input):
        parts.append(
            f'<text class="tick" x="{left}" y="{top - 8}" text-anchor="start">'
            f"{note.format(count=len(placed))}</text>"
        )
    parts.append(
        f'<text class="axis" x="{width / 2:.0f}" y="{height - 14}" '
        'text-anchor="middle">effective cost, log scale '
        "(relative to the reference)</text>"
    )
    parts.append(
        f'<text class="axis" transform="translate(18,{height / 2:.0f}) '
        'rotate(-90)" text-anchor="middle">raw capability</text>'
    )
    parts.append("</svg>")
    return f'<div class=chart data-chart="{ident}">{chart_controls(ident)}{"".join(parts)}</div>'


# --------------------------------------------------------------------
# Evidence. Everything below reports what the ranking was computed FROM:
# which board, at what weight, from whose page, on what date, and what
# the raw number was before it was min-max scaled. A score nobody can
# trace back to a dated page is worth exactly as much as a guess, so the
# page and results/evidence.md carry the whole chain rather than asking
# a reader to take the ladder on trust.
# --------------------------------------------------------------------


@dataclass(slots=True)
class Source:
    """One dated page a number came from."""

    key: str
    title: str
    url: str
    date: str


def source_of(sources: dict[str, Any], key: str) -> Source:
    """Look a `sources:` key up, tolerating one that was never filled in."""
    entry = sources.get(key) or {}
    return Source(
        key=key or "unrecorded",
        title=str(entry.get("title") or key or "unrecorded source"),
        url=str(entry.get("url") or ""),
        date=str(entry.get("date") or "undated"),
    )


def run_source(ratios: dict[str, Any], url: str, date: str, benchmark: str = "") -> Source:
    """One published run as a linkable source.

    A cost-ratio row names its benchmark, which is the most useful thing
    to call it; an effort row names only a URL, so `source_titles:` in
    cost_ratios.yaml gives those a readable name. A URL nobody titled
    still links, under itself — the link is the evidence either way.
    """
    titles = ratios.get("source_titles") or {}
    return Source(
        key=url,
        title=benchmark or str(titles.get(url) or url),
        url=url,
        date=date,
    )


def bench_meta(groups: dict[str, Any], key: str) -> tuple[str, str]:
    """A benchmark's printable name and its one-line "measures" note."""
    entry = (groups.get("benchmark_meta") or {}).get(key) or {}
    label = str(entry.get("label") or key)
    return label, " ".join(str(entry.get("measures") or "").split())


def bench_trust(groups: dict[str, Any], key: str) -> str:
    """The one-line "what would make this board wrong" note, if any."""
    entry = (groups.get("benchmark_meta") or {}).get(key) or {}
    return " ".join(str(entry.get("trust") or "").split())


def style_control(sources: dict[str, Any], keys: list[str]) -> str:
    """How the sources behind one board handled Arena's style control.

    Only an Arena capture records the setting at all, and a board file
    records it per board because Arena publishes some of its category
    tables controlled and some raw. Where several captures fed one board
    and disagreed, the answer is `mixed`, which is a fact about the
    evidence rather than a value to average away.

    A board with no style-control toggle records the key as ``null``,
    and a ``null`` is not a setting: it is the absence of one. It takes
    no part in the answer, so a board whose sources are all ``null``
    reads `not applicable` and a `null` alongside a real `on` does not
    turn that board `mixed`.
    """
    seen = {
        bool(setting)
        for key in keys
        if key
        for setting in [(sources.get(key) or {}).get("style_control")]
        if setting is not None
    }
    if not seen:
        return "not applicable"
    return "on" if seen == {True} else "off" if seen == {False} else "mixed"


def paid_pool(models: list[Model]) -> list[Model]:
    """The models the ranking actually orders: paid, not rejected."""
    return rankable(models)


@dataclass(slots=True)
class BenchEvidence:
    """One benchmark as it feeds one task group."""

    key: str
    label: str
    measures: str
    weight: float
    #: The pillar this board sits in: `preference` or `capability`.
    pillar: str
    covered: list[Model]
    sources: list[tuple[Source, int]]
    #: What would make this board wrong, in plain words.
    trust: str = ""
    #: `on`, `off`, `mixed`, or `not applicable` where no capture
    #: behind the board records the setting at all.
    style: str = ""


def benchmark_evidence(
    models: list[Model], groups: dict[str, Any], sources: dict[str, Any], name: str
) -> list[BenchEvidence]:
    """Every benchmark feeding one group, heaviest weight first.

    The weight is the flattened one the ranker actually multiplies by —
    a third of the group for the board's pillar, split inside it — so the
    column adds to 1.00 and a reader can see what share of a raw-capability
    score each board bought.
    """
    if name == OVERALL or name not in groups["groups"]:
        return []
    weights = group_weights(groups, name)
    pillars = board_pillars(groups)
    ranked = paid_pool(models)
    out: list[BenchEvidence] = []
    for key, weight in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0])):
        covered = sorted((m for m in ranked if key in m.scores), key=lambda m: -m.scores[key])
        tally: dict[str, int] = defaultdict(int)
        for model in covered:
            tally[model.srcs.get(key, "")] += 1
        label, measures = bench_meta(groups, key)
        out.append(
            BenchEvidence(
                key=key,
                label=label,
                measures=measures,
                weight=weight,
                pillar=pillars.get(key, ""),
                covered=covered,
                sources=[
                    (source_of(sources, src), count)
                    for src, count in sorted(tally.items(), key=lambda kv: (-kv[1], kv[0]))
                ],
                trust=bench_trust(groups, key),
                style=style_control(sources, list(tally)),
            )
        )
    return out


def raw_rows(
    evidence: BenchEvidence, name: str, sources: dict[str, Any]
) -> list[tuple[Model, float, float, Source]]:
    """Raw score, the value it normalised to in this group, and its source.

    Both numbers side by side are the point: the median/IQR scaling is
    the step where a board stops being a published figure and starts
    being a contribution to a fit score, and it is the step most worth
    checking.
    """
    return [
        (
            model,
            model.scores[evidence.key],
            model.normed.get(name, {}).get(evidence.key, float("nan")),
            source_of(sources, model.srcs.get(evidence.key, "")),
        )
        for model in evidence.covered
    ]


@dataclass(slots=True)
class RatioBlock:
    """Every pairwise ratio one published run produced."""

    source: Source
    benchmark: str
    rows: list[tuple[str, str, float]]


def ratio_blocks(ratios: dict[str, Any], names_by_id: dict[str, str]) -> list[RatioBlock]:
    """Group the cost ratios by the run that published them.

    A row may only ever relate two models measured on the same tasks in
    the same run, so the run is the natural unit to show them in: seeing
    all of one source's pairs together is how a reader spots that two
    sources disagree about the same pair.
    """
    grouped: dict[tuple[str, str, str], list[tuple[str, str, float]]] = defaultdict(list)
    for row in ratios.get("cost_ratios", []):
        key = (str(row["source"]), str(row.get("benchmark", "")), str(row.get("date", "")))
        grouped[key].append(
            (
                names_by_id.get(row["model_a"], row["model_a"]),
                names_by_id.get(row["model_b"], row["model_b"]),
                float(row["ratio"]),
            )
        )
    blocks = [
        RatioBlock(
            source=run_source(ratios, url, date, benchmark),
            benchmark=benchmark,
            rows=sorted(rows, key=lambda r: r[2]),
        )
        for (url, benchmark, date), rows in grouped.items()
    ]
    return sorted(blocks, key=lambda b: (-len(b.rows), b.source.date, b.benchmark))


@dataclass(slots=True)
class EffortBlock:
    """Effort multipliers from one published run."""

    source: Source
    rows: list[tuple[str, str, str, float]]


def effort_blocks(ratios: dict[str, Any], names_by_id: dict[str, str]) -> list[EffortBlock]:
    """Effort ratios grouped by source; a cost dial, never a value one."""
    grouped: dict[tuple[str, str], list[tuple[str, str, str, float]]] = defaultdict(list)
    for row in ratios.get("effort_ratios", []):
        key = (str(row["source"]), str(row.get("date", "")))
        grouped[key].append(
            (
                names_by_id.get(row["model"], row["model"]),
                str(row["effort_a"]),
                str(row["effort_b"]),
                float(row["ratio"]),
            )
        )
    blocks = [
        EffortBlock(
            source=run_source(ratios, url, date),
            rows=sorted(rows),
        )
        for (url, date), rows in grouped.items()
    ]
    return sorted(blocks, key=lambda b: (-len(b.rows), b.source.date))


@dataclass(slots=True)
class CostEvidence:
    """How one model's relative cost per task was arrived at."""

    model: Model
    observations: list[tuple[str, float, str, Source]]
    implied: list[float]

    @property
    def geometric_mean(self) -> float | None:
        """The plain geometric mean of what each source implies alone."""
        if not self.implied:
            return None
        return math.exp(sum(math.log(v) for v in self.implied) / len(self.implied))

    @property
    def span(self) -> tuple[float, float] | None:
        """Lowest and highest cost these rows imply, read one at a time."""
        if not self.implied:
            return None
        return min(self.implied), max(self.implied)

    @property
    def spread(self) -> float | None:
        """Highest implied cost over lowest — the cross-source noise."""
        if len(self.implied) < 2:
            return None
        return max(self.implied) / min(self.implied)


def cost_evidence(
    models: list[Model], ratios: dict[str, Any], rel_costs: dict[str, float]
) -> list[CostEvidence]:
    """Per model, every ratio row it appears in and what each one implies.

    The published ranking solves the whole ratio graph at once, which is
    right and is also opaque: the fitted number matches no single source.
    So each row is also read on its own — this model's cost against the
    other end's *solved* cost — and the geometric mean of those is shown
    beside the fit. Where the two differ, the graph is telling you the
    sources disagree, and the spread says by how much.
    """
    gathered: dict[str, list[tuple[str, float, str, Source]]] = defaultdict(list)
    for row in ratios.get("cost_ratios", []):
        ratio = float(row["ratio"])
        if ratio <= 0.0:
            continue
        source = run_source(
            ratios,
            str(row["source"]),
            str(row.get("date", "")),
            str(row.get("benchmark", "")),
        )
        a, b = str(row["model_a"]), str(row["model_b"])
        gathered[a].append((b, ratio, "this / other", source))
        gathered[b].append((a, 1.0 / ratio, "this / other", source))
    out: list[CostEvidence] = []
    for model in sorted(base_variant(paid_pool(models)), key=lambda m: m.eff_cost):
        rows = gathered.get(model.id, [])
        implied = [ratio * rel_costs[other] for other, ratio, _, _ in rows if other in rel_costs]
        out.append(CostEvidence(model=model, observations=rows, implied=implied))
    return out


def noise_floor(evidence: list[CostEvidence]) -> tuple[float | None, float | None, int]:
    """Median and worst cross-source spread, and how many models have one.

    Two runs that priced the same pair rarely agree. Whatever they
    disagree by is the floor under every cost comparison on this page: a
    gap smaller than it is not evidence of anything.
    """
    spreads = sorted(s for s in (e.spread for e in evidence) if s is not None)
    if not spreads:
        return None, None, 0
    middle = spreads[len(spreads) // 2]
    return middle, spreads[-1], len(spreads)


def price_rows(models: list[Model], sources: dict[str, Any]) -> list[tuple[Model, Source]]:
    """Every paid list price with the catalogue page it was read from."""
    return [
        (model, source_of(sources, model.price_src))
        for model in sorted(base_variant(paid_pool(models)), key=lambda m: m.blended)
    ]


def drilldown_boards(
    model: Model, groups: dict[str, Any], names: list[str]
) -> list[tuple[str, str, str, float, float, float]]:
    """Every (group, benchmark) pair that fed one model's raw capability."""
    rows = []
    for name in names:
        if name == OVERALL or name not in groups["groups"]:
            continue
        weights = group_weights(groups, name)
        for key, weight in sorted(weights.items(), key=lambda kv: (-kv[1], kv[0])):
            if key not in model.scores:
                continue
            label, _ = bench_meta(groups, key)
            rows.append(
                (
                    name,
                    key,
                    label,
                    model.scores[key],
                    model.normed.get(name, {}).get(key, float("nan")),
                    weight,
                )
            )
    return rows


def drilldown_ratios(
    model: Model, ratios: dict[str, Any], names_by_id: dict[str, str]
) -> list[tuple[str, str, float, str, Source]]:
    """Every cost-ratio row this model is one end of, either way round."""
    rows = []
    for row in ratios.get("cost_ratios", []):
        a, b = str(row["model_a"]), str(row["model_b"])
        if model.id not in (a, b):
            continue
        other = b if model.id == a else a
        source = run_source(
            ratios,
            str(row["source"]),
            str(row.get("date", "")),
            str(row.get("benchmark", "")),
        )
        rows.append(
            (
                "this / other" if model.id == a else "other / this",
                names_by_id.get(other, other),
                float(row["ratio"]),
                str(row.get("benchmark", "")),
                source,
            )
        )
    return rows


#: How many rows a soft-spot line will name before it gives a count
#: instead. A caveat nobody finishes reading is not a caveat.
WEAK_SPOT_NAMES = 15


def weak_spots(
    models: list[Model], groups: dict[str, Any], ratios: dict[str, Any], names: list[str]
) -> list[str]:
    """The known soft spots, read off the data rather than remembered.

    Each line here is a fact the YAML already states — a group's own
    `pending:` note, the rows no board of a pillar reaches, the short
    list of models anyone published effort multipliers for. Restating
    them by hand is how a caveat outlives the thing it was about.
    """
    out: list[str] = []
    for name in names:
        spec = groups["groups"].get(name)
        if spec and spec.get("pending"):
            out.append(f"{name}: " + " ".join(spec["pending"].split()))
    pillars = board_pillars(groups)
    for pillar in PILLARS:
        keys = {key for key, held in pillars.items() if held == pillar}
        blind = [m.name for m in paid_pool(models) if not keys & set(m.scores)]
        if not blind:
            continue
        named = ", ".join(blind) if len(blind) <= WEAK_SPOT_NAMES else f"{len(blind)} rows"
        out.append(
            f"On no {pillar} board at all, so that pillar is unmeasured for "
            "them rather than zero and what they are scored on is the pillar "
            f"that remains: {named}."
        )
    names_by_id = {m.id: m.base_name for m in models}
    tuned = sorted(
        {names_by_id.get(r["model"], r["model"]) for r in ratios.get("effort_ratios", [])}
    )
    if tuned:
        out.append(
            "Effort multipliers were published for these models only, so effort "
            "is priced for them and unpriced everywhere else: " + ", ".join(tuned) + "."
        )
    return out


def html_table(
    header: list[str], rows: list[list[str]], *, cls: str = "", sorted_col: str = ""
) -> str:
    """One HTML table from plain string cells.

    `sorted_col` is the column the rows already arrive sorted by, as
    `index:desc` — the page marks that header so the arrow a reader sees
    is the order they are actually looking at, and one click flips it.
    """
    head = "".join(f"<th>{html.escape(c)}</th>" for c in header)
    body = "".join(
        "<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    attrs = f' class="{cls}"' if cls else ""
    attrs += f' data-sorted="{sorted_col}"' if sorted_col else ""
    table = f"<table{attrs}><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
    # A table whose prose columns need more room than the section is wide
    # grows past width:100% (auto layout treats it as a floor, not a cap);
    # the wrapper turns that overflow into a horizontal scrollbar on the
    # table alone instead of letting it clip or blow out the section.
    return f'<div class="table-wrap">{table}</div>'


def slug(name: str) -> str:
    """A stable anchor id for one section title."""
    return "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")


def anchored(block: str, ident: str) -> str:
    """Give a rendered `<section>` an id, so the contents list can reach it."""
    return block.replace("<section>", f"<section id={ident}>", 1)


def toc_html(entries: list[tuple[str, str, list[tuple[str, str]]]]) -> str:
    """The sticky contents list: one link per section, sub-links indented.

    The page is long by design — every number on it is meant to be
    traceable — so it needs a way back. The list is sticky, the section
    the reader is in is highlighted, and nothing here needs the page to
    be scrolled to be used.
    """
    items = []
    for ident, title, subs in entries:
        items.append(f'<li><a href="#{ident}">{html.escape(title)}</a></li>')
        items += [
            f'<li class=sub><a href="#{sub_id}">{html.escape(sub_title)}</a></li>'
            for sub_id, sub_title in subs
        ]
    return (
        '<nav id=toc aria-label="Contents"><p class=toc-h>On this page</p>'
        "<ul>" + "".join(items) + "</ul></nav>"
    )


GROUP_TABLE_HEADER = [
    "model",
    "capability per cost",
    "raw capability (0-100)",
    *PILLARS,
    "effective cost (x reference)",
    "evidence coverage",
    "measured boards",
    "ability band",
    "status",
]


def group_table_html(models: list[Model], group: str, front_ids: set[str]) -> str:
    """One group table, in the page's column order.

    The rows arrive frontier first and then by raw capability,
    descending, which is what `sorted_col` tells the page to mark.
    """
    return html_table(
        GROUP_TABLE_HEADER,
        [
            [r[0], r[1], r[2], *r[6:-2], r[3], r[4], r[-2], r[-1], r[5]]
            for r in rows_for(models, group, front_ids)
        ],
        cls="group",
        sorted_col="2:desc",
    )


def link(source: Source) -> str:
    """One source as a link, or as plain text when no URL was recorded."""
    title = html.escape(source.title)
    if not source.url:
        return title
    return f'<a href="{html.escape(source.url, quote=True)}">{title}</a>'


#: How many source pages one board names before the tail is counted.
#: Four fits the column; a dozen turns the cell into a page of links.
BENCH_SOURCE_LIMIT = 4


def captured_span(dates: list[str]) -> str:
    """One capture date, or the range several captures span.

    A page that never published a date is counted rather than folded
    into the range: "undated" is not a date, and a range that pretends
    otherwise is the kind of small lie this file exists to avoid.
    """
    seen = sorted({date for date in dates if date and date != "undated"})
    blank = sum(1 for date in dates if not date or date == "undated")
    if not seen:
        return "undated"
    span = seen[0] if len(seen) == 1 else f"{seen[0]} to {seen[-1]}"
    return f"{span}, {plural(blank, 'capture')} undated" if blank else span


BENCH_USED_HEADER = [
    "board",
    "pillar",
    "weight",
    "what it measures",
    "source",
    "captured",
    "style control",
    "models covered",
    "what would make it wrong",
]


def benchmarks_used_html(
    models: list[Model], groups: dict[str, Any], sources: dict[str, Any], name: str
) -> str:
    """The "Benchmarks used" block that sits under one group's chart.

    Everything a reader needs to argue with a point on the chart without
    scrolling anywhere: which boards bought this group's raw capability, at
    what weight, from which dated page, with Arena's style control on or
    off, over how much of the pool, and what would make each board
    wrong. The last column is the one that keeps the chart honest.
    """
    ranked = paid_pool(models)
    evidence = benchmark_evidence(models, groups, sources, name)
    anchor = f"boards-{slug(name)}"
    if not evidence:
        return (
            f'<h3 id="{anchor}">Benchmarks used</h3><p class=note>This group has no boards '
            "of its own: its raw capability is the mean of every other group's, so its evidence "
            "is theirs. The benchmarks-used table of each group above applies unchanged.</p>"
        )
    table = html_table(
        BENCH_USED_HEADER,
        [
            [
                item.label,
                item.pillar or "-",
                f"{item.weight:.3f}",
                item.measures,
                "",
                captured_span([src.date for src, _ in item.sources]),
                item.style,
                f"{len(item.covered)} of {len(ranked)}",
                item.trust or "-",
            ]
            for item in evidence
        ],
        cls="bench",
        sorted_col="2:desc",
    )
    # The source column holds links, which html_table escapes, so it is
    # filled in afterwards rather than teaching the table about markup.
    for item in evidence:
        # A board read from a dozen model pages would otherwise turn one
        # cell into a column of links: the widest captures are named and
        # the tail is counted, and the Evidence block below still lists
        # every one of them against the model it covered.
        shown = item.sources[:BENCH_SOURCE_LIMIT]
        rest = sum(count for _, count in item.sources[BENCH_SOURCE_LIMIT:])
        cell = "; ".join(f"{link(src)} ({plural(count, 'model')})" for src, count in shown)
        if rest:
            others = len(item.sources) - len(shown)
            cell += f"; and {plural(others, 'further page')} ({plural(rest, 'model')})"
        table = table.replace("<td></td>", f"<td>{cell}</td>", 1)
    return (
        f'<h3 id="{anchor}">Benchmarks used</h3>'
        "<p class=note>Weights are the flattened ones the ranker multiplies by, so the "
        "column sums to 1.000. <strong>Models covered</strong> counts the paid variants "
        "carrying a score on that board, out of every paid variant ranked. "
        "<strong>Style control</strong> is Arena's adjustment for length and formatting "
        "habit, and it is a property of the capture, not of the board.</p>"
        "<p class=note>Across those flattened weights the pillars carry "
        f"<strong>{html.escape(pillar_share_text(groups, name))}</strong> — equal "
        "halves by construction, with each pillar's boards sharing its half "
        "equally unless the group says otherwise.</p>" + table
    )


def group_evidence_html(
    models: list[Model], groups: dict[str, Any], sources: dict[str, Any], name: str
) -> str:
    """The Evidence block under one group: its boards, then every score."""
    ranked = paid_pool(models)
    evidence = benchmark_evidence(models, groups, sources, name)
    if not evidence:
        return ""
    summary = html_table(
        ["benchmark", "what it measures", "pillar", "weight", "models covered", "sources"],
        [
            [
                item.label,
                item.measures,
                item.pillar,
                f"{item.weight:.3f}",
                f"{len(item.covered)} of {len(ranked)}",
                "",
            ]
            for item in evidence
        ],
    )
    # The source column holds links, which html_table escapes, so it is
    # filled in afterwards rather than teaching the table about markup.
    for item in evidence:
        cell = "; ".join(
            f"{link(src)} ({src.date}, {count} model{'s' if count != 1 else ''})"
            for src, count in item.sources
        )
        summary = summary.replace("<td></td>", f"<td>{cell}</td>", 1)

    tables = []
    for item in evidence:
        rows = raw_rows(item, name, sources)
        body = "".join(
            "<tr>"
            f"<td>{html.escape(model.name)}</td>"
            f"<td>{raw:g}</td>"
            f"<td>{norm:.1f}</td>"
            f"<td>{link(src)}</td>"
            f"<td>{html.escape(src.date)}</td>"
            "</tr>"
            for model, raw, norm, src in rows
        )
        tables.append(
            f"<h4>{html.escape(item.label)} — raw scores, and what they "
            f"normalise to here</h4>"
            f"<p class=note>{html.escape(item.measures)} Weight {item.weight:.3f} "
            f"of this group's raw capability.</p>"
            "<table><thead><tr><th>model</th><th>raw score</th>"
            "<th>normalised (0-100)</th><th>source</th><th>date</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
        )
    return (
        "<details class=evidence><summary>Evidence — the benchmarks behind "
        f"{html.escape(name)}, and every raw score</summary>"
        "<p class=note>Weights are the flattened ones the ranker multiplies by, "
        "so the column sums to 1.000. Each board is scaled to 0-100 by its own "
        "median and inter-quartile range over every plotted variant, then "
        "weighted; the raw tables below show both ends of that step.</p>"
        + summary
        + "".join(tables)
        + "</details>"
    )


def plural(count: int, word: str) -> str:
    """`1 run`, `3 runs` — the small courtesy a generated table owes."""
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def cost_row(item: CostEvidence) -> list[str]:
    """One model's line in the cost-per-task summary."""
    if not item.observations:
        gap = item.model.cost_gap
        return [
            item.model.name,
            "none",
            "-",
            f"{item.model.rel_cost:.2f}x" if item.model.rel_cost is not None else "-",
            "no cost-per-task data at this reasoning effort"
            if gap == "effort"
            else "price-only, no cost-per-task data",
        ]
    runs = len({obs[3].url for obs in item.observations})
    span = item.span
    spread = item.spread
    return [
        item.model.name,
        f"{plural(runs, 'run')}, {plural(len(item.observations), 'pair')}",
        f"{span[0]:.2f}x to {span[1]:.2f}x" if span else "-",
        f"{item.model.rel_cost:.2f}x" if item.model.rel_cost is not None else "-",
        f"{spread:.2f}x" if spread is not None else "one source only",
    ]


def cost_evidence_html(
    models: list[Model],
    ratios: dict[str, Any],
    rel_costs: dict[str, float],
    reference: str,
) -> str:
    """The cost-per-task section: every ratio, then every model's chain."""
    names_by_id = {m.id: m.base_name for m in models}
    blocks = []
    for block in ratio_blocks(ratios, names_by_id):
        rows = "".join(
            f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{ratio:g}</td></tr>"
            for a, b, ratio in block.rows
        )
        blocks.append(
            f"<h4>{link(block.source)} <span class=when>{html.escape(block.source.date)}"
            "</span></h4>"
            "<table><thead><tr><th>model a</th><th>model b</th>"
            "<th>ratio (cost a / cost b)</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    efforts = []
    for block in effort_blocks(ratios, names_by_id):
        rows = "".join(
            f"<tr><td>{html.escape(model)}</td><td>{a}</td><td>{b}</td><td>{ratio:g}</td></tr>"
            for model, a, b, ratio in block.rows
        )
        efforts.append(
            f"<h4>{link(block.source)} <span class=when>{html.escape(block.source.date)}"
            "</span></h4>"
            "<table><thead><tr><th>model</th><th>effort a</th><th>effort b</th>"
            "<th>ratio (cost a / cost b)</th></tr></thead>"
            f"<tbody>{rows}</tbody></table>"
        )
    evidence = cost_evidence(models, ratios, rel_costs)
    per_model = html_table(
        [
            "model",
            "priced through",
            "what those rows imply, one at a time",
            "fitted relative cost per task",
            "cross-source spread",
        ],
        [cost_row(item) for item in evidence],
    )
    middle, worst, counted = noise_floor(evidence)
    floor = (
        f"Across the {counted} models two or more runs both priced, the same pair "
        f"comes out a median of {middle:.2f}x apart and at worst {worst:.2f}x apart. "
        "That is the noise floor under this whole axis: a cost gap smaller than it "
        "is not evidence of anything."
        if middle is not None and worst is not None
        else "No model is priced by two sources, so there is nothing to cross-check."
    )
    return (
        "<section><h2>Cost per task evidence</h2>"
        "<p class=note>A ratio row may only relate two models measured on the same "
        "tasks in the same published run, so nothing here crosses sources. The "
        "chaining happens in the ranker, which solves the whole graph at once in "
        f"log space with <code>{html.escape(reference)}</code> pinned at 1.00 — which "
        "is why a fitted number matches no single source exactly.</p>"
        f"<p class=note>{html.escape(floor)}</p>"
        "<h3>Every pairwise ratio, grouped by the run that published it</h3>"
        + "".join(blocks)
        + "<h3>Effort multipliers</h3>"
        "<p class=note>Effort is a cost dial, not a value one: one harness has "
        "Opus 5 solving fewer tasks at xhigh than at high while costing more. These "
        "price the dial and never move a raw-capability score. <strong>They exist for these "
        "models only.</strong> Every other model split by effort has no cost per "
        "task at any effort but its default: the default's cost is not that "
        "effort's cost and is not borrowed for it. Those rows say <em>no "
        "cost-per-task data at this reasoning effort</em> in their status and are "
        "placed on their list price alone.</p>" + "".join(efforts) + "<h3>What each "
        "model's relative cost per task rests on</h3>"
        "<p class=note>Every ratio row is also read on its own — this model against "
        "the other end's solved cost — and the range is what those readings span. "
        "The fit lands on their geometric mean by construction, so the range, not "
        "the fit, is where a disagreement between runs shows up.</p>" + per_model + "</section>"
    )


def price_evidence_html(
    models: list[Model], sources: dict[str, Any], groups: dict[str, Any]
) -> str:
    """The list-price section: what each model costs and where that came from."""
    weight, basis = price_blend(groups)
    rows = "".join(
        "<tr>"
        f"<td>{html.escape(model.name)}</td>"
        f"<td>{model.price_in:g}</td>"
        f"<td>{model.price_out:g}</td>"
        f"<td>{model.blended:.3f}</td>"
        f"<td>{model.rel_price:.2f}</td>"
        + (
            "<td>none</td>"
            if not model.discount
            else "<td>"
            + html.escape(
                f"{model.discount.get('input', '?')}/{model.discount.get('output', '?')} "
                f"— {' '.join(str(model.discount.get('note', '')).split())}"
            )
            + "</td>"
        )
        + f"<td>{link(src)}</td><td>{html.escape(src.date)}</td></tr>"
        for model, src in price_rows(models, sources)
    )
    return (
        "<section><h2>Price evidence</h2>"
        "<p class=note>List prices in $/M tokens, discounts deliberately ignored: a "
        "launch promotion or one cheap endpoint lapses, and the ladder should not "
        "reshuffle when it does. The blended proxy averages the input price and the "
        f"output price with output counted {weight:g} times as heavily — agentic "
        "traffic is output-dominated once prompt caching works. That weighting is "
        f"<strong>{html.escape(basis)}</strong>: nothing here measures it, and it is "
        f"one number, <code>price_blend:</code> in {html.escape(SKILL_REL)}"
        "/data/task_groups.yaml, to change. A cheaper route, where one exists, is "
        "recorded and not scored.</p>"
        "<table><thead><tr><th>model</th><th>input $/M</th><th>output $/M</th>"
        "<th>blended proxy $/M</th><th>relative price</th><th>discount route</th>"
        "<th>source</th><th>date</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def model_drilldown_html(
    models: list[Model],
    groups: dict[str, Any],
    sources: dict[str, Any],
    ratios: dict[str, Any],
    names: list[str],
) -> str:
    """One collapsible block per model: every number that fed it."""
    names_by_id = {m.id: m.base_name for m in models}
    order = sorted(models, key=lambda m: (bool(m.rejected), m.free, -m.fit.get(OVERALL, 0.0)))
    blocks = []
    for model in order:
        head = [f"<p class=note>OpenRouter id <code>{html.escape(model.id)}</code>"]
        if model.rung:
            head.append(f", rung <code>{html.escape(str(model.rung))}</code>")
        head.append(".</p>")
        parts = ["".join(head)]
        if model.rejected:
            parts.append(
                "<p class=note><strong>Rejected"
                + (f" — {html.escape(model.rejected_short)}" if model.rejected_short else "")
                + ".</strong> "
                + html.escape(" ".join(model.rejected.split()))
                + " It keeps its row in the data so a future run does not "
                "re-litigate it, and enters no ranking table and no frontier.</p>"
            )
        if model.free:
            parts.append(
                "<p class=note>A <code>:free</code> listing: throttled, temporary and "
                "never a price. "
                + (
                    "No paid listing exists, so it has no list price at all."
                    if model.free_only
                    else f"Priced through its paid listing "
                    f"<code>{html.escape(str(model.paid_listing))}</code>."
                )
                + "</p>"
            )
        elif not model.rejected:
            parts.append(
                "<p class=note>Blended list price "
                f"${model.blended:.3f}/M, {model.rel_price:.2f}x the reference; "
                + (
                    "no cost per task at this reasoning effort — nobody "
                    "published a multiplier for it, and the default "
                    "effort's cost is not borrowed for it"
                    if model.cost_gap == "effort"
                    else "no cost per task: no same-source ratio reaches "
                    "it, so it is absent from the cost-per-task third "
                    "rather than given a guessed one"
                    if model.rel_cost is None
                    else f"relative cost per task {model.rel_cost:.2f}x"
                )
                + f"; effective cost {model.eff_cost:.2f}x.</p>"
            )
            status = html_table(
                [
                    "group",
                    "capability per cost",
                    "raw capability",
                    "measured boards",
                    "evidence coverage",
                    "ability band",
                    "status",
                ],
                [
                    [
                        name,
                        f"{model.calibrated_intelligence[name]:.2f}"
                        if name in model.calibrated_intelligence
                        else "-",
                        f"{model.fit[name]:.1f}" if name in model.fit else "-",
                        f"{model.boards.get(name, 0)} of {model.board_pool.get(name, 0)}",
                        f"{model.cover.get(name, 0.0):.2f}",
                        f"+/-{model.band[name]:.1f}" if name in model.band else "-",
                        "; ".join(model.status(name)),
                    ]
                    for name in names
                    if name in model.fit
                ],
            )
            parts.append(status)
            short = [
                name for name in names if name not in model.fit and model.boards.get(name, 0) > 0
            ]
            if short:
                parts.append(
                    "<p class=note>Not ranked in "
                    + html.escape(", ".join(short))
                    + f": measured on fewer than {MIN_MEASURED_BOARDS} of "
                    "those groups' boards, and a score for it would have "
                    "to be filled in from somewhere it was never run.</p>"
                )
        board_rows = drilldown_boards(model, groups, names)
        if board_rows:
            body = "".join(
                f"<tr><td>{html.escape(label)}</td><td>{html.escape(group)}</td>"
                f"<td>{raw:g}</td><td>{norm:.1f}</td><td>{weight:.3f}</td>"
                f"<td>{link(source_of(sources, model.srcs.get(key, '')))}</td></tr>"
                for group, key, label, raw, norm, weight in board_rows
            )
            parts.append(
                "<h4>Every benchmark number that fed this model</h4>"
                "<table><thead><tr><th>benchmark</th><th>group</th><th>raw score</th>"
                "<th>normalised (0-100)</th><th>weight in that group</th>"
                "<th>source</th></tr></thead>"
                f"<tbody>{body}</tbody></table>"
            )
        elif not model.scores:
            parts.append("<p class=note>No benchmark score is recorded for it at all.</p>")
        ratio_rows = drilldown_ratios(model, ratios, names_by_id)
        if ratio_rows:
            body = "".join(
                f"<tr><td>{html.escape(direction)}</td><td>{html.escape(other)}</td>"
                f"<td>{ratio:g}</td><td>{html.escape(benchmark)}</td>"
                f"<td>{link(source)}</td><td>{html.escape(source.date)}</td></tr>"
                for direction, other, ratio, benchmark, source in ratio_rows
            )
            parts.append(
                "<h4>Cost ratios this model appears in</h4>"
                "<table><thead><tr><th>direction</th><th>other model</th><th>ratio</th>"
                "<th>benchmark</th><th>source</th><th>date</th></tr></thead>"
                f"<tbody>{body}</tbody></table>"
            )
        else:
            parts.append("<p class=note>No same-source cost ratio reaches this model.</p>")
        blocks.append(
            f"<details class=evidence><summary>{html.escape(model.name)}"
            + ("  — rejected" if model.rejected else "")
            + ("  — free listing" if model.free else "")
            + "</summary>"
            + "".join(parts)
            + "</details>"
        )
    return (
        '<section id="drilldown"><h2>Per-model drilldown</h2>'
        "<p class=note>Open a model to see every number behind it: each benchmark "
        "with its raw score, what that normalised to in each group and the weight it "
        "carried there, every cost ratio it is one end of, and — where it has one — "
        "the reason it was rejected.</p>" + "".join(blocks) + "</section>"
    )


def how_to_judge_html(
    models: list[Model],
    groups: dict[str, Any],
    ratios: dict[str, Any],
    names: list[str],
    evidence: list[CostEvidence],
) -> str:
    """The paragraph that tells a reader what they are looking at."""
    weights = groups["calibrated_intelligence_weights"]
    middle, worst, counted = noise_floor(evidence)
    floor = (
        f"Two runs that priced the same pair land a median of {middle:.2f}x apart "
        f"(worst {worst:.2f}x, across {counted} models). Treat that as the noise "
        "floor: a cost difference smaller than it means nothing."
        if middle is not None and worst is not None
        else "No pair is priced twice, so there is no cross-check on the cost axis."
    )
    spots = "".join(
        f"<li>{html.escape(line)}</li>" for line in weak_spots(models, groups, ratios, names)
    )
    return (
        "<details id=judge><summary>How to judge this</summary>"
        "<p><strong>Capability per cost</strong> is the ranking key, and it is the mean "
        "of three equal thirds, each min-max scaled over the models present: "
        f"<strong>list-price cheapness</strong> ({weights['price_cheapness']:.4f}), "
        "<strong>cost-per-task cheapness</strong> "
        f"({weights['cost_per_task_cheapness']:.4f}) and <strong>raw capability</strong> "
        f"({weights['task_fit']:.4f}). A model has to earn its place on all three; "
        "no single axis can carry it. The name is a name, not a sum you can do: "
        "the three thirds are averaged, never divided one by another. The two cost thirds are scaled in log space, "
        "because price spans three orders of magnitude here and a linear scale would "
        "flatten everything under a dollar into one clump.</p>"
        "<p><strong>Nothing here is filled in.</strong> A variant is scored on "
        "the boards it was itself measured on at its own reasoning effort, and on "
        "no others: no board is carried over from another effort, another model or "
        "a ratio, and a variant no same-source cost ratio reaches has no cost per "
        "task at all rather than a guessed one. Its capability per cost is then the "
        "two thirds it has, renormalised, and its row says "
        "<em>price-only, no cost-per-task data</em>.</p>"
        "<p><strong>The scores come from one fit per group</strong>, over exactly "
        "the cells that exist. Every board is put on a 0-100 scale by its own "
        "median and inter-quartile range, so a board the pool is near-flat on "
        "uses about a third of the scale rather than being stretched across all "
        "of it. Then one "
        "least-squares fit reads every score in the group at once as two numbers "
        "added together: a level for the board and an ability for the variant, "
        "each cell weighted by its board's weight. The board level absorbs how "
        "hard or how generous a board is; the <strong>ability</strong> that is "
        "left is the raw capability printed here. Two variants that share "
        "boards are compared through those boards; two that do not are compared "
        "through the chain of variants connecting them. That is why a model "
        "measured on the easy half of a group no longer outranks one measured on "
        "the hard half, and why nothing had to be invented to get there.</p>"
        "<p><strong>Efforts of one model are placed against each other.</strong> "
        "The fit has a level per board and an ability per row and no term for "
        "the two together, so a weakness the whole model shares on boards only "
        "one of its efforts was run on lands on that effort alone. So the "
        "best-measured effort of a model keeps the fit's ability, and each "
        "other effort is placed at that ability plus the weighted mean gap "
        "between the two on the boards both were measured on — above it where "
        f"it beats it there. Under {MIN_SIBLING_SHARED} shared boards the row "
        "keeps the fit's own answer and says so.</p>"
        "<p><strong>Thin rows are named, not scored.</strong> A variant measured on "
        f"fewer than {MIN_MEASURED_BOARDS} of a group's boards is left out of that "
        "group's fit, chart and table, and listed by name in the least-measured "
        "fold under the group instead. What a row does carry is two columns: "
        "<strong>measured boards</strong>, how many of the group's boards it sits "
        "on, and <strong>evidence coverage</strong>, the share of the group's "
        "benchmark weight those boards are. The <strong>ability band</strong> is "
        "the standard error the fit itself puts on that row, so a row on three "
        "boards carries a visibly wider band than one on fifteen, and the ring "
        "around a dot is the weight the row was <em>not</em> measured on.</p>"
        "<p><strong>Read a sparse row as optimistic.</strong> Which boards a lab "
        "publishes is not a coin toss: a model is entered where it does well, so "
        "across this catalogue a row's coverage and its score rise together. The "
        "fit cannot correct for that — the missing cells are missing — so it is "
        "left visible instead: a row on three boards with a wide band and a heavy "
        "ring is the page saying the number is the best of what was published, not "
        "the average of what was run.</p>"
        "<p><strong>A thin row is scored, but it may not define a "
        "frontier.</strong> The frontier is the one thing on this page a reader "
        "takes at face value, and a row on a quarter of a group's weight should not "
        "hold its cheap end however well that quarter went. So a row also has to "
        "carry enough of the group's weight to be on it. One that does not says "
        "<em>too thin for the frontier</em> in its status, is drawn as a hollow "
        "dashed dot, and is listed in the least-measured fold under its group. "
        "and on enough boards of its own — two bars, both read off what was "
        "run at this row's own reasoning effort. A row placed against another "
        "effort of the same model inherits neither: its number leans on its "
        "anchor, which is exactly why it may not draw the line in its anchor's "
        "place, so an anchor can sit on a frontier its own placed siblings are "
        "held off. The status of a barred row names the bar it fell under. "
        "Where the two bars sit is two numbers, "
        f"<code>shrinkage:</code> in {html.escape(SKILL_REL)}"
        "/data/task_groups.yaml.</p>"
        "<p>The <strong>two pillars</strong> — <em>preference</em>, blind "
        "human pairwise votes on Arena, and <em>capability</em>, Artificial "
        "Analysis' re-run fixed task sets — are "
        "fitted separately and averaged, so each carries half of every group "
        "however many boards it holds — the alternative, one flat fit over "
        "every cell, quietly hands the ranking to whichever pillar published "
        "the most numbers. A pillar column is filled in wherever the row has "
        "one measured board of it; where it has none the column reads "
        "<code>-</code>, the row says <em>pillar missing</em>, and the raw "
        "capability beside it is the pillar that remains. A row "
        "measured in fewer than two pillars is not ranked at all: one kind of "
        "evidence is a reading, not a verdict.</p>"
        + glossary_html("Every column on this page, in plain words:", COLUMN_TERMS)
        + glossary_html("Every status a row can carry:", STATUS_TERMS)
        + "<p><strong>Where this is weakest</strong>, in the data's own words:</p>"
        f"<ul class=spots>{spots}<li>{html.escape(floor)}</li></ul>"
        "<p class=note>Every claim above is recomputed from "
        "<code>data/*.yaml</code> on each run. The evidence blocks under each group, "
        "and the drilldown at the foot of the page, carry the raw numbers and the "
        "dated pages they came from.</p></details>"
    )


#: The whole page style. It lives out here rather than inside the
#: template so the braces are CSS braces: an f-string would need every
#: one of them doubled, which is a rule a later edit will forget.
PAGE_CSS = """\
:root { color-scheme: light; --ink:#16181d; --mute:#6b7280;
  --line:#dfe3ea; --accent:#1d6fd4; --front:#b8410f; --thin:#9aa3b2; }
* { box-sizing: border-box; }
body { margin:0 auto; padding:28px 22px 64px; background:#fbfbfd;
  max-width:1660px; color:var(--ink);
  font:15px/1.55 ui-sans-serif,system-ui,sans-serif;
  display:grid; gap:26px; grid-template-columns:236px minmax(0,1fr); }
main { max-width:1340px; min-width:0; }
nav#toc { position:sticky; top:20px; align-self:start; font-size:13px;
  max-height:calc(100vh - 40px); overflow:auto; padding-bottom:8px; }
nav#toc p.toc-h { margin:0 0 8px 10px; font-size:11px; font-weight:700;
  letter-spacing:.08em; text-transform:uppercase; color:var(--mute); }
nav#toc ul { list-style:none; margin:0; padding:0; }
nav#toc a { display:block; padding:4px 10px; color:var(--mute);
  text-decoration:none; border-left:2px solid transparent;
  border-radius:0 7px 7px 0; }
nav#toc a:hover { background:#eef1f6; color:var(--ink); }
nav#toc a.here { background:#e9f1fd; border-left-color:var(--accent);
  color:var(--ink); font-weight:600; }
nav#toc li.sub a { padding-left:24px; font-size:12px; }
h1 { font-size:26px; margin:0 0 6px; letter-spacing:-.02em; }
h2 { font-size:19px; margin:0 0 4px; letter-spacing:-.01em; }
p.lede, p.note { color:var(--mute); margin:0 0 18px; max-width:82ch; }
code { font-size:.9em; }
section { background:#fff; border:1px solid var(--line); border-radius:12px;
  padding:20px; margin:22px 0; scroll-margin-top:16px; }
svg { width:100%; height:auto; display:block; margin:6px 0 14px; }
svg.sprite { position:absolute; width:0; height:0; overflow:hidden; }
.chart svg { touch-action:none; }
.chart svg.panning { cursor:grabbing; }
.cbar { display:flex; flex-wrap:wrap; align-items:center; gap:6px 14px;
  margin:12px 0 0; font-size:12px; color:var(--mute); }
.cbar label { display:inline-flex; align-items:center; gap:5px;
  cursor:pointer; user-select:none; }
.cbar input[type=search], .cbar button { font:inherit; padding:3px 9px;
  border:1px solid var(--line); border-radius:7px; background:#fff; }
.cbar input[type=search] { min-width:16ch; color:var(--ink); }
.cbar button { cursor:pointer; color:var(--accent); }
.cbar button:hover { border-color:var(--accent); }
.cbar .chint { margin-left:auto; font-size:11px; }
.mk .gone { display:none; }
.mk .dim { opacity:.07; }
.lg { fill:#fff; pointer-events:none; }
.lg.thin-lg { fill:var(--mute); }
circle.hl, circle.pin { stroke:var(--ink); stroke-width:2.4; opacity:1; }
tr.hl { background:#eef4fd; }
.ttl, .tick, .axis { paint-order:stroke; stroke:#fff; stroke-width:3;
  stroke-linejoin:round; }
.ttl { font-size:13px; font-weight:600; fill:var(--ink); }
.grid { stroke:var(--line); stroke-width:1; }
.tick, .axis { font-size:11px; fill:var(--mute); }
.legend { fill:#fff; stroke:var(--line); stroke-width:1; }
.dot { fill:var(--accent); opacity:.78; }
.front-dot { fill:var(--front); opacity:1; }
.thin-dot { fill:#fbfbfd; stroke:var(--thin); stroke-width:1.6;
  stroke-dasharray:3 2.4; opacity:1; }
.ring { fill:none; stroke:var(--thin); stroke-width:2.2; }
.front { fill:none; stroke:var(--front); stroke-width:2;
  stroke-dasharray:5 4; }
.lead { stroke:var(--thin); stroke-width:.8; }
.lbl { font-size:10.5px; fill:var(--ink); font-weight:600;
  paint-order:stroke; stroke:#fff; stroke-width:2.6; stroke-linejoin:round; }
.thin-lbl { fill:var(--thin); font-weight:400; }
circle[data-name] { cursor:crosshair; }
circle[data-name]:hover { stroke:var(--ink); stroke-width:2; opacity:1; }
div#tip { position:fixed; z-index:30; pointer-events:none; max-width:330px;
  background:#16181d; color:#fff; border-radius:9px; padding:9px 11px;
  font-size:12px; line-height:1.45;
  box-shadow:0 8px 24px rgba(16,18,29,.26); }
div#tip[hidden] { display:none; }
div#tip strong { display:block; font-size:13px; margin-bottom:4px; }
div#tip span { display:block; color:#cbd2de; }
div#tip span b { color:#fff; font-weight:600; }
div#tip.pinned { box-shadow:0 0 0 2px var(--accent), 0 8px 24px rgba(16,18,29,.3); }
div#tip span.pinnote { margin-top:4px; color:#9aa3b2; font-style:italic; }
.table-wrap { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-size:13px; }
th, td { text-align:left; padding:5px 10px 5px 0; vertical-align:top;
  border-bottom:1px solid var(--line); }
th { color:var(--mute); font-weight:600; cursor:pointer;
  user-select:none; white-space:nowrap; }
th:hover { color:var(--accent); }
th .arrow { color:var(--accent); font-size:10px; margin-left:3px; }
th.sorted { color:var(--ink); }
td:nth-child(n+2):nth-child(-n+5) { font-variant-numeric:tabular-nums; }
table.bench td:first-child { min-width:13ch; }
table.bench td:nth-child(4), table.bench td:nth-child(9) { min-width:26ch; }
table.bench td:nth-child(5) { min-width:38ch; white-space:normal; }
table.bench td:nth-child(6) { min-width:11ch; }
table.bench td { font-variant-numeric:normal; }
table.bench td:nth-child(3) { font-variant-numeric:tabular-nums; }
/* The model group table's numeric columns stay on one line; the prose
   status column gets enough room to wrap to a few lines instead of
   being squeezed to a sliver by the browser's auto table layout. */
table.group td:nth-child(2), table.group td:nth-child(3),
table.group td:nth-child(6), table.group td:nth-child(7),
table.group td:nth-child(8), table.group td:nth-child(9) {
  white-space:nowrap; }
table.group td:nth-child(10) { white-space:normal; min-width:34ch; }
h3 { font-size:15px; margin:26px 0 4px; letter-spacing:-.01em;
  scroll-margin-top:16px; }
h4 { font-size:13px; margin:20px 0 4px; color:var(--ink); }
h4 + p.note { margin-bottom:8px; }
a { color:var(--accent); }
.when { color:var(--mute); font-weight:400; font-size:12px; }
ul.spots { color:var(--mute); margin:0 0 18px; max-width:82ch;
  padding-left:20px; }
p.gloss-h { margin:0 0 6px; font-weight:600; }
dl.gloss { margin:0 0 18px; max-width:82ch; color:var(--mute); }
dl.gloss dt { font-weight:600; color:var(--ink); margin-top:6px; }
dl.gloss dd { margin:0; }
ul.spots li { margin-bottom:6px; }
#judge p { max-width:82ch; margin:0 0 12px; }
details#judge { background:#fff; border:1px solid var(--line);
  border-radius:12px; padding:20px; margin:22px 0; scroll-margin-top:16px; }
details#judge > summary { cursor:pointer; font-size:19px; font-weight:600;
  letter-spacing:-.01em; }
details#judge[open] > summary { margin-bottom:14px; }
details { margin-top:26px; scroll-margin-top:16px; }
details.evidence { margin:18px 0 0; border-top:1px solid var(--line);
  padding-top:12px; }
details.evidence > summary { cursor:pointer; font-size:13px;
  font-weight:600; color:var(--accent); }
details.evidence[open] > summary { margin-bottom:10px; }
details.thin { margin:14px 0 0; }
details.thin > summary { cursor:pointer; font-size:13px;
  font-weight:600; color:var(--mute); }
details.thin[open] > summary { margin-bottom:8px; }
pre { overflow-x:auto; background:#fff; border:1px solid var(--line);
  border-radius:12px; padding:18px; font-size:12px; }
@media (max-width:1040px) {
  body { grid-template-columns:minmax(0,1fr); }
  nav#toc { position:static; max-height:none; }
  nav#toc ul { columns:2; }
}
"""

#: The page's whole behaviour: sortable tables, a hover card on every
#: chart point, and a contents list that follows the reader. Vanilla,
#: inline and tiny, because the page has to keep working as one file
#: copied anywhere, with no network and no build step.
PAGE_SCRIPT = """\
(function () {
  "use strict";

  var number = function (text) {
    var cleaned = text.replace(/[,$%x]/g, "").trim();
    if (!cleaned || cleaned === "-") { return null; }
    var value = Number(cleaned);
    return isFinite(value) ? value : null;
  };

  var cellText = function (row, index) {
    var cell = row.cells[index];
    return cell ? cell.textContent.trim() : "";
  };

  var mark = function (head, index, dir) {
    for (var i = 0; i < head.cells.length; i++) {
      var other = head.cells[i];
      other.classList.remove("sorted");
      if (i !== index) { delete other.dataset.dir; }
      var old = other.querySelector(".arrow");
      if (old) { old.remove(); }
    }
    var cell = head.cells[index];
    cell.classList.add("sorted");
    cell.dataset.dir = dir;
    var arrow = document.createElement("span");
    arrow.className = "arrow";
    arrow.textContent = dir === "asc" ? "\u25b2" : "\u25bc";
    cell.appendChild(arrow);
  };

  var sortBy = function (table, index) {
    var head = table.tHead.rows[0];
    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.rows);
    var numeric = rows.every(function (row) {
      var text = cellText(row, index);
      return text === "" || text === "-" || number(text) !== null;
    });
    var was = head.cells[index].dataset.dir;
    var dir = was === "desc" ? "asc" : was === "asc" ? "desc" : numeric ? "desc" : "asc";
    var sign = dir === "asc" ? 1 : -1;
    rows.sort(function (a, b) {
      var left = cellText(a, index);
      var right = cellText(b, index);
      if (numeric) {
        var lv = number(left);
        var rv = number(right);
        // A missing number sorts last whichever way the column runs:
        // "-" is an absent measurement, not a small one.
        if (lv === null && rv === null) { return 0; }
        if (lv === null) { return 1; }
        if (rv === null) { return -1; }
        return (lv - rv) * sign;
      }
      return left.localeCompare(right) * sign;
    });
    rows.forEach(function (row) { body.appendChild(row); });
    mark(head, index, dir);
  };

  Array.prototype.forEach.call(document.querySelectorAll("table"), function (table) {
    if (!table.tHead || !table.tHead.rows.length || !table.tBodies.length) { return; }
    var head = table.tHead.rows[0];
    Array.prototype.forEach.call(head.cells, function (cell, index) {
      cell.tabIndex = 0;
      cell.title = "sort by " + cell.textContent.trim();
      cell.addEventListener("click", function () { sortBy(table, index); });
      cell.addEventListener("keydown", function (event) {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          sortBy(table, index);
        }
      });
    });
    // The rows arrive already sorted by the ranker, so the first arrow
    // shows the order the reader is looking at and one click flips it.
    var already = table.dataset.sorted;
    if (already) {
      var parts = already.split(":");
      mark(head, Number(parts[0]), parts[1]);
    }
  });

  var tip = document.getElementById("tip");
  var pinned = null;
  var lines = [
    ["data-ci", "capability per cost"],
    ["data-fit", "raw capability"],
    ["data-cost", "effective cost"],
    ["data-measured", "evidence coverage"],
    ["data-boards", "measured boards"],
    ["data-band", "ability band"],
    ["data-costbasis", "cost per task"],
    ["data-state", "status"]
  ];

  var fill = function (dot) {
    tip.textContent = "";
    var title = document.createElement("strong");
    title.textContent = dot.getAttribute("data-name");
    tip.appendChild(title);
    lines.forEach(function (pair) {
      var value = dot.getAttribute(pair[0]);
      if (!value) { return; }
      var row = document.createElement("span");
      row.textContent = pair[1] + " ";
      var strong = document.createElement("b");
      strong.textContent = value;
      row.appendChild(strong);
      tip.appendChild(row);
    });
  };

  var follow = function (event) {
    var box = tip.getBoundingClientRect();
    var x = event.clientX + 16;
    var y = event.clientY + 16;
    if (x + box.width > window.innerWidth - 8) { x = event.clientX - box.width - 16; }
    if (y + box.height > window.innerHeight - 8) { y = event.clientY - box.height - 16; }
    tip.style.left = Math.max(8, x) + "px";
    tip.style.top = Math.max(8, y) + "px";
  };

  // A pinned card belongs to the reader, so hovering another point must
  // not steal it: every hover handler stands down while one is pinned.
  var unpin = function () {
    if (!pinned) { return; }
    pinned.classList.remove("pin");
    pinned = null;
    tip.classList.remove("pinned");
    tip.hidden = true;
  };

  var setPin = function (dot, event) {
    var was = pinned;
    unpin();
    if (was === dot) { return; }
    pinned = dot;
    dot.classList.add("pin");
    fill(dot);
    var note = document.createElement("span");
    note.className = "pinnote";
    note.textContent = "pinned — click it again, or press Esc, to release";
    tip.appendChild(note);
    tip.classList.add("pinned");
    tip.hidden = false;
    follow(event);
  };

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") { unpin(); }
  });

  Array.prototype.forEach.call(document.querySelectorAll("circle[data-name]"), function (dot) {
    dot.addEventListener("mouseenter", function (event) {
      if (pinned) { return; }
      fill(dot);
      tip.hidden = false;
      follow(event);
    });
    dot.addEventListener("mousemove", function (event) { if (!pinned) { follow(event); } });
    dot.addEventListener("mouseleave", function () { if (!pinned) { tip.hidden = true; } });
  });

  // ---- live charts: zoom, pan, filter, and table-to-point highlight --
  //
  // Zooming redraws rather than scales: the marks layer is moved point
  // by point under a screen-space transform, so a marker, a label and a
  // logo keep the size they were drawn at, and the two axis layers are
  // rebuilt from the plot geometry so a decade label is recomputed
  // instead of stretched.
  var SVGNS = "http://www.w3.org/2000/svg";
  var MOVES = {
    circle: ["cx", "cy"], text: ["x", "y"], use: ["x", "y"],
    line: ["x1", "y1", "x2", "y2"]
  };

  var node = function (parent, tag, attrs, text) {
    var el = document.createElementNS(SVGNS, tag);
    Object.keys(attrs).forEach(function (name) {
      var value = attrs[name];
      el.setAttribute(name, typeof value === "number" ? value.toFixed(1) : value);
    });
    if (text !== undefined) { el.textContent = text; }
    parent.appendChild(el);
    return el;
  };

  var tidy = function (value) { return String(Number(value.toPrecision(3))); };

  var lit = function (nodes, on) {
    nodes.forEach(function (one) { one.classList.toggle("hl", on); });
  };

  var liveChart = function (wrap) {
    var svg = wrap.querySelector("svg");
    var geom = svg && svg.getAttribute("data-geom");
    if (!geom) { return; }
    var g = geom.split(",").map(Number);
    var left = g[0], top = g[2], width = g[4], height = g[5];
    var x0 = g[6], x1 = g[7], y0 = g[8], y1 = g[9];
    var px0 = left, px1 = width - g[1], py0 = top, py1 = height - g[3];
    var gl = svg.querySelector("g.gl");
    var tk = svg.querySelector("g.tk");
    var mk = svg.querySelector("g.mk");
    var k = 1, tx = 0, ty = 0;

    var toX = function (v) { return px0 + (v - x0) / (x1 - x0) * (px1 - px0); };
    var toY = function (v) { return py1 - (v - y0) / (y1 - y0) * (py1 - py0); };
    var fromX = function (s) { return x0 + ((s - tx) / k - px0) / (px1 - px0) * (x1 - x0); };
    var fromY = function (s) { return y0 + (py1 - (s - ty) / k) / (py1 - py0) * (y1 - y0); };

    // One pass over the marks layer records what each element is hung
    // on: its own centre, or the `data-a` dot a label, leader or logo
    // belongs to. Everything sharing a dot's seat moves and dims with it.
    var items = [], dots = [], bucket = {}, front = null;
    Array.prototype.forEach.call(mk.children, function (el) {
      var tag = el.tagName.toLowerCase();
      if (tag === "polyline") {
        front = el;
        items.push({ el: el, pts: el.getAttribute("points").split(" ").map(function (p) {
          return p.split(",").map(Number);
        }) });
        return;
      }
      var names = MOVES[tag];
      if (!names) { return; }
      var vals = names.map(function (name) { return Number(el.getAttribute(name)); });
      var anchor = el.getAttribute("data-a");
      var a = anchor ? anchor.split(",").map(Number) : [vals[0], vals[1]];
      items.push({
        el: el, names: names, ax: a[0], ay: a[1],
        off: vals.map(function (v, i) { return v - a[i % 2]; })
      });
      var key = a[0].toFixed(1) + "," + a[1].toFixed(1);
      (bucket[key] = bucket[key] || []).push(el);
      if (el.hasAttribute("data-name")) { el.dataset.key = key; dots.push(el); }
    });

    var place = function () {
      items.forEach(function (it) {
        if (it.pts) {
          it.el.setAttribute("points", it.pts.map(function (p) {
            return (k * p[0] + tx).toFixed(1) + "," + (k * p[1] + ty).toFixed(1);
          }).join(" "));
          return;
        }
        var bx = k * it.ax + tx, by = k * it.ay + ty;
        it.names.forEach(function (name, i) {
          it.el.setAttribute(name, ((i % 2 ? by : bx) + it.off[i]).toFixed(1));
        });
      });
    };

    var nice = function (span) {
      var raw = span / 6;
      var pow = Math.pow(10, Math.floor(Math.log10(raw)));
      var n = raw / pow;
      return (n > 5 ? 10 : n > 2 ? 5 : n > 1 ? 2 : 1) * pow;
    };

    var axes = function () {
      gl.textContent = "";
      tk.textContent = "";
      // The cost axis is a log one, so its ticks are the round numbers
      // of the range in view: bare decades while the whole ladder is on
      // screen, then the round mantissas between them as the view
      // narrows, and round multiples of the cost itself once even those
      // run out. Whichever set first gives four labels is the one drawn.
      var lo = fromX(px0), hi = fromX(px1), span = hi - lo, marks = [], d, i, s, v;
      var sets = [[1], [1, 3], [1, 2, 5], [1, 1.5, 2, 3, 4, 5, 6, 8]];
      if (span > 8) {
        var by = Math.ceil(span / 8);
        for (d = Math.ceil(lo / by) * by; d <= hi; d += by) { marks.push(d); }
      } else {
        for (s = 0; s < sets.length && marks.length < 4; s++) {
          marks = [];
          for (d = Math.floor(lo); d <= Math.ceil(hi); d++) {
            for (i = 0; i < sets[s].length; i++) {
              v = d + Math.log10(sets[s][i]);
              if (v >= lo && v <= hi) { marks.push(v); }
            }
          }
        }
        if (marks.length < 4) {
          var vlo = Math.pow(10, lo), vhi = Math.pow(10, hi), by2 = nice(vhi - vlo);
          marks = [];
          for (i = Math.ceil(vlo / by2); i * by2 <= vhi; i++) { marks.push(Math.log10(i * by2)); }
        }
      }
      marks.forEach(function (at) {
        var x = k * toX(at) + tx;
        if (x < px0 - 0.5 || x > px1 + 0.5) { return; }
        node(gl, "line", { "class": "grid", x1: x, y1: top - 10, x2: x, y2: py1 });
        node(tk, "text", { "class": "tick", x: x, y: py1 + 18, "text-anchor": "middle" },
          tidy(Math.pow(10, at)) + "x");
      });
      var lowY = fromY(py1), highY = fromY(py0), stepY = nice(highY - lowY);
      for (i = Math.ceil(lowY / stepY); i * stepY <= highY; i++) {
        var y = k * toY(i * stepY) + ty;
        if (y < py0 - 0.5 || y > py1 + 0.5) { continue; }
        node(gl, "line", { "class": "grid", x1: px0, y1: y, x2: px1, y2: y });
        node(tk, "text", { "class": "tick", x: px0 - 9, y: y + 4, "text-anchor": "end" },
          tidy(i * stepY));
      }
    };

    var draw = function () {
      // Panning stops at the edges of the data: at rest the view is the
      // whole chart, and zoomed in it can never be dragged off it.
      if (k <= 1) { k = 1; tx = 0; ty = 0; } else {
        tx = Math.min(px0 * (1 - k), Math.max(px1 * (1 - k), tx));
        ty = Math.min(py0 * (1 - k), Math.max(py1 * (1 - k), ty));
      }
      place();
      axes();
    };

    var reset = function () { k = 1; tx = 0; ty = 0; draw(); };

    var at = function (point) {
      var box = svg.getBoundingClientRect();
      return {
        x: (point.clientX - box.left) / box.width * width,
        y: (point.clientY - box.top) / box.height * height
      };
    };

    var zoomAt = function (p, factor) {
      var next = Math.min(80, Math.max(1, k * factor));
      tx = p.x - (p.x - tx) * (next / k);
      ty = p.y - (p.y - ty) * (next / k);
      k = next;
      draw();
    };

    var inside = function (p) {
      return p.x >= px0 && p.x <= px1 && p.y >= py0 - 14 && p.y <= py1;
    };

    svg.addEventListener("wheel", function (event) {
      var p = at(event);
      // Off the panel the page keeps its scroll; only the plot zooms.
      if (!inside(p)) { return; }
      event.preventDefault();
      var steps = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 400 : 1;
      zoomAt(p, Math.pow(1.0016, -event.deltaY * steps));
    }, { passive: false });

    var drag = null, panned = false;
    svg.addEventListener("mousedown", function (event) {
      if (event.button !== 0 || !inside(at(event))) { return; }
      drag = { p: at(event), tx: tx, ty: ty };
      panned = false;
      event.preventDefault();
    });
    document.addEventListener("mousemove", function (event) {
      if (!drag) { return; }
      var p = at(event);
      if (Math.abs(p.x - drag.p.x) + Math.abs(p.y - drag.p.y) > 2) {
        panned = true;
        svg.classList.add("panning");
      }
      tx = drag.tx + (p.x - drag.p.x);
      ty = drag.ty + (p.y - drag.p.y);
      draw();
    });
    document.addEventListener("mouseup", function () {
      drag = null;
      svg.classList.remove("panning");
    });

    svg.addEventListener("dblclick", function (event) {
      if (event.target.closest && event.target.closest("circle[data-name]")) { return; }
      reset();
    });

    mk.addEventListener("click", function (event) {
      var dot = event.target.closest ? event.target.closest("circle[data-name]") : null;
      if (dot && !panned) { setPin(dot, event); }
    });

    var last = null;
    svg.addEventListener("touchstart", function () { last = null; }, { passive: true });
    svg.addEventListener("touchend", function () { last = null; }, { passive: true });
    svg.addEventListener("touchmove", function (event) {
      var t = event.touches, a, b, apart, mid;
      if (t.length === 1) {
        a = at(t[0]);
        if (last && last.n === 1) { tx += a.x - last.x; ty += a.y - last.y; draw(); }
        last = { n: 1, x: a.x, y: a.y };
      } else if (t.length === 2) {
        a = at(t[0]);
        b = at(t[1]);
        apart = Math.sqrt((a.x - b.x) * (a.x - b.x) + (a.y - b.y) * (a.y - b.y));
        mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
        if (last && last.n === 2) {
          tx += mid.x - last.x;
          ty += mid.y - last.y;
          zoomAt(mid, apart / last.d);
        }
        last = { n: 2, x: mid.x, y: mid.y, d: apart };
      } else { return; }
      event.preventDefault();
    }, { passive: false });

    var boxes = {};
    var search = wrap.querySelector(".nf");
    var filter = function () {
      var q = search ? search.value.trim().toLowerCase() : "";
      dots.forEach(function (dot) {
        var kind = dot.classList.contains("front-dot") ? "front"
          : dot.classList.contains("thin-dot") ? "thin" : "off";
        var hidden = boxes[kind] ? !boxes[kind].checked : false;
        var dim = !hidden && q !== "" &&
          dot.getAttribute("data-name").toLowerCase().indexOf(q) < 0;
        (bucket[dot.dataset.key] || []).forEach(function (el) {
          el.classList.toggle("gone", hidden);
          el.classList.toggle("dim", dim);
        });
      });
      if (front && boxes.front) { front.classList.toggle("gone", !boxes.front.checked); }
    };

    Array.prototype.forEach.call(wrap.querySelectorAll(".cbar input[data-k]"), function (box) {
      boxes[box.dataset.k] = box;
      box.addEventListener("change", filter);
    });
    if (search) { search.addEventListener("input", filter); }
    var button = wrap.querySelector(".rst");
    if (button) { button.addEventListener("click", reset); }

    // The tables under a chart name the same models, so a row and its
    // point light each other up; a name the chart never plotted is left
    // alone, which is what skips the benchmark and evidence tables.
    var byName = {}, rows = {};
    dots.forEach(function (dot) {
      var name = dot.getAttribute("data-name");
      (byName[name] = byName[name] || []).push(dot);
    });
    var section = wrap.closest ? wrap.closest("section") : null;
    if (section) {
      Array.prototype.forEach.call(section.querySelectorAll("tbody tr"), function (row) {
        var name = row.cells[0] ? row.cells[0].textContent.trim() : "";
        if (!byName[name]) { return; }
        (rows[name] = rows[name] || []).push(row);
        row.addEventListener("mouseenter", function () { lit(byName[name], true); });
        row.addEventListener("mouseleave", function () { lit(byName[name], false); });
      });
    }
    dots.forEach(function (dot) {
      var name = dot.getAttribute("data-name");
      dot.addEventListener("mouseenter", function () { lit(rows[name] || [], true); });
      dot.addEventListener("mouseleave", function () { lit(rows[name] || [], false); });
    });
  };

  Array.prototype.forEach.call(document.querySelectorAll(".chart"), liveChart);

  var links = Array.prototype.slice.call(document.querySelectorAll("nav#toc a"));
  var targets = links.map(function (link) {
    return document.getElementById(link.hash.slice(1));
  });

  links.forEach(function (link, index) {
    link.addEventListener("click", function () {
      // A link into a collapsed block opens it, or the jump lands on a
      // closed summary and looks broken.
      var node = targets[index];
      while (node) {
        if (node.tagName === "DETAILS") { node.open = true; }
        node = node.parentElement;
      }
    });
  });

  var spy = function () {
    // Before the first section clears the top of the window the reader is
    // still in it, so the list starts on the first entry rather than on none.
    var here = 0;
    for (var i = 0; i < targets.length; i++) {
      var node = targets[i];
      if (node && node.getBoundingClientRect().top <= 140) { here = i; }
    }
    links.forEach(function (link, index) {
      link.classList.toggle("here", index === here);
    });
  };

  var waiting = false;
  window.addEventListener("scroll", function () {
    if (waiting) { return; }
    waiting = true;
    window.requestAnimationFrame(function () {
      waiting = false;
      spy();
    });
  }, { passive: true });
  window.addEventListener("resize", spy, { passive: true });
  spy();
})();
"""


def render_html(
    models: list[Model],
    names: list[str],
    groups: dict[str, Any],
    md: str,
    sources: dict[str, Any],
    ratios: dict[str, Any],
    rel_costs: dict[str, float],
    reference: str,
) -> str:
    """Self-contained page: one chart per group, then the tables."""
    ranked = rankable(models)
    # Every maker's mark the charts need, inlined once for all four of
    # them, so a logo costs the file one copy however often it is drawn.
    sprite = logo_sprite(ranked)
    blocks = [
        how_to_judge_html(models, groups, ratios, names, cost_evidence(models, ratios, rel_costs))
    ]
    for name in names:
        spec = groups["groups"].get(name)
        note = (
            " ".join(spec["rationale"].split())
            if spec
            else "Mean of every group's raw-capability score."
        )
        front = pareto_front(ranked, name)
        front_ids = {m.key for m in front}
        ordered = group_order(ranked, name, front_ids)
        thinnest = least_measured(ranked, name)
        unranked = not_enough_boards(ranked, name)
        missing = (
            "<details class=thin><summary>"
            f"{len(unranked)} models not scored in this group"
            "</summary>"
            "<p class=note>These carry a board in this group and still cannot "
            f"be read on their own: fewer than {MIN_MEASURED_BOARDS} measured "
            "boards, which is not enough to tell an ability from one lucky "
            "reading, or boards in only one of the two pillars, which is one "
            "kind of witness. They are named here with the boards they do have "
            "rather than given a score filled in from another effort, another "
            "model or a pool-wide ratio.</p>"
            + html_table(
                ["model", "measured boards", "why", "the boards it has"],
                [
                    [
                        row.name,
                        f"{row.boards.get(name, 0)} of {row.board_pool.get(name, 0)}",
                        unranked_reason(row, name),
                        ", ".join(sorted(row.normed.get(name, {}))) or "-",
                    ]
                    for row in unranked
                ],
            )
            + "</details>"
            if unranked
            else ""
        )
        thin = (
            "<details class=thin><summary>"
            f"{len(thinnest)} least-measured models in this group</summary>"
            "<p class=note>The ranked rows with the least of this group's "
            "benchmark weight behind them. Every score here is the row's own "
            "boards, or the distance from another effort of the same model where "
            "the status says <em>placed relative to</em>, and few boards make a "
            "wide band: read the ability band beside each. The ones marked "
            "<em>too thin for the frontier</em> were kept off the frontier for "
            "that reason — they are drawn as hollow dashed dots on the chart.</p>"
            + group_table_html(thinnest, name, front_ids)
            + "</details>"
            if thinnest
            else ""
        )
        blocks.append(
            f'<section id="g-{slug(name)}"><h2>{html.escape(name)}</h2>'
            f"<p class=note>{html.escape(note)}</p>"
            + svg_chart(ranked, name, f"{name}: effective cost against raw capability")
            + benchmarks_used_html(models, groups, sources, name)
            + f'<h3 id="rank-{slug(name)}">Every model in this group</h3>'
            + "<p class=note>Click any column header to sort by it; the rows arrive "
            "frontier first, then by raw capability \u2014 the axis the frontier "
            "itself is drawn on, so no row here sits above one that beats it on "
            "both cost and capability at once. Capability per cost is a mean of "
            "min-max-scaled thirds, one of which (cost per task) a price-only row "
            "does not have, so it is a column to read rather than an order to "
            "rank by. The <strong>pillar "
            "split</strong> is the same raw capability recomputed over the "
            "preference and capability boards separately, reading "
            "<code>-</code> where a model carries less than half of one "
            "pillar's weight. A wide gap between two of them is a finding about "
            "the model, not a defect in the table. <strong>Measured boards</strong> "
            "and <strong>evidence coverage</strong> say how much of the group the "
            "row was actually run on, and the <strong>ability band</strong> is the "
            "standard error the fit puts on it.</p>"
            + group_table_html(ordered, name, front_ids)
            + thin
            + missing
            + group_evidence_html(models, groups, sources, name)
            + "</section>"
        )

    blocks.append(anchored(cost_evidence_html(models, ratios, rel_costs, reference), "cost"))
    blocks.append(anchored(price_evidence_html(models, sources, groups), "price"))

    free = sorted(
        (m for m in models if m.free and not m.rejected),
        key=lambda m: m.fit.get(OVERALL, 0.0),
        reverse=True,
    )
    blocks.append(
        "<section id=free><h2>free pool</h2><p class=note>A <code>:free</code> listing is not "
        "a price — it is a shared, throttled, temporary lane, so free availability is "
        "unreliable and nothing here is scored at a price of zero. The free backend "
        "still needs an ordering, so these are ranked by raw capability alone and carry no "
        "cost chart. <code>list</code> says whether the same model has a paid listing; "
        "<code>none</code> means free-only with no list price, and that model never "
        "enters the paid ranking.</p>"
        + html_table(
            [
                "model",
                "raw capability (0-100)",
                "evidence coverage",
                "paid listing",
                "why this place",
            ],
            [
                [
                    m.name,
                    f"{m.fit.get(OVERALL, 0.0):.1f}",
                    f"{m.cover.get(OVERALL, 0.0):.2f}",
                    "none" if m.free_only else "paid",
                    " ".join(m.free_rationale.split()),
                ]
                for m in free
            ],
        )
        + "</section>"
    )
    appendix = no_evidence_pool(models)
    blocks.append(
        f"<section id=no-evidence><h2>priced, no evidence</h2><p class=note>The candidate rule is "
        f"every text-only tool-capable model published in the last three years, so "
        f"most of the catalogue lands here: <strong>{len(appendix)}</strong> models "
        "carry a list price and appear on no board this skill reads. They are ranked "
        "nowhere, drawn on no chart, and they anchor no scale. The count is the "
        "coverage number that matters — it says how much of the market the boards do "
        "not reach.</p><details><summary>"
        f"{len(appendix)} priced candidates with no board evidence</summary>"
        + html_table(
            ["model", "id", "blended $/M", "created"],
            [[m.name, m.id, f"{m.blended:.3f}", m.created or "-"] for m in appendix],
        )
        + "</details></section>"
    )
    blocks.append(
        "<section id=rejected><h2>rejected</h2><p class=note>Kept in the data so a future run does "
        "not re-litigate them, and excluded from every ranking table and every "
        "frontier.</p>"
        + html_table(
            ["model", "disqualifier", "reason"],
            [
                [m.name, m.rejected_short or "-", " ".join(m.rejected.split())]
                for m in models
                if m.rejected
            ],
        )
        + "</section>"
    )
    blocks.append(model_drilldown_html(models, groups, sources, ratios, names))
    entries: list[tuple[str, str, list[tuple[str, str]]]] = [("judge", "How to judge this", [])]
    entries += [
        (
            f"g-{slug(name)}",
            name,
            [
                (f"boards-{slug(name)}", "Benchmarks used"),
                (f"rank-{slug(name)}", "Every model in this group"),
            ],
        )
        for name in names
    ]
    entries += [
        ("cost", "Cost per task evidence", []),
        ("price", "Price evidence", []),
        ("free", "Free pool", []),
        ("no-evidence", "Priced, no evidence", []),
        ("rejected", "Rejected", []),
        ("drilldown", "Per-model drilldown", []),
        ("markdown", "Full markdown report", []),
    ]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agentic LLM capability-per-cost frontiers</title>
<style>
{PAGE_CSS}</style></head><body>
{sprite}
{toc_html(entries)}
<main>
<h1>Agentic LLM capability-per-cost frontiers</h1>
<p class=lede>Each chart plots effective cost (log scale, the geometric
mean of relative list price and relative cost per task) against raw capability
for one group of research pipeline steps. Filled points joined by the
dashed line are the Pareto frontier, and each marker carries the logo of
the company that made the model. Every chart is live: <strong>wheel to
zoom</strong> on the cursor, <strong>drag to pan</strong>,
<strong>double-click</strong> or <em>reset view</em> to go back, and the
axes relabel as you go while markers and names keep their size. Hover a
point for its card, click it to pin the card, type in the box to dim
every model whose name does not match, untick a marker kind to drop it,
and hover a table row to light up its point. Click any column header to
sort the table by it.</p>
{"".join(blocks)}
<details id=markdown><summary>Full markdown report</summary>
<pre>{html.escape(md)}</pre></details>
</main>
<div id=tip hidden></div>
<script>
{PAGE_SCRIPT}</script></body></html>
"""


class SourceIndex:
    """Numbered source tags, so a table cell never carries a URL.

    A markdown table here has 69 characters to spend, and one
    leaderboard URL is most of that. The numbers point at one list at
    the foot of the file, which is also the only place a reader has to
    look to see every page this ranking rests on.
    """

    def __init__(self) -> None:
        self.order: list[Source] = []
        self.seen: dict[tuple[str, str], int] = {}

    def tag(self, source: Source) -> str:
        """The `[n]` for one source, adding it to the list on first sight."""
        key = (source.title, source.url)
        if key not in self.seen:
            self.order.append(source)
            self.seen[key] = len(self.order)
        return f"[{self.seen[key]}]"

    def legend(self) -> list[str]:
        """The numbered list, one line per source, links spelled out."""
        out = ["## Sources", ""]
        for number, source in enumerate(self.order, start=1):
            out.append(f"{number}. {source.title} ({source.date})")
            if source.url:
                out.append(f"   <{source.url}>")
        out.append("")
        return out


def glossary_md(title: str, terms: list[tuple[str, str]]) -> list[str]:
    """One glossary as markdown bullets, wrapped to the line width."""
    out = [title, ""]
    for term, meaning in terms:
        out += wrap(f"- **{term}** — {meaning}", bullet=True)[:-1]
    return [*out, ""]


def glossary_html(title: str, terms: list[tuple[str, str]]) -> str:
    """The same glossary as a definition list on the page."""
    items = "".join(
        f"<dt>{html.escape(term)}</dt><dd>{html.escape(meaning)}</dd>" for term, meaning in terms
    )
    return f"<p class=gloss-h>{html.escape(title)}</p><dl class=gloss>{items}</dl>"


def wrap(text: str, *, bullet: bool = False) -> list[str]:
    """One paragraph wrapped to the file's line width, blank line after.

    Long words are never broken: a path or a model id split across two
    lines stops being copy-pastable, which is most of what this file is
    for. A bullet's continuation lines are indented to stay one item.
    """
    return [
        *textwrap.wrap(
            " ".join(text.split()),
            width=MAX_TABLE_WIDTH,
            break_long_words=False,
            break_on_hyphens=False,
            subsequent_indent="  " if bullet else "",
        ),
        "",
    ]


def evidence_groups_md(
    models: list[Model],
    names: list[str],
    groups: dict[str, Any],
    sources: dict[str, Any],
    index: SourceIndex,
) -> list[str]:
    """One section per group: its boards, then every raw score."""
    ranked = paid_pool(models)
    out: list[str] = []
    for name in names:
        evidence = benchmark_evidence(models, groups, sources, name)
        if not evidence:
            continue
        out += [f"## {name}", ""]
        out += wrap(
            "Weights are the flattened ones the ranker multiplies by, so the "
            "column sums to 1.000. Every board is scaled to 0-100 by its own "
            "median and inter-quartile range over every plotted variant "
            "before it is weighted."
        )
        out += md_table(
            ["benchmark", "pillar", "weight", "covered", "srcs"],
            [
                [
                    item.label,
                    item.pillar,
                    f"{item.weight:.3f}",
                    f"{len(item.covered)}/{len(ranked)}",
                    str(len(item.sources)),
                ]
                for item in evidence
            ],
        )
        out.append("")
        for item in evidence:
            out += [f"### {item.label}", ""]
            out += wrap(item.measures)
            out += md_table(
                ["model", "raw", "norm", "src"],
                [
                    [
                        model.name,
                        f"{raw:g}",
                        f"{norm:.1f}",
                        index.tag(src),
                    ]
                    for model, raw, norm, src in raw_rows(item, name, sources)
                ],
            )
            out.append("")
    return out


def evidence_cost_md(
    models: list[Model],
    ratios: dict[str, Any],
    rel_costs: dict[str, float],
    reference: str,
    index: SourceIndex,
) -> list[str]:
    """Every cost ratio, every effort multiplier, and what each model rests on."""
    names_by_id = {m.id: m.base_name for m in models}
    out = ["## Cost per task evidence", ""]
    out += wrap(
        "A ratio row relates two models measured on the same tasks in the "
        "same published run, so nothing here crosses sources. The chaining "
        "happens in the ranker, which solves the whole graph at once in log "
        f"space with {reference} pinned at 1.00 — which is why a fitted "
        "number matches no single source exactly."
    )
    for block in ratio_blocks(ratios, names_by_id):
        out += [f"### Pairwise ratios {index.tag(block.source)}", ""]
        out += wrap(f"{block.benchmark}. Published {block.source.date}.")
        out += md_table(
            ["model a", "model b", "ratio"],
            [[a, b, f"{ratio:g}"] for a, b, ratio in block.rows],
        )
        out.append("")
    out += ["### Effort multipliers", ""]
    out += wrap(
        "Effort is a cost dial, not a value one: one harness has Opus 5 "
        "solving fewer tasks at xhigh than at high while costing more. "
        "These price the dial and never move a raw-capability score. They exist "
        "for these models only: every other model split by effort has no "
        "cost per task at any effort but its default, because the "
        "default's cost is not that effort's cost and is not borrowed for "
        "it. Those rows say `no cost-per-task data at this reasoning "
        "effort` in their status and are placed on their list price alone."
    )
    for block in effort_blocks(ratios, names_by_id):
        out += md_table(
            ["model", "effort a", "effort b", "ratio", "src"],
            [
                [model, a, b, f"{ratio:g}", index.tag(block.source)]
                for model, a, b, ratio in block.rows
            ],
        )
        out.append("")
    evidence = cost_evidence(models, ratios, rel_costs)
    out += ["### What each model's relative cost rests on", ""]
    out += wrap(
        "Low and high are what this model's ratio rows imply when each is "
        "read on its own against the other end's solved cost. The fit "
        "lands on their geometric mean by construction, so the width of "
        "that range, not the fit, is where runs disagree."
    )
    out += md_table(
        ["model", "runs", "pairs", "low", "high", "fitted", "spread"],
        [
            [
                item.model.name,
                str(len({obs[3].url for obs in item.observations})),
                str(len(item.observations)),
                f"{item.span[0]:.2f}" if item.span else "-",
                f"{item.span[1]:.2f}" if item.span else "-",
                f"{item.model.rel_cost:.2f}" if item.model.rel_cost is not None else "-",
                f"{item.spread:.2f}" if item.spread else "-",
            ]
            for item in evidence
        ],
    )
    out.append("")
    middle, worst, counted = noise_floor(evidence)
    if middle is not None and worst is not None:
        out += wrap(
            f"Across the {counted} models two or more runs both priced, the "
            f"same pair comes out a median of {middle:.2f}x apart and at "
            f"worst {worst:.2f}x apart. That is the noise floor under this "
            "whole axis: a cost gap smaller than it is not evidence."
        )
    return out


def evidence_price_md(
    models: list[Model],
    sources: dict[str, Any],
    index: SourceIndex,
    groups: dict[str, Any],
) -> list[str]:
    """List prices, the blended proxy, and any cheaper route recorded."""
    rows = price_rows(models, sources)
    weight, basis = price_blend(groups)
    blends = group_blends(groups)
    out = ["## Price evidence", ""]
    out += wrap(
        "List prices in $/M tokens, discounts deliberately ignored: a launch "
        "promotion or one cheap endpoint lapses, and the ladder should not "
        "reshuffle when it does. The blended proxy is "
        f"(input + w*output)/(1 + w), and **w is measured per task group** "
        "from the output-to-input ratio of that group's own steps in "
        f"`{SKILL_REL}/data/pipeline_steps.yaml`. The table below is the "
        f"pool-wide fallback at w = {weight:g}, which is {basis} and which "
        "only a group with no measured steps reads; the blended column is "
        "that fallback and the ranking is not."
    )
    out.append("")
    out += md_table(
        ["task group", "output per input", "basis"],
        [[name, f"{value:.4f}", note] for name, (value, note) in blends.items() if name != OVERALL],
    )
    out.append("")
    out += wrap(
        "Every one of them is far under one: agentic traffic reads far more "
        "than it writes once the prompt, the tool results and the cache "
        "reads are counted, so a price axis that weights output above input "
        "is ranking on a shape the runs do not have."
    )
    out += md_table(
        ["model", "in", "out", "blended", "rel", "src"],
        [
            [
                model.name,
                f"{model.price_in:g}",
                f"{model.price_out:g}",
                f"{model.blended:.3f}",
                f"{model.rel_price:.2f}",
                index.tag(src),
            ]
            for model, src in rows
        ],
    )
    out.append("")
    routes = [(model, model.discount) for model, _ in rows if model.discount]
    out += ["### Cheaper routes, recorded and not scored", ""]
    if not routes:
        out += wrap("No model in the pool has a discount route recorded.")
        return out
    for model, discount in routes:
        out += wrap(
            f"- {model.name}: {discount.get('input', '?')} in / "
            f"{discount.get('output', '?')} out $/M — "
            f"{' '.join(str(discount.get('note', '')).split())}",
            bullet=True,
        )
    return out


def evidence_drilldown_md(
    models: list[Model],
    names: list[str],
    groups: dict[str, Any],
    sources: dict[str, Any],
    ratios: dict[str, Any],
    index: SourceIndex,
) -> list[str]:
    """Per model, every number that fed it and every ratio it appears in."""
    names_by_id = {m.id: m.base_name for m in models}
    codes = ", ".join(f"{code} = {name}" for name, code in GROUP_CODE.items())
    out = ["## Per-model drilldown", ""]
    out += wrap(f"Group codes: {codes}.")
    order = sorted(models, key=lambda m: (bool(m.rejected), m.free, -m.fit.get(OVERALL, 0.0)))
    for model in order:
        out += [f"### {model.name}", ""]
        out += wrap(f"`{model.id}`" + (f", rung {model.rung}." if model.rung else "."))
        if model.rejected:
            out += wrap(
                f"Rejected — {model.rejected_short or 'see below'}. "
                + " ".join(model.rejected.split())
            )
        elif model.free:
            out += wrap(
                "A :free listing: throttled, temporary and never a price. "
                + (
                    "No paid listing exists, so it has no list price."
                    if model.free_only
                    else f"Priced through its paid listing {model.paid_listing}."
                )
            )
        else:
            out += wrap(
                f"Blended list price ${model.blended:.3f}/M, "
                f"{model.rel_price:.2f}x the reference; "
                + (
                    "no same-source ratio reaches it, so its cost-per-task "
                    "third falls back to its list price"
                    if model.rel_cost is None
                    else f"relative cost per task {model.rel_cost:.2f}x"
                )
                + f"; effective cost {model.eff_cost:.2f}x."
            )
            scored = [name for name in names if name in model.fit]
            if scored:
                out += md_table(
                    ["group", "capability per cost", "raw capability", "coverage"],
                    [
                        [
                            GROUP_CODE.get(name, name),
                            f"{model.calibrated_intelligence[name]:.2f}"
                            if name in model.calibrated_intelligence
                            else "-",
                            f"{model.fit[name]:.1f}",
                            f"{model.cover.get(name, 0.0):.2f}",
                        ]
                        for name in scored
                    ],
                )
                out.append("")
                for name in scored:
                    out += wrap(
                        f"- {GROUP_CODE.get(name, name)}: " + "; ".join(model.status(name)),
                        bullet=True,
                    )
        boards = drilldown_boards(model, groups, names)
        if boards:
            out += md_table(
                ["benchmark", "group", "raw", "norm", "weight", "src"],
                [
                    [
                        label,
                        GROUP_CODE.get(group, group),
                        f"{raw:g}",
                        f"{norm:.1f}",
                        f"{weight:.3f}",
                        index.tag(source_of(sources, model.srcs.get(key, ""))),
                    ]
                    for group, key, label, raw, norm, weight in boards
                ],
            )
            out.append("")
        elif not model.scores:
            out += wrap("No benchmark score is recorded for it at all.")
        pairs = drilldown_ratios(model, ratios, names_by_id)
        if pairs:
            out += md_table(
                ["other model", "this / other", "src"],
                [[other, f"{ratio:g}", index.tag(source)] for _, other, ratio, _, source in pairs],
            )
            out.append("")
        else:
            out += wrap("No same-source cost ratio reaches this model.")
    return out


def evidence_overlap_md(models: list[Model], names: list[str]) -> list[str]:
    """Every pair the fit ordered against the boards the two rows share.

    The count alone — 91% of pairs — tells a reader the method holds
    without telling them where it did not, which is the half they can
    act on. So each disagreeing pair is named, with both gaps and the
    boards behind them, worst first.
    """
    ranked = rankable(models)
    out = ["## Where the fit disagrees with the overlap", ""]
    out += wrap(
        "Every pair of scored variants sharing at least "
        f"{MIN_MEASURED_BOARDS} boards, asking whether the fit ordered them "
        "the same way those shared boards do. A pair can disagree honestly: "
        "the fit reads a row against the whole group through every chain "
        "that reaches it, while the shared-board gap reads two rows against "
        "each other alone. A wide disagreement is still worth seeing, "
        "because it is the fit saying something the two rows' own overlap "
        "does not."
    )
    for name in names:
        if name == OVERALL:
            continue
        agreed, compared = overlap_agreement(ranked, name)
        found = overlap_disagreements(ranked, name)
        out += [f"### {name}", ""]
        out += wrap(
            f"{agreed} of {compared} overlapping pairs agree"
            + (f" ({agreed / compared:.1%})" if compared else "")
            + f"; the {len(found)} that do not are listed here, widest "
            "contradiction first. `fit` is the gap the fit put between the "
            "two rows, `shared` their mean gap on the boards both were "
            "measured on, both read as the first row minus the second."
        )
        if not found:
            out += ["None.", ""]
            continue
        out += [
            f"- {item.left} vs {item.right}: {item.shared} shared boards, "
            f"fit {item.fitted:+.1f}, shared {item.measured:+.1f}"
            for item in found
        ]
        out += [""]
    return out


def render_evidence(
    models: list[Model],
    names: list[str],
    groups: dict[str, Any],
    sources: dict[str, Any],
    ratios: dict[str, Any],
    rel_costs: dict[str, float],
    reference: str,
) -> str:
    """Build the whole of results/evidence.md — the page's tables, as text."""
    index = SourceIndex()
    weights = groups["calibrated_intelligence_weights"]
    out = ["# Evidence behind the ranking", ""]
    out += wrap(
        f"Every number here is recomputed from `{SKILL_REL}/data/*.yaml` by "
        f"`{SKILL_REL}/scripts/rank_llms.py`; none is written by hand. It is "
        "the same evidence the page `results/frontiers.html` shows, in a "
        "form that greps and diffs."
    )
    out += ["## How to judge this", ""]
    out += wrap(
        "Capability per cost is the ranking key, and it is the mean of three "
        "equal thirds, each min-max scaled over the models present: "
        f"list-price cheapness ({weights['price_cheapness']:.4f}), "
        "cost-per-task cheapness "
        f"({weights['cost_per_task_cheapness']:.4f}) and raw capability "
        f"({weights['task_fit']:.4f}). A model has to earn its place on all "
        "three; no single axis can carry it. The name is a name, not a sum "
        "you can do: the three thirds are averaged, never divided one by "
        "another. The two cost thirds are scaled "
        "in log space, because price spans three orders of magnitude here."
    )
    out += wrap(
        "Nothing here is filled in. A variant is scored on the boards it was "
        "itself measured on at its own reasoning effort and on no others: no "
        "board is carried over from another effort, another model or a ratio, "
        "and a variant no same-source cost ratio reaches has no cost per task "
        "rather than a guessed one. Its capability per cost is then the two "
        "thirds it has, renormalised, and its row says price-only."
    )
    out += wrap(
        "The scores come from one fit per group over exactly the cells that "
        "exist. Every board is put on a 0-100 scale by its own median and "
        f"inter-quartile range — the median lands on 50 and {ROBUST_CLIP:.0f} "
        "of those ranges either side of it reach the ends, so a board the "
        "pool is near-flat on uses a third of the scale rather than all of "
        "it. Then one least-squares "
        "fit reads every score in the group at once as two numbers added "
        "together: a level for the board and an ability for the variant, "
        "each cell weighted by its board's weight. The board level absorbs "
        "how hard or how generous a board is; the ability that is left is "
        "the raw capability printed here. Variants "
        "that share boards are compared through them, and variants that do "
        "not are compared through the chain that connects them — so a model "
        "measured on a group's easy half no longer outranks one measured on "
        "its hard half."
    )
    out += wrap(
        "One fit cannot compare two reasoning efforts of one model that were "
        "run on different boards: it has a level per board and an ability "
        "per row and no term for the two together, so a weakness the whole "
        "model shares on the boards only one effort was run on is charged to "
        "that effort alone. So within a model the best-measured effort keeps "
        "the fit's ability and every other effort is placed at that ability "
        "plus the two rows' weighted mean gap on the boards both were "
        f"measured on. Under {MIN_SIBLING_SHARED} shared boards there is no "
        "gap worth reading and the row keeps the fit's own answer, saying so "
        "in its status."
    )
    out += wrap(
        f"A variant on fewer than {MIN_MEASURED_BOARDS} of a group's boards "
        "is left out of that group's fit, chart and table and named under it "
        "instead. Measured boards and evidence coverage say how much of the "
        "group a row was run on, and the ability band is the standard error "
        "the fit puts on it."
    )
    out += wrap(
        "Read a sparse row as optimistic. Which boards a lab publishes is "
        "not a coin toss: a model is entered where it does well, so across "
        "this catalogue a row's coverage and its score rise together. The "
        "fit cannot correct for that, because the missing cells are "
        "missing, so it is left visible instead — a row on few boards with "
        "a wide band is the best of what was published, not the average of "
        "what was run."
    )
    out += wrap(
        "Every plotted row sets the per-board scales, but a row may only sit on "
        "a frontier once it carries enough of the group's benchmark weight. "
        "One that is under that bar says too thin for "
        "the frontier in its status, is drawn as a hollow dashed dot, and is "
        "listed among the least-measured models in its group."
    )
    out += glossary_md("Columns, in plain words:", COLUMN_TERMS)
    out += glossary_md("Status words:", STATUS_TERMS)
    out += ["### Where this is weakest", ""]
    for line in weak_spots(models, groups, ratios, names):
        out += wrap(f"- {line}", bullet=True)
    middle, worst, counted = noise_floor(cost_evidence(models, ratios, rel_costs))
    if middle is not None and worst is not None:
        out += wrap(
            f"- Two runs that priced the same pair land a median of "
            f"{middle:.2f}x apart (worst {worst:.2f}x, across {counted} "
            "models). Treat that as the noise floor: a cost difference "
            "smaller than it means nothing.",
            bullet=True,
        )
    out += evidence_groups_md(models, names, groups, sources, index)
    out += evidence_overlap_md(models, names)
    out += evidence_cost_md(models, ratios, rel_costs, reference, index)
    out += evidence_price_md(models, sources, index, groups)
    out += evidence_drilldown_md(models, names, groups, sources, ratios, index)
    out += index.legend()
    return "\n".join(out).rstrip() + "\n"


def monotone_breaks(models: list[Model], group: str) -> list[tuple[str, str, float, str, float]]:
    """Where a model's dearer effort scores below its cheaper one.

    Effort is sold as a quality dial, so a higher effort scoring lower is
    the kind of thing a report should say out loud rather than average
    away. Compares adjacent efforts in the published order, so it is the
    step that went backwards that is named, not the whole ladder.
    """
    order = {name: index for index, name in enumerate(EFFORT_ORDER)}
    out = []
    by_model: dict[str, list[Model]] = defaultdict(list)
    for model in models:
        if group in model.fit and model.effort:
            by_model[model.base_name].append(model)
    for base, variants in sorted(by_model.items()):
        ladder = sorted(variants, key=lambda m: order.get(m.effort, len(order)))
        for low, high in itertools.pairwise(ladder):
            if high.fit[group] < low.fit[group] - MONOTONE_SLACK:
                out.append((base, low.effort, low.fit[group], high.effort, high.fit[group]))
    return out


def pillar_gaps(models: list[Model], group: str, count: int = 12) -> list[Model]:
    """The rows whose pillars disagree most, widest spread first.

    The disagreement is the spread between the highest and the lowest
    pillar the row was scored on, so a row the voters love and the task
    sets do not shows up whichever way round it falls.
    """

    def gap(model: Model) -> float:
        split = list(model.pillar_fit.get(group, {}).values())
        if len(split) < 2:
            return -1.0
        return max(split) - min(split)

    return sorted((m for m in models if gap(m) > 0), key=gap, reverse=True)[:count]


def requirement_gap_text(model: Model, gaps: list[str]) -> str:
    """The failing fields with the number that failed, in words."""
    shown: list[str] = []
    for gap in gaps:
        if gap == "context window":
            shown.append(f"context {(model.context_window or 0):,}")
        elif gap == "max output":
            shown.append(f"max output {(model.max_output_tokens or 0):,}")
        else:
            shown.append("no tool calling")
    return and_list(shown)


def requirement_findings(models: list[Model], groups: dict[str, Any], core: list[str]) -> list[str]:
    """The rows a group's hard requirements take off its frontier.

    Named row by row with the field that failed and the value it failed
    on, because an exclusion nobody can see is indistinguishable from a
    model the ranking never heard of.
    """
    reqs = group_requirements(groups)
    out = ["## Rows the hard requirements exclude", ""]
    out += wrap(
        "Each group declares the context window, single-response length "
        "and tool calling its steps need, derived in "
        f"`{SKILL_REL}/data/task_groups.yaml` from the step medians in "
        f"`{SKILL_REL}/data/pipeline_steps.yaml`. A row below a floor it "
        "has a published value for keeps its place in the group's table, "
        "flagged, and leaves that group's frontier and cuts. A row the "
        "capability catalogue does not publish that field for is not "
        "excluded: unknown is not a failure."
    )
    out += md_table(
        ["group", "context", "max output", "tools"],
        [
            [
                name,
                f"{int(spec.get('min_context_tokens') or 0):,}",
                f"{int(spec.get('min_max_output_tokens') or 0):,}",
                "yes" if spec.get("tool_calling") else "no",
            ]
            for name, spec in reqs.items()
        ],
    )
    out += [""]
    ranked = rankable(models)
    hit = sorted(
        (m for m in ranked if any(m.requirement_gaps.get(n) for n in core)),
        key=lambda m: (m.context_window or 0, m.key),
    )
    counts = {n: sum(1 for m in ranked if m.requirement_gaps.get(n)) for n in core}
    out += wrap(
        f"{len(hit)} of {len(ranked)} ranked variants fail at least one "
        "group's floor: " + ", ".join(f"{n} {counts[n]}" for n in core) + "."
    )
    if hit:
        rows = []
        for model in hit[:REQUIREMENT_ROWS]:
            failed = [n for n in core if model.requirement_gaps.get(n)]
            gaps = model.requirement_gaps[failed[0]]
            where = "every group" if len(failed) == len(core) else and_list(failed)
            rows.append([trim_name(model.name, 24), requirement_gap_text(model, gaps), where])
        out += md_table(["model", "fails on", "excluded from"], rows)
        if len(hit) > REQUIREMENT_ROWS:
            out += [""]
            out += wrap(
                f"{len(hit) - REQUIREMENT_ROWS} more rows fail the same "
                "way; the full list is every row whose status in "
                f"`{SKILL_REL}/results/ranking.md` names a requirement."
            )
    out += [""]
    unknown = sorted({m.name for m in ranked if m.tool_calling is None})
    blind = sorted({m.name for m in ranked if m.context_window is None})
    out += wrap(
        f"{len(unknown)} ranked models are absent from the capability "
        "catalogue, so nothing publishes a response ceiling or a "
        "tool-calling flag for them and only the context window "
        "`models.yaml` already carried can exclude them: " + (", ".join(unknown) or "none") + "."
    )
    if blind:
        out += [""]
        out += wrap(
            "Not even a context window is published for "
            + and_list(blind)
            + ", so no floor reaches them at all."
        )
    out += [""]
    return out


def render_findings(
    models: list[Model],
    names: list[str],
    groups: dict[str, Any],
    reference: str,
    notes: DataNotes,
) -> str:
    """Build results/findings.md — every stated number, recomputed.

    SKILL.md used to carry this section by hand, and it drifted: a count
    written after one run is wrong after the next, and nothing tells you
    which. So the findings are generated and SKILL.md points here. If a
    number in this file looks wrong, the data or the code is wrong; it
    cannot be the prose that is stale.
    """
    ranked = rankable(models)
    core = [n for n in names if n != OVERALL]
    aliases = [m for m in models if m.alias_of]
    out = ["# What this run found", ""]
    out += wrap(
        f"Generated by `{SKILL_REL}/scripts/rank_llms.py` from "
        f"`{SKILL_REL}/data/*.yaml`. Every number below is recomputed on "
        "each run; nothing here is written by hand. The tables it "
        f"summarises are in `{SKILL_REL}/results/ranking.md` and the raw "
        f"evidence in `{SKILL_REL}/results/evidence.md`."
    )

    out += ["## The pool", ""]
    catalogue = {m.id for m in models}
    free = [m for m in models if m.free and not m.rejected]
    rejected = [m for m in models if m.rejected]
    blind = no_evidence_pool(models)
    out += wrap(
        f"{len(catalogue)} catalogue entries become {len(ranked)} ranked "
        f"variants over {len({m.id for m in ranked})} paid models, because "
        "every (model, reasoning effort) a source actually split is its "
        "own row."
    )
    out += md_table(
        ["what", "count"],
        [
            ["catalogue entries", str(len(catalogue))],
            ["ranked paid variants", str(len(ranked))],
            ["distinct paid models", str(len({m.id for m in ranked}))],
            ["aliases folded into a snapshot", str(len(aliases))],
            ["free listings", str(len(free))],
            ["priced, on no board", str(len(blind))],
            ["rejected", str(len(rejected))],
            ["reference model", reference],
        ],
    )
    out += [""]
    split = [m for m in ranked if m.effort_split]
    measured_cost = [m for m in split if not m.price_only]
    no_cost = [m for m in ranked if m.price_only]
    out += wrap(
        "No score and no cost on this page is filled in from anywhere. "
        "A variant is scored on the boards it was itself measured on at "
        "its own reasoning effort, and each group's scores come from one "
        "weighted least-squares fit that reads every score in the group "
        "as a level for the board plus an ability for the variant, over "
        "exactly the cells that exist."
    )
    out += md_table(
        ["check", "count"],
        [
            ["variants split by reasoning effort", str(len(split))],
            ["of those, on a published cost multiplier", str(len(measured_cost))],
            ["variants with no cost per task at all", str(len(no_cost))],
        ],
    )
    out += [""]
    out += wrap(
        f"{len(split) - len(measured_cost)} of the effort-split variants "
        "have no published multiplier for their own effort, so they have "
        "no cost per task: the default effort's cost is not theirs. "
        f"{len(no_cost)} variants in all are priced on the list price "
        "alone, and their capability per cost is the two thirds they "
        "have rather than three with one invented."
    )
    out += [""]
    out += wrap(
        "**The fit against the overlap.** Every pair of scored variants "
        f"sharing at least {MIN_MEASURED_BOARDS} boards, asking whether "
        "the fit ordered them the same way their shared boards do. This "
        "is the check that the additive fit reads the overlap rather "
        "than the boards each row happens to sit on. Every pair that came "
        "out the other way is named, with both gaps, under *Where the fit "
        "disagrees with the overlap* in `results/evidence.md`."
    )
    rows = []
    for name in names:
        if name == OVERALL:
            continue
        agreed, compared = overlap_agreement(ranked, name)
        rows.append(
            [
                name,
                str(compared),
                f"{agreed / compared:.1%}" if compared else "-",
            ]
        )
    out += md_table(["group", "pairs compared", "agree"], rows)

    out += requirement_findings(models, groups, core)

    out += ["## What one board is holding up", ""]
    out += wrap(
        "Every group refitted with one board deleted, once per board, and "
        f"the worst move any of the top {LOBO_TOP} rows makes when it goes, "
        f"and how many of the top {LOBO_SET} it swaps out. "
        "The fit is least squares and least squares does not report how "
        "much of its answer rests on any single input, so this asks the "
        "question the only way sparse evidence allows: take the board "
        "away and see what happens. A big move is not an error — it is "
        "the group telling you which board it is actually ranking on, "
        "which is worth knowing before trusting the order. Rows that "
        f"fall under {MIN_MEASURED_BOARDS} boards once the board is gone "
        "leave the comparison rather than counting as a move."
    )
    for name in core:
        weights = group_weights(groups, name)
        shifts = lobo_shifts(ranked, name, weights, board_pillars(groups))
        if not shifts:
            continue
        worst = shifts[0]
        out += wrap(
            f"- **{name}** — `{worst.board}`, weight "
            f"{weights.get(worst.board, 0.0):.3f}. Drop it and the table's "
            f"worst move is {worst.moved} "
            f"{'place' if worst.moved == 1 else 'places'}: {worst.model} "
            f"goes from {worst.was} to {worst.now}, and {worst.churn} of "
            f"the top {LOBO_SET} rows "
            f"{'changes' if worst.churn == 1 else 'change'}.",
            bullet=True,
        )
    out += wrap(
        "One board per group, the one that moves it most; every other "
        "board in these groups moves the top less than that. The move is "
        "measured in table positions, not score."
    )

    out += ["## Weight, as the run flattened it", ""]
    out += wrap(
        "Every group is two equal pillars, and each pillar's boards "
        "share its half equally unless the group weighted them. So the "
        "flattened share below is a half apiece wherever the group "
        "declares both — the number to quote, and the check that no "
        "pillar quietly grew by holding more boards."
    )
    rows = []
    for name in core:
        shares = pillar_shares(groups, name)
        rows.append([name, *(f"{shares.get(p, 0.0):.0%}" for p in PILLARS)])
    out += md_table(["group", *PILLARS], rows)
    out += [""]

    out += ["## Per group", ""]
    out += wrap(
        "Plotted means the row was measured on at least "
        f"{MIN_MEASURED_BOARDS} of that group's boards, which is what it "
        "takes to be scored at all. Unranked counts the variants that "
        "carry a board here but not enough of them, and are named under "
        "the group rather than given a number."
    )
    rows = []
    for name in names:
        plotted = [m for m in ranked if name in m.fit]
        unranked = not_enough_boards(ranked, name)
        front = pareto_front(ranked, name)
        rows.append([name, str(len(plotted)), str(len(unranked)), str(len(front))])
    out += md_table(["group", "plotted", "unranked", "frontier"], rows)
    out += [""]
    for name in names:
        front = pareto_front(ranked, name)
        out += [f"### {name}", ""]
        out += wrap(
            "Frontier, cheapest first: "
            + (" -> ".join(m.name for m in front) if front else "nothing is plotted here")
        )
        top = by_calibrated_intelligence(ranked, name)[:5]
        out += md_table(
            ["best capability per cost", "raw capability", "eff cost"],
            [[m.name, f"{m.fit[name]:.1f}", f"{m.eff_cost_in(name):.2f}"] for m in top],
        )
        out += [""]

    out += ["## Where the pillars disagree", ""]
    out += wrap(
        "The same row scored on each pillar's boards alone, widest "
        "spread first. A wide gap is a finding rather than a fault: it "
        "says the model is better liked than it is correct, or better "
        "paid for than either, and which of those matters depends on "
        "the step. A blank pillar is a row with too little of it to be "
        "scored there, and blanks do not count toward the spread."
    )
    for name in names:
        gaps = pillar_gaps(ranked, name)
        if not gaps:
            continue
        out += [f"### {name}", ""]
        out += md_table(
            ["model", *PILLARS],
            [
                [
                    m.name,
                    *(
                        f"{m.pillar_fit[name][p]:.1f}" if p in m.pillar_fit.get(name, {}) else "-"
                        for p in PILLARS
                    ),
                ]
                for m in gaps
            ],
        )
        out += [""]

    out += ["## Effort is not monotone", ""]
    breaks = monotone_breaks(ranked, OVERALL)
    if breaks:
        out += wrap(
            f"{len(breaks)} models score lower at a dearer effort than at "
            "the one below it, on the overall blend. Effort is a cost "
            "dial; it is not reliably a quality one."
        )
        out += md_table(
            ["model", "step", "raw capability"],
            [
                [base, f"{low}->{high}", f"{low_fit:.1f}->{high_fit:.1f}"]
                for base, low, low_fit, high, high_fit in breaks
            ],
        )
    else:
        out += wrap("No model scores lower at a dearer effort on the overall blend.")
    out += [""]

    out += ["## What the data flagged", ""]
    if notes.ladder_clashes:
        out += wrap(
            "These models publish an effort-tagged row that contradicts "
            "the untagged row it is supposed to restate, by more than "
            f"{LADDER_AGREEMENT:.0%}. The two captures are not of the same "
            "thing, so one of them is filed under the wrong effort and "
            "the fix is a re-capture, not an average."
        )
        for model_id, clashes in sorted(notes.ladder_clashes.items()):
            out += wrap(f"- `{model_id}`: " + "; ".join(clashes), bullet=True)
    else:
        out += wrap("Every effort-tagged row agrees with its untagged row.")
    pillars = board_pillars(groups)
    for pillar in PILLARS:
        keys = {k for k, held in pillars.items() if held == pillar}
        blind = sorted({m.base_name for m in ranked if not keys & set(m.scores)})
        out += wrap(
            f"{len(blind)} of the {len({m.base_name for m in ranked})} paid "
            f"models carry no {pillar} board at all, so that pillar is "
            "unmeasured for them rather than zero and they are scored on "
            "the pillar that remains — or not ranked, where that leaves "
            "them under the pillar bar."
        )
    if notes.board_unmatched:
        out += wrap(
            f"{len(notes.board_unmatched)} captured cells named something "
            "`data/models.yaml` does not carry — an id that is not in the "
            "catalogue, or a reasoning effort that model does not declare — "
            "so they were dropped rather than turned into a row: "
            + ", ".join(f"`{cell}`" for cell in notes.board_unmatched)
        )
    else:
        out += wrap("Every captured cell landed on a catalogue row.")
    out += wrap(
        f"{len(notes.effort_unpriced)} models are split by effort with no "
        "published cost multiplier between those efforts: "
        + (", ".join(notes.effort_unpriced) if notes.effort_unpriced else "none")
    )
    if aliases:
        out += wrap(
            "These ids are aliases folded into a dated snapshot, and are "
            "not ranked in their own right: "
            + ", ".join(f"`{m.id}` -> `{m.alias_of}`" for m in sorted(aliases, key=lambda m: m.id))
        )
    return "\n".join(out).rstrip() + "\n"


@logger.catch(reraise=True)
def main() -> None:
    """Recompute the ranking and write both report files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=SKILL_DIR / "data")
    parser.add_argument("--out-dir", type=Path, default=SKILL_DIR / "results")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    logger.remove()
    logger.add(args.out_dir / "rank_llms.log", level="DEBUG", rotation="1 MB")
    if not args.quiet:
        logger.add(lambda m: print(m, end=""), format=LOG_FORMAT, level="INFO")

    raw_models = load_yaml(args.data_dir / "models.yaml")
    ratios = load_yaml(args.data_dir / "cost_ratios.yaml")
    groups = load_yaml(args.data_dir / "task_groups.yaml")
    steps = load_yaml(args.data_dir / "pipeline_steps.yaml")

    boards, board_cells, board_sources = load_boards(args.data_dir)
    unmatched = apply_boards(raw_models, boards, board_cells, declared_efforts(raw_models, ratios))
    raw_models.setdefault("sources", {}).update(board_sources)
    logger.info(
        f"{len(boards)} captured boards over "
        f"{len({c.split('@', 1)[0] for col in board_cells.values() for c in col})} models; "
        f"model-level: {', '.join(sorted(k for k, b in boards.items() if not b.per_effort)) or 'none'}"
    )

    check_sources(raw_models)
    output_weight, blend_basis = price_blend(groups)
    logger.info(
        f"list prices blended at (input + {output_weight:g} x output) / "
        f"{1.0 + output_weight:g}; that weight is {blend_basis}"
    )
    blends = group_blends(groups)
    measured = sorted(n for n, (_, basis) in blends.items() if basis == "measured")
    logger.info(
        "per-group blends measured from the step medians for " + (", ".join(measured) or "no group")
    )
    models, reference = build_models(
        raw_models, output_weight, {name: w for name, (w, _) in blends.items()}
    )
    free_only = [m.name for m in models if m.free_only and not m.rejected]
    logger.info(
        f"{len(models)} models, reference {reference}; "
        f"free-only with no list price: {', '.join(free_only) or 'none'}"
    )

    rel_costs = solve_relative_cost(ratios.get("cost_ratios", []), reference)
    notes = collect_notes(models, ratios)
    notes.board_unmatched = unmatched
    models = expand_efforts(models, ratios)
    apply_prices(models, reference)
    apply_costs(models, rel_costs)
    priced = rankable(models)
    logger.info(f"{len(priced)} paid variants over {len({m.id for m in priced})} paid models")
    logger.info(
        f"{len(priced)} priced candidates carry board evidence; "
        f"{len(no_evidence_pool(models))} are priced with none"
    )
    flagged = [m.name for m in priced if m.price_only]
    logger.info(
        f"{len(priced) - len(flagged)} of {len(priced)} models carry "
        f"cost-per-task evidence; price-only: {', '.join(flagged) or 'none'}"
    )

    names = score_models(models, groups)
    for name in names:
        plotted = [m for m in priced if name in m.fit]
        unranked = not_enough_boards(priced, name)
        agreed, compared = overlap_agreement(priced, name)
        agree = f"{agreed} of {compared} overlapping pairs" if compared else "n/a"
        logger.info(
            f"{name}: {len(plotted)} of {len(priced)} variants are scored; "
            f"{len(unranked)} carry a board here but fewer than "
            f"{MIN_MEASURED_BOARDS}; the fit agrees with {agree}"
        )
    cuts = build_cuts(models, [n for n in names if n != OVERALL])
    (args.out_dir / "cuts.yaml").write_text(render_cuts(cuts), encoding="utf-8")
    markdown = render_markdown(models, names, groups, reference, steps, cuts=cuts)
    (args.out_dir / "ranking.md").write_text(markdown, encoding="utf-8")
    sources = raw_models.get("sources") or {}
    (args.out_dir / "frontiers.html").write_text(
        render_html(models, names, groups, markdown, sources, ratios, rel_costs, reference),
        encoding="utf-8",
    )
    (args.out_dir / "findings.md").write_text(
        render_findings(models, names, groups, reference, notes),
        encoding="utf-8",
    )
    (args.out_dir / "evidence.md").write_text(
        render_evidence(models, names, groups, sources, ratios, rel_costs, reference),
        encoding="utf-8",
    )
    logger.info(f"wrote {args.out_dir / 'cuts.yaml'}")
    logger.info(f"wrote {args.out_dir / 'ranking.md'}")
    logger.info(f"wrote {args.out_dir / 'frontiers.html'}")
    logger.info(f"wrote {args.out_dir / 'evidence.md'}")
    logger.info(f"wrote {args.out_dir / 'findings.md'}")
    print(markdown)


if __name__ == "__main__":
    main()
