<!-- hook: no-lint-silencers -->

| stage | scope | budget | status |
|---|---|---|---|
| pre-commit | tree | 5s | active |

> Migration notes: runs through lib/amg_hooks/amg-hooks-env: PATH:rules-grep
# A lint warning is fixed at the smell — the silencer comment and the allowlist entry are last resorts, not the fix

A standing house directive, restated. It stood in the global CLAUDE.md until
the 2026-09-07 overhaul (1c930309) moved commit-time invariants into this
engine and dropped it from the prose; this rule is where it now lives. The
substance: when hooks warn or error (ruff, ty, dead, knip, oxlint, typos,
shellcheck, gitleaks, …), apply the most common modern best-practice fix to
the actual code smell rather than silencing it with `# noqa`,
`# type: ignore`, a `_typos.toml` or `dead_allowlist.txt` entry, or a hook
exclude. Allowlist entries are a last resort, for genuine false positives
and real domain terms.

What blocks, on lines the staged diff ADDS:

- `noqa`, `type: ignore`, `ruff: noqa`, `eslint-disable` (any form,
  including `eslint-disable-next-line`), `oxlint-disable` — in `*.py`,
  `*.js`, `*.jsx`, `*.ts`, `*.tsx`, `*.mjs`, `*.cjs`, **where a linter
  would actually read it**;
- any new ENTRY in `_typos.toml` or `dead_allowlist.txt` — those files ARE
  the allowlist, so one added entry is one silenced warning.

FAIL evidence: the added line the grep prints.

Fix when blocked: change the code. Narrow the type instead of ignoring it,
delete the dead symbol instead of allowlisting it, spell the word correctly
or rename the identifier. When the warning really is a false positive or a
genuine domain term, the allowlist entry is the right answer — take it
through the `Rules-Waive: rule-no-lint-silencers - <reason>` trailer, which
leaves the decision permanently auditable in `git log`.

## What each pass counts, and why

**It used to be two bare greps, and both counted the wrong things.**
`check.sh` is now a shim over `_silencers.py`, which runs the same
`rules-grep` — so the commit lane still judges only ADDED lines, `AMG_HOOKS_SWEEP=1`
still walks the whole INDEX, and `.amg-hooks-exclude` still applies — and then
subtracts what a grep cannot tell apart.

Four passes, not two. The source pass is split by LANGUAGE because the
commit lane's `git diff` output carries no path: a pass per language is the
only way a bare added line is known to be Python or TypeScript. The two
pathspecs union to exactly the one they replaced, so the population is
unchanged and only the filter moves the count.

### The directive passes: a position, not a token

A directive is counted where the linter that owns it would honour it, and
the two families differ (`_directives.py` carries each rule):

| where the token sits | verdict |
|---|---|
| comment body opens with it (JS) | reported |
| after any `#` in a Python comment | reported |
| in prose later in a comment (JS) | not reported |
| in a `*`-led JSDoc continuation | not reported |
| inside a string literal | not reported |
| inside a Python docstring | not reported |

The JS row is ESLint's own grammar: it trims the whole comment body and
matches the directive at its head. That is why `/*` on one line and a bare
`eslint-disable` on the next IS reported — a whole-file rule switch must not
be waved through because its opener sits above the match.

The Python row is ruff's: it reads every `#` on a line, so a comment that
quotes the remedy really does apply a blanket noqa to itself. That is a
silencer, and it is reported.

### The allowlist passes: an entry, not a line

`dead_allowlist.txt` is one symbol per line, so every non-comment, non-blank
line is an entry. `_typos.toml` is a TOML document, and an entry there is a
key bound to a value or an element of an array — never the syntax holding
them up (`_entries.py`).

The classifier is line-oriented rather than a `tomllib` parse because both
lanes need line numbers, which a whole-file parse throws away, and the
commit lane is handed one added line with no document around it.
`test_the_entry_count_agrees_with_tomllib` validates it against a real parse
instead of against itself.

**An entry counts only when it has no preceding WHY comment.** An allowlist
entry with a written reason is linter CONFIGURATION, not a silencer — the
house directive is no per-line silencers, and when a rule is wrong for a
whole category the fix is to narrow the rule's scope once (with the reason
on the record), never to relitigate the same line forever. `_entries.py`'s
`is_documented` walks upward from an entry over blank lines, other entries,
and (`toml` only) the `key = [` / `]` around an array — that bracket pair
silences nothing itself, so it no more blocks a governing comment from
reaching what it holds than a blank line does. It stops, documented, at a
`#` comment; it stops, not documented, at a table header (`toml` only) or
the top of the file. Checked directly against the real
`dead_allowlist.txt` and `_typos.toml`: one header can document a whole
block of symbols, and one comment can document a small group of typos
keys — including the 17-element `extend-exclude` array, whose only comment
sits above the `extend-exclude = [` that opens it, which is why the walk
has to treat that bracket as transparent rather than as a boundary.

`is_documented` and its whole-file counterpart `undocumented_lines` take
the file's lines (or full text) directly, because a preceding comment is
not visible from a single line — `is_entry`'s own signature, which
`_silencers.py` calls with exactly one line and no surrounding document,
is unchanged so both its existing call sites keep working.

`_silencers.py` wires the filter into both live lanes. The sweep lane
already holds the whole indexed blob, so it hands `is_documented` that
blob's lines directly. The commit lane cannot: `rules-grep`'s added-lines
stream carries no path and renumbers each hit to a position in that
stream, neither of which a neighbour walk can use. So the allowlist
passes' commit lane skips `rules-grep` and reads the same pinned staged
diff a second way, through `lib/amg_hooks/gitio.py`'s `staged_diff`, grouped into
hunks — under `-U0` a hunk's added lines are exactly consecutive lines of
the resulting file starting at its real line number, and are also exactly
"what this diff added," so a comment `is_documented` finds by walking one
hunk's own lines is always a comment this same commit also added. A
pre-existing comment one line above, itself untouched by the diff, never
enters the hunk and so cannot document anything there — the sweep lane may
call the same tree clean once the commit lands, but the commit that adds
only the entry is judged on what it, itself, adds.

## The two false-positive shapes, and the file:line that proved each

**Prose that NAMES a directive.**
`aii_frontend/eslint.react-compiler.mjs` was reported twice: `:25` explains
that its stub plugins exist for rule names that
`// eslint-disable-next-line` comments elsewhere reference, and `:45` says
the ESLint pass suppresses "unused eslint-disable directive" warnings.
Neither is in a position any linter reads. That file is the one place in the
repo whose job is to talk about disable comments, so the bare grep charged
it for writing its own explanation — and both hits were permanent debt,
since the only way to clear them was to delete the prose.

**TOML syntax.** In `_typos.toml` the old `^[^#[:space:]]` anchor matched
`:15` `[default.extend-identifiers]`, `:26` `[default.extend-words]`, `:120`
`[files]`, `:122` `extend-exclude = [` and `:174` `]`. None silences
anything, and every one of them would come back the moment the file was
reformatted. The same anchor could not see what those brackets CONTAIN: a
TOML array element is indented, so the 17 `extend-exclude` paths — each
dropping a whole subtree from `typos`, a far broader silence than any single
word — were the one thing the pass missed. Over-counting syntax while
under-counting the allowlist is the worst of both.

## Vacuity bails

A check that examined nothing must not read as clean, so `_silencers.py`
exits 2 with `cannot run:` on each of these rather than printing an empty
verdict:

| bail | when |
|---|---|
| not inside a git work tree | no index to judge |
| `rules-grep exited N` | the grep itself failed |
| `unparseable finding` | output is not `path:line:text` |
| `cannot read <p> from index` | a blob will not read back |
| `<p>:<n> past end of blob` | the index moved mid-run |

The first exists because `rules-grep` cannot supply it: its `if hits=$(git
grep …)` reads a non-match and a fatal 128 alike, so run outside a
repository it exits 0 and the hook would go green having searched nothing.

The whole-index lane reads blobs with `git cat-file blob :<path>`, never the
working copy — the same snapshot `rules-grep --cached` just searched, so a
peer's unstaged edit in a shared checkout is not judged with your commit.
An index entry that will not read back is a bail, not an excused hit.

## Measured

research-monorepo, whole-index lane, 2026-09-10 — **299 -> 309**:

| change | count |
|---|---|
| prose dropped (both in one file) | -2 |
| TOML syntax dropped | -5 |
| TOML array elements added | +17 |

The count went UP, and that is the point: the 17 additions are path
exclusions, the widest silences in the file, and nothing was watching them.
The 7 subtractions are lines no author could have fixed.

notes-repo, measured 2026-09-07 with the bare grep and not re-measured since:
**110 silencer comments in 79 of the 630 in-scope source files** — 70 of the
110 under `apps/lantern/`, 27 under `areas/food/` — with 35
entries in `_typos.toml` (143 lines, the rest comment and blank) and 194 in
`dead_allowlist.txt` (309 lines). Those are pre-filter numbers: expect the
comment half to fall and the `_typos.toml` half to rise when it is measured
again. That stock is a cleanup backlog, not a gate — it prints as an
advisory in all-mode and blocks nothing.

Scope excludes any `.claude/` tree — which is also where the engine's own
silencers live, wherever the engine is currently checked out — plus whatever
the consumer's `.amg-hooks-exclude` list adds (an `archive/` or a vendored
`resources/skills/` belongs there).

Mode: ADDED LINES. `test_no_lint_silencers_bites.py` pins both lanes, both
false-positive shapes, the shapes that must still bite, and the bails.

Delete-check: cannot delete while the hooks exist — this rule is what keeps
"the hook is green" meaning "the code is right" rather than "the warning was
turned off".
