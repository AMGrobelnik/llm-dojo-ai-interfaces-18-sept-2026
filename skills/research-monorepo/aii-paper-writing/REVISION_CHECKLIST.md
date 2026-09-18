# Final revision checklist

Run this **after the draft is finished**, as a separate pass, before the paper
is handed on. It is not a writing guide — the rest of `SKILL.md` is that. It is
the list of defects that survive a first draft *because* the author wrote it:
each one is invisible from the inside and obvious to the first outside reader.

**How to run it.** Re-read the whole draft once as an editor who did not write
it. Then take the items below one at a time, against the full text — not from
memory of what you intended. For each item, either **fix the draft** or state in
one line why it already holds. A pass that produces no edits is a pass that was
not really run: assume at least a few of these apply to any first draft.

---

## 1. Plain, professional language

Write the plainest prose the field accepts. Formality is not complexity — a
top-venue paper reads *simply*; it is the ideas that are hard, not the
sentences.

- Test: could a competent researcher from a neighbouring subfield follow each
  sentence on the first pass, at reading speed?
- Fix: replace ornamental vocabulary with the ordinary word. Unpack stacked
  noun phrases ("gradient-based sample-efficiency degradation analysis").
  Split any sentence carrying more than one claim. Cut throat-clearing
  ("It is important to note that", "In this work, we importantly").
- Every term of art gets a one-clause definition at first use, including the
  names this paper itself invents.

## 2. The abstract is prose, not a results table

An abstract dense with numbers cannot be read — the reader has no axes,
baselines, or units in mind yet, so each number costs them more than it tells
them.

- Test: count the numbers in the abstract. More than about three, and it is a
  data dump.
- Fix: keep only the headline results — the ones that would appear in a
  one-sentence summary of the paper. Move the rest to Results, where they sit
  next to the baseline and the axis that make them mean something.
- The abstract must state, in words: the problem, what was done, what was
  found, and why it matters. A reader who stops after the abstract should be
  able to say all four back.

## 3. One job per section

Sections leak in a first draft because the author writes what they know as they
think of it.

- Test: read the Introduction alone. Does it contain method detail, result
  tables, or a survey of prior work? Those belong to Method, Results, and
  Related Work.
- Test the reverse direction too, which is the half that gets missed: **no
  later section may depend on a definition, formula, symbol, or piece of
  notation that appears only in the Introduction.** If Method needs it, it is
  defined in Method or in Preliminaries; the Introduction may motivate it, not
  own it.
- Fix: move the material to the section whose job it is, and leave a
  forward-reference ("we define this formally in Section 3") if the
  Introduction still needs to gesture at it.

## 4. Conventional section names

Section names are navigation, not titles. A reader scanning the contents must
know what is in each section *without reading it*.

- Test: could this table of contents belong to any paper in the field? If a
  heading names a concept the paper itself invented, it tells the reader
  nothing until they have already read the section.
- Fix: use the names the field uses — Introduction, Related Work,
  Preliminaries, Method, Experiments, Results, Analysis, Discussion,
  Limitations, Conclusion. Put the invented name in the section's first
  sentence, or in a subsection heading underneath the conventional one.
- Legitimate variants exist ("Discussion and Related Work" when related work
  sits at the end). The bar is that the name says what kind of content follows.

## 5. Related work, searched with the *final* vocabulary

By the end of the draft the work has a name, a metric, and a problem statement
that the project did not have when it started. The literature search that was
run at the beginning could not have used any of them.

- Fix: run at least one more search now, using the draft's own final terms —
  the contribution's name, the metric's name, the exact problem statement, and
  the nearest baseline's name. Fetch real BibTeX (see `SKILL.md`) and cite what
  comes back.
- Also check the reference lists of the two or three closest papers already
  cited; the nearest neighbour is very often cited by one of them.
- An uncited close prior work is among the most common reasons a paper is
  rejected, and it is entirely preventable at this point.

## 6. Figure 1 carries the main idea

The first figure is the one every reader looks at, often before reading a word.
It must answer "what is this work?".

- Test: shown only Figure 1 and its caption, could a reader say what the paper
  proposes or studies?
- Fix: Figure 1 shows the system, method, or central concept — not one narrow
  comparison and not a secondary improvement, however strong that result is. If
  the current first figure is a specific result, move it into Results and
  promote (or specify) an overview figure in its place. Its marker belongs near
  the end of the Introduction.
- A correct figure in the wrong slot is still the wrong Figure 1.

## 7. Report the whole study, not only the highlights

If the work covers N of something — metrics, models, datasets, configurations,
seeds — then all N must be visible somewhere the reader can check them.

- Test: state N explicitly, from the artifacts rather than from the draft. Now
  find where all N appear. "We evaluate 53 metrics" followed by a figure
  showing eight is a gap the reader will assume was chosen to flatter.
- Fix: add the complete view — a full figure, or a complete table, in the body
  or an appendix. Highlighting a subset in the main text is good writing;
  showing *only* that subset is not.
- The same applies to negative and null results from the study. They belong in
  the paper.

## 8. No implementation-internal references in the prose

The paper describes the work; the repository holds the implementation. A reader
cannot follow a sentence that names a file they cannot see.

- Test: search the draft for filenames, module paths, function names, class
  names, CLI flags, and variable names from the codebase.
- Fix: state the rule, not the code that implements it. Not "`eligibility.py`
  declares E1 as ..." but "an item is eligible when ...". If the pointer is
  genuinely useful, it goes in a footnote, an artifact link, or an appendix —
  never in a sentence the reader has to parse.
- Mathematical notation and algorithm names are not affected by this; they are
  the paper's own vocabulary, not the implementation's.

## 9. Consistency — several separate passes, one concern each

Inconsistency is the defect a first draft is *guaranteed* to have: the paper was
written in pieces, over time, while the results were still moving. A single
"check it's consistent" sweep finds almost nothing, because each concern needs a
different thing held in mind. Run these as **separate passes over the whole
document**, one per entry below, and repeat any pass that produced an edit — a
fix in one place routinely breaks agreement somewhere else. Each entry names the
pass, what to hold in mind while running it (in brackets), and the failure it
catches.

- **Claim ↔ evidence** (every claim in the text) — a claim with no figure,
  table, or number behind it; or one whose evidence shows something weaker
  than claimed.
- **Evidence ↔ claim** (every figure and table) — a result presented but never
  discussed, and the reverse: something described in the text that is never
  actually shown (see item 7).
- **Numbers** (one value at a time) — the same quantity differing between
  abstract, text, table, figure, and caption.
- **Citations — placement** (each `[n]` in context) — a reference attached to a
  claim it does not support, or supporting a claim it only mentions in
  passing.
- **Citations — integrity** (the bibliography) — cited but not listed; listed
  but never cited; the same work under two entries; a fabricated or
  unverified entry.
- **Terminology** (one term at a time) — the same concept under two names, or
  one name used for two concepts.
- **Notation** (each symbol) — a symbol reused with a second meaning, or used
  before it is defined.
- **Cross-references** (each "Section/Figure/Table N") — a pointer to the wrong
  item, or to one that no longer exists.
- **Section name ↔ content** (each heading, then its section) — a heading that
  no longer describes what ended up under it after material was moved (item 3
  moves material; this pass re-checks the names afterwards).
- **Tense and voice** (section by section) — method in past tense in one place
  and present in another; person switching mid-paper.

For the citation passes specifically: check what each cited work actually says
before trusting its placement. A citation that is real, correctly formatted, and
attached to the wrong sentence is worse than a missing one — it is a factual
error the reader will attribute to carelessness across the whole paper.

---

## Before finishing

Confirm every item above was actually applied to the current text, not to the
version you remember writing. Then emit the final output.
