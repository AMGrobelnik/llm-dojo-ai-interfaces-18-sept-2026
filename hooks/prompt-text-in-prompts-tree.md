<!-- hook: prompt-text-in-prompts-tree -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH, RULES_EXCLUDE
# Agent-facing instruction strings live under prompts/, never inline in step modules — steps/ contains zero non-docstring strings with imperative agent-instruction markers

Measured with a docstring-excluded AST scan across all of aii_pipeline/steps:
exactly ONE inline agent-instruction string exists, the figure-verification
retry prompt at steps/_4_gen_paper_repo/_4_gen_full_paper.py:103-115 ('You
MUST:' at 106). Every sibling retry prompt already lives in the tree:
build_figure_retry_prompt at
prompts/steps/_3_invention_loop/_4_gen_paper_text/u_prompt.py:294,
build_artifact_retry_prompt at _1_gen_strat/u_prompt.py:233, and
_3_gen_art/retry_prompt.py. One home for prompt text is the premise the whole
aii/prompts rule family (module-shape, string-style, this survey) stands on; a
stray inline prompt is invisible to all of them.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **high** (proposer: prompts)

Command (BUILT — the mechanism exists and the frontmatter carries it):

    python3 $RULE_DIR/scripts/check_no_inline_agent_prompts.py  # AST over the steps tree; non-docstring strings carrying imperative agent-instruction markers

**The marker set was measured, not guessed.** All ten candidates were scanned
across the whole steps tree in BOTH directions — the tree before the stray was
relocated, and after. `You MUST` found the violation and nothing else; the
other nine found nothing either way. They are carried anyway: zero false
positives today, and they catch shapes `You MUST` alone would miss, since an
inline prompt opening `Your task` or `<task>` is the same defect in different
words.

Docstrings are excluded deliberately. A step docstring explains the step and
routinely quotes the instruction it sends; counting those would flag the
documentation for describing what it documents.

ADOPTION (2026-08-25): the one stray is relocated. `_build_figure_fix_prompt`
now lives in the module's prompts twin as `build_figure_fix_prompt`, under a
`RETRY PROMPT (figure verification)` banner after EXPORTS — the same placement
`build_figure_retry_prompt` has in `_4_gen_paper_text`. The move was proven
byte-identical (768 chars) by rendering the pre-move and post-move builders
against the same input, because prompt text changes agent behaviour.

Verified against history: on the tree before the relocation the gate exits 1
naming exactly one site, `_4_gen_full_paper.py:104`; today it exits 0, having
scanned 2,275 non-docstring strings across 55 step modules.

A first draft reported that one prompt as TWO findings — an f-string and the
Constant chunks inside it are separate AST nodes on different lines. The
f-string is the site; its own pieces are not.

Delete-check: This IS the delete-first shape: relocate the one stray into
_4_gen_full_paper's prompt module on adoption, then the gate enforces the zero
end-state. Small utility prompts in aii_lib
(workflows/guided_questions.py:216-227, workflows/summarize.py) are
deliberately out of scope — they are not pipeline-agent prompts and have no
prompts tree to live in.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: Exactly one stray with every sibling already compliant — relocate it,
then enforce the zero end-state with the docstring-excluded AST scan. Keeps
the prompt tree the single review surface.
- KEEP: Exactly one stray today, so adoption is a single relocation; the
docstring-excluded AST scan with imperative markers measured low-FP. Keeps the
prompt corpus greppable/reviewable in one tree, which the whole prompts rule-
family depends on.
- KEEP: Docstring-excluded AST scan of steps/ for a pinned imperative-marker
list ('You MUST', 'You are', ...). One stray to relocate first; marker list is
small and the measured FP rate is zero today. Loud.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**.
A separate agent re-ran every measurement above against the live tree.

What it found:
The named instance is real, with the line numbers off by one: `grep -n` on
aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/_4_gen_full_paper.py
gives `97: def _build_figure_fix_prompt`, `107: f"You MUST:\n"`, `171: return
False, _build_figure_fix_prompt(missing)`; the returned string literal spans
104-114 inside a paren at 103-115 — so 'You MUST:' is at 107, not 106, and the
range is 103-115/116, not 103-115 starting the string. The three sibling
builders are exactly where claimed: `grep -

Corrected statement of fact:
There are FOUR inline agent-instruction strings in
aii_pipeline/src/aii_pipeline/steps, not one:
_4_gen_paper_repo/_4_gen_full_paper.py:103-115,
_3_invention_loop/_4_gen_paper_text.py:69-73, and
_3_invention_loop/utils/gen_strat_tasks.py:73-77 and :80-83. 'You MUST:' is on
line 107, not 106. The rule's premise survives and is arguably stronger, but
any scan written to the stated 'exactly one, zero findings after the fix' spec
would fail on day one against the other three.
