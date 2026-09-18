<!-- hook: latex-figure-recipe-single-spelling -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: RULES_REPO
# The LaTeX figure recipe — placement token, includegraphics options, and package list — is spelled identically in the gen_full_paper prompt, its figure-fix retry, and the aii-paper-to-latex skill

The same agent reads all three sites in one task (u_prompt TODO 1 orders it
to read the skill), so a recipe spelled differently across them makes figure
sizing nondeterministic per run. **The mechanism IS wired, and the tree is
green** (re-measured 2026-09-14): `scripts/check_latex_recipe_parity.py` runs
at `research-monorepo/lefthook.yml:422-426`, globbed to the two prompt trees, and
exits 0 against research-monorepo. The width disagreement that held the rule back —
u_prompt mandating `width=\linewidth` against SKILL.md:26 showing
`width=0.92\textwidth` — is settled: both sites now spell the option list
`width=\linewidth,height=0.85\textheight,keepaspectratio`.
The other two contradictions originally cited here are retired — the height
policy now reads LAST RESORT with 0.85\textheight at BOTH sites, and `url`
is in the skill preamble (SKILL.md:14). Details in the RE-MEASURED section
below. Distinct from pending rule-prompt-claims-cite-surface (existence of
claimed external surfaces) — this is mutual consistency of duplicated
prescriptive guidance; distinct from enforced rule-viz-figure-pipeline, whose
prompt-claims test covers the aii-data-fig-gen skill only.

## Original measurement (2026-08-22) — two of its three contradictions since retired

At proposal time all three were measured as live disagreements:
prompts/steps/_4_gen_paper_repo/_4_gen_full_paper/u_prompt.py:49 mandates
`width=\linewidth,height=0.85\textheight,keepaspectratio` on every figure,
while .claude/skills/aii-paper-to-latex/SKILL.md:26 shows
`width=0.92\textwidth,keepaspectratio` and SKILL.md:41-47 says height is a
LAST RESORT — contradictory width values AND contradictory height policy;
u_prompt.py:67 demands \usepackage{hyperref} AND \usepackage{url} while the
skill preamble (SKILL.md:14) omits url. The recipe is spelled at 3 sites
(u_prompt HEADER, _4_gen_full_paper.py:108-110 fix prompt, SKILL.md), so
contradictory instructions make figure sizing nondeterministic per run.

Proposed type: **cmd-check** · scope: **whole-tree** · value: **medium** (proposer: pipeline-paper-quality)

SHIPPED — wired since `5f8db60` (2026-09-08), verified green 2026-09-14. The
card below is the original proposal, kept for its reasoning; the command it
proposes is the one that runs today.

Proposed command (implemented at approval):

    $RULE_DIR/scripts/check_latex_recipe_parity.py  # extract [!htbp] token, includegraphics option string, and usepackage set from the three sites; exit 1 on any disagreement

Proposed condition: `[ "$RULES_MODE" = commit ] || exit 1; git diff --cached --name-only -- 'aii_pipeline/src/aii_pipeline/prompts/steps/_4_gen_paper_repo/_4_gen_full_paper/' 'aii_pipeline/src/aii_pipeline/steps/_4_gen_paper_repo/_4_gen_full_paper.py' '.claude/skills/aii-paper-to-latex/' | grep -q .`

Delete-check: Delete the duplication rather than police it: hoist one LATEX_FIGURE_RECIPE
constant in the u_prompt module, have the fix prompt interpolate it, and make
the skill quote the same literal — the check then collapses to 'the option
string appears once in prompt source and the skill's copy byte-matches it'.
The rule enforces that end-state either way.

Filter verdicts (3-lens adversarial, kept 3/3):
- KEEP: The same agent reads all three prescriptions in one task and they
disagree today; the full delete (one constant) is blocked because one site is
a skill SKILL.md that can't import Python. Hoist the constant between the two
Python sites first, then the rule compares the single spelling against the
skill — a genuine cross-surface parity no claimed rule covers (prompt-claims-
cite-surface …
- KEEP: Three prescription sites read by the same agent in one task disagree
today; delete-shaped fix (hoist one recipe constant) then a trivial parity
check holds it.
- KEEP: Live three-way disagreement read by one agent in one task; prefer the
delete-form (hoist one LATEX_FIGURE_RECIPE constant, rule then greps for stray
re-spellings) over normalized triple-compare — both mechanizable, the hoist is
simpler and the check gets stronger.

INDEPENDENT VERIFICATION (2026-08-22) — verdict: **partly-wrong**. A separate agent re-measured every factual
claim above against the live tree rather than trusting it.

What it found:
WIDTH HALF CONFIRMED. `sed`/Read of aii_pipeline/src/aii_pipeline/prompts/step
s/_4_gen_paper_repo/_4_gen_full_paper/u_prompt.py:49 returns: "Constrain every
\\includegraphics with
`width=\\linewidth,height=0.85\\textheight,keepaspectratio`";
.claude/skills/aii-paper-to-latex/SKILL.md:26 returns `\includegraphics[width=
0.92\textwidth,keepaspectratio]{figures/filename.pdf}`. I compiled the skill's
o

Corrected statement of fact:
The only live disagreement is the WIDTH literal: u_prompt.py:49 mandates
`width=\linewidth` while .claude/skills/aii-paper-to-latex/SKILL.md:26 shows
`width=0.92\textwidth`, and \linewidth == \textwidth == 469.75502pt in this
document class (measured), so the same agent is told 100% and 92% in one task.
The height policy is NOT contradictory (both sites say LAST RESORT and both
name 0.85\textheight) and is already pinned by test_viz_seams.py:404-408. The
\usepackage{url} difference has no effect (hyperref loads url.sty; the skill
preamble compiles \url cleanly). _4_gen_full_paper.py:106-114 is not a third
spelling of the width/height/package recipe — it carries only the [!htbp]
token, which test_viz_seams.py:326-345 already enforces. So this is a one-
literal alignment inside an already-enforced rule, not a new three-site parity
rule.

## RE-MEASURED 2026-08-26 — one contradiction is stale, one is fixed, one is the owner's

The body names three disagreements. Measured against the tree today, they are
in three different states, and only the last still blocks a mechanism.

**The height policy is NOT contradictory any more.** The body says the prompt
"mandates `width=\linewidth,height=0.85\textheight,keepaspectratio`" while the
skill "says height is a LAST RESORT". Both are now true of BOTH sites: the
prompt's own line reads "The height is a LAST RESORT, not the usual limit ... at
0.4 it bound almost everything", and the skill says "Add `height` only as a LAST
RESORT ... keep it generous — `0.85\textheight`". Same policy, same number.
(Worth noting how nearly I read this the other way: a `grep` truncated at 130
columns showed only the first clause of a very long line, and the sizing text
sits past that. The line, not the tree, was hiding it.)

**The `url` omission was real and is fixed.** The prompt orders
`\usepackage{url}`; the skill preamble listed eight packages without it. `url`
is added to the skill, which changes no behaviour — the prompt already demanded
it — and it resolves to `texlive-latex-base`, which the image installs, so
`rule-latex-preamble-ships-in-pipeline-image` stays green (verified after).

**The width value WAS a genuine disagreement and it has since been settled.**
The prompt said `width=\linewidth` and "Use exactly these option keys" while
the skill's worked example showed `width=0.92\textwidth`. An agent reading
both in one task got two concrete values, which is exactly the nondeterminism
this rule is about. The owner picked `\linewidth`: re-read 2026-09-14, both
sites spell `width=\linewidth,height=0.85\textheight,keepaspectratio`.

**The mechanism is wired, and that unblocked it.** A checker built while the
width was open would have arrived RED, and a rule that cannot be approved on
the day it lands is not ready — so this section is history, not the current
state. What ships is `scripts/check_latex_recipe_parity.py` at
`research-monorepo/lefthook.yml:422-426`: it locates the two prompt sites by NAME
rather than by line (`HEADER`, `build_figure_fix_prompt`), compares the three
facets — placement token, `\includegraphics` option list, `\usepackage` names
— and exits 2 rather than 0 when it finds fewer than two sites stating a
facet.

**The third site moved (2026-08-28).** Commit 269dfe87c (2026-08-25, "the
figure-fix prompt moves into the prompts tree") relocated the figure-fix
retry prompt: it now lives at
prompts/steps/_4_gen_paper_repo/_4_gen_full_paper/u_prompt.py:204-212 (its
`[!htbp]` literal at :208), and
steps/_4_gen_paper_repo/_4_gen_full_paper.py today contains no figure prompt
and no `[!htbp]` — its lines 106-114 are workspace-setup code. The `:108-110`
and `:106-114` citations in the sections above were exact on their dates and
are stale now; a checker built at approval reads the prompts-tree site.

## Mechanism (built 2026-09-03)

`scripts/check_latex_recipe_parity.py` — green on the real tree, exit 0,
after the one-literal fix below. Four colocated tests in
`test_the_figure_recipe_parity_gate_bites.py` prove it bites.

**What it asserts.** Three sites, three facets, and a site that does not
state a facet is never a disagreement:

- **`u_prompt.HEADER`** — placement: `!htbp`; includegraphics options:
  `width=\linewidth,…`; packages: required 2
- **`u_prompt.build_figure_fix_prompt`** — placement: `!htbp`;
  includegraphics options: —; packages: —
- **`aii-paper-to-latex/SKILL.md`** — placement: `!htbp`;
  includegraphics options: `width=\linewidth,…`; packages: preamble 9

`placement` and `includegraphics options` must agree across every site that
states them; whitespace is the only normalisation, because LaTeX ignores
spaces inside an option list.

**The sites are found by NAME, not by line.** Every line citation this rule
ever recorded went stale — the RE-MEASURED section above is largely a record
of that, `269dfe87c` having moved the figure-fix prompt out of the step
module. So the two prompt sites are located with `ast`: the `HEADER`
assignment and the `build_figure_fix_prompt` function, wherever they sit. The
checker's own first run proved the point by reporting the header recipe at
**:53**, not the `:49` this body still cites.

Two extractions needed care and both are pinned by the shape of the tree
rather than by a list of exceptions:

- The prompt writes `\begin{figure}[placement]` as a PLACEHOLDER two
  paragraphs before it prescribes `\begin{figure}[!htbp]`. Only real LaTeX
  float specifiers (`!htbpH`) count, which separates them without naming
  either.
- The option string appears in two forms — inside `\includegraphics[…]` in
  the skill, and as a backticked span in the prompt ("Constrain every
  \includegraphics with `…`"). A backticked span qualifies only if it holds
  `keepaspectratio` AND a `key=value` pair. That is what keeps the prompt's
  NEGATIVE example `` `max height=` `` and the skill's bare
  `` `keepaspectratio` `` out of the comparison; a looser rule reports both
  as rival spellings.

**Packages are compared by CONTAINMENT, and that is a decision, not an
oversight.** The two sites that state packages state different KINDS of
thing: the skill gives a COMPLETE preamble (its block also carries
`\documentclass`), the prompt gives a REQUIRED SUBSET — "Include
`\usepackage{hyperref}` and `\usepackage{url}`". Demanding set equality
there would report a disagreement that does not exist and would land the
rule red on a tree nobody has broken. It is also the relation this body
already settled once: the real `url` omission was closed on 2026-08-26 by
ADDING `url` to the skill, making it a superset, and that was accepted as
resolving the disagreement. So `\documentclass` present means complete;
every required package must appear in every complete preamble; two complete
preambles must be equal; two required sets must be equal. Measured today:
2 required, both present among the 9.

**Discovery fails closed.** A missing site file, a named prompt site that
cannot be located, a site stating none of the three facets, or a facet fewer
than two sites state — all exit 2, never 0. The last is the one worth
spelling out: a facet only ONE site spells has no parity left to check, so a
clean run there would be a guard that is green because it never looked. The
skill's worked example is the only `\includegraphics[…]` in the tree's
prescriptive text, so deleting it is exactly that failure, and the third test
removes it and asserts exit 2.

**The stock fix — one literal, in the skill.** SKILL.md:26 now reads

```latex
\includegraphics[width=\linewidth,height=0.85\textheight,keepaspectratio]{figures/filename.pdf}
```

where it read `width=0.92\textwidth,keepaspectratio`. **The prompt won
because the prompt is what the pipeline executes**: it mandates the option
string and adds "Use exactly these option keys", while the skill's block is
an illustrative worked example the agent reads alongside it. Aligning the
illustration to the executed instruction changes no prescribed behaviour;
aligning the instruction to the illustration would have changed every
generated paper's figure width, which is the layout call this body correctly
refused to make on its own. Nothing else in the skill was touched — the
prose at SKILL.md:41-47 still reads "Add `height` only as a LAST RESORT",
which is the same tension the prompt itself carries ("The height is a LAST
RESORT, not the usual limit") and therefore parity, not a new contradiction.

**Probe.** Against a tmp copy of the two site files with that single width
literal changed back:

```
aii_pipeline/.../u_prompt.py:53: includegraphics options: prompt-header states `width=\linewidth,height=0.85\textheight,keepaspectratio`
.claude/skills/aii-paper-to-latex/SKILL.md:26: includegraphics options: skill states `width=0.92\textwidth,height=0.85\textheight,keepaspectratio`
```

exit 1, both spellings cited with the file and line of each. On the real
tree: exit 0, no output. `.venv/bin/python -m pytest <rule dir> -q` → 4
passed.

**One thing this rule still does not do**, and it is the delete-check the
proposal opens with: the recipe is still spelled twice in prompt source
rather than hoisted into one `LATEX_FIGURE_RECIPE` constant the fix prompt
interpolates. The checker enforces the end-state either way, so the hoist
remains available as a simplification rather than a prerequisite — but note
the figure-fix site states no option string at all today, so the hoist would
have to add one before it could share it.
