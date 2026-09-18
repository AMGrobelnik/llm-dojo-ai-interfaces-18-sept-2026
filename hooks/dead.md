<!-- hook: dead -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_STAGED
# No dead code in aii_lib / aii_pipeline / aii_server / aii_launcher / aii_runpod

Pure-Python flat-namespace dead-code finder — name-matching catches unused
module-level symbols across the tree. `dead_allowlist.txt` lists symbols
dead can't see as used (Django settings, framework callbacks, Pydantic
validators); add new entries there with a comment WHY when dead flags a
real false positive. Project-wide — dead does its own `git ls-files` walk,
so no staged-file scoping. That walk is run with git's per-invocation
bindings scrubbed (`GIT_INDEX_FILE` and friends, the same five
`lib/amg_hooks/amg-hooks-git` drops): a commit hook inherits `GIT_INDEX_FILE`
naming the temporary index `git commit --only` builds -- HEAD plus the
committer's own paths -- and against that index every symbol only a PEER's
staged file uses reads as dead. Measured 2026-09-07 in research-monorepo:
`drop_legacy_notify_trigger` was reported dead while its one caller sat in
another session's staged `dbos_app/schema_bootstrap.py`, and that blocked
every Python commit in the shared checkout for two hours. Scrubbed, the
walk reads the real shared index. Files nobody has staged at all stay
invisible either way -- `dead` has no flag for untracked files -- so a
symbol used only from a brand-new unstaged module still reports dead; that
is a known limit, not a silent one. dead always exits 0, so `check.sh` fails on any
output instead. `--exclude "/archive/"` skips archived / phased-out source,
matching the ruff/ty archive excludes — no live shared helper is
archive-only-consumed any more, so scanning it would only surface
phased-out dead code.

WHY `--files` lists five packages and not every Python root:
`claude_cred_manager` is left out on purpose. Measured by running dead
against it directly — it reports exactly 7 symbols, and all 7 (health,
list_accounts, get_credentials, usage_snapshot, select_slot, start_relogin,
job_status) are `@app.get`/`@app.post` handlers defined inside the app
factory in app.py. dead cannot see decorator-based registration, so every
one is a false positive and there are no true positives to trade for them.
Bringing the package in scope would mean 7 allowlist entries bought with
zero coverage — and the allowlist is meant to be a last resort, not a
silencer. Revisit if that package ever grows plain helper functions.
Install once: `uv tool install dead==2.1.0`.

Fix when blocked: delete the dead symbol (that is the point), or — for a
genuine false positive dead cannot see — add it to `dead_allowlist.txt`
with a comment WHY, in the same commit. Note a re-export counts as a read,
so a module split can make moved symbols look live; an allowlist entry
that starts "silencing nothing" after a split is that, not evidence of use.

Delete-check: tool-enforced, cannot delete — dead code accretes silently
without a finder; the tuning knobs are the `--files` scope and the
allowlist, both in one place each.
