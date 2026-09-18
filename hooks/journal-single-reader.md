<!-- hook: journal-single-reader -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# `operation_outputs` is read only inside aii_lib/run/events/, plus three named readers on the cleanup backlog

`events/query.py` declares itself the single home of the journal SQL and
decoder. Every direct reader elsewhere re-implements fork-chain stitching
and pickle decoding, and every one breaks when the journal read path moves
(which is decision D1).

Re-measured 2026-08-24 with THIS rule's own pattern: 8 first-party Python
files reference the journal table in a SQL or schema shape. Five are inside
`aii_lib/run/events/` — the sanctioned home. The other three are the named
exclusions in the command above (`_cli/_dispatch/_resume.py`,
`dashboard/services/runs_sidebar.py`, `dashboard/services/zombie_reaper.py`),
and THOSE THREE are the whole cleanup backlog. Nothing unsanctioned remains.

**The `dbos_app/` exclusion is gone (2026-08-28), because the home it
sanctioned was empty.** Re-measured with the pattern above: of the 8 matching
files, five are in `run/events/` and three are the named exclusions. Zero
were under `dbos_app/` — on disk as well as in `HEAD` — whose only mention of
the table is a comment beside the `SystemSchema` re-export in `internals.py`.
That made the exclusion a standing opening rather than a sanction of existing
code: `dbos_app` re-exports the very `SystemSchema` handle the pattern looks
for, so a reader added there would have been excluded from a whole-tree check
by a path rule written when nothing needed it. Dropping it was verified a
no-op first — the command runs green without it — and the H1 was narrowed in
the same edit: "read", not "touched", since the pattern matches SQL/schema
ACCESS shapes, not mentions.

This paragraph previously reported 23 and then, two lines later, 24 — two
numbers for one population, neither reproducible today. They came from a
looser query (any mention of `operation_outputs`, which still matches 33
first-party files, most of them comments and tests) rather than from the
SQL-shape pattern the rule actually enforces. A count in a rule body is only
meaningful with the query that produced it, so the query is now stated:
re-run the `command:` above to reproduce these figures.

This checks the WHOLE TRACKED TREE at every commit, not added lines. That
sentence used to read "At commit this checks ADDED lines only", which was
true until the `--tree` flip recorded two paragraphs below and false from
that moment on — the flip is why the stock had to reach zero first.
`rules-grep`'s own header states the semantics: `--tree` "greps the whole
tracked tree and BLOCKS in BOTH modes."

**Consequence worth knowing before you are puzzled by it: a violation in
a file you never touched can block your commit.** `--tree` runs a bare
`git grep`, which reads the WORKING TREE, not `HEAD` and not the index —
so an UNCOMMITTED edit by anyone sharing this checkout counts. Measured
2026-08-24: `aii_server/dashboard/services/run_cost.py` matched in the
working tree, did not match in `HEAD`, and did not match under
`git grep --cached`; it blocked an unrelated markdown-only commit until
its author finished.

That is the intended trade, not a defect — a whole-tree invariant is
worth more than a per-diff one, and this repo runs several agents in one
checkout on purpose. But diagnose it correctly: check whether the
offending line is even yours (`git diff --name-only` and
`git show HEAD:<file>`) before trying to fix it, and if it is someone
else's work in flight, wait rather than edit their file.

Fix when blocked: go through `aii_lib.run.events` (query/stitch/
cost_projection) — if the helper you need is missing, add it THERE.

Delete-check: deletable upstream by D1 (a first-party read model makes the
DBOS table private again); until then this stops the count growing.

Sharpened + flipped --tree (2026-08-22): the ERE now matches ACCESS
shapes (SQL FROM/JOIN, SystemSchema attribute, .c column handle), not the
word — the 23 prose mentions stop mattering. The sanctioned readers are
named as excludes and ARE the closed list — at flip that list was
events/ + dbos_app/ (the reader machinery), _cli/_dispatch/_resume.py
(fork surgery), runs_sidebar.py (liveness SQL), zombie_reaper.py; the
dbos_app/ exclude was dropped 2026-08-28 as sanctioning an empty set
(see above), so the live list is events/ plus the three named files.
Measured zero hits at flip; a new journal reader anywhere else blocks,
and joining the sanctioned list means editing this command in the same
commit — visible, reviewed.

## The grep+AST-confirm port (2026-09-14) — written, INERT

`dispatch.py` and `scripts/run_static_check.py` implement this rule on the
one-pass AST dispatcher. Neither is wired: the `run:` line above is still
the raw `amg-hooks-grep`, and the cutover is the merge owner's to make. The line
to swap in is written out at the end of this section, not applied.

The grep survives as a cheap line-level PREFILTER and stays the SOLE
source of candidates; `ast` only FILTERS what it produced. The finding set
is therefore a subset of the candidate set by construction, and the port
can never report a line the live command does not.

### The port is PARTIAL, and one third of it stays textual

The ERE is three alternatives, and they are not the same kind of thing:

| alternative | what it is | confirmed by |
|---|---|---|
| `SystemSchema.operation_outputs` | attribute | an AST node |
| `operation_outputs.c` | attribute | an AST node |
| `FROM\|JOIN dbos.operation_outputs` | SQL text | where it sits |

The first two are real expressions, so the confirmation is the NODE: an
`ast.Attribute` named `operation_outputs` on a `SystemSchema` receiver,
and an `ast.Attribute` named `c` on an `operation_outputs` receiver. Prose
wearing that text — a `#` comment, a docstring, any other string constant
— builds no node at all and is dropped.

The third cannot work that way. SQL inside a Python file is ALWAYS a
string, so there is no node to confirm and an AST rule modelled on the
other two would drop every real query in the tree. It stays TEXTUAL, and
the test is where the text SITS: inside a string constant that is not a
docstring it is a query being issued and stays a finding; in a `#` comment
or a docstring it is prose and is dropped. That asymmetry — a plain string
keeps a SQL read and drops an attribute chain — is the whole design, and
each half has its own positive and its own negative in
`test_journal_single_reader_bites.py`.

### The false-positive class this removes

Prose about the table, which is what this rule's first pattern drowned in
(it matched the WORD `operation_outputs`, pulled in 33 first-party files,
and produced the two irreproducible counts corrected above). Two specimens
sit in the tree today, each ONE CHARACTER from firing under the sharpened
ERE:

- `aii_server/dashboard/apps.py:349` — a `#` comment reading
  ``MAX(operation_outputs.started_at_epoch_ms)``
- `aii_server/dashboard/services/runs_sidebar.py:197` — a docstring
  reading ``operation_outputs.output``

Neither is a read. Either becomes a hit the day somebody writes `.c` where
`.started_at_epoch_ms` or `.output` stands, and the AST step is what makes
that a non-event.

### The drop-set, measured

Against the consumer's INDEX, with the live pathspec:

| set | count |
|---|---|
| OLD — `git grep --cached -nE` | 0 |
| NEW — the port | 0 |
| DROPS | 0 |
| ADDED | 0 |

Zero against zero is a real result and a weak one: the four excludes ARE
the sanctioned homes, so the enforced population is clean by construction
and the two implementations have nothing to disagree about. The filter was
therefore measured a second time over the POSITIVES-ONLY pathspec — the
same ERE with the four `:!` excludes dropped, i.e. the whole first-party
tree, where the reads actually live:

| set | count |
|---|---|
| OLD — positives only | 16 |
| NEW — the port | 15 |
| DROPS | 1 |
| ADDED | **0** |

The single drop is `aii_lib/src/aii_lib/run/events/query.py:326`, which
spells `SELECT … FROM dbos.operation_outputs WHERE …` inside
`iter_run_tree_events`'s docstring — documentation of the scan shape, not
a scan. The surviving 15 are all real reads: the SQL strings in
`events/_query/_sql.py`, `query.py` and `tailer.py`, the two
`SystemSchema.operation_outputs.c` chains in `event_step.py`, the
`pg_insert` in `journal_writer.py`, and the three named backlog readers.
ADDED is 0, which is the property that matters — the AST step only ever
removes.

### The false negative the port KEEPS, deliberately

An aliased import — `from dbos import SystemSchema as S`, then
`S.operation_outputs` — is a read this hook misses. It is a false negative
the regex already has (no `SystemSchema.` text, so no candidate line) and
the port keeps it, because the subset property forbids the filter from
inventing a finding the prefilter did not produce. Same for a receiver
reached through a call or a subscript (`schema_for(db).operation_outputs`).
Closing either means widening the ERE first, and paying for whatever that
widening admits; it is future work, not a defect of the port.

### The cutover line, for the merge owner

Replace this hook's `run:` value with:

    {amg_hooks}/lib/amg_hooks/amg-hooks-env {amg_hooks}/research-monorepo/hooks/journal-single-reader commit -- .venv/bin/python {amg_hooks}/research-monorepo/hooks/journal-single-reader/scripts/run_static_check.py

Three things stay absent from that line, each on purpose. No `glob:` — the
entry is ungated today and the port's `GLOBS = ["*"]` reproduces exactly
that. No `{staged_files}` — the check is TREE-scope and judges the whole
index regardless, and lefthook CHUNKS a long staged-file list, which would
run the whole-index scan once per chunk. No `snapshot.py exec` wrapper —
every read goes through `gitio` to the INDEX and never opens a file on
disk, so there is no working tree to snapshot. That last one also retires
the hazard recorded above: an index-only read cannot be moved by a peer's
unstaged edit, which is what blocked an unrelated markdown-only commit on
2026-08-24.
