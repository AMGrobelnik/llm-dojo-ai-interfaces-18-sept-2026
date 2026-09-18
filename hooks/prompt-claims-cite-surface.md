<!-- hook: prompt-claims-cite-surface -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every capability claim a prompt makes about an external surface (skill flags, CLI commands, file extensions, supported options) is verified against that surface, whole-tree, with quoted evidence

Five commits in recent history are this one defect: 89f58446d 'the prompt's
checklist asked for two things that cannot happen', d381a9ce2 'still asked the
agent to police tick labels', 3d71ed5a4 'stop forbidding what the skill says
is supported', 563c891f4 stale chart-type menu, d360d692a 'never used the
style preset built for it'. Coverage today is partial: rule-skills-declare-
what-exists checks names resolve (not claims), and test_viz_prompt_claims
mechanizes claim-checking for the gen_viz prompts only — e.g.
_4_gen_full_paper/u_prompt.py:47's '.pdf for data / .jpg for concept' prose
duplicates VIZ_FORMAT_BY_TYPE (gen_viz out_schema.py:143-145) with nothing
pinning the rest of the tree. The hard part — deciding what constitutes a
claim and reading the named surface's semantics — is genuinely non-
programmable in general.

Mechanism (implemented 2026-08-26, `scripts/extract_claims.py`):

    .venv/bin/python $RULE_DIR/scripts/extract_claims.py

**This mechanizes a SLICE and the rule stays an agent-check**, exactly as the
body argues. Deciding what counts as a capability claim, and reading a named
surface's semantics to judge it, is a judgement. What a machine can do is the
subset where the prompt restates a value that exists as a CONSTANT — then both
sides are readable and the comparison is exact.

The motivating instance is now gated: `_4_gen_full_paper/u_prompt.py` tells the
agent "Data figures are delivered as `.pdf` … and concept figures as `.jpg`",
duplicating `VIZ_FORMAT_BY_TYPE`. Both claims are correct today.

**It resolves the constant rather than reading the literal.**
`VIZ_FORMAT_BY_TYPE` is `{"data": "pdf", "concept": VIZ_OUTPUT_FORMAT}` — one
value is a literal and the other a NAME. Matching literal text would compare
the prompt against the string `VIZ_OUTPUT_FORMAT`, which no prompt will ever
contain, so the concept half would silently check nothing. Both are resolved
through the module's other constants first.

Scope is deliberately ONE mapping. A sweep that guessed at every claim would
produce a candidate list nobody reads — worse than no sweep, because this
rule's value is the judgement, and a noisy helper trains its reader to skip it.

Probed five ways: a changed constant with stale prose, and a prompt naming the
wrong extension, both fire; agreeing prose, a prompt making no claim, and prose
that follows a CHANGED named constant all pass.

Proposed type: **agent-check** · scope: **whole-tree** · value: **medium** (proposer: prompts)

Proposed condition: `git diff --cached --name-only -- aii_pipeline/src/aii_pipeline/prompts .claude/skills | grep -q .`

Delete-check: Per-claim deletion is the preferred fix and the body must demand it: a claim
derivable from a constant gets interpolated from that constant (the
VIZ_FORMAT_BY_TYPE prose is derivable today), and a mechanizable claim family
gets a pin test in the owning unit-tests group — each promotion shrinks this
rule. Body mechanizes extraction via $RULE_DIR/scripts/extract_claims.py
(flag/extension/command tokens per module plus
tests/source_probe.skills_loaded_by) and instructs exhaustive whole-tree
verification with quoted file:line evidence, never diff-only. Fully cmd when
every claim family has a pin test — that is the promotion criterion.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Five commits are this one defect (prompts asserting things an external
surface does not support). Agent check with quoted evidence is the only viable
instrument, and the body's interpolate-from-the-constant demand is the per-
claim deletion.
- KEEP: Five commits of the same defect (prompts demanding what the surface
cannot do) justify an agent rule — but the whole-tree scope is wrong:
verifying every claim in every prompt per qualifying commit is
disproportionate. Keep as staged-only over added/edited prompt claims, with
the interpolate-from-constant deletion demanded per claim.
- KEEP: Legitimately agent-typed: verifying a prose capability claim against a
skill's actual documented surface requires reading and judgment, no grep can
align 'never use X' with what a skill README permits. Five incident commits
justify the cost. The body should demand the per-claim deletion (interpolate
from constants) where derivable.
