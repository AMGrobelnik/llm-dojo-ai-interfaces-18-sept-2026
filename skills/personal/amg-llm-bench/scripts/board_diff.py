#!/usr/bin/env python3
"""Print before/after markdown tables from two `data/boards/` snapshots.

Built for the weekly refresh workflow's PR body
(`.github/workflows/llm-bench-refresh.yml`): given the boards directory the
last committed run left on disk and the one `capture_arena.py`/
`capture_aa.py` just overwrote, this prints two tables per the run's whole
`data/boards/*.yaml` set:

- a per-file summary: model count (rows across every board's `values`) and
  `source.captured` date, old vs new
- a per-board `style_control` table, one row per `(file, board key)` whose
  `style_control` changed — most boards never set it, so a group with no
  changes prints nothing rather than an all-`-` table nobody would read

A board file present in only one directory (added or dropped since the last
run) is shown with `(new file)`/`(dropped)` on the missing side rather than
silently skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def _load(path: Path) -> dict:
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _model_count(doc: dict) -> int:
    boards = doc.get("boards") or {}
    return sum(len((b or {}).get("values") or {}) for b in boards.values())


def _captured(doc: dict) -> str:
    return str((doc.get("source") or {}).get("captured", "?"))


def _board_names(old_dir: Path, new_dir: Path) -> list[str]:
    old_names = {p.name for p in old_dir.glob("*.yaml")} if old_dir.is_dir() else set()
    new_names = {p.name for p in new_dir.glob("*.yaml")} if new_dir.is_dir() else set()
    return sorted(old_names | new_names)


def summary_table(old_dir: Path, new_dir: Path) -> str:
    lines = [
        "| board file | old models | new models | old captured | new captured |",
        "|---|---|---|---|---|",
    ]
    for name in _board_names(old_dir, new_dir):
        old_doc, new_doc = _load(old_dir / name), _load(new_dir / name)
        old_n = _model_count(old_doc) if old_doc else "(new file)"
        old_d = _captured(old_doc) if old_doc else "-"
        new_n = _model_count(new_doc) if new_doc else "(dropped)"
        new_d = _captured(new_doc) if new_doc else "-"
        lines.append(f"| {name} | {old_n} | {new_n} | {old_d} | {new_d} |")
    return "\n".join(lines)


def style_control_table(old_dir: Path, new_dir: Path) -> str | None:
    """`None` when nothing changed — callers skip the section entirely."""
    rows = []
    for name in _board_names(old_dir, new_dir):
        old_boards = _load(old_dir / name).get("boards") or {}
        new_boards = _load(new_dir / name).get("boards") or {}
        for key in sorted(set(old_boards) | set(new_boards)):
            old_sc = (old_boards.get(key) or {}).get("style_control", "-")
            new_sc = (new_boards.get(key) or {}).get("style_control", "-")
            if old_sc != new_sc:
                rows.append(f"| {name} | {key} | {old_sc} | {new_sc} |")
    if not rows:
        return None
    header = [
        "| board file | board key | old style_control | new style_control |",
        "|---|---|---|---|",
    ]
    return "\n".join(header + rows)


def board_diff(old_dir: Path, new_dir: Path) -> str:
    parts = ["## Boards changed", "", summary_table(old_dir, new_dir)]
    style_table = style_control_table(old_dir, new_dir)
    if style_table is not None:
        parts += ["", "Per-board `style_control` changes:", "", style_table]
    return "\n".join(parts) + "\n"


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {Path(sys.argv[0]).name} <old_boards_dir> <new_boards_dir>", file=sys.stderr)
        return 2
    sys.stdout.write(board_diff(Path(sys.argv[1]), Path(sys.argv[2])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
