<!-- hook: sweep-population-floor -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A guard whose verdict is computed over a DISCOVERED population proves it was non-empty — a floor, a failing for…else or a sibling premise test — unless it opts out because empty is correct.

In full: a test whose every assertion sits inside a `for` loop must loop over
an in-place literal, carry a `for…else` that raises or `pytest.fail`s, or
assert the collection is non-empty before the loop — the floor may also live
in a sibling premise test, which is the repo's own convention — and a
frontend `*.guard.test.ts` sweep asserting `expect(sweep()).toEqual([])`
must assert its scanned population is non-empty too. A population that is
empty BY DESIGN opts out with `# population-may-be-empty: <why>` instead of
a floor that would assert the hazard still exists.

**State on 2026-08-28.** `scripts/sweep_floor.py` is built and exits 0 over
the tree. It enforces the Python half in the CORRECTED form worked out below,
not the literal one: only the derived class is checked, and literals,
`range(...)`, module constants, `for…else`, sibling premise tests and the
opt-out comment are exempt. The frontend half is NOT mechanized and its stock
is still one:
`aii_frontend/lib/__tests__/scrollable-region-focusable.guard.test.ts` reads
`views()` at :58 and :92 and asserts nothing about its length, so all three
a11y sweeps there go green on an empty population. Adjacent, not duplicate:
`rule-group-run-proves-something` gates at the group level (zero tests
passed); this gates the loop population inside a test that passed.

## History (how the corrected form was reached)

CONFIRMED LIVE VACUOUS PASS. `.venv/bin/python scratchpad/vacuous2.py` (AST
over `git ls-files '*test_*.py'`, excluding literal iterables and for/else-
fail) prints `tests whose every assert sits in a loop that can run zero times:
44`. One is provably firing zero assertions today: `rule-image-watcher-
release-guards/test_image_watcher_contract.py::test_no_stop_signal_handler_rem
oves_a_worktree` loops `for handler, signals in _SIGNAL_TRAP.findall(src)`.
Running that module's OWN regex against the file it reads — `python -c
"rx=re.compile(r'^\s*trap\s+(\S+)\s+([A-Z ]*\b(?:TERM|INT)\b[A-Z ]*)$',re.M);
print('matches:', rx.findall(Path.home()/'.local/bin/aii-image-watcher.sh'))"`
— prints `matches: []`, and `grep -nE "trap" scripts/local/watchers/aii-image-
watcher.sh` returns exactly one line, `73:# \`systemctl restart\` the old
\`trap cleanup EXIT INT TERM\` deleted the worktree` (a comment; the trap was
removed). The test still reports green: `.venv/bin/pytest -n 0 -q <that test>`
→ `. [100%]`. Its docstring calls it "The regression that cost a build" — the
guard for a build-killing incident asserts nothing. The house convention
already exists and is named: `rule-pod-boot-handoff-parity/test_claude_config_
dir_agrees_with_the_derivation.py::test_the_deploy_still_pins_the_store` is a
dedicated premise test whose docstring says "the checks below would pass while
saying nothing", and `test_pod_start_commands_are_tracked.py` writes `assert
workers, "no worker templates found — did the block move?"` inline. Frontend
twin, same shape: `aii_frontend/lib/__tests__/scrollable-region-
focusable.guard.test.ts:116` is `expect(unreachable()).toEqual([])` where
`unreachable()` filters `readdirSync(viewsDir)` by `.endsWith(".tsx")` — no
test anywhere asserts `views().length > 0`, so a filter that stops matching
turns all three a11y guards green.

CORRECTION (2026-08-25, from working the population) — **the headline example
is documented, and this rule's own remedy would break it.**

`test_no_stop_signal_handler_removes_a_worktree` does loop zero times, and the
census above is right that it asserts nothing today. But it is not an unnoticed
vacuity: its docstring says so in capitals, explains that the installed watcher
has no signal trap because one deleted a worktree during an incident, states
that an empty-by-design population is indistinguishable from a regex that
stopped matching, names what separates them here (`_src` fails loudly if the
file stops looking like the watcher), and names its own residual gap (a trap
reintroduced in a shape the regex cannot see would still slip past).

Applying the remedy this rule prescribes — assert the collection is non-empty
before the loop — would make that test FAIL, because zero traps IS the correct
state. So "every loop-only test asserts a non-empty population" is too strong
as written. An empty-by-design population needs a different treatment: say so
in the docstring and pin the premise separately, which is what this test and
`rule-pod-boot-handoff-parity`'s dedicated premise test already do.

MEASURED TAXONOMY (2026-08-25), which is what a mechanism would have to respect
— 56 loop-only tests lacked a floor across 27 groups, and they are not one
population:

- **derived / drawn collections** — `axes.patches`, `figure.axes`,
  `content_axes(fig)`, `enumerate(cells)`, `.get(k, {})`. Empty means the
  renderer or the schema produced nothing, which is the regression the guard
  exists to catch. NINE were floored this session; inverting each floor fails
  the suite, so they are load-bearing.
- **module constants** — `chart_style.PALETTE`, `Legend.codes`. Non-empty by
  construction; a floor is ceremony that can never fire.
- **empty-by-design** — the signal-trap guard above. A floor is actively wrong.

A gate that demands a floor everywhere would add assertions that cannot fire to
the second class and break the third. Scoping it to the first is the work this
rule still needs before it can be enforced.

## Mechanism

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: guard-effectiveness)

Command (BUILT — `scripts/sweep_floor.py`), no condition:

    python3 $RULE_DIR/scripts/sweep_floor.py

Clean today, and getting there took 22 floors plus one opt-out. The mechanism
implements the CORRECTED statement above, not the literal one: it checks the
**derived** class only, and exempts literals (inline, module-level, and bound
locally inside the test), `range(...)`, permutations, `for…else`, and any
population a SIBLING test already pins — the repo's own convention.

`# population-may-be-empty: <why>` is the escape hatch, used exactly once:
`test_no_stop_signal_handler_removes_a_worktree`, where zero matches IS the
fix and a floor would assert the hazard still exists.

Two subtleties the build surfaced, both now in the script:

- A floor on a GENERATOR is meaningless — `assert subsets` where `subsets` is
  `chain.from_iterable(...)` is always truthy. That test now floors `TIERS`,
  the population that can actually empty, rather than the generator derived
  from it. `combinations(x, 0)` also always yields one empty tuple, so the
  derived floor could never have failed.
- Counting per-function reported 14 unfloored where 8 were real; the rest were
  pinned by a sibling premise test in the same module.

Proposed condition: `none — whole-tree cmd, runs unconditionally`

Delete-check: Yes, per site, and the rule enforces exactly the deleted end-state. A
population that is a written-down literal cannot be empty, so those sites need
no floor at all and the script already exempts them (that is why 44 is the
count, not 130). The floor is only demanded where the test chose a runtime
discovery — glob, regex findall, dict lookup, readdirSync — and there the
emptiness case is irreducible: no reformulation (set-comparison, `assert not
offenders`) removes it, because an empty population satisfies every one of
them. So the choice is: pin the population as a literal (dimension deleted) or
assert the floor (dimension enforced). Both are green under this rule.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **partly-wrong**.
A different agent re-ran every measurement before this reached the owner.

What it found:
THE NAMED LIVE VACUOUS PASS — FULLY CONFIRMED, three independent ways: $ grep
-nE 'trap' scripts/local/watchers/aii-image-watcher.sh AND ~/.local/bin/aii-
image-watcher.sh -> both: '73:# `systemctl restart` the old `trap cleanup EXIT
INT TERM` deleted the worktree' and nothing else. One line, a comment. $
.venv/bin/python -c "rx=re.compile(r'^\s*trap\s+(\S+)\s+([A-Z
]*\b(?:TERM|INT)\b[A-Z ]*)$',re.M); print('matches:',
rx.findall((Path.home()/'.local/bin/aii-image-watcher.sh').read_text()))" ->
matches: [] (the module's OWN regex, against the file the module itself reads
— WATCHER_SH is defined at test_image_watcher_contract.py:41 as
Path.home()/'.local'/'bin'/'aii-image-watcher.sh', and the file EXISTS so the
pytest.skip at :51 does not fire) $ timeout 300 .venv/bin/pytest -n 0 -q -p
no:cacheprovider '.../rule-image-watcher-release-guards/test_image_watcher_con
tract.py::test_no_stop_signal_handler_removes_a_worktree' -> . [100%] Green
while firing zero assertions. Docstring at :56 is verbatim 'The regression
that cost a build: TERM must not touch the worktree.' HOUSE PRECEDENTS — both
verbatim: $ grep -n 'def test_the_deploy_still_pins_the_store' -A12 .../rule-
pod-boot-handoff-parity/test_claude_config_dir_agrees_with_the_derivation.py
-> :71-73 '...and the checks below would pass while saying nothing.' then :74
`assert _deploy_claude_config_dirs()`. $ grep -n 'assert workers' .../rule-
deploy-config-single-source/test_pod_start_commands_are_tracked.py -> :67
assert workers, "no worker templates found — did the block move?" FRONTEND
TWIN — exact: $ cd aii_frontend && grep -n 'unreachable()|views()|readdirSync'
lib/__tests__/scrollable-region-focusable.guard.test.ts -> 1:readdirSync
import, 50-51: const views = () => readdirSync(viewsDir).filter(f =>
f.endsWith('.tsx') && !f.includes('.stories.')), 58 & 92: views() call sites,
116: expect(unreachable()).toEqual([]). The file has THREE such assertions
(116, 120, 124) and zero non-empty assertion on views() — all three go green
on an empty population. MY OWN COUNT (their scratchpad/vacuous2.py does not
exist — `ls` -> No such file, so nothing to re-run): Wrote an independent AST
scan over `git ls-files '*test_*.py'` with the same two exclusions (in-place
literal iterables incl. enumerate/zip/sorted over one; for/else that raises,
pytest.fail/skip/exit, or asserts): -> 'test FUNCTIONS whose every assert sits
in a possibly-empty loop: 58' -> 'distinct test MODULES: 35' The image-watcher
test appears in my list, as does
test_the_deploys_literal_is_the_derived_directory (the sibling the named
premise test exists to protect — corroborating the convention).

Corrected statement of fact:
The count '44' does not reproduce and cannot be reproduced — the script it
cites (scratchpad/vacuous2.py) is not on disk. My independent AST scan with
the stated exclusions gives 58 test FUNCTIONS across 35 MODULES. Direction
identical, magnitude larger; either the proposal counted modules under a
stricter filter or its heuristic differed. Restate as '35 modules / 58 test
functions, measured <date>' or drop the number and lead with the confirmed
exemplar. Everything else in the proposal is exact, including both verbatim
docstrings, the line numbers, and the green-while-asserting-nothing run.
DEDUPE: not a duplicate, but flag rule-group-run-proves-something (PENDING —
'a unit-test group that fires at commit fails when zero tests pass') as the
adjacent claim; it gates at the group/skip level, this one at the loop-
population level inside a passing test, so the mechanisms genuinely differ —
say so explicitly in the rule body.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Caught a LIVE vacuous pass, and a guard that silently checks nothing
is the worst failure mode in a repo whose conventions live in tests. Claimed
rule-group-run-proves-something works at group level (zero tests pass), not at
the per-assertion empty-population level.
- KEEP: The meta-rule this whole lens is about, and mechanizable exactly as
stated: AST-flag any test whose every assertion sits inside a for with no
literal population, no for/else and no non-empty pre-assertion. Confirmed a
live vacuous pass exists. Distinct from rule-group-run-proves-something (group
exit code) and rule-ban-grep-probes-bite (ban-greps).
- KEEP: The residual the claimed vacuity family genuinely misses. I read all
three neighbours: rule-gate-steps-resolve checks a gate step RESOLVES and is
not `:`/`true`; rule-ban-grep-probes-bite checks an ERE fires on probe
fixtures; rule-group-run-proves-something checks a GROUP has passed>=1. None
of them sees a test that runs, passes, and loops zero times — and this repo's
…
