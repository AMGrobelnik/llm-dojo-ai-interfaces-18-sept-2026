"""Fixture-only tests for ``scripts/aggregate_steps.py``.

No live database: :func:`collect_attempts` and :func:`aggregate_by_step`
take plain ``(workflow_uuid, message_dict)`` iterables, so a handful of
hand-built journal messages exercise the same grouping and median logic
the real journal scan uses, without a psycopg connection. The yaml
surgery (:func:`patch_step_chunk` / :func:`rewrite_pipeline_steps_yaml`)
is tested against a small fixture file, never the real
``data/pipeline_steps.yaml``.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "scripts" / "aggregate_steps.py"


def load_script() -> ModuleType:
    """Import aggregate_steps.py by path, without touching sys.path.

    Registered in ``sys.modules`` before exec so its ``@dataclass``
    fields can resolve their own module's namespace (dataclasses
    looks itself up there for postponed-annotation evaluation).
    """
    spec = importlib.util.spec_from_file_location("aggregate_steps", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        del sys.modules[spec.name]
        raise
    return module


@pytest.fixture(scope="module")
def agg() -> ModuleType:
    return load_script()


# ---------------------------------------------------------------------------
# derive_step: task_id -> pipeline_steps.yaml step key
# ---------------------------------------------------------------------------


def test_derive_step_execute_and_gen_plan_families(agg: ModuleType) -> None:
    assert agg.derive_step("gen_art_research_1_d95c3d9d992f") == "execute.research"
    assert agg.derive_step("gen_art_experiment_3_abc123456789") == "execute.experiment"
    assert agg.derive_step("gen_plan_dataset_2_abc123456789") == "gen_plan.dataset"


def test_derive_step_direct_renames(agg: ModuleType) -> None:
    assert agg.derive_step("gen_hypo_1_abc123456789") == "gen_hypo"
    assert agg.derive_step("review_hypo_1_abc123456789") == "review_hypo"
    assert agg.derive_step("upd_hypo_1_abc123456789") == "upd_hypo"


def test_derive_step_gen_demo_art_aliases_fold_together(agg: ModuleType) -> None:
    """gen_art_demo_* is a dead pre-rename alias for the current gen_demo_art_* name."""
    current = agg.derive_step("gen_demo_art_dataset_1_abc123456789")
    legacy = agg.derive_step("gen_art_demo_dataset_1_abc123456789")
    assert current == legacy == "gen_demo_art"


def test_derive_step_gen_viz_resume_folds_into_gen_viz(agg: ModuleType) -> None:
    assert agg.derive_step("gen_viz_resume_1_abc123456789") == "gen_viz"


def test_derive_step_unrelated_task_id_returns_none(agg: ModuleType) -> None:
    assert agg.derive_step("sketch 3: Central bank digital currency") is None


def test_derive_step_non_llm_repo_steps_excluded(agg: ModuleType) -> None:
    """gen_repo/deploy_gh never emit a recognized task_id, so they drop out."""
    assert agg.derive_step("gen_repo_1_abc123456789") is None
    assert agg.derive_step("deploy_gh_1_abc123456789") is None


# ---------------------------------------------------------------------------
# collect_attempts / aggregate_by_step: the median population itself
# ---------------------------------------------------------------------------


def _agent_summary(
    task_id: str,
    *,
    total_cost: float,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    tool_calls: dict | None = None,
) -> dict:
    return {
        "type": "agent_summary",
        "task_id": task_id,
        "total_cost": total_cost,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "extras": {"tool_calls": tool_calls or {}},
    }


def test_one_task_end_becomes_one_sample(agg: ModuleType) -> None:
    """A single task attempt: one task_start, one agent_summary, one task_end."""
    task_id = "gen_art_research_1_d95c3d9d992f"
    rows = [
        ("wf-1", {"type": "task_start", "task_id": task_id, "end_at": "2026-09-01T00:00:00Z"}),
        (
            "wf-1",
            _agent_summary(
                task_id,
                total_cost=1.5,
                input_tokens=100,
                output_tokens=200,
                tool_calls={"Bash": 3, "Read": 2},
            ),
        ),
        (
            "wf-1",
            {
                "type": "task_end",
                "task_id": task_id,
                "status": "done",
                "end_at": "2026-09-01T00:10:00Z",
            },
        ),
    ]
    attempts = agg.collect_attempts(rows)
    by_step, unmapped = agg.aggregate_by_step(attempts)
    assert not unmapped
    stats = by_step["execute.research"]
    assert stats.n == 1
    assert stats.failures == 0
    assert stats.tool_calls == [5]
    assert stats.minutes == [10.0]
    assert stats.cost_usd == [1.5]
    assert stats.input_tokens == [100]
    assert stats.output_tokens == [200]


def test_multiple_agent_summaries_in_one_workflow_sum(agg: ModuleType) -> None:
    """Subagent conversations under the same task attempt add up, not overwrite."""
    task_id = "gen_hypo_1_abc123456789"
    rows = [
        ("wf-2", {"type": "task_start", "task_id": task_id, "end_at": "2026-09-01T00:00:00Z"}),
        (
            "wf-2",
            _agent_summary(
                task_id, total_cost=1.0, input_tokens=50, output_tokens=60, tool_calls={"Bash": 1}
            ),
        ),
        (
            "wf-2",
            _agent_summary(
                task_id, total_cost=0.5, input_tokens=20, output_tokens=30, tool_calls={"Write": 1}
            ),
        ),
        (
            "wf-2",
            {
                "type": "task_end",
                "task_id": task_id,
                "status": "done",
                "end_at": "2026-09-01T00:05:00Z",
            },
        ),
    ]
    attempts = agg.collect_attempts(rows)
    by_step, _ = agg.aggregate_by_step(attempts)
    stats = by_step["gen_hypo"]
    assert stats.cost_usd == [1.5]
    assert stats.input_tokens == [70]
    assert stats.tool_calls == [2]


def test_two_workflows_for_same_task_id_stay_separate_samples(agg: ModuleType) -> None:
    """A hot-resume rerun reuses task_id but gets a fresh workflow_uuid: two samples."""
    task_id = "gen_strat_1_abc123456789"
    rows = [
        ("wf-a", {"type": "task_start", "task_id": task_id, "end_at": "2026-09-01T00:00:00Z"}),
        ("wf-a", _agent_summary(task_id, total_cost=0.1, input_tokens=10, output_tokens=10)),
        (
            "wf-a",
            {
                "type": "task_end",
                "task_id": task_id,
                "status": "failed",
                "end_at": "2026-09-01T00:01:00Z",
            },
        ),
        (
            "wf-a-rerun-1",
            {
                "type": "task_start",
                "task_id": task_id,
                "end_at": "2026-09-01T00:02:00Z",
            },
        ),
        (
            "wf-a-rerun-1",
            _agent_summary(task_id, total_cost=0.2, input_tokens=20, output_tokens=20),
        ),
        (
            "wf-a-rerun-1",
            {
                "type": "task_end",
                "task_id": task_id,
                "status": "done",
                "end_at": "2026-09-01T00:04:00Z",
            },
        ),
    ]
    attempts = agg.collect_attempts(rows)
    by_step, _ = agg.aggregate_by_step(attempts)
    stats = by_step["gen_strat"]
    assert stats.n == 2
    assert stats.failures == 1
    assert sorted(stats.cost_usd) == [0.1, 0.2]


def test_failure_rate_counts_any_non_done_status(agg: ModuleType) -> None:
    task_id_ok = "upd_hypo_1_abc123456789"
    task_id_bad = "upd_hypo_2_abc123456789"
    rows = [
        ("wf-ok", {"type": "task_start", "task_id": task_id_ok, "end_at": "2026-09-01T00:00:00Z"}),
        (
            "wf-ok",
            {
                "type": "task_end",
                "task_id": task_id_ok,
                "status": "done",
                "end_at": "2026-09-01T00:01:00Z",
            },
        ),
        (
            "wf-bad",
            {"type": "task_start", "task_id": task_id_bad, "end_at": "2026-09-01T00:00:00Z"},
        ),
        (
            "wf-bad",
            {
                "type": "task_end",
                "task_id": task_id_bad,
                "status": "stopped",
                "end_at": "2026-09-01T00:01:00Z",
            },
        ),
    ]
    attempts = agg.collect_attempts(rows)
    by_step, _ = agg.aggregate_by_step(attempts)
    stats = by_step["upd_hypo"]
    assert stats.n == 2
    assert stats.failures == 1


def test_build_step_update_omits_cache_read_when_never_recorded(agg: ModuleType) -> None:
    task_id = "gen_strat_1_abc123456789"
    rows = [
        ("wf-1", {"type": "task_start", "task_id": task_id, "end_at": "2026-09-01T00:00:00Z"}),
        ("wf-1", _agent_summary(task_id, total_cost=0.1, input_tokens=10, output_tokens=10)),
        (
            "wf-1",
            {
                "type": "task_end",
                "task_id": task_id,
                "status": "done",
                "end_at": "2026-09-01T00:01:00Z",
            },
        ),
    ]
    attempts = agg.collect_attempts(rows)
    by_step, _ = agg.aggregate_by_step(attempts)
    update = agg.build_step_update(by_step["gen_strat"])
    assert "cache_read_tokens_median" not in update
    assert update["output_tokens_median"] == 10


# ---------------------------------------------------------------------------
# yaml surgery: patch_step_chunk / rewrite_pipeline_steps_yaml
# ---------------------------------------------------------------------------

FIXTURE_YAML = """\
# A tiny fixture, shaped like data/pipeline_steps.yaml.
#
# Evidence: 2 real pipeline runs, medians per step.

evidence:
  runs_sampled: 2
  date: 2026-01-01
  method: >-
    Old method text.

levels:
  1: >-
    Easiest.

steps:
  - step: gen_strat
    group: research-reasoning
    level: 1
    n: 5
    tool_calls_median: 2
    minutes_median: 4
    cost_usd_median: 0.11
    input_tokens_median: 38620
    failure_rate: 0.0

  - step: execute.proof
    group: research-reasoning
    level: 3
    n: 0
    failure_rate: null
    note: >-
      Zero runs in the sample used this artifact type.
"""


def test_patch_step_chunk_updates_numeric_fields_only(agg: ModuleType) -> None:
    chunks = agg.split_step_chunks(FIXTURE_YAML.split("steps:\n", 1)[1])
    gen_strat_chunk = chunks[0]
    patched = agg.patch_step_chunk(
        gen_strat_chunk,
        {
            "n": 12,
            "tool_calls_median": 3,
            "minutes_median": 2,
            "cost_usd_median": 0.2,
            "input_tokens_median": 1000,
            "output_tokens_median": 500,
            "failure_rate": 0.05,
        },
    )
    parsed = yaml.safe_load("steps:\n" + patched)
    entry = parsed["steps"][0]
    assert entry["group"] == "research-reasoning"
    assert entry["level"] == 1
    assert entry["n"] == 12
    assert entry["output_tokens_median"] == 500
    # field order: output_tokens_median lands right after input_tokens_median
    keys = list(entry.keys())
    assert keys.index("output_tokens_median") == keys.index("input_tokens_median") + 1


def test_patch_step_chunk_inserts_missing_medians_before_note(agg: ModuleType) -> None:
    chunks = agg.split_step_chunks(FIXTURE_YAML.split("steps:\n", 1)[1])
    proof_chunk = chunks[1]
    patched = agg.patch_step_chunk(
        proof_chunk,
        {
            "n": 3,
            "tool_calls_median": 10,
            "minutes_median": 5,
            "cost_usd_median": 1.0,
            "input_tokens_median": 999,
            "failure_rate": 0.0,
        },
    )
    assert "note: >-" in patched
    assert patched.index("failure_rate:") < patched.index("note: >-")
    assert "Zero runs in the sample" in patched  # note text untouched


def test_rewrite_pipeline_steps_yaml_preserves_group_level_and_header(
    agg: ModuleType, tmp_path: Path
) -> None:
    fixture_path = tmp_path / "pipeline_steps.yaml"
    fixture_path.write_text(FIXTURE_YAML)

    warnings = agg.rewrite_pipeline_steps_yaml(
        path=fixture_path,
        updates={"gen_strat": {"n": 9, "tool_calls_median": 4, "failure_rate": 0.0}},
        runs_sampled=9,
        run_date="2026-09-18",
    )
    assert any("gen_strat" in w for w in warnings)

    doc = yaml.safe_load(fixture_path.read_text())
    assert doc["evidence"]["runs_sampled"] == 9
    assert str(doc["evidence"]["date"]) == "2026-09-18"
    gen_strat = next(s for s in doc["steps"] if s["step"] == "gen_strat")
    assert gen_strat["group"] == "research-reasoning"
    assert gen_strat["level"] == 1
    assert gen_strat["n"] == 9
    # untouched step keeps its original numbers
    proof = next(s for s in doc["steps"] if s["step"] == "execute.proof")
    assert proof["level"] == 3
    assert proof["n"] == 0

    text = fixture_path.read_text()
    assert text.startswith("# A tiny fixture")  # header comment survives verbatim
