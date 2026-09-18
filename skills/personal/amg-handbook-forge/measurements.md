# Measurements — the evidence behind P6/P1

Why the spec says what it says. The raw harness, blinded pools, and
per-run `VERDICT.md` live in `.forge/` (gitignored, machine-local). This
file is the distilled, checked-in record so the thresholds stay auditable
if that scratch is ever lost.

> **READ THIS FIRST — the 2026-07-29 retraction.**
> Every arm-vs-arm verdict this forge produced before 2026-07-29 used the
> **wrong unit of analysis** and is retracted as a statistical claim. The
> corrected analysis is `.forge/RUN_2026-07-27.md:589` ("DEFINITIVE
> ANALYSIS — correct unit of analysis, and it overturns every verdict
> above"). Its bottom line, verbatim:
>
> **"Not one result, per-handbook or pooled, reaches p<0.05. This forge has
> never demonstrated a statistically significant ideation benefit from any
> handbook — in either direction."**
>
> This file previously reported the retracted numbers as settled and called
> best-of picks "Most robust". It was last edited 2026-08-10 — twelve days
> AFTER the retraction — and still did not carry it. Folded in 2026-08-26.
> If you are about to design a forge change off a pick margin or a vote
> margin quoted anywhere, stop: those units do not exist any more.

## The unit problem (why everything above the line was retracted)

Three units were available; only the third is valid
(`.forge/RUN_2026-07-27.md:595-601`):

- **CHECKER** (best-of picks), n = 4-20 — **WRONG**: all checkers judge the
  SAME pool, so they are many reads of ONE ideation draw. Pseudo-replication.
- **VOTE** (individual yes/no), n = 48-192 — **ALSO WRONG**: N checkers × 6
  ideas looks like 6N observations, but it is N reads of the same 6 ideas.
  Clustered.
- **IDEA**, n = **12 per arm** — **CORRECT**: each generated idea is one
  independent draw from its arm. Score it by the fraction of checkers voting
  yes; compare arms with Mann-Whitney U.

The practical consequence is larger than it looks. Best-of picks were the
forge's *primary* read-out, chosen precisely because they seemed most
robust — so the retraction hits the strongest-looking evidence hardest,
not the weakest.

## Method (identical across runs)

Per run: **k=6** independent Fable-5 ideation samples per arm on one
ceiling scenario → strip citation tags → blind-pool + shuffle all 2k
outputs → **4** independent Fable-5 checkers score bounded yes/no
criteria. Two rounds pool to k=12.

Score each IDEA by the fraction of checkers voting yes, then compare the
two arms' 12-idea distributions with an exact Mann-Whitney U. Do **not**
tally picks, and do **not** run Fisher on raw votes.

## Idea-level results — the only valid arm comparison on record

12 ideas per arm, 2 rounds pooled, exact Mann-Whitney U
(`.forge/RUN_2026-07-27.md:608-612`). Positive = handbook ahead. MAS is the
promoted handbook.

| handbook | avoids_crowded | challenges_assumption | groundbreaking |
|---|---|---|---|
| MAS | +0.08 (p=0.631) | +0.08 (p=0.129) | +0.17 (p=0.210) |
| mech interp | +0.08 (p=0.544) | +0.04 (p=0.692) | +0.08 (p=0.572) |
| comp ling v1 | −0.21 (p=0.091) | +0.10 (p=0.381) | −0.29 (p=0.144) |

Nothing is significant. Note in particular that **mech interp's margins are
all POSITIVE** — it was written up as a loss on the retracted units.

## What survives

1. **`challenges_assumption` is the one candidate effect.** Positive in
   **all four** handbooks (+0.08, +0.04, +0.10, +0.15; 4/4 on sign),
   pooled **p=0.063**. Not significant, and must never be reported as
   such — but it is the one hypothesis worth powering properly.

   **It is credited to the SUBSTRATE, not the lens** — verbatim,
   `.forge/RUN_2026-07-27.md:643-644`: "consistent with the qualitative
   read all along: the substrate makes the consumer interrogate the
   field's premises." Any proposal that cuts substrate *in order to*
   raise assumption-challenging has the causal arrow backwards.

2. **Power comes from ROUNDS, not from checkers and not from k**
   (`:647-652`). At 2 rounds × 12 ideas the design cannot detect a +0.09
   effect. Testing `challenges_assumption` properly needs **~8-10 rounds
   per arm**, 4 checkers each — 4-5× the ideation cost, and no extra
   checker cost. **Do not spend on another 2-round gate; it cannot answer
   the question.** A run that added 16 checkers over existing pools cost
   ~4.4M tokens and could not, even in principle, move a pick result
   (`:704-709`) — the record calls that the wrong call, in its own words.

3. **Added density backfires — still the best-supported design rule.**
   Two search-resistant rebalances of the interp handbook, one dense prose
   and one a 3-question form, both lost. **Experiment #81**
   (`.forge/kn-p6/interp-rebalance2/VERDICT.md`, 2026-07-12) is the one
   that matters most for future proposals: it added the search-resistant
   signal as **3 sharp open questions** — reversal-history, negative-space,
   taste — and its verdict is "**do not add search-resistant content, in
   any form**", with the mechanism named as **"anchoring bites at minimal
   dose, not just at high density."** Net line count is not the mechanism;
   new anchorable framings are.

   Strength caveat, added honestly: #81's 0:4 is a *pick* margin, so it is
   retracted as a significance claim like everything else. It stands as a
   directional prior plus a mechanism, not as proof. It is still enough to
   refuse to re-run the same manipulation without new reasoning — and note
   that a 2026-08 grounded design pass proposed exactly this manipulation
   again, not knowing #81 existed, because this file did not carry it.

4. **Process base rates (unaffected by the retraction).** These are
   single-arm counts, not arm comparisons, so the unit problem does not
   touch them.

   - **Unchecked lanes are not neutral — 11/11 came back occupied.** Both
     bundles shipped lanes flagged "plausibly occupied, not
     saturation-checked this pass"; two later dated sweeps found all 11
     occupied, most with a dedicated survey, workshop series or shared
     task. Small n, one forge — directional. → P3: default an unchecked
     lane to OCCUPIED; closing it is a pre-ship work item.
   - **Fetch-time paraphrase is the dominant citation-defect source —
     2/106, and 100% of defects.** Every quote defect P4 caught came from
     the summarizing fetch layer, not the writer: one contraction silently
     inserted ("We've been" for "We have been"), and two quotes cut
     through inline LaTeX in an arXiv abstract. Both invisible to reading;
     only the mechanical check found them. → P2: a summarizing fetch is a
     lead; shipped quotes come from the raw extractor.

## Promotion status (the dangling re-gate, resolved)

`.forge/RUN_2026-07-27.md:663-672` closes the re-gate this file used to
leave open:

- **MAS: keep promoted.** Margins positive on every criterion, replicated
  across two independent harnesses. Supporting evidence, not proof —
  nothing argues for removing it. Do **not** cite the old round-1 3:1 /
  13:7 figures as the justification; they did not replicate and their unit
  is retracted.
- **comp ling and mech interp: leave staged.** No demonstrated benefit —
  but equally **no demonstrated harm**. Their earlier "loss" write-ups
  were wrong.

## Decisions whose evidence is now weaker than their wording

Recorded so nobody re-derives them as settled. Each was taken on a
retracted unit, and each **stands by default** — there is no evidence to
reverse them either, and reversing on retracted evidence would repeat the
mistake.

- **Keep the do-not-redo repeller.** The WITH/WITHOUT ablation
  (`.forge/RUN_2026-07-27.md:361-388`) is a 0:4 pick result and a
  one-vote criterion gap (18 v 17), i.e. retracted and below instrument
  resolution. Keep it, but do not tune it, and do not cite it as measured.
- **`avoids_crowded` is domain-dependent**, not a universal effect
  (comp-ling negative, mech-interp positive, each replicated within its
  domain). Do not tune the repeller on one domain's number.
- **No depth annexes.** Grounded partly on an n=5 directional run, partly
  on the two rebalances above. The rule survives on the mechanism
  (anchoring) more than on any single number.

## Caveats that still apply

- The panel is a Fable-5 checker panel, **not** the human novelty verdict
  P6 requires. That verdict remains the certifier and remains open.
- Same-model-family checkers share blind spots. Inter-checker agreement
  (0.79-1.00 on these runs) measures consistency, not correctness.
- Six verdicts shipped on this panel before the retraction. Treat every
  design rule traceable to them as directional.
