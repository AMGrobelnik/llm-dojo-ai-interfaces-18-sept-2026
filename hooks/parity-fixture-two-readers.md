<!-- hook: parity-fixture-two-readers -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every shared parity fixture under tests/fixtures/ is read by both its Python test and its frontend twin — a fixture never silently reverts to one-sided truth.

The fixture pattern exists precisely to stop twin drift (history class #1:
584f91167 'the same reported-zero defect, in all three FE cost derivations';
c509ff509 introduced the shared cost fixture). Verified the current invariant
holds: tests/fixtures/run_cost_parity.json is read by rule-cost-
accounting/test_run_cost_parity.py AND its frontend twin, and rule-cost-
accounting/SKILL.md's Genre note says the pair 'must migrate together with its
FE twin'. Nothing checks that: delete either reader and both suites stay green
while the parity guarantee is gone — the dangerous silent case the repo's own
split-module doc warns about (a guard that is green and checking nothing).

The frontend twin's own location has already moved once — from
`aii_frontend/features/labs/__tests__/run-cost-parity.test.ts` to the vendored
`research-monorepo/fe-unit-tests/features-labs/run-cost-parity.test.ts` a consumer
carries at `<engine>/research-monorepo/fe-unit-tests/...` (e.g.
`.claude/skills/amg-hooks/research-monorepo/fe-unit-tests/...`) once
`run_groups_fe.py` could select and run the FE suite there by group. A reader
under either root counts: `FRONTEND_ROOT` still catches `aii_frontend/`, and
`_vendored_frontend_root` derives the engine's own prefix the same way the
`run_static_check.py` shims do (`RULES_ENGINE_DIR`, falling back to walking up
from `__file__` when run bare) so the classification survives the suite
moving again without a second hard-coded path.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: tests-quality)

Mechanism (implemented 2026-08-26, `scripts/check_fixture_readers.py`):

    .venv/bin/python $RULE_DIR/scripts/check_fixture_readers.py

**The proposed command below would have failed open, and measuring it is what
showed that.** It greps the basename across the engine tree and `aii_frontend`,
failing when either side has zero hits. But `run_cost_parity.json` is named in
far more files than read it — re-counted 2026-09-14, **9 tracked files** in
this repo, of which exactly ONE loads the fixture
(`research-monorepo/unit-tests/cost-accounting/test_run_cost_parity.py`); the other
eight are two checker scripts, a second test module that only names it as a
constant, three `README.md` bodies including this one, a `paths.txt` and
`docs/migration-report.json`. (The three `SKILL.md` files this paragraph used
to name are gone with the rule engine — no `SKILL.md` remains under any group.)
So the Python side reports far more hits than readers,
and would still report several after the one real reader was deleted. The
guard would pass
while the invariant it exists for was broken, which is the exact
green-and-checking-nothing failure this rule is about.

Restricting to source extensions (`.py`, `.ts`) was the obvious fix and it was
**also not enough** — the second mistake being the instructive one. The
checker script itself names the fixture in its own docstring and is a `.py`
file, so the moment it was staged the Python-side count went from 2 to 3. It
would have gone on counting itself as a reader long after the real test was
deleted: the checker would have been the last thing keeping itself green.

So a reader must be a TEST module (`test_*.py`, `*.test.ts`, `__tests__/`).
Both halves of a parity pair are tests by construction, so nothing legitimate
is lost, and prose — in a `.md`, in a rule, or in a checker — can never be
mistaken for a use.

Probed on a synthetic repository, five cases: deleting the Python test while
the prose survives fires, deleting the frontend test fires, and deleting the
test while adding a non-test `.py` that names the fixture **still** fires —
that last one is the self-reference trap above. Removing only the `.md`
correctly does not.

Residual limit, stated rather than papered over: a mention inside a test file
counts even if it sits in a docstring rather than a load, so deleting the
`FIXTURE = …` line alone would still pass. Proving a line actually reads the
file, statically, across both Python and TypeScript, trades this narrow gap
for a wide one. Both documented failure modes are closed.

Measured 2026-08-26: 1 fixture, 1 Python reader, 1 frontend reader.

Superseded proposal:

    python3 $RULE_DIR/scripts/check_fixture_readers.py  # for each tests/fixtures/*: grep -rl its basename in .claude/skills/amg-hooks/rules AND in aii_frontend — fail if either side has zero readers

Delete-check: Cannot be deleted — the fixture IS the collapsed dimension (one dataset
instead of two hand-kept derivations); the rule guards that the collapse stays
two-sided. Deleting the fixture would resurrect the twin-drift class it was
built to kill.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The fixture IS the collapsed dimension from history class #1 (same
defect in three FE derivations); a fixture read by only one side silently
reverts to one-sided truth. Cheap two-reader assert per fixture.
- KEEP: The fixture pattern exists to stop the repo's #1 twin-drift class, and
a fixture silently losing one reader reverts to one-sided truth with all gates
green. Two-reader grep per fixture is cheap and low-FP.
- KEEP: For each tests/fixtures/*.json, grep its basename in Python tests AND
frontend tests, require both non-empty. Deterministic; a fixture reverting to
one-sided truth fails loudly. Guards the house parity pattern itself.
