# A restartable workflow id is never started through a NEW bare SetWorkflowID

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

DBOS does not re-execute a workflow row that has reached a terminal state, so a
start under an id whose row is already terminal is a silent no-op: no
exception, a handle to the already-finished workflow, and nothing tears the
run's resources down. The incident is written into the tree itself, in the
`scheduling_safety_workflow_id` docstring at
`aii_server/dashboard/services/safety_net.py` — measured 2026-08-22, a stop at
02:42 "scheduled" a safety workflow that had already reached SUCCESS, the run's
worker pod stayed up at $0.25/hr with no sweeper, and four more workers
outlived their stops the same night.

The invariant holds today only because five independent hand-rolled
start-or-resume treatments, in five different modules, each check the row their
own way: `run_stop.py` and `zombie_reaper.py` mint a fresh id off a spent one,
`_cli/_dispatch/_resume.py` lists the sibling rows and resumes the cancelled
ones, `_cli/dispatch.py` resumes and returns early, `_fresh.py` branches on a
recoverability probe. Nothing forced a twenty-sixth site to pick any of them,
and the failure mode is silent.

The agent rule that preceded this hook was red at HEAD by construction. Its
ledger records 466 applies, 156 fails and 25 work-in-progress verdicts, and
every one of the 25 says the same three mechanical measurements: 26 grep hits,
no shared door, and this diff adds nothing matching the pattern. That is a
hand-verification paid on every commit to re-state a constant.

## Mechanism

`check.py` walks each file's INDEX content with `ast` and keys every
`with SetWorkflowID(<arg>):` by `(file, unparsed-argument, occurrence-in-file)`
against a frozen baseline, `debt_setworkflowid.json`. A site that is not in the
baseline is new, undiscussed debt.

| failure mode | mechanism |
|---|---|
| a new start site | AST walk against the baseline |
| same argument twice in a file | occurrence index, not text |
| prose naming the pattern | AST, so a docstring is not a site |
| `dbos.SetWorkflowID` | the attribute spelling matches too |
| an unstaged edit deciding it | content read from the index |
| the identifier renamed | vacuity guard, exit 2 |
| the baseline unresolved | vacuity guard, exit 2 |

The shared helper's own module is exempt; it is named in
`CONFIG["door_module"]` as `aii_lib/src/aii_lib/dbos_app/workflow_start.py`.

Paths arriving from `{staged_files}` are filtered to `.py` under the policed
roots. A path that is not in the index is read from disk, so a human running
the checker by hand on an unstaged new file still gets an answer.

## Stock

**0 findings** against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7499`. Whole-tree runtime 0.14 / 0.14 / 0.18 s over three runs
(median 0.14 s) across a population of 543 tracked `.py` files under the three
roots; the per-file lane over 30 changed files also costs 0.14 s.

The baseline holds **24 grandfathered start sites in 14 modules** — 21 sites in
12 modules under `aii_pipeline/src`, 3 sites in 2 modules under `aii_server`.
That stock never blocks a commit: the hook is file-scoped, and a commit
touching a grandfathered file passes because the site is on the list. Only a
twenty-sixth site fails.

The baseline was re-verified against the index at this HEAD rather than trusted
from its capture at `619d5e085`: 24 AST call sites, 24 baseline entries, zero
unlisted, zero stale. One entry (`aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/_2_gen_viz.py`) was migrated and has been removed from the debt. The
key is `(file, argument, occurrence)`, so the drift never affected matching.

The raw grep the old rule cited still returns 26. The twenty-sixth is
`aii_pipeline/src/aii_pipeline/pipeline.py:316`, a docstring example rather
than a call, which is the whole 26-versus-25 gap.

Re-measured after the consumer moved on, at HEAD `eaf82761cddc` (2026-09-08), in one sequential pass over all eleven hooks of this
integration: **0 findings**, whole-tree 0.07 s (median of 0.07 / 0.07 / 0.09). The figures above are
from the earlier HEAD and are unchanged by the move.

## Fragility

| refactor | effect | guard |
|---|---|---|
| identifier renamed | ban matches nothing | sweep exits 2 |
| policed roots move | both lanes go quiet | anchor guard, exit 2 |
| baseline emptied | anchored to nothing | exit 2, no door named |
| a site inserted first | indices shift | fails closed |

The anchor guard is what covers the per-file lane, where an empty result is
the ordinary case: every baseline-listed file carries the identifier by
construction, so if not one of them still does, the policed area moved and
the baseline must be regenerated. The last row is the one soft spot — adding
a start site with the same argument text *before* an existing grandfathered
one in the same file shifts every later occurrence index, and the checker
reports the shifted sites as new rather than passing them silently.

## Residue

Whether a *particular* start site's surrounding code checks the row correctly
before starting is not judged. The shared `start_or_resume_under` helper the
old rule's delete-check names does not exist, so there is nothing for a program
to compare a site against, and telling a safe hand-rolled treatment from an
unsafe one is real judgment. The program's contribution is narrower and exact:
it closes the population at 25.

When that helper lands, `CONFIG["door_module"]` names its module and the
baseline shrinks by one entry per site migrated, until the file-scoped ban
becomes the one-door check the rule always wanted.
