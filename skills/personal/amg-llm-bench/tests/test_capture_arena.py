"""Offline coverage for capture_arena.py: parsing and alias mapping only.

`tests/fixtures/arena/capture_dump.json` is a trimmed copy of
`capture_arena.mjs`'s real JSON contract — built by replaying that same
`$$eval` extraction against locally saved, already-hydrated HTML snapshots
of the real site (`file://` navigation, no network) and keeping a small,
representative slice of the rows. It exercises: the Text board's frontier
models plus two rows that genuinely don't resolve (an Arena bot literally
named `claude-fable-5-high`, distinct from `claude-fable-5.1`, and an
obscure Nvidia checkpoint), a WebDev board with no style-control toggle at
all, a Search board with the toggle present and turned on (the live
capture always turns the toggle on before reading a board that has one), a
Document board with no toggle, and a slice of the Agent board's signed
percentage cells. No
network or Playwright call is made; alias resolution runs against the
real `data/models.yaml` catalogue, exactly as the live capture would.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arena"


def load_script() -> ModuleType:
    """Import capture_arena.py by path, without touching sys.path."""
    spec = importlib.util.spec_from_file_location(
        "capture_arena", SKILL_DIR / "scripts" / "capture_arena.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot import capture_arena.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # `from __future__ import annotations` needs this to resolve
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="cap")
def cap_fixture() -> ModuleType:
    return load_script()


@pytest.fixture(name="catalogue")
def catalogue_fixture(cap: ModuleType):
    return cap.load_catalogue(cap.MODELS_YAML)


def load_dump() -> dict:
    return json.loads((FIXTURES / "capture_dump.json").read_text(encoding="utf-8"))


# --- pure helpers -----------------------------------------------------------


def test_normalize_drops_all_punctuation(cap: ModuleType) -> None:
    assert cap.normalize("Claude Fable 5.1 (Max)") == "claudefable51max"
    assert cap.normalize("gemini-3.8-flash") == "gemini38flash"


def test_strip_effort_suffix_hyphen_form(cap: ModuleType) -> None:
    base, effort = cap.strip_effort_suffix("claude-opus-5-high")
    assert base == "claude-opus-5"
    assert effort == "high"


def test_strip_effort_suffix_parenthetical_form(cap: ModuleType) -> None:
    base, effort = cap.strip_effort_suffix("Claude Fable 5.1 (Max)")
    assert base == "Claude Fable 5.1"
    assert effort == "max"


def test_strip_effort_suffix_leaves_non_effort_suffix_alone(cap: ModuleType) -> None:
    # "flash" is a real model-family word, not a reasoning-effort tag.
    base, effort = cap.strip_effort_suffix("glm-5.3-flash")
    assert base == "glm-5.3-flash"
    assert effort is None


def test_parse_leading_number_ignores_ci_and_trailing_flags(cap: ModuleType) -> None:
    assert cap.parse_leading_number("1493±9Preliminary") == pytest.approx(1493)
    assert cap.parse_leading_number("1800+16/-16") == pytest.approx(1800)
    assert cap.parse_leading_number("13.71%±1.72%") == pytest.approx(13.71)


def test_parse_int_commas(cap: ModuleType) -> None:
    assert cap.parse_int_commas("30,057") == 30057
    assert cap.parse_int_commas("N/A") is None


# --- alias resolution against the real catalogue ----------------------------


def test_resolve_key_folds_default_effort_into_bare_id(cap: ModuleType, catalogue) -> None:
    # claude-opus-5's default_effort is "high".
    assert (
        cap.resolve_key("anthropic/claude-opus-5", "high", catalogue) == "anthropic/claude-opus-5"
    )
    assert (
        cap.resolve_key("anthropic/claude-opus-5", "max", catalogue)
        == "anthropic/claude-opus-5@max"
    )
    assert cap.resolve_key("anthropic/claude-opus-5", None, catalogue) == "anthropic/claude-opus-5"


def test_match_by_name_resolves_slug_style_and_display_style_titles(
    cap: ModuleType, catalogue
) -> None:
    assert cap.match_by_name("claude-opus-5-high", catalogue) == ("anthropic/claude-opus-5", "high")
    assert cap.match_by_name("Claude Fable 5.1 (Max)", catalogue) == (
        "anthropic/claude-fable-5.1",
        "max",
    )
    # gpt-6-astra's default_effort is "max", and its own id ends in no
    # effort word at all — the untouched-title fallback must not fire here.
    assert cap.match_by_name("gpt-6-astra-max", catalogue) == ("openai/gpt-6-astra", "max")


def test_match_by_name_resolves_a_same_family_predecessor_to_its_own_id(
    cap: ModuleType, catalogue
) -> None:
    # "claude-fable-5" (no ".1") is its own catalogue id, distinct from
    # `anthropic/claude-fable-5.1` — normalized matching must not conflate
    # the two just because they share most of a name.
    assert cap.match_by_name("claude-fable-5-high", catalogue) == (
        "anthropic/claude-fable-5",
        "high",
    )


def test_match_by_name_returns_none_for_an_unknown_model(cap: ModuleType, catalogue) -> None:
    assert cap.match_by_name("totally-unknown-vendor-ghost-model-9000", catalogue) is None


# --- build_capture end to end, against the fixture dump --------------------


def test_build_capture_resolves_all_seven_frontier_ids_on_text_board(
    cap: ModuleType, catalogue
) -> None:
    dump = load_dump()
    result = cap.build_capture(catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17")
    text_values = result.boards["arena_text_elo"]["values"]
    for frontier_id in (
        "anthropic/claude-fable-5.1",
        "openai/gpt-6-astra",
        "anthropic/claude-opus-5",
        "anthropic/claude-sonnet-5",
        "google/gemini-3.8-flash",
    ):
        assert any(
            key == frontier_id or key.startswith(f"{frontier_id}@") for key in text_values
        ), f"{frontier_id} did not resolve on the Text board"


def test_build_capture_keeps_genuinely_unmatched_rows_out_of_values(
    cap: ModuleType, catalogue
) -> None:
    dump = load_dump()
    result = cap.build_capture(catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17")
    # deepseek-v3.2-exp-thinking has no catalogue id and no arena_text_elo
    # ground truth close enough to disambiguate it from its neighbours.
    assert "deepseek-v3.2-exp-thinking" in result.unmatched
    assert "nvidia-nemotron-3.5-lightning-30b-a3b-nvfp4" in result.unmatched
    # claude-fable-5-high and claude-fable-5.1-max are two distinct,
    # correctly-resolved catalogue ids, not one row swallowing the other.
    text_values = result.boards["arena_text_elo"]["values"]
    assert text_values["anthropic/claude-fable-5"] == pytest.approx(1506)
    assert text_values["anthropic/claude-fable-5.1@max"] == pytest.approx(1498)


def test_build_capture_records_votes_alongside_values(cap: ModuleType, catalogue) -> None:
    dump = load_dump()
    result = cap.build_capture(catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17")
    text_board = result.boards["arena_text_elo"]
    assert "votes" in text_board
    assert set(text_board["votes"]) <= set(text_board["values"])
    assert text_board["votes"]["anthropic/claude-opus-5"] == 42617


def test_build_capture_style_control_true_when_toggle_present_none_when_not(
    cap: ModuleType, catalogue
) -> None:
    dump = load_dump()
    result = cap.build_capture(catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17")
    assert result.boards["arena_text_elo"]["style_control"] is True
    assert result.boards["arena_webdev_elo"]["style_control"] is None  # no toggle in the DOM
    assert result.boards["arena_search_elo"]["style_control"] is True  # toggle present, turned on
    assert result.boards["arena_document_elo"]["style_control"] is None  # no toggle in the DOM


def test_build_capture_never_writes_style_control_false(cap: ModuleType, catalogue) -> None:
    # The live capture always turns a present toggle on before reading the
    # table, so no board should ever be written with style_control: false —
    # only True (toggle present and on) or None (no toggle at all in the DOM).
    dump = load_dump()
    result = cap.build_capture(catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17")
    for board_key, board in result.boards.items():
        assert board["style_control"] in (True, None), (
            f"{board_key}: style_control={board['style_control']!r}"
        )


def test_build_capture_negates_tool_hallucination_by_its_trend_icon(
    cap: ModuleType, catalogue
) -> None:
    dump = load_dump()
    result = cap.build_capture(catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17")
    halluc = result.boards["arena_agent_tool_halluc"]["values"]
    # claude-fable-5.1@max shows "0.37%" on screen with a "Down" trend icon.
    assert halluc["anthropic/claude-fable-5.1@max"] == pytest.approx(-0.37)
    net_impr = result.boards["arena_agent_net_impr"]["values"]
    # ...but its Net Improvement cell shows the same 13.71% with an "Up" icon.
    assert net_impr["anthropic/claude-fable-5.1@max"] == pytest.approx(13.71)


def test_build_capture_skips_a_missing_board_without_failing_the_others(
    cap: ModuleType, catalogue
) -> None:
    dump = load_dump()
    boards = dict(dump["boards"])
    del boards["arena_document_elo"]
    errors = {**dump["errors"], "arena_document_elo": "table never populated (timeout)"}
    result = cap.build_capture(catalogue, boards, errors, captured_on="2026-09-17")
    assert "arena_document_elo" not in result.boards
    assert "arena_text_elo" in result.boards
    assert any("arena_document_elo" in note for note in result.notes)


def test_capture_result_yaml_dict_is_deterministic(cap: ModuleType, catalogue) -> None:
    dump = load_dump()
    first = cap.build_capture(
        catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17"
    ).to_yaml_dict()
    second = cap.build_capture(
        catalogue, dump["boards"], dump["errors"], captured_on="2026-09-17"
    ).to_yaml_dict()
    assert first == second
    assert list(first["boards"]["arena_text_elo"]["values"]) == sorted(
        first["boards"]["arena_text_elo"]["values"]
    )
