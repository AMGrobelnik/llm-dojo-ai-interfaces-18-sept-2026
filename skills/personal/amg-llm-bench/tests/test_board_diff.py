"""`scripts/board_diff.py` reads two `data/boards/` snapshots straight off
disk — these fixtures are small hand-written board files shaped like the
real `arena.yaml`/`aa.yaml` (a `boards:` map of `values:`, a `source:` with
`captured:`, `style_control` on some board entries), small enough to see
the diff by eye.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "scripts" / "board_diff.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("board_diff", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def write_board(path: Path, *, captured: str, boards: dict) -> None:
    path.write_text(
        yaml.safe_dump({"source": {"captured": captured}, "boards": boards}),
        encoding="utf-8",
    )


@pytest.fixture
def snapshots(tmp_path):
    old_dir, new_dir = tmp_path / "old", tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    return old_dir, new_dir


def test_summary_reports_model_count_and_capture_date(snapshots):
    old_dir, new_dir = snapshots
    write_board(
        old_dir / "arena.yaml",
        captured="2026-09-01",
        boards={"coding": {"style_control": True, "values": {"a": 1, "b": 2}}},
    )
    write_board(
        new_dir / "arena.yaml",
        captured="2026-09-08",
        boards={"coding": {"style_control": True, "values": {"a": 1, "b": 2, "c": 3}}},
    )
    module = load_script()
    table = module.summary_table(old_dir, new_dir)
    assert "| arena.yaml | 2 | 3 | 2026-09-01 | 2026-09-08 |" in table


def test_new_and_dropped_board_files_are_labelled(snapshots):
    old_dir, new_dir = snapshots
    write_board(new_dir / "aa.yaml", captured="2026-09-08", boards={})
    write_board(old_dir / "arena.yaml", captured="2026-09-01", boards={})
    module = load_script()
    table = module.summary_table(old_dir, new_dir)
    assert "| aa.yaml | (new file) | 0 | - | 2026-09-08 |" in table
    assert "| arena.yaml | 0 | (dropped) | 2026-09-01 | - |" in table


def test_style_control_table_only_lists_changed_boards(snapshots):
    old_dir, new_dir = snapshots
    write_board(
        old_dir / "arena.yaml",
        captured="2026-09-01",
        boards={
            "coding": {"style_control": False, "values": {}},
            "stable": {"style_control": True, "values": {}},
        },
    )
    write_board(
        new_dir / "arena.yaml",
        captured="2026-09-08",
        boards={
            "coding": {"style_control": True, "values": {}},
            "stable": {"style_control": True, "values": {}},
        },
    )
    module = load_script()
    table = module.style_control_table(old_dir, new_dir)
    assert table is not None
    assert "| arena.yaml | coding | False | True |" in table
    assert "stable" not in table


def test_style_control_table_is_none_when_nothing_changed(snapshots):
    old_dir, new_dir = snapshots
    boards = {"coding": {"style_control": True, "values": {}}}
    write_board(old_dir / "arena.yaml", captured="2026-09-01", boards=boards)
    write_board(new_dir / "arena.yaml", captured="2026-09-08", boards=boards)
    module = load_script()
    assert module.style_control_table(old_dir, new_dir) is None


def test_board_diff_omits_style_control_section_when_nothing_changed(snapshots):
    old_dir, new_dir = snapshots
    boards = {"coding": {"style_control": True, "values": {"a": 1}}}
    write_board(old_dir / "arena.yaml", captured="2026-09-01", boards=boards)
    write_board(new_dir / "arena.yaml", captured="2026-09-08", boards=boards)
    module = load_script()
    out = module.board_diff(old_dir, new_dir)
    assert out.startswith("## Boards changed")
    assert "style_control" not in out


def test_cli_prints_the_same_diff_as_the_function(snapshots):
    old_dir, new_dir = snapshots
    write_board(
        old_dir / "arena.yaml",
        captured="2026-09-01",
        boards={"coding": {"style_control": False, "values": {"a": 1}}},
    )
    write_board(
        new_dir / "arena.yaml",
        captured="2026-09-08",
        boards={"coding": {"style_control": True, "values": {"a": 1, "b": 2}}},
    )
    module = load_script()
    expected = module.board_diff(old_dir, new_dir)
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(old_dir), str(new_dir)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert proc.stdout == expected


def test_real_boards_dir_parses_without_error():
    """The parser must not choke on the committed real boards."""
    module = load_script()
    boards_dir = SKILL_DIR / "data" / "boards"
    out = module.board_diff(boards_dir, boards_dir)
    assert "arena.yaml" in out
    assert "aa.yaml" in out
