"""`scripts/cut_diff.py` reads two `ranking.md` snapshots by their own
markdown, not by re-running the ranker — so these fixtures are hand-written
`## <group>` sections shaped exactly like `rank_llms.py`'s real output
(table header, rows, a trailing `Pareto frontier, cheapest first:` line),
small enough to see the diff by eye.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "scripts" / "cut_diff.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("cut_diff", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclass field resolution under `from __future__ import annotations`
    # looks the defining module up in sys.modules; a module built via
    # module_from_spec is never registered there on its own.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def group_section(title: str, rows: list[tuple[str, str, str]], frontier: str) -> str:
    """One `## <title>` section shaped like a real ranking.md task group."""
    lines = [f"## {title}", "", "| model | capability per cost | raw capability |"]
    lines += [f"| {m} | {c} | {r} |" for m, c, r in rows]
    lines += ["", f"Pareto frontier, cheapest first: {frontier}"]
    return "\n".join(lines)


CODING_OLD = group_section(
    "coding-experiments",
    [
        ("Alpha (high)", "0.40", "70.0"),
        ("Beta (default)", "0.60", "65.0"),
        ("Gamma (max)", "0.55", "60.0"),
        ("Delta (high)", "0.50", "55.0"),
        ("Epsilon (default)", "0.45", "50.0"),
        ("Zeta (default)", "0.70", "40.0"),
    ],
    "Zeta (default) -> Gamma (max) -> Alpha (high)",
)

# `after`: Beta overtakes Alpha (raw capability, not table order), a new
# model (Theta) enters the top 5 bumping Zeta out, and the frontier gains a
# leg.
CODING_NEW = group_section(
    "coding-experiments",
    [
        ("Alpha (high)", "0.40", "70.0"),
        ("Beta (default)", "0.60", "72.0"),
        ("Gamma (max)", "0.55", "60.0"),
        ("Delta (high)", "0.50", "55.0"),
        ("Theta (max)", "0.48", "51.0"),
        ("Epsilon (default)", "0.45", "50.0"),
    ],
    "Zeta (default) -> Gamma (max) -> Beta (default) -> Alpha (high)",
)

OTHER_GROUP = group_section(
    "research-reasoning",
    [("Alpha (high)", "0.40", "70.0")],
    "Alpha (high)",
)

NON_GROUP_SECTION = "\n\n## Cost basis\n\nSome prose with no Pareto frontier line at all.\n"


def test_top_five_sorted_by_raw_capability_not_table_order():
    module = load_script()
    # Table order here is deliberately not capability order (frontier rows
    # first, as the real generator prints them): Zeta (40.0) sits last in
    # the table but the parser must never let it into a sorted top 5.
    groups = module.task_groups(CODING_OLD)
    top = groups["coding-experiments"].top
    assert [r.model for r in top] == [
        "Alpha (high)",
        "Beta (default)",
        "Gamma (max)",
        "Delta (high)",
        "Epsilon (default)",
    ]
    assert [r.raw_capability for r in top] == [70.0, 65.0, 60.0, 55.0, 50.0]


def test_non_group_sections_are_skipped():
    module = load_script()
    groups = module.task_groups(CODING_OLD + NON_GROUP_SECTION)
    assert "Cost basis" not in groups
    assert "coding-experiments" in groups


def test_diff_shows_rank_change_new_entrant_and_frontier_growth():
    module = load_script()
    out = module.cut_diff(CODING_OLD, CODING_NEW)
    assert "### coding-experiments" in out
    # Beta moved from #2 (65.0) to #2 with a higher score (72.0), still
    # ranks above Gamma either way, but the score itself must reflect the
    # new run, not the old one carried over.
    assert "Beta (default) — 65.0" in out  # before
    assert "Beta (default) — 72.0" in out  # after
    # Theta is a new top-5 entrant, Zeta was never in the top 5 either run.
    assert "Theta (max)" in out
    assert "Zeta (default)" not in out.split("**Pareto frontier")[0]
    # frontier gained a leg
    assert "Zeta (default) -> Gamma (max) -> Alpha (high)" in out
    assert "Zeta (default) -> Gamma (max) -> Beta (default) -> Alpha (high)" in out


def test_group_present_only_in_one_side_is_labelled():
    module = load_script()
    out_added = module.cut_diff(CODING_OLD, CODING_OLD + "\n\n" + OTHER_GROUP)
    assert "_new task group this run._" in out_added
    out_dropped = module.cut_diff(CODING_OLD + "\n\n" + OTHER_GROUP, CODING_OLD)
    assert "_task group dropped this run._" in out_dropped


def test_cli_prints_the_same_diff_as_the_function(tmp_path):
    module = load_script()
    old_path = tmp_path / "old.md"
    new_path = tmp_path / "new.md"
    old_path.write_text(CODING_OLD, encoding="utf-8")
    new_path.write_text(CODING_NEW, encoding="utf-8")

    expected = module.cut_diff(CODING_OLD, CODING_NEW)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(old_path), str(new_path)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout == expected


def test_identical_files_show_no_score_movement():
    module = load_script()
    out = module.cut_diff(CODING_OLD, CODING_OLD)
    before = out.split("**Pareto frontier")[0]
    # Every "before" line must have an identical "after" line right after
    # it for an unchanged run — cheapest sanity check is that each model's
    # score string appears twice.
    for model, _cost, raw in [
        ("Alpha (high)", "0.40", "70.0"),
        ("Beta (default)", "0.60", "65.0"),
        ("Gamma (max)", "0.55", "60.0"),
        ("Delta (high)", "0.50", "55.0"),
        ("Epsilon (default)", "0.45", "50.0"),
    ]:
        assert before.count(f"{model} — {raw}") == 2


@pytest.mark.parametrize(
    ("old_path", "new_path"),
    [
        pytest.param(
            SKILL_DIR / "results" / "ranking.md",
            SKILL_DIR / "results" / "ranking.md",
            id="real-ranking-file-parses",
        ),
    ],
)
def test_real_ranking_md_parses_without_error(old_path: Path, new_path: Path):
    """The parser must not choke on the committed real output."""
    module = load_script()
    out = module.cut_diff(
        old_path.read_text(encoding="utf-8"), new_path.read_text(encoding="utf-8")
    )
    assert "### overall" in out
    assert "**Pareto frontier, cheapest first**" in out
