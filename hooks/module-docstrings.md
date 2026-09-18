<!-- hook: module-docstrings -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# A new module's docstring explains WHY, in the house register

Applies only to Python modules ADDED (or near-fully rewritten) by the staged
diff, in package source — not tests, not scripts/, not .claude/.

The house form, measured 2026-08-22 at 536 of 545 package-source modules — 457 of 462 once `__init__.py` is set aside, which is the population the earlier "457 of 462" counted, not a tree that grew: a one-line
summary, a blank line, then prose paragraphs explaining WHY the module
exists, what breaks without it, and the incident or measurement behind it —
never a restatement of the filename. Big modules usually get long WHYs (122 of the
154 modules over 200 code lines carry ≥5 docstring lines; all 154 carry
some docstring). The ratio is the norm this rule protects, not a floor it
enforces — the gate is on ADDED modules, and shortness alone never fails.

FAIL only when the diff adds a package-source module whose docstring is
missing or is a bare filename-restatement ("Utilities for X."). Quote the
added docstring (or the bare `"""..."""` line) as evidence. PASS edits to
existing modules, test files, and generated code.

Fix when blocked: write the why — what problem this solves, what breaks
without it, any measurement that motivated it. Two paragraphs beat two
sentences; this repo explains itself in prose deliberately (the 600-line cap
excludes comments for exactly this reason).

Delete-check: ruff D100 already forces docstring PRESENCE in most trees;
this rule exists for the register, which no mechanical check can read.

Scope note (2026-08-22): applies to modules ADDED by the staged diff by
design — the docstring format is a birth-time contract. The whole-tree
docstring dimension is covered by the pending candidates
rule-big-module-docstring-floor and rule-unit-test-docstring-present.

RE-MEASURED 2026-08-24 — **exact, both figures.** Recomputed over tracked
`*.py` in the six package trees with `/tests/` excluded, counting code
lines as non-blank non-comment and parsing each module docstring with
`ast`: **154** modules exceed 200 code lines, and **122** of them carry
five or more docstring lines. Both match the stated census to the digit,
which is unusual — most counts in this tree have drifted by growth.

RE-MEASURED 2026-08-26 — **the ratio held exactly; the census grew by 3.**

| quantity | 08-22/24 | 08-26 |
|---|---|---|
| documented / all | 536 / 545 | **539 / 548** |
| documented / non-`__init__` | 457 / 462 | **460 / 465** |
| `>200` lines with ≥5 doc lines | 122 / 154 | 122 / 154 |

Both populations gained exactly 3 modules and both gained exactly 3
documented ones, so the undocumented remainder is unchanged — 9 overall
and 5 once `__init__.py` is set aside. The 2026-08-24 note called the
figures "exact" and predicted that most counts here drift by growth; it
was right about the mechanism and is now an instance of it.

The remainder is not a backlog. Every undocumented non-`__init__`
module is a Django auto-generated migration under
`aii_server/dashboard/migrations/`, which no one hand-writes and this
gate never sees — it fires only on modules ADDED by a staged diff.

`all 154 carry some docstring` re-verified true: of the 154 modules over
200 code lines, 0 lack one.
