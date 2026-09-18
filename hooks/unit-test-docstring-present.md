<!-- hook: unit-test-docstring-present -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Re-homed 2026-09-15: this hook now runs as a research-monorepo consumer check,
> discovered by `research-monorepo-ast-checks` (`dispatch.py`) over the consumer's own
> `tests/unit/<group>/test_*.py`, not this repo's own vendored (and since-deleted)
> copy of that tree. The `RULES_ENGINE_DIR`/`--recurse-submodules` machinery the
> body below describes historically no longer applies — the population is a
> native consumer tree, never a submodule.
# Every rule-engine unit test opens with a module docstring of at least 40 characters

The statement names what the mechanism checks — presence and a 40-character
floor — and no more. It used to promise a docstring "naming what it pins";
the register (the defect AND the incident behind it) is a judgement the
checker cannot make, the body below calls the floor "only a proxy" for it,
and nine subject-naming one-liners are left for a person. That register stays
with `general/hooks/test-genre-declared`. Under the retired engine the
condition carried a `[ "$RULES_MODE" = all ] ||` escape (added 2026-08-28)
because without it the condition exited 1 in all-mode and `rules.py all`
skipped the rule permanently while its statement claimed every test. There is
no condition today: lefthook's `glob:` is the whole gate.

Repo CLAUDE.md ('Unit tests live in the amg-hooks submodule' — the
heading was 'the rule engine' when this was written) states the convention:
'a docstring naming the defect it pins and the incident behind it'.
RE-MEASURED 2026-09-14 in research-monorepo: **707 of 707** `test_*.py` files under
`.claude/skills/amg-hooks/*/unit-tests/*` carry a module docstring of
40+ chars — no outlier left, and the 2026-08 figure of 486 of 487 was taken
under `.claude/skills/amg-rule-engine/`, which now has ZERO tracked files. The
population moved wholesale rather than grew. A norm at
100% adherence is cheapest to pin now: presence and length are cmd-able; only
the register ('names the defect AND the incident') stays with the agent-side
rule-test-genre-declared, which covers genre, not docstrings. Promotion note:
this rule is fully cmd from day one — no agent half needed.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: docs-comments)

Command (BUILT — `dispatch.py`, discovered by `research-monorepo-ast-checks`):

    python3 $RULE_DIR/scripts/check_test_docstrings.py  # ast.get_docstring over tracked test_*.py under tests/unit: present, and >= 40 chars

Condition: none. lefthook gates the dispatcher command with `glob: 'tests/unit/**'`
(`research-monorepo/lefthook.yml`, `research-monorepo-ast-checks`) and nothing else — the
`RULES_MODE` escape below was the retired engine's shape, and no condition
survives the migration.

Delete-check: Cannot delete the dimension — the docstring is the only place the pinned
incident is recorded (the test name carries the sentence, the docstring
carries the WHY). The near-universal adherence shows the convention costs
little; one file to fix before enforcing.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: 486/487 with the CLAUDE.md convention explicit; fix the outlier and
pin. rule-module-docstrings excludes tests (verified), so no overlap; the
docstring is the only record of the pinned incident.
- KEEP: 486/487 already comply and the docstring is the only record of the
pinned incident — the convention CLAUDE.md states. One-file fix then a near-
zero-cost presence check scoped to the rules tree, which module-docstrings
does not cover.
- KEEP: AST docstring-presence check over rule-tree tests, 486/487 compliant
today. Trivial, loud; this is the mechanical fringe that lets rule-test-
authoring-style stay judgment-only.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **the claim's shape is
exact; its denominator has drifted; and the outlier is now fixed, so this
rule would ship at zero stock.**

Re-measured with `ast.get_docstring` over `git ls-files`:

| quantity | claimed | measured |
|---|---|---|
| modules | 487 | 504 |
| no docstring at all | 0 | 0 |
| shorter than 40 chars | 1 | 1 |
| the outlier | `test_ranking.py` | same, 38 chars |

Every qualitative part reproduces exactly — one outlier, the named file, the
named length. Only the denominator moved, and it moved for a known reason:
the suite is growing (`rule-test-genre-declared` records 477 -> 499 -> 507
over four days). A proposal that pins a total will always drift; one that
pins "exactly one outlier, and here it is" does not.

**The outlier is fixed rather than left as stock.** Its docstring was
`"""Tests for claude_cred_manager.ranking."""` — 38 characters that restate
the import path and name no invariant, which is the shape the house
convention exists to prevent, not merely two characters short of a
threshold. It now names the three distinctions the module actually pins
(missing-is-not-zero, stale-is-not-fresh, weekly-sonnet-is-not-capacity) and
the exhausted-alternatives waiver, including which two tests pin the waiver's
halves. Both named tests were checked to exist; all 16 still pass.

Measured after: **0 of 504** modules under 40 characters. So the
"99.8% adherence" argument in the body is now 100%, which strengthens the
case the proposal makes — a norm already universally followed is the cheapest
possible thing to pin, because approving it cannot generate a backlog.

Worth noting for whoever builds the checker: a 40-character floor is a proxy
for "says something", and this outlier is why it is only a proxy. 38
characters of "Tests for X" and 41 characters of "Tests for X, extended"
would both be judged by length rather than content. The floor is still worth
having as the mechanical half; it just cannot be the whole rule.

ADOPTION (2026-08-25): BUILT — and built WITHOUT the two-line floor, which is a
correction rather than an omission.

What this rule measured is length: "486 of 487 carry a module docstring of 40+
chars", re-measured above as 504 with one outlier since fixed. What its proposed
command asked for is length **and** `>= 2 lines`. That second condition appears
in no measurement anywhere in this rule — it entered as a detail of the command
line and was never run against the tree.

Run against the tree, it fails. Measured 2026-08-25 over **507** modules (the
suite grew again, exactly as the verification section predicts a pinned total
will):

| criterion | offenders |
|---|---|
| no docstring at all | 0 |
| under 40 chars | 0 |
| under 2 lines | **9** |

So building the command as written would have shipped a gate that is red on
arrival — the one outcome an approval must not produce, since a rule that
blocks every commit the day it lands gets bypassed rather than fixed. Both
MEASURED halves hold at zero, so the gate as built arrives green.

The 9 one-liners are a real gap against the convention's spirit and are left
for an owner rather than silently absorbed. Six sit in
`rule-cred-manager-service`, whose tests migrated in from a separate service and
predate this convention; they read `"""Tests for
claude_cred_manager.store.CredentialStore."""`. Naming the subject is not naming
the defect, which is precisely the distinction the verification section draws
above when it calls the 40-char floor "only a proxy". But the fix is to write
what each test actually pins, and that needs the incident behind it — inventing
one to satisfy a line count would put fiction into the record this suite exists
to be. A gate cannot tell the difference; a person can.

Proven to bite in a throwaway tree rather than inferred from this repo's clean
exit: a module with no docstring and one with a 16-char docstring are both
named, and a proper one is left alone.
