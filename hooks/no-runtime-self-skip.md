<!-- hook: no-runtime-self-skip -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A test never decides its own applicability at runtime: `pytest.skip()` appears only at collection time, never inside a `test_*` body; MONITOR-genre groups are exempt by their declared Genre line.

A test never decides its own applicability at runtime: `pytest.skip()`
appears only as a collection-time decision (`@pytest.mark.skipif`, or
module-level `allow_module_level=True`), never inside a `test_*` body — so a
parametrized guard cannot silently stop covering most of its cases.

CURRENT STATE (re-measured 2026-08-28): the tree is clean and the mechanism
runs green (rc=0). A fresh AST scan over `git ls-files '*test_*.py'` finds 9
in-body `pytest.skip()` calls across 5 tests, all in the MONITOR-genre group
`research-monorepo/unit-tests/watchers-installed-and-current`, which the check
exempts via its
declared `Genre:` line. The flagship offender is FIXED:
`test_data_fig_computed_geometry.py` now pins the refusing kinds in a
`_REFUSES_NEGATED_DATA` frozenset with membership asserted both ways, and
its comment records that the guard "used to call `pytest.skip()`" from
inside its own body. The rule is a pure regression guard over a clean tree.

## History — the loss as measured (2026-08-24)

The flagship case was large. The `-rs` block of a targeted run showed 28
skips at one location: `test_data_fig_computed_geometry.py:911: <kind>
refuses negated data` — the group is
`research-monorepo/unit-tests/data-figure-skill-contract/` today, and the
`rule-` prefixed paths quoted in this section are the retired engine's tree —
once
per chart kind (`treemap`, `upset`, `volcano`, `waterfall`, `area`, `bar`,
… 28 of them). That line sat inside the body of
`test_a_figure_draws_only_one_kind_of_minus_sign`, decorated
`@pytest.mark.parametrize("kind", sorted(chart_examples.EXAMPLES))`, and its
body read `except SpecError: pytest.skip(f"{kind} refuses negated data")` /
`except ValueError as raw: pytest.skip(...)`. Importing the catalogue gave
`EXAMPLES kinds: 61`, so a guard whose docstring said "found by NEGATING
every example" actually asserted on 33 of 61 kinds, and nothing pinned that
share — a change that made `build_figure` refuse negated data more broadly
would have taken it to 0/61 with a green suite and no diff to any test.
Tree-wide the population was small: the same AST scan then reported 22
in-body calls across 17 tests, of which 5 parametrized. NOT a claim against
the documented host-conditional skips: CLAUDE.md declares
`test_watcher_scripts_match_installed.py` "skips where the installed copy is
absent", and the MONITOR-genre exemption preserves that intent exactly.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: guard-effectiveness)

Command (BUILT — `scripts/no_runtime_self_skip.py`), no condition:

    python3 $RULE_DIR/scripts/no_runtime_self_skip.py

**All 11 behaviour-genre offenders are fixed**, across five modules and six
commits: font, `pdftotext`, locale and `dbos` probes hoisted to collection;
three litellm capability probes turned into per-parameter marks so one
unbuildable class skips that class rather than the whole test; and one handler
deleted outright because measurement showed it never fired — zero of 24 kinds
refuse a reordered spec, so there was no refusing set to pin.

**MONITOR-genre groups are exempt, and the exemption is DECLARED rather than
hardcoded.** The watcher group's own `README.md` says "Genre: MONITOR-heavy +
pin — ... probe THIS MACHINE ... and skip where absent", and CLAUDE.md
documents those tests as skipping where the installed copy is absent. The check
reads that `Genre:` line out of the group's `README.md`
(`scripts/no_runtime_self_skip.py:68,74`); no group carries a `SKILL.md` any
more, and that file name survives only in the script's own module docstring.
So a new monitor group is exempt the day it declares
itself and a group that stops being one loses the exemption with no edit here.
That is the difference between this rule and its original phrasing, which
admitted no exemption and would have demanded breaking 9 tests that are correct
by design.

Verified to bite with byte-identical restores: reintroducing one in-body
`pytest.skip()` fails naming file, line and function; the 9 monitor skips that
remain do not fail it.

Proposed condition: `none — whole-tree cmd, runs unconditionally`

Delete-check: Yes — the end-state deletes the runtime skip rather than counting it, which is
why the rule is a ban and not a skip-manifest. The 61-kind figure guard's
conversion is DONE: the try/except-skip became `_REFUSES_NEGATED_DATA =
frozenset({...28 names...})` with membership asserted both ways, so the
exclusion is a reviewable literal and a kind that newly starts or stops
refusing FAILS instead of skipping. The host-conditional watcher/CI-log
skips remain, exempt as a declared MONITOR-genre group. Nothing needs a
manifest.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
TREE @ 4c15ea6db8ec (git status: 1 dirty file). (1) The flagship case, run
directly: $ .venv/bin/pytest -p no:cacheprovider -rs -q '.../rule-data-figure-
skill-contract/test_data_fig_computed_geometry.py::test_a_figure_draws_only_on
e_kind_of_minus_sign' progress line
's.s...sssss.s.s..s.s.....s...ss.s....ss.s..s.ssss.ss...s.s.s.' -> 61 chars $
grep -c '^SKIPPED' minus.log -> 28 Every one of the 28 is the SAME location:
'test_data_fig_computed_geometry.py:911: <kind> refuses negated data' for
bar_sig, calibration, area, bar, fan, forest, funnel, cd_diagram, bubble,
learning_curve, hexbin, network, pr, radar, contour, roc, scaling, ridgeline,
sankey, stacked_pct, step, survival, timeline, speedup, upset, volcano,
waterfall, treemap. So 61 collected, 28 skipped -> 33 actually assert. (2)
Denominator, independently: $ .venv/bin/python -c "import sys;
sys.path.insert(0,'.claude/skills/aii-data-fig-gen/scripts'); import
chart_examples; print('EXAMPLES kinds:', len(chart_examples.EXAMPLES))"
EXAMPLES kinds: 61 (3) Source, read at :880-913 — decorator is
'@pytest.mark.parametrize("kind", sorted(chart_examples.EXAMPLES))' and the
body holds 'except SpecError: pytest.skip(f"{kind} refuses negated data")' /
'except ValueError as raw: pytest.skip(...)'. Docstring does say 'found by
NEGATING every example'. (4) Tree-wide population, my own AST scan over `git
ls-files '*test_*.py'`: pytest.skip() calls INSIDE a test body: 22 across 17
tests, of which parametrized: 5 — byte-identical to the proposal's figure. The
5 parametrized: test_a_figure_draws_only_one_kind_of_minus_sign,
test_reordering_the_series_does_not_change_what_the_figure_says,
test_transport_maps_litellm_exceptions,
test_unmapped_context_overflow_400_fails_over_not_fatal,
test_versioned_copy_matches_the_installed_one. (5) Failure-mode check — no
comment declares the partial coverage deliberate. Read :895-913; the docstring
explains the negation technique, nothing sanctions 28/61. (6) The exempted
forms already dominate, so the rule codifies the house norm rather than
inventing one: $ git grep -c 'allow_module_level' -- '*.py' | wc -l -> 25
modules $ git grep -c 'mark.skipif' -- '*test_*.py' -> 8 files (7) No existing
guard: `.claude/skills/amg-hooks/rules` contains no rule matching 'zero
tests pass'/'all-skipped' (grep -rln, empty), and rule-group-run-proves-
something has no directory yet. DEDUPE: nearest claims are rule-group-run-
proves-something [PENDING] (a GROUP that fires at commit fails when zero tests
pass) and rule-ci-coverage-parity [ENFORCED] (every test/hook runs somewhere).
Both operate at group/suite wiring level; neither can see a parametrized test
that loses 28 of 61 cases while its group reports pass. Not a duplicate.

Corrected statement of fact:
Two things to fix before this ships. (a) I could NOT confirm the '6873 passed,
3 failed, 28 skipped' full-suite figure — I launched `.venv/bin/pytest -p
no:cacheprovider -rs -q` and it ran past 20 min without reaching a summary
line (log grew to 6672 lines, then stalled), so that sentence is unverified.
It is also not load-bearing: my targeted run is the direct evidence for the 28
and for 'all at one location'. Drop the full-suite sentence or re-measure it.
(b) 'mechanically convertible' overstates the remedy for the two cases that
matter most. Whether `build_figure` raises SpecError is not knowable at
COLLECTION time, so a plain `@pytest.mark.skipif` cannot replace this skip —
the honest fix is a pinned refuses-list (or `pytest.param(kind,
marks=pytest.mark.xfail/skipif(...))`), which is precisely what makes the
33/61 share visible. The same applies to the proposal's own counter-example:
`test_versioned_copy_matches_the_installed_one` is ALSO parametrized, and
`skipif` cannot read a param — it needs `pytest.param(...,
marks=pytest.mark.skipif(...))`. State the remedy as 'collection-time, per-
param marks' rather than 'skipif'.

Filter verdicts (3-lens adversarial, kept 2/3):
- KEEP: Verified holds with a live case where a parametrized guard skips most
of its cases at runtime, which reads green while covering almost nothing.
Collection-time-only skips are a clean AST check, and the killed rule-unit-
mark-total was a different mechanism (pytestmark presence).
- KILL: I ran the AST scan: 22 pytest.skip calls sit inside test_ bodies
today, and most are legitimate runtime environment facts (no CJK font, no
pdftotext, this litellm version cannot construct BadRequestError). An absolute
ban would be waived continuously, and the narrow defect it actually targets —
skipping on a verdict computed from the code under test — is not …
- KEEP: A pure ban-grep on a stdlib call that cannot be deleted or collapsed
away — the only enforcement available is refusing it. Residual over rule-
group-run-proves-something is real and I checked it: that rule fires at GROUP
granularity (passed>=1), so a parametrized guard where 1 of 40 cases runs and
passes still reports green under it while covering 2.5% of what it claims. …
