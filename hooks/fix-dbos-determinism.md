<!-- hook: fix-dbos-determinism -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MODE, RULES_STAGED
# DBOS workflow determinism is checked before every commit

Runs `scripts/lint/check_dbos_workflow_determinism.py` over the tracked
Python tree (skill bundles and the checker itself excluded). A violation it
cannot auto-fix blocks with the script's own error text.

NO RE-STAGING (2026-09-15): this wrapper used to `git add` back every
staged .py after the run (ported from the lefthook `dbos-determinism` hook,
which carried `stage_fixed: true`). That silently folded whatever the
checker had auto-fixed into someone else's commit the moment `RULES_STAGED`
stopped meaning just this commit's own staged paths and became the whole
tracked index like every other hook's population — see fix-whitespace's
README for the incident this class of bug caused. Anything the checker
still edits on disk is left unstaged; `git status` shows it and a human (or
the next commit) decides whether to include it.

Why: a DBOS workflow body must be deterministic for replay/fork to work —
wall-clock reads and randomness inside a workflow poison recovery. The
checker and its regression tests live at scripts/lint/ and
.claude/skills/amg-hooks/research-monorepo/unit-tests/lint-gates-actually-bite/test_workflow_determinism_lint.py.

Delete-check: cannot delete — determinism is a DBOS correctness invariant;
this is aii/ because the checker is repo-local.
