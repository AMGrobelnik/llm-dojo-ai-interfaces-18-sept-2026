# A migration that has already shipped is append-only: between the newest release tag and the index it may gain files, never change one

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | relation | 1s | active |

## Why

The applied-migrations table records only the migration's `(app, name)`. There
is no content hash anywhere in Django, so an edited file is never re-run: the
deployed schema silently stops matching the file that claims to describe it,
and no later command can notice. `rule-django-migrations` runs `makemigrations
--check --dry-run`, which compares the models against the SUM of the migration
files — edit an applied one and that sum is unchanged, so the gate stays green
while the database diverges permanently. (That command does catch multiple
leaf nodes, so graph linearity is already covered and is not re-checked here.)

The convention holds and nothing enforced it. Swept across the whole release
history — every consecutive `v*` pair, `git diff --name-status` over the
migrations directory with adds filtered out — the count of modified-after-
release files is 0 over 90 tag transitions, and `0002` through `0008` each
carry exactly one commit. The neighbouring expand/contract rule was measured
and rejected: 90 release transitions, 0 rollbacks, and Postgres runs inside
the pod that gets swapped, so there is no rolling window to protect.

The agent rule that preceded this hook recorded 5 applications, 3 blocks and
**no evidence text at all** — five silent passes for a judgment that is one
`git diff`.

## Mechanism

`check.py` resolves the baseline — the newest release tag — then diffs it
against the INDEX and reads the name-status letters.

| failure mode | mechanism |
|---|---|
| a shipped migration is edited | status `M` |
| deleted | status `D` |
| renamed (new name, re-run) | status `R`, old name named |
| file becomes a symlink | status `T` |
| a new migration is added | status `A`, allowed |
| the edit is staged, not committed | end of the diff is the index |
| tags unfetched, no baseline | exit 2 |
| the migrations directory moves | discovered, exit 2 if none |

Two things differ from the command the old rule proposed, and both are
load-bearing.

The comparison end is the **index** (`git diff --cached <tag>`), not `HEAD`.
At commit time `HEAD` is the previous commit, so `<tag>..HEAD` notices an
edited migration one commit after it landed. Reading the index also means a
concurrent agent's unstaged edit in the same checkout cannot decide the
verdict. In a clean tree index equals HEAD, so the sweep is unchanged.

Migration directories are **discovered**, not named: any tracked
`*/migrations/__init__.py` marks its own directory, and discovery runs over
the index AND over the baseline tag, because a directory deleted wholesale
since the tag is exactly a violation and is invisible to a discovery that only
looks at today. A second Django app is covered with no edit.

The tag list is sorted by `creatordate`, not lexically: `v2026.09.07.10` sorts
before `v2026.09.07.9` in a plain listing, and picking that as the baseline
would compare against a tag where the newer migration does not yet exist —
every edit to it then reads as an add. A test pins this with two tags an hour
apart.

**Why the fragment passes no `{staged_files}`.** A relation hook keeps its
glob and runs whole-tree, and here that is not a style choice. Measured: after
`git mv`, lefthook hands the command only the NEW path, and
`git diff --cached --name-status <tag> -- <new path>` reports `A`, not `R100
old new` — restricting the pathspec to one side of a rename hides the rename.
Scoped to `{staged_files}`, a renamed shipped migration passes silently. The
whole-tree run costs 0.04 s, so there is nothing to buy by scoping it.

`check.py [PATH...]` still honours paths (the contract, and how a human checks
one file); paths outside a discovered migrations directory are a quiet no-op.

## Stock

**0 findings**, measured against `/home/<user>/projects/research-monorepo` at HEAD
`3f1060fa7` (re-confirmed unchanged at `eaf82761c`). Baseline tag `v2026.09.07.11` out of 145 `v*` tags; one
migrations directory discovered, `aii_server/dashboard/migrations`, holding 10
numbered migrations in the index. Whole-tree runtime 0.04 s (0.03 s scoped to
a single migration), so the hook ships `active`.

## Fragility

| refactor | effect | guard |
|---|---|---|
| tags not fetched | no baseline | exit 2 |
| the app dir moves | follows it | discovery |
| Django drops `__init__.py` | nothing found | exit 2 |
| a repo that never released | no baseline | exit 2, loudly |
| deploys stop tagging | baseline ages | none — see below |

Two tags created in the SAME second tie under `creatordate` and fall back to
refname order, which is the lexical trap again. Deploy tags are minutes to
hours apart, so this does not arise here.

If `aii_launcher --redeploy` stops pushing a `v<CalVer>` tag, the baseline
silently ages and the immutability window widens: the check keeps working and
grows conservative rather than failing. A warning when the newest tag is older
than N days would close it.

## Residue

The hook cannot see a commit that ONLY deletes migrations. Lefthook builds the
file list with `--diff-filter=ACMR`, so a pure deletion matches no glob and
the command is skipped before `check.py` runs — measured, and true whether or
not `{staged_files}` is passed. A deletion alongside any other migration
change is caught, which is the realistic squash-and-drop shape.

Deliberately not implemented: the expand/contract half of the original rule
(a column drop as a two-release change), rejected on a measured zero rollbacks
across 90 release transitions. Ceremony for a hazard with a measured frequency
of zero is the requirement being wrong.

The check proves a shipped migration was not touched. It says nothing about
whether the migration was CORRECT, whether it matches the models, or whether
the graph has one leaf — the first two are `makemigrations --check`'s job and
the third is already covered by it.
