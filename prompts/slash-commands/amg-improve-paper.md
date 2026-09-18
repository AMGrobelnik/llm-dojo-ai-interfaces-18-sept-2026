---
description: Paragraph-by-paragraph best-paper-style improvement of an academic paper. Ultrathinks each paragraph, preserves structural conventions, runs compile checks.
---

**Goal:** Improve an academic paper one paragraph at a time, applying NeurIPS-best-paper-style polish (precise verbs, dense citations, claim → mechanism → evidence flow, single-job sentences). Preserve every existing structural convention exactly: section names, bolded paragraph labels, table layouts, figure placement.

## Discovery (do this once, before any editing)

State what you found in 3–5 lines before proceeding to the audit.

1. **The paper source.** LaTeX (`.tex`), Markdown, or whatever the working format is. Read it end-to-end. For very long papers, read by section, but read every section before editing any.
2. **Any structure spec.** Look for `structure*.txt`, `outline.md`, `paper-plan.md`, etc. in the project root, `docs/`, or a `paper/` adjacent folder. If one exists, the section/subsection/paragraph names should match it — flag any drift.
3. **Resource folders.** `references/`, `resources/`, `notes/`, `related_work.md`, `learnings.md`, `eval_benchmarks.md`, etc. These usually hold the citation pool, prior-work summaries, benchmark notes, and design rationale you'll draw on.
4. **Page or word budget.** Conferences cap body length (NeurIPS = 9 pages excluding refs, ICML = 8, ACL = 8). Find the cap. Check current state: where does the body actually end, and where do References start?
5. **Project-specific style constraints.** Check the conversation history, `STYLE.md`, or `CLAUDE.md` for: em-dash policy in body prose, British vs US spelling, system-name macros (e.g., `\sysname`), citation style (numeric vs author-year), and any banned/required vocabulary.

## Structural audit

Extract the section hierarchy:

```bash
# LaTeX
grep -nE '^(\\section|\\subsection|\\paragraph)\{' paper.tex
# Markdown
grep -nE '^(#{1,4}\s|^\*\*[A-Z][^*]+\.\*\*)' paper.md
```

Compare against the structure spec. Note:

- **Bolded paragraph labels are load-bearing.** A `\paragraph{Bold name.}` (LaTeX) or `**Bold name.**` (Markdown) doubles as the beat name a reviewer scans for and the rhetorical contract the prose underneath honors. Never drop, rename, or merge these without explicit user approval.
- **Single unnamed paragraphs are sometimes deliberate** (lead paragraphs after a `\section`, single-paragraph subsections, or chosen-by-the-author single beats). Don't add labels to these without checking.
- **Table and figure references** stay. If a paragraph cites `Table~\ref{tab:X}` or `Figure~\ref{fig:Y}`, that reference must survive your edit.

## The per-paragraph loop (the main workflow)

Work through the paper top to bottom. **One paragraph per edit; never batch.** This is the whole point — batching loses focus, batched edits are harder for the user to veto cleanly, and one-at-a-time forces real ultrathink per paragraph.

For each paragraph:

### 1. Ultrathink (state the plan in 2–4 lines)

Specifically check:

- **Citations.** Every empirical claim, prior-work contrast, and named-system reference needs a `\citep{...}` (or equivalent). Look for unsupported claims like "prior studies showed X", "the field's converged-on Y", "as observed by Z" — each needs a cite. Forward pointers (§X) tie design to evaluation.
- **Filler words.** "Actually", "essentially", "basically", "the X is the Y which is the Z" preambles — strip.
- **Run-on sentences.** Best-paper sentences have one job. If a sentence is doing 3, split it.
- **Anthropomorphism.** "The benchmark asks the system to..." → "tasks the system with...". "The judge thinks..." → "votes...".
- **Code-like punctuation in prose.** `+` between concepts → "and"; `/` between names → ", and"; `→` between phases → write the phase out.
- **Subjunctive evasions.** "would constitute" → "constitute". "may help" → "helps" (if you have evidence) or drop entirely.
- **Redundant bridges.** "We accordingly", "Therefore", "As a result" — usually the prose flow already implies this.
- **Internal-system jargon.** Capitalised proper-noun-ish internal names ("Concept Knowledge-Graph sub-pipeline", "BaseArtifact") read as branding. Lowercase or rephrase: "knowledge-graph sub-pipeline".
- **Project-specific style.** Apply the constraints you found in Discovery #5.

### 2. Apply ONE focused edit

Use the edit tool to change exactly the paragraph you just analyzed. Don't preview neighbouring paragraphs. Don't speculate about edits four paragraphs ahead.

### 3. Preserve structure

- The `\paragraph{Bold name.}` label stays exactly as it was, even if the prose underneath is rewritten end-to-end.
- Subsection/section names stay.
- Table and figure references stay.
- Citation keys stay (only add new ones from the existing bib; don't invent keys).

### 4. Move to the next paragraph

Repeat. Don't loop back to a paragraph you've already done unless the user asks.

## Best-paper-style targets

Patterns NeurIPS/ICML best-paper papers consistently use:

- **Direct opening of result paragraphs.** "Across all manuscripts and reviewers, the average score lands at X" beats "The headline number is the average score across all manuscripts and reviewers, which lands at X". Skip "the headline number is" / "the result is" preambles — just state the result.
- **Bold opening sentence when finding is striking.** `\textbf{6 of 8 LLM judges fail self-consistency screening.}` Use sparingly — bold only the most counterintuitive findings, not every result.
- **Cite-per-component for composition arguments.** If a paragraph claims "each component is individually traceable to prior work" or similar, every component listed needs an inline citation backing the traceability.
- **Forward pointers tie design to evaluation.** When introducing a design choice (e.g., §3.2 fan-out across seeded/unseeded variants), point to the evaluation that exercises it (§4.1 cautionary tale). And vice versa.
- **Prior-work contrasts use specific framings.** "in contrast to X", "extending Y with Z", "addressing the W observed by [refs]", "versus single-shape pipelines [refs]". Generic "unlike prior work" is weak; name the specific prior pattern.
- **Numbers > qualifiers.** `$\sim$374 papers $\times$ 1{,}481 concepts` beats "many papers and concepts". `85\%/15\%` threshold beats "permissive threshold". `$+0.5$, Mann--Whitney $p\!=\!0.055$` beats "moderately significant".
- **Active verbs.** "tasks the system with producing X" > "asks for X". "fires" > "is hit". "yields" > "produces".

## Compile-check cadence

Run the build chain every 5–10 paragraph edits or after any edit that adds/removes ~50+ words.

LaTeX (NeurIPS / ICML / ACL):

```bash
pdflatex -interaction=nonstopmode -halt-on-error paper.tex
bibtex paper                      # if bibliography changed
pdflatex -interaction=nonstopmode paper.tex
pdflatex -interaction=nonstopmode paper.tex   # second pass for cross-refs
```

Verify:

- **0 LaTeX warnings.** Grep `^LaTeX Warning:` in `paper.log`. Benign "Label(s) may have changed. Rerun" disappears after the second pass.
- **Page count holds within budget.** `pdftotext -layout paper.pdf - | awk 'BEGIN{c=1}/\f/{c++; next}/^References$/{print c; exit}'` tells you which page References starts on.
- **References page unchanged or earlier.** Never later than before your edits.

Compensate overflow by tightening adjacent paragraphs, never by `\textfloatsep` shrinkage, font hacks, or margin tricks (most conference style files flag those).

## Final pass

After the last paragraph:

1. **Bold-label audit.** Re-extract the `\paragraph{}` list and confirm every paragraph that should have a bolded label per the structure spec still has the right one. None added that shouldn't be there; none missing that should be.
2. **Style hygiene.** Grep for the project's banned constructions (em dashes in body, US-spelling drift, deprecated macro names, etc.).
3. **Citation density.** Spot-check that no paragraph has more than one unsupported claim.
4. **Final compile.** `pdflatex` × 2 + `bibtex` + `pdflatex` × 2. Confirm the final PDF is stable.

## Summarize

Report what changed paragraph-by-paragraph, grouped by section, in under ~250 words. Mention page-count delta (e.g. "Discussion moved from page 9 to page 8 — body has more breathing room"). Flag any open issues you noticed but didn't fix.

## Hard rules

- **One paragraph per edit.** Never batch.
- **Never drop or rename a `\paragraph{Bold name.}` label** without explicit user approval.
- **Never change existing citation keys** (only add new ones from the existing bib).
- **Don't introduce new sections, subsections, tables, or figures** without asking.
- **Don't add em dashes to body prose** unless the project explicitly allows them.
- **If a paragraph is already best-paper quality, say so and move on** — don't edit for the sake of editing.
- **Never push References to a later page than it was before.** If your edit overflows, trim adjacent paragraphs to compensate; if you can't, revert and ask.
