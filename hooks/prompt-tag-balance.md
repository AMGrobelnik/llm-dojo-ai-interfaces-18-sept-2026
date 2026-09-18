<!-- hook: prompt-tag-balance -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Every structural XML-ish section tag opened in a prompt module's template strings is closed the same number of times, module-scoped over AST string fragments

The house format is tag-block sections (pending rule-prompt-string-style pins
the style but nothing checks balance). A deleted or renamed close tag ships a
structurally broken prompt with every test green. Verified programmable at
near-zero false-positive cost: naive whole-line grep yields 36-56 false hits
(tags referenced in prose, opens at f-string fragment starts like
u_prompt.py:89 f\"\"\"<task_preview>), but an AST-fragment scan over all 73
modules leaves exactly one residual — the attribute-interpolated open
<inspiration id=\"{i}\"> at _2_hypo_loop/_1_gen_hypo/u_prompt.py:209 — which
the script special-cases, giving 0 findings today. Prose mentions like
'<max_notebook_total_runtime>' inline in u_prompt_code.py stay invisible via
line-anchoring.

Mechanism (implemented 2026-08-26, `scripts/check_tag_balance.py`):

    .venv/bin/python $RULE_DIR/scripts/check_tag_balance.py

Arrives green: 73 prompt modules, 135 opening tags, 0 imbalanced.

**Three false-positive shapes, and the body only predicted one.** The naive
whole-file grep reports 31 imbalances (prose mentions in docstrings; Python is
not prompt text), which the body records. Two more only appear once you build
it:

- An f-string SPLITS a tag across the interpolation, so a scan over bare
  `ast.Constant` values sees `</inspiration>` with no open. The body predicted
  this one and proposed special-casing that single site; reconstructing each
  string with interpolations as an explicit placeholder handles it as a class
  instead, with no site named.
- Four opens sit immediately after an interpolation on the same TEMPLATE line
  — `}<artifact_plan>` — where the branch before them expands to a block
  ending in a newline, or to nothing. They are at line start in the RENDERED
  prompt but not in the source, so a strict anchor calls all four broken.

**A shortcut here is right by accident, which is worse than wrong.** Joining
raw fragments with a newline and matching attributes as `[^>]*` also balances
this tree — because a negated character class spans the join. It reports 0,
the same as the correct version, and stops being true the moment the separator
or the interpolation position changes. Making the hole explicit costs nothing
and means the check describes what it intends to.

Probed six ways: a deleted close and a renamed open fire; a balanced pair, a
prose mention mid-sentence, a split f-string tag and an interpolation-adjacent
tag do not.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: prompts)

Proposed command (implemented at approval):

    python3 $RULE_DIR/scripts/check_tag_balance.py aii_pipeline/src/aii_pipeline/prompts

Delete-check: Not deletable — tags are the prompt format itself, and replacing hand-written
tags with a builder DSL that auto-closes would trade the entire house
readability convention (template reads as the rendered prompt) for one check.
Rule is the right form.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: A broken close tag ships a structurally broken prompt with every gate
green; verified programmable at near-zero false-positive cost via AST string
fragments. Nothing else looks at prompt structure.
- KEEP: A dropped close tag ships a structurally broken prompt with every gate
green — invisible until output quality drops. Verified programmable at near-
zero FP over AST string fragments; complements the pending style rule with an
actual invariant.
- KEEP: Module-scoped open/close tag counting over AST string fragments — the
module-level aggregation handles open-in-one-fragment/close-in-another. The
why records the FP analysis (naive grep 36-56 FPs, AST-scoped near zero).
Implementable, loud.

INDEPENDENT VERIFICATION (2026-08-24) — verdict: **holds, exactly**.

Both measurable claims reproduce to the digit. `git ls-files
'aii_pipeline/**/prompts/**/*.py'` gives **73** modules, and the single
cited residual is at the stated line: `u_prompt.py:209`,
`sections.append(f'<inspiration id=…`.

Worth being explicit about what the "one residual" means, since the
phrasing invites misreading it as a live defect. It is not. The body says
the script special-cases that attribute-interpolated open, "giving 0
findings today" — so the stock is ZERO and this is a pure regression
guard. A reader skimming for "exactly one residual" would file a defect
that does not exist.
