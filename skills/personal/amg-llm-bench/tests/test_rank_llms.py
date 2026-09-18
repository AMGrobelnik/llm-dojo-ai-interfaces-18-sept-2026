"""The ranker turns a handful of toy models into the ordering we expect.

A fixture small enough to reason about by hand: a cheap weak model, a
dear strong one, and a middle model that is the only one with no cost
ratio, so it exercises the price-only fallback at the same time. A
fourth, `Stylish`, scores middling on the two static boards and top of
the arena board, so the family split has something to disagree about.
The rest cover the paths that keep a row out of the paid ranking — a
rejected model, a thinly covered one, a priced model on no board at
all, and a `:free` listing.
"""

import copy
import html
import importlib.util
import itertools
import math
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPT = SKILL_DIR / "scripts" / "rank_llms.py"

MODELS: dict[str, Any] = {
    "sources": {
        "toy": {
            "title": "Toy leaderboard",
            "url": "https://example.invalid/toy",
            "date": "2026-09-01",
        }
    },
    "models": [
        {
            "id": "toy/cheap",
            "name": "Cheap",
            "list_price": {"input": 0.1, "output": 0.3},
            "scores": {
                "terminal_bench_4_0": {"value": 10.0, "src": "toy"},
                "kilobench_tb2": {"value": 14.0, "src": "toy"},
                "arena_text_elo": {"value": 1400.0, "src": "toy"},
            },
            "model_scores": {"toy_shared": {"value": 2.0, "src": "toy"}},
            "reference": True,
        },
        {
            "id": "toy/middle",
            "name": "Middle",
            "list_price": {"input": 1.0, "output": 3.0},
            "scores": {
                "terminal_bench_4_0": {"value": 50.0, "src": "toy"},
                "kilobench_tb2": {"value": 54.0, "src": "toy"},
                "arena_text_elo": {"value": 1450.0, "src": "toy"},
            },
            "model_scores": {"toy_shared": {"value": 3.0, "src": "toy"}},
        },
        {
            "id": "toy/dear",
            "name": "Dear",
            "list_price": {"input": 10.0, "output": 30.0},
            "scores": {
                "terminal_bench_4_0": {"value": 90.0, "src": "toy"},
                "kilobench_tb2": {"value": 94.0, "src": "toy"},
                "arena_text_elo": {"value": 1500.0, "src": "toy"},
            },
            "model_scores": {"toy_shared": {"value": 5.0, "src": "toy"}},
        },
        {
            "id": "toy/thin",
            "name": "Thin",
            "list_price": {"input": 0.2, "output": 0.6},
            "scores": {"terminal_bench_4_0": {"value": 99.0, "src": "toy"}},
        },
        {
            "id": "toy/dud",
            "name": "Dud",
            "list_price": {"input": 0.1, "output": 0.1},
            "rejected": "Outputs audio as well as text, so out of scope.",
            "rejected_short": "audio output",
            "scores": {
                "terminal_bench_4_0": {"value": 95.0, "src": "toy"},
                "kilobench_tb2": {"value": 95.0, "src": "toy"},
            },
        },
        {
            "id": "toy/middle:free",
            "name": "Middle (free)",
            "free": True,
            "free_of": "toy/middle",
            "scores": {
                "terminal_bench_4_0": {"value": 50.0, "src": "toy"},
                "kilobench_tb2": {"value": 54.0, "src": "toy"},
                "arena_text_elo": {"value": 1450.0, "src": "toy"},
            },
        },
        {
            "id": "toy/stylish",
            "name": "Stylish",
            "list_price": {"input": 1.2, "output": 3.6},
            "created": "2026-05-01",
            "scores": {
                "terminal_bench_4_0": {"value": 50.0, "src": "toy"},
                "kilobench_tb2": {"value": 54.0, "src": "toy"},
                "arena_text_elo": {"value": 1500.0, "src": "toy"},
            },
            "model_scores": {"toy_shared": {"value": 3.2, "src": "toy"}},
        },
        {
            "id": "toy/sliver",
            "name": "Sliver",
            "list_price": {"input": 1.0, "output": 3.0},
            # The whole preference pillar, and capability answered
            # by the model-level board alone: four boards across both
            # pillars, so it is scored on the thinnest evidence that
            # still clears every bar.
            "scores": {
                "arena_text_elo": {"value": 1500.0, "src": "toy"},
                "arena_style_elo": {"value": 1500.0, "src": "toy"},
                "arena_long_elo": {"value": 1500.0, "src": "toy"},
            },
            "model_scores": {"toy_shared": {"value": 4.0, "src": "toy"}},
        },
        {
            "id": "toy/unseen",
            "name": "Unseen",
            "list_price": {"input": 0.5, "output": 1.5},
            "created": "2026-08-14",
            "evidence": "none",
        },
        {
            "id": "toy/onlyfree:free",
            "name": "Only Free",
            "free": True,
            "free_of": None,
            "scores": {
                "terminal_bench_4_0": {"value": 30.0, "src": "toy"},
                "kilobench_tb2": {"value": 30.0, "src": "toy"},
                "arena_text_elo": {"value": 1380.0, "src": "toy"},
            },
        },
    ],
}
RATIOS = {
    "cost_ratios": [
        {
            "model_a": "toy/dear",
            "model_b": "toy/cheap",
            "ratio": 4.0,
            "benchmark": "toy",
            "source": "https://example.invalid/toy",
            "date": "2026-09-01",
        }
    ],
    "effort_ratios": [],
}
GROUPS: dict[str, Any] = {
    "calibrated_intelligence_weights": {
        "price_cheapness": 1 / 3,
        "cost_per_task_cheapness": 1 / 3,
        "task_fit": 1 / 3,
    },
    "shrinkage": {},
    "benchmark_meta": {
        "terminal_bench_4_0": {
            "label": "Terminal-Bench 4.0",
            "measures": "Long-horizon terminal work.",
            "trust": "Too new to have leaked; one harness, one vendor.",
        },
        "kilobench_tb2": {
            "label": "KiloBench",
            "measures": "Cost per solved task.",
            "trust": "Self-published by the harness vendor.",
        },
        "arena_text_elo": {
            "label": "Toy arena Elo",
            "measures": "Blind human preference.",
            "trust": "No answer key to leak; length confounds it.",
        },
        "arena_style_elo": {
            "label": "Toy style arena Elo",
            "measures": "Blind human preference, style controlled.",
            "trust": "No answer key to leak; a thin panel votes it.",
        },
        "arena_long_elo": {
            "label": "Toy long-query arena Elo",
            "measures": "Blind human preference on long prompts.",
            "trust": "No answer key to leak; length is the prompt.",
        },
        "toy_shared": {
            "label": "Toy model-level board",
            "measures": "One score per model, whatever effort it ran at.",
            "trust": "Published per model, so it says nothing about effort.",
        },
    },
    "groups": {
        "toy-group": {
            "rationale": "One toy group.",
            "steps": ["toy_step"],
            "pillars": {
                # Half shares for the two thin arena boards, so the
                # fixture carries the weighted case as well as the even
                # one: a pillar's members split its half equally only
                # where the group hands out no numbers.
                "preference": {
                    "arena_text_elo": 1.0,
                    "arena_style_elo": 0.5,
                    "arena_long_elo": 0.5,
                },
                "capability": [
                    "terminal_bench_4_0",
                    "kilobench_tb2",
                    "toy_shared",
                ],
            },
        }
    },
}
STEPS = {
    "steps": [
        {
            "step": "toy_step",
            "group": "toy-group",
            "level": 3,
            "tool_calls_median": 9,
            "cost_usd_median": 1.0,
        }
    ]
}


def load_script() -> ModuleType:
    """Import rank_llms.py by path, without touching sys.path."""
    spec = importlib.util.spec_from_file_location("rank_llms", SCRIPT)
    if spec is None or spec.loader is None:
        raise AssertionError(f"cannot import {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(name="rank")
def rank_fixture() -> ModuleType:
    return load_script()


@pytest.fixture(name="data_dir")
def data_dir_fixture(tmp_path: Path) -> Path:
    for name, payload in (
        ("models.yaml", MODELS),
        ("cost_ratios.yaml", RATIOS),
        ("task_groups.yaml", GROUPS),
        ("pipeline_steps.yaml", STEPS),
    ):
        (tmp_path / name).write_text(yaml.safe_dump(payload), encoding="utf-8")
    return tmp_path


def test_blended_price_weights_output_three_to_one(rank: ModuleType) -> None:
    models, reference = rank.build_models(MODELS)
    assert reference == "toy/cheap"
    blended = {m.id: m.blended for m in models}
    assert math.isclose(blended["toy/cheap"], (0.1 + 3 * 0.3) / 4)
    assert math.isclose(blended["toy/dear"], (10.0 + 3 * 30.0) / 4)


def test_cost_solve_anchors_the_reference_and_skips_the_unreached(
    rank: ModuleType,
) -> None:
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], "toy/cheap")
    assert math.isclose(solved["toy/cheap"], 1.0)
    assert math.isclose(solved["toy/dear"], 4.0, rel_tol=1e-6)
    assert "toy/middle" not in solved


def test_price_only_model_falls_back_to_price_cheapness(
    rank: ModuleType,
) -> None:
    models, reference = rank.build_models(MODELS)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], reference)
    dear = next(m for m in models if m.id == "toy/dear")
    rank.apply_prices(models, reference)
    for model in models:
        model.rel_cost = solved.get(model.id)
        model.price_only = model.rel_cost is None
    rank.score_models(models, GROUPS)
    middle = next(m for m in models if m.id == "toy/middle")
    assert middle.price_only
    # A price-only row has two of the three thirds, renormalised over
    # themselves: list-price cheapness and the min-max-scaled fit, and
    # nothing invented for the cost per task it does not have.
    cheap = next(m for m in models if m.id == "toy/cheap")
    price_cheap = (math.log(dear.blended) - math.log(middle.blended)) / (
        math.log(dear.blended) - math.log(cheap.blended)
    )
    fits = [m.fit["toy-group"] for m in rank.rankable(models) if "toy-group" in m.fit]
    scaled = (middle.fit["toy-group"] - min(fits)) / (max(fits) - min(fits))
    expected = (price_cheap + scaled) / 2
    assert math.isclose(middle.calibrated_intelligence["toy-group"], expected, rel_tol=1e-6)


def test_end_to_end_run_writes_every_report(
    rank: ModuleType, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        ["rank_llms.py", "--data-dir", str(data_dir), "--out-dir", str(out), "--quiet"],
    )
    rank.main()
    report = (out / "ranking.md").read_text(encoding="utf-8")
    page = (out / "frontiers.html").read_text(encoding="utf-8")
    assert "Cheap" in report and "Dear" in report
    # Thin is cheap and leads the heaviest board in the pool, and one
    # board is not a score: the frontier is drawn without it, and it is
    # named apart instead of placed on a number it never earned.
    assert "Cheap (default) -> Sliver (default) -> Dear (default)" in report
    assert "Thin" not in report.split("Pareto frontier")[1].split("\n")[0]
    assert "least-measured models" in report
    assert "models not scored in this group" in page
    # Self-contained: charts, behaviour and style all inline, and not one
    # request off the file the page is opened from.
    assert "<svg" in page and "<script" in page
    assert "src=" not in page.split("<body")[0]
    assert "@import" not in page and "http-equiv" not in page
    evidence = (out / "evidence.md").read_text(encoding="utf-8")
    assert "# Evidence behind the ranking" in evidence
    assert "https://example.invalid/toy" in evidence
    for text in (report, evidence):
        for line in text.splitlines():
            if line.startswith("|"):
                assert len(line) <= rank.MAX_TABLE_WIDTH, line


def scored(rank: ModuleType) -> list:
    """The toy catalogue, run through the whole scoring pass."""
    models, reference = rank.build_models(MODELS)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], reference)
    rank.apply_prices(models, reference)
    for model in models:
        model.rel_cost = solved.get(model.id)
        model.price_only = model.rel_cost is None
    rank.score_models(models, GROUPS)
    return models


def test_rejected_model_keeps_its_row_but_leaves_every_ranking(
    rank: ModuleType,
) -> None:
    models = scored(rank)
    dud = next(m for m in models if m.id == "toy/dud")
    assert dud.rejected_short == "audio output"
    # Scored high enough to top the table, and still nowhere in it.
    assert not dud.calibrated_intelligence and not dud.fit
    assert dud.id not in {m.id for m in rank.pareto_front(models, "toy-group")}
    assert "Dud" not in {row[0] for row in rank.group_rows(models, "toy-group", set())}


def test_a_one_board_model_is_named_and_never_scored(
    rank: ModuleType,
) -> None:
    """One flattering board buys a mention, not a number.

    Thin leads the highest-weight board in the pool, so any method that
    filled its four missing boards in from anywhere would hand it the
    group. It has one measured board, which is not enough to tell an
    ability from one lucky reading, so it is named under the group with
    the board it has and given no score at all.
    """
    models = scored(rank)
    thin = next(m for m in models if m.id == "toy/thin")
    assert thin.boards["toy-group"] == 1
    assert math.isclose(thin.cover["toy-group"], 1 / 6)
    assert "toy-group" not in thin.fit
    assert "toy-group" not in thin.band
    assert "toy-group" not in thin.calibrated_intelligence
    # Named in the group's own note, with the board it does have.
    unranked = rank.not_enough_boards(rank.rankable(models), "toy-group")
    assert thin.key in {m.key for m in unranked}
    assert thin.name not in {row[0] for row in rank.group_rows(models, "toy-group", set())}


def test_no_row_is_scored_above_its_own_best_measured_board(
    rank: ModuleType,
) -> None:
    """The whole point: a score is reachable from the row's own cells."""
    models = scored(rank)
    for model in rank.rankable(models):
        cells = model.normed.get("toy-group") or {}
        if "toy-group" not in model.fit or not cells:
            continue
        assert model.fit["toy-group"] <= max(cells.values()) + 1e-6, model.name


def test_the_fit_agrees_with_the_boards_two_rows_share(
    rank: ModuleType,
) -> None:
    """The sanity check the additive fit exists to pass."""
    models = scored(rank)
    agreed, compared = rank.overlap_agreement(rank.rankable(models), "toy-group")
    assert compared >= 3
    assert agreed == compared


def test_a_row_measured_on_hard_boards_is_not_beaten_by_an_easy_one(
    rank: ModuleType,
) -> None:
    """Two rows, no board in common, compared through a third.

    `hard` and `easy` share nothing. Averaging each over its own boards
    would put `easy` on top, because its boards are the generous ones.
    The board levels take that generosity out, and the chain through
    `both` — which sits on all four — is what compares them.
    """
    cells = {
        "hard": {"a": 60.0, "b": 62.0},
        "easy": {"c": 80.0, "d": 82.0},
        "both": {"a": 50.0, "b": 52.0, "c": 90.0, "d": 92.0},
    }
    weights = dict.fromkeys("abcd", 0.25)
    fit = rank.solve_ability(cells, weights)
    assert fit.score["hard"] > fit.score["both"] > fit.score["easy"]
    # `both` is 10 under `hard` on the two boards they share and 10 over
    # `easy` on the other two, so the chain puts 20 between the ends.
    assert fit.score["hard"] - fit.score["easy"] == pytest.approx(20.0)


def test_a_disconnected_piece_is_anchored_on_its_own_boards(
    rank: ModuleType,
) -> None:
    """Two islands with no shared board still land on one scale."""
    cells = {
        "left": {"a": 40.0, "b": 60.0},
        "right": {"c": 40.0, "d": 60.0},
    }
    weights = dict.fromkeys("abcd", 0.25)
    fit = rank.solve_ability(cells, weights)
    # Nothing connects them, so neither may be declared the better: both
    # sit at the mean of the boards that anchored their own piece.
    assert fit.score["left"] == pytest.approx(fit.score["right"])


def test_fit_scale_spans_every_scored_variant(rank: ModuleType) -> None:
    models = scored(rank)
    fits = {m.id: m.fit["toy-group"] for m in models if "toy-group" in m.fit}
    # Dear leads every board it is on; Cheap is last on every board.
    assert fits["toy/dear"] > fits["toy/middle"] > fits["toy/cheap"]
    assert min(fits.values()) >= 0.0
    assert max(fits.values()) <= 100.0
    # And the row with one board is not in the scale at all.
    assert "toy/thin" not in fits


def test_free_listing_is_priced_by_its_paid_sibling_and_never_zero(
    rank: ModuleType,
) -> None:
    models, _ = rank.build_models(MODELS)
    twin = next(m for m in models if m.id == "toy/middle:free")
    orphan = next(m for m in models if m.id == "toy/onlyfree:free")
    paid = next(m for m in models if m.id == "toy/middle")
    assert twin.paid_listing == "toy/middle"
    assert not twin.free_only
    assert math.isclose(twin.blended, paid.blended)
    assert orphan.free_only and orphan.paid_listing is None
    assert all(m.blended > 0.0 for m in models if not m.free_only)


def test_free_pool_is_its_own_table_ordered_by_fit(rank: ModuleType) -> None:
    models = scored(rank)
    rows = rank.free_rows(models)
    assert [row[0] for row in rows] == ["Middle (free)", "Only Free"]
    assert [row[-1] for row in rows] == ["paid", "none"]
    # A slug reads its paid sibling's number, to the decimal: the two
    # endpoints serve the same weights, and a pool of a handful of
    # slugs shares too few boards to fit anything of its own.
    paid = next(m for m in models if m.id == "toy/middle")
    assert float(rows[0][1]) == pytest.approx(paid.fit["toy-group"], abs=0.05)
    # And a slug with no paid sibling inherits nothing rather than a
    # number the pool made up for it.
    assert rows[1][1] == "none"
    free_ids = {m.id for m in models if m.free}
    assert not free_ids & {m.id for m in rank.pareto_front(models, "toy-group")}
    assert not any(m.calibrated_intelligence for m in models if m.free)


def rendered_page(rank: ModuleType) -> str:
    """The whole HTML page, built from the toy catalogue."""
    models = scored(rank)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], "toy/cheap")
    names = [*GROUPS["groups"], rank.OVERALL]
    markdown = rank.render_markdown(
        models,
        names,
        GROUPS,
        "toy/cheap",
        STEPS,
        cuts=rank.build_cuts(models, [*GROUPS["groups"]]),
    )
    return rank.render_html(
        models,
        names,
        GROUPS,
        markdown,
        MODELS["sources"],
        RATIOS,
        solved,
        "toy/cheap",
    )


def test_every_benchmark_shows_a_linked_source_and_a_raw_table(
    rank: ModuleType,
) -> None:
    page = rendered_page(rank)
    url = MODELS["sources"]["toy"]["url"]
    for label in ("Terminal-Bench 4.0", "KiloBench"):
        # The board is named, its raw scores are broken out, and the
        # dated page they came from is one click away.
        assert f"{label} — raw scores" in page
        assert f'<a href="{url}">Toy leaderboard</a>' in page
    boards = {
        board for members in GROUPS["groups"]["toy-group"]["pillars"].values() for board in members
    }
    assert page.count("raw score") >= len(boards)
    # Raw and normalised side by side is the point of the table.
    assert "<th>raw score</th><th>normalised (0-100)</th>" in page


def test_the_page_explains_itself_and_drills_down_per_model(
    rank: ModuleType,
) -> None:
    page = rendered_page(rank)
    assert "How to judge this" in page
    assert "Cost per task evidence" in page and "Price evidence" in page
    assert "Per-model drilldown" in page
    # Every model gets a block, rejected and free listings included.
    for name in ("Cheap", "Dear", "Dud", "Middle (free)"):
        assert f"<summary>{name}" in page
    assert "Outputs audio as well as text" in page
    # Words, not markers, and no leftover single-letter flags.
    assert "price-only" in page
    assert "measured boards" in page and "ability band" in page
    assert "below coverage guard" not in page
    assert "<th>cov</th>" not in page and "<th>eff cost</th>" not in page


def test_the_explanations_are_prose_and_never_a_formula(
    rank: ModuleType,
) -> None:
    """The author reads this page. Nothing on it is written in algebra."""
    models = scored(rank)
    names = [*GROUPS["groups"], rank.OVERALL]
    markdown = rank.render_markdown(
        models,
        names,
        GROUPS,
        "toy/cheap",
        STEPS,
        cuts=rank.build_cuts(models, [*GROUPS["groups"]]),
    )
    page = rendered_page(rank)
    judge = page.split("<details id=judge>")[1].split("</details>")[0]
    for text in (judge, markdown):
        squeezed = " ".join(text.split()).lower()
        for token in ("c/(c+k)", "c / (c + k)", "w =", "(1 - w)", "1 - w)", "fit ="):
            assert token not in squeezed, token
    # A config key may be named in code voice; an equation may not.
    for chunk in judge.split("<code>")[1:]:
        assert "=" not in chunk.split("</code>")[0]


def test_the_reader_facing_words_are_the_current_ones(
    rank: ModuleType,
) -> None:
    """The two headline terms were renamed; nothing prints the old ones."""
    models = scored(rank)
    names = [*GROUPS["groups"], rank.OVERALL]
    markdown = rank.render_markdown(
        models,
        names,
        GROUPS,
        "toy/cheap",
        STEPS,
        cuts=rank.build_cuts(models, [*GROUPS["groups"]]),
    )
    page = rendered_page(rank)
    for text in (page, markdown):
        low = text.lower()
        assert "task" + " fit" not in low
        assert "calibrated" + " intelligence" not in low
        assert "raw capability" in low
        assert "capability per cost" in low
    # The new name must not read as a division.
    assert "equal thirds" in page.lower()


def test_evidence_markdown_carries_the_same_numbers(rank: ModuleType) -> None:
    models = scored(rank)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], "toy/cheap")
    names = [*GROUPS["groups"], rank.OVERALL]
    text = rank.render_evidence(
        models, names, GROUPS, MODELS["sources"], RATIOS, solved, "toy/cheap"
    )
    assert "## toy-group" in text
    for label in ("Terminal-Bench 4.0", "KiloBench"):
        assert f"### {label}" in text
    assert "## Cost per task evidence" in text
    assert "## Where the fit disagrees with the overlap" in text
    assert "## Price evidence" in text
    assert "## Per-model drilldown" in text
    # Sources are numbered once at the foot rather than inlined, which
    # is what keeps the tables inside the width limit.
    assert "1. Toy leaderboard (2026-09-01)" in text
    assert f"   <{MODELS['sources']['toy']['url']}>" in text
    for line in text.splitlines():
        if line.startswith("|"):
            assert len(line) <= rank.MAX_TABLE_WIDTH, line


def test_priced_model_with_no_evidence_is_appendix_only(rank: ModuleType) -> None:
    models = scored(rank)
    unseen = next(m for m in models if m.id == "toy/unseen")
    assert unseen.no_evidence and unseen.created == "2026-08-14"
    # Priced, so it has a blended price; unevidenced, so nothing else.
    assert unseen.blended > 0.0
    assert not unseen.fit and not unseen.calibrated_intelligence
    assert unseen.id not in {m.id for m in rank.rankable(models)}
    assert unseen.id not in {m.id for m in rank.pareto_front(models, "toy-group")}
    assert "Unseen" not in {row[0] for row in rank.group_rows(models, "toy-group", set())}
    # It appears once, in the appendix: a count and a collapsed table.
    appendix = "\n".join(rank.no_evidence_md(models))
    assert "**1** priced candidates" in appendix
    assert "<details>" in appendix and "| Unseen | 1.250 | 2026-08-14 |" in appendix
    # And it never reaches a chart.
    assert "Unseen" not in rank.svg_chart(rank.rankable(models), "toy-group", "t")


def test_group_table_splits_raw_capability_into_its_two_pillars(
    rank: ModuleType,
) -> None:
    models = scored(rank)
    rows = {row[0]: row for row in rank.group_rows(models, "toy-group", set())}
    # Stylish is mid-table on both capability boards and level with Dear
    # and Sliver at the top of the arena board — three of the five
    # plotted variants on one Elo. Min-max called that 100 and read the
    # row far above its capability column, a disagreement manufactured
    # by putting the pool's most common value at the end of the scale.
    # On the median/IQR scale the value three of five share *is* the
    # median, so every column reads 50 and the disagreement was the
    # scale's, not the model's.
    stylish = next(m for m in models if m.name == "Stylish")
    split = stylish.pillar_fit["toy-group"]
    assert set(split) == {"preference", "capability"}
    assert all(math.isclose(value, 50.0, abs_tol=1e-6) for value in split.values())
    # Raw capability is the mean of the pillars, so a row level on both
    # is level overall — neither pillar outvotes the other by holding
    # more boards.
    assert math.isclose(stylish.fit["toy-group"], 50.0, abs_tol=1e-6)
    assert rows["Stylish"][6:8] == ["50.0", "50.0"]
    # The boards still separate what they can: Middle sits under that
    # tie on the arena board and just under it on the capability ones,
    # and the two columns say exactly that.
    middle = next(m for m in models if m.name == "Middle")
    agree = middle.pillar_fit["toy-group"]
    assert math.isclose(agree["preference"], 33.3333, rel_tol=1e-4)
    assert math.isclose(agree["capability"], 48.8889, rel_tol=1e-4)
    assert math.isclose(middle.fit["toy-group"], 41.1111, rel_tol=1e-4)
    # Sliver holds the whole preference pillar and answers capability
    # on one model-level board, so its raw capability is the mean of
    # the two — never one pillar counted twice for holding more boards.
    assert rows["Sliver"][6] == "50.0"
    assert math.isclose(
        next(m for m in models if m.name == "Sliver").fit["toy-group"],
        (50.0 + 62.2222) / 2,
        rel_tol=1e-4,
    )
    # Every row carries what stands behind its number: the share of the
    # group's weight measured, the boards that was, and the band.
    assert rows["Sliver"][4] == "0.67"
    assert rows["Sliver"][8] == "4 of 6"
    assert rows["Sliver"][9].startswith("+/-")


def dense_catalogue(count: int) -> dict:
    """A pool too big to label: cheaper models are strictly better.

    Price climbs and every board score falls with the index, so the
    frontier is the first model alone and capability-per-cost order
    is index order. One Anthropic row is priced high and scored mid, so
    it is neither on the frontier nor in the top ten by calibrated
    intelligence — the only thing that can
    label it is the flagship rule.
    """
    models = [
        {
            "id": f"toy/m{index:02d}",
            "name": f"M{index:02d}",
            "list_price": {"input": 0.1 * (index + 1), "output": 0.3 * (index + 1)},
            "scores": {
                "terminal_bench_4_0": {"value": 90.0 - 2.0 * index, "src": "toy"},
                "kilobench_tb2": {"value": 90.0 - 2.0 * index, "src": "toy"},
                "arena_text_elo": {"value": 1500.0 - 2.0 * index, "src": "toy"},
            },
            **({"reference": True} if index == 0 else {}),
        }
        for index in range(count)
    ]
    models.append(
        {
            "id": "anthropic/toy",
            "name": "Anthropic Toy",
            "list_price": {"input": 9.0, "output": 27.0},
            "scores": {
                "terminal_bench_4_0": {"value": 60.0, "src": "toy"},
                "kilobench_tb2": {"value": 60.0, "src": "toy"},
                "arena_text_elo": {"value": 1470.0, "src": "toy"},
            },
        }
    )
    return {"sources": MODELS["sources"], "models": models}


def test_the_frontier_is_always_labelled_and_every_point_may_be(
    rank: ModuleType,
) -> None:
    catalogue = dense_catalogue(30)
    models, reference = rank.build_models(catalogue)
    rank.apply_prices(models, reference)
    for model in models:
        model.price_only = True
    rank.score_models(models, GROUPS)
    points = rank.rankable(models)
    front = rank.pareto_front(points, "toy-group")
    front_ids = {m.key for m in front}
    # No point is barred from a label any more: the ring carries the
    # uncertainty the hollow dot used to, without hiding the name.
    assert {m.key for m in rank.label_pool(points, front_ids, "toy-group")} == {
        m.key for m in points
    }
    chart = rank.svg_chart(points, "toy-group", "crowded")
    for model in front:
        assert f">{html.escape(model.short)}</text>" in chart
    # Every point keeps a hover card, labelled or not, and a dot.
    assert chart.count("data-name=") == len(points)
    rings = sum(1 for m in points if 1.0 - m.cover["toy-group"] > 0.08)
    # One dot each, four legend swatches, one legend ring, one ring per
    # point with a visible share of the group left unmeasured.
    assert chart.count("<circle") == len(points) + 5 + rings


#: The toy catalogue plus a dirt-cheap listing entered on the three
#: lowest-weight boards: enough of them to be scored, and 0.35 of the
#: group's weight, so it is under the bar a frontier row has to clear.
WISP_MODELS = {
    "sources": MODELS["sources"],
    "models": [
        *MODELS["models"],
        {
            "id": "toy/wisp",
            "name": "Wisp",
            "list_price": {"input": 0.01, "output": 0.03},
            "scores": {
                "kilobench_tb2": {"value": 94.0, "src": "toy"},
                "arena_style_elo": {"value": 1500.0, "src": "toy"},
                "arena_long_elo": {"value": 1500.0, "src": "toy"},
            },
        },
    ],
}


def wisp_scored(rank: ModuleType) -> list:
    """The toy catalogue plus Wisp, run through the whole scoring pass."""
    models, reference = rank.build_models(WISP_MODELS)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], reference)
    rank.apply_prices(models, reference)
    for model in models:
        model.rel_cost = solved.get(model.id)
        model.price_only = model.rel_cost is None
    rank.score_models(models, GROUPS)
    return models


def test_a_row_on_too_little_weight_may_not_anchor_the_frontier(
    rank: ModuleType,
) -> None:
    """The cheapest point on the page is not always allowed to hold it."""
    models = wisp_scored(rank)
    points = rank.rankable(models)
    wisp = next(m for m in points if m.id == "toy/wisp")
    # Three boards is enough to be scored and 0.39 of the group's weight
    # is not enough to anchor the one line a reader traces.
    assert wisp.boards["toy-group"] == rank.MIN_MEASURED_BOARDS
    assert math.isclose(wisp.cover["toy-group"], 1 / 6 + 1 / 8 + 1 / 8)
    assert wisp.cover["toy-group"] < rank.DEFAULT_FRONTIER_MIN_WEIGHT
    assert wisp.frontier_ok["toy-group"] is False
    # It is still a scored, ranked, plotted row with a hover card.
    assert "toy-group" in wisp.calibrated_intelligence
    assert wisp.name in {row[0] for row in rank.group_rows(models, "toy-group", set())}
    chart = rank.svg_chart(points, "toy-group", "thin")
    assert f'data-name="{wisp.name}"' in chart
    # Cheapest by an order of magnitude, so nothing can beat it on cost:
    # lift the bar and it holds the cheap end of every frontier.
    for model in points:
        model.frontier_ok["toy-group"] = True
    assert wisp.key in {m.key for m in rank.pareto_front(points, "toy-group")}
    for model in points:
        model.frontier_ok["toy-group"] = model.cover.get("toy-group", 0.0) >= 0.5
    front = rank.pareto_front(points, "toy-group")
    assert wisp.key not in {m.key for m in front}
    # And what is left is exactly the frontier of the same points with
    # Wisp gone: barring a row removes it, it does not reshape the line.
    without = [m for m in points if m.id != "toy/wisp"]
    for model in without:
        model.frontier_ok["toy-group"] = True
    assert [m.key for m in front] == [m.key for m in rank.pareto_front(without, "toy-group")]


def test_a_barred_row_says_so_and_is_drawn_apart(rank: ModuleType) -> None:
    """The reader is told which rows the line was not allowed to touch."""
    models = wisp_scored(rank)
    points = rank.rankable(models)
    wisp = next(m for m in points if m.id == "toy/wisp")
    status = wisp.status("toy-group")
    assert any(word.startswith("too thin for the frontier") for word in status)
    assert "42% of the group's weight, under 50%" in status[0]
    assert "on frontier" not in status and "off frontier" not in status
    chart = rank.svg_chart(points, "toy-group", "thin")
    assert "thin-dot" in chart
    assert ">too thin for the frontier</text>" in chart
    # However short the fold, every barred row is named in it.
    thinnest = rank.least_measured(points, "toy-group", count=1)
    assert wisp.key in {m.key for m in thinnest}


def test_the_frontier_bar_is_a_share_and_the_run_stops_if_it_is_not(
    rank: ModuleType,
) -> None:
    """A share outside 0 to 1 is a typo, not a setting."""
    assert rank.frontier_min_weight({}) == rank.DEFAULT_FRONTIER_MIN_WEIGHT
    assert rank.frontier_min_weight({"shrinkage": {"frontier_min_weight": 0.0}}) == 0.0
    assert rank.frontier_min_weight({"shrinkage": {"frontier_min_weight": 1.0}}) == 1.0
    for bad in (-0.1, 1.5, 50):
        with pytest.raises(SystemExit) as caught:
            rank.frontier_min_weight({"shrinkage": {"frontier_min_weight": bad}})
        assert "between 0 and 1" in str(caught.value)


def test_the_board_bar_is_a_count_and_the_run_stops_if_it_is_not(
    rank: ModuleType,
) -> None:
    """A share of the weight is not the whole question a frontier asks.

    A group whose weight sits on a handful of wide boards can put a row
    over the weight bar on one of them, and one board is a reading
    rather than a position. So the second bar is a count of the row's
    own boards, and a count that is not a whole number of at least one
    is a typo the run refuses to guess at.
    """
    assert rank.frontier_min_boards({}) == rank.DEFAULT_FRONTIER_MIN_BOARDS
    assert rank.DEFAULT_FRONTIER_MIN_BOARDS == 2
    assert rank.frontier_min_boards({"shrinkage": {"frontier_min_boards": 5}}) == 5
    for bad in (0, -2, 1.5, "2", True, None):
        with pytest.raises(SystemExit) as caught:
            rank.frontier_min_boards({"shrinkage": {"frontier_min_boards": bad}})
        assert "whole number of at least 1" in str(caught.value)
    # The skill's own settings carry both bars, so neither is a default
    # nobody chose.
    live = yaml.safe_load((SKILL_DIR / "data" / "task_groups.yaml").read_text(encoding="utf-8"))
    assert set(live["shrinkage"]) == {"frontier_min_weight", "frontier_min_boards"}
    assert rank.frontier_min_boards(live) >= 2


def test_a_board_cell_may_not_invent_an_effort_the_catalogue_denies(
    rank: ModuleType,
) -> None:
    """A capture measures a level; only the catalogue says one exists.

    A board row tagged with an effort no source sells would otherwise
    conjure a whole ranked row out of that one board — priced, placed
    against its siblings and plotted — on evidence that is one
    leaderboard's label. So the cell is dropped and named in the
    findings, and declaring the effort in `models.yaml` is what brings
    it back.
    """
    raw = copy.deepcopy(MODELS)
    by_id = {entry["id"]: entry for entry in raw["models"]}
    by_id["toy/dial"] = {
        "id": "toy/dial",
        "name": "Dial",
        "list_price": {"input": 1.0, "output": 3.0},
        "scores_by_effort": {"high": {"terminal_bench_4_0": {"value": 60.0, "src": "toy"}}},
    }
    raw["models"].append(by_id["toy/dial"])
    efforts = rank.declared_efforts(raw, {"effort_ratios": []})
    assert efforts["toy/dial"] == {"", "high"}
    board = rank.Board(
        key="arena_text_elo",
        title="Toy text Elo",
        unit="elo",
        higher_is_better=True,
        per_effort=True,
        transform="",
        source_key="board:toy:arena_text_elo",
    )
    cells = {
        "arena_text_elo": {
            "toy/dial@high": 1500.0,
            "toy/dial@ultra": 1600.0,
            "toy/nobody@high": 1700.0,
        }
    }
    dropped = rank.apply_boards(raw, {"arena_text_elo": board}, cells, efforts)
    # The declared effort is written; the undeclared one and the unknown
    # id are both dropped, and both are named for the report.
    assert by_id["toy/dial"]["scores_by_effort"]["high"]["arena_text_elo"]["value"] == 1500.0
    assert "ultra" not in by_id["toy/dial"]["scores_by_effort"]
    assert dropped == ["toy/dial@ultra", "toy/nobody@high"]
    # Declare the level and the same cell lands, because the objection
    # was never to the board.
    raw = copy.deepcopy(raw)
    by_id = {entry["id"]: entry for entry in raw["models"]}
    by_id["toy/dial"]["efforts"] = ["ultra"]
    efforts = rank.declared_efforts(raw, {"effort_ratios": []})
    dropped = rank.apply_boards(raw, {"arena_text_elo": board}, cells, efforts)
    assert by_id["toy/dial"]["scores_by_effort"]["ultra"]["arena_text_elo"]["value"] == 1600.0
    assert dropped == ["toy/nobody@high"]


def test_a_crowded_chart_labels_more_than_the_frontier_but_not_everything(
    rank: ModuleType,
) -> None:
    catalogue = dense_catalogue(90)
    models, reference = rank.build_models(catalogue)
    rank.apply_prices(models, reference)
    for model in models:
        model.price_only = True
    rank.score_models(models, GROUPS)
    points = rank.rankable(models)
    front = rank.pareto_front(points, "toy-group")
    chart = rank.svg_chart(points, "toy-group", "crowded")
    drawn = chart.count('<text class="lbl')
    assert len(front) < drawn < len(points)
    # The count under the chart is the count of labels actually drawn.
    assert f"{drawn} of {len(points)} points are labelled" in chart


def test_every_table_is_sortable_and_the_page_carries_a_contents_list(
    rank: ModuleType,
) -> None:
    page = rendered_page(rank)
    assert "<nav id=toc" in page and 'href="#drilldown"' in page
    assert 'href="#boards-toy-group"' in page and 'href="#g-toy-group"' in page
    # The group table arrives sorted by raw capability, and the page
    # says so, so the first click flips rather than re-sorts.
    assert 'data-sorted="2:desc"' in page
    assert "sortBy(table, index)" in page


def test_benchmarks_used_table_names_every_board_behind_a_group(
    rank: ModuleType,
) -> None:
    page = rendered_page(rank)
    assert "Benchmarks used" in page
    for column in ("style control", "models covered", "what would make it wrong"):
        assert f"<th>{column}</th>" in page
    # The pillar, the style-control note and the trust note come
    # straight from the two data files, never from the script.
    for pillar in ("preference", "capability"):
        assert f"<td>{pillar}</td>" in page
    assert "<td>not applicable</td>" in page
    benchmark_meta = GROUPS["benchmark_meta"]
    assert isinstance(benchmark_meta, dict)
    terminal_bench_4_0 = benchmark_meta["terminal_bench_4_0"]
    assert isinstance(terminal_bench_4_0, dict)
    trust = terminal_bench_4_0["trust"]
    assert isinstance(trust, str)
    assert trust.split(";")[0] in page


MUTE_MODELS: dict[str, Any] = copy.deepcopy(MODELS)
MUTE_MODELS["models"].append(
    {
        "id": "toy/mute",
        "name": "Mute",
        "list_price": {"input": 1.0, "output": 3.0},
        # The whole preference pillar and not one capability board, not
        # even a model-level one: three measured boards, and still only
        # one kind of witness.
        "scores": {
            "arena_text_elo": {"value": 1500.0, "src": "toy"},
            "arena_style_elo": {"value": 1500.0, "src": "toy"},
            "arena_long_elo": {"value": 1500.0, "src": "toy"},
        },
    }
)


def mute_scored(rank: ModuleType) -> list:
    """The toy catalogue plus Mute, run through the whole scoring pass."""
    models, reference = rank.build_models(MUTE_MODELS)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], reference)
    rank.apply_prices(models, reference)
    for model in models:
        model.rel_cost = solved.get(model.id)
        model.price_only = model.rel_cost is None
    rank.score_models(models, GROUPS)
    return models


def test_a_row_that_answers_one_pillar_is_named_not_scored(
    rank: ModuleType,
) -> None:
    """One kind of witness is a reading, not a ranking.

    Mute holds the whole preference pillar — three measured boards,
    enough to be read on its own — and no capability board at all. Two
    pillars is the floor, so it is not scored, ranked or plotted; it is
    named under the group with the boards it has and the bar it missed.
    """
    models = mute_scored(rank)
    mute = next(m for m in models if m.name == "Mute")
    assert mute.boards["toy-group"] == rank.MIN_MEASURED_BOARDS
    assert mute.pillars_missing["toy-group"] == ["capability"]
    assert "toy-group" not in mute.fit
    assert "Mute" not in {row[0] for row in rank.group_rows(models, "toy-group", set())}
    unranked = rank.not_enough_boards(rank.rankable(models), "toy-group")
    assert "Mute" in {m.name for m in unranked}
    # The reason is printed, because the two bars fail differently: Mute
    # has boards enough and one pillar, Thin has neither.
    assert rank.unranked_reason(mute, "toy-group") == "no capability board"
    thin = next(m for m in models if m.name == "Thin")
    assert rank.unranked_reason(thin, "toy-group") == (
        f"under {rank.MIN_MEASURED_BOARDS} measured boards"
    )
    # A model carrying both pillars keeps both columns and says nothing.
    full = next(m for m in models if m.name == "Middle")
    assert set(full.pillar_fit["toy-group"]) == {"preference", "capability"}
    assert "toy-group" not in full.pillars_missing


def test_a_model_level_board_answers_a_pillar_it_is_not_measured_in(
    rank: ModuleType,
) -> None:
    """A per-model board is evidence about the pillar, not about the effort.

    Sliver holds the whole preference pillar and answers capability on
    one model-level board. That is enough for the pillar — a board is
    evidence however light — and it is not a board measured at any
    reasoning effort, so it cannot buy the row the measured boards it
    needs.
    """
    models = scored(rank)
    sliver = next(m for m in models if m.name == "Sliver")
    assert sliver.boards["toy-group"] == 4
    assert set(sliver.pillar_fit["toy-group"]) == {"preference", "capability"}
    assert "toy-group" not in sliver.pillars_missing
    assert math.isclose(sliver.pillar_fit["toy-group"]["capability"], 62.2222, rel_tol=1e-4)
    rows = {row[0]: row for row in rank.group_rows(models, "toy-group", set())}
    assert rows["Sliver"][6] != "-" and rows["Sliver"][7] != "-"
    # Every board it has is still in the fit of its own pillar.
    assert set(sliver.normed["toy-group"]) == {
        "arena_text_elo",
        "arena_style_elo",
        "arena_long_elo",
        "toy_shared",
    }
    assert sliver.cover["toy-group"] == pytest.approx(2 / 3)


def test_group_tables_put_the_frontier_first(rank: ModuleType) -> None:
    models = scored(rank)
    front = rank.pareto_front(models, "toy-group")
    front_ids = {m.id for m in front}
    ordered = rank.group_order(models, "toy-group", front_ids)
    # The frontier takes the top of the table; inside it and after it,
    # raw-capability order.
    assert front_ids and {m.id for m in ordered[: len(front)]} == front_ids
    assert [m.fit["toy-group"] for m in ordered[: len(front)]] == sorted(
        (m.fit["toy-group"] for m in front), reverse=True
    )
    rest = ordered[len(front) :]
    assert [m.fit["toy-group"] for m in rest] == sorted(
        (m.fit["toy-group"] for m in rest), reverse=True
    )
    # No row is split off any more: every scored row is in one table.
    assert {m.name for m in ordered} == {
        m.name for m in models if "toy-group" in m.fit and not m.free
    }


def test_the_least_measured_fold_lists_the_thinnest_rows_first(
    rank: ModuleType,
) -> None:
    models = scored(rank)
    ranked = rank.rankable(models)
    thinnest = rank.least_measured(ranked, "toy-group", count=2)
    covers = [m.cover["toy-group"] for m in thinnest]
    assert covers == sorted(covers)
    # Sliver carries 0.55 of the group's weight; the rest carry 0.90.
    assert thinnest[0].name == "Sliver"
    # The fold is for rows that were scored. A row with too few boards
    # is not thin evidence, it is no evidence, and it is named apart.
    assert "Thin" not in {m.name for m in thinnest}
    assert "Thin" in {m.name for m in rank.not_enough_boards(ranked, "toy-group")}


#: A second toy catalogue for the effort axis: one model a source split
#: by effort, one it did not, and the reference to price them against.
EFFORT_MODELS = {
    "sources": MODELS["sources"],
    "models": [
        {
            "id": "toy/cheap",
            "name": "Cheap",
            "list_price": {"input": 0.1, "output": 0.3},
            "scores": {
                "terminal_bench_4_0": {"value": 10.0, "src": "toy"},
                "kilobench_tb2": {"value": 14.0, "src": "toy"},
                "arena_text_elo": {"value": 1400.0, "src": "toy"},
                "arena_style_elo": {"value": 1400.0, "src": "toy"},
            },
            "reference": True,
        },
        {
            "id": "toy/dial",
            "name": "Dial",
            "list_price": {"input": 2.0, "output": 6.0},
            "default_effort": "high",
            "scores": {
                "terminal_bench_4_0": {"value": 60.0, "src": "toy"},
                "kilobench_tb2": {"value": 64.0, "src": "toy"},
                "arena_text_elo": {"value": 1460.0, "src": "toy"},
                "arena_style_elo": {"value": 1460.0, "src": "toy"},
            },
            "scores_by_effort": {
                "low": {"terminal_bench_4_0": {"value": 40.0, "src": "toy"}},
            },
        },
        {
            "id": "toy/flat",
            "name": "Flat",
            "list_price": {"input": 1.0, "output": 3.0},
            "scores": {
                "terminal_bench_4_0": {"value": 50.0, "src": "toy"},
                "kilobench_tb2": {"value": 54.0, "src": "toy"},
                "arena_text_elo": {"value": 1450.0, "src": "toy"},
                "arena_style_elo": {"value": 1450.0, "src": "toy"},
            },
        },
    ],
}
EFFORT_RATIOS = {
    "cost_ratios": [
        {
            "model_a": "toy/dial",
            "model_b": "toy/cheap",
            "ratio": 3.0,
            "benchmark": "toy",
            "source": "https://example.invalid/toy",
            "date": "2026-09-01",
        }
    ],
    "effort_ratios": [
        {
            "model": "toy/dial",
            "effort_a": "low",
            "effort_b": "high",
            "ratio": 0.25,
            "source": "https://example.invalid/toy",
            "date": "2026-09-01",
        }
    ],
}


def effort_variants(rank: ModuleType) -> list:
    """The effort catalogue, expanded, priced and scored."""
    models, reference = rank.build_models(EFFORT_MODELS)
    variants = rank.expand_efforts(models, EFFORT_RATIOS)
    solved = rank.solve_relative_cost(EFFORT_RATIOS["cost_ratios"], reference)
    rank.apply_prices(variants, reference)
    rank.apply_costs(variants, solved)
    rank.score_models(variants, GROUPS)
    return variants


def test_effort_ladder_expands_one_model_into_one_point_per_effort(
    rank: ModuleType,
) -> None:
    models, _ = rank.build_models(EFFORT_MODELS)
    variants = rank.expand_efforts(models, EFFORT_RATIOS)
    keys = [m.key for m in variants]
    # An effort-specific board row and a published effort multiplier each
    # buy a point of their own; nothing else does.
    assert keys == ["toy/cheap", "toy/dial@high", "toy/dial@low", "toy/flat"]
    names = {m.key: m.name for m in variants}
    assert names["toy/dial@low"] == "Dial (low)"
    assert names["toy/dial@high"] == "Dial (high)"
    # A model no source splits keeps its single row, labelled with the
    # effort it was run at where that is known and (default) where it is not.
    assert names["toy/flat"] == "Flat (default)"
    low = next(m for m in variants if m.key == "toy/dial@low")
    high = next(m for m in variants if m.key == "toy/dial@high")
    assert low.scores["terminal_bench_4_0"] == 40.0
    assert high.scores["terminal_bench_4_0"] == 60.0
    # The untagged rows belong to the default-effort variant alone. The
    # boards low was never run on stay missing: nothing is carried over
    # from the high row, by a ratio or otherwise.
    assert set(low.scores) == {"terminal_bench_4_0"}
    assert set(high.scores) == {
        "terminal_bench_4_0",
        "kilobench_tb2",
        "arena_text_elo",
        "arena_style_elo",
    }


def test_an_unmeasured_effort_is_named_and_never_filled_in(
    rank: ModuleType,
) -> None:
    """The bug this method exists to stop, in the small.

    Dial was run at low effort on one board only. Moving its high-effort
    rows down by a ratio gave the low row four boards it never sat on,
    and a score built on them. It still has the one board it was run on:
    the number it gets now is Dial (high) on the three boards *it* sat,
    moved by the distance between the two on the single board they
    share. Nothing is carried over board by board, and the boards low
    never sat stay out of its own cells.
    """
    variants = effort_variants(rank)
    low = next(m for m in variants if m.key == "toy/dial@low")
    high = next(m for m in variants if m.key == "toy/dial@high")
    flat = next(m for m in variants if m.key == "toy/flat")
    assert low.boards["toy-group"] == 1
    assert low.anchored["toy-group"] == high.key
    assert low.placement["toy-group"] == (
        "placed relative to Dial (high) on 1 shared board in the capability pillar"
    )
    assert set(low.normed["toy-group"]) == {"terminal_bench_4_0"}
    # 40 against 60 on the board they share, so low lands below high.
    assert low.fit["toy-group"] < high.fit["toy-group"]
    # The gap was measured in the capability pillar, so that is the only
    # pillar it moves: the preference column is the anchor's own reading,
    # unshifted, because nothing was measured about the distance there.
    assert low.pillar_fit["toy-group"]["capability"] < high.pillar_fit["toy-group"]["capability"]
    assert math.isclose(
        low.pillar_fit["toy-group"]["preference"],
        high.pillar_fit["toy-group"]["preference"],
    )
    # And it inherits none of the anchor's standing: one board of its
    # own is under both frontier bars, and the status names both.
    assert low.frontier_ok["toy-group"] is False
    bar = low.frontier_bar["toy-group"]
    assert "1 board of its own, under 2" in bar
    assert "17% of the group's weight, under 50%" in bar
    assert low.key not in {
        m.key for m in rank.not_enough_boards(rank.rankable(variants), "toy-group")
    }
    # The rows that were measured are scored, and on their own cells.
    assert high.cover["toy-group"] == pytest.approx(1 / 3 + 1 / 4 + 1 / 8)
    assert flat.cover["toy-group"] == pytest.approx(1 / 3 + 1 / 4 + 1 / 8)
    assert high.boards["toy-group"] == 4 and flat.boards["toy-group"] == 4
    # A measured value is never overwritten.
    assert low.scores["terminal_bench_4_0"] == 40.0


def test_effort_multiplier_moves_cost_and_never_the_list_price(
    rank: ModuleType,
) -> None:
    variants = effort_variants(rank)
    low = next(m for m in variants if m.key == "toy/dial@low")
    high = next(m for m in variants if m.key == "toy/dial@high")
    # The rate card does not change with how hard the model thinks.
    assert low.blended == high.blended
    assert low.rel_price == high.rel_price
    assert math.isclose(high.effort_cost, 1.0)
    assert math.isclose(low.effort_cost, 0.25, rel_tol=1e-6)
    assert math.isclose(low.rel_cost, 0.25 * high.rel_cost, rel_tol=1e-6)
    # Effective cost is the geometric mean, so a quarter of the cost per
    # task moves the point half way, not all the way.
    assert math.isclose(low.eff_cost, 0.5 * high.eff_cost, rel_tol=1e-6)


def test_evidence_none_row_keeps_the_scores_it_carries(rank: ModuleType) -> None:
    """`evidence: none` means no scores, so a row with both is a data error.

    The tag used to drop the row whatever it held, which quietly deleted
    every board on a model somebody had since scored. Now the data wins
    over the label and the run says which labels disagreed with it.
    """
    payload = {
        "sources": MODELS["sources"],
        "models": [
            dict(MODELS["models"][0]),
            {
                "id": "toy/mislabelled",
                "name": "Mislabelled",
                "list_price": {"input": 1.0, "output": 3.0},
                "evidence": "none",
                "scores": {"terminal_bench_4_0": {"value": 70.0, "src": "toy"}},
            },
            {
                "id": "toy/blank",
                "name": "Blank",
                "list_price": {"input": 1.0, "output": 3.0},
                "evidence": "none",
            },
        ],
    }
    models, _ = rank.build_models(payload)
    kept = next(m for m in models if m.id == "toy/mislabelled")
    blank = next(m for m in models if m.id == "toy/blank")
    assert not kept.no_evidence
    assert kept.scores["terminal_bench_4_0"] == 70.0
    assert blank.no_evidence
    assert kept in rank.rankable(models)
    assert blank not in rank.rankable(models)


def test_an_alias_is_folded_into_its_snapshot_and_leaves_the_ranking(
    rank: ModuleType,
) -> None:
    """One purchasable endpoint is one point, not two thin ones."""
    payload = {
        "sources": MODELS["sources"],
        "models": [
            dict(MODELS["models"][0]),
            {
                "id": "toy/snap-0813",
                "name": "Snap (0813)",
                "list_price": {"input": 2.0, "output": 6.0},
                "scores": {"terminal_bench_4_0": {"value": 60.0, "src": "toy"}},
            },
            {
                "id": "toy/snap",
                "name": "Snap",
                "alias_of": "toy/snap-0813",
                "list_price": {"input": 9.0, "output": 27.0},
                "scores": {
                    "terminal_bench_4_0": {"value": 11.0, "src": "toy"},
                    "kilobench_tb2": {"value": 64.0, "src": "toy"},
                },
            },
        ],
    }
    models, _ = rank.build_models(payload)
    snapshot = next(m for m in models if m.id == "toy/snap-0813")
    alias = next(m for m in models if m.id == "toy/snap")
    # The alias's extra board is folded in; the dated row's own value and
    # its own price both stand.
    assert snapshot.scores == {"terminal_bench_4_0": 60.0, "kilobench_tb2": 64.0}
    assert snapshot.blended == pytest.approx((2.0 + 3 * 6.0) / 4)
    assert alias.alias_of == "toy/snap-0813"
    assert alias not in rank.rankable(models)
    assert snapshot in rank.rankable(models)


def test_a_group_that_does_not_add_up_stops_the_run(rank: ModuleType) -> None:
    """A weight map summing to anything but 1 used to be renormalised.

    That kept every score right and every declared share wrong, with no
    way to tell which weight was meant to be lower. Pillars make the sum
    arithmetic rather than editorial — each is renormalised over its own
    members and then takes an equal share — so the check is now a guard
    against the arithmetic, and the editorial mistake it used to catch
    is unwritable.
    """
    with pytest.raises(SystemExit, match=r"sum to 0\.6000"):
        rank.check_weight_sum("group toy-group", 0.6)
    groups = copy.deepcopy(GROUPS)
    groups["groups"]["toy-group"]["pillars"] = {
        "preference": {"arena_text_elo": 2.0, "arena_style_elo": 6.0},
        "capability": ["terminal_bench_4_0"],
    }
    weights = rank.group_weights(groups, "toy-group")
    # Declared 2 and 6, so a quarter and three quarters of a half.
    assert weights == pytest.approx(
        {"arena_text_elo": 0.125, "arena_style_elo": 0.375, "terminal_bench_4_0": 0.5}
    )
    groups["groups"]["toy-group"]["pillars"]["nonsense"] = ["terminal_bench_4_0"]
    with pytest.raises(SystemExit, match=r"nonsense"):
        rank.group_weights(groups, "toy-group")


def test_price_blend_is_read_from_the_yaml_and_labelled(rank: ModuleType) -> None:
    """The output weight is one number in the data, not a constant."""
    assert rank.price_blend({}) == (rank.DEFAULT_OUTPUT_WEIGHT, "assumed")
    groups = {"price_blend": {"output_weight": 1.0, "basis": "measured"}}
    weight, basis = rank.price_blend(groups)
    assert (weight, basis) == (1.0, "measured")
    price = {"input": 2.0, "output": 6.0}
    assert rank.blended_price(price, weight) == pytest.approx(4.0)
    assert rank.blended_price(price) == pytest.approx(5.0)


def test_a_step_is_scored_on_its_group_s_own_weights(rank: ModuleType) -> None:
    """A step points at a group; there is nothing left for it to override.

    A step used to be able to re-split its group, which meant a weight
    map no group-level guard ever saw. Three equal pillars leave nothing
    to re-split, so every step in a group is scored on that group's map
    and the group is the only thing weighted.
    """
    groups = copy.deepcopy(GROUPS)
    groups["groups"]["toy-group"]["steps"] = ["toy_step", "picky_step"]
    assert rank.step_groups(groups) == {"toy_step": "toy-group", "picky_step": "toy-group"}
    models, reference = rank.build_models(MODELS)
    rank.apply_prices(models, reference)
    names = rank.score_models(models, groups)
    assert names == ["toy-group", rank.OVERALL]
    ranked = rank.rankable(models)
    picks = rank.best_by_band(ranked, "toy-group")
    assert picks
    front = {m.key for m in rank.pareto_front(ranked, "toy-group")}
    assert all(pick.on_frontier == (pick.model.key in front) for pick in picks.values())
    assert any(pick.on_frontier for pick in picks.values())


def test_a_pillar_with_no_board_measured_is_absent_not_average(
    rank: ModuleType,
) -> None:
    """Silence in a pillar is reported, never filled in at the middle.

    One measured board answers a pillar's question; none leaves it
    unanswered, and the row's raw capability is the mean of the pillars
    that did answer. Filling the gap with the pool's middle would say
    "average here" about evidence nobody collected.
    """
    weights = {"pref_a": 0.25, "pref_b": 0.25, "cap_a": 0.25, "cap_b": 0.25}
    pillars = {
        "pref_a": "preference",
        "pref_b": "preference",
        "cap_a": "capability",
        "cap_b": "capability",
    }
    present, missing = rank.pillars_present({"pref_a": 70.0, "cap_a": 50.0}, weights, pillars)
    assert present == ["capability", "preference"]
    assert missing == []
    # One board is an answer, however light that board is in the group.
    present, missing = rank.pillars_present({"pref_b": 50.0}, weights, pillars)
    assert present == ["preference"]
    assert missing == ["capability"]
    # And with two pillars, one answered pillar is not a ranking: the
    # floor is both, so a row like that is named rather than scored.
    assert rank.MIN_MEASURED_PILLARS == 2


def test_a_model_level_board_is_not_a_board_measured_at_this_effort(
    rank: ModuleType,
) -> None:
    """A per-model number describes the model, not one of its efforts.

    Some boards publish one number per model however hard it is asked
    to think. Such a board reaches every effort variant, so it answers
    that variant's pillar, and it is a board measured at none of them:
    it cannot buy a thin row the three measured boards it needs, and
    two siblings both carrying it have not thereby shared a board.
    """
    models = scored(rank)
    sliver = next(m for m in models if m.id == "toy/sliver")
    assert sliver.shared == {"toy_shared": 4.0}
    assert sliver.scores["toy_shared"] == 4.0
    # It answers the capability pillar — a board is evidence however
    # light — while the three measured boards it has are all preference.
    assert "capability" in sliver.pillar_fit["toy-group"]
    assert "toy-group" not in sliver.pillars_missing
    assert sliver.boards["toy-group"] == 4
    measured = set(sliver.normed["toy-group"]) - set(sliver.shared)
    assert len(measured) == rank.MIN_MEASURED_BOARDS


def board_file(tmp_path: Path, name: str, body: dict) -> Path:
    """Write one `data/boards/<name>.yaml` under a throwaway data dir."""
    folder = tmp_path / "boards"
    folder.mkdir(exist_ok=True)
    path = folder / f"{name}.yaml"
    path.write_text(yaml.safe_dump(body, sort_keys=True), encoding="utf-8")
    return path


def test_a_captured_board_replaces_the_catalogue_cell_it_covers(
    rank: ModuleType, tmp_path: Path
) -> None:
    """The capture is reproducible; the hand-kept catalogue is not.

    `data/models.yaml` is where a number goes when nobody has automated
    pulling it. Once a capture script does, the board file is the same
    column measured again, so it replaces that column wherever it
    reaches — untagged row and effort rows alike — rather than landing
    beside a stale number and letting the two average. Boards no
    capture carries are left exactly as the catalogue has them.
    """
    board_file(
        tmp_path,
        "arena",
        {
            "source": {
                "title": "Toy Arena",
                "url": "https://example.invalid/arena",
                "captured": "2026-09-17",
                "method": "playwright scrape",
            },
            "boards": {
                "arena_text_elo": {
                    "title": "Toy text Elo",
                    "unit": "elo",
                    "higher_is_better": True,
                    "style_control": True,
                    "values": {"toy/cheap": 1490.0, "toy/dear@low": 1410.0},
                }
            },
        },
    )
    boards, cells, sources = rank.load_boards(tmp_path)
    assert set(boards) == {"arena_text_elo"}
    assert boards["arena_text_elo"].per_effort is True
    assert cells["arena_text_elo"] == {"toy/cheap": 1490.0, "toy/dear@low": 1410.0}
    # Every cell cites the board file's own source block, so a reader
    # lands on the page and the date the number was taken from.
    key = boards["arena_text_elo"].source_key
    assert sources[key]["date"] == "2026-09-17"
    assert sources[key]["url"] == "https://example.invalid/arena"
    assert sources[key]["method"] == "playwright scrape"
    assert sources[key]["title"] == "Toy Arena - Toy text Elo"
    assert sources[key]["style_control"] is True
    raw = copy.deepcopy(MODELS)
    rank.apply_boards(raw, boards, cells)
    by_id = {entry["id"]: entry for entry in raw["models"]}
    assert by_id["toy/cheap"]["scores"]["arena_text_elo"] == {"value": 1490.0, "src": key}
    # The catalogue's own boards, which no capture covers, are untouched.
    assert by_id["toy/cheap"]["scores"]["terminal_bench_4_0"]["src"] == "toy"
    # An effort-tagged cell lands on that effort and nowhere else.
    dear = by_id["toy/dear"]
    assert dear["scores_by_effort"]["low"]["arena_text_elo"]["value"] == 1410.0
    assert "arena_text_elo" not in dear.get("scores", {})


def test_a_model_level_board_lands_on_the_model_not_an_effort(
    rank: ModuleType, tmp_path: Path
) -> None:
    """A board about the whole model is read as being about the model.

    A source that publishes one number per model however hard it was
    asked to think says so in its board file, and the cell then goes on
    a shelf of its own rather than onto the default-effort row (which
    would hand one effort a number about all of them) or onto every
    effort row (which would let it pass for a measurement of an effort
    nobody ran). A column whose raw unit spans orders of magnitude asks
    for `transform: log10` in the same place, and gets it.
    """
    board_file(
        tmp_path,
        "toy_model_level",
        {
            "source": {
                "title": "Toy model-level source",
                "url": "https://example.invalid/model-level",
                "captured": "2026-09-17",
                "method": "data api",
            },
            "boards": {
                "toy_shared": {
                    "title": "Toy model-level board",
                    "unit": "count",
                    "higher_is_better": True,
                    "per_effort": False,
                    "transform": "log10",
                    "values": {"toy/cheap": 1000.0, "toy/dear": 10.0, "toy/gone": 0.0},
                },
                "toy_latency": {
                    "title": "Toy latency",
                    "unit": "seconds",
                    "higher_is_better": False,
                    "values": {"toy/cheap": 2.0},
                },
            },
        },
    )
    boards, cells, _ = rank.load_boards(tmp_path)
    # Per-effort is the default, because that is what a leaderboard row
    # is; a board is read as model-level only where the file says so.
    assert boards["toy_shared"].per_effort is False
    assert boards["toy_latency"].per_effort is True
    assert boards["toy_shared"].transform == "log10"
    assert cells["toy_shared"] == {"toy/cheap": 3.0, "toy/dear": 1.0}
    # Zero has no log, and is not zero evidence either: a model outside
    # the published window is unmeasured, so the cell is dropped rather
    # than floored.
    assert "toy/gone" not in cells["toy_shared"]
    # A board scored the other way round is negated, so every column in
    # the fit reads higher-is-better.
    assert cells["toy_latency"] == {"toy/cheap": -2.0}
    raw = copy.deepcopy(MODELS)
    rank.apply_boards(raw, boards, cells)
    by_id = {entry["id"]: entry for entry in raw["models"]}
    assert by_id["toy/cheap"]["model_scores"]["toy_shared"]["value"] == 3.0
    assert "toy_shared" not in by_id["toy/cheap"]["scores"]
    # And every effort variant of that model carries it, on the shelf
    # that keeps it out of the per-effort board count.
    models, _ = rank.build_models(raw)
    for model in [m for m in models if m.id == "toy/cheap"]:
        assert model.shared["toy_shared"] == 3.0
        assert model.scores["toy_shared"] == 3.0


def test_one_board_may_not_come_from_two_captures(rank: ModuleType, tmp_path: Path) -> None:
    """Two files claiming one column is two numbers for one question.

    Whichever loaded last would silently win, and the page would cite a
    source that did not produce the number beside it.
    """
    for name in ("aa", "arena"):
        board_file(
            tmp_path,
            name,
            {
                "source": {"title": name, "url": f"https://example.invalid/{name}"},
                "boards": {"shared_board": {"unit": "index", "values": {"toy/cheap": 1.0}}},
            },
        )
    with pytest.raises(SystemExit, match="shared_board"):
        rank.load_boards(tmp_path)


def test_no_boards_directory_is_a_warning_and_the_catalogue_alone(
    rank: ModuleType, tmp_path: Path
) -> None:
    """A checkout with no captures yet still ranks on models.yaml."""
    boards, cells, sources = rank.load_boards(tmp_path)
    assert (boards, cells, sources) == ({}, {}, {})
    raw = copy.deepcopy(MODELS)
    rank.apply_boards(raw, boards, cells)
    assert raw == MODELS


def test_no_pillar_holds_one_measurement_twice(rank: ModuleType) -> None:
    """Two boards in one pillar must not be the same column twice.

    `aa_hle` restated Humanity's Last Exam and `aa_gpqa_diamond`
    restated GPQA Diamond under a better-sourced key, so a model
    carrying both had one measurement counted twice inside one pillar.
    The pillar caps what that can cost — a pillar is a third however
    many boards it holds — but a board counted twice still crowds out
    the boards beside it.
    """
    data = SKILL_DIR / "data"
    groups = rank.load_yaml(data / "task_groups.yaml")
    raw = rank.load_yaml(data / "models.yaml")
    boards, cells, _ = rank.load_boards(data)
    rank.apply_boards(raw, boards, cells)
    columns: dict[str, dict[str, float]] = defaultdict(dict)
    for entry in raw["models"]:
        for shelf in ("scores", "model_scores"):
            for key, cell in (entry.get(shelf) or {}).items():
                columns[key][entry["id"]] = float(cell["value"])
    for name in groups["groups"]:
        for pillar, members in rank.group_pillars(groups, name).items():
            for left, right in itertools.combinations(sorted(members), 2):
                shared = sorted(set(columns.get(left, {})) & set(columns.get(right, {})))
                if len(shared) < 3:
                    continue
                same = all(
                    math.isclose(columns[left][key], columns[right][key], rel_tol=1e-9)
                    for key in shared
                )
                assert not same, (
                    f"{left} and {right} agree on all {len(shared)} models they "
                    f"share inside the {pillar} pillar of {name}, so that is one "
                    "measurement weighted twice: drop the worse-sourced key"
                )


def test_every_declared_source_is_cited_by_something(rank: ModuleType) -> None:
    """A source list longer than the evidence reads like more evidence."""
    raw = rank.load_yaml(SKILL_DIR / "data" / "models.yaml")
    declared = set(raw["sources"])
    cited = rank.source_citations(raw)
    assert not sorted(cited - declared), "a `src:` names no entry under `sources:`"
    assert not sorted(declared - cited), "these sources back no number: delete them"


def test_skill_md_states_the_method_and_never_the_results(rank: ModuleType) -> None:
    """Findings are generated; SKILL.md may not restate them by hand.

    The old section 9 was written after one run and quoted counts from
    it. Two rewrites later every number in it was wrong and nothing said
    so. The fix is that the section holds no numbers at all: it points at
    `results/findings.md`, which the run rebuilds.
    """
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    heading = "\n## 9. "
    start = text.index(heading)
    body = text[start + len(heading) :]
    body = body[body.index("\n") : body.index("\n## 10.")]
    assert "results/findings.md" in body
    stray = sorted({word for word in body.split() if any(c.isdigit() for c in word)})
    assert not stray, (
        "section 9 of SKILL.md carries numbers again: "
        f"{', '.join(stray)}. Findings belong in results/findings.md, which is "
        "regenerated on every run; this section states where to read them"
    )


def test_findings_are_written_and_carry_the_run_s_own_numbers(
    rank: ModuleType, data_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The findings file is generated by the same run as the ranking."""
    out = tmp_path / "out"
    monkeypatch.setattr(
        "sys.argv",
        ["rank_llms.py", "--data-dir", str(data_dir), "--out-dir", str(out), "--quiet"],
    )
    rank.main()
    findings = (out / "findings.md").read_text(encoding="utf-8")
    ranking = (out / "ranking.md").read_text(encoding="utf-8")
    assert "# What this run found" in findings
    assert "| ranked paid variants |" in findings
    assert "## Best pick per pipeline step" in ranking
    assert "**Effective cost at or under the reference**" in ranking
    for line in findings.splitlines():
        if line.startswith("|"):
            assert len(line) <= rank.MAX_TABLE_WIDTH, line


#: Which pillar each board of the placement fixture belongs to. `b1`
#: and `b2` are preference, the rest capability, so a gap can be read in
#: one pillar and be silent about the other.
PLACED_PILLARS = {
    "b1": "preference",
    "b2": "preference",
    "b3": "capability",
    "b4": "capability",
    "b5": "capability",
    "b8": "capability",
    "b9": "capability",
}


def placed(rank: ModuleType) -> tuple[list, dict[str, float], dict[str, float], dict]:
    """One family of five efforts, placed against its anchor.

    `max` is measured on five boards and is the anchor. `low` and
    `high` share three of them — two preference and one capability —
    and are built to sit four points under and four points over it
    there. `one` was measured on a single board of the group, a
    preference one, which it shares with the anchor. `apart` was
    measured on two boards the anchor was never run on. Every ability
    the fit reached starts at 70 so that any move is the placement's.
    """
    boards = ["b1", "b2", "b3", "b4", "b5"]
    cells = {
        "fam/m@max": dict.fromkeys(boards, 50.0),
        "fam/m@low": dict.fromkeys(boards[:3], 46.0),
        "fam/m@high": dict.fromkeys(boards[:3], 54.0),
    }
    # Under MIN_MEASURED_BOARDS, so the group's own fit never reached
    # these two: they are the rows placement either rescues or leaves.
    extra = {
        "fam/m@one": {"b1": 62.0},
        "fam/m@apart": {"b8": 90.0, "b9": 90.0},
    }
    models = [
        rank.Model(id="fam/m", name=f"Fam ({effort})", scores={}, effort=effort)
        for effort in ("max", "low", "high", "one", "apart")
    ]
    weights = dict.fromkeys([*boards, "b8", "b9"], 0.2)
    _, _, parts = rank.pillar_fits(cells, weights, PLACED_PILLARS)
    for part in parts.values():
        for key in part.raw:
            part.raw[key], part.raw_band[key] = 70.0, 2.0
    raw = dict.fromkeys(cells, 70.0)
    # The band of a mean of pillars, exactly as `pillar_fits` builds it,
    # so a placed row's band is comparable with its anchor's.
    band = {
        key: math.sqrt(sum(part.raw_band[key] ** 2 for part in parts.values() if key in part.raw))
        / len([part for part in parts.values() if key in part.raw])
        for key in cells
    }
    spots = rank.sibling_placements(
        models,
        cells,
        weights,
        pillars=PLACED_PILLARS,
        fits=parts,
        extra=extra,
        raw=raw,
    )
    rank.apply_placements(spots, raw, band, parts)
    return spots, raw, band, parts


def test_an_effort_variant_is_placed_by_the_boards_it_shares(rank: ModuleType) -> None:
    """The rule the ordering defect asked for, in both directions.

    The global fit has a board level and a row ability and nothing for
    the two together, so a weakness a family shares on the boards only
    one of its efforts was run on lands on that effort alone. Placing
    each sibling at the anchor's ability plus their gap on the boards
    both were measured on takes the board out of the comparison — and
    it has to work both ways, or it is a thumb on the scale for the
    variant that ran the most boards.
    """
    spots, raw, _, parts = placed(rank)
    by_key = {spot.key: spot for spot in spots}
    assert set(by_key) == {"fam/m@low", "fam/m@high", "fam/m@one", "fam/m@apart"}
    # The anchor is the most-measured variant and does not move.
    assert all(spot.anchor_key == "fam/m@max" for spot in spots)
    assert raw["fam/m@max"] == pytest.approx(70.0)
    # Below on the shared boards lands below, above lands above, each
    # by what the boards say and not by a fraction of it.
    assert by_key["fam/m@low"].gap == pytest.approx(-4.0)
    assert by_key["fam/m@high"].gap == pytest.approx(4.0)
    assert raw["fam/m@low"] == pytest.approx(66.0)
    assert raw["fam/m@high"] == pytest.approx(74.0)
    # The three shared boards span both pillars, so both pillars move,
    # and each by what its own boards measured.
    assert {part.pillar for part in by_key["fam/m@high"].parts} == {
        "preference",
        "capability",
    }
    assert parts["preference"].raw["fam/m@high"] == pytest.approx(74.0)
    assert parts["capability"].raw["fam/m@high"] == pytest.approx(74.0)
    assert by_key["fam/m@high"].note == (
        "placed relative to Fam (max) on 3 shared boards in the preference and capability pillars"
    )


def test_one_shared_board_is_a_distance_and_so_is_enough(rank: ModuleType) -> None:
    """A row the group's own fit never reached, ranked on one board.

    What a placement reads is a distance, not an ability, and a
    distance needs one board at both ends: `one` sits 12 points over
    the anchor on the single board the two share, so it lands 12 points
    over the anchor's ability — a number it has no other way of
    getting, since one board of its own cannot be told from one lucky
    reading.
    """
    spots, raw, band, parts = placed(rank)
    lone = next(spot for spot in spots if spot.key == "fam/m@one")
    assert rank.MIN_SIBLING_SHARED == 1
    assert lone.shared == 1
    assert lone.gap == pytest.approx(12.0)
    # The one board they share is a preference board, so the distance
    # is a statement about preference: that pillar moves 12 points and
    # capability, where nothing was measured about the distance, keeps
    # the anchor's own reading. The row is the mean of the two.
    assert parts["preference"].raw["fam/m@one"] == pytest.approx(82.0)
    assert parts["capability"].raw["fam/m@one"] == pytest.approx(70.0)
    assert raw["fam/m@one"] == pytest.approx(76.0)
    assert lone.note == ("placed relative to Fam (max) on 1 shared board in the preference pillar")
    # One gap has no spread of its own, so the band falls back to the
    # anchor's residual scatter rather than claiming certainty. Here
    # the anchor's own boards agree exactly, and a row whose evidence
    # is one board still cannot be narrower than its anchor.
    assert band["fam/m@one"] >= band["fam/m@max"]


def test_a_noisy_gap_is_kept_in_proportion_to_its_own_reliability(
    rank: ModuleType,
) -> None:
    """The defect this rule was written for, and what it must not do.

    Last run a medium-effort row arrived at the top of a coding group
    on one shared board the pool is near-flat on: a rounding difference
    there is worth a whole inter-quartile range up the scale, so the
    "distance" was mostly that board's noise. Each gap is now kept in
    proportion to how well the boards behind it agree — the spread of
    the real sibling gaps against the reading error — so a thin, loud
    reading is pulled toward zero while a well-measured one is left
    exactly where it was.
    """

    # Three families placed on several boards each, all agreeing that
    # siblings sit about two points apart: that is the spread of real
    # gaps, so tau is 2.
    def one_pillar(key: str, anchor: str, shared: int, gap: float, error: float) -> Any:
        """One placement whose whole distance was read in one pillar."""
        part = rank.PillarGap(pillar="capability", shared=shared, gap=gap, error=error)
        return rank.Placement(
            key=key,
            anchor_key=f"{key.split('@', maxsplit=1)[0]}@max",
            anchor=anchor,
            shared=shared,
            gap=gap,
            error=error,
            parts=(part,),
        )

    tight = [one_pillar(f"fam{i}/m@low", f"Fam{i} (max)", 4, 2.0, 0.0) for i in range(3)]
    # A fourth, read off one board whose scatter is four points, says
    # its sibling is twenty points clear.
    loud = one_pillar("loud/m@medium", "Loud (max)", 1, 20.0, 4.0)
    out = {spot.key: spot for spot in rank.shrink_placements([*tight, loud], {})}
    # tau^2 / (tau^2 + error^2) = 4 / (4 + 16) = 0.2
    assert out["loud/m@medium"].weight == pytest.approx(0.2)
    assert out["loud/m@medium"].gap == pytest.approx(4.0)
    # It is not a clamp: the direction survives, nothing is bounded,
    # and the row still lands above its anchor — by what the evidence
    # supports rather than by what one flat board said.
    assert out["loud/m@medium"].gap > 0.0
    # The well-measured placements are untouched, and say nothing extra.
    assert all(out[spot.key].gap == pytest.approx(2.0) for spot in tight)
    assert all(out[spot.key].weight == pytest.approx(1.0) for spot in tight)
    assert out[tight[0].key].note == (
        "placed relative to Fam0 (max) on 4 shared boards in the capability pillar"
    )
    # Where the shrink bites, the status says how much of the gap it
    # kept, so the number on the page is never quietly smaller than the
    # boards behind it.
    assert out["loud/m@medium"].note == (
        "placed relative to Loud (max) on 1 shared board in the capability "
        "pillar, at 20% of the measured gap"
    )
    # A family whose efforts really do differ widens tau and so keeps
    # more of the same gap: nothing here is a fixed discount.
    wide = [one_pillar(spot.key, spot.anchor, 4, 12.0, 0.0) for spot in tight]
    kept = {spot.key: spot for spot in rank.shrink_placements([*wide, loud], {})}
    assert kept["loud/m@medium"].weight > out["loud/m@medium"].weight
    # With no multi-board placement to read a spread off, the abilities
    # the group found stand in for it rather than the shrink guessing.
    only = rank.shrink_placements([loud], {"a": 40.0, "b": 50.0, "c": 60.0})
    assert 0.0 < only[0].weight < 1.0


def test_no_shared_board_leaves_the_variant_where_it_was(rank: ModuleType) -> None:
    """Nothing to read, so nothing is read.

    `apart` was run on two boards the anchor never touched. There is no
    distance between the two to measure, so it is not placed, gets no
    number out of this, and says which row it could not be compared
    with.
    """
    spots, raw, _, _ = placed(rank)
    away = next(spot for spot in spots if spot.key == "fam/m@apart")
    assert away.shared == 0
    assert away.gap is None
    assert "fam/m@apart" not in raw
    assert away.note == "no board shared with Fam (max)"


def test_a_placed_row_inherits_nothing_from_its_anchor(
    rank: ModuleType,
) -> None:
    """Whose evidence the frontier is drawn on.

    A placed row's number is its anchor's ability plus the distance
    between the two where they overlap, which is a fine way to score it
    and no way at all to earn the line a reader traces. Both bars are
    read off the row's own boards at its own effort: an anchor can hold
    the line while the sibling placed against it does not, and the
    sibling's status says which bar it fell under and whose boards it
    was placed on.
    """
    anchor = rank.Model(id="fam/m", name="Fam (max)", scores={}, effort="max")
    anchor.fit["g"] = 70.0
    anchor.cover["g"] = 0.8
    anchor.boards["g"] = 27
    anchor.board_pool["g"] = 40
    sibling = rank.Model(id="fam/m", name="Fam (low)", scores={}, effort="low")
    sibling.fit["g"] = 66.0
    sibling.cover["g"] = 0.04
    sibling.boards["g"] = 1
    sibling.board_pool["g"] = 40
    sibling.placement["g"] = (
        "placed relative to Fam (max) on 1 shared board in the capability pillar"
    )
    sibling.anchored["g"] = anchor.key
    # A second thin row, placed against nobody, is the control: the two
    # are treated alike, because the bar is about measurement and not
    # about whom a row is related to.
    alone = rank.Model(id="solo/s", name="Solo (default)", scores={})
    alone.fit["g"] = 60.0
    alone.cover["g"] = 0.04
    alone.boards["g"] = 1
    alone.board_pool["g"] = 40
    rank.mark_frontier_eligible([anchor, sibling, alone], ["g"], 0.5, 2)
    assert anchor.frontier_ok["g"] is True
    assert sibling.frontier_ok["g"] is False
    assert alone.frontier_ok["g"] is False
    assert sibling.frontier_bar["g"] == alone.frontier_bar["g"]
    assert sibling.status("g") == [
        "too thin for the frontier: 1 board of its own, under 2 and 4% of "
        "the group's weight, under 50%",
        "1 of 40 boards measured",
        "placed relative to Fam (max) on 1 shared board in the capability pillar",
    ]
    # Clearing one bar is not clearing the frontier: the status names
    # the one that is still failing, and nothing else.
    sibling.boards["g"] = 4
    rank.mark_frontier_eligible([sibling], ["g"], 0.5, 2)
    assert sibling.frontier_ok["g"] is False
    assert sibling.frontier_bar["g"] == (
        "too thin for the frontier: 4% of the group's weight, under 50%"
    )


def test_a_near_flat_board_uses_less_of_the_scale_than_a_spread_one(
    rank: ModuleType,
) -> None:
    """Why the per-board scale is the median and IQR, not the ends.

    Min-max declares every board equally discriminating before any
    weight is applied: AA-LCR, whose whole pool runs 0.803 to 0.887,
    was stretched onto the same 0-100 as a board that separates the
    pool. On the robust scale a board's span is what its own spread
    earns it.
    """
    # A near-flat board: nine readings evenly across a narrow range,
    # so its ends sit about one IQR from its median.
    flat = {f"m{i}": 0.80 + 0.01 * i for i in range(9)}
    # A board that separates: a cluster in the middle, clear leaders
    # and clear laggards, so its ends sit three IQR out.
    spread = dict(
        zip(
            [f"m{i}" for i in range(9)],
            [0.0, 0.02, 0.42, 0.46, 0.50, 0.54, 0.58, 0.98, 1.0],
            strict=True,
        )
    )
    # Min-max cannot tell the two apart: both span the whole scale.
    for column in (flat, spread):
        stretched = rank.scale_unit(column, invert=False)
        assert max(stretched.values()) - min(stretched.values()) == pytest.approx(1.0)
    # The robust scale gives the flat board a third of the scale and
    # the discriminating one all of it, so a point of agreement on the
    # flat board is worth a third of a point on the other.
    quiet, loud = rank.scale_robust(flat), rank.scale_robust(spread)
    assert quiet["m4"] == pytest.approx(50.0) and loud["m4"] == pytest.approx(50.0)
    assert max(quiet.values()) - min(quiet.values()) == pytest.approx(100.0 / rank.ROBUST_CLIP)
    assert max(loud.values()) - min(loud.values()) == pytest.approx(100.0)
    # A single runaway capture is clipped rather than setting an end.
    assert rank.scale_robust({**spread, "runaway": 40.0})["runaway"] == pytest.approx(100.0)
    # Deterministic where there is no middle half to read: the IQR is
    # zero, so half the full range stands in for it, and a column with
    # no spread at all and a lone reading both land on the middle.
    tied = {"a": 1.0, "b": 2.0, "c": 2.0, "d": 2.0, "e": 3.0}
    assert rank.scale_robust(tied)["a"] == pytest.approx(50.0 - 50.0 / rank.ROBUST_CLIP)
    assert set(rank.scale_robust(dict.fromkeys("abcd", 7.0)).values()) == {50.0}
    assert rank.scale_robust({"a": 7.0}) == {"a": 50.0}


def test_every_pair_the_fit_orders_against_its_overlap_is_named(
    rank: ModuleType,
) -> None:
    """The count says how often the fit reads the overlap, not where.

    A reader who wants to know whether to trust a row needs the pairs,
    so evidence.md lists each one with both gaps and the boards behind
    them.
    """

    def row(name: str, fit: float, value: float) -> object:
        model = rank.Model(id=f"toy/{name.lower()}", name=name, scores={})
        model.fit["g"] = fit
        model.normed["g"] = dict.fromkeys(("b1", "b2", "b3"), value)
        return model

    # Flip is ten points over Flop in the fit and eight points under it
    # on all three boards they share. Steady agrees with both.
    models = [row("Flip", 60.0, 40.0), row("Flop", 50.0, 48.0), row("Steady", 20.0, 10.0)]
    assert rank.overlap_agreement(models, "g") == (2, 3)
    found = rank.overlap_disagreements(models, "g")
    assert [(item.left, item.right, item.shared) for item in found] == [("Flip", "Flop", 3)]
    assert found[0].fitted == pytest.approx(10.0)
    assert found[0].measured == pytest.approx(-8.0)
    text = "\n".join(rank.evidence_overlap_md(models, ["g"]))
    assert "## Where the fit disagrees with the overlap" in text
    assert "2 of 3 overlapping pairs agree" in text
    assert "- Flip vs Flop: 3 shared boards, fit +10.0, shared -8.0" in text


# --------------------------------------------------------------------
# What a row has to be able to do before it may be recommended.
# --------------------------------------------------------------------


def with_requirements(floor: dict[str, Any]) -> dict[str, Any]:
    """The toy groups with one hard floor on the one group."""
    groups = copy.deepcopy(GROUPS)
    groups["groups"]["toy-group"]["requirements"] = floor
    return groups


def with_capabilities(caps: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """The toy catalogue with endpoint capabilities on some of its rows."""
    models = copy.deepcopy(MODELS)
    for entry in models["models"]:
        entry.update(caps.get(entry["id"], {}))
    return models


def scored_with(rank: ModuleType, models_yaml: dict, groups: dict) -> list:
    """The same scoring pass as `scored`, over a doctored catalogue."""
    models, reference = rank.build_models(models_yaml)
    solved = rank.solve_relative_cost(RATIOS["cost_ratios"], reference)
    rank.apply_prices(models, reference)
    for model in models:
        model.rel_cost = solved.get(model.id)
        model.price_only = model.rel_cost is None
    rank.score_models(models, groups)
    return models


def test_a_row_that_cannot_hold_the_prompt_is_ranked_but_never_bought(
    rank: ModuleType,
) -> None:
    """The strongest model on the boards, with a window a step overruns.

    It keeps its row and its number — the boards say what they say —
    and it leaves the frontier, because a frontier is a list of things
    to buy and this one cannot run the work.
    """
    groups = with_requirements(
        {"min_context_tokens": 200000, "min_max_output_tokens": 4096, "tool_calling": True}
    )
    models = scored_with(
        rank,
        with_capabilities(
            {
                "toy/dear": {
                    "context_window": 32768,
                    "max_output_tokens": 65536,
                    "tool_calling": True,
                },
                "toy/middle": {
                    "context_window": 1000000,
                    "max_output_tokens": 1024,
                    "tool_calling": False,
                },
                "toy/cheap": {
                    "context_window": 1000000,
                    "max_output_tokens": 65536,
                    "tool_calling": True,
                },
            }
        ),
        groups,
    )
    dear = next(m for m in models if m.id == "toy/dear")
    middle = next(m for m in models if m.id == "toy/middle")
    cheap = next(m for m in models if m.id == "toy/cheap")
    assert dear.requirement_gaps["toy-group"] == ["context window"]
    assert middle.requirement_gaps["toy-group"] == ["max output", "tool calling"]
    assert not cheap.requirement_gaps
    # Still ranked, and still carrying the number its boards earned.
    assert "toy-group" in dear.fit and "toy-group" in dear.calibrated_intelligence
    # And off the frontier, with the failing field named where a reader
    # meets the row.
    front = {m.id for m in rank.pareto_front(models, "toy-group")}
    assert dear.id not in front and middle.id not in front
    assert cheap.id in front
    assert any("context window" in note for note in dear.status("toy-group"))


def test_a_capability_the_catalogue_never_published_is_not_a_failure(
    rank: ModuleType,
) -> None:
    """Silence is not a measurement: an unknown field clears the floor."""
    groups = with_requirements(
        {"min_context_tokens": 200000, "min_max_output_tokens": 4096, "tool_calling": True}
    )
    models = scored_with(rank, with_capabilities({}), groups)
    assert not any(m.requirement_gaps for m in models)
    front = {m.id for m in rank.pareto_front(models, "toy-group")}
    assert front


def test_a_group_with_no_floor_declared_rules_nothing_out(
    rank: ModuleType,
) -> None:
    models = scored_with(
        rank,
        with_capabilities({"toy/dear": {"context_window": 4096, "tool_calling": False}}),
        copy.deepcopy(GROUPS),
    )
    assert not any(m.requirement_gaps for m in models)


def test_a_free_slug_takes_the_paid_row_s_scores_and_its_own_endpoint(
    rank: ModuleType,
) -> None:
    """`free_of:` is a mapping, not a merge.

    The weights are the same model, so the boards carry across whole.
    The endpoint is not the same endpoint, so the window and the
    tool-calling flag stay the free row's own — they are what the hard
    floors are checked against.
    """
    groups = with_requirements({"min_context_tokens": 200000, "tool_calling": True})
    models = scored_with(
        rank,
        with_capabilities(
            {
                "toy/middle": {
                    "context_window": 1000000,
                    "max_output_tokens": 65536,
                    "tool_calling": True,
                },
                "toy/middle:free": {
                    "context_window": 32768,
                    "max_output_tokens": 4096,
                    "tool_calling": False,
                },
            }
        ),
        groups,
    )
    paid = next(m for m in models if m.id == "toy/middle")
    slug = next(m for m in models if m.id == "toy/middle:free")
    orphan = next(m for m in models if m.id == "toy/onlyfree:free")
    assert slug.fit["toy-group"] == pytest.approx(paid.fit["toy-group"])
    assert slug.boards == paid.boards and slug.cover == paid.cover
    assert slug.band == paid.band
    # Its own endpoint, and the floors read that and not the paid one.
    assert slug.context_window == 32768
    assert not paid.requirement_gaps
    assert slug.requirement_gaps["toy-group"] == ["context window", "tool calling"]
    # No base row, nothing to inherit, and no number invented for it.
    assert orphan.free_only and "toy-group" not in orphan.fit
    # A free row never becomes a purchasable point, whatever it scores.
    assert not any(slug.frontier_ok.values()) and slug.frontier_bar
    assert slug.id not in {m.id for m in rank.pareto_front(models, "toy-group")}


# --------------------------------------------------------------------
# Cutting the presets.
# --------------------------------------------------------------------


def test_a_cut_descends_and_never_names_a_model_twice_by_padding(
    rank: ModuleType,
) -> None:
    """Every preset's four roles, read off one ladder, in order."""
    models = scored(rank)
    cuts = rank.build_cuts(models, [*GROUPS["groups"]])
    ladders = cuts["ladders"][rank.PAID_BACKEND]
    ladder = ladders["toy-group"]
    assert ladder, "the toy catalogue routes on the paid OpenRouter lane"
    # Weakest first, strictly up, and one rung per id-and-effort.
    caps = [rung["capability"] for rung in ladder]
    assert caps == sorted(caps)
    keys = [(rung["model"], rung["effort"]) for rung in ladder]
    assert len(set(keys)) == len(keys)
    order = {key: index for index, key in enumerate(keys)}
    for preset in rank.PRESETS:
        cut = cuts["presets"][preset][rank.PAID_BACKEND]["toy-group"]
        rungs = [
            order[(cut[role]["model"], cut[role]["effort"])]
            for role in ("easy", "medium", "hard", "orchestrator")
        ]
        assert rungs == sorted(rungs), f"{preset} does not descend: {rungs}"
        # The orchestrator is above the hard tier, or says why not.
        if rungs[-1] == rungs[-2]:
            assert cut["orchestrator"]["note"]


def test_a_cut_only_names_a_model_the_backend_can_dial(
    rank: ModuleType,
) -> None:
    """Each backend's own routability test, applied to its own cut."""
    models = scored(rank)
    cuts = rank.build_cuts(models, [*GROUPS["groups"]])
    # The toy ids are `vendor/model`, so the paid lane takes them and
    # the two Claude-only and free-only lanes take none of them.
    assert rank.PAID_BACKEND in cuts["ladders"]
    assert not cuts["ladders"].get(rank.CLAUDE_BACKEND)
    assert not cuts["ladders"].get(rank.FREE_BACKEND)
    for preset, backends in cuts["presets"].items():
        for backend, by_group in backends.items():
            for group, cut in by_group.items():
                for role, pick in cut.items():
                    assert rank.tier_id_routable_on(backend, pick["model"]), (
                        f"{preset}/{backend}/{group}/{role} names "
                        f"{pick['model']}, which that backend cannot dial"
                    )


def test_a_row_below_a_group_s_floor_is_never_cut_into_a_preset(
    rank: ModuleType,
) -> None:
    groups = with_requirements({"min_context_tokens": 200000})
    models = scored_with(
        rank,
        with_capabilities(
            {
                "toy/dear": {"context_window": 8192},
                "toy/cheap": {"context_window": 1000000},
                "toy/middle": {"context_window": 1000000},
            }
        ),
        groups,
    )
    cuts = rank.build_cuts(models, [*groups["groups"]])
    named = {
        pick["model"]
        for backends in cuts["presets"].values()
        for by_group in backends.values()
        for cut in by_group.values()
        for pick in cut.values()
    }
    assert "toy/dear" not in named
    assert named


def test_the_cuts_file_carries_its_own_header_and_parses(
    rank: ModuleType,
) -> None:
    models = scored(rank)
    text = rank.render_cuts(rank.build_cuts(models, [*GROUPS["groups"]]))
    assert text.startswith("# Preset cuts")
    parsed = yaml.safe_load(text)
    assert set(parsed) == {"ladders", "presets"}
    assert set(parsed["presets"]) == set(rank.PRESETS)


# --------------------------------------------------------------------
# A toggle a board does not have is not a toggle set to off.
# --------------------------------------------------------------------


def test_a_board_with_no_style_toggle_reads_not_applicable(
    rank: ModuleType,
) -> None:
    """`null` is the absence of a setting, and absence never votes.

    It used to be coerced to `False`, which printed a static capability
    board as "style control off" and turned a controlled Arena board
    "mixed" as soon as a source without the toggle joined it.
    """
    sources = {
        "static": {"title": "A board with no such toggle", "style_control": None},
        "controlled": {"title": "Arena, controlled", "style_control": True},
        "raw": {"title": "Arena, raw", "style_control": False},
        "silent": {"title": "A board that never says"},
    }
    assert rank.style_control(sources, ["static", "silent"]) == "not applicable"
    assert rank.style_control(sources, []) == "not applicable"
    assert rank.style_control(sources, ["controlled", "static"]) == "on"
    assert rank.style_control(sources, ["raw", "silent"]) == "off"
    assert rank.style_control(sources, ["controlled", "raw", "static"]) == "mixed"


def test_a_capture_without_the_toggle_records_null_not_false(
    rank: ModuleType,
) -> None:
    """The board reader keeps the difference the renderer depends on."""
    block = {"title": "Capture", "url": "u", "captured": "2026-01-01"}
    absent = rank.board_source(block, {"title": "A static board"}, "b")
    assert "style_control" not in absent
    null = rank.board_source(block, {"title": "A static board", "style_control": None}, "b")
    assert null["style_control"] is None
    on = rank.board_source(block, {"title": "Arena", "style_control": True}, "b")
    assert on["style_control"] is True


# --------------------------------------------------------------------
# md_table: the separator row must actually render.
# --------------------------------------------------------------------


def test_md_table_emits_separator_row_after_header(rank: ModuleType) -> None:
    """A copied header list broke an ``is`` identity check, so the
    ``|---|---|`` row after the header was never appended and every
    rendered table lost its markdown table formatting."""
    header = ["model", "rung", "blended $/M"]
    rows = [["gpt-5", "1", "2.50"], ["claude", "2", "3.10"]]
    out = rank.md_table(header, rows)
    assert len(out) == len(rows) + 2
    separator = out[1]
    assert set(separator) <= {"|", "-"}
    assert separator.count("|") == len(header) + 1


def test_md_table_separator_column_count_matches_header(rank: ModuleType) -> None:
    header = ["group", "preference", "capability"]
    rows = [["general", "0.5", "0.6"]]
    out = rank.md_table(header, rows)
    separator = out[1]
    assert separator.count("-") // 3 == len(header)
