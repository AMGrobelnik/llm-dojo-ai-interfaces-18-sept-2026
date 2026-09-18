<!-- hook: django-migrations -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_STAGED
# Django models and committed migrations stay in sync

Fails when a model change has no generated+committed migration file —
without it every other machine (and the server pod, which runs
`migrate --run-syncdb` at boot, aii_server.py) gets a schema that no
longer matches the models. `--check --dry-run` never touches the DB or
writes files. `config.settings_models_only` boots only the app/model
registry (no ability discovery, no DBOS, no daemons — standard Django
settings layering, see that module), and only when aii_server Python
files are staged.

COST, measured after the AII_WEB_APP_MODE fix below: fast where a
database is reachable (CI starts a worktree-local Postgres; a dev box has
the stack up), but ~11 s where none is — makemigrations probes for a
consistent migration history and waits out a 10 s connection-pool timeout
before warning and carrying on. Neither --skip-checks nor
PGCONNECT_TIMEOUT avoids it (measured: 10.3 s and 10.6 s). The wait is
the price of the check seeing the dashboard models at all — it used to
take 0.3 s because it was looking at 1 model instead of 13.

`AII_WEB_APP_MODE=1` is what puts the dashboard app in INSTALLED_APPS
without the gitignored `*.private.yaml` overlays — the same line the
repo-root conftest.py and check_openapi_drift.py both carry, and for the
same reason. WITHOUT it this hook saw 1 model instead of 13: every
dashboard model (accounts, runs, sharing, API keys) was invisible, so it
exited 0 for any change to them and could never fire for the app it
exists to protect. Measured — adding a field to UserApiKeys: exit 0
without the flag, exit 1 with it.

Fix when blocked: `cd aii_server && AII_WEB_APP_MODE=1 ../.venv/bin/python
-m django makemigrations --settings config.settings_models_only`, then
`git add` the generated migration and commit it with the model change.

Delete-check: tool-enforced, cannot delete — the schema drift it guards
against surfaces only at pod boot, far from the commit that caused it.
