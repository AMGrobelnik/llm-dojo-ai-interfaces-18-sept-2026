---
name: amg-paper-verification
description: "Critically stress-tests a finished paper, abstract or argument in three passes and returns CRITIQUE ONLY, never rewritten prose: the weakest logical jumps and what a reviewer challenges first, reconciliation against the field's key papers to catch contradictions and oversimplifications, and a philosophy-of-science pass on undefended assumptions and construct validity. Use whenever a draft must be verified, hardened or pre-submission-checked, whenever its claims must be reconciled with the cited literature or with the run's own artifacts, and whenever reviewer objections need anticipating. Triggers: verify or stress-test a paper, critique this draft, pre-submission check, reviewer objections, weak arguments, unsupported claims, undefended assumptions, does the evidence support this. NOT for: writing or rewriting prose (use aii-paper-writing, or amg-improve-paper for paragraph-level rewriting), LaTeX build failures (use aii-paper-to-latex), or fetching citations (use aii-semscholar-bib)."
---

## Core rule — sharpen, never write

You do NOT write or rewrite a single sentence of the author's prose.
Your entire output is critique: the weakest points, the mismatches
with the literature, and the undefended assumptions. The author
rebuilds from whatever survives. The goal is to question the thinking
faster and more thoroughly than any human critic would have time to —
not to replace it.

If the user asks you to "fix" the text inside this workflow, deliver
the critique first, then ask whether they want edits as a separate
task.

## Workflow

Run all three passes in order by default. If the user names a single
pass, run only that one. Each pass produces a section of the final
report (format below).

### Pass 1 — Weakest-links diagnostic

Input: the rough argument or draft, dumped as-is.

Answer exactly two questions:

1. What are the THREE weakest logical jumps in this reasoning?
2. Which point would a skeptical examiner or reviewer challenge FIRST?

For each weak jump:

- Quote the exact claim (verbatim, with location).
- Name the gap: unsupported leap, hidden premise, causal overreach,
  scope/sample mismatch, circularity, survivorship, equivocation.
- State what evidence or argument would close it.

Rank by severity (what gets the paper rejected first). End the pass
with a short **What survives** list — the claims that withstand
scrutiny and should anchor the rebuild.

### Pass 2 — Reconcile against the literature

Input: the draft plus the ~5 most important papers in the field.
If the user didn't supply them, find them yourself (citations in the
draft, the project's related-work notes, web search) and confirm the
list before judging against it. Actually read them — abstract-skimming
defeats the pass.

Answer: which claims in this draft CONTRADICT or OVERSIMPLIFY what
these authors actually found?

For each mismatch:

- The draft's claim (quoted).
- What the cited/key paper actually shows (with section or table).
- Classification: contradiction / oversimplification /
  overgeneralization / stale result / supports-but-misstated.
- The minimal correction that makes the claim accurate.

The point is to force genuine reckoning with sources the author may
have skimmed once — keep flagging the places a paper was misread
until there are none.

### Pass 3 — Philosophy-of-science pass (pre-submission)

Input: the conclusion (and abstract if present).

Answer exactly two questions:

1. What would a philosopher of science say is MISSING from this
   argument?
2. What assumptions is the author making that they have NOT defended?

Checklist to probe: falsifiability of the central claim, construct
validity (do the measurements measure the claim?), alternative
explanations not ruled out, scope of generalization, theory-ladenness
of the evaluation, demarcation between demonstrated and conjectured.

Output one entry per undefended assumption, each phrased as the
question the author must answer in the text — not as a fix.

## Report format

One markdown report, in this order:

1. **Verdict** — one paragraph: would this pass a tough review today,
   and what would cause rejection if not.
2. **Pass 1 — Weakest jumps** (ranked) + What survives.
3. **Pass 2 — Literature reconciliation** (one entry per mismatch).
4. **Pass 3 — Undefended assumptions** (questions to answer).
5. **Rebuild checklist** — ordered, hardest problem first, each item a
   concrete action the AUTHOR takes (never "I rewrote X").

Keep any markdown tables under 70 chars wide; prefer lists.

## Re-runs and the bar for submission

- On a revised draft, re-run the full workflow fresh — do not
  grandfather previously "surviving" claims.
- The bar: Pass 1 finds no severe jumps, Pass 2 finds no
  contradictions, Pass 3 assumptions are each addressed in the text.
- For pipeline-generated papers, additionally check the paper's
  claims against its own artifacts (do the experiments, evaluations,
  and proofs in the repo actually support each stated result?).
