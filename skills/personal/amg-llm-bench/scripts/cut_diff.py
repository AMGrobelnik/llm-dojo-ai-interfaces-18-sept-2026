#!/usr/bin/env python3
"""Print a before/after markdown summary of two `results/ranking.md` runs.

Built for the weekly refresh workflow's PR body
(`.github/workflows/llm-bench-refresh.yml`): given the `ranking.md` from the
last committed run and the one `scripts/rank_llms.py` just wrote, this prints
one markdown section per task group — any `## <title>` section of the file
that carries a `Pareto frontier, cheapest first:` line, which is exactly the
sections `rank_llms.py` emits per `data/task_groups.yaml` entry plus
`overall`. Non-group sections (`Cost basis`, `Free pool`, ...) are skipped
without being named, so a future section never needs an update here.

Two things move per group, read straight from the file rather than
recomputed:

- **top 5** — the five rows with the highest `raw capability` in the
  group's first table (`| model | capability per cost | raw capability |`),
  sorted here rather than taken as the table's first five rows, because
  the table prints frontier rows first (cheapest-first, not
  capability-first) and only the remainder in capability order.
- **frontier** — the `Pareto frontier, cheapest first: A -> B -> C` line
  verbatim, which is `rank_llms.py`'s own Pareto computation, not
  re-derived here.

A group present in only one file (added or dropped since the last run) is
printed with just that side filled in, never silently skipped.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

SECTION_RE = re.compile(r"(?m)^## (.+)$")
FRONTIER_RE = re.compile(r"(?m)^Pareto frontier, cheapest first: (.+)$")
TABLE_HEADER_RE = re.compile(
    r"^\|\s*model\s*\|\s*capability per cost\s*\|\s*raw capability\s*\|\s*$"
)
TOP_N = 5


@dataclass(frozen=True)
class Row:
    model: str
    capability_per_cost: str
    raw_capability: float
    raw_capability_text: str


def iter_sections(text: str) -> list[tuple[str, str]]:
    """Every top-level (`## `) section as (title, body); `### ` never matches."""
    matches = list(SECTION_RE.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append((m.group(1).strip(), text[start:end]))
    return sections


def parse_rows(body: str) -> list[Row]:
    lines = body.splitlines()
    header_i = next((i for i, ln in enumerate(lines) if TABLE_HEADER_RE.match(ln)), None)
    if header_i is None:
        return []
    rows = []
    for ln in lines[header_i + 1 :]:
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        if len(cells) != 3:
            break
        model, cap_per_cost, raw_text = cells
        try:
            raw = float(raw_text)
        except ValueError:
            continue
        rows.append(Row(model, cap_per_cost, raw, raw_text))
    return rows


def parse_frontier(body: str) -> str | None:
    m = FRONTIER_RE.search(body)
    return m.group(1).strip() if m else None


@dataclass(frozen=True)
class GroupSnapshot:
    title: str
    top: list[Row]
    frontier: str | None


def task_groups(text: str) -> dict[str, GroupSnapshot]:
    groups = {}
    for title, body in iter_sections(text):
        frontier = parse_frontier(body)
        if frontier is None:
            continue  # not a task-group section (Cost basis, Free pool, ...)
        rows = parse_rows(body)
        top = sorted(rows, key=lambda r: r.raw_capability, reverse=True)[:TOP_N]
        groups[title] = GroupSnapshot(title, top, frontier)
    return groups


def render_top(rows: list[Row]) -> list[str]:
    if not rows:
        return ["  _(no rows)_"]
    return [f"  {i}. {r.model} — {r.raw_capability_text}" for i, r in enumerate(rows, 1)]


def render_group(old: GroupSnapshot | None, new: GroupSnapshot | None) -> list[str]:
    title = (new or old).title  # type: ignore[union-attr]
    lines = [f"### {title}"]
    if old is None:
        lines.append("_new task group this run._")
    elif new is None:
        lines.append("_task group dropped this run._")
    lines += ["", "**Top 5 by raw capability**", ""]
    lines += ["- before:", *render_top(old.top if old else [])]
    lines += ["- after:", *render_top(new.top if new else [])]
    lines += ["", "**Pareto frontier, cheapest first**", ""]
    lines.append(f"- before: {old.frontier if old else '_none_'}")
    lines.append(f"- after: {new.frontier if new else '_none_'}")
    return lines


def cut_diff(old_text: str, new_text: str) -> str:
    old_groups = task_groups(old_text)
    new_groups = task_groups(new_text)
    titles = list(dict.fromkeys([*old_groups, *new_groups]))  # stable order, old first
    lines = ["## Task group changes", ""]
    if not titles:
        lines.append("_no task-group sections found in either ranking.md._")
    for title in titles:
        lines += render_group(old_groups.get(title), new_groups.get(title))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_ranking", type=Path)
    parser.add_argument("new_ranking", type=Path)
    args = parser.parse_args()

    old_text = args.old_ranking.read_text(encoding="utf-8")
    new_text = args.new_ranking.read_text(encoding="utf-8")
    sys.stdout.write(cut_diff(old_text, new_text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
