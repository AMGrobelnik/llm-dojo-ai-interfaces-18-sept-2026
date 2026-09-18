# A prompt template's section tags nest, close, and stand on their own lines

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | file | 1s | active |

## Why

The agent rule was applied 200 times and failed 20, with no recorded evidence
line, and its own delete-check drew the line this conversion follows:
*"judgment ('reads nicely') is the hard part; the tag/blank-line skeleton
could later become an AST+regex cmd check (same rule id)"*.

The skeleton is what a program can hold. A prompt whose `<section>` never
closes, or whose two sections run together with no blank line between them, is
a defect visible in the text; whether the content under a tag belongs there is
not, and stays with the agent.

Filed under `research-monorepo` because the tag convention is this repo's prompt
house style, not a general property of Python.

## Mechanism

`check.py` walks each module's triple-quoted templates with `ast` and runs a
tag stack over them.

| # | clause |
|---|---|
| 1-3 | tags open, close, and nest rather than interleave |
| 4 | a blank line between two adjacent sections |
| 5 | a multi-line block is not spliced mid-sentence |
| 6 | a component call does not share a line with prose |

**Telling source lines from template lines is the whole difficulty**, and
getting it wrong is why a first prototype reported 68 findings on a clean
tree. Each literal is analysed against a projection of the source in which its
own placeholders and every quote delimiter are blanked in place, offsets and
newlines preserved so the reported line numbers stay real. Three measured
reasons: `return f"""{block}` puts the opening delimiter on the same line as
the first placeholder; a formatter joins `}{` with no template text between;
and a nested `f'''...'''` inside a placeholder carries its own tags, so it is
analysed independently instead of corrupting the outer literal.

The judged text is the git INDEX copy, so a peer's unstaged edit cannot fail
this commit.

## Stock

Whole tree, at HEAD: **0 findings**, 0.07-0.08 s over 32 `s_prompt*` /
`u_prompt*` modules holding 137 multi-line templates.

The censuses behind that zero: 218 structural tags, 82 section boundaries, 21
block interpolations, 42 component calls. Injection at real sites scored
**64 of 64** across five mutation shapes. The first sweep read 64 of 68, and
all four misses were injector artifacts — the mutation had merged a
placeholder onto a line made only of other placeholders, which is a shape the
checker allows on purpose. Recorded because "the detector missed it" and "the
injection did not create the defect" look identical from a score.

## Fragility

| refactor | effect and guard |
|---|---|
| the house style drops XML-ish tags | every clause goes quiet |
| prompt modules renamed | no-arg mode exits 2; prefixes in CONFIG |
| the components package moves | identity comes from the import |
| a formatter rewrites templates | clauses 1-4 go quiet; not guarded |
| the file population empties | exit 2 |

**A named gap, left deliberately:** exit 2 fires when the FILE population is
empty, not when the tag population is. Thirty-two prompt modules containing no
tags at all would pass green. A floor — at least one structural tag
across the population, or exit 2 — is the obvious hardening, and it is
not built.

## Residue

Each dropped clause was measured to be a false-positive generator. A
line-level scan for `if`/`for`/`lambda` beside a `{` flags 7 sites, every one
English prose beside LaTeX braces; with an `ast` there is nothing left to
find, because no comprehension appears inside a template interpolation.
"Every interpolation on its own line", read literally, flags 33 scalars
interpolated mid-sentence, which is prose — restricted to component calls, as
the rule's own example has it, the stock is 0. The closing edge of a block
interpolation (`}{`, `}<next>`) is 4 sites of identical rendered output and is
not judged; only the opening edge is.

Multi-line emphasis spans and tag names quoted in prose are excluded by
requiring a structural tag to stand alone on its line. Implicitly
concatenated literals fold into one `Constant` whose source slice is not its
template text, and reading one invented a finding — excluded by requiring a
triple-quote opener.

Whether a section's content belongs under its tag has no closed form and is
what the agent rule keeps.
