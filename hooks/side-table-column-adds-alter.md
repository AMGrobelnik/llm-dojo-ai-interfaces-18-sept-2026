<!-- hook: side-table-column-adds-alter -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A column added to a SQLAlchemy side table after it first shipped is also added by `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` in its `ensure_*` function, with DEFAULT and index parity

Full statement: a column added to a SQLAlchemy side table AFTER that table
first shipped is also added by an explicit `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS` in the table's own `ensure_*` function — with a matching DEFAULT when
the column is NOT NULL and a matching `CREATE INDEX IF NOT EXISTS
ix_<table>_<col>` when it declares `index=True` — because
`create_all(checkfirst=True)` creates missing TABLES and never missing COLUMNS.
Re-run 2026-08-28: `scripts/check_side_table_alters.py` exits 0.

10 side tables across 9 modules all evolve this way, and the hazard is written
down three times in the source, each time as an incident-shaped warning. `sed
-n '250,330p' aii_server/dashboard/services/run_cost.py` -> "``create_all``
only CREATES; it never alters a table that already exists, so a column added
to the definition above would be missing in any deployment whose table
predates it and every SELECT would fail". `sed -n '280,312p'
aii_server/dashboard/services/runs_sidebar.py` -> "Verified rather than
assumed: declaring ``aii_run_sidebar_meta`` with an extra column and running
``create_all(checkfirst=True)`` against the dev database left its five columns
exactly as they were... It would pass every local test and fail only in
production, as an ``UndefinedColumn`` on the sidebar's hot path." And `sed -n
'240,300p' aii_lib/src/aii_lib/run/events/cost_projection.py` repeats it for a
table that has NO ALTER block at all yet. I ran the check I am proposing (per-
table git-history anchor, index+default parity included) over the tracked
tree: `tables scanned cols=55 late-added=4 violations=0` in `real 0m1.582s`.
The four late-added columns and their covering ALTERs, from `for col in ...;
do git log --oneline --reverse -S"Column(\"$col\"" -- <file>; done`:
`fork_override.target_task_id` (e4dd45eb2, 2026-06-14; table f4c83a379,
2026-05-07), `fork_override.parent_run_dir` (dabe7acac, 2026-05-15),
`runpod_orch_pods.username` (db9517003, 2026-08-03; table 0e305c439,
2026-05-09), `run_cost.notional` (38008e47f, 2026-07-31; table 5dda35b2c,
2026-06-17). Each has a matching ALTER: `grep -n 'ADD COLUMN IF NOT EXISTS' -r
aii_lib aii_server` returns exactly those four, plus `username`'s `CREATE
INDEX IF NOT EXISTS ix_aii_runpod_orch_pods_username` (SQLAlchemy's own
default index name for `Column("username", String, index=True)`, so fresh-
created and ALTER-evolved databases converge on the same object), and
`notional`'s `NOT NULL DEFAULT 0` matching `Column("notional", Float,
nullable=False, server_default="0")`. So the convention is real, universal,
currently 4/4 green, and today enforced by nothing but three prose comments. A
first draft that anchored per FILE instead of per TABLE reported 3 false
positives in run_messages.py (its second table, aii_run_message_deliveries,
landed in b468b4f0e, later than the first) — the script must key on the table-
name literal, which the final run above does.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: schema-migration)

Command (BUILT — `scripts/check_side_table_alters.py`), deliberately
UNCONDITIONED — it runs on every commit:

    python3 $RULE_DIR/scripts/check_side_table_alters.py

Clean today: 9 modules, 55 columns, zero gaps. Every column added after its
table shipped already carries its ALTER, which is the discipline the three
in-source warnings describe.

**"Late" is a RELEASE boundary, not a later commit, and getting that wrong is
the trap.** The first build compared commit identity and reported three
defects in `run_messages.py` — a table created in `dabe7acac` and given three
columns in `b468b4f0e`, six commits and twelve hours later. No `v*` tag
contains the first without the second, so no deployment ever had that table
without those columns and nothing was ever missing. The check now asks whether
some release shipped the table but not the column; a column not committed at
all is late whenever the table has shipped, which is what makes adding one
right now fail immediately.

The population is derived, not listed: any tracked module declaring
SQLAlchemy columns beside an `ensure_*` function. A list would go stale on the
tenth table, and the file it missed would be the one nobody remembered.

Verified to bite, probes with byte-identical restores: adding a column with no
ALTER fails naming it and the release it would be missing from; adding the
same column WITH an idempotent ALTER passes. Runs in 1.5 s (re-run
2026-08-28: 1.3 s, exit 0).

No condition, for the same reason the population is derived: the script
enumerates its modules from `git ls-files '*.py'` (check_side_table_alters.py
:94-101), and a path-scoped condition would be exactly the directory list the
paragraph above refuses to keep — a side table added under a third directory
would then never trigger the check. At ~1.5 s whole-tree, scoping buys
nothing. (The round-3 proposal carried a two-directory condition; building
the script dropped it.)

Delete-check: PARTLY deletable, and the deleted end-state is better. The hand-written ALTERs
exist only because `create_all_idempotent` is a create-only primitive. Replace
it with `ensure_table(metadata, engine)` in aii_lib/utils/db_ddl.py that
reflects the live table and emits `ADD COLUMN` for every declared-but-absent
column (SQLAlchemy renders the DDL via `CreateColumn` against the dialect) —
then no author can forget, and the rule collapses to a one-line grep: zero
direct `create_all_idempotent` callers and zero hand-written `ADD COLUMN IF
NOT EXISTS`. NOT deletable by moving these to Alembic/Django: `init_dbos`
states the choice deliberately (aii_lib/src/aii_lib/dbos_app/__init__.py:580
'created here rather than via a migration tool because they're tiny and
tightly coupled to the DBOS lifecycle'), and the app DB is DBOS's, not
Django's.

INDEPENDENT VERIFICATION (in-pipeline, 2026-08-24) — verdict: **holds**.
A different agent re-ran every measurement before this reached the owner.

What it found:
Re-derived the whole thing with my own AST+git scan
(/tmp/.../scratchpad/scan1.py: parse every `Table(...)` in modules that call
create_all_idempotent, anchor the table on `git log --reverse -S'"<table>"' --
<file>` and each column on `-S'Column("<col>"'`). After resolving the one
table whose name is a module constant (cost_projection.py:84 passes
COST_PROJECTION_TABLE, not a literal — my first pass crashed on it), the
surface is exactly 10 tables / 55 columns in 9 modules, matching the proposal:
$ git grep -n 'Table(' -- '*.py' | grep -v tests/ -> 10 Table calls, 9 modules
scan1 output: tables 9 cols 45 late 4 (cost_projection's 10 cols added by hand
= 55) Late-added columns, 4, with my own dates:
aii_fork_overrides.target_task_id table f4c83a379 2026-05-07 -> col e4dd45eb2
2026-06-14 aii_fork_overrides.parent_run_dir table f4c83a379 2026-05-07 -> col
dabe7acac 2026-05-15 aii_runpod_orch_pods.username table 0e305c439 2026-05-09
-> col db9517003 2026-08-03 (index=True) aii_run_cost_meta.notional table
5dda35b2c 2026-06-17 -> col 38008e47f 2026-07-31 (nullable=False)
cost_projection: all 10 columns + the table landed in ONE commit 8264e3045
2026-08-04, so 0 late there. Coverage 4/4: $ grep -rn 'ADD COLUMN IF NOT
EXISTS' aii_lib aii_server -> runpod_orch_pods.py:148 username VARCHAR;
fork_override.py:95 parent_run_dir; fork_override.py:98 target_task_id;
run_cost.py:312 notional DOUBLE PRECISION NOT NULL DEFAULT 0 (plus 2 prose
mentions) Index parity is exact, not merely plausible: $ .venv/bin/python -c
"from aii_lib.run.runpod_orch_pods import runpod_orch_pods as t;
print([(i.name,list(i.columns.keys())) for i in t.indexes])" ->
[('ix_aii_runpod_orch_pods_username', ['username']),
('ix_aii_runpod_orch_pods_pod_id', ['pod_id'])] == the literal in
runpod_orch_pods.py:152. Default parity: Column("notional", Float,
nullable=False, server_default="0") at run_cost.py:267 vs `NOT NULL DEFAULT 0`
in the ALTER. The three prose warnings exist verbatim (run_cost.py:305-311,
runs_sidebar.py:306, cost_projection.py:270-274 — the last one on a table with
no ALTER block, as claimed). Nothing enforces it today: `grep -rln 'ADD
COLUMN|create_all|checkfirst' .claude/skills/amg-hooks/rules/` hits only
test_db_ddl_race.py and test_cost_projection.py, and grepping both shows they
assert the CREATE-race swallow, never column/ALTER parity. rule-dbos-
bootstrap's SKILL.md statement is 'losing a CREATE TABLE race is not a
failure' — a different invariant. Rename robustness checked (a moved module
would silently reset the anchor and hide every late column): `git log --follow
--diff-filter=AR` on all four modules shows each was added once, at exactly
the anchor commit cited — no renames to defeat the -S anchor.

Corrected statement of fact:
No correction to the claims — every number reproduced. Two implementation
notes the rule's script must carry or it silently checks less than it says:
(1) one table name is a module constant (COST_PROJECTION_TABLE), so a scan
that only accepts `Table("literal", ...)` drops 10 of the 55 columns without
erroring — mine crashed on it, a quieter one would just skip; (2) the git -S
anchor is per-file, so if a side-table module is ever split into `_foo/` (the
repo's standard split layout, 26 existing instances per CLAUDE.md) the table's
first-commit resets to the move and every one of its columns stops looking
late. Worth using --follow, or anchoring the table on the tracked tree rather
than one path.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: create_all(checkfirst=True) creates missing TABLES and never missing
COLUMNS — a post-ship column is an UndefinedColumn on the next deploy.
Unclaimed (rule-django-migrations covers Django models only), verified holds,
mechanically checkable from git history plus the ensure_* body.
- KEEP: Demote the git archaeology: require every Column in a side-table
Table() to appear in that table's ensure_* ALTER block, no first-shipped date
needed. Deterministic AST join with the column count as the floor, and it pins
a failure mode create_all(checkfirst=True) structurally cannot catch. Not
covered by rule-django-migrations (Django models only).
- KEEP: Only PARTLY deletable, by the delete-check's own verdict —
`create_all_idempotent` is a create-only door, and short of adopting a
migration tool for SQLAlchemy side tables the ALTERs stay hand-written.
Confirmed live surface: 10 modules call create_all, 5 carry ADD COLUMN IF NOT
EXISTS. Not claimed: rule-django-migrations is `makemigrations --check --dry-
run` over …
