"""Offline coverage for capture_aa.py: name parsing and effort mapping only.

Every test here runs against `tests/fixtures/aa/models.json` — a trimmed,
shape-preserving copy of the real API response — and the real
`data/models.yaml` catalogue for id resolution and effort validation. No
network call is made.
"""

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "aa"


def load_script() -> ModuleType:
    """Import capture_aa.py by path, without touching sys.path."""
    spec = importlib.util.spec_from_file_location(
        "capture_aa", SKILL_DIR / "scripts" / "capture_aa.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot import capture_aa.py")
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


def load_rows() -> list[dict]:
    return json.loads((FIXTURES / "models.json").read_text(encoding="utf-8"))["data"]


@pytest.mark.parametrize(
    ("name", "expected_base", "expected_tags"),
    [
        (
            "Claude Fable 5.1 (Adaptive Reasoning, Max Effort, Default Fallback)",
            "Claude Fable 5.1",
            ["Adaptive Reasoning, Max Effort, Default Fallback"],
        ),
        ("GPT-6 Astra (xhigh)", "GPT-6 Astra", ["xhigh"]),
        ("Some Model (Sep '25) (Reasoning)", "Some Model", ["Sep '25", "Reasoning"]),
        ("Plain Model", "Plain Model", []),
    ],
)
def test_strip_trailing_parens(
    cap: ModuleType, name: str, expected_base: str, expected_tags: list[str]
) -> None:
    base, tags = cap.strip_trailing_parens(name)
    assert base == expected_base
    assert tags == expected_tags


@pytest.mark.parametrize(
    ("tags", "expected_effort"),
    [
        (["Adaptive Reasoning, Max Effort, Default Fallback"], "max"),
        (["xhigh"], "xhigh"),
        (["Non-reasoning, High Effort"], "high"),
        (["Reasoning, High Effort"], "high"),
        (["Reasoning"], "reasoning"),
        (["Non-reasoning"], "non-reasoning"),
        (["Beta"], None),
        ([], None),
    ],
)
def test_extract_effort(cap: ModuleType, tags: list[str], expected_effort: str | None) -> None:
    assert cap.extract_effort(tags) == expected_effort


def test_match_model_resolves_frontier_name_with_effort(cap: ModuleType, catalogue) -> None:
    resolved, effort = cap.match_model(
        catalogue, "Claude Fable 5.1 (Adaptive Reasoning, Max Effort, Default Fallback)"
    )
    assert resolved == "anthropic/claude-fable-5.1"
    assert effort == "max"


def test_match_model_bare_openai_effort_word(cap: ModuleType, catalogue) -> None:
    resolved, effort = cap.match_model(catalogue, "GPT-6 Astra (xhigh)")
    assert resolved == "openai/gpt-6-astra"
    assert effort == "xhigh"


def test_match_model_reasoning_tag_prefers_thinking_id(cap: ModuleType, catalogue) -> None:
    # moonshotai/kimi-k2-thinking is its own catalogue id (name "Kimi K2
    # Thinking"), so a "(Reasoning)" tag should land there with NO effort
    # suffix rather than becoming "kimi-k2@reasoning".
    resolved, effort = cap.match_model(catalogue, "Kimi K2 (Reasoning)")
    assert resolved == "moonshotai/kimi-k2-thinking"
    assert effort is None


def test_match_model_non_reasoning_falls_back_to_base_with_suffix(
    cap: ModuleType, catalogue
) -> None:
    # "Kimi K2" (undecorated) is itself `alias_of: moonshotai/kimi-k2-0905`;
    # a "(Non-reasoning)" tag has no distinct id to prefer, so it folds the
    # alias and keeps the tag as an effort suffix.
    resolved, effort = cap.match_model(catalogue, "Kimi K2 (Non-reasoning)")
    assert resolved == "moonshotai/kimi-k2-0905"
    assert effort == "non-reasoning"


def test_match_model_unmatched_name_returns_none(cap: ModuleType, catalogue) -> None:
    resolved, effort = cap.match_model(catalogue, "Totally New Frontier Model X1 (high)")
    assert resolved is None
    assert effort == "high"


def test_build_capture_keys_boards_by_id_and_effort(cap: ModuleType, catalogue) -> None:
    result = cap.build_capture(catalogue, load_rows(), captured_on="2026-09-17")
    intelligence = result.boards["aa_api_intelligence_index"]["values"]

    assert intelligence["anthropic/claude-fable-5.1@max"] == pytest.approx(53.4)
    assert intelligence["anthropic/claude-fable-5.1@high"] == pytest.approx(51.2)
    assert intelligence["anthropic/claude-fable-5.1@low"] == pytest.approx(47.3)
    assert intelligence["openai/gpt-6-astra@xhigh"] == pytest.approx(60.0)
    assert intelligence["moonshotai/kimi-k2-thinking"] == pytest.approx(44.0)
    assert intelligence["moonshotai/kimi-k2-0905@non-reasoning"] == pytest.approx(38.0)
    assert intelligence["google/gemini-3.1-pro-preview"] == pytest.approx(45.0)

    # Nulls are skipped, not written as zeros or missing-but-present keys.
    coding = result.boards["aa_api_coding_index"]["values"]
    assert "anthropic/claude-fable-5.1@low" not in coding
    assert coding["anthropic/claude-fable-5.1@max"] == pytest.approx(81.6)

    assert result.boards["aa_api_intelligence_index"]["unit"] == "index"
    assert result.boards["aa_api_gpqa"]["unit"] == "fraction"

    meta = result.meta["anthropic/claude-fable-5.1@max"]
    assert meta["input_per_m"] == 10
    assert meta["release_date"] == "2026-09-01"


def test_build_capture_reports_unmatched_and_flags_current_gen(cap: ModuleType, catalogue) -> None:
    result = cap.build_capture(catalogue, load_rows(), captured_on="2026-09-17")
    assert "Totally New Frontier Model X1 (high)" in result.unmatched
    assert "Ancient Model Zeta" in result.unmatched
    current_gen_note = "; ".join(result.notes)
    assert "Totally New Frontier Model X1 (high)" in current_gen_note
    assert "Ancient Model Zeta" not in current_gen_note


def test_validate_effort_mapping_flags_the_deliberate_mismatch(cap: ModuleType, catalogue) -> None:
    result = cap.build_capture(catalogue, load_rows(), captured_on="2026-09-17")
    mismatches = cap.validate_effort_mapping(catalogue, result.boards)
    joined = "; ".join(mismatches)
    # Fixture deliberately mis-scores GPT-6 Astra's xhigh row (60.0 vs the
    # 53 models.yaml carries) to prove the checker catches it.
    assert "openai/gpt-6-astra@xhigh" in joined
    # And the low-effort rows for both frontier models are within the
    # 1-point tolerance, so they must NOT be reported.
    assert "anthropic/claude-fable-5.1@low" not in joined
    assert "openai/gpt-6-astra@low" not in joined


def test_capture_result_yaml_dict_is_deterministic(cap: ModuleType, catalogue) -> None:
    rows = load_rows()
    first = cap.build_capture(catalogue, rows, captured_on="2026-09-17").to_yaml_dict()
    second = cap.build_capture(catalogue, rows, captured_on="2026-09-17").to_yaml_dict()
    assert first == second
    assert list(first["boards"]["aa_api_intelligence_index"]["values"]) == sorted(
        first["boards"]["aa_api_intelligence_index"]["values"]
    )
