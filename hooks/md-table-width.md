<!-- hook: md-table-width -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# Markdown table rows added by a commit stay under 70 characters

House rule (global CLAUDE.md #9): tables wider than ~70 chars wrap or
scroll in every terminal and diff view, which defeats a table's point.
This checks table rows (lines starting `|`) ADDED by the staged diff.

**The exclusion is vendored code, not the whole `.claude` tree (narrowed
2026-08-26).** It used to read `:!.claude/**`, which exempted the rules corpus
— 409 markdown files the owner reads to approve rules — from the house rule
those rules are written under. Measured before narrowing: 10 wide rows across
those 409 files, so the corpus was already all but compliant; five were mine
from one session and went unnoticed precisely because the gate could not see
them.

What stays excluded is code this repo does not own or does not hand-write:
`anthropic-*` skills, `archive/`, `plugins/`, the auto-generated
`aii-handbook-*` SOURCES files, and `.agents/`. Measured: 92 wide rows in the
vendored set and 487 in the generated handbooks — neither is ours to reflow.

This is a commit-mode grep over ADDED lines, so the three remaining pre-existing
rows in `rule-gitignore-tells-truth` do not block anything; they each carry a
path plus its explanation and cannot reach 70 without dropping one of the two.

Fix when blocked: split columns across two tables, abbreviate headers, or
move prose out of cells into the surrounding text.

Delete-check: could be deleted by dropping the house rule — an owner call;
until then this closes the gap between stating it and following it.

Scope tightened (2026-08-22): of the 761 whole-tree hits, ~650 were
agent-consumed reference tables (.claude/skills handbooks' SOURCES/
catalog tables carrying URLs — structurally unwrappable without mangling
the data) and vendored .agents docs. The 70-char rule is for docs HUMANS
read in terminals, so those trees are excluded. Human-doc residual: 110
lines (README.md 53, e2e/JOURNEYS.md 30, aii_public/README.md 12,
CLAUDE.md 7, misc 8). Rewrapping them is editorial work on owner-facing
docs — restructuring flag/command tables changes how they read — so the
rule stays added-lines until the owner wants that pass; the residual is
small enough to work through in one sitting.

Near-miss files cleared 2026-08-22 (7 lines, all overflowing by <=13
chars — cell-text trims, not restructures): FREE_TIER_SOURCES.md,
BENCHMARK.md, CUTOVER_RUNBOOK.md. Residual **105** lines, measured by
width 2026-08-24: 15 at 71-89, 28 at 90-119, 30 at 120-199, and 32 at
200+. (This said 106 while its own four buckets summed to 105; re-measured
independently at 105 the same day, so the buckets were right and the total
was not.)

**"None is mechanically fixable" was wrong, and five of them have now been
fixed.** Residual is **100**: 10 at 71-89, 28 at 90-119, 30 at 120-199, 32
at 200+ — the whole reduction came out of the narrowest bucket. The five
were the same shape as the 2026-08-22 near-misses this paragraph already
records as legitimate: a cell whose text shortens without losing anything,
never a restructure.

    Cursor-polled run-event stream (…)  ->  Cursor-polled (…)
    Python dead-code (allowlist in X)   ->  Python dead-code (see X)

So the honest line is not "none" but "some of the narrow tail was pure
redundancy". What remains genuinely resists a trim: 90 of the 100 overflow
by 20+ characters, and a third of them by 130+, which is prose living in a
cell rather than a long word — those need the column split or the move-to-
prose that makes this an editorial pass, still an owner call.

The 10 still in the 71-89 bucket were each looked at and left, so nobody
repeats the search: they overflow by 13-19 and every one needs a decision
about what INFORMATION to drop, not which words to shorten. Two examples
that make the boundary concrete —
`| \`ModuleNotFoundError: aii_lib\` | \`uv pip install -e "aii_lib[…]"\` |`
is two literal code cells, where trimming falsifies the command; and
`aii_config/pipeline/harness/execute_env.yaml` is a 46-character path whose
row cannot fit however terse the other cell gets. That is the same editorial
call as the wide ones, just cheaper, and it is not made here.

Also worth knowing before measuring this again: the pattern anchors `^\|`,
so a table INDENTED under a list item never matches. Three such rows in
CLAUDE.md were trimmed alongside the five, and they were never in scope —
counting them as residual overstates it. There are 0 indented wide rows
left, so the two measurements agree at 100 today, but they will diverge
again the moment someone indents a table.

Re-measured 2026-08-24 by TABLE rather than by row, which is the unit that
actually decides this: the 105 rows sit in **15 tables** across 5 files
(README.md 8, JOURNEYS.md 2, aii_public/README.md 2, watchers/README.md 2,
CLAUDE.md 1). Every one of the 15 has at least one row over 90 characters
— widest 421 in JOURNEYS.md, 381 in CLAUDE.md — so not a single table can
be brought under the limit by trimming alone. A table is all-or-nothing;
fixing its narrow rows leaves it non-compliant. That is why the count of
"trimmable" rows is not an actionable subset: 0 of 15 tables are. The 90+ rows are many-column tables that
CANNOT be rewrapped — a markdown table row has no legal line break — so
they need restructuring into narrower tables or prose. The 71-89 band
looks trimmable and is not: unlike the data tables cleared above (run
labels, benchmark timings, where "2 (concurrent)" -> "2 conc" lost
nothing), these are descriptive cells in README.md and aii_public/
README.md where the text IS the content — "Pipeline runner — 4 phases
under `src/aii_pipeline/steps/`" cannot lose 14 characters without
losing the path or the phase count.
So this is an owner decision with two honest options, not a backlog to
grind: restructure those tables, or scope the 70-char rule to prose
docs and exempt reference tables the way it already exempts
.claude/skills and .agents.

Residual stays **100**, and an attempt to reduce it found a RULE CONFLICT
worth more than the two lines it would have saved.

Splitting the hits by whether they sit in a real table:

| kind | n |
|---|---|
| genuine body rows | 96 |
| header rows | 2 |
| padded separators | 2 |

The two separators (`| ------- | ------- |`, 139 and 421 chars in
`JOURNEYS.md`) looked like free wins — a separator carries no information and
`|---|---|` renders identically. **It is not available.** `oxfmt` formats
markdown and PADS separators to align columns, so normalising them fails
`rule-oxfmt-fe`, and running `oxfmt` restores the 139/421 lines byte for byte.

So on `aii_frontend/**/*.md` the two enforced rules disagree: this one counts a
padded separator as a violation, `rule-oxfmt-fe` requires the padding. Neither
is wrong on its own and no waiver resolves it, because only ONE rule is
waivable per commit and the file cannot satisfy both. That is an owner
decision — exempt frontend markdown from the width rule, drop `.md` from
oxfmt's scope, or accept the standoff — and it is stated rather than taken.

**No wrapped prose is in scope.** A line of hard-wrapped prose whose wrap point
lands a `|` at column 0 matches this pattern and is NOT a table row; the
examples live in the flattened instance blob near the end of
`rules-pending/general/meta-rules/rule-site-carries-companion/SKILL.md`.
It never fires because `:!.claude/**` excludes it. Checked the in-scope set for
the same shape and found none, so the residual is 100 table lines and not 100
"lines starting with a pipe".

Beware the cheap way of testing that. Classifying a row by looking a few lines
up for a `|---|` separator misreports every row past the window in a long table
— it called 37 of the 100 "prose", including `README.md` rows 22-26, whose
separator is at line 15. Walk the contiguous run of pipe-leading lines instead.

### The oxfmt conflict is STRUCTURAL, and it is bounded

Driven with a throwaway probe rather than reasoned about. `oxfmt` pads a
separator to the width of the widest CELL in its table:

    before            after
    |---|---|   ->    | ----- | ----- |          (narrow table, 9 -> 17)
    |---|---|   ->    | ------ … ------ |        (79-char row, 9 -> 81)

So any markdown table under `aii_frontend/` carrying a row over ~70 characters
automatically gets a separator over 70 as well. The formatter turns ONE wide
row into TWO width violations, and the second one is not something an author
wrote or can remove.

Measured scope today, which is the reassuring half:

| population | n |
|---|---|
| in-scope `*.md` | 19 |
| of those under `aii_frontend/` | 4 |
| padded separators over 70, tree-wide | 2 |

Both are in `JOURNEYS.md`. The other three frontend docs are unaffected only
because their tables are narrow — not because the interaction does not apply
to them. Add one wide table to any of them and it recurs.

That is what makes this an owner decision rather than a cleanup: the
`JOURNEYS.md` pair can never be fixed in place, and the count grows with any
future wide frontend table. Excluding separator lines from this rule's pattern
would resolve it in one edit and lose nothing measurable — a separator carries
no content — but that is a change to an enforced rule and is not made here.

CITATION DE-PINNED 2026-08-25. This used to say "one exists at …
`SKILL.md:72`". Both halves had drifted: `1c53bc025` reflowed that instance blob
earlier the same day, so the example is no longer at line 72, and there are now
**two** such lines rather than one (the blob's wrap now lands a `|` at column 0
twice). The phenomenon is unchanged and still there — only the coordinates moved,
which is why the paragraph's conclusion needed no revision.

The line number is deliberately NOT replaced with the new one. A citation into a
`rules-pending/` SKILL.md points at a document that is edited constantly, by
design, so pinning a line there guarantees the same drift again; naming the file
and the shape locates it and survives the next reflow. Line cites into package
source are a different matter and stay — that code does not churn this way, and
an audit of all six `file:line` citations in the enforced tree found the other
five exact.

RE-MEASURED 2026-08-25 — the residual has FALLEN, and this rule's own
prediction about indentation has come true.

| quantity | recorded | today |
|---|---|---|
| wide rows | 100 | **82** |
| wide tables | 15 | **13** |
| files | 5 | **4** |

By width band, against the four buckets recorded above:

| band | recorded | today |
|---|---|---|
| 71-89 | 10 | 8 |
| 90-119 | 28 | 22 |
| 120-199 | 30 | 27 |
| 200+ | 32 | 25 |

**CLAUDE.md is now fully clear** — 0 wide rows, widest table row 58
characters — which is why the file count went 5 to 4. It is NOT the whole of
the 18-row drop, and the arithmetic is worth stating because the tempting
version is wrong: CLAUDE.md contributed 7 and README.md 11.

| file | at `2a620a836^` | today |
|---|---|---|
| README.md | 48 | 37 |
| JOURNEYS.md | 30 | 30 |
| aii_public/README.md | 12 | 12 |
| watchers/README.md | 3 | 3 |
| CLAUDE.md | 7 | **0** |

That before-column sums to exactly 100, which independently confirms the
residual this body recorded. Three commits did it — `2a620a836` (the launcher
table), `ae82f56da` and `544dd626e` (the README flags table, then its last
misused cell) — all by the same method: moving prose out of cells into the
surrounding text, the remedy this rule's own "Fix when blocked" line names.

So the editorial pass is not hypothetical; one file has had it completely and
another partially. That also softens a claim this body makes. It argued no
table can be brought under the limit by trimming — "0 of 15 tables are"
actionable — and that stays true of what is LEFT. But a table can be brought
under by RESTRUCTURING, and several were.

**The indented-table divergence has arrived, exactly as predicted.** This body
warned that the `^\|` anchor misses a table indented under a list item, that
there were 0 such rows, and that "they will diverge again the moment someone
indents a table". There are now **2**, both in CLAUDE.md under a list item
(the keepalive alarm table). They are out of scope, correctly, and they are why
a whole-tree count of "wide rows in markdown" would read 84 rather than 82.
Quote which measurement you mean.

RESIDUAL 79 (2026-08-25, later the same evening) — one more file cleared, by
the method this rule names rather than by trimming.

| quantity | earlier tonight | now |
|---|---|---|
| wide rows | 82 | **79** |
| wide tables | 13 | **11** |
| files | 4 | **3** |

`scripts/local/watchers/README.md` is now clear. Its three rows were two
three-column tables whose last column held a sentence — the shape this body
calls "prose living in a cell". Both became two-column tables with the sentence
moved directly beneath, which is exactly the "move prose out of cells into the
surrounding text" remedy the Fix line names, and the same edit that cleared
CLAUDE.md earlier.

Bands: 8 / 22 / 24 / 25, summing to 79. Only the 120-199 band moved, by two,
which is where those rows sat.

That leaves `README.md` (37), `JOURNEYS.md` (30) and `aii_public/README.md`
(12). The argument for stopping here is unchanged and worth restating: those
are 90+-character many-column tables where the text IS the content, so they need
restructuring decisions about what information to drop, not a cheaper edit. What
the watchers file shows is that when a table's last column is one sentence, the
fix is mechanical and costs nothing — so the remaining 79 are genuinely the hard
ones rather than an unstarted pile.

### THE OXFMT CONFLICT IS A SYMPTOM, NOT A BLOCKER (probed 2026-08-25)

This body calls the `JOURNEYS.md` pair unfixable in place and treats that as
what makes the file an owner decision "rather than a cleanup". The first half is
true only of the separator ON ITS OWN. Probed with two throwaway tables run
through the real `oxfmt`:

| table | separator after oxfmt |
|---|---|
| all rows narrow | **20 chars** |
| one row wide | **90 chars** |

So the padding tracks the widest cell in both directions. Narrow every body row
and `oxfmt` re-pads the separator NARROW — both rules are then satisfied, and
nothing about the interaction prevents it. What cannot be done is fixing the
separator while a wide row remains, which is a different statement.

`JOURNEYS.md` is therefore not blocked by a rule conflict. It is blocked by the
same thing as `README.md` and `aii_public/README.md`: restructuring many-column
tables is editorial work on a document someone owns. That is still a decision,
and the effort is real — 28 body rows across two tables. But it should be
weighed as editing, not declined as impossible, and this rule previously
invited the second reading.

Worth knowing before repeating the probe: `oxfmt` DOES process
`aii_frontend/tests/e2e/JOURNEYS.md` and reports it correctly formatted today.
The current wide separators are what the formatter wants given the current wide
rows — they are not drift.

RE-MEASURED 2026-08-26 — the residual has fallen again, and the shape of
what is left has changed qualitatively.

| quantity | 08-24 | 08-25 | 08-26 |
|---|---|---|---|
| wide rows | 100 | 82 | **33** |
| wide tables | 15 | 13 | **4** |
| files | 5 | 4 | **2** |

Per file, against the 08-25 column this body records:

| file | 08-25 | 08-26 |
|---|---|---|
| README.md | 37 | **10** |
| JOURNEYS.md | 30 | **23** |
| aii_public/README.md | 12 | **0** |
| watchers/README.md | 3 | **0** |

Two more files are now fully clear, joining CLAUDE.md. But the interesting
half is the band distribution, which did NOT fall evenly:

| band | 08-25 | 08-26 |
|---|---|---|
| 71-89 | 8 | **0** |
| 90-119 | 22 | **4** |
| 120-199 | 27 | **5** |
| 200+ | 25 | **24** |

The three narrower bands collapsed by 48 rows between them; the 200+ band
moved by one. So 24 of the 33 rows that remain are past 200 characters, and
23 of the 33 sit in `JOURNEYS.md`. That is the honest picture of the tail:
the rows an editorial pass can reach have largely been reached, and what is
left is the genuinely wide many-column stock this body already argued has to
be RESTRUCTURED rather than trimmed. It is still editorial work on a document
someone owns, and still a decision rather than a defect.

The indented-table divergence is unchanged at **2** rows, both still invisible
to the `^\|` anchor.

RE-MEASURED 2026-08-28 — and the H1 now reads "added by a commit", which is
what `rules-grep` without `--tree` has enforced all along: added lines block
at commit, the all-mode sweep is advisory. Two populations, quoted separately
because this body's residual series only ever tracked the first:

| population | rows |
|---|---|
| human-doc residual | 32 |
| whole command scope | 416 |

The human-doc residual is README.md 9 (was 10) and JOURNEYS.md 23. The other
384 in-scope rows sit in first-party skill docs that the 2026-08-26 narrowing
brought into the command's scope but the residual series never counted:
amg-frontend-testing 218 (SKILL.md plus references/), aii-data-fig-gen 73,
seo-geo 48, and a tail across other skills — plus the 3 in
rule-gitignore-tells-truth this body already records. None of it blocks
anything: the rule is added-lines, and the sweep is advisory.

PORTED 2026-09-14 onto the one-pass AST dispatcher (`general-ast-checks`,
`dispatch.py`), off the standalone `amg-hooks-grep` command this file's history
above was written against. The `^\|.{70,}` ERE survives unchanged as the
candidate PREFILTER; an `mdast` (markdown-it-py) pass behind it drops a
candidate line unless it is a row (header, delimiter or body) of a real GFM
pipe table — the drop is proven rather than guessed, because `mdast` only
ever finds a table inside the token kind markdown-it-py builds for prose,
never for a fenced or indented code block, so "is this line one of the
table's rows" already implies "outside any code block" by construction. The
false-positive shape this removes is exactly the one this file's own history
names above: "a line of hard-wrapped prose whose wrap point lands a `|` at
column 0 matches this pattern and is NOT a table row" — a synthetic
reproduction of that shape is a candidate under the live ERE and is dropped
by the port, proven in `test_md_table_width_bites.py`.

Measured against the research-monorepo consumer tree (whole-index/sweep lane, this
hook's live PATHSPEC): **0 candidates, 0 findings** — the tree's own residual
under this pathspec is already clear, so this measurement records DROPPED 0 /
ADDED 0 rather than a nonzero reduction. Findings are a subset of candidates
by construction regardless; the fixture-level proof lives in the test file.
