<!-- hook: commit-subject-length -->

| stage | scope | budget | status |
|---|---|---|---|
| commit-msg | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_MSG_FILE, RULE_DIR
# Commit subjects stay ≤ 72 characters

Measured over 6 months: 40% of subjects exceeded 72 chars (1,224 of 3,049;
median 70, max 317). Long subjects wrap in every log view and usually mean
the subject is carrying body-detail or a second concern (see
rule-commit-one-concern).

Fix when blocked: keep the subject to `type(scope): what changed`; move the
how/why into the body — bodies are free-form and unlimited.

Delete-check: cannot delete — subject length is a property of every commit;
the only alternative is an open dimension, which measurably drifted to 317.

RE-MEASURED 2026-08-24 — **the rule is working, and the numbers say so in a
way the original census could not.**

| quantity | body | today |
|---|---|---|
| subjects in the window | 3,049 | 3,232 |
| over 72 chars | 1,224 (40%) | 1,190 (37%) |
| median | 70 | 69 |
| max | 317 | 317 |

The interesting pair is the first two rows read together. The window gained
**183** subjects while the count of long ones **fell by 34**. A rolling window
can only do that if the commits entering it comply at a much higher rate than
the ones ageing out — which is the effect this rule exists to have, and it is
visible without any before/after framing.

`max` is unchanged at 317 because that commit is still inside the six months.
When it ages out the figure will drop sharply; do not read that as an
improvement.

Note the denominator disagrees with `rule-commit-one-concern`, which records
3,149 for the same window. That is not a contradiction: this counts
`--no-merges` (3,232 here) and the sibling counts all commits (3,299 today).
Two rules measuring the same window with different filters should say so,
which neither did.
