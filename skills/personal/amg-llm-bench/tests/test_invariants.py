"""The audit's invariant checklist, one test per line of it.

`scratchpad/amg-llm-bench-audit.md` ended in twenty numbered invariants
— cheap assertions over the pipeline's own output that, taken together,
say the published ranking is the evidence and nothing else. Most of them
failed when they were written. They are tests now, over the real
catalogue rather than a toy one, because a toy fixture cannot fail the
ones that matter: a family cap, a coverage rule and a duplicate check
are claims about this data.

Three of the twenty could not be tested as written, and each says so
where it is implemented: I2 and I5 assumed a per-row score bounded by
that row's own boards, which an additive fit over shared boards does not
give and should not; I10 assumed a top five that no single board moves,
which the measured answer contradicts by two places. Each is tested in
the nearest form the corrected method can actually promise, and the
looser reading is reported on the findings page rather than asserted
away.
"""

import fnmatch
import importlib.util
import itertools
from pathlib import Path
from types import ModuleType
from typing import Any, NamedTuple

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.behaviour]

SKILL_DIR = Path(__file__).resolve().parent.parent
DATA = SKILL_DIR / "data"


def load_script() -> ModuleType:
    """Import rank_llms.py by path, without touching sys.path."""
    spec = importlib.util.spec_from_file_location(
        "rank_llms", SKILL_DIR / "scripts" / "rank_llms.py"
    )
    if spec is None or spec.loader is None:
        raise AssertionError("cannot import rank_llms.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Run(NamedTuple):
    """One full pass over the real catalogue, shared by every test here."""

    rank: ModuleType
    raw: dict[str, Any]
    groups: dict[str, Any]
    ratios: dict[str, Any]
    models: list[Any]
    ranked: list[Any]
    names: list[str]
    core: list[str]


@pytest.fixture(name="run", scope="module")
def run_fixture() -> Run:
    """The real pipeline, run once for the whole module.

    Every invariant below is a statement about the published ranking, so
    they all need the same 200-odd variants scored the same way. Scoring
    them per test would cost a minute; scoring them once costs a second.
    """
    rank = load_script()
    raw = rank.load_yaml(DATA / "models.yaml")
    ratios = rank.load_yaml(DATA / "cost_ratios.yaml")
    groups = rank.load_yaml(DATA / "task_groups.yaml")
    # The captured board files are the evidence the ranking runs on, so
    # an invariant read off models.yaml alone would be an invariant
    # about a catalogue nothing publishes.
    boards, cells, board_sources = rank.load_boards(DATA)
    rank.apply_boards(raw, boards, cells)
    raw.setdefault("sources", {}).update(board_sources)
    output_weight, _ = rank.price_blend(groups)
    models, reference = rank.build_models(raw, output_weight)
    rel_costs = rank.solve_relative_cost(ratios.get("cost_ratios", []), reference)
    models = rank.expand_efforts(models, ratios)
    rank.apply_prices(models, reference)
    rank.apply_costs(models, rel_costs)
    names = rank.score_models(models, groups)
    core = [n for n in names if n != rank.OVERALL]
    return Run(rank, raw, groups, ratios, models, rank.rankable(models), names, core)


# --------------------------------------------------------------------
# I1-I6: the ones that change a published conclusion.
# --------------------------------------------------------------------


def backing(run: Run, model: Any, name: str) -> list[Any]:
    """The rows whose measured boards carry `model`'s number in `name`.

    Its own row, in every ordinary case. A row placed against an effort
    sibling gets both: its number is that sibling's number moved by a
    distance the two of them measured on boards both sat, so either
    side's evidence can answer for it and the bars below take the
    better of the two.
    """
    anchor = model.anchored.get(name)
    if not anchor:
        return [model]
    return [model, next(row for row in run.models if row.key == anchor)]


def test_i1_every_ranked_row_carries_enough_measured_boards(run: Run) -> None:
    """I1 — a row is scored on at least MIN_MEASURED_BOARDS of the group,
    its own or the effort sibling it was placed against.

    Was 100 of 207 rows in coding-experiments under three boards, every
    one of them ranked, several of them on the frontier. A placed row
    is not a return of that: it needs a board it sat itself and shares
    with the sibling, and the sibling has to clear the floor on cells of
    its own for the placement to mean anything.
    """
    floor = run.rank.MIN_MEASURED_BOARDS
    for name in run.core:
        for model in run.ranked:
            if name not in model.fit:
                continue
            rows = backing(run, model, name)
            held = max(len(row.normed.get(name, {})) for row in rows)
            if len(rows) > 1:
                assert len(model.normed[name]) >= run.rank.MIN_SIBLING_SHARED, (
                    f"{model.name} is placed against {rows[1].name} in {name} "
                    f"on {len(model.normed[name])} boards of its own"
                )
            assert held >= floor, (
                f"{model.name} is scored in {name} on {held} boards, under the "
                f"{floor} it takes to be comparable at all"
            )
    # OVERALL has no cells of its own: it is the mean of the groups a row
    # is scored in, so a row reaching it has already cleared the floor.
    for model in run.ranked:
        if run.rank.OVERALL in model.fit:
            assert any(name in model.fit for name in run.core), model.name


def test_i2_a_score_rests_only_on_cells_the_row_was_measured_on(run: Run) -> None:
    """I2 — nothing borrowed, nothing imputed, nothing assumed.

    The invariant as written was "the printed fit sits inside the range
    of the row's own measured boards", which was a test for imputation
    when every gap was filled from somewhere. The additive fit has no
    gaps to fill: it solves a board level and an ability over the cells
    that exist, and an ability is deliberately not bounded by the row's
    own raw values — a model measured only on hard boards should score
    above its own raw mean, that is the whole point.

    So this tests what the method can promise: every cell entering a
    row's score is a number that row was published with.
    """
    for name in run.core:
        for model in run.ranked:
            borrowed = sorted(set(model.normed.get(name, {})) - set(model.scores))
            assert not borrowed, (
                f"{model.name} is scored in {name} on {borrowed}, which it was never measured on"
            )
            counted = model.boards.get(name, 0)
            held = len(model.normed.get(name, {}))
            assert counted == held, f"{model.name} in {name}: {counted} vs {held}"


def test_i3_a_thin_row_is_never_printed_as_a_buy(run: Run) -> None:
    """I3 — a capability-per-cost number means the evidence is there.

    Was: the top five of every group were rows under 0.35 of the group's
    weight, printed with a number and no warning. Read through
    `backing`: a row placed against an effort sibling is printed on that
    sibling's evidence, so the sibling is what has to carry the weight.
    """
    floor = run.rank.frontier_min_weight(run.groups)
    for name in run.core:
        for model in run.ranked:
            if name not in model.calibrated_intelligence:
                continue
            held = max(len(row.normed.get(name, {})) for row in backing(run, model, name))
            assert held >= run.rank.MIN_MEASURED_BOARDS, f"{model.name}: {held}"
    for name in run.names:
        for model in run.rank.pareto_front(run.ranked, name):
            cover = max(row.cover.get(name, 0.0) for row in backing(run, model, name))
            assert cover >= floor - 1e-9, (
                f"{model.name} holds a frontier in {name} on {cover:.2f} of its "
                f"weight, under {floor}"
            )


def test_i4_no_row_is_printed_above_one_that_beats_it_outright(run: Run) -> None:
    """I4 — the table's order never contradicts the frontier's axes.

    Was 0.852 against 0.743: a one-board row at the top of a table,
    above the frontier it could not reach. The fix is the order itself —
    frontier first, then raw capability, which is the axis the frontier
    is drawn on.

    Read over the rows that can hold a frontier at all. A row under the
    coverage floor is barred from the frontier by I3 and says so in its
    status column, so it can print below something it beats on these two
    axes; that is the coverage rule working, not the order failing.
    """
    for name in run.names:
        front = {m.key for m in run.rank.pareto_front(run.ranked, name)}
        ordered = [
            m
            for m in run.rank.group_order(run.ranked, name, front)
            if m.frontier_ok.get(name, True)
        ]
        assert ordered, name
        for above, below in itertools.combinations(ordered, 2):
            beaten = below.eff_cost < above.eff_cost and below.fit[name] > above.fit[name]
            assert not beaten, (
                f"in {name}, {below.name} is cheaper ({below.eff_cost:.2f} vs "
                f"{above.eff_cost:.2f}) and better ({below.fit[name]:.1f} vs "
                f"{above.fit[name]:.1f}) than {above.name}, yet prints below it"
            )


def test_i5_an_effort_is_scored_on_its_own_ladder_or_not_at_all(run: Run) -> None:
    """I5 — one effort's evidence never becomes another's.

    The invariant as written wanted a dearer effort to outscore a cheaper
    one on their shared boards. It does not, 32 of 85 comparable pairs
    over this catalogue, and that is a finding rather than a fault:
    findings.md carries it under "Effort is not monotone". What must
    hold is the thing that made the old numbers meaningless — an effort
    variant inheriting the base effort's cells and then being ranked
    against it.
    """
    for model in run.ranked:
        if not model.effort:
            continue
        for name in run.names:
            for board in model.normed.get(name, {}):
                assert board in model.scores, (
                    f"{model.name} at effort {model.effort} is scored in {name} "
                    f"on {board}, which belongs to another rung of its ladder"
                )


def test_i6_an_effort_has_a_cost_only_where_one_was_published(run: Run) -> None:
    """I6 — no effort inherits its neighbour's cost per task.

    Was: an unmeasured rung silently carried a 1.0 multiplier, which is
    the claim that thinking harder is free.
    """
    for model in run.ranked:
        if model.rel_cost is None:
            assert model.cost_gap, f"{model.name} has no cost per task and does not say so"
        assert model.price_only == (model.rel_cost is None)


# --------------------------------------------------------------------
# I7-I10: weighting hygiene.
# --------------------------------------------------------------------


def test_i7_no_two_weighted_terms_are_one_measurement(run: Run) -> None:
    """I7 and I15 — the duplicate guard, read over normalised columns.

    Six arena pairs correlated above 0.98 and every one of them carried
    its own full weight; scientific-writing was 0.44 of one opinion poll
    counted four times. The guard compares PILLARS now rather than
    boards, because the fix for correlated boards inside a pillar is
    the pillar itself: four Arena columns share one third between them
    however tightly they agree. What is left to catch is the same
    measurement filed as two different kinds of evidence.
    """
    found = run.rank.duplicate_terms(run.ranked, run.groups)
    assert not found, "\n".join(
        f"{group}: {left} and {right} correlate at {value:.3f} over {shared} "
        "shared variants, so they are one measurement weighted twice"
        for group, left, right, value, shared in found
    )


def test_i7_the_duplicate_guard_catches_one_board_in_two_pillars(run: Run) -> None:
    """The guard has to fail on the shape that would smuggle one in.

    A board named in two pillars is one measurement wearing two hats,
    and with two pillars it would take the whole group instead of half.
    """
    groups = run.rank.load_yaml(DATA / "task_groups.yaml")
    pillars = groups["groups"]["scientific-writing"]["pillars"]
    pillars["capability"] = list(pillars["preference"])
    found = run.rank.duplicate_terms(run.ranked, groups)
    assert {(left, right) for _, left, right, _, _ in found} >= {("capability", "preference")}


def test_i8_no_evaluation_family_decides_a_group(run: Run) -> None:
    """I8 — one benchmark under several names is still one benchmark.

    Terminal-Bench was 0.710 of coding-experiments across three keys,
    which made that group a Terminal-Bench ranking with another name on
    it.
    """
    guards = run.rank.weight_guards(run.groups)
    assert guards, "task_groups.yaml declares no weight_guards: the cap is not enforced"
    families = run.rank.eval_families(run.groups)
    for name in run.core:
        weights = run.rank.group_weights(run.groups, name)
        for family, share in run.rank.family_totals(weights, families).items():
            assert share <= guards["max_family_share"] + run.rank.WEIGHT_TOLERANCE, (
                f"{name}: the {family} family carries {share:.3f}"
            )
        for board, share in weights.items():
            assert share <= guards["max_board_weight"] + run.rank.WEIGHT_TOLERANCE, (
                f"{name}: {board} carries {share:.3f} on its own"
            )


def test_i8_a_step_reads_its_group_s_weights_and_no_others(run: Run) -> None:
    """There is no per-step override left to smuggle anything past.

    A step used to be able to re-split its group, which meant a weight
    map the group-level guards never saw. A group is two equal
    pillars now and a step is a pointer to one, so the map a step is
    scored on is its group's map, checked once.
    """
    families = run.rank.eval_families(run.groups)
    cap = run.rank.weight_guards(run.groups)["max_family_share"]
    for step, group in run.rank.step_groups(run.groups).items():
        weights = run.rank.group_weights(run.groups, group)
        worst = max(run.rank.family_totals(weights, families).values())
        assert worst <= cap + run.rank.WEIGHT_TOLERANCE, f"{step} reaches {worst:.3f}"


def test_i8_every_pipeline_step_maps_to_exactly_one_group(run: Run) -> None:
    """Every measured step is scored, and no step is scored twice.

    `data/pipeline_steps.yaml` is the list of steps the pipeline
    actually runs; `data/task_groups.yaml` says which group scores
    each one, by name or by a `gen_plan.*` style pattern. A step no
    group claims would be published with no model behind it, and a
    step two groups claim would have two different best picks, so both
    are errors rather than a footnote. The two files also have to
    agree: `pipeline_steps.yaml` records the group per step as well,
    and a disagreement means one of them was edited alone.
    """
    steps = run.rank.load_yaml(DATA / "pipeline_steps.yaml").get("steps") or []
    assert steps, "pipeline_steps.yaml lists no steps"
    patterns = run.rank.step_groups(run.groups)
    for entry in steps:
        step = str(entry["step"])
        hit = sorted({g for p, g in patterns.items() if fnmatch.fnmatchcase(step, p)})
        assert len(hit) == 1, f"{step} maps to {hit or 'no group'}"
        assert hit[0] == entry["group"], (
            f"{step} is grouped {entry['group']} in pipeline_steps.yaml "
            f"and {hit[0]} in task_groups.yaml"
        )
    claimed = {
        pattern
        for pattern in patterns
        if not any(fnmatch.fnmatchcase(str(e["step"]), pattern) for e in steps)
    }
    assert not claimed, f"task_groups.yaml claims steps nothing runs: {sorted(claimed)}"


def test_i9_a_heavy_board_is_a_well_covered_one(run: Run) -> None:
    """I9 — weight the pool was not measured on does not rank the pool.

    Terminal-Bench 4.0 carried 0.448 of coding-experiments on 24% of the
    variants: for the other 76% that weight was renormalised away, so
    the group's headline weight described almost none of its rows.
    """
    leverage = run.rank.weight_guards(run.groups)["coverage_leverage"]
    measured = {
        board: sum(board in m.scores for m in run.ranked) / len(run.ranked)
        for m in run.ranked
        for board in m.scores
    }
    for name in run.core:
        weights = run.rank.group_weights(run.groups, name)
        for board, share in weights.items():
            cover = measured.get(board, 0.0)
            assert share <= leverage * cover + run.rank.WEIGHT_TOLERANCE, (
                f"{name}: {board} carries {share:.3f} of the group on {cover:.3f} of the pool"
            )


def test_i9_the_guards_stop_a_run_rather_than_publishing(run: Run) -> None:
    """The guards are not advisory: a group that breaks one does not print."""
    groups = run.rank.load_yaml(DATA / "task_groups.yaml")
    arena = run.rank.eval_families(run.groups)
    twins = sorted(k for k, v in arena.items() if v == "chatbot-arena")[:2]
    groups["groups"]["review-judging"]["pillars"] = {
        "preference": twins,
        "capability": twins[:1],
    }
    with pytest.raises(SystemExit, match=r"max_family_share"):
        run.rank.group_weights(groups, "review-judging")

    with pytest.raises(SystemExit, match=r"max_board_weight"):
        run.rank.check_weight_guards(
            "group toy",
            {"eqbench_cw3_elo": 0.40, "browsecomp": 0.35, "gpqa_diamond": 0.25},
            run.groups,
        )
    with pytest.raises(SystemExit, match=r"coverage_leverage"):
        run.rank.check_coverage_leverage(
            "group toy", {"a": 0.9, "b": 0.1}, {"a": 0.01, "b": 0.9}, run.groups
        )


def test_the_guards_are_skipped_where_no_bounds_are_declared(run: Run) -> None:
    """A YAML with no `weight_guards:` is not checked, on purpose.

    The toy fixtures are deliberately lopsided — one board at full
    weight — and a guard that fired on them would be testing the fixture
    rather than the ranking.
    """
    groups = run.rank.load_yaml(DATA / "task_groups.yaml")
    del groups["weight_guards"]
    assert run.rank.weight_guards(groups) is None
    run.rank.check_weight_guards("group toy", {"terminal_bench_4_0": 1.0}, groups)
    run.rank.check_coverage_leverage("group toy", {"a": 1.0}, {"a": 0.0}, groups)


def _family(key: str) -> str:
    """A model's catalogue id without its `@effort` tag.

    The shortlist slot I10 cares about is the model, not the row: four
    efforts of one model trading places among themselves in the top
    five is the same family standing in the same slot, not a rewrite of
    who is on the shortlist.
    """
    return key.split("@", 1)[0]


def _family_top(order: list[str], depth: int) -> list[str]:
    """The first `depth` distinct families walking `order`, best first."""
    seen: list[str] = []
    families: set[str] = set()
    for key in order:
        fam = _family(key)
        if fam in families:
            continue
        families.add(fam)
        seen.append(fam)
        if len(seen) >= depth:
            break
    return seen


class FamilyLobo(NamedTuple):
    """I10's own reading of one board's removal: families, not rows."""

    board: str
    churn: int


def family_lobo_shifts(
    rank: ModuleType,
    models: list[Any],
    name: str,
    weights: dict[str, float],
    pillars: dict[str, str],
    *,
    tolerance: float = 1.0,
    depth: int = 5,
) -> list[FamilyLobo]:
    """I10's guard, replayed over model families with a noise tolerance.

    Mirrors `rank.lobo_shifts`'s own refit-without-a-board loop — the
    fit itself is not this test's to second-guess — and changes only
    what counts as a shortlist rewrite: the top `depth` is read as
    distinct model families (`_family`), and a family leaving is paired
    with the family that took its place; a pair within `tolerance` raw
    points of each other is the fit's own noise floor swapping two
    near-identical rows, not a reader noticing a different shortlist.
    """
    cells = {m.key: dict(m.normed.get(name, {})) for m in models if name in m.fit}
    cells = {k: v for k, v in cells.items() if v}
    if not cells:
        return []
    model_level = {key for m in models for key in m.shared}
    base_scores = {k: next(m for m in models if m.key == k).fit[name] for k in cells}
    base = sorted(cells, key=lambda k: -base_scores[k])
    out: list[FamilyLobo] = []
    for board in sorted(weights):
        kept = {k: v for k, v in weights.items() if k != board}
        if not kept or not any(board in row for row in cells.values()):
            continue
        left = {key: {k: v for k, v in row.items() if k != board} for key, row in cells.items()}
        own = {k: set(v) - model_level for k, v in left.items()}
        fitted = {k: v for k, v in left.items() if len(own[k]) >= rank.MIN_MEASURED_BOARDS}
        spare = {k: v for k, v in left.items() if 0 < len(own[k]) < rank.MIN_MEASURED_BOARDS}
        after, after_band, parts = rank.pillar_fits(fitted, kept, pillars)
        rank.apply_placements(
            rank.sibling_placements(
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
        if not common:
            continue
        after_order = sorted(common, key=lambda k: -after[k])
        before_top = _family_top(common, depth)
        after_top = _family_top(after_order, depth)
        left_fams = [f for f in before_top if f not in after_top]
        entered_fams = [f for f in after_top if f not in before_top]
        left_score = {f: max(base_scores[k] for k in common if _family(k) == f) for f in left_fams}
        entered_score = {
            f: max(after[k] for k in after_order if _family(k) == f) for f in entered_fams
        }
        left_sorted = sorted(left_fams, key=lambda f: -left_score[f])
        entered_sorted = sorted(entered_fams, key=lambda f: -entered_score[f])
        churn = sum(
            1
            for dep, arr in zip(left_sorted, entered_sorted, strict=False)
            if abs(left_score[dep] - entered_score[arr]) >= tolerance
        )
        churn += abs(len(left_sorted) - len(entered_sorted))  # unpaired -> no tolerance partner
        out.append(FamilyLobo(board, churn))
    return out


def test_i10_no_single_board_rewrites_a_shortlist(run: Run) -> None:
    """I10 — leave one board out and report how far the top travels.

    The invariant as written wanted the top five in the same order after
    any single board is dropped. Measured, it is not: dropping
    terminal_bench_4_0 moves the second row of scientific-writing to
    fourth, and one group's fifth row falls to sixth. Refusing to
    publish over that would be refusing to publish the evidence we have.

    What holds, and is worth promising, is the coarser claim a reader
    building a shortlist is actually asking about: no single board
    changes more than three members of any group's top five, read as
    `family_lobo_shifts` reads it — by model family, not by row, and
    ignoring a swap between two rows within 1.0 raw point of each other.
    A top five that is four efforts of one model reordering within a
    point of one another, because a board both of them sat moved, is
    not a rewrite a reader building a shortlist would notice; it is the
    fit's own noise floor relabelling which of one model's rows sits on
    top. The ordering inside the shortlist, and the worst mover per
    group, are reported on the findings page instead of asserted away.

    It was one member until effort variants were placed against their
    family's best-measured variant rather than against the group. A
    placed row is tied to its anchor through the handful of boards the
    two share, so dropping one of those boards moves it further than
    dropping a board moves a row fitted against the whole group — the
    price of not charging a family-wide weakness to whichever effort
    happened to be run on the hard boards. Reading the top five by
    family absorbs exactly that: a placed row and the anchor it moved
    with are one family, so a board that reorders them without touching
    which families are in the top five is not counted at all.

    It is three since the three pillars. A group is now nine to
    thirteen boards where it was forty, because a pillar is a third
    whether its question is answered by one board or by eight, so every
    board carries three to five times what it did and dropping one is a
    correspondingly bigger change to the evidence. What would be a
    defect is a board moving the top of a group it barely touches, and
    the guards of §4 are what stop that.
    """
    for name in run.core:
        weights = run.rank.group_weights(run.groups, name)
        pillars = run.rank.group_pillars(run.groups, name)
        # A pillar with one member is half the group by construction,
        # so dropping that board drops a whole pillar and the shortlist
        # is supposed to move — there is no second opinion left to hold
        # it steady. What this invariant is about is a board inside a
        # pillar standing in for the pillar.
        alone = {next(iter(members)) for members in pillars.values() if len(members) == 1}
        shifts = family_lobo_shifts(
            run.rank, run.ranked, name, weights, run.rank.board_pillars(run.groups)
        )
        assert shifts, f"{name} has no board whose removal is measured"
        for shift in shifts:
            if shift.board in alone:
                continue
            assert shift.churn <= 3, (
                f"{name}: dropping {shift.board}, which carries "
                f"{weights[shift.board]:.3f} of the group, swaps {shift.churn} "
                f"of the top {run.rank.LOBO_SET} families out"
            )
    findings = (SKILL_DIR / "results" / "findings.md").read_text(encoding="utf-8")
    assert "## What one board is holding up" in findings


# --------------------------------------------------------------------
# I11-I16: what a printed number is allowed to mean.
# --------------------------------------------------------------------


def test_i11_nothing_in_the_fit_is_a_prior(run: Run) -> None:
    """I11 — the prior is gone, so it cannot count a model five times.

    A per-model prior blended into every effort variant let one strong
    base model vote five times for itself. The fit has no prior at all
    now: a group's scores are a function of its measured cells, so
    deleting a variant that shares no board with the rest cannot move
    anybody.
    """
    rank, groups = run.rank, run.groups
    cells = {
        m.key: dict(m.normed["review-judging"]) for m in run.ranked if "review-judging" in m.fit
    }
    weights = rank.group_weights(groups, "review-judging")
    before = rank.solve_ability(cells, weights).score
    loner = {"toy/loner": dict.fromkeys(list(weights)[:3], 50.0)}
    after = rank.solve_ability({**cells, **loner}, weights).score
    assert set(after) == set(before) | {"toy/loner"}
    moved = max(abs(after[key] - before[key]) for key in before)
    assert moved < 1.0, f"an unrelated row moved the group by {moved:.2f}"


def test_i12_one_lab_has_one_provider_id(run: Run) -> None:
    """I12 — `meta` and `meta-llama` were two labs by the catalogue's count."""
    prefixes = sorted({str(entry["id"]).split("/", 1)[0] for entry in run.raw["models"]})
    for left, right in itertools.combinations(prefixes, 2):
        assert not (left.startswith(f"{right}-") or right.startswith(f"{left}-")), (
            f"`{left}` and `{right}` look like one lab under two ids"
        )
    slugs: dict[str, str] = {}
    for prefix in prefixes:
        slug = run.rank.VENDOR_LOGOS.get(prefix)
        if slug:
            assert slug not in slugs, f"`{prefix}` and `{slugs[slug]}` share one maker"
            slugs[slug] = prefix


def test_i13_every_variant_has_a_cost_basis_it_states(run: Run) -> None:
    """I13 — 205 of 225 rows carried an unstated, assumed 1.0 multiplier."""
    for model in run.ranked:
        if model.rel_cost is not None:
            continue
        said = " ".join(model.status(run.core[0], on_frontier=False)).lower()
        assert "price" in said or "cost" in said, (
            f"{model.name} has no cost per task and the table does not say so: {said}"
        )


def test_i14_a_drilldown_number_is_measured_or_labelled(run: Run) -> None:
    """I14 — every number in a model's own card traces to a data row."""
    page = (SKILL_DIR / "results" / "frontiers.html").read_text(encoding="utf-8").lower()
    # The comparison is reduced to a bool before the assert: a five-megabyte
    # page inside a failing assertion sends pytest's differ away for hours.
    printed = [word for word in ("imputed", "estimated value", "assumed cost") if word in page]
    assert not printed, f"the page still prints {printed}"
    # A source may say its own method is an estimate, and that word may
    # then reach the page inside the citation it belongs to — never as
    # the description of a number in a card or a table cell.
    outside = [chunk for chunk in page.split("estimated")[:-1] if "<cite" not in chunk[-200:]]
    assert not outside, "the page calls something estimated outside a cited source"
    assert [m for m in run.ranked if m.rel_cost is None], "nothing is price-only"
    assert "price-only" in page


def test_i16_a_band_with_no_frontier_row_still_names_a_model(run: Run) -> None:
    """I16 — 12 of 15 steps printed "none" for the 1x-5x band.

    No frontier row sits between one and five times the reference in any
    group on this catalogue: the frontier jumps from cheap open weights
    to expensive closed ones. A reader with that budget was told
    nothing.
    """
    for name in run.core:
        picks = run.rank.best_by_band(run.ranked, name)
        labels = [label for label, _ in run.rank.COST_BANDS]
        assert set(picks) == set(labels), f"{name} leaves a band empty: {sorted(picks)}"
    ranking = (SKILL_DIR / "results" / "ranking.md").read_text(encoding="utf-8")
    picks = ranking.split("## Best pick per pipeline step")[-1]
    empty = [line for line in picks.splitlines() if "| none |" in line]
    assert not empty, f"{len(empty)} step rows still print `none`"
    # Where a band holds no frontier row the pick is marked, and the
    # mark is explained under the table it appears in. Where every band
    # reaches the line — which the captured boards made true for the
    # first time — there is no mark to explain and no legend.
    marked = [line for line in picks.splitlines() if " + |" in line]
    legend = "`+` marks a band the frontier does not reach"
    assert bool(marked) == (legend in ranking), (
        f"{len(marked)} picks are marked `+` and the legend is "
        f"{'present' if legend in ranking else 'missing'}"
    )


# --------------------------------------------------------------------
# I17-I19: already true when the audit was written; locked in here.
# --------------------------------------------------------------------


def test_i17_every_resolved_weight_map_sums_to_one(run: Run) -> None:
    """I17 — including the step overrides, which are maps too."""
    tolerance = run.rank.WEIGHT_TOLERANCE
    for name in run.core:
        weights = run.rank.group_weights(run.groups, name)
        assert sum(weights.values()) == pytest.approx(1.0, abs=tolerance)
    for step, group in run.rank.step_groups(run.groups).items():
        weights = run.rank.group_weights(run.groups, group)
        assert sum(weights.values()) == pytest.approx(1.0, abs=tolerance), step
    with pytest.raises(SystemExit, match=r"sum to 0\.8000, not 1"):
        run.rank.check_weight_sum("toy", 0.8)


def test_i18_a_cost_ratio_never_mixes_two_sources(run: Run) -> None:
    """I18 — a ratio across two runs measures the runs, not the models."""
    for entry in run.ratios.get("cost_ratios", []):
        pair = f"{entry.get('model_a')} / {entry.get('model_b')}"
        assert isinstance(entry.get("source"), str), f"{pair} names no single source"
        assert isinstance(entry.get("benchmark"), str), f"{pair} names no benchmark"


def test_i19_the_ranking_survives_the_price_blend_it_assumes(run: Run) -> None:
    """I19 — the blend is one input, so the answer must not turn on it.

    The two inputs have different provenance and are swept over
    different ranges. The pool-wide fallback is a guess, so it is swept
    over the whole range a guess could plausibly take, 1 to 7; a group
    with a measured ratio no longer reads it at all, which is most of
    the point. The per-group weights are medians over recorded runs and
    are swept a quarter either side, which is the sampling error a
    median over that many runs carries.

    The honest edge: past about 1.5x the measured coding ratio, fifth
    place in that group swaps between two rows the fit separates by
    less than either one's band. That is a near-tie being decided by
    the blend rather than the blend rewriting the shortlist, and it is
    written down here rather than asserted away.
    """
    rank = run.rank
    raw = rank.load_yaml(DATA / "models.yaml")
    boards, cells, sources = rank.load_boards(DATA)
    rank.apply_boards(raw, boards, cells)
    raw.setdefault("sources", {}).update(sources)
    ratios = rank.load_yaml(DATA / "cost_ratios.yaml")
    tops = []
    for weight, scale in ((1.0, 0.75), (3.0, 1.0), (7.0, 1.25)):
        groups = rank.load_yaml(DATA / "task_groups.yaml")
        measured = (groups.get("price_blend") or {}).get("by_group") or {}
        assert measured, "the per-group blends are gone, so this sweeps nothing"
        groups["price_blend"] = {
            "output_weight": weight,
            "basis": "a sensitivity run",
            "by_group": {name: value * scale for name, value in measured.items()},
            "by_group_basis": "a sensitivity run",
        }
        blends = {name: w for name, (w, _) in rank.group_blends(groups).items()}
        models, reference = rank.build_models(raw, weight, blends)
        rel_costs = rank.solve_relative_cost(ratios.get("cost_ratios", []), reference)
        models = rank.expand_efforts(models, ratios)
        rank.apply_prices(models, reference)
        rank.apply_costs(models, rel_costs)
        rank.score_models(models, groups)
        ranked = rank.rankable(models)
        front = {m.key for m in rank.pareto_front(ranked, "coding-experiments")}
        tops.append([m.name for m in rank.group_order(ranked, "coding-experiments", front)[:5]])
    assert tops[0] == tops[1] == tops[2], f"the top five moves with the blend: {tops}"


# --------------------------------------------------------------------
# I20: the prose has to match the data it describes.
# --------------------------------------------------------------------


def _column(run: Run, board: str) -> dict[str, float]:
    """One board's published values, over the variants the guard sees.

    The duplicate guard compares boards across expanded variants, not
    catalogue rows, so a comment about overlap is a claim about those.
    """
    return run.rank.board_columns(run.models).get(board, {})


def test_i20_the_yaml_comments_state_what_the_data_says(run: Run) -> None:
    """I20 — every count and correlation in the comments, recomputed.

    The comments claimed 21 composite members where there are 19, that
    two boards were "identical to the third decimal" where no pair
    matches, and that another pair "overlaps on 8 models" where it
    overlaps on 15. A comment nobody can check is a comment nobody
    should believe.
    """
    text = (DATA / "task_groups.yaml").read_text(encoding="utf-8")
    for claim, left, right, expected, overlap in (
        ("gpqa", "aa_gpqa_diamond", "gpqa_diamond", 0.9998, 10),
        ("terminal-bench", "terminal_bench_4_0", "aa_terminal_bench_4_0", 0.96, 15),
    ):
        first, second = _column(run, left), _column(run, right)
        value, shared = run.rank.correlation(first, second)
        assert shared == overlap, (
            f"{claim}: the comment says {overlap} shared variants, there are {shared}"
        )
        assert value == pytest.approx(expected, abs=0.01), (
            f"{claim}: the comment says r {expected}, the data says {value:.4f}"
        )
    assert "identical to the third decimal" not in text.lower()
    assert "21 AA component boards" not in text
    # Every board a group names is a board something can measure, and
    # every board file the comments point at exists.
    columns = run.rank.board_columns(run.models)
    for name in run.groups["groups"]:
        for members in run.rank.group_pillars(run.groups, name).values():
            for board in members:
                assert columns.get(board), (
                    f"{name} weights `{board}` and no model in the catalogue "
                    "or any capture carries it"
                )
    for source in ("arena", "aa"):
        assert (
            f"data/boards/{source}.yaml" not in text
            or (DATA / "boards" / f"{source}.yaml").exists()
        )


def test_i20_skill_md_describes_the_method_the_code_runs(run: Run) -> None:
    """I20 — the reader-facing prose, against the same data.

    SKILL.md rejected models on the rule "every number traces to the
    vendor's own announcement", which the catalogue does not follow:
    poolside/laguna-s-2.1 is carried on third-party captures.
    """
    text = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    assert "vendor's own announcement" not in text
    assert "21 " not in text.split("## 5")[-1].split("## 6")[0]
    for term in ("max_family_share", "coverage_leverage", "frontier_min_boards"):
        assert term in text, f"SKILL.md never mentions {term}"
    # The two scales the code runs, named where a reader meets them.
    assert "ROBUST_CLIP" in text and str(int(run.rank.ROBUST_CLIP)) in text
    assert "inter-quartile range" in text
    assert "min-max scaled to 0–100" not in text
    # And the sibling rule, in the words the status column uses.
    assert "MIN_SIBLING_SHARED" in text
    assert str(run.rank.MIN_SIBLING_SHARED) in text
    flowed = " ".join(text.split())
    for phrase in (
        "placed relative to",
        "no board shared with",
        "too thin for the frontier",
    ):
        assert phrase in flowed, f"SKILL.md never mentions the status `{phrase}`"


def test_i20_the_generated_pages_carry_no_retracted_claim(run: Run) -> None:
    """The words the audit caught, gone from everything a reader opens."""
    for name in ("frontiers.html", "ranking.md", "findings.md", "evidence.md"):
        text = (SKILL_DIR / "results" / name).read_text(encoding="utf-8").lower()
        said = [p for p in ("with style control on", "imputed", "shrunk toward") if p in text]
        assert not said, f"{name} still says {said}"


# --------------------------------------------------------------------
# The cuts: every id in them has to be dialable and in order.
# --------------------------------------------------------------------


def cuts(run: Run) -> dict[str, Any]:
    """The preset cuts, built from the same pass the pages are."""
    return run.rank.build_cuts(run.models, run.core)


def test_a_cut_only_names_an_id_its_backend_can_route(run: Run) -> None:
    """The runtime refuses an id it cannot dial, so the cut must not.

    Three different refusals: the Claude CLI takes the ids its roster
    shipped at the efforts that roster names and Haiku takes no effort
    at all, the paid OpenRouter lane takes any `vendor/model`, and the
    free lane takes only the slugs the free router's pool declares. A
    cut that names anything else is a cut that fails at run time, which
    is the one thing a generated cut has to be incapable of.
    """
    rank = run.rank
    roster = rank.claude_roster(rank.ROSTER_PATH)
    slugs = set(rank.free_pool_slugs(rank.FREE_POOL_PATH))
    assert roster and slugs, "the roster and the free pool are what this checks against"
    seen = 0
    for preset, backends in cuts(run)["presets"].items():
        for backend, by_group in backends.items():
            for group, cut in by_group.items():
                for role, pick in cut.items():
                    where = f"{preset}/{backend}/{group}/{role}"
                    seen += 1
                    assert rank.tier_id_routable_on(backend, pick["model"]), (
                        f"{where}: {pick['model']} is not routable there"
                    )
                    if backend == rank.CLAUDE_BACKEND:
                        efforts = roster.get(pick["model"])
                        assert efforts is not None, f"{where}: not in the Claude roster"
                        assert (pick["effort"] or "") in (efforts or [""]), (
                            f"{where}: {pick['model']} does not take effort {pick['effort']!r}"
                        )
                    if backend == rank.FREE_BACKEND:
                        assert pick["model"] in slugs, f"{where}: not in the free pool"
                        assert len(pick["fallbacks"]) == rank.FREE_FALLBACKS, (
                            f"{where}: the free pool exhausts, so a role "
                            "with no fallback is a role that stops working"
                        )
                        assert pick["model"] not in pick["fallbacks"]
                        assert set(pick["fallbacks"]) <= slugs
    assert seen, "no cut was built at all"


def test_a_cut_descends_and_the_orchestrator_leads_or_says_why_not(
    run: Run,
) -> None:
    """easy <= medium <= hard <= orchestrator, on the ladder's own order."""
    built = cuts(run)
    for backend, by_group in built["ladders"].items():
        for group, ladder in by_group.items():
            keys = [(rung["model"], rung["effort"]) for rung in ladder]
            assert len(set(keys)) == len(keys), (
                f"{backend}/{group}: a rung is repeated, so two tiers "
                "would be handed the same model while claiming to differ"
            )
            measured = [r["capability"] for r in ladder if r["capability"] is not None]
            assert measured == sorted(measured), f"{backend}/{group}: ladder is not in order"
            order = {key: index for index, key in enumerate(keys)}
            for preset in run.rank.PRESETS:
                cut = built["presets"][preset][backend][group]
                rungs = [
                    order[(cut[role]["model"], cut[role]["effort"])]
                    for role in ("easy", "medium", "hard", "orchestrator")
                ]
                assert rungs == sorted(rungs), f"{preset}/{backend}/{group}: {rungs}"
                if rungs[-1] == rungs[-2]:
                    assert cut["orchestrator"].get("note"), (
                        f"{preset}/{backend}/{group}: the orchestrator "
                        "matches the hard tier and does not say why"
                    )


def test_a_row_below_its_group_s_floor_is_ranked_and_never_recommended(
    run: Run,
) -> None:
    """The requirement filter, on the real catalogue.

    A flagged row keeps its number — the boards measured what they
    measured — and leaves the frontier and every cut, because a model
    that cannot hold the step's prompt is not a cheap way to run it.
    """
    rank = run.rank
    floors = rank.group_requirements(run.groups)
    assert all(floors[name] for name in run.core), "every group declares a floor"
    flagged = [m for m in run.ranked if m.requirement_gaps]
    assert flagged, "no row fails any floor, so this filter checks nothing"
    for model in flagged:
        for group, gaps in model.requirement_gaps.items():
            floor = floors[group]
            for gap in gaps:
                if gap == "context window":
                    assert model.context_window < floor["min_context_tokens"]
                elif gap == "max output":
                    assert model.max_output_tokens < floor["min_max_output_tokens"]
                else:
                    assert model.tool_calling is False and floor["tool_calling"]
            assert model.id not in {m.id for m in rank.pareto_front(run.ranked, group)}
            assert any(gap in note for note in model.status(group) for gap in gaps)
    named = {
        pick["model"]
        for backends in cuts(run)["presets"].values()
        for by_group in backends.values()
        for cut in by_group.values()
        for pick in cut.values()
    }
    barred = {
        rank.roster_id(m.id) if m.id.startswith("anthropic/") else m.id
        for m in flagged
        if len(m.requirement_gaps) == len(run.core)
    }
    assert not (named & barred), f"a cut names a row that fails every group: {named & barred}"
